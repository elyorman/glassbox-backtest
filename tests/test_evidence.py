"""Evidence-pack numbers on hand-worked synthetic runs and series."""

from datetime import date
from decimal import Decimal
import unittest

from quant_core.analytics import return_metrics, summarize_run
from quant_core.analytics.evidence import (
    RunSeries, calendar_years, drawdowns, period, periods, results, run_series, twelve_month_extremes,
)
from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.execution import OrderRequest
from quant_core.strategies.plans import TrendPlan, build_plan
from test_monthly_plans import DAYS, FREE, PRICES, fixture, rates, snapshot

D = Decimal
DATA = snapshot({"A": PRICES["A"]})  # A: 10, 10, 11, 12, 12, 11, 11, 11 on Jan 27/28 ... Apr 27/28.
# Buy 40 A on Jan 27's signal (filled at Jan 28's open, $10); 1,000 more on Feb 27's cannot be paid for,
# and selling 100 on Feb 28's is more than is held: only the first refusal is an opening-gap rejection.
ORDERS = OrderSchedule((ScheduledOrder(DAYS[0], OrderRequest("A", "buy", 40)),
                        ScheduledOrder(DAYS[2], OrderRequest("A", "buy", 1000)),
                        ScheduledOrder(DAYS[3], OrderRequest("A", "sell", 100))))


def simulate(**settings):
    return run_backtest(DATA, ORDERS, RunConfig("1000", FREE, ("A",), **settings))


class RunSeriesTests(unittest.TestCase):
    def test_excess_returns_subtract_what_cash_earned_over_the_same_days(self):
        series = run_series(simulate(cash_rates=rates()))
        # 36.5% a year is 0.1% a calendar day: 1, 30, 1, 28, 1, 30 and 1 days between the sessions.
        bills = (0, D("0.001"), D("0.030"), D("0.001"), D("0.028"), D("0.001"), D("0.030"), D("0.001"))
        self.assertEqual(series.excess, tuple(r - c for r, c in zip(series.returns, bills)))
        self.assertEqual((series.sessions, series.initial_cash), (DAYS, 1000))
        self.assertEqual(series.weights[0], ())
        self.assertEqual(series.weights[1], (("A", D(400) / series.equity[1]),))  # 40 shares at $10.
        plain = run_series(simulate())
        self.assertEqual(plain.excess, plain.returns)  # Without a rate series, cash earns nothing.


class ResultsTests(unittest.TestCase):
    def test_the_results_row_of_a_hand_worked_run(self):
        result = simulate()
        row, summary = results(result), summarize_run(result)
        self.assertEqual(sum(o.status == "rejected" for o in result.orders), 2)
        # Equity 1,000, 1,000, 1,040, 1,080, 1,080, 1,040, 1,040, 1,040: the worst fall is 40 / 1,080.
        self.assertAlmostEqual(row["max_drawdown"], D(40) / 1080, places=25)
        self.assertEqual((row["longest_underwater_sessions"], row["trades"], row["opening_gap_rejections"]),
                         (3, 1, 1))
        self.assertEqual((row["first_session"], row["last_session"], row["sessions"]),
                         ("2024-01-27", "2024-04-28", 8))
        # $400 bought against $1,000 of equity, over the 93 calendar days from Jan 27 to Apr 28.
        self.assertEqual(row["annual_turnover"], D("0.4") / (D(93) / D("365.2425")))
        self.assertEqual((row["cagr"], row["calmar"], row["average_gross_exposure"], row["interest_income"]),
                         (summary["cagr_calendar"], summary["calmar"], summary["average_gross_exposure"], 0))
        self.assertIsNotNone(row["sharpe"])

    def test_sharpe_and_sortino_are_measured_over_t_bills(self):
        result = simulate(cash_rates=rates())
        with_bills, without, series = results(result), results(simulate()), run_series(result)
        self.assertLess(with_bills["sharpe"], without["sharpe"])  # Paying 36.5% on cash raises the bar.
        self.assertGreater(with_bills["interest_income"], 0)
        raw, excess = return_metrics(series.returns), return_metrics(series.excess)
        self.assertEqual((with_bills["sortino"], with_bills["max_drawdown"]), (excess["sortino"], raw["max_drawdown"]))
        self.assertNotEqual(excess["sortino"], raw["sortino"])  # So the two sources can be told apart.
        self.assertNotEqual(excess["max_drawdown"], raw["max_drawdown"])

    def test_selected_lines_too_small_for_one_share_are_counted(self):
        plan = fixture(TrendPlan, universe=("A", "B"), average_months=2)
        data = snapshot()
        result = run_backtest(data, build_plan(data, plan, None, FREE), RunConfig("20", FREE, plan.universe))
        # A quarter of $20 buys no $12 share of A in February or $21 share of B in March.
        self.assertEqual(results(result)["whole_share_shortfalls"], 2)


def series(days, equity, excess=None, initial="100"):
    """A RunSeries from closing equity; each return is measured from the previous close (initial cash first)."""
    equity = tuple(D(value) for value in equity)
    returns = tuple(e / p - 1 for e, p in zip(equity, (D(initial),) + equity[:-1]))
    return RunSeries(tuple(days), returns, tuple(D(x) for x in excess) if excess else returns, equity,
                     ((),) * len(days), D(initial))


