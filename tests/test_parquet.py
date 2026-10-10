"""Immutable optional Parquet bundle persistence and hostile import cases."""

from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core.data import Bar, DataMetadata, Dividend, Security, Snapshot, Split
from quant_core.data.parquet import ParquetSource, load_parquet_snapshot, save_parquet_snapshot
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.provenance import canonical_json, content_hash


def snapshot():
    day = date(2024, 1, 2)
    return Snapshot((day, date(2024, 1, 3)),
                    (Bar("ID", day, "100.000000000000000000001", "101", "99", "1.00E+2", "1000"),),
                    DataMetadata("synthetic", datetime(2024, 1, 4, tzinfo=timezone.utc),
                                 "supplied_panel", True, "explicit"),
                    (Security("ID", "SYNTH", "TEST", day),),
                    (Split("ID", day, "1.25"),
                     Dividend("ID", day, "0.123456789012345678901", date(2024, 1, 4))))


def rewrite_manifest(path, mutate):
    envelope = json.loads((path / "manifest.json").read_text())
    mutate(envelope["manifest"])
    envelope["manifest_hash"] = content_hash(envelope["manifest"])
    (path / "manifest.json").write_text(canonical_json(envelope), encoding="utf-8")


class DependencyTests(unittest.TestCase):
    def test_missing_pyarrow_is_actionable_and_creates_no_output(self):
        with TemporaryDirectory() as directory, patch.dict("sys.modules", {"pyarrow": None}):
            path = Path(directory) / "bundle"
            with self.assertRaisesRegex(ImportError, "Parquet.*pyarrow"):
                save_parquet_snapshot(snapshot(), path)
            self.assertFalse(path.exists())
            with self.assertRaisesRegex(ImportError, "Parquet.*pyarrow"):
                load_parquet_snapshot(path)


@unittest.skipUnless(importlib.util.find_spec("pyarrow"), "optional pyarrow not installed")
class ParquetTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "access-mode probe uses POSIX fcntl")
    def test_durability_sync_uses_writable_descriptors(self):
        import fcntl
        from quant_core.data import parquet
        real_fsync = os.fsync

        def checked(descriptor):
            if fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY:
                raise AssertionError("fsync on a read-only descriptor fails on Windows")
            return real_fsync(descriptor)

        with TemporaryDirectory() as folder, patch.object(parquet.os, "fsync", side_effect=checked):
            save_parquet_snapshot(snapshot(), Path(folder) / "bundle")

    def test_exact_decimal_roundtrip_and_original_dataset_hash_with_json_compatibility(self):
        import pyarrow.parquet as pq
        data = snapshot()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bundle"
            save_parquet_snapshot(data, path)
            loaded = ParquetSource(path).load()
            self.assertEqual(loaded, data)
            self.assertEqual(loaded.dataset_hash, data.dataset_hash)
            self.assertEqual(loaded.bars[0].open, Decimal("100.000000000000000000001"))
            rows = pq.read_table(path / "bars.parquet").to_pylist()
            self.assertEqual(rows[0]["open"], "100.000000000000000000001")
            legacy = Path(directory) / "snapshot.json"
            save_snapshot(loaded, legacy)
            self.assertEqual(load_snapshot(legacy), data)

    def test_empty_bar_table_retains_explicit_schema(self):
        data = snapshot()
        data = Snapshot(data.sessions, (), data.metadata, data.securities, data.actions)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bundle"
            save_parquet_snapshot(data, path)
            self.assertEqual(load_parquet_snapshot(path), data)

    def test_schema_two_exact_split_counts_roundtrip_through_parquet_and_json(self):
        data = snapshot()
        action = Split("ID", data.sessions[0], new_shares=1, old_shares=3)
        data = Snapshot(data.sessions, data.bars, data.metadata, data.securities, (action,))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bundle"
            save_parquet_snapshot(data, path)
            loaded = load_parquet_snapshot(path)
            self.assertEqual(loaded.dataset_hash, data.dataset_hash)
            self.assertEqual(loaded.actions[0].new_shares, 1)
            self.assertEqual(loaded.actions[0].old_shares, 3)
            json_path = Path(directory) / "exact.json"
            save_snapshot(loaded, json_path)
            self.assertEqual(load_snapshot(json_path), data)

    def test_never_overwrite_any_existing_output(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bundle"
            path.mkdir()
            with self.assertRaises(FileExistsError):
                save_parquet_snapshot(snapshot(), path)
            self.assertEqual(list(path.iterdir()), [])
            file = Path(directory) / "already.txt"
            file.write_text("keep")
            with self.assertRaises(FileExistsError):
                save_parquet_snapshot(snapshot(), file)
            self.assertEqual(file.read_text(), "keep")

    def test_write_or_publication_failure_leaves_no_partial_bundle(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bundle"
            for target in ("quant_core.data.parquet.os.link", "pyarrow.parquet.write_table"):
                with self.subTest(target=target), patch(target, side_effect=OSError("injected")):
                    with self.assertRaises(OSError):
                        save_parquet_snapshot(snapshot(), path)
                self.assertFalse(path.exists())
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_corruption_missing_extra_files_and_manifest_tampering_rejected(self):
        operations = [lambda p: (p / "bars.parquet").write_bytes(b"broken"),
                      lambda p: (p / "bars.parquet").unlink(),
                      lambda p: (p / "extra.parquet").write_bytes(b"extra"),
                      lambda p: (p / "manifest.json").write_text("{}")]
        for operation in operations:
            with self.subTest(operation=operation), TemporaryDirectory() as directory:
                path = Path(directory) / "bundle"
                save_parquet_snapshot(snapshot(), path)
                operation(path)
                with self.assertRaises(ValueError):
                    load_parquet_snapshot(path)

    def test_bound_metadata_and_original_hash_cannot_diverge(self):
        for operation in (lambda m: m.update(dataset_hash="a" * 64),
                          lambda m: m["snapshot"]["metadata"].update(source="changed"),
                          lambda m: m.update(schema_version=True),
                          lambda m: m["snapshot"].update(schema_version=99),
                          lambda m: m["files"]["bars.parquet"].update(rows=99)):
            with self.subTest(operation=operation), TemporaryDirectory() as directory:
                path = Path(directory) / "bundle"
                save_parquet_snapshot(snapshot(), path)
                rewrite_manifest(path, operation)
                with self.assertRaises(ValueError):
                    load_parquet_snapshot(path)

    def test_valid_hash_does_not_bypass_parquet_schema_or_decimal_validation(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        for field, value in (("open", 100.0), ("open", "NaN"), ("session", "20240102"),
                             ("close", None)):
            with self.subTest(field=field, value=value), TemporaryDirectory() as directory:
                path = Path(directory) / "bundle"
                save_parquet_snapshot(snapshot(), path)
                original = pq.read_table(path / "bars.parquet")
                rows = original.to_pylist()
                rows[0][field] = value
                table = pa.Table.from_pylist(rows, schema=original.schema if value is not None and not isinstance(value, float) else None)
                pq.write_table(table, path / "bars.parquet")
                raw = (path / "bars.parquet").read_bytes()

                def rebind(m):
                    m["files"]["bars.parquet"].update(sha256=sha256(raw).hexdigest(), size_bytes=len(raw))
                    m["dataset_hash"] = content_hash(dict(m["snapshot"], bars=rows))

                rewrite_manifest(path, rebind)
                with self.assertRaises(ValueError):
                    load_parquet_snapshot(path)


if __name__ == "__main__":
    unittest.main()
