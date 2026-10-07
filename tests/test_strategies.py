"""Causal features, exact strategy rules and independent synthetic portfolios."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.backtest import RunConfig, SourceSpec, run_backtest
from quant_core.backtest.cli import main
from quant_core.backtest.contracts import SignalDecision
from quant_core.backtest.sources import OrderBatch
from quant_core.data import Bar, Dividend, DataMetadata, Security, Snapshot, Split
from quant_core.data.csv_source import CsvSource
from quant_core.data.storage import save_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.features import signal_prices, trailing_return, trailing_mean, nearness_to_high
from quant_core.provenance import content_hash, canonical_json, primitive
from quant_core.reporting import save_run, verify_run, SCHEMA_FILES
from quant_core.risk import RiskPolicy
from quant_core.strategies import (
    StrategyConfig, benchmark_recipes, build_strategy, initial_recipes, load_config,
    rebalance_dates, save_recipe_registry,
)
from quant_core.strategies.cli import main as registry_main

D = Decimal
META = DataMetadata("synthetic_strategy", datetime(2024, 3, 10, tzinfo=timezone.utc),
                    "fixed_engineering_sample", True, "synthetic_explicit_sessions")
DAYS = tuple(date.fromisoformat(d) for d in ("2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-05"))


def snapshot(paths=None, sessions=DAYS, actions=(), highs=None, volumes=None, securities=None):
    paths = paths or {"A": (100, 110, 120, 125, 128, 130), "B": (100, 95, 90, 90, 85, 80)}
    bars = []
    for asset, values in paths.items():
        for index, (day, price) in enumerate(zip(sessions, values)):
            high = max(price, highs[asset][index]) if highs is not None else price
            volume = volumes[asset][index] if volumes is not None else 10000
            bars.append(Bar(asset, day, price, high, price, price, volume))
    return Snapshot(tuple(sessions), tuple(bars), META,
                    tuple(securities) if securities is not None else tuple(Security(a, a, "SYNTHETIC") for a in paths), tuple(actions))


def config(family="momentum", **kwargs):
    options = dict(name="engineering_" + family, family=family, universe=("A", "B"),
                   mean_window=3, momentum_lookback=2, momentum_skip=0, high_window=3,
                   reversal_window=1, top_k=1, invested_fraction="0.50", volume_lookback=1,
                   max_volume_participation="1", atr_period=2, purpose="engineering_fixture")
    options.update(kwargs)
    return StrategyConfig(**options)


def run(cfg=None, data=None, cash="1000", start=None, **kwargs):
    data, cfg = data or snapshot(), cfg or config()
    execution = kwargs.pop("execution", ExecutionProfile("0"))
    source = build_strategy(data, cfg, start, execution)
    return run_backtest(data, source, RunConfig(cash, execution,
                                               cfg.universe, start, **kwargs))


class FeatureTests(unittest.TestCase):
    def test_endpoints_mean_high_and_skip_month_return(self):
        prices = (D(100), D(110), D(120), D(50))
        self.assertEqual(trailing_return(prices, 3, 1), D("0.2"))
        self.assertEqual(trailing_return(prices, 3), D("-0.5"))
        self.assertEqual(trailing_mean(prices, 3), D(280) / 3)
        self.assertEqual(nearness_to_high(prices, 3), D(50) / 120)
        self.assertIsNone(trailing_return(prices[:3], 3))
        self.assertIsNone(trailing_mean(prices, 5))
        self.assertIsNone(nearness_to_high(prices, 5))

    def test_invalid_windows_and_returns_are_rejected(self):
        for window in (0, -1, True, 2.0):
            for feature in (trailing_mean, nearness_to_high, trailing_return):
                with self.subTest(window=window, feature=feature), self.assertRaises(ValueError):
                    feature((D(1),), window)
        for skip in (-1, 3, True):
            with self.assertRaises(ValueError):
                trailing_return((D(1),) * 4, 3, skip)

    def test_split_and_same_day_dividend_leave_total_return_flat(self):
        bars = (Bar("A", DAYS[0], 100, 100, 100, 100, 1000),
                Bar("A", DAYS[1], 49, 49, 49, 49, 2000))
        splits = (Split("A", DAYS[1], 2),)
        dividends = (Dividend("A", DAYS[1], 1, DAYS[3]),)
        self.assertEqual(signal_prices(bars, splits, dividends), (D(1), D(1)))
        self.assertEqual(bars[0].close, 100)

    def test_dividend_before_later_split_is_normalized_in_correct_units(self):
        bars = tuple(Bar("A", day, p, p, p, p, 1000) for day, p in zip(DAYS, (100, 99, D("49.5"))))
        self.assertEqual(signal_prices(bars, (Split("A", DAYS[2], 2),),
                                       (Dividend("A", DAYS[1], 1, DAYS[3]),)), (D(1), D(1), D(1)))

    def test_signals_reinvest_dividend_at_ex_close_independently_of_payment(self):
        bars = tuple(Bar("A", d, p, p, p, p, 1000) for d, p in zip(DAYS, (100, 99, 100)))
        first = signal_prices(bars, dividends=(Dividend("A", DAYS[1], 1, DAYS[2]),))
        second = signal_prices(bars, dividends=(Dividend("A", DAYS[1], 1, DAYS[5]),))
        self.assertEqual(first, second)
        self.assertEqual(first[-1], D(100) / 99)

    def test_future_actions_do_not_change_current_signal_prices(self):
        bars = tuple(Bar("A", d, p, p, p, p, 1000) for d, p in zip(DAYS, (100, 110, 120)))
        self.assertEqual(signal_prices(bars), signal_prices(bars, (Split("A", DAYS[4], 2),),
                                                          (Dividend("A", DAYS[4], 1, DAYS[5]),)))

    def test_appending_later_split_does_not_recalculate_earlier_index_values(self):
        bars = tuple(Bar("A", d, p, p, p, p, 1000) for d, p in zip(DAYS, (103, 107, 109, D("55.5"))))
        prefix = signal_prices(bars[:3])
        full = signal_prices(bars, (Split("A", DAYS[3], 2),), (Dividend("A", DAYS[3], 1, DAYS[5]),))
        self.assertEqual(prefix, full[:3])

    def test_signal_series_rejects_mixed_or_unordered_history(self):
        a = Bar("A", DAYS[0], 100, 100, 100, 100, 1)
        for bars in ((a, a), (replace(a, session=DAYS[1]), a), (a, replace(a, security_id="B", session=DAYS[1]))):
            with self.assertRaises(ValueError):
                signal_prices(bars)


class CalendarAndConfigurationTests(unittest.TestCase):
    def test_calendar_month_week_holidays_and_truncated_last_period(self):
        calendar = tuple(date.fromisoformat(d) for d in ("2023-12-28", "2023-12-29", "2024-01-02",
                          "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"))
        self.assertEqual(rebalance_dates(calendar, "month_end"), (date(2023, 12, 29),))
        self.assertEqual(rebalance_dates(calendar, "week_end"), (date(2023, 12, 29), date(2024, 1, 5)))
        self.assertNotIn(calendar[-1], rebalance_dates(calendar, "week_end"))
        with self.assertRaises(ValueError):
            rebalance_dates(tuple(reversed(calendar)), "month_end")

    def test_configuration_rejects_ambiguous_or_unsafe_values(self):
        for changes in ({"family": "ml"}, {"universe": ()}, {"universe": ("A", "A")},
                        {"profile": "kelly"}, {"mean_window": True}, {"momentum_skip": 2},
                        {"invested_fraction": "1.1"}, {"min_price": "-1"},
                        {"risk_fraction": .01}, {"volume_lookback": 0}, {"top_k": 0},
                        {"family": "cash", "profile": "atr_protected"}, {"family": "buy_hold"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                config(**changes)

    def test_freezing_configuration_registry_and_source_metadata(self):
        universe = ["B", "A"]
        cfg = config(universe=universe)
        universe.append("C")
        self.assertEqual(cfg.universe, ("A", "B"))
        with self.assertRaises(FrozenInstanceError):
            cfg.top_k = 99
        source = build_strategy(snapshot(), cfg)
        self.assertEqual(source.spec.configuration, cfg)
        self.assertEqual(source.spec, build_strategy(snapshot(), cfg).spec)
        self.assertNotEqual(source.spec.artifact_hash, build_strategy(snapshot(), replace(cfg, top_k=2)).spec.artifact_hash)

    def test_exactly_ten_initial_recipes_and_four_explicit_benchmark_configs(self):
        recipes = initial_recipes(("A", "B"))
        self.assertEqual(len(recipes), 10)
        self.assertEqual(len({content_hash(r) for r in recipes}), 10)
        self.assertEqual([r.mean_window for r in recipes if r.family == "trend"], [100, 200])
        self.assertEqual([(r.momentum_lookback, r.top_k) for r in recipes if r.family == "momentum"],
                         [(126, 3), (126, 5), (252, 3), (252, 5)])
        self.assertEqual([r.reversal_window for r in recipes if r.family == "reversal"], [3, 5])
        self.assertTrue(all(r.profile == "scheduled_slots" for r in recipes))
        benchmarks = benchmark_recipes(("A", "B"), "SPY-ID")
        self.assertEqual([r.family for r in benchmarks], ["buy_hold", "buy_hold", "equal_weight", "cash"])
        self.assertEqual(benchmarks[0].universe, ("SPY-ID",))
        self.assertEqual(benchmarks[0].invested_fraction, 1)
        self.assertEqual(benchmarks[1].invested_fraction, D("0.95"))

    def test_wrong_universe_or_bound_start_fails_before_running(self):
        source = build_strategy(snapshot(), config())
        for cfg in (RunConfig("1000", universe=("A",)), RunConfig("1000", start=DAYS[1])):
            with self.assertRaises(ValueError):
                run_backtest(snapshot(), source, cfg)
        with self.assertRaises(ValueError):
            build_strategy(snapshot(), config(universe=("UNKNOWN",)))

    def test_explicit_baseline_and_protected_risk_pairing(self):
        with self.assertRaisesRegex(ValueError, "scheduled-slots"):
            run(risk=RiskPolicy())
        with self.assertRaisesRegex(ValueError, "require risk"):
            run(config(profile="atr_protected"))

    def test_incomplete_actions_cannot_masquerade_as_total_return_signals(self):
        data = replace(snapshot(), metadata=replace(META, actions_complete=False))
        with self.assertRaisesRegex(ValueError, "complete corporate actions"):
            run(data=data)
        diagnostic=run(data=data, actions_policy="allow_incomplete_diagnostic")
        self.assertFalse(diagnostic.manifest.data.actions_complete)
        self.assertTrue(any('unqualified' in s for s in diagnostic.manifest.assumptions))


class StrategyRuleTests(unittest.TestCase):
    def test_momentum_buy_fills_next_open_with_independent_final_equity(self):
        result = run()
        self.assertEqual(len(result.fills), 1)
        fill = result.fills[0]
        self.assertEqual((fill.signal_date, fill.execution_date), (DAYS[2], DAYS[3]))
        self.assertEqual((fill.security_id, fill.quantity, fill.price), ("A", 4, 125))
        self.assertEqual(result.summary.final_equity, 1020)
        self.assertEqual(result.equity[-1].cash, 500)
        selected = [s for s in result.signal_decisions if s.selected][0]
        self.assertEqual(selected.score, D("0.2"))
        self.assertEqual(selected.target_fraction, D("0.50"))
        self.assertEqual(selected.rank, 1)

    def test_trend_uses_strict_above_mean_and_fixed_universe_slots(self):
        result = run(config("trend", invested_fraction="0.90"))
        selected = [s for s in result.signal_decisions if s.selected]
        self.assertEqual([s.security_id for s in selected], ["A"])
        self.assertEqual(selected[0].target_fraction, D("0.45"))
        self.assertEqual(result.fills[0].quantity, 3)
        flat = run(config("trend"), snapshot({"A": (100,) * 6, "B": (100,) * 6}))
        self.assertFalse(flat.fills)
        self.assertTrue(all(s.eligible and not s.qualifies for s in flat.signal_decisions))

    def test_momentum_retains_negative_winners_without_hidden_absolute_gate(self):
        data = snapshot({"A": (100, 95, 90, 90, 90, 90), "B": (100, 90, 80, 80, 80, 80)})
        result = run(data=data)
        selected = [s for s in result.signal_decisions if s.selected][0]
        self.assertEqual(selected.security_id, "A")
        self.assertEqual(selected.score, D("-0.1"))
        self.assertEqual(len(result.fills), 1)

    def test_skipped_latest_return_is_excluded_from_rank(self):
        data = snapshot({"A": (100, 120, 50, 50, 50, 50), "B": (100, 110, 200, 200, 200, 200)})
        result = run(config(momentum_skip=1), data)
        self.assertEqual([s.security_id for s in result.signal_decisions if s.selected], ["A"])
        self.assertEqual(result.fills[0].quantity, 10)

    def test_nearness_uses_highest_signal_close_not_raw_intraday_high(self):
        data = snapshot({"A": (100, 120, 110, 110, 110, 110), "B": (100, 110, 108, 108, 108, 108)},
                        highs={"A": (10000,) * 6, "B": (10000,) * 6})
        result = run(config("nearness_high"), data)
        self.assertEqual([s.security_id for s in result.signal_decisions if s.selected], ["B"])
        self.assertEqual([s.score for s in result.signal_decisions if s.selected][0], D(108) / 110)

    def test_reversal_selects_lowest_return_among_above_mean_assets(self):
        data = snapshot({"A": (100, 110, 120, 150, 141, 141),
                         "B": (100, 110, 120, 140, 150, 150),
                         "C": (100, 110, 120, 140, 70, 70)})
        result = run(config("reversal", universe=("A", "B", "C")), data)
        records = [s for s in result.signal_decisions if s.session == DAYS[4]]
        self.assertEqual([s.security_id for s in records if s.selected], ["A"])
        self.assertEqual(next(s for s in records if s.security_id == "A").score, D("-0.06"))
        self.assertTrue(next(s for s in records if s.security_id == "C").eligible)
        self.assertFalse(next(s for s in records if s.security_id == "C").qualifies)
        self.assertEqual(result.fills[0].execution_date, DAYS[5])

    def test_top_k_slots_do_not_expand_when_candidates_are_few(self):
        result = run(config(top_k=5))
        self.assertEqual([s.target_fraction for s in result.signal_decisions], [D("0.10"), D("0.10")])
        self.assertLessEqual(result.equity[3].market_value, 300)

    def test_ties_are_broken_by_id_independently_of_input_order(self):
        data = snapshot({"B": (100, 110, 120, 125, 125, 125), "A": (100, 110, 120, 125, 125, 125)})
        first = run(config(universe=("B", "A")), data)
        second = run(config(universe=("A", "B")), replace(data, bars=tuple(reversed(data.bars))))
        self.assertEqual(first.result_hash, second.result_hash)
        self.assertEqual(first.fills[0].security_id, "A")

    def test_eligibility_filters_are_distinct_from_alpha_and_rank(self):
        result = run(config(min_price="100"))
        rejected = next(s for s in result.signal_decisions if s.security_id == "B")
        self.assertFalse(rejected.eligible or rejected.qualifies or rejected.selected)
        self.assertIn("price_filter", rejected.reason_codes)
        self.assertIsNone(rejected.score)
        self.assertIsNone(rejected.rank)

    def test_liquidity_limit_records_target_and_capped_request_separately(self):
        data = snapshot(volumes={"A": (100,) * 6, "B": (100,) * 6})
        result = run(config(max_volume_participation="0.01"), data)
        record = next(s for s in result.signal_decisions if s.selected)
        self.assertEqual(record.target_quantity, 4)
        self.assertEqual(record.requested_quantity, 1)
        self.assertIn("entry_participation_cap", record.reason_codes)
        self.assertEqual(result.fills[0].quantity, 1)

    def test_no_rebalance_is_invented_at_run_end(self):
        result = run(end=DAYS[1])
        self.assertFalse(result.signal_decisions or result.fills or result.orders)

    def test_insufficient_warmup_and_missing_history_are_audited(self):
        short = run(config(momentum_lookback=3))
        self.assertFalse(short.fills)
        self.assertTrue(all("insufficient_history" in s.reason_codes for s in short.signal_decisions))
        data = snapshot()
        data = replace(data, bars=tuple(b for b in data.bars if not (b.security_id == "A" and b.session == DAYS[1])))
        missing = run(data=data, data_policy="allow_missing_unheld_diagnostic")
        record = next(s for s in missing.signal_decisions if s.security_id == "A")
        self.assertFalse(record.eligible)
        self.assertTrue(any(code in record.reason_codes for code in ("insufficient_history", "missing_history_session")))

    def test_buy_hold_equal_weight_and_cash_are_portfolios_with_declared_trades(self):
        buy_hold = run(config("buy_hold", universe=("A",), invested_fraction="1"))
        # 10 shares sized at first close $100, actual next open $110: reject,
        # never silently resize or retry to make a full-investment benchmark look good.
        self.assertEqual(buy_hold.orders[0].reason_code, "insufficient_cash")
        self.assertFalse(buy_hold.fills)
        equal = run(config("equal_weight", invested_fraction="0.90"))
        self.assertEqual([(f.security_id, f.quantity) for f in equal.fills], [("A", 3), ("B", 5)])
        cash = run(config("cash"))
        self.assertEqual(cash.summary.final_equity, 1000)
        self.assertFalse(cash.orders or cash.fills)

    def test_benchmark_can_use_independent_id_and_common_start_with_warmup(self):
        data = snapshot({"A": (100, 110, 120, 120, 120, 120), "SPY": (20,) * 6})
        cfg = config("buy_hold", universe=("SPY",), invested_fraction="0.95")
        result = run(cfg, data, start=DAYS[2])
        self.assertEqual(result.fills[0].quantity, 47)
        self.assertEqual(result.fills[0].security_id, "SPY")
        self.assertEqual(result.fills[0].execution_date, DAYS[3])

    def test_full_budget_benchmark_sizes_entry_costs_before_rounding(self):
        result = run(config("buy_hold", universe=("A",), invested_fraction="1"),
                     snapshot({"A": (100,) * 6}), cash="10000", execution=ExecutionProfile("10"))
        self.assertEqual(result.fills[0].quantity, 99)
        self.assertEqual(result.equity[-1].cash, D("90.100"))
        self.assertEqual(result.summary.final_equity, D("9990.100"))


class StrategyIntegrationTests(unittest.TestCase):
    def test_unscheduled_evaluation_reuses_rules_without_trading_the_backtest(self):
        data = snapshot()
        source = build_strategy(data, config(), execution=ExecutionProfile("0"))
        observed = []
        class Probe:
            spec = SourceSpec("scanner_reuse_probe", "1", source.spec.artifact_hash)
            def orders(self, context):
                if context.as_of == DAYS[3]:
                    self_batch = source.orders(context)
                    projected = source.evaluate(context)
                    observed.append((self_batch, projected))
                return ()
        result = run_backtest(data, Probe(), RunConfig("1000", ExecutionProfile("0")))
        self.assertFalse(result.fills)
        self.assertFalse(observed[0][0].requests or observed[0][0].decisions)
        self.assertEqual([s.security_id for s in observed[0][1].decisions if s.selected], ["A"])
        self.assertEqual(observed[0][1].decisions[0].session, DAYS[3])

    def test_rank_rotation_sells_first_and_reuses_actual_shared_cash(self):
        calendar = []
        day = date(2024, 1, 29)
        while day <= date(2024, 3, 4):
            if day.weekday() < 5:
                calendar.append(day)
            day += timedelta(days=1)
        first = {DAYS[0]: 100, DAYS[1]: 110, DAYS[2]: 120}
        end = {date(2024, 2, 28): 110, date(2024, 2, 29): 100,
               date(2024, 3, 1): 100, date(2024, 3, 4): 100}
        a = tuple(first.get(d, end.get(d, 125)) for d in calendar)
        b = tuple(100 if d == DAYS[0] else 95 if d == DAYS[1] else 90 if d == DAYS[2]
                  else 45 if d == date(2024, 2, 28) else 50 if d in (date(2024, 2, 29), date(2024, 3, 1))
                  else 55 if d == date(2024, 3, 4) else 40 for d in calendar)
        result = run(config(invested_fraction="1"), snapshot({"A": a, "B": b}, tuple(calendar)))
        self.assertEqual([(f.security_id, f.side, f.quantity) for f in result.fills],
                         [("A", "buy", D(8)), ("A", "sell", D(8)), ("B", "buy", D(16))])
        self.assertEqual(result.fills[1].cash_after, 800)
        self.assertEqual(result.fills[2].cash_after, 0)
        self.assertEqual(result.summary.final_equity, 880)
        self.assertEqual(result.equity[-1].realized_pnl, -200)

    def test_retained_equal_weight_positions_are_trimmed_and_topped_up(self):
        calendar = []
        day = date(2024, 1, 29)
        while day <= date(2024, 3, 1):
            if day.weekday() < 5:
                calendar.append(day)
            day += timedelta(days=1)
        a = tuple(200 if d >= date(2024, 2, 2) else 100 for d in calendar)
        result = run(config("equal_weight", invested_fraction="0.90"),
                     snapshot({"A": a, "B": (100,) * len(calendar)}, tuple(calendar)))
        self.assertEqual([(f.security_id, f.side, f.quantity) for f in result.fills],
                         [("A", "buy", D(4)), ("B", "buy", D(4)),
                          ("A", "sell", D(1)), ("B", "buy", D(2))])
        self.assertEqual(result.summary.final_equity, 1400)
        self.assertEqual(result.equity[-1].cash, 200)

    def test_protected_selected_holdings_are_not_pyramided_at_next_rebalance(self):
        calendar = []
        day = date(2024, 1, 29)
        while day <= date(2024, 3, 1):
            if day.weekday() < 5:
                calendar.append(day)
            day += timedelta(days=1)
        a = tuple(100 + 2 * i for i in range(len(calendar)))
        risk = RiskPolicy(max_trade_risk="0.01", volume_lookback=1, max_volume_participation="1")
        result = run(config(profile="atr_protected"),
                     snapshot({"A": a, "B": (100,) * len(calendar)}, tuple(calendar)), cash="10000", risk=risk)
        self.assertEqual(len(result.fills), 1)
        record = next(s for s in result.signal_decisions if s.session == date(2024, 2, 29) and s.security_id == "A")
        self.assertEqual(record.action, "hold")
        self.assertIsNone(record.target_quantity)
        self.assertIsNone(record.target_fraction)

    def test_protected_alpha_is_allowed_to_fail_the_portfolio_risk_gate(self):
        risk = RiskPolicy(max_trade_risk="0.001", volume_lookback=1, max_volume_participation="1")
        result = run(config(profile="atr_protected", risk_fraction="0.10"), risk=risk)
        self.assertTrue(any(s.selected and s.action == "entry_intent" for s in result.signal_decisions))
        self.assertFalse(result.fills)
        self.assertIn("trade_risk", next(r for r in result.risk_decisions if r.phase == "close").reason_codes)

    def test_protected_entries_fill_and_stop_on_adverse_future_gap(self):
        data = snapshot({"A": (100, 110, 120, 120, 90, 90), "B": (100, 95, 90, 90, 90, 90)})
        risk = RiskPolicy(max_trade_risk="0.03", volume_lookback=1, max_volume_participation="1",
                          max_portfolio_heat="0.10", max_position_fraction="0.50")
        result = run(config(profile="atr_protected", risk_fraction="0.03"), data, risk=risk)
        self.assertEqual([f.side for f in result.fills], ["buy", "sell"])
        self.assertEqual(result.fills[0].quantity, 1)
        self.assertEqual(result.fills[1].execution_kind, "stop_gap")
        self.assertEqual(result.fills[1].price, 90)
        self.assertEqual(result.summary.final_equity, 970)

    def test_future_price_mutations_do_not_change_prior_signals_or_fills(self):
        first = run()
        data = snapshot({"A": (100, 110, 120, 125, 10, 10000), "B": (100, 95, 90, 90, 10000, 10)})
        second = run(data=data)
        self.assertEqual(first.signal_decisions, second.signal_decisions)
        self.assertEqual(first.fills, second.fills)
        self.assertEqual(first.equity[:4], second.equity[:4])

    def test_future_split_and_dividend_are_not_visible_before_effective_date(self):
        first = run()
        data = snapshot({"A": (100, 110, 120, 125, 64, 65), "B": (100, 95, 90, 90, 85, 80)},
                        actions=(Split("A", DAYS[4], 2), Dividend("A", DAYS[4], 1, DAYS[5])))
        second = run(data=data)
        self.assertEqual(first.signal_decisions, second.signal_decisions)
        self.assertEqual(first.fills[0], second.fills[0])
        self.assertEqual(second.equity[-1].positions[0].quantity, 8)
        self.assertEqual(second.equity[-1].dividend_income, 8)

    def test_reusing_source_and_changing_decimal_context_reproduces_results(self):
        data, cfg = snapshot(), config()
        source = build_strategy(data, cfg)
        settings = RunConfig("1000", ExecutionProfile("10"), cfg.universe)
        first = run_backtest(data, source, settings)
        with localcontext() as context:
            context.prec, context.rounding = 7, ROUND_DOWN
            second = run_backtest(data, source, settings)
        self.assertEqual(first.result_hash, second.result_hash)

    def test_signal_batch_rejects_future_or_duplicate_decisions(self):
        record = SignalDecision(DAYS[-1], "A", "bad_source", True, True, True, "1", 1,
                                "0.10", "0", "1", "hold", "0", ("test",))
        class BadSource:
            spec = SourceSpec("bad_source", "1", "a" * 64)
            def orders(self, context):
                return OrderBatch((), (record,))
        with self.assertRaisesRegex(ValueError, "signal session"):
            run_backtest(snapshot(), BadSource(), RunConfig())

    def test_signal_contract_rejects_false_selection_float_score_and_duplicate_features(self):
        record = SignalDecision(DAYS[0], "A", "source", True, True, True, "1", 1,
                                "0.10", "0", "1", "hold", "0", ("test",))
        for change in ({"eligible": False}, {"qualifies": False}, {"score": 1.0},
                       {"rank": True}, {"features": (("price", "1"), ("price", "2"))},
                       {"reason_codes": ()}, {"target_fraction": "1.1"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(record, **change)


class StrategyPersistenceTests(unittest.TestCase):
    def test_versioned_synthetic_strategy_fixture_matches_independent_values(self):
        root = Path(__file__).parent / "fixtures" / "strategies"
        data = CsvSource(root / "bars.csv", root / "calendar.csv", root / "securities.csv", META,
                         root / "actions.csv").load()
        result = run(load_config(root / "momentum.json"), data)
        expected = json.loads((root / "expected.json").read_text())
        self.assertEqual(result.summary.initial_cash, D(expected["initial_cash"]))
        fill = result.fills[0]
        self.assertEqual(fill.signal_date.isoformat(), expected["signal_session"])
        self.assertEqual(fill.execution_date.isoformat(), expected["execution_session"])
        self.assertEqual(fill.security_id, expected["selected_security"])
        self.assertEqual(fill.quantity, D(expected["quantity"]))
        self.assertEqual(fill.price, D(expected["execution_price"]))
        self.assertEqual(next(s for s in result.signal_decisions if s.selected).score, D(expected["selected_score"]))
        self.assertEqual(result.equity[-1].cash, D(expected["final_cash"]))
        self.assertEqual(result.summary.final_equity, D(expected["final_equity"]))

    def test_signals_and_full_recipe_spec_are_persisted_with_integrity_hashes(self):
        with TemporaryDirectory() as temporary:
            result = run()
            directory = Path(temporary) / "run"
            save_run(result, directory)
            self.assertEqual(verify_run(directory), primitive(result))
            marker = json.loads((directory / "COMPLETE.json").read_text())
            self.assertEqual(marker["schema_version"], 3)
            self.assertIn("signals.csv", marker["files"])
            self.assertEqual(verify_run(directory)["manifest"]["source"]["configuration"]["family"], "momentum")
            (directory / "signals.csv").write_text("altered\n")
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                verify_run(directory)

    def test_v2_saved_risk_bundle_remains_readable(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "run"
            save_run(run(), directory)
            payload = primitive(run())
            payload.pop("signal_decisions")
            payload["manifest"]["schema_version"] = 2
            digest = content_hash(payload)
            (directory / "run.json").write_text(canonical_json({"schema_version": 2, "result_hash": digest, "result": payload}))
            (directory / "manifest.json").write_text(canonical_json(payload["manifest"]))
            (directory / "COMPLETE.json").write_text(canonical_json({"schema_version": 2, "result_hash": digest,
                "files": {name: sha256((directory / name).read_bytes()).hexdigest() for name in SCHEMA_FILES[2]}}))
            self.assertEqual(verify_run(directory), payload)

    def test_registry_is_complete_deterministic_and_refuses_overwrite(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "recipes"
            save_recipe_registry(("B", "A"), "SPY", root)
            registry = json.loads((root / "REGISTRY.json").read_text())
            self.assertEqual(len(registry["recipes"]), 14)
            self.assertEqual(registry["registry_hash"], content_hash(registry["recipes"]))
            for entry in registry["recipes"]:
                self.assertEqual(content_hash(load_config(root / entry["file"])), entry["configuration_hash"])
            with self.assertRaises(FileExistsError):
                save_recipe_registry(("A", "B"), "SPY", root)
            with redirect_stdout(StringIO()):
                self.assertEqual(registry_main(["--universe", "A", "B", "--benchmark", "SPY", "--output", str(root.parent / "other")]), 0)

    def test_cli_loads_and_runs_strategy_configuration(self):
        with TemporaryDirectory() as temporary, redirect_stdout(StringIO()):
            root = Path(temporary)
            save_snapshot(snapshot(), root / "data.json")
            (root / "strategy.json").write_text(canonical_json({"schema_version": 1, "configuration": config()}))
            self.assertEqual(main(["run", str(root / "data.json"), "--strategy", str(root / "strategy.json"),
                                   "--capital", "1000", "--slippage-bps", "0", "--output", str(root / "run")]), 0)
            self.assertEqual(verify_run(root / "run")["summary"]["final_equity"], "1020")
            self.assertEqual(main(["verify", str(root / "run")]), 0)

    def test_unknown_config_fields_and_bad_schemas_reject(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "strategy.json"
            for payload in ({"schema_version": True, "configuration": {}},
                            {"schema_version": 1, "configuration": {"optimizer": "best_sharpe"}}):
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    load_config(path)


if __name__ == "__main__":
    unittest.main()
