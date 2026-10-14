"""The evidence pack of the synthetic registered study: every section from the study's own runs."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from quant_core.analytics.evidence import (
    bootstrap, correlation, deflated, holdings_overlap, periods, results, run_series,
)
from quant_core.analytics import return_metrics
from quant_core.reporting.evidence import NOT_PROMISED, build_pack, holds
from quant_core.strategies.plans import EqualWeightPlan
from quant_core.validation import study
from quant_core.validation.study import run_study
from test_study import KEYS, REGISTRATION, synthetic_dataset

D = Decimal


class PackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory()
        cls.dataset = synthetic_dataset()
        cls.runs = run_study(REGISTRATION, cls.dataset, Path(cls.directory.name) / "study")
        cls.parent, cls.earlier = run_series(cls.runs["plan-10bps"]), run_series(cls.runs["equal_weight-10bps"])
        cls.pack = build_pack(REGISTRATION, cls.dataset, cls.runs, {"earlier-fixture": cls.earlier})

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_sections_and_the_registration_they_come_from(self):
        self.assertEqual(list(self.pack), ["schema_version", "registration", "results", "references", "comparison",
                                           "uncertainty", "deflated_sharpe", "periods", "sensitivity", "cash",
                                           "overlap", "limitations", "reproduction"])
        registration = self.pack["registration"]
        self.assertEqual((registration["study"], registration["hash"], registration["plan"]["average_months"]),
                         ("trend-fixture", REGISTRATION.hash, 2))
        self.assertEqual(registration["trials"], {"cumulative": 50, "this_study": 5, "per_role": 4})
        self.assertEqual(list(self.pack["results"]), ["10", "25", "50"])
        self.assertEqual(self.pack["results"]["25"], results(self.runs["plan-25bps"]))

    def test_comparisons_use_the_runs_at_the_primary_cost(self):
        reference = results(self.runs["sixty_forty-10bps"])
        row = self.pack["comparison"]["sixty_forty"]
        self.assertEqual(row["sharpe_difference"], self.pack["results"]["10"]["sharpe"] - reference["sharpe"])
        self.assertEqual(row["cagr_difference"], self.pack["results"]["10"]["cagr"] - reference["cagr"])
        self.assertEqual(row["correlation"], correlation(self.parent, run_series(self.runs["sixty_forty-10bps"])))
        self.assertEqual(self.pack["references"]["tbills"]["50bps"], results(self.runs["tbills-50bps"]))
        self.assertEqual(set(self.pack["references"]["equal_weight"]), {"holds", "10bps", "25bps", "50bps",
                                                                        "10bps-cash0"})

    def test_references_say_what_they_hold(self):
        described = {name: values["holds"] for name, values in self.pack["references"].items()}
        self.assertEqual(described["sixty_forty"], "Rebalanced at each month end to 57% SPY, 38% IEF and 5% cash")
        self.assertEqual(described["spy_buy_hold"], "SPY bought once with 95% of the capital and held; 5% cash")
        # The first buy of B is refused at the open, but the rule chose both ETFs at every month end.
        self.assertTrue(described["equal_weight"].endswith("ETFs chosen: 2 at the first month end and 2 at the last"))
        self.assertEqual(described["tbills"], "Cash only, earning the 3-month Treasury rate")

    def test_equal_weight_counts_the_chosen_etfs_at_the_first_and_last_month_ends(self):
        source = EqualWeightPlan(name="equal_weight", universe=("A", "B", "C"))
        def decisions(*rows):
            return SimpleNamespace(signal_decisions=[SimpleNamespace(session=date(2024, month, 28), security_id=asset,
                                                                     selected=selected)
                                                     for month, asset, selected in rows])
        result = decisions((1, "A", True), (1, "B", False), (2, "A", True), (2, "B", True), (2, "C", True))
        self.assertTrue(holds(source, result).endswith("ETFs chosen: 1 at the first month end and 3 at the last"))
        self.assertTrue(holds(source, decisions()).endswith("ETFs chosen: none"))

    def test_an_undefined_sharpe_gives_no_difference(self):
        row = self.pack["comparison"]["tbills"]  # All cash: excess returns are exactly zero.
        self.assertEqual((row["sharpe_difference"], row["correlation"]), (None, None))
        self.assertEqual(row["cagr_difference"], self.pack["results"]["10"]["cagr"]
                         - results(self.runs["tbills-10bps"])["cagr"])

    def test_uncertainty_and_deflation_follow_the_registration(self):
        expected = bootstrap(self.parent, run_series(self.runs["sixty_forty-10bps"]), (5, 20), 100, 1729)
        self.assertEqual({key: value for key, value in self.pack["uncertainty"].items()
                          if key not in ("observed", "reference")}, expected)
        self.assertEqual(self.pack["uncertainty"]["reference"], "sixty_forty")
        observed, parent = self.pack["uncertainty"]["observed"], self.pack["results"]["10"]
        self.assertEqual((observed["sharpe"], observed["max_drawdown"]), (parent["sharpe"], parent["max_drawdown"]))
        self.assertEqual(observed["annualized_return_252"],
                         return_metrics(self.parent.returns)["annualized_return_252"])
        neighbours = [run_series(self.runs[f"neighbour-trend_fixture_{n}-10bps"]) for n in (3, 4)]
        self.assertEqual(self.pack["deflated_sharpe"],
                         {**deflated(self.parent, neighbours, 50, D("0.000197")), "per_role_trials": 4})

    def test_periods_sensitivity_and_cash(self):
        self.assertEqual(self.pack["periods"], periods(self.parent, date(2023, 6, 1),
                                                       (("first year", date(2022, 9, 28), date(2023, 9, 28)),)))
        self.assertEqual(list(self.pack["sensitivity"]), list(KEYS[:9]))
        self.assertEqual(self.pack["sensitivity"]["shift+2-10bps"]["role"], "shift")
        self.assertEqual(self.pack["sensitivity"]["plan-10bps-delay2"]["sharpe"],
                         results(self.runs["plan-10bps-delay2"])["sharpe"])
        self.assertEqual(self.pack["cash"]["zero_cash"], results(self.runs["plan-10bps-cash0"]))
        self.assertEqual((self.pack["cash"]["series"], self.pack["cash"]["first"]), ("test_bills", "2021-12-01"))

    def test_overlap_with_an_earlier_study(self):
        self.assertEqual(self.pack["overlap"], {"earlier-fixture": {
            "correlation": correlation(self.parent, self.earlier),
            "holdings_overlap": holdings_overlap(self.parent, self.earlier)}})
        self.assertGreater(self.pack["overlap"]["earlier-fixture"]["holdings_overlap"], D("0.1"))  # Both trade.

    def test_the_limitations_page_is_generated(self):
        limits = self.pack["limitations"]
        self.assertEqual(limits["data"]["first_sessions"], {"A": "2022-01-10", "B": "2022-01-10"})
        self.assertEqual(limits["data"]["provider"], "synthetic_study")
        years = self.pack["periods"]["calendar_years"]
        self.assertEqual(list(limits["losing_years"]), ["2023", "2024"])  # 2022 gained.
        self.assertGreater(years["2022"]["return"], 0)
        self.assertEqual(limits["losing_years"]["2023"], years["2023"]["return"])
        self.assertEqual(limits["largest_drawdowns"], self.pack["periods"]["drawdowns"])
        self.assertEqual(limits["not_promised"], list(NOT_PROMISED))
        self.assertEqual(limits["disclosures"], ["Synthetic data only."])

    def test_reproduction_names_every_run_hash(self):
        reproduction = self.pack["reproduction"]
        self.assertEqual(list(reproduction["runs"]), list(KEYS))
        self.assertEqual(reproduction["runs"]["tbills-10bps"], self.runs["tbills-10bps"].result_hash)
        self.assertEqual((reproduction["tag"], reproduction["code_hash"]), (REGISTRATION.tag, REGISTRATION.code_hash))

    def test_missing_runs_or_neighbours_on_other_sessions_are_refused(self):
        with self.assertRaisesRegex(ValueError, "planned runs"):
            build_pack(REGISTRATION, self.dataset, {k: v for k, v in self.runs.items() if k != "tbills-10bps"})
        later = replace(REGISTRATION, start=date(2023, 1, 28))
        planned = {run.key: run for run in study.planned_runs(REGISTRATION)}
        shorter = {**self.runs, "neighbour-trend_fixture_3-10bps": study._run(
            planned["neighbour-trend_fixture_3-10bps"], later, self.dataset)}
        with self.assertRaisesRegex(ValueError, "same sessions"):
            build_pack(REGISTRATION, self.dataset, shorter)


if __name__ == "__main__":
    unittest.main()
