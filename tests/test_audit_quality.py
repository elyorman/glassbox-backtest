"""Suspicious prices are surfaced without fabricating corporate actions."""

from datetime import date
from dataclasses import replace
import unittest

import test_data as fixtures
from quant_core.data import Dividend, Split
from quant_core.data.quality import check_quality


class AuditQualityTests(unittest.TestCase):
    def test_known_cash_dividend_explains_split_sized_price_change(self):
        for before, split in (("30", ()), ("60", (Split("A", fixtures.DAYS[1], 2),))):
            with self.subTest(before=before):
                data = fixtures.snapshot(tuple(fixtures.bar(day, before if i == 0 else "20")
                                               for i, day in enumerate(fixtures.DAYS)),
                                         actions=split + (Dividend("A", fixtures.DAYS[1], 10, fixtures.DAYS[1]),))
                report = check_quality(data, strict_discontinuities=True)
                self.assertFalse(report.has_errors, report.issues)
                self.assertNotIn("suspected_missing_split", [i.code for i in report.issues])
                self.assertEqual(data.bars[0].close, fixtures.Decimal(before))

    def test_common_split_sized_changes_are_flagged_without_repair(self):
        for before, after in (("200", "100"), ("150", "100"), ("125", "100"),
                              ("100", "200"), ("100", "150")):
            with self.subTest(before=before, after=after):
                data = fixtures.snapshot(tuple(fixtures.bar(day, before if i == 0 else after)
                                               for i, day in enumerate(fixtures.DAYS)))
                issues = check_quality(data).issues
                self.assertIn("suspected_missing_split", [i.code for i in issues])
                self.assertEqual(data.bars[0].close, fixtures.Decimal(before))
                self.assertEqual(data.actions, ())

    def test_split_sized_changes_with_ordinary_gaps_are_flagged(self):
        for before, after in (("100", "50.5"), ("150", "101"), ("150", "99"), ("125", "101"), ("100", "75")):
            with self.subTest(before=before, after=after):
                data = fixtures.snapshot(tuple(fixtures.bar(day, before if i == 0 else after)
                                               for i, day in enumerate(fixtures.DAYS)))
                self.assertIn("suspected_missing_split", [i.code for i in check_quality(data).issues])

    def test_ordinary_moves_away_from_split_ratios_are_not_flagged(self):
        for before, after in (("100", "90"), ("100", "110"), ("100", "60")):
            with self.subTest(before=before, after=after):
                data = fixtures.snapshot(tuple(fixtures.bar(day, before if i == 0 else after)
                                               for i, day in enumerate(fixtures.DAYS)))
                self.assertNotIn("suspected_missing_split", [i.code for i in check_quality(data).issues])

    def test_exact_jump_threshold_is_inclusive(self):
        data = fixtures.snapshot(tuple(fixtures.bar(day, "200" if i == 0 else "100")
                                       for i, day in enumerate(fixtures.DAYS)))
        self.assertIn("price_discontinuity", [i.code for i in check_quality(data).issues])

    def test_known_split_is_accounted_for_before_suspicion(self):
        data = fixtures.snapshot(tuple(fixtures.bar(day, "150" if i == 0 else "100")
                                       for i, day in enumerate(fixtures.DAYS)),
                                 actions=(Split("A", fixtures.DAYS[1], "1.5"),))
        self.assertNotIn("suspected_missing_split", [i.code for i in check_quality(data).issues])

    def test_explicit_strict_discontinuities_prevent_accepting_unresolved_prices(self):
        data = fixtures.snapshot(tuple(fixtures.bar(day, "125" if i == 0 else "100")
                                       for i, day in enumerate(fixtures.DAYS)))
        self.assertTrue(check_quality(data, strict_discontinuities=True).has_errors)

    def test_backtester_can_require_discontinuity_review_before_execution(self):
        from quant_core.backtest import RunConfig, OrderSchedule, run_backtest
        data = fixtures.snapshot(tuple(fixtures.bar(day, "200" if i == 0 else "100")
                                       for i, day in enumerate(fixtures.DAYS)))
        config = RunConfig(strict_discontinuities=True)
        with self.assertRaisesRegex(ValueError, "Data quality error"):
            run_backtest(data, OrderSchedule(()), config)

    def test_missing_bar_diagnostic_does_not_bypass_strict_discontinuities(self):
        from quant_core.backtest import RunConfig, OrderSchedule, run_backtest
        data = fixtures.snapshot(tuple(fixtures.bar(day, "200" if i == 0 else "100")
                                       for i, day in enumerate(fixtures.DAYS)))
        config = RunConfig(data_policy="allow_missing_unheld_diagnostic", strict_discontinuities=True)
        with self.assertRaisesRegex(ValueError, "Data quality error"):
            run_backtest(data, OrderSchedule(()), config)


if __name__ == "__main__":
    unittest.main()
