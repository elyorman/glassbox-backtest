"""Hand-calculated historical membership, availability and local import checks."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.universes import (
    DatedUniverse, MembershipInterval, UniverseAvailabilityError, UniverseCoverageError,
)
from quant_core.universes.csv_source import import_membership_csv
from quant_core.universes.cli import main


def day(number):
    return date(2024, 1, number)


def universe(intervals=None, **changes):
    result = DatedUniverse(
        "synthetic-index", day(2), day(10),
        (MembershipInterval("A", day(2), day(1), day(5), day(4)),
         MembershipInterval("B", day(4), day(3)),
         MembershipInterval("A", day(8), day(7))) if intervals is None else intervals,
        "hand-calculated synthetic", datetime(2024, 2, 1, tzinfo=timezone.utc),
        day(1), limitations=("Synthetic engineering fixture, not empirical qualification",),
    )
    return replace(result, **changes)


CSV = ("security_id,entered_on,entry_available_on,left_on,exit_available_on\n"
       "A,2024-01-02,2024-01-01,2024-01-05,2024-01-04\n"
       "B,2024-01-04,2024-01-03,,\n"
       "A,2024-01-08,2024-01-07,,\n")


class MembershipTests(unittest.TestCase):
    def test_add_remove_reenter_with_effective_boundaries(self):
        record = universe()
        for number, wanted in ((2, ("A",)), (3, ("A",)), (4, ("A", "B")),
                               (5, ("B",)), (7, ("B",)), (8, ("A", "B")), (10, ("A", "B"))):
            with self.subTest(day=number):
                self.assertEqual(record.members_on(day(number)), wanted)
        self.assertEqual(record.security_ids, ("A", "B"))

    def test_unknown_history_raises_and_known_empty_day_is_empty(self):
        record = universe(intervals=(MembershipInterval("A", day(4), day(3)),))
        self.assertEqual(record.members_on(day(2)), ())
        for value in (day(1), day(11)):
            with self.subTest(value=value), self.assertRaises(UniverseCoverageError):
                record.members_on(value)
        self.assertEqual(universe(intervals=()).members_on(day(4)), ())

    def test_announced_addition_waits_for_effective_date(self):
        record = universe(intervals=(MembershipInterval("A", day(5), day(2)),))
        self.assertEqual(record.members_on(day(4)), ())
        self.assertEqual(record.members_on(day(5)), ("A",))

    def test_future_exit_need_not_be_announced_at_entry(self):
        record = universe(intervals=(MembershipInterval("A", day(2), day(1), day(8), day(7)),))
        self.assertEqual(record.members_on(day(2)), ("A",))
        self.assertEqual(record.members_on(day(7)), ("A",))
        self.assertEqual(record.members_on(day(8)), ())

    def test_unavailable_addition_does_not_silently_omit_member(self):
        record = universe(intervals=(MembershipInterval("A", day(4), day(6)),))
        self.assertEqual(record.members_on(day(3)), ())
        for number in (4, 5):
            with self.subTest(number=number), self.assertRaises(UniverseAvailabilityError):
                record.members_on(day(number))
        self.assertEqual(record.members_on(day(6)), ("A",))

    def test_unavailable_exit_does_not_leak_retroactive_removal(self):
        record = universe(intervals=(MembershipInterval("A", day(2), day(1), day(5), day(7)),))
        self.assertEqual(record.members_on(day(4)), ("A",))
        for number in (5, 6):
            with self.subTest(number=number), self.assertRaises(UniverseAvailabilityError):
                record.members_on(day(number))
        self.assertEqual(record.members_on(day(7)), ())

    def test_missing_baseline_availability_raises_for_whole_snapshot(self):
        record = universe(coverage_available_on=day(4))
        with self.assertRaises(UniverseAvailabilityError):
            record.members_on(day(3))
        self.assertEqual(record.members_on(day(4)), ("A", "B"))

    def test_overlaps_rejected_but_adjacent_membership_allowed(self):
        for intervals in (
            (MembershipInterval("A", day(2), day(1)), MembershipInterval("A", day(5), day(4))),
            (MembershipInterval("A", day(2), day(1), day(6), day(5)),
             MembershipInterval("A", day(5), day(4))),
        ):
            with self.subTest(intervals=intervals), self.assertRaises(ValueError):
                universe(intervals=intervals)
        record = universe(intervals=(MembershipInterval("A", day(2), day(1), day(5), day(4)),
                                     MembershipInterval("A", day(5), day(4))))
        self.assertEqual(record.members_on(day(5)), ("A",))

    def test_invalid_identity_dates_and_provenance_rejected(self):
        for factory in (
            lambda: MembershipInterval(" A", day(2), day(1)),
            lambda: MembershipInterval("A", "2024-01-02", day(1)),
            lambda: MembershipInterval("A", day(2), day(1), day(2), day(1)),
            lambda: MembershipInterval("A", day(2), day(1), day(5)),
            lambda: MembershipInterval("A", day(2), day(1), None, day(5)),
            lambda: universe(coverage_end=day(1)),
            lambda: universe(retrieved_at=datetime(2024, 2, 1)),
            lambda: universe(source=""),
            lambda: universe(limitations="not a sequence"),
        ):
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()
        with self.assertRaises(ValueError):
            universe().members_on(datetime(2024, 1, 3, tzinfo=timezone.utc))


class PersistenceAndImportTests(unittest.TestCase):
    def test_canonical_roundtrip_preserves_provenance_and_rejects_overwrite(self):
        record = universe()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            record.save(path)
            before = path.read_bytes()
            loaded = DatedUniverse.load(path)
            self.assertEqual(loaded.members_on(day(5)), ("B",))
            self.assertEqual(loaded.limitations, record.limitations)
            self.assertEqual(loaded.retrieved_at, record.retrieved_at)
            self.assertEqual(loaded.content_hash(), record.content_hash())
            with self.assertRaises(FileExistsError):
                record.save(path)
            self.assertEqual(path.read_bytes(), before)

    def test_hash_is_order_independent_and_availability_sensitive(self):
        record = universe()
        self.assertEqual(record.content_hash(), replace(record, intervals=record.intervals[::-1]).content_hash())
        self.assertNotEqual(record.content_hash(), replace(record, coverage_available_on=day(2)).content_hash())
        self.assertNotEqual(record.content_hash(), replace(record, limitations=("new limitation",)).content_hash())

    def test_tampering_and_unknown_schemas_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            universe().save(path)
            envelope = json.loads(path.read_text())
            envelope["universe"]["coverage_start"] = "2024-01-03"
            path.write_text(json.dumps(envelope))
            with self.assertRaises(ValueError):
                DatedUniverse.load(path)
            payload = universe().to_dict()
            payload["schema_version"] = True
            with self.assertRaises(ValueError):
                DatedUniverse.from_dict(payload)
            payload = universe().to_dict()
            payload["extra"] = "ignored metadata would lose provenance"
            with self.assertRaises(ValueError):
                DatedUniverse.from_dict(payload)

    def test_malformed_hash_provenance_and_json_arrays_fail_with_value_error(self):
        for input_hashes in ((("a", "f" * 64), (3, "e" * 64)),
                             (("a", "f" * 64), ("a", "e" * 64)),
                             (("a", "bad"),), (None,)):
            with self.subTest(input_hashes=input_hashes), self.assertRaises(ValueError):
                universe(input_hashes=input_hashes)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.json"
            for text in ("null", "[{}]", "{}", "not JSON"):
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError):
                        DatedUniverse.load(path)

    def test_csv_import_preserves_bytes_hash_and_explicit_limitations(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "members.csv"
            path.write_text(CSV)
            before = path.read_bytes()
            record = import_membership_csv(path, universe_id="synthetic-index", coverage_start=day(2),
                coverage_end=day(10), coverage_available_on=day(1), source="local historical export",
                retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc), limitations=("Corrections not qualified",))
            self.assertEqual(record.members_on(day(5)), ("B",))
            self.assertEqual(record.input_hashes, (("membership_csv", sha256(before).hexdigest()),))
            self.assertEqual(record.limitations, ("Corrections not qualified",))
            self.assertEqual(path.read_bytes(), before)

    def test_csv_malformed_records_and_headers_fail_closed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "members.csv"
            for text in (
                "security_id,entered_on,entry_available_on,left_on,left_on\n",
                CSV + "C,2024-01-05\n",
                CSV + "C,2024-01-05,2024-01-04,,,extra\n",
                CSV + "C,2024-01-05,2024-01-04,2024-01-08,\n",
                CSV.replace("2024-01-02", "not-a-date"),
            ):
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError):
                        import_membership_csv(path, universe_id="synthetic-index", coverage_start=day(2),
                            coverage_end=day(10), coverage_available_on=day(1), source="local",
                            retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc))

    def test_cli_import_query_and_coverage_failure(self):
        with TemporaryDirectory() as directory:
            source, target = Path(directory) / "members.csv", Path(directory) / "history.json"
            source.write_text(CSV)
            with redirect_stdout(StringIO()):
                code = main(["import-csv", "--input", str(source), "--output", str(target),
                    "--universe-id", "synthetic-index", "--coverage-start", "2024-01-02",
                    "--coverage-end", "2024-01-10", "--coverage-available-on", "2024-01-01",
                    "--source", "local historical export", "--retrieved-at", "2024-02-01T00:00:00+00:00",
                    "--limitation", "Synthetic only"])
            self.assertEqual(code, 0)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["members", "--input", str(target), "--date", "2024-01-05"]), 0)
            self.assertEqual(json.loads(output.getvalue())["members"], ["B"])
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["members", "--input", str(target), "--date", "2024-01-01"]), 2)


if __name__ == "__main__":
    unittest.main()
