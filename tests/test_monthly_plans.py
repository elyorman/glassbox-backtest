"""Built-in plans through the engine: decision sessions, data checks, T-bills, hand-worked portfolios."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from quant_core.backtest import RunConfig, run_backtest
from quant_core.data import Bar, DataMetadata, Dividend, RAW_PRICES_SPLIT_ADJUSTED_VOLUME, Security, Snapshot, Split
from quant_core.data.rates import CashRateSeries
from quant_core.execution import ExecutionProfile
from quant_core.risk import RiskPolicy
from quant_core.strategies.plans import (
    DualMomentumPlan, InverseVolatilityPlan, MonthlyPlan, SectorRotationPlan, TrendPlan, build_plan,
    decision_sessions,
)

D = Decimal
FREE = ExecutionProfile("0")
META = DataMetadata("synthetic_plans", datetime(2024, 5, 1, tzinfo=timezone.utc), "fixed_engineering_sample",
                    True, "synthetic_explicit_sessions")
# Two sessions a month; month-end decisions fall on the 28th of January, February and March.
DAYS = tuple(date(2024, month, day) for month in (1, 2, 3, 4) for day in (27, 28))
J28, F27, F28, M27, M28, A27 = DAYS[1], DAYS[2], DAYS[3], DAYS[4], DAYS[5], DAYS[6]
PRICES = {"A": (10, 10, 11, 12, 12, 11, 11, 11), "B": (20, 20, 19, 18, 18, 21, 21, 21)}


def snapshot(prices=PRICES, actions=(), listed=None, skip=(), quiet=()):
    bars = tuple(Bar(asset, day, price, price, price, price, 0 if (asset, day) in quiet else 1000)
                 for asset, series in prices.items() for day, price in zip(DAYS, series)
                 if price is not None and (asset, day) not in skip)
    listed = listed or {}
    return Snapshot(DAYS, bars, META, tuple(Security(a, a, "SYNTHETIC", listed.get(a)) for a in prices), actions)


def rates(rate="0.365", changed_from=None, changed_rate="0.9", first=date(2023, 12, 1), end=date(2024, 5, 1)):
    days = (first + timedelta(i) for i in range((end - first).days))
    return CashRateSeries("test", "test_bills", META.retrieved_at, tuple(
        (day, changed_rate if changed_from and day >= changed_from else rate) for day in days))


def fixture(plan_class, **options):
    return plan_class(**{"name": "fixture", "invested_fraction": "0.5", "volume_lookback": 1,
                         "max_volume_participation": "1", "purpose": "engineering_fixture", **options})


def run(plan, data=None, bills=None, start=None, **settings):
    data = data or snapshot()
    source = build_plan(data, plan, start, FREE, bills)
    return run_backtest(data, source, RunConfig("1000", FREE, plan.universe, start, **settings))


def fills(result):
    return [(f.execution_date, f.security_id, f.side, f.quantity, f.price) for f in result.fills]


def decided(result, day):
    return {d.security_id: d for d in result.signal_decisions if d.session == day}


class DecisionSessionTests(unittest.TestCase):
    def test_month_ends_move_by_the_offset_and_the_unfinished_month_is_never_a_decision(self):
        calendar = (date(2024, 1, 27), date(2024, 1, 28), date(2024, 2, 27), date(2024, 3, 27), date(2024, 3, 28),
                    date(2024, 4, 27))
        jan27, jan28, feb27, mar27, mar28, apr27 = calendar
        self.assertEqual(decision_sessions(calendar), (jan28, feb27, mar28))  # February's last session is the 27th.
        self.assertEqual(decision_sessions(calendar, 1), (feb27, mar27, apr27))
        self.assertEqual(decision_sessions(calendar, -1), (jan27, jan28, mar27))
        self.assertEqual(decision_sessions(calendar, 2), (mar27, mar28))
        self.assertEqual(decision_sessions(calendar, -2), (jan27, feb27))

    def test_an_offset_moves_the_decisions_and_the_values_they_compare(self):
        plan = fixture(TrendPlan, universe=("A", "B"), average_months=2, decision_offset=-1)
        result = run(plan)
        self.assertEqual(result.manifest.source.decision_sessions, (DAYS[0], DAYS[2], DAYS[4]))
        # On March 27: A's values on Feb 27 and Mar 27 are 11 and 12, so A is above its average.
        self.assertEqual(decided(result, M27)["A"].reason_codes, ("above_average",))
        self.assertEqual({d.session for d in result.signal_decisions}, {DAYS[0], DAYS[2], DAYS[4]})


class HandWorkedRunTests(unittest.TestCase):
    def test_trend_holds_each_asset_while_above_its_average(self):
        result = run(fixture(TrendPlan, universe=("A", "B"), average_months=2))
        # Jan 28: one month-end only. Feb 28: A (10, 12) is above 11; B (20, 18) is not. A's quarter of
        # $1,000 buys floor(250 / 12) = 20 shares at the next open, $12.
        self.assertEqual(decided(result, J28)["A"].reason_codes, ("insufficient_history",))
        self.assertEqual(decided(result, F28)["A"].target_fraction, D("0.25"))
        # Mar 28: A (12, 11) falls below 11.5 and is sold; B (18, 21) is above 19.5. Equity 760 + 20 x 11 = 980
        # buys floor(245 / 21) = 11 shares of B.
        self.assertEqual(fills(result), [(M27, "A", "buy", 20, 12), (A27, "A", "sell", 20, 11),
                                         (A27, "B", "buy", 11, 21)])
        self.assertEqual(result.summary.final_equity, D("980"))
        self.assertEqual(decided(result, M28)["A"].action, "sell")

    def test_sector_rotation_holds_the_top_ranked_asset(self):
        plan = fixture(SectorRotationPlan, universe=("A", "B"), lookback_months=1, skip_months=0, top=1)
        result = run(plan)
        # Feb 28: A +20% beats B -10%; half of $1,000 buys floor(500 / 12) = 41 shares. Mar 28: B +16.7% leads;
        # equity 508 + 41 x 11 = 959 buys floor(479.5 / 21) = 22 shares of B.
        self.assertEqual(fills(result), [(M27, "A", "buy", 41, 12), (A27, "A", "sell", 41, 11),
                                         (A27, "B", "buy", 22, 21)])
        self.assertEqual(result.summary.final_equity, D("959"))
        self.assertEqual((decided(result, M28)["B"].rank, decided(result, M28)["A"].rank), (1, 2))
        self.assertEqual([o.request.priority for o in result.orders], [1, 2, 1])  # Orders carry the rank.

    def test_dual_momentum_compares_us_stocks_with_compounded_t_bills(self):
        prices = {"U": (100, 100, 103, 105, 105, 106, 106, 106), "N": (50, 50, 52, 54, 54, 55, 55, 55),
                  "B": (25,) * 8}
        plan = fixture(DualMomentumPlan, universe=("U", "N", "B"), us_stocks="U", non_us_stocks="N", bonds="B",
                       lookback_months=1)
        result = run(plan, snapshot(prices), rates())
        # T-bills at 36.5% earn 0.1% a calendar day: Jan 28 to Feb 28 is 30 days then 1 day,
        # growth 1.03 x 1.001 = 1.03103. US +5% beats 3.103%, non-US +8% is stronger: buy N.
        february = decided(result, F28)
        self.assertEqual(dict(february["N"].features)["bill_lookback_return"], D("0.03103"))
        self.assertEqual(february["N"].reason_codes, ("us_stocks_beat_bills", "higher_lookback_return"))
        # Feb 28 to Mar 28 is 28 days then 1 day: 2.9028%; US +0.95% loses, so bonds.
        self.assertEqual(decided(result, M28)["B"].reason_codes, ("bills_beat_us_stocks", "bond_fallback"))
        # floor(500 / 54) = 9 N; then equity 514 + 9 x 55 = 1,009 buys floor(504.5 / 25) = 20 B.
        self.assertEqual(fills(result), [(M27, "N", "buy", 9, 54), (A27, "N", "sell", 9, 55),
                                         (A27, "B", "buy", 20, 25)])
        self.assertEqual(result.summary.final_equity, D("1009"))
        self.assertEqual(decided(result, J28)["B"].reason_codes, ("plan_input_unavailable",))

    def test_inverse_volatility_weights_become_whole_shares(self):
        prices = {"A": (100, 100, 105, 110, 110, 99, 99, 99), "B": (100, 100, 110, 120, 120, 96, 96, 96)}
        plan = fixture(InverseVolatilityPlan, universe=("A", "B"), volatility_months=2)
        result = run(plan, snapshot(prices), rates("0"))
        # With zero T-bills, A's returns (+10%, -10%) are half as volatile as B's (+20%, -20%): weights 2/3, 1/3.
        march = decided(result, M28)
        self.assertAlmostEqual(march["A"].target_fraction, D(1) / 3, places=20)
        # floor(1000 x 1/3 / 99) = 3 A and floor(1000 x 1/6 / 96) = 1 B.
        self.assertEqual(fills(result), [(A27, "A", "buy", 3, 99), (A27, "B", "buy", 1, 96)])

    def test_inverse_volatility_pairs_each_month_with_its_own_t_bills(self):
        prices = {"A": (100, 100, 105, 110, 110, 99, 99, 99), "B": (100, 100, 110, 120, 120, 96, 96, 96)}
        plan = fixture(InverseVolatilityPlan, universe=("A", "B"), volatility_months=2)
        # 36.5% until Feb 19, then 0%: January's month earns 30 days at 0.1% a day (1.03), March's nothing.
        result = run(plan, snapshot(prices), rates(changed_from=date(2024, 2, 20), changed_rate="0"))
        # A: +10% - 3% = 0.07, then -10% - 0% = -0.10; two values 0.17 apart have sample variance 0.17^2 / 2.
        self.assertEqual(dict(decided(result, M28)["A"].features)["monthly_excess_volatility"], D("0.01445").sqrt())


class LookAheadTests(unittest.TestCase):
    def test_later_prices_actions_and_rates_do_not_change_earlier_decisions(self):
        plan = fixture(DualMomentumPlan, universe=("U", "N", "B"), us_stocks="U", non_us_stocks="N", bonds="B",
                       lookback_months=1)
        prices = {"U": (100, 100, 103, 105, 105, 106, 106, 106), "N": (50, 50, 52, 54, 54, 55, 55, 55),
                  "B": (25,) * 8}
        base = run(plan, snapshot(prices), rates())
        later = {asset: series[:5] + (1, 1, 1) for asset, series in prices.items()}
        actions = (Split("N", M28, new_shares=2, old_shares=1), Dividend("U", M28, "3", M28))
        changed = run(plan, snapshot(later, actions), rates(changed_from=F27))
        for day in (J28, F28):
            self.assertEqual(decided(base, day), decided(changed, day))
        self.assertEqual(fills(base)[:1], fills(changed)[:1])  # The March 27 fill comes before every change.

    def test_splits_and_dividends_inside_the_lookback_are_total_return(self):
        # A splits 2-for-1 on Feb 27: 5.5 and 6 are 11 and 12 before the split. B's $2 dividend on Feb 28
        # makes 19 worth 21 against 20.
        prices = {"A": (10, 10, "5.5", 6, 6, 6, 6, 6), "B": (20, 20, 20, 19, 19, 19, 19, 19)}
        actions = (Split("A", F27, new_shares=2, old_shares=1), Dividend("B", F28, "2", F28))
        february = decided(run(fixture(TrendPlan, universe=("A", "B"), average_months=2, volume_lookback=4),
                               snapshot(prices, actions)), F28)
        self.assertEqual(dict(february["A"].features)["month_end_value"], D("1.2"))
        # Four sessions of 1,000 shares; the two before the split count as 2,000 post-split shares each.
        self.assertEqual(dict(february["A"].features)["average_volume"], D("1500"))
        self.assertEqual(dict(february["B"].features)["month_end_value"], D("1.05"))
        self.assertTrue(february["A"].selected and february["B"].selected)


class DataCheckTests(unittest.TestCase):
    def test_a_late_listing_joins_once_its_history_covers_the_lookback(self):
        prices = dict(PRICES, C=(None, None, 30, 30, 30, 33, 33, 33))
        result = run(fixture(TrendPlan, universe=("A", "B", "C"), average_months=2),
                     snapshot(prices, listed={"C": F27}))
        self.assertEqual(decided(result, J28)["C"].reason_codes, ("outside_security_lifetime",))
        self.assertEqual(decided(result, F28)["C"].reason_codes, ("insufficient_history",))
        self.assertEqual(decided(result, M28)["C"].reason_codes, ("above_average",))

    def test_a_missing_session_skips_the_security_with_its_reason(self):
        result = run(fixture(TrendPlan, universe=("A", "B"), average_months=2), snapshot(skip={("B", F27)}),
                     data_policy="allow_missing_unheld_diagnostic")
        self.assertEqual(decided(result, F28)["B"].reason_codes, ("missing_history_session",))
        self.assertFalse(decided(result, F28)["B"].eligible)
        result = run(fixture(TrendPlan, universe=("A", "B"), average_months=2), snapshot(skip={("B", F28)}),
                     data_policy="allow_missing_unheld_diagnostic")
        self.assertEqual(decided(result, F28)["B"].reason_codes, ("missing_signal_bar",))

    def test_no_volume_over_the_lookback_skips_the_security(self):
        result = run(fixture(TrendPlan, universe=("A", "B"), average_months=2), snapshot(quiet={("A", F28)}))
        self.assertEqual(decided(result, F28)["A"].reason_codes, ("liquidity_filter",))
        self.assertEqual(fills(result)[0][1], "B")  # A is never bought; B is, after March.

    def test_decisions_do_not_depend_on_idle_cash_interest(self):
        prices = {"U": (100, 100, 103, 105, 105, 106, 106, 106), "N": (50, 50, 52, 54, 54, 55, 55, 55),
                  "B": (25,) * 8}
        plan = fixture(DualMomentumPlan, universe=("U", "N", "B"), us_stocks="U", non_us_stocks="N", bonds="B",
                       lookback_months=1)
        plain = run(plan, snapshot(prices), rates())
        earning = run(plan, snapshot(prices), rates(), cash_rates=rates())
        self.assertGreater(earning.equity[-1].interest_income, 0)
        choices = lambda r: [(d.session, d.security_id, d.selected, d.target_fraction, d.score)
                             for d in r.signal_decisions]
        self.assertEqual(choices(plain), choices(earning))


class PreflightTests(unittest.TestCase):
    DUAL = fixture(DualMomentumPlan, universe=("U", "N", "B"), us_stocks="U", non_us_stocks="N", bonds="B",
                   lookback_months=1)
    DATA = snapshot({"U": (100,) * 8, "N": (50,) * 8, "B": (25,) * 8})

    def test_t_bill_rates_must_cover_the_lookback_before_the_run_start(self):
        late = rates(first=date(2024, 2, 20))  # Covers the run from Feb 28, not its lookback from Jan 28.
        with self.assertRaisesRegex(ValueError, "must cover every lookback in the run: No test_bills "
                                                "observation before 2024-01-28"):
            run(self.DUAL, self.DATA, late, start=F28)
        run(self.DUAL, self.DATA, late, start=M28)  # March's lookback starts on Feb 28.
        early = rates(end=date(2024, 3, 10))  # Its last observation, Mar 9, is stale for March's lookback.
        with self.assertRaisesRegex(ValueError, "must cover every lookback in the run: test_bills is stale for "
                                                "2024-03-27"):
            run(self.DUAL, self.DATA, early, start=F28)

    def test_bindings_and_settings_are_checked(self):
        trend = fixture(TrendPlan, universe=("A", "B"), average_months=2)
        with self.assertRaisesRegex(ValueError, "need their own T-bill rates"):
            build_plan(self.DATA, self.DUAL)
        with self.assertRaisesRegex(ValueError, "need their own T-bill rates"):
            build_plan(snapshot(), trend, cash_rates=rates())
        with self.assertRaisesRegex(ValueError, "require risk=None"):
            run(trend, risk=RiskPolicy())
        with self.assertRaisesRegex(ValueError, "frozen run binding"):
            run_backtest(snapshot(), build_plan(snapshot(), trend, J28, FREE),
                         RunConfig("1000", FREE, trend.universe, F28))
        with self.assertRaisesRegex(ValueError, "costs must match"):
            run_backtest(snapshot(), build_plan(snapshot(), trend, None, ExecutionProfile("10")),
                         RunConfig("1000", FREE, trend.universe))
        with self.assertRaisesRegex(ValueError, "unknown security"):
            build_plan(snapshot(), replace(trend, universe=("A", "X")))
        with self.assertRaisesRegex(ValueError, "decision sessions"):
            build_plan(snapshot(), trend).evaluate(_Context(F27))
        early = build_plan(snapshot(), trend, M28).orders(_Context(F28))
        self.assertEqual((early.requests, early.decisions), ((), ()))  # Before the first signal session.

    def test_data_declarations_are_checked(self):
        trend, data = fixture(TrendPlan, universe=("A", "B"), average_months=2), snapshot()
        source = build_plan(data, trend, None, FREE)
        cases = ((replace(data, metadata=replace(META, actions_complete=False)), RunConfig("1000", FREE, ("A", "B")),
                  "require declared complete corporate actions"),
                 (data, RunConfig("1000", FREE, ("A",)), "outside the run universe"),
                 (replace(data, securities=(Security("A", "A", "OTHER"), Security("B", "B", "SYNTHETIC"))),
                  RunConfig("1000", FREE, ("A", "B")), "registry disagrees"),
                 (replace(data, metadata=replace(META, adjustment_policy=RAW_PRICES_SPLIT_ADJUSTED_VOLUME)),
                  RunConfig("1000", FREE, ("A", "B")), "raw share volume required"),
                 (replace(data, sessions=DAYS[:-1], bars=tuple(b for b in data.bars if b.session != DAYS[-1])),
                  RunConfig("1000", FREE, ("A", "B")), "frozen run binding"))
        for snapshot_, settings, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                run_backtest(snapshot_, source, settings)

    def test_the_source_hash_covers_rule_calendar_execution_and_rates(self):
        trend = fixture(TrendPlan, universe=("A", "B"), average_months=2)
        hashes = {build_plan(snapshot(), trend).spec.artifact_hash,
                  build_plan(snapshot(), replace(trend, average_months=3)).spec.artifact_hash,
                  build_plan(snapshot(), trend, execution=ExecutionProfile("25")).spec.artifact_hash,
                  build_plan(self.DATA, self.DUAL, cash_rates=rates()).spec.artifact_hash,
                  build_plan(self.DATA, self.DUAL, cash_rates=rates("0.1")).spec.artifact_hash}
        self.assertEqual(len(hashes), 5)
        self.assertEqual(build_plan(snapshot(), trend).spec.artifact_hash,
                         build_plan(snapshot(), trend).spec.artifact_hash)


class _Context:
    def __init__(self, as_of):
        self.as_of = as_of


if __name__ == "__main__":
    unittest.main()
