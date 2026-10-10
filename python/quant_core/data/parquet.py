"""Optional exact-decimal Parquet snapshot bundles with byte-bound manifests.

Decimal text avoids lossy floats or a fixed Arrow decimal scale/precision cap.
The provider-neutral bundle retains the original normalized snapshot hash.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from quant_core.data import Snapshot, snapshot_payload
from quant_core.provenance import canonical_json, content_hash


def _arrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError("Parquet support requires optional pyarrow; install quant-platform-core[parquet]") from None
    return pa, pq


def _bar_schema(pa):
    return pa.schema([pa.field(name, pa.string(), nullable=False) for name in
                      ("security_id", "session", "open", "high", "low", "close", "volume")])


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest field")
        result[key] = value
    return result


def save_parquet_snapshot(snapshot: Snapshot, path: Path) -> None:
    """Save a new directory; existing files/directories are never replaced.

    All bytes are staged first. Exclusive directory creation reserves publication,
    then bars are linked before the manifest commit marker. Caught failures remove
    our published files; interruption can leave an incomplete, rejected directory.
    """
    pa, pq = _arrow()
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Parquet output already exists")
    if not isinstance(snapshot, Snapshot):
        raise ValueError("Parquet export requires a Snapshot")
    payload = snapshot_payload(snapshot)
    rows = payload.pop("bars")
    path.parent.mkdir(parents=True, exist_ok=True)
    published = []
    reserved = False
    with TemporaryDirectory(prefix=".parquet-", dir=path.parent) as directory:
        staging = Path(directory)
        bar_path = staging / "bars.parquet"
        table = pa.Table.from_pylist(rows, schema=_bar_schema(pa))
        pq.write_table(table, bar_path, compression="zstd")
        with bar_path.open("r+b") as stream:  # Windows requires write access to flush to disk.
            os.fsync(stream.fileno())
        raw = bar_path.read_bytes()
        manifest = {"schema_version": 1, "dataset_hash": snapshot.dataset_hash,
                    "snapshot": payload,
                    "files": {"bars.parquet": {"sha256": sha256(raw).hexdigest(),
                                               "size_bytes": len(raw), "rows": len(rows)}}}
        envelope = {"manifest_hash": content_hash(manifest), "manifest": manifest}
        with (staging / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical_json(envelope) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            path.mkdir()  # Exclusive, even if another exporter raced our first check.
            reserved = True
            for name in ("bars.parquet", "manifest.json"):
                os.link(staging / name, path / name)
                published.append(path / name)
        except BaseException:
            for file in reversed(published):
                file.unlink(missing_ok=True)
            if reserved:
                path.rmdir()
            raise


def load_parquet_snapshot(path: Path) -> Snapshot:
    """Verify every byte and the normalized domain hash before accepting a bundle."""
    pa, pq = _arrow()
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Not a Parquet bundle directory")
        if {file.name for file in path.iterdir()} != {"bars.parquet", "manifest.json"}:
            raise ValueError("Unexpected or missing bundle files")
        if any((path / name).is_symlink() or not (path / name).is_file()
               for name in ("bars.parquet", "manifest.json")):
            raise ValueError("Bundle requires regular files")
        envelope = json.loads((path / "manifest.json").read_bytes(), object_pairs_hook=_object)
        if not isinstance(envelope, dict) or set(envelope) != {"manifest", "manifest_hash"}:
            raise ValueError("Invalid manifest envelope")
        manifest = envelope["manifest"]
        if not _digest(envelope["manifest_hash"]) or content_hash(manifest) != envelope["manifest_hash"]:
            raise ValueError("Manifest integrity mismatch")
        if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "dataset_hash", "snapshot", "files"}:
            raise ValueError("Invalid manifest fields")
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
            raise ValueError("Unsupported Parquet bundle schema")
        if not _digest(manifest["dataset_hash"]):
            raise ValueError("Invalid original snapshot hash")
        header = manifest["snapshot"]
        if not isinstance(header, dict) or set(header) != {"schema_version", "sessions", "metadata", "securities", "actions"}:
            raise ValueError("Invalid snapshot header")
        files = manifest["files"]
        if not isinstance(files, dict) or set(files) != {"bars.parquet"}:
            raise ValueError("Invalid manifest file list")
        entry = files["bars.parquet"]
        if not isinstance(entry, dict) or set(entry) != {"sha256", "size_bytes", "rows"}:
            raise ValueError("Invalid file metadata")
        if (not _digest(entry["sha256"]) or type(entry["size_bytes"]) is not int
                or entry["size_bytes"] < 0 or type(entry["rows"]) is not int or entry["rows"] < 0):
            raise ValueError("Invalid file hash, size or row count")
        raw = (path / "bars.parquet").read_bytes()
        if len(raw) != entry["size_bytes"] or sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Parquet file integrity mismatch")
        # Consume the exact verified buffer; do not reopen a mutable path.
        table = pq.read_table(pa.BufferReader(raw))
        if not table.schema.equals(_bar_schema(pa), check_metadata=True) or table.num_rows != entry["rows"]:
            raise ValueError("Invalid Parquet bar schema or row count")
        rows = table.to_pylist()
        for row in rows:
            if any(not isinstance(value, str) for value in row.values()):
                raise ValueError("Null or non-text bar value")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["session"]):
                raise ValueError("Invalid bar session date")
        payload = dict(header, bars=rows)
        if content_hash(payload) != manifest["dataset_hash"]:
            raise ValueError("Original snapshot integrity mismatch")
        from quant_core.data.storage import snapshot_from_payload
        snapshot = snapshot_from_payload(payload)
        if snapshot.dataset_hash != manifest["dataset_hash"]:
            raise ValueError("Noncanonical snapshot payload")
        return snapshot
    except ImportError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ArithmeticError):
        # Neither hostile JSON text nor Arrow's error bodies are user diagnostics.
        raise ValueError("Invalid Parquet snapshot bundle: integrity, schema or domain validation failed") from None


@dataclass(frozen=True)
class ParquetSource:
    path: Path

    def load(self) -> Snapshot:
        return load_parquet_snapshot(self.path)