class PeriodTests(unittest.TestCase):
    DAYS = (date(2023, 12, 28), date(2023, 12, 29), date(2024, 1, 2), date(2024, 1, 3))
    SERIES = series(DAYS, ("100", "110", "99", "108.9"))  # Returns 0, +10%, -10%, +10%.

    def test_a_period_compounds_its_own_sessions(self):
        self.assertEqual(period(self.SERIES, date(2024, 1, 1), date(2024, 12, 31)),
                         {"first_session": "2024-01-02", "last_session": "2024-01-03", "sessions": 2,
                          "return": D("-0.01"), "max_drawdown": D("0.1"),  # 0.9 x 1.1, from the year's start.
                          "sharpe": period(self.SERIES, date(2024, 1, 1), date(2024, 12, 31))["sharpe"]})
        self.assertIsNone(period(self.SERIES, date(2025, 1, 1), date(2025, 12, 31)))
        flat = series(self.DAYS, ("100", "100", "100", "100"))
        self.assertIsNone(period(flat, date(2023, 1, 1), date(2024, 12, 31))["sharpe"])  # No variance.

    def test_the_sharpe_of_a_period_uses_excess_returns(self):
        days = (date(2023, 12, 27),) + self.DAYS[:2]
        returns_only = period(series(days, ("100", "110", "99")), date(2023, 1, 1), date(2023, 12, 31))
        over_bills = period(series(days, ("100", "110", "99"), excess=("0", "0.05", "0.01")),
                            date(2023, 1, 1), date(2023, 12, 31))
        self.assertEqual(returns_only["return"], over_bills["return"])
        self.assertEqual(returns_only["sharpe"], 0)  # Returns 0, +10%, -10% average zero.
        # Excess 0, 0.05, 0.01: mean 0.02 over sample deviation sqrt(0.0007), times sqrt(252), is exactly 12.
        self.assertAlmostEqual(over_bills["sharpe"], D(12), places=20)

    def test_calendar_years_windows_publication_and_segments(self):
        self.assertEqual({year: row["return"] for year, row in calendar_years(self.SERIES).items()},
                         {"2023": D("0.1"), "2024": D("-0.01")})
        days = (date(2019, 12, 31), date(2020, 1, 2), date(2023, 1, 3), date(2026, 10, 12))
        sections = periods(series(days, ("100", "110", "121", "133.1")), publication=date(2020, 1, 1),
                           segments=(("early", date(2019, 1, 1), date(2020, 12, 31)),))
        self.assertEqual({name: row["sessions"] for name, row in sections["windows"].items()},
                         {"2016-2019": 1, "2020-2022": 1, "2023-end": 2})
        self.assertEqual(sections["since_publication"]["first_session"], "2020-01-02")
        self.assertEqual(sections["segments"]["early"]["return"], D("0.1"))  # 2019-12-31 and 2020-01-02.
        self.assertEqual(set(sections), {"calendar_years", "windows", "since_publication", "segments",
                                         "twelve_months", "drawdowns"})
        self.assertIsNone(periods(series(days, ("100",) * 4))["since_publication"])


class TwelveMonthTests(unittest.TestCase):
    def test_best_and_worst_twelve_months_between_month_ends(self):
        days = [date(2023, month, 28) for month in range(1, 13)] + [date(2024, 1, 31), date(2024, 2, 28)]
        equity = ["100"] * 12 + ["120", "90"]  # Jan to Jan: +20%; Feb to Feb: -10%.
        extremes = twelve_month_extremes(series(days, equity))
        self.assertEqual(extremes["best"], {"start": "2023-01-28", "end": "2024-01-31", "return": D("0.2")})
        self.assertEqual(extremes["worst"], {"start": "2023-02-28", "end": "2024-02-28", "return": D("-0.1")})
        self.assertIsNone(twelve_month_extremes(series(days[:12], equity[:12])))
        gap = days[:5] + days[6:]  # Without June, the only pair left (Jan 2023, Feb 2024) is 13 months apart.
        self.assertIsNone(twelve_month_extremes(series(gap, equity[:5] + equity[6:])))


class DrawdownTests(unittest.TestCase):
    def test_falls_are_measured_from_their_peak_to_recovery(self):
        days = [date(2024, 1, day) for day in range(1, 9)]
        falls = drawdowns(series(days, ("100", "90", "95", "100", "120", "60", "70", "80")))
        self.assertEqual(falls, [
            {"depth": D("0.5"), "peak_session": "2024-01-05", "trough_session": "2024-01-06",
             "recovery_session": None, "sessions_to_trough": 1, "sessions_to_recovery": None},
            {"depth": D("0.1"), "peak_session": "2024-01-01", "trough_session": "2024-01-02",
             "recovery_session": "2024-01-04", "sessions_to_trough": 1, "sessions_to_recovery": 3}])

    def test_a_fall_from_initial_capital_and_the_count_limit(self):
        days = [date(2024, 1, day) for day in range(1, 15)]
        first = drawdowns(series(days[:2], ("95", "100")))
        self.assertEqual(first, [{"depth": D("0.05"), "peak_session": None, "trough_session": "2024-01-01",
                                  "recovery_session": "2024-01-02", "sessions_to_trough": 1,
                                  "sessions_to_recovery": 2}])
        saw = ("99", "100", "98", "100", "97", "100", "96", "100", "95", "100", "94", "100", "93", "100")
        self.assertEqual([row["depth"] for row in drawdowns(series(days, saw))],
                         [D("0.07"), D("0.06"), D("0.05"), D("0.04"), D("0.03")])


if __name__ == "__main__":
    unittest.main()
