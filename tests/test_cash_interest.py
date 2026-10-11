"""Idle cash earns a strictly lagged rate; expected values are calculated by hand."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Context, Decimal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.analytics import summarize_run
from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.data import Bar, DataMetadata, Security, Snapshot
from quant_core.data.rates import CashRateSeries
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.reporting import save_run, verify_run

META = DataMetadata("synthetic", datetime(2024, 1, 10, tzinfo=timezone.utc),
                    "fixed_synthetic_universe", True, "synthetic_explicit_sessions")
WEEKEND = (date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9))  # Friday, Monday, Tuesday.
WEEK = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
D = Decimal


def snapshot(sessions):
    bars = tuple(Bar("A", day, "10", "10", "10", "10", "1000") for day in sessions)
    return Snapshot(sessions, bars, META, (Security("A", "AAA", "SYNTHETIC"),))


def rates(*observations):
    return CashRateSeries("test_source", "test_3m", META.retrieved_at, observations)


def run(sessions, cash_rates, cash="10000", orders=()):
    return run_backtest(snapshot(sessions), OrderSchedule(tuple(orders)),
                        RunConfig(cash, ExecutionProfile("0"), cash_rates=cash_rates))


class InterestTests(unittest.TestCase):
    def test_weekend_accrual_uses_the_rate_before_the_previous_session(self):
        series = rates((date(2024, 1, 4), "0.05"), (date(2024, 1, 5), "0.09"), (date(2024, 1, 8), "0.02"))
        result = run(WEEKEND, series)
        with localcontext(Context(prec=28)):
            # Monday: Friday's close cash, Thursday's 5% rate, three calendar days.
            monday = D(1500) / 365
            # Tuesday: Monday's close cash, Friday's 9% rate, one day.
            tuesday = (D(10000) + monday) * D("0.09") * 1 / 365
        self.assertEqual([s.interest_income for s in result.equity], [0, monday, monday + tuesday])
        self.assertEqual(result.equity[-1].cash, 10000 + monday + tuesday)
        self.assertEqual(result.equity[-1].equity, result.equity[-1].cash)
        self.assertEqual([(m.session, m.kind, m.amount) for m in result.cash_movements[1:]],
                         [(WEEKEND[1], "interest", monday), (WEEKEND[2], "interest", tuesday)])

    def test_rates_observed_on_or_after_the_previous_session_are_not_used(self):
        base = run(WEEKEND, rates((date(2024, 1, 4), "0.05"), (date(2024, 1, 5), "0.09")))
        changed = run(WEEKEND, rates((date(2024, 1, 4), "0.05"), (date(2024, 1, 5), "0.09"),
                                     (date(2024, 1, 8), "0.90"), (date(2024, 1, 9), "0.90")))
        self.assertEqual(base.equity, changed.equity)

    def test_interest_is_credited_before_orders_and_the_identity_holds(self):
        series = rates((date(2023, 12, 29), "0.0365"))  # 0.0001 per calendar day.
        buy = ScheduledOrder(WEEK[0], OrderRequest("A", "buy", "50"))
        result = run(WEEK, series, cash="1000", orders=(buy,))
        # Jan 3: 1000 earns 0.1 before the 500 buy; Jan 4: 500.1 earns 0.05001.
        self.assertEqual([s.cash for s in result.equity], [1000, D("500.1"), D("500.15001")])
        self.assertEqual(result.equity[-1].equity, D("1000.15001"))
        self.assertEqual(result.equity[-1].interest_income, D("0.15001"))
        metrics = summarize_run(result)
        self.assertEqual(metrics["interest_income"], D("0.15001"))
        self.assertEqual(metrics["asset_pnl"], {"A": 0})
        tampered = replace(result, equity=result.equity[:-1] + (replace(result.equity[-1], interest_income=D(0)),))
        with self.assertRaisesRegex(ArithmeticError, "interest do not reconcile"):
            summarize_run(tampered)

    def test_stale_or_missing_rates_refuse_the_run_before_simulating(self):
        with self.assertRaisesRegex(ValueError, "stale for 2024-01-02"):
            run(WEEK, rates((date(2023, 12, 20), "0.05")))
        with self.assertRaisesRegex(ValueError, "No test_3m observation before 2024-01-02"):
            run(WEEK, rates((date(2024, 1, 2), "0.05")))
        # A one-session run accrues nothing and needs no rate.
        self.assertEqual(run(WEEK[:1], rates((date(2024, 1, 2), "0.05"))).equity[0].interest_income, 0)

    def test_zero_rates_record_nothing_and_negative_rates_charge(self):
        zero = run(WEEK, rates((date(2023, 12, 29), "0")))
        self.assertEqual([m.kind for m in zero.cash_movements], ["initial_capital"])
        negative = run(WEEK, rates((date(2023, 12, 29), "-0.0365")), cash="1000")
        self.assertEqual(negative.equity[1].cash, D("999.9"))

    def test_without_rates_cash_earns_nothing(self):
        result = run(WEEK, None)
        self.assertTrue(all(s.interest_income == 0 for s in result.equity))
        self.assertEqual(result.equity[-1].cash, 10000)
        self.assertIn("USD long-only; no leverage; cash return zero", result.manifest.assumptions)
        with self.assertRaisesRegex(ValueError, "CashRateSeries"):
            RunConfig(cash_rates=((date(2024, 1, 2), "0.05"),))

    def test_rate_assumption_and_bundle_columns_are_recorded(self):
        result = run(WEEK, rates((date(2023, 12, 29), "0.05")))
        self.assertEqual(result.manifest.schema_version, 4)
        self.assertTrue(any("idle cash earns test_3m (test_source)" in a for a in result.manifest.assumptions))
        self.assertEqual(result.manifest.config.cash_rates.observations, ((date(2023, 12, 29), D("0.05")),))
        with TemporaryDirectory() as directory:
            save_run(result, Path(directory) / "run")
            verify_run(Path(directory) / "run")
            header = (Path(directory) / "run" / "equity.csv").read_text().splitlines()[0]
            self.assertTrue(header.endswith(",drawdown,interest_income"))


if __name__ == "__main__":
    unittest.main()
