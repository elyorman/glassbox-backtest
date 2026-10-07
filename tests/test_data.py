"""Independent synthetic examples for the initial market-data contract."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core.cli import main
from quant_core.data import (
    Bar, CashDelisting, DataMetadata, Dividend, Security, Snapshot, Split, number,
)
from quant_core.data.csv_source import CsvSource
from quant_core.data.quality import check_quality
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.provenance import canonical_json, content_hash

FIXTURES = Path(__file__).parent / "fixtures" / "data"
DAYS = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
META = DataMetadata("synthetic", datetime(2024, 1, 5, tzinfo=timezone.utc),
                    "fixed_synthetic_universe", True, "synthetic_explicit_sessions")


def bar(day=DAYS[0], price="100", asset="A", volume="1000"):
    return Bar(asset, day, price, price, price, price, volume)


def snapshot(bars=None, actions=(), securities=None, metadata=META):
    return Snapshot(DAYS, tuple(bars) if bars is not None else tuple(bar(d) for d in DAYS),
                    metadata, tuple(securities) if securities is not None else (Security("A", "AAA", "SYNTHETIC"),),
                    tuple(actions))


def csv_source():
    return CsvSource(FIXTURES / "bars.csv", FIXTURES / "calendar.csv",
                     FIXTURES / "securities.csv", META, FIXTURES / "actions.csv")


class SchemaTests(unittest.TestCase):
    def test_exact_decimals_and_rejection_of_ambiguous_numbers(self):
        self.assertEqual(number("0.1") + number("0.2"), Decimal("0.3"))
        for invalid in (0.1, True, "NaN", "Infinity", "bad", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                number(invalid)

    def test_invalid_ohlc_and_volume_rejected(self):
        for values in (("0", "2", "1", "1", "10"), ("2", "1", "1", "2", "10"),
                       ("2", "3", "3", "2", "10"), ("2", "3", "1", "2", "-1")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Bar("A", DAYS[0], *values)

    def test_dates_and_identity_validated(self):
        with self.assertRaises(ValueError):
            bar(datetime(2024, 1, 2))
        with self.assertRaises(ValueError):
            bar(asset=" A ")
        with self.assertRaises(ValueError):
            replace(META, retrieved_at=datetime(2024, 1, 5))
        with self.assertRaises(ValueError):
            replace(META, adjustment_policy="split_adjusted")
        with self.assertRaises(ValueError):
            replace(META, actions_complete="yes")

    def test_corporate_action_bounds(self):
        for action in (lambda: Split("A", DAYS[0], "0"),
                       lambda: Dividend("A", DAYS[1], "1", DAYS[0]),
                       lambda: Dividend("A", DAYS[0], "-1", DAYS[1]),
                       lambda: CashDelisting("A", DAYS[0], "-1")):
            with self.assertRaises(ValueError):
                action()

    def test_calendar_requires_unique_ascending_dates(self):
        for sessions in ((), tuple(reversed(DAYS)), (DAYS[0], DAYS[0]), ("2024-01-02",)):
            with self.subTest(sessions=sessions), self.assertRaises(ValueError):
                replace(snapshot(), sessions=sessions)

    def test_duplicate_bars_and_off_calendar_bar_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            snapshot((bar(), bar()))
        with self.assertRaisesRegex(ValueError, "calendar"):
            snapshot((bar(date(2024, 1, 6)),))

    def test_registry_identity_and_lifetimes(self):
        with self.assertRaisesRegex(ValueError, "unknown security"):
            snapshot((bar(asset="X"),))
        with self.assertRaisesRegex(ValueError, "unique"):
            snapshot(securities=(Security("A", "AAA", "X"), Security("A", "BBB", "X")))
        with self.assertRaisesRegex(ValueError, "lifetime"):
            snapshot(securities=(Security("A", "AAA", "X", listed_on=DAYS[1]),))
        with self.assertRaises(ValueError):
            Security("A", "AAA", "X", listed_on=DAYS[1], delisted_on=DAYS[0])

    def test_action_identity_duplicates_and_delisting_effective_date(self):
        split = Split("A", DAYS[1], "2")
        with self.assertRaisesRegex(ValueError, "Duplicate corporate"):
            snapshot(actions=(split, split))
        with self.assertRaisesRegex(ValueError, "unknown security"):
            snapshot(actions=(Split("X", DAYS[0], "2"),))
        with self.assertRaisesRegex(ValueError, "match registry"):
            snapshot(actions=(CashDelisting("A", DAYS[2], "0"),))
        valid = snapshot((bar(DAYS[0]), bar(DAYS[1])), (CashDelisting("A", DAYS[2], "0"),),
                         (Security("A", "AAA", "X", delisted_on=DAYS[2]),))
        self.assertFalse(check_quality(valid).has_errors)

    def test_immutable_snapshot_canonicalizes_input_order(self):
        first = snapshot()
        second = snapshot(tuple(reversed(first.bars)))
        self.assertEqual(first.dataset_hash, second.dataset_hash)
        with self.assertRaises(FrozenInstanceError):
            first.metadata.source = "other"
        bars = list(first.bars)
        stable = snapshot(bars)
        bars.clear()
        self.assertEqual(len(stable.bars), 3)

    def test_observation_and_metadata_changes_change_hash(self):
        base = snapshot()
        changed = snapshot((bar(DAYS[0], "101"), bar(DAYS[1]), bar(DAYS[2])))
        self.assertNotEqual(base.dataset_hash, changed.dataset_hash)
        self.assertNotEqual(base.dataset_hash, replace(base, metadata=replace(META, source="other")).dataset_hash)

    def test_iterable_inputs_are_not_consumed_during_validation(self):
        expected = snapshot()
        actual = Snapshot(iter(DAYS), iter(expected.bars), META, iter(expected.securities))
        self.assertEqual(actual, expected)

    def test_provenance_sequences_are_validated(self):
        for change in ({"limitations": "unstructured"}, {"input_hashes": (("bars", "not-a-hash"),)},
                       {"input_hashes": (("bars", "a" * 64), ("bars", "b" * 64))}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(META, **change)


class QualityTests(unittest.TestCase):
    def test_missing_session_is_an_error_without_fabrication(self):
        data = snapshot((bar(DAYS[0]), bar(DAYS[2])))
        report = check_quality(data)
        self.assertTrue(report.has_errors)
        missing = [issue for issue in report.issues if issue.code == "missing_bar"]
        self.assertEqual([issue.session for issue in missing], [DAYS[1]])
        self.assertEqual(len(data.bars), 2)

    def test_completely_absent_security_is_detected(self):
        report = check_quality(snapshot(securities=(Security("A", "AAA", "X"), Security("B", "BBB", "X"))))
        self.assertEqual(sum(issue.security_id == "B" for issue in report.issues), 3)

    def test_lifetimes_exclude_pre_listing_and_post_delisting(self):
        data = snapshot((bar(DAYS[1]),), securities=(Security("A", "AAA", "X", DAYS[1], DAYS[2]),))
        report = check_quality(data)
        self.assertFalse(report.has_errors)
        self.assertEqual([issue.code for issue in report.issues], ["missing_delisting_settlement"])

    def test_known_split_does_not_trigger_false_price_jump(self):
        data = snapshot((bar(DAYS[0]), bar(DAYS[1], "25"), bar(DAYS[2], "25")),
                        (Split("A", DAYS[1], "4"),))
        self.assertFalse(check_quality(data).issues)
        without_action = replace(data, actions=())
        self.assertEqual([issue.code for issue in check_quality(without_action).issues], ["price_discontinuity"])

    def test_incomplete_actions_and_zero_volume_are_visible(self):
        report = check_quality(snapshot((bar(DAYS[0], volume="0"), bar(DAYS[1]), bar(DAYS[2])),
                                        metadata=replace(META, actions_complete=False, limitations=("static universe",))))
        self.assertEqual({issue.code for issue in report.issues},
                         {"zero_volume", "actions_incomplete", "source_limitation"})
        self.assertFalse(report.has_errors)
        self.assertFalse(report.actions_declared_complete)


class ImportAndStorageTests(unittest.TestCase):
    def test_csv_preserves_raw_bytes_and_records_exact_input_hashes(self):
        source = csv_source()
        before = source.bars_path.read_bytes()
        data = source.load()
        self.assertEqual(source.bars_path.read_bytes(), before)
        self.assertEqual(dict(data.metadata.input_hashes)["bars"], sha256(before).hexdigest())
        self.assertEqual((len(data.bars), len(data.securities), len(data.actions)), (6, 2, 2))
        self.assertFalse(check_quality(data).issues)
        self.assertEqual(source.load().dataset_hash, data.dataset_hash)

    def test_csv_malformed_headers_rows_and_values(self):
        samples = (
            "security_id,session_date,open,high,low,close,volume,adjusted_close\n",
            "security_id,session_date,open,high,low,close,close\n",
            "security_id,session_date,open,high,low,close,volume\nA,2024-01-02,10\n",
            "security_id,session_date,open,high,low,close,volume\nA,2024-01-02,10,10,10,10,1,extra\n",
            "security_id,session_date,open,high,low,close,volume\nA,2024-01-02,NaN,10,10,10,1\n",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            for sample in samples:
                path.write_text(sample, encoding="utf-8")
                with self.subTest(sample=sample), self.assertRaisesRegex(ValueError, "bad.csv"):
                    replace(csv_source(), bars_path=path).load()

    def test_csv_rejects_unexpected_action_fields(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad-actions.csv"
            path.write_text("kind,security_id,session_date,ratio,amount,pay_date\n"
                            "Split,SYNTH-A,2024-01-03,2,1,\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bad-actions.csv:2"):
                replace(csv_source(), actions_path=path).load()

    def test_snapshot_round_trip_preserves_actions_and_identity(self):
        data = csv_source().load()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            save_snapshot(data, path)
            loaded = load_snapshot(path)
            self.assertEqual(loaded, data)
            self.assertEqual(loaded.dataset_hash, data.dataset_hash)
            self.assertIsInstance(loaded.actions[0], Split)
            self.assertIsInstance(loaded.actions[1], Dividend)

    def test_storage_never_overwrites_existing_snapshot(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            save_snapshot(snapshot(), path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                save_snapshot(snapshot(), path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_failed_snapshot_publication_leaves_no_partial_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            with patch("quant_core.data.storage.os.link", side_effect=OSError("publication failed")):
                with self.assertRaises(OSError):
                    save_snapshot(snapshot(), path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_corrupted_snapshot_detected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            save_snapshot(snapshot(), path)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["snapshot"]["bars"][0]["close"] = "99"
            path.write_text(canonical_json(envelope), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity"):
                load_snapshot(path)

    def test_unsupported_schema_rejected_even_with_valid_hash(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            save_snapshot(snapshot(), path)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["snapshot"]["schema_version"] = 99
            envelope["dataset_hash"] = content_hash(envelope["snapshot"])
            path.write_text(canonical_json(envelope), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema version"):
                load_snapshot(path)


class CliTests(unittest.TestCase):
    def import_args(self, output):
        return ["import-csv", "--bars", str(FIXTURES / "bars.csv"),
                "--calendar", str(FIXTURES / "calendar.csv"),
                "--securities", str(FIXTURES / "securities.csv"),
                "--actions", str(FIXTURES / "actions.csv"), "--output", str(output),
                "--source", "synthetic", "--retrieved-at", "2024-01-05T00:00:00+00:00",
                "--universe-policy", "fixed_synthetic_universe", "--calendar-name", "synthetic",
                "--actions-complete"]

    def test_import_then_inspect_reports_identical_snapshot(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "data.json"
            first, second = StringIO(), StringIO()
            with redirect_stdout(first):
                self.assertEqual(main(self.import_args(output)), 0)
            with redirect_stdout(second):
                self.assertEqual(main(["inspect", str(output)]), 0)
            self.assertEqual(first.getvalue(), second.getvalue())
            self.assertFalse(json.loads(first.getvalue())["has_errors"])

    def test_missing_bars_prevent_persistence(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "data.json"
            bars_path = Path(directory) / "missing.csv"
            original = (FIXTURES / "bars.csv").read_text(encoding="utf-8").splitlines()
            bars_path.write_text("\n".join(line for line in original if "2024-01-03" not in line) + "\n",
                                 encoding="utf-8")
            args = self.import_args(output)
            args[args.index("--bars") + 1] = str(bars_path)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(args), 1)
            self.assertFalse(output.exists())

    def test_errors_are_actionable_without_traceback(self):
        error = StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["inspect", "/not-a-real-snapshot.json"]), 2)
        self.assertIn("Data error:", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
