"""Regressions for audit findings, using independently constructed policy inputs."""

from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch

import test_validation as fixtures
from quant_core.validation.campaign import _comparison, _nomination, _scenarios, _trial, crosscheck, register_campaign
from quant_core.validation.registry import Registry
from quant_core.validation.temporal import Period
from quant_core.data import Bar, CashDelisting, Security
from quant_core.strategies import StrategyConfig


class AuditValidationTests(unittest.TestCase):
    def test_wipeout_trial_retains_loss_and_undefined_later_fold(self):
        case = fixtures.CampaignTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        register_campaign(case.spec, case.data, case.qualification, case.root)
        days = case.data.sessions
        data = replace(case.data,
                       securities=(Security("A", "A", "SYN", delisted_on=days[10]),),
                       bars=tuple(Bar("A", day, 100, 100, 100, 100, 100000) for day in days[:10]),
                       actions=(CashDelisting("A", days[10], 0),))
        recipe = StrategyConfig("wipeout", "buy_hold", ("A",), invested_fraction="1",
                                volume_lookback=1, max_volume_participation="1",
                                purpose="engineering_fixture")
        period = Period("development", days[5], days[34])
        registry = Registry(case.root)
        with registry.exclusive():
            row = _trial(registry, case.spec, data, recipe, period,
                         ("gross_diagnostic", Decimal(0), 1, False))
        self.assertEqual(row["status"], "undefined_returns", row)
        self.assertEqual(Decimal(row["metrics"]["total_return"]), -1)
        self.assertIsNone(row["returns"][-1])
        self.assertIsNone(row["folds"]["fold2"]["total_return"])
        self.assertEqual(row["folds"]["fold2"]["reason"], "zero_equity_at_period_start")
        self.assertTrue(Registry(case.root).has("trial_finished"))
        self.assertFalse(Registry(case.root).has("trial_failed"))

    def test_undefined_trial_does_not_erase_other_comparisons_or_search_history(self):
        data, spec, _ = fixtures.fixture()
        period = spec.selection
        dates = [d.isoformat() for d in data.sessions if period.start <= d <= period.end]
        rows = [{"recipe": cfg.name, "scenario": scenario, "status": "completed",
                 "dates": dates, "returns": ["0"] * len(dates)}
                for scenario in ("cost_10", "cost_25") for cfg in spec.candidates + spec.benchmarks]
        for row in rows:
            if row["recipe"] == spec.candidates[0].name:
                row.update(status="undefined_returns", returns=["0", "-1"] + [None] * (len(dates) - 2))
        comparison = _comparison(spec, rows, period)
        self.assertIn(spec.candidates[1].name, comparison["candidate_comparisons"])
        self.assertNotIn(spec.candidates[0].name, comparison["candidate_comparisons"])
        self.assertEqual(comparison["search_diagnostics"], {})
        self.assertIn("cost_10", comparison["search_diagnostic_limitations"])

    def test_low_volatility_candidate_can_be_nominated(self):
        _, spec, _ = fixtures.fixture()
        candidate = replace(spec.candidates[0], name="low_vol3", family="low_vol",
                            volatility_window=3, purpose="research_candidate")
        spec = replace(spec, purpose="exploratory_research", candidates=(candidate,))
        development, selection = fixtures.nomination_reports(spec)
        result = _nomination(spec, development, selection)
        self.assertEqual(result["nominee"], "low_vol3")

    def test_equivalent_cost_spellings_have_matching_scenario_identity(self):
        _, spec, _ = fixtures.fixture()
        variant = replace(spec, costs_bps=("5.00", "10.0", "25.000"),
                          primary_cost_bps="10", stressed_cost_bps="25.0")
        self.assertEqual([s[0] for s in _scenarios(variant)], [s[0] for s in _scenarios(spec)])
        self.assertEqual([s[1] for s in _scenarios(variant)], [s[1] for s in _scenarios(spec)])

    def test_crosscheck_preserves_original_search_and_labels_nominee_only_test(self):
        case = fixtures.CampaignTests("test_final_requires_independent_reviewed_snapshot_and_consumes_once")
        case.setUp()
        self.addCleanup(case.doCleanups)
        independent, qualification, outcome = case._frozen_gate_fixture()
        with patch("quant_core.validation.campaign._nomination", return_value=outcome):
            report = crosscheck(case.root, independent, qualification)
        context = report["search_context"]
        self.assertEqual(context["original_candidates"], [c.name for c in case.spec.candidates])
        self.assertEqual(context["original_registered_trial_count"], 72)
        self.assertEqual(context["retested_candidates"], [outcome["nominee"]])
        self.assertFalse(context["full_search_repeated"])
        self.assertTrue(context["original_selection_bound"])


if __name__ == "__main__":
    unittest.main()
