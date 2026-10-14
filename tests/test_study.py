"""Registered studies on a synthetic dataset: the planned runs, their settings and every refusal."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.data import Bar, DataMetadata, Security, Snapshot
from quant_core.data.dataset import Dataset, save_dataset
from quant_core.data.rates import CashRateSeries
from quant_core.provenance import code_hash, content_hash
from quant_core.strategies.plans import DualMomentumPlan, TrendPlan, plan_to_dict
from quant_core.validation import study
from quant_core.validation.registration import parse_registration
from quant_core.validation.study import planned_runs, run_study
from quant_core.validation.study_cli import main
from test_registration import example

D = Decimal
AT = datetime(2024, 7, 1, tzinfo=timezone.utc)
# Three sessions a month from January 2022 to June 2024: 90 sessions.
SESSIONS = tuple(date(year, month, day) for year in (2022, 2023, 2024) for month in range(1, 13)
                 for day in (10, 20, 28) if date(year, month, day) <= date(2024, 6, 28))
PATTERNS = {"SPY": lambda i: 100 + i // 2 + (i * 7) % 11, "IEF": lambda i: 90 + (i * 3) % 5,
            "A": lambda i: 50 + i // 3 + (i * 5) % 9, "B": lambda i: 70 - i // 4 + (i * 11) % 13}


def synthetic_dataset(dataset_id="c" * 64):
    bars = tuple(Bar(asset, day, price(i), price(i), price(i), price(i), 1000000)
                 for asset, price in PATTERNS.items() for i, day in enumerate(SESSIONS))
    snapshot = Snapshot(SESSIONS, bars, DataMetadata("synthetic_study", AT, "fixed_engineering_sample", True,
                                                     "synthetic_sessions"),
                        tuple(Security(asset, asset, "TEST") for asset in PATTERNS))
    first = date(2021, 12, 1)
    rates = CashRateSeries("test", "test_bills", AT, tuple((first + timedelta(i), "0.04") for i in range(950)))
    return Dataset(snapshot, rates, {"dataset_id": dataset_id})


def trend(name, months):
    return plan_to_dict(TrendPlan(name=name, universe=("A", "B"), average_months=months, volume_lookback=2))


def study_payload(**changes):
    """The synthetic trend study: registered for this code and the synthetic dataset."""
    payload = example()
    payload.update(code_hash=code_hash(), dataset={"id": "c" * 64, "tickers": ["A", "B", "IEF", "SPY"]},
                   plan=trend("trend_fixture", 2),
                   neighbours=[trend("trend_fixture_3", 3), trend("trend_fixture_4", 4)],
                   period={"start": "2022-09-28", "end": "2024-05-28"},  # A month before the data ends.
                   publication={"date": "2023-06-01", "source": "A synthetic paper"},
                   segments=[{"name": "first year", "start": "2022-09-28", "end": "2023-09-28"}],
                   bootstrap={"block_lengths": [5, 20], "repetitions": 100, "seed": 1729})
    payload.update(changes)
    return payload


REGISTRATION = parse_registration(study_payload())
KEYS = ("plan-10bps", "plan-25bps", "plan-50bps", "plan-10bps-delay2", "plan-10bps-cash0", "shift-2-10bps",
        "shift+2-10bps", "neighbour-trend_fixture_3-10bps", "neighbour-trend_fixture_4-10bps") + tuple(
    f"{name}-{suffix}" for name in ("spy_buy_hold", "sixty_forty", "equal_weight", "tbills")
    for suffix in ("10bps", "25bps", "50bps", "10bps-cash0"))


class PlannedRunTests(unittest.TestCase):
    def test_every_declared_run_in_a_fixed_order(self):
        runs = planned_runs(REGISTRATION)
        self.assertEqual(tuple(run.key for run in runs), KEYS)
        by_key = {run.key: run for run in runs}
        self.assertEqual((by_key["plan-10bps-delay2"].delay, by_key["plan-10bps-cash0"].cash), (2, False))
        self.assertEqual(by_key["shift+2-10bps"].source.decision_offset, 2)
        self.assertEqual(by_key["shift-2-10bps"].source.name, "trend_fixture_shift_minus_2")
        self.assertEqual(by_key["sixty_forty-25bps"].source.weights, (("IEF", D("0.4")), ("SPY", D("0.6"))))
        self.assertEqual(by_key["equal_weight-10bps"].source.universe, ("A", "B"))
        self.assertIsNone(by_key["tbills-50bps"].source)
        self.assertEqual({run.role for run in runs},
                         {"plan", "delay", "cash0", "shift", "neighbour", "reference", "reference_cash0"})


class RunStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory()
        cls.output = Path(cls.directory.name) / "study"
        cls.results = run_study(REGISTRATION, synthetic_dataset(), cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_each_run_is_saved_once_under_its_key(self):
        self.assertEqual(tuple(self.results), KEYS)
        self.assertEqual(sorted(p.name for p in (self.output / "runs").iterdir()), sorted(KEYS))
        self.assertTrue(all((self.output / "runs" / key / "COMPLETE.json").exists() for key in KEYS))

    def test_runs_have_the_registered_settings(self):
        primary = self.results["plan-10bps"].manifest.config
        self.assertEqual((primary.start, primary.end, primary.initial_cash), (date(2022, 9, 28), date(2024, 5, 28),
                                                                             D(100000)))
        self.assertEqual({result.equity[-1].session for result in self.results.values()}, {date(2024, 5, 28)})
        self.assertEqual(self.results["plan-50bps"].manifest.config.execution.slippage_bps, 50)
        self.assertEqual(self.results["sixty_forty-50bps"].manifest.config.execution.slippage_bps, 50)
        self.assertEqual(self.results["plan-10bps-delay2"].manifest.config.execution_delay_sessions, 2)
        self.assertEqual({key for key, result in self.results.items() if result.manifest.config.cash_rates is None},
                         {key for key in KEYS if key.endswith("cash0")})
        self.assertIsNotNone(primary.cash_rates)
        self.assertEqual(self.results["neighbour-trend_fixture_4-10bps"].manifest.source.plan.average_months, 4)

    def test_variants_change_only_what_they_name(self):
        def choices(key):
            return [(d.session, d.security_id, d.selected) for d in self.results[key].signal_decisions]
        self.assertEqual(choices("plan-10bps"), choices("plan-10bps-cash0"))  # Decisions ignore idle-cash interest.
        sessions = {key: self.results[key].manifest.source.decision_sessions for key in ("plan-10bps", "shift+2-10bps")}
        self.assertNotEqual(sessions["plan-10bps"], sessions["shift+2-10bps"])

    def test_comparison_portfolios_hold_what_their_names_say(self):
        self.assertEqual(self.results["tbills-10bps"].fills, ())
        self.assertGreater(self.results["tbills-10bps"].equity[-1].interest_income, 0)
        self.assertEqual({f.side for f in self.results["spy_buy_hold-10bps"].fills}, {"buy"})
        self.assertEqual(len(self.results["spy_buy_hold-10bps"].fills), 1)
        self.assertEqual({f.security_id for f in self.results["sixty_forty-10bps"].fills}, {"IEF", "SPY"})
        self.assertEqual({f.security_id for f in self.results["equal_weight-10bps"].fills}, {"A", "B"})


class BillsTests(unittest.TestCase):
    def test_plans_that_compare_with_t_bills_get_them_even_with_idle_cash_at_zero(self):
        plan = DualMomentumPlan(name="dual_fixture", universe=("A", "B", "IEF"), us_stocks="A", non_us_stocks="B",
                                bonds="IEF", lookback_months=2, volume_lookback=2)
        for cash in (True, False):
            with self.subTest(cash=cash):
                result = study._run(study.PlannedRun("dual", "plan", plan, D(10), cash=cash), REGISTRATION,
                                    synthetic_dataset())
                self.assertEqual(result.manifest.config.cash_rates is not None, cash)
                self.assertTrue(any(d.selected for d in result.signal_decisions))


class RefusalTests(unittest.TestCase):
    def test_another_dataset_other_code_or_an_existing_output_is_refused(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "not the registered one"):
                run_study(REGISTRATION, synthetic_dataset("d" * 64), Path(directory) / "a")
            other = parse_registration(study_payload(code_hash="e" * 64))
            with self.assertRaisesRegex(ValueError, "check out the registration's tag"):
                run_study(other, synthetic_dataset(), Path(directory) / "b")
            Path(directory, "c").mkdir()
            with self.assertRaisesRegex(ValueError, "runs once"):
                run_study(REGISTRATION, synthetic_dataset(), Path(directory) / "c")
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["c"])  # Nothing else was written.


def saved_dataset(directory):
    """The synthetic dataset saved with a manifest that `load_dataset` accepts; returns its ID."""
    dataset = synthetic_dataset()
    manifest = {"schema_version": 1, "snapshot": {"dataset_hash": dataset.snapshot.dataset_hash},
                "rates": {"rates_hash": content_hash(dataset.rates)}}
    manifest["dataset_id"] = content_hash(manifest)
    return save_dataset(directory, Dataset(dataset.snapshot, dataset.rates, manifest))


def command(*args):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


class StudyCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.dataset_id = saved_dataset(self.root / "dataset")
        self.registration = self.register("trend-fixture")

    def tearDown(self):
        self.directory.cleanup()

    def register(self, study, **changes):
        path = self.root / f"{study}.json"
        path.write_text(json.dumps(study_payload(
            study=study, tag=f"study/{study}-2026-10-15",
            dataset={"id": self.dataset_id, "tickers": ["A", "B", "IEF", "SPY"]}, **changes)))
        return path

    def test_check_runs_nothing_and_run_writes_the_pack_once(self):
        code, out, err = command("check", self.registration, "--dataset", self.root / "dataset")
        self.assertEqual((code, err, json.loads(out)["status"], json.loads(out)["planned_runs"]), (0, "", "ready", 25))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["dataset", "trend-fixture.json"])
        output = self.root / "study"
        code, out, err = command("run", self.registration, "--dataset", self.root / "dataset", "--output", output)
        self.assertEqual((code, err), (0, ""))
        summary = json.loads(out)
        pack = json.loads((output / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual((summary["status"], summary["pack_hash"]), ("complete", content_hash(pack)))
        self.assertEqual(pack["registration"]["hash"], summary["registration_hash"])
        self.assertTrue((output / "PACK.md").read_text(encoding="utf-8").startswith("# Evidence pack: trend-fixture"))
        self.assertEqual(len(list((output / "runs").iterdir())), 25)
        code, out, err = command("run", self.registration, "--dataset", self.root / "dataset", "--output", output)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("runs once", err)

    def test_an_earlier_study_is_read_from_its_saved_primary_run(self):
        first = self.root / "first"
        self.assertEqual(command("run", self.registration, "--dataset", self.root / "dataset", "--output", first)[0], 0)
        earlier = [{"study": "trend-fixture", "runs": str(first / "runs" / "plan-10bps")}]
        second = self.register("trend-fixture-two", earlier_studies=earlier)
        code, _, err = command("run", second, "--dataset", self.root / "dataset", "--output", self.root / "second")
        self.assertEqual((code, err), (0, ""))
        overlap = json.loads((self.root / "second" / "pack.json").read_text(encoding="utf-8"))["overlap"]
        self.assertEqual(overlap["trend-fixture"]["correlation"], "1")  # The same plan on the same data.

    def test_refusals_come_before_any_run(self):
        missing = self.register("trend-fixture-three",
                                earlier_studies=[{"study": "trend-fixture", "runs": str(self.root / "none")}])
        other = self.register("trend-fixture-four", code_hash="e" * 64)
        for registration, message in ((missing, "Earlier study trend-fixture: "), (other, "registration's tag")):
            for name, extra in (("check", ()), ("run", ("--output", self.root / "never"))):
                with self.subTest(message=message, command=name):
                    code, out, err = command(name, registration, "--dataset", self.root / "dataset", *extra)
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn(message, err)
                    self.assertFalse((self.root / "never").exists())


if __name__ == "__main__":
    unittest.main()
