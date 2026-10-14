"""Evidence-pack numbers on hand-worked synthetic runs and series."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.analytics import return_metrics, summarize_run
from quant_core.analytics.evidence import (
    RunSeries, bootstrap, calendar_years, correlation, deflated, drawdowns, holdings_overlap, period, periods,
    results, run_series, run_series_from_bundle, twelve_month_extremes,
)
from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.execution import OrderRequest
from quant_core.reporting import save_run
from quant_core.strategies.plans import FixedWeightPlan, TrendPlan, build_plan
from quant_core.validation.statistics import deflated_sharpe, return_moments, sharpe_variance
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
        self.assertEqual(series.excess, tuple((r - c).quantize(D("1e-20")) for r, c in zip(series.returns, bills)))
        self.assertEqual((series.sessions, series.initial_cash), (DAYS, 1000))
        self.assertEqual(series.weights[0], ())
        self.assertEqual(series.weights[1], (("A", D(400) / series.equity[1]),))  # 40 shares at $10.
        plain = run_series(simulate())
        self.assertEqual(plain.excess, tuple(r.quantize(D("1e-20")) for r in plain.returns))  # Cash earns nothing.

    def test_the_rate_is_the_one_observed_before_the_interval_starts(self):
        # From Feb 28 the rate doubles to 0.2% a day; Feb 28 to Mar 27 still earns Feb 27's rate.
        series = run_series(simulate(cash_rates=rates(changed_from=DAYS[3], changed_rate="0.73")))
        bills = (0, D("0.001"), D("0.030"), D("0.001"), D("0.028"), D("0.002"), D("0.060"), D("0.002"))
        self.assertEqual(series.excess, tuple((r - c).quantize(D("1e-20")) for r, c in zip(series.returns, bills)))

    def test_cash_alone_has_no_sharpe_over_t_bills(self):
        result = run_backtest(DATA, OrderSchedule(()), RunConfig("123457", FREE, ("A",), cash_rates=rates("0.05")))
        row = results(result)
        self.assertEqual(set(run_series(result).excess), {0})  # Not the engine's rounding noise.
        self.assertEqual((row["sharpe"], row["sortino"]), (None, None))
        self.assertGreater(row["interest_income"], 0)


    def test_a_saved_run_gives_the_same_series(self):
        for settings in ({"cash_rates": rates(changed_from=DAYS[3], changed_rate="0.73")}, {}):
            result = simulate(**settings)
            with self.subTest(cash=bool(settings)), TemporaryDirectory() as directory:
                save_run(result, Path(directory) / "run")
                self.assertEqual(run_series_from_bundle(Path(directory) / "run"), run_series(result))
                (Path(directory) / "run" / "equity.csv").write_text("tampered")
                with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                    run_series_from_bundle(Path(directory) / "run")


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
        self.assertEqual((with_bills["volatility"], with_bills["longest_underwater_sessions"]),
                         (raw["volatility"], raw["longest_underwater_sessions"]))
        for name in ("sortino", "max_drawdown", "volatility"):  # So the two sources can be told apart.
            self.assertNotEqual(excess[name], raw[name], name)

    def test_selected_lines_too_small_for_one_share_are_counted(self):
        plan = fixture(TrendPlan, universe=("A", "B"), average_months=2)
        data = snapshot()
        result = run_backtest(data, build_plan(data, plan, None, FREE), RunConfig("20", FREE, plan.universe))
        # A quarter of $20 buys no $12 share of A in February or $21 share of B in March.
        self.assertEqual(results(result)["whole_share_shortfalls"], 2)
        capped = fixture(TrendPlan, universe=("A", "B"), average_months=2, max_volume_participation="0.00001")
        result = run_backtest(data, build_plan(data, capped, None, FREE), RunConfig("1000", FREE, plan.universe))
        self.assertEqual(results(result)["whole_share_shortfalls"], 0)  # The budget buys shares; the cap blocks them.

    def test_a_held_line_sold_because_its_budget_buys_no_share_is_counted(self):
        plan = fixture(FixedWeightPlan, universe=("A", "B"), weights=(("A", "0.6"), ("B", "0.4")))
        data = snapshot({"A": (10, 10, 15, 20, 20, 20, 20, 20), "B": (20,) * 8})
        result = run_backtest(data, build_plan(data, plan, None, FREE), RunConfig("40", FREE, plan.universe))
        sold = [d for d in result.signal_decisions if d.action == "sell"]
        # Jan 28: 30% of $40 buys one $10 A; B's $8 buys no $20 share. Feb 28: equity 45 buys no $20 A, so the
        # A held is sold; B again none. Mar 28: neither. Five selected lines with a zero-share target.
        self.assertEqual([(d.security_id, d.target_quantity) for d in sold], [("A", 0)])
        self.assertEqual(results(result)["whole_share_shortfalls"], 5)


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
        self.assertEqual(period(self.SERIES, date(2024, 1, 2), date(2024, 1, 2))["sessions"], 1)  # Both ends count.
        flat = series(self.DAYS, ("100", "100", "100", "100"))
        self.assertIsNone(period(flat, date(2023, 1, 1), date(2024, 12, 31))["sharpe"])  # No variance.

    def test_a_year_that_starts_below_an_earlier_peak_is_measured_from_its_own_start(self):
        days = (date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29), date(2024, 1, 2), date(2024, 1, 3))
        years = calendar_years(series(days, ("100", "130", "120", "110", "125")))
        self.assertEqual(years["2024"]["max_drawdown"], 1 - D(110) / 120)  # From 120, not from 2023's 130.

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
        on_session = periods(series(days, ("100", "110", "121", "133.1")), publication=date(2020, 1, 2))
        self.assertEqual(on_session["since_publication"]["sessions"], 3)
        self.assertEqual(sections["segments"]["early"]["return"], D("0.1"))  # 2019-12-31 and 2020-01-02.
        self.assertEqual(set(sections), {"calendar_years", "windows", "since_publication", "segments",
                                         "twelve_months", "drawdowns"})
        self.assertIsNone(periods(series(days, ("100",) * 4))["since_publication"])


class TwelveMonthTests(unittest.TestCase):
    DAYS = [date(2023, month, 28) for month in range(1, 13)] + [date(2024, 1, 31), date(2024, 2, 28),
                                                               date(2024, 3, 1)]
    EQUITY = ["100"] * 12 + ["120", "90", "90"]  # Jan to Jan: +20%; Feb to Feb: -10%. March is unfinished.

    def test_best_and_worst_twelve_months_between_month_ends(self):
        extremes = twelve_month_extremes(series(self.DAYS, self.EQUITY))
        self.assertEqual(extremes["best"], {"start": "2023-01-28", "end": "2024-01-31", "return": D("0.2")})
        self.assertEqual(extremes["worst"], {"start": "2023-02-28", "end": "2024-02-28", "return": D("-0.1")})
        self.assertIsNone(twelve_month_extremes(series(self.DAYS[:13], self.EQUITY[:13])))  # Jan 2024 unfinished.
        self.assertIsNone(twelve_month_extremes(series(self.DAYS[:12], self.EQUITY[:12])))

    def test_months_are_matched_by_the_calendar_not_by_position(self):
        gap = self.DAYS[:5] + self.DAYS[6:]  # No June: Jan and Feb still have their twelve-month pairs.
        extremes = twelve_month_extremes(series(gap, self.EQUITY[:5] + self.EQUITY[6:]))
        self.assertEqual((extremes["best"]["return"], extremes["worst"]["return"]), (D("0.2"), D("-0.1")))


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


def steady(count, daily="0.001", excess=None):
    days = [date(2024, 1, 1) + (date(2024, 1, 2) - date(2024, 1, 1)) * i for i in range(count)]
    equity, value = [], D(100)
    for _ in range(count):
        value *= 1 + D(daily)
        equity.append(value)
    return series(days, equity, excess=excess)


class BootstrapTests(unittest.TestCase):
    def test_a_steady_series_has_a_known_answer_and_runs_repeat_exactly(self):
        run = steady(30)
        result = bootstrap(run, run, block_lengths=(5,), repetitions=100, seed=7)
        block = result["blocks"]["5"]
        low, high = block["annualized_return_252"]  # Every resample of a steady 0.1% a day is the same.
        self.assertAlmostEqual(low, D("1.001") ** 252 - 1, places=20)
        self.assertAlmostEqual(high, D("1.001") ** 252 - 1, places=20)
        self.assertEqual(block["max_drawdown"], (0, 0))
        self.assertEqual((block["sharpe"], block["defined_sharpe_replicates"]), ((None, None), 0))  # No variance.
        self.assertEqual(bootstrap(run, run, block_lengths=(5,), repetitions=100, seed=7), result)
        self.assertEqual((result["repetitions"], result["seed"]), (100, 7))

    def test_the_reference_is_resampled_on_the_same_sessions(self):
        days = [date(2024, 1, 1) + (date(2024, 1, 2) - date(2024, 1, 1)) * i for i in range(40)]
        noisy = series(days, [str(100 + (i % 5) - 2 * (i % 3)) for i in range(40)])
        result = bootstrap(noisy, noisy, block_lengths=(5, 20), repetitions=100, seed=1)
        for block in ("5", "20"):
            self.assertEqual(result["blocks"][block]["sharpe_minus_reference"], (0, 0))  # Itself: no difference.
            low, high = result["blocks"][block]["sharpe"]
            self.assertLess(low, high)
        self.assertNotEqual(result["blocks"]["5"], bootstrap(noisy, noisy, block_lengths=(5,), repetitions=100,
                                                             seed=2)["blocks"]["5"])
        alone = bootstrap(noisy, block_lengths=(5,), repetitions=100)
        self.assertIsNone(alone["blocks"]["5"]["sharpe_minus_reference"])
        with self.assertRaisesRegex(ValueError, "same sessions"):
            bootstrap(noisy, steady(39), block_lengths=(5,), repetitions=100)
        with self.assertRaisesRegex(ValueError, ">=100 repetitions"):
            bootstrap(noisy, repetitions=99)
        with self.assertRaisesRegex(ValueError, "Block length"):
            bootstrap(noisy, block_lengths=(41,), repetitions=100)


    def test_resampled_paths_give_known_extremes(self):
        days = (date(2024, 1, 1), date(2024, 1, 2))
        two = series(days, ("110", "99"))  # +10% then -10%; one-session blocks draw each day independently.
        block = bootstrap(two, block_lengths=(1,), repetitions=100, seed=0)["blocks"]["1"]
        self.assertEqual(block["max_drawdown"], (0, D("0.19")))  # Up twice; down twice.
        self.assertEqual(block["annualized_return_252"], (D("0.81") ** 126 - 1, D("1.21") ** 126 - 1))

    def test_each_block_length_starts_again_at_the_seed(self):
        days = [date(2024, 1, 1) + (date(2024, 1, 2) - date(2024, 1, 1)) * i for i in range(40)]
        noisy = series(days, [str(100 + (i % 5) - 2 * (i % 3)) for i in range(40)])
        both = bootstrap(noisy, noisy, block_lengths=(5, 20), repetitions=100, seed=3)
        self.assertEqual(both["blocks"]["20"], bootstrap(noisy, noisy, block_lengths=(20,), repetitions=100,
                                                         seed=3)["blocks"]["20"])


class DeflatedTests(unittest.TestCase):
    def test_the_larger_variance_is_primary(self):
        days = [date(2024, 1, 1) + (date(2024, 1, 2) - date(2024, 1, 1)) * i for i in range(20)]
        runs = [series(days, [str(100 + (i * k) % 7) for i in range(20)]) for k in (1, 2, 3)]
        parent, neighbours = runs[0], runs[1:]
        own = sharpe_variance([return_moments(run.excess)["sharpe"] for run in runs])
        for floor in (own / 2, own * 2):
            with self.subTest(floor=floor):
                report = deflated(parent, neighbours, 50, floor)
                self.assertEqual((report["own_variance"], report["floor_variance"], report["trials"]),
                                 (own, floor, 50))
                self.assertEqual(report["primary"], deflated_sharpe(parent.excess, 50, max(own, floor)))
                self.assertEqual(report["alternative"], deflated_sharpe(parent.excess, 50, min(own, floor)))
        with self.assertRaisesRegex(ValueError, "at least two neighbours"):
            deflated(parent, neighbours[:1], 50, own)


class OverlapTests(unittest.TestCase):
    DAYS = (date(2024, 1, 30), date(2024, 1, 31), date(2024, 2, 28), date(2024, 2, 29))

    def test_correlation_of_excess_returns_on_shared_sessions(self):
        a = series(self.DAYS, ("100", "110", "99", "108.9"))
        mirror = RunSeries(a.sessions, a.returns, tuple(-x for x in a.excess), a.equity, a.weights, a.initial_cash)
        self.assertAlmostEqual(correlation(a, a), 1, places=25)
        self.assertAlmostEqual(correlation(a, mirror), -1, places=25)
        self.assertIsNone(correlation(a, series(self.DAYS, ("100",) * 4)))  # No variance.
        self.assertIsNone(correlation(a, series(self.DAYS[:1], ("100",))))
        later = (date(2024, 1, 31), date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1))
        left = RunSeries(self.DAYS, (D(0),) * 4, (D(5), D(1), D(2), D(3)), (D(1),) * 4, ((),) * 4, D(1))
        right = RunSeries(later, (D(0),) * 4, (D(1), D(2), D(3), D(0)), (D(1),) * 4, ((),) * 4, D(1))
        self.assertAlmostEqual(correlation(left, right), 1, places=25)  # Jan 31 to Feb 29: 1, 2, 3 against 1, 2, 3.

    def test_holdings_overlap_at_shared_month_ends(self):
        def holding(*weights):
            return RunSeries(self.DAYS, (D(0),) * 4, (D(0),) * 4, (D(100),) * 4,
                             tuple(tuple((asset, D(w)) for asset, w in day) for day in weights), D(100))
        a = holding((), (("A", "0.6"), ("B", "0.4")), (("A", "1"),), (("A", "0.5"), ("B", "0.5")))
        b = holding((("A", "1"),), (("A", "0.5"), ("C", "0.5")), (), (("B", "0.95"),))
        # Month ends Jan 31 and Feb 29: min(0.6, 0.5) = 0.5, then min(0.5, 0.95) = 0.5; Jan 30 and Feb 28 ignored.
        self.assertEqual(holdings_overlap(a, b), D("0.5"))
        later = RunSeries((date(2025, 1, 1),), (D(0),), (D(0),), (D(1),), ((),), D(1))
        self.assertIsNone(holdings_overlap(a, later))  # No shared month end.


if __name__ == "__main__":
    unittest.main()
