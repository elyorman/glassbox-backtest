"""The evidence pack of the synthetic registered study: every section from the study's own runs."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from quant_core.analytics.evidence import (
    bootstrap, correlation, deflated, holdings_overlap, periods, results, run_series,
)
from quant_core.analytics import return_metrics
from quant_core.provenance import content_hash, primitive
from quant_core.reporting.evidence import (
    NOT_PROMISED, _fixed, _flag_outside, _pct, _probability, build_pack, holds, render_pack, write_pack,
)
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
        cls.pack = build_pack(REGISTRATION, cls.dataset, cls.runs, {"earlier-fixture": (cls.earlier, "f" * 64)})

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_sections_and_the_registration_they_come_from(self):
        self.assertEqual(list(self.pack), ["schema_version", "registration", "results", "references", "comparison",
                                           "uncertainty", "deflated_sharpe", "start", "periods", "sensitivity",
                                           "cash", "overlap", "limitations", "reproduction"])
        self.assertEqual(self.pack["registration"]["file"], REGISTRATION.payload)
        self.assertEqual(set(self.pack["registration"]["configuration_hashes"]),
                         {"trend_fixture", "trend_fixture_shift_minus_2", "trend_fixture_shift_plus_2",
                          "trend_fixture_3", "trend_fixture_4"})
        self.assertEqual(self.pack["registration"]["configuration_hashes"]["trend_fixture"],
                         content_hash(REGISTRATION.plan))
        self.assertEqual(self.pack["start"], {"first_decision": "2022-09-28", "without_enough_history": []})
        registration = self.pack["registration"]
        self.assertEqual((registration["study"], registration["hash"], registration["plan"]["average_months"]),
                         ("trend-fixture", REGISTRATION.hash, 2))
        self.assertEqual(registration["trials"], {"cumulative": 50, "this_study": 5, "per_role": 5})
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
        self.assertEqual(described["spy_buy_hold"], "Rebalanced at each month end to 95% SPY and 5% cash")
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
        found = {key: value for key, value in self.pack["uncertainty"].items() if key not in ("observed", "reference")}
        flags = {block: row.pop("observed_outside") for block, row in deepcopy(found)["blocks"].items()}
        self.assertEqual({**found, "blocks": {block: {k: v for k, v in row.items() if k != "observed_outside"}
                                              for block, row in found["blocks"].items()}}, expected)
        observed = self.pack["uncertainty"]["observed"]
        for block, row in found["blocks"].items():
            for name in ("annualized_return_252", "sharpe", "max_drawdown"):
                low, high = row[name]
                self.assertEqual(name in flags[block], not low <= observed[name] <= high, (block, name))
        self.assertEqual(self.pack["uncertainty"]["reference"], "sixty_forty")
        observed, parent = self.pack["uncertainty"]["observed"], self.pack["results"]["10"]
        self.assertEqual((observed["sharpe"], observed["max_drawdown"]), (parent["sharpe"], parent["max_drawdown"]))
        self.assertEqual(observed["annualized_return_252"],
                         return_metrics(self.parent.returns)["annualized_return_252"])
        neighbours = [run_series(self.runs[f"neighbour-trend_fixture_{n}-10bps"]) for n in (3, 4)]
        self.assertEqual(self.pack["deflated_sharpe"],
                         {**deflated(self.parent, neighbours, 50, D("0.000197")), "per_role_trials": 5})

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
            "run_hash": "f" * 64, "correlation": correlation(self.parent, self.earlier),
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


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as directory:
            cls.dataset = synthetic_dataset()
            cls.runs = run_study(REGISTRATION, cls.dataset, Path(directory) / "study")
        cls.pack = build_pack(REGISTRATION, cls.dataset, cls.runs)
        cls.text = render_pack(cls.pack)

    def test_numbers_are_rounded_half_even_without_negative_zero(self):
        self.assertEqual((_fixed(D("0.125"), 2), _fixed(D("0.135"), 2), _fixed(D("-0.004"), 2)),
                         ("0.12", "0.14", "0.00"))
        self.assertEqual((_pct(D("0.123456")), _pct(D("-0.5")), _pct(None), _fixed(None, 2)),
                         ("12.35%", "-50.00%", "n/a", "n/a"))

    def test_sections_appear_in_order_with_the_pack_numbers(self):
        headings = [line for line in self.text.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## Registration", "## Results", "## Comparison portfolios", "## Uncertainty",
                                    "## Deflated Sharpe ratio", "## Periods", "## Sensitivity", "## Cash",
                                    "## Overlap with earlier built-ins", "## Limitations", "## Reproduction"])
        row = self.pack["results"]["25"]
        self.assertIn(f"| 25 | {row['first_session']} | {row['last_session']} | {_pct(row['cagr'])} | "
                      f"{_pct(row['volatility'])} | {_fixed(row['sharpe'], 2)} |", self.text)
        self.assertIn("| tbills | n/a | ", self.text)  # An undefined Sharpe difference.
        self.assertIn("| tbills | 10bps-cash0 | 0.00% | n/a |", self.text)
        self.assertEqual(self.pack["sensitivity"]["shift+2-10bps"]["label"],
                         "Decisions +2 sessions from month end (10 bps)")
        last = self.pack["sensitivity"]["neighbour-trend_fixture_4-10bps"]
        self.assertIn(f"| Neighbour trend_fixture_4 (10 bps) | {_pct(last['cagr'])} | {_fixed(last['sharpe'], 2)} |",
                      self.text)
        self.assertIn("| sixty_forty | Rebalanced at each month end to 57% SPY, 38% IEF and 5% cash |", self.text)
        year = self.pack["periods"]["calendar_years"]["2023"]
        self.assertIn(f"| 2023 | {year['first_session']} | {year['last_session']} | {year['sessions']} | "
                      f"{_pct(year['return'])} | {_pct(year['max_drawdown'])} | {_fixed(year['sharpe'], 2)} |",
                      self.text)
        primary = self.pack["deflated_sharpe"]["primary"]
        self.assertIn(f"| Primary (larger) | {_fixed(primary['sharpe_variance'], 6)} | "
                      f"{_fixed(primary['expected_maximum_sharpe'], 4)} | {_fixed(primary['z'], 2)} | "
                      f"{_probability(primary['deflated_sharpe_ratio'])} |", self.text)
        self.assertIn(f"| plan-10bps | `{self.pack['reproduction']['runs']['plan-10bps']}` |", self.text)
        self.assertIn("No earlier built-in.", self.text)
        self.assertIn(self.pack["reproduction"]["command"], self.text)
        self.assertNotIn("-0.00", self.text)
        for line in NOT_PROMISED:
            self.assertIn(f"- {line}", self.text)

    def test_the_registration_section_shows_what_was_fixed_before_the_run(self):
        for line in ("Period 2022-09-28 to 2024-05-28. The rule's source was first published 2023-06-01: "
                     "A synthetic paper.", "### Parent: trend_fixture", "| average_months | 2 |", "| universe | A, B |",
                     "| trend_fixture_3 | average_months 3 |", "Rebalance shifts: -2, +2 sessions.",
                     "| average_months | A synthetic paper, p. 1 |",
                     "| Fills at the next open | The engine never fills on the signal bar |",
                     "- first year: 2022-09-28 to 2023-09-28", "- 2026-10-03 trend recipes",
                     "None for the tester round. Reason: Owner decision.",
                     f"| trend_fixture | `{content_hash(REGISTRATION.plan)}` |",
                     "First decision 2022-09-28; ETFs without enough history then: none.",
                     "long falls are under-represented"):
            self.assertIn(line, self.text)

    def test_observed_values_outside_their_intervals_are_named(self):
        blocks = {"5": {"annualized_return_252": (D("-0.1"), D("0.2")), "sharpe": (D("0.1"), D("0.9")),
                        "max_drawdown": (D("0.2"), D("0.6"))},
                  "20": {"annualized_return_252": (None, None), "sharpe": (D("0.6"), D("0.9")),
                         "max_drawdown": (D("0.1"), D("0.65"))}}
        observed = {"annualized_return_252": D("0.25"), "sharpe": D("0.5"), "max_drawdown": D("0.65")}
        flagged = _flag_outside({"blocks": deepcopy(blocks)}, observed)["blocks"]
        self.assertEqual({block: row["observed_outside"] for block, row in flagged.items()},
                         {"5": ["annualized_return_252", "max_drawdown"], "20": ["sharpe"]})  # Bounds included.
        pack = deepcopy(self.pack)
        pack["uncertainty"]["blocks"]["5"]["observed_outside"] = ["sharpe", "max_drawdown"]
        self.assertIn(" | Sharpe, max drawdown |", render_pack(pack))

    def test_probabilities_never_read_as_certain(self):
        self.assertEqual([_probability(value) for value in (D("0.99995"), D(1), D("0.99994"), D("0.00005"),
                                                             D("0.00006"), D(0), None)],
                         ["> 0.9999", "> 0.9999", "0.9999", "< 0.0001", "0.0001", "< 0.0001", "n/a"])
        pack = deepcopy(self.pack)
        pack["deflated_sharpe"]["primary"]["deflated_sharpe_ratio"] = D("0.99999")
        self.assertIn(" | > 0.9999 |", render_pack(pack))  # Never 1.0000, which reads as certain.

    def test_missing_periods_say_so(self):
        pack = deepcopy(self.pack)
        pack["periods"]["twelve_months"], pack["periods"]["drawdowns"] = None, []
        pack["start"]["without_enough_history"] = ["A", "B"]
        text = render_pack(pack)
        self.assertIn("ETFs without enough history then: A, B.", text)
        self.assertIn("The run is shorter than twelve months.", text)
        self.assertIn("| 2016-2019 | no sessions |", text)
        self.assertIn("| None |", text)

    def test_the_pack_is_written_once_as_json_and_markdown(self):
        with TemporaryDirectory() as directory:
            digest = write_pack(self.pack, directory)
            saved = json.loads(Path(directory, "pack.json").read_text(encoding="utf-8"))
            self.assertEqual((saved, digest), (primitive(self.pack), content_hash(self.pack)))
            self.assertEqual(Path(directory, "PACK.md").read_bytes(), self.text.encode("utf-8"))  # No CRLF.
            with self.assertRaises(FileExistsError):
                write_pack(self.pack, directory)


if __name__ == "__main__":
    unittest.main()
