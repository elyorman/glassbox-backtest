"""Evidence-pack numbers on hand-worked synthetic runs and series."""

from decimal import Decimal
import unittest

from quant_core.analytics import return_metrics, summarize_run
from quant_core.analytics.evidence import results, run_series
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


if __name__ == "__main__":
    unittest.main()
