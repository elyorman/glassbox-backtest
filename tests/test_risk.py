"""Independent sizing calculations and portfolio/execution risk regressions."""

from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_UP, localcontext
from io import StringIO
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.backtest.cli import main
from quant_core.backtest.sources import load_schedule
from quant_core.data import Bar, CashDelisting, DataMetadata, Dividend, Security, Snapshot, Split
from quant_core.data.storage import save_snapshot
from quant_core.data.csv_source import CsvSource
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.provenance import canonical_json, content_hash, primitive
from quant_core.reporting import LEGACY_FILES, save_run, verify_run
from quant_core.risk import RiskPolicy, load_policy
from quant_core.sizing import EntryIntent, normalized_history, size_entry, wilder_atr

D = Decimal
DAYS = tuple(date(2024, 1, 2) + timedelta(days=i) for i in range(6))
META = DataMetadata("synthetic_risk", datetime(2024, 2, 1, tzinfo=timezone.utc),
                    "fixed_engineering_universe", True, "synthetic_explicit_sessions")


def bar(day, asset="A", price="100", low=None, high=None, close=None, volume="10000"):
    p = D(price)
    c = p if close is None else D(close)
    return Bar(asset, day, p, max(p, c) if high is None else high,
               min(p, c) if low is None else low, c, volume)


def data(bars=None, assets=("A",), actions=(), sessions=DAYS):
    bars = tuple(bar(d, a) for d in sessions for a in assets) if bars is None else tuple(bars)
    return Snapshot(tuple(sessions), bars, META,
                    tuple(Security(a, a, "SYNTHETIC") for a in assets), tuple(actions))


def policy(**kwargs):
    options = dict(max_trade_risk="1", max_position_fraction="1", max_gross_fraction="1",
                   cash_reserve_fraction="0", max_portfolio_heat="1", max_positions=10,
                   volume_lookback=1, max_volume_participation="1", drawdown_reduce="0.50",
                   drawdown_halt="1")
    options.update(kwargs)
    return RiskPolicy(**options)


def intent(day=DAYS[0], asset="A", method="fixed_fractional", **kwargs):
    options = {"stop_price": "90"} if method != "atr" else {}
    options.update(kwargs)
    return ScheduledOrder(day, EntryIntent(asset, method, **options))


def raw(day=DAYS[0], asset="A", side="buy", quantity="1", stop="90"):
    return ScheduledOrder(day, OrderRequest(asset, side, quantity, stop_price=stop if side == "buy" else None))


def run(entries=(), snapshot=None, risk=None, cash="10000", execution=None, **kwargs):
    return run_backtest(snapshot or data(), OrderSchedule(tuple(entries)),
                        RunConfig(cash, execution or ExecutionProfile("0"),
                                  risk=policy() if risk is None else risk, **kwargs))


def decisions(result, phase="close", asset="A"):
    return [r for r in result.risk_decisions if r.phase == phase and r.security_id == asset]


class RiskContractTests(unittest.TestCase):
    def test_policy_rejects_invalid_numeric_and_group_inputs(self):
        for change in ({"max_trade_risk": "0"}, {"max_gross_fraction": "1.1"},
                       {"cash_reserve_fraction": "1"}, {"max_positions": True},
                       {"volume_lookback": 0}, {"max_trade_risk": 0.01},
                       {"drawdown_reduce": "0.20", "drawdown_halt": "0.10"},
                       {"min_average_dollar_volume": "-1"}, {"reduced_budget_scale": "NaN"},
                       {"max_group_fraction": "0"}, {"security_groups": (("A", "X"), ("A", "Y"))},
                       {"security_groups": (("A",),)}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                RiskPolicy(**change)

    def test_intents_reject_unsupported_or_ambiguous_inputs(self):
        for change in ({"method": "kelly"}, {"method": "fixed_fractional"},
                       {"method": "fixed_allocation", "stop_price": "0"},
                       {"stop_price": "90"}, {"atr_period": True}, {"atr_multiple": "0"},
                       {"risk_fraction": "-1"}, {"allocation": "1.1"}, {"priority": False}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                EntryIntent("A", **change)

    def test_immutable_policy_and_intents_copy_mutable_group_input(self):
        groups = [["B", "Y"], ["A", "X"]]
        config = RiskPolicy(security_groups=groups)
        groups[0][1] = "OTHER"
        self.assertEqual(config.security_groups, (("A", "X"), ("B", "Y")))
        with self.assertRaises(FrozenInstanceError):
            config.max_trade_risk = D("1")
        with self.assertRaises(FrozenInstanceError):
            EntryIntent("A").atr_period = 1

    def test_entry_intents_cannot_run_without_risk(self):
        with self.assertRaisesRegex(ValueError, "enabled risk"):
            run_backtest(data(), OrderSchedule((intent(),)), RunConfig("10000"))

    def test_stops_require_positive_buy_only_values(self):
        for side, stop in (("sell", "90"), ("buy", "0"), ("buy", "-1")):
            with self.subTest(side=side, stop=stop), self.assertRaises(ValueError):
                OrderRequest("A", side, "1", stop_price=stop)


class SizingTests(unittest.TestCase):
    def test_fractional_and_allocation_hand_calculation(self):
        fractional = run((intent(risk_fraction="0.01"),))
        allocation = run((intent(method="fixed_allocation", allocation="0.20"),))
        self.assertEqual(fractional.fills[0].quantity, 10)
        self.assertEqual(decisions(fractional)[0].planned_loss, 100)
        self.assertEqual(allocation.fills[0].quantity, 20)
        self.assertEqual(allocation.equity[1].cash, 8000)

    def test_round_trip_costs_and_flat_commissions_in_loss_budget(self):
        # Buy 101, entry percentage cost 1.01/share. Stop sale 89.1,
        # exit percentage cost .891/share. Loss 13.801/share + $4 flat.
        result = run((intent(risk_fraction="0.01"),), execution=ExecutionProfile("100", "100", "2"))
        self.assertEqual(result.fills[0].quantity, 6)
        self.assertEqual(decisions(result)[0].planned_loss, D("86.806"))
        self.assertEqual(result.equity[1].cash, D("9385.94"))
        self.assertEqual(result.equity[1].equity, D("9985.94"))

    def test_allocation_debit_includes_costs(self):
        entry = EntryIntent("A", "fixed_allocation", allocation="0.20", stop_price="90")
        quantity = size_entry(entry, D("10000"), D("100"), D("90"), ExecutionProfile("100", "100", "2"))
        # $2,000 allocation, $2 flat; $102.01/share debit -> 19 whole shares.
        self.assertEqual(quantity, 19)

    def test_wilder_seed_recursion_and_atr_stop(self):
        bars = (bar(DAYS[0], high="101", low="99"),
                bar(DAYS[1], high="103", low="99", close="102"),
                bar(DAYS[2], price="102", high="103", low="100", close="101"),
                bar(DAYS[3], price="101", high="105", low="100", close="104"),
                bar(DAYS[4], price="104"), bar(DAYS[5], price="104"))
        self.assertEqual(wilder_atr(bars[:4], 2), D("4.25"))
        result = run((intent(DAYS[3], method="atr", atr_period=2, risk_fraction="0.01"),), data(bars))
        self.assertEqual(decisions(result)[0].stop_price, D("95.50"))
        self.assertEqual(result.fills[0].quantity, 11)

    def test_insufficient_or_zero_atr_rejects(self):
        short = run((intent(method="atr", atr_period=2),))
        flat = run((intent(DAYS[2], method="atr", atr_period=2),))
        self.assertIn("insufficient_atr_history", decisions(short)[0].reason_codes)
        self.assertIn("zero_atr", decisions(flat)[0].reason_codes)
        self.assertFalse(short.fills or flat.fills)

    def test_split_normalization_preserves_dollar_volume_and_ranges(self):
        bars = (bar(DAYS[0], high="102", low="98", volume="1000"),
                bar(DAYS[1], price="50", high="51", low="49", volume="2000"))
        normalized = normalized_history(bars, (Split("A", DAYS[1], "2"),))
        self.assertEqual(normalized[0].close, 50)
        self.assertEqual(normalized[0].volume, 2000)
        self.assertEqual(wilder_atr(normalized, 1), 2)
        self.assertEqual(normalized[0].close * normalized[0].volume, 100000)

    def test_future_split_does_not_change_past_features(self):
        original = tuple(bar(d, high="101", low="99") for d in DAYS)
        future = original[:4] + tuple(bar(d, price="50", high="50.5", low="49.5") for d in DAYS[4:])
        first = run((intent(DAYS[2], method="atr", atr_period=2),), data(original))
        second = run((intent(DAYS[2], method="atr", atr_period=2),),
                     data(future, actions=(Split("A", DAYS[4], "2"),)))
        self.assertEqual(decisions(first)[0], decisions(second)[0])
        self.assertEqual(first.fills[0], second.fills[0])

    def test_missing_risk_history_rejected_even_diagnostic_mode(self):
        bars = tuple(bar(d) for d in DAYS if d != DAYS[1])
        result = run((intent(DAYS[2]),), data(bars), data_policy="allow_missing_unheld_diagnostic")
        self.assertIn("missing_risk_history", decisions(result)[0].reason_codes)

    def test_below_one_share_and_invalid_stop_are_not_silently_bought(self):
        small = run((intent(risk_fraction="0.00001"),))
        wrong = run((intent(stop_price="100"),))
        self.assertIn("below_one_share", decisions(small)[0].reason_codes)
        self.assertIn("invalid_stop_distance", decisions(wrong)[0].reason_codes)


class PortfolioAdmissionTests(unittest.TestCase):
    def test_trade_risk_and_position_cap_reduce_sized_entries(self):
        trade = run((intent(risk_fraction="0.05"),), risk=policy(max_trade_risk="0.01"))
        position = run((intent(method="fixed_allocation", allocation="1"),),
                       risk=policy(max_position_fraction="0.20"))
        self.assertEqual(trade.fills[0].quantity, 10)
        self.assertIn("trade_risk", decisions(trade)[0].reason_codes)
        self.assertEqual(position.fills[0].quantity, 20)
        self.assertEqual(decisions(position)[0].status, "capped")

    def test_shared_cash_reserved_between_candidates_without_future_sales(self):
        entries = (intent(asset="B", method="fixed_allocation", allocation="0.80"),
                   intent(asset="A", method="fixed_allocation", allocation="0.80"))
        result = run(entries, data(assets=("A", "B")))
        self.assertEqual([(f.security_id, f.quantity) for f in result.fills], [("A", 80), ("B", 20)])
        self.assertEqual(result.equity[1].cash, 0)

    def test_pending_sale_proceeds_not_reserved_at_close(self):
        result = run((intent(method="fixed_allocation", allocation="1"),
                      raw(DAYS[1], side="sell", quantity="100"),
                      intent(DAYS[1], asset="B", method="fixed_allocation", allocation="0.50")),
                     data(assets=("A", "B")))
        self.assertEqual([f.side for f in result.fills], ["buy", "sell"])
        self.assertIn("insufficient_cash", decisions(result, asset="B")[0].reason_codes)

    def test_position_count_and_pyramiding_reject(self):
        result = run((intent(), intent(asset="B"), intent(DAYS[1])), data(assets=("A", "B")),
                     risk=policy(max_positions=1))
        self.assertIn("max_positions", decisions(result, asset="B")[0].reason_codes)
        self.assertIn("pyramiding_unsupported", decisions(result)[1].reason_codes)
        self.assertEqual(len(result.fills), 1)

    def test_reserve_and_exposure_caps_apply_to_post_cost_equity(self):
        result = run((intent(method="fixed_allocation", allocation="1"),),
                     risk=policy(cash_reserve_fraction="0.20", max_gross_fraction="0.70"))
        self.assertEqual(result.fills[0].quantity, 70)
        self.assertIn("gross_exposure", decisions(result)[0].reason_codes)
        self.assertGreaterEqual(result.equity[1].cash, D("0.20") * result.equity[1].equity)

    def test_cost_aware_caps_do_not_round_up_into_a_breach(self):
        result = run((intent(method="fixed_allocation", allocation="1"),),
                     risk=policy(max_position_fraction="0.20", cash_reserve_fraction="0.80"),
                     execution=ExecutionProfile("100", "100", "2"))
        self.assertEqual(result.fills[0].quantity, 19)
        state = result.equity[1]
        self.assertLessEqual(state.market_value, state.equity * D("0.20"))
        self.assertGreaterEqual(state.cash, state.equity * D("0.80"))

    def test_portfolio_heat_accounts_for_existing_and_reserved_positions(self):
        result = run((intent(risk_fraction="0.02"), intent(asset="B", risk_fraction="0.02")),
                     data(assets=("A", "B")), risk=policy(max_portfolio_heat="0.03"))
        self.assertEqual([f.quantity for f in result.fills], [20, 10])
        self.assertIn("portfolio_heat", decisions(result, asset="B")[0].reason_codes)

    def test_group_cap_combines_positions_and_missing_groups_fail_closed(self):
        entries = (intent(method="fixed_allocation", allocation="0.20"),
                   intent(asset="B", method="fixed_allocation", allocation="0.20"))
        result = run(entries, data(assets=("A", "B")),
                     risk=policy(max_group_fraction="0.30", security_groups=(("A", "X"), ("B", "X"))))
        self.assertEqual([f.quantity for f in result.fills], [20, 10])
        self.assertIn("group_exposure", decisions(result, asset="B")[0].reason_codes)
        missing = run((intent(),), risk=policy(max_group_fraction="0.30"))
        self.assertIn("missing_group", decisions(missing)[0].reason_codes)

    def test_adv_limits_use_past_share_units_not_execution_day_volume(self):
        bars = tuple(bar(d, volume="1000" if d == DAYS[0] else "10000000") for d in DAYS)
        result = run((intent(method="fixed_allocation", allocation="1"),), data(bars),
                     risk=policy(max_volume_participation="0.01"))
        self.assertEqual(result.fills[0].quantity, 10)
        self.assertEqual(decisions(result, "open")[0].average_volume, 1000)

    def test_dollar_liquidity_and_warmup_rejections(self):
        illiquid = run((intent(),), risk=policy(min_average_dollar_volume="1000001"))
        warmup = run((intent(),), risk=policy(volume_lookback=2))
        self.assertIn("insufficient_liquidity", decisions(illiquid)[0].reason_codes)
        self.assertIn("insufficient_liquidity_history", decisions(warmup)[0].reason_codes)

    def test_raw_buys_cannot_bypass_limits_or_omit_stop(self):
        missing = run((raw(stop=None),))
        excessive = run((raw(quantity="50"),), risk=policy(max_position_fraction="0.20"))
        self.assertEqual(missing.orders[0].status, "rejected")
        self.assertIn("missing_protective_stop", missing.orders[0].reason_code)
        self.assertIn("position_cap", excessive.orders[0].reason_code)
        self.assertFalse(missing.fills or excessive.fills)

    def test_adverse_entry_gap_rechecks_trade_risk_without_resizing(self):
        bars = (bar(DAYS[0]),) + tuple(bar(d, price="120") for d in DAYS[1:])
        result = run((intent(risk_fraction="0.01"),), data(bars), risk=policy(max_trade_risk="0.01"))
        self.assertEqual(decisions(result)[0].approved_quantity, 10)
        self.assertIn("trade_risk", decisions(result, "open")[0].reason_codes)
        self.assertFalse(result.fills)

    def test_entry_gap_below_stop_rejects(self):
        bars = (bar(DAYS[0]),) + tuple(bar(d, price="80") for d in DAYS[1:])
        result = run((intent(),), data(bars))
        self.assertEqual(result.orders[0].reason_code, "entry_open_below_stop")
        self.assertFalse(result.fills)

    def test_open_exposure_checks_use_other_holdings_opens(self):
        bars = tuple(bar(d, a, price="200" if a == "A" and d >= DAYS[2] else "100")
                     for d in DAYS for a in ("A", "B"))
        result = run((intent(method="fixed_allocation", allocation="0.50"),
                      intent(DAYS[1], asset="B", method="fixed_allocation", allocation="0.10")),
                     data(bars, assets=("A", "B")), risk=policy(max_gross_fraction="0.60"))
        self.assertIn("gross_exposure", decisions(result, "open", "B")[0].reason_codes)
        self.assertEqual(len(result.fills), 1)

    def test_future_low_does_not_change_entry_plan_or_open_approval(self):
        first = run((intent(),))
        bars = tuple(bar(d, low="85" if d == DAYS[1] else None) for d in DAYS)
        second = run((intent(),), data(bars))
        self.assertEqual(decisions(first)[0], decisions(second)[0])
        self.assertEqual(decisions(first, "open")[0], decisions(second, "open")[0])
        self.assertEqual(first.fills[0], second.fills[0])
        self.assertEqual(second.fills[1].execution_kind, "stop_intraday")

    def test_candidate_ordering_is_stable_and_priority_is_respected(self):
        entries = (intent(asset="B", method="fixed_allocation", allocation="1", priority=-1),
                   intent(asset="A", method="fixed_allocation", allocation="1"))
        first = run(entries, data(assets=("A", "B")))
        second = run(tuple(reversed(entries)), data(assets=("A", "B")))
        self.assertEqual(first.result_hash, second.result_hash)
        self.assertEqual(first.fills[0].security_id, "B")

    def test_price_drift_is_reported_without_promising_an_immediate_cap(self):
        bars = tuple(bar(d, price="200" if d >= DAYS[2] else "100") for d in DAYS)
        result = run((intent(method="fixed_allocation", allocation="0.20"),), data(bars),
                     risk=policy(max_position_fraction="0.20"))
        record = [r for r in result.risk_decisions if r.phase == "portfolio" and r.session == DAYS[2]][0]
        self.assertIn("position_weight_drift", record.reason_codes)
        self.assertEqual(record.gross_fraction, D(4000) / 12000)
        self.assertEqual(record.cash_fraction, D(8000) / 12000)
        self.assertEqual(record.heat_fraction, D(2200) / 12000)
        self.assertEqual(len(result.fills), 1)

    def test_zero_volume_execution_has_linked_risk_rejection(self):
        bars = tuple(bar(d, volume="0" if d == DAYS[1] else "10000") for d in DAYS)
        result = run((intent(),), data(bars))
        record = decisions(result, "open")[0]
        self.assertEqual(record.order_id, result.orders[0].order_id)
        self.assertEqual(record.reason_codes, ("zero_volume",))
        self.assertIsNone(record.planned_loss)
        self.assertEqual(record.method, "fixed_fractional")

    def test_prior_warmup_is_available_when_run_starts_later(self):
        bars = tuple(bar(d, high="102", low="98") for d in DAYS)
        result = run((intent(DAYS[2], method="atr", atr_period=2),), data(bars),
                     risk=policy(volume_lookback=3), start=DAYS[2])
        self.assertEqual(decisions(result)[0].atr, 4)
        self.assertEqual(result.fills[0].execution_date, DAYS[3])


class StopsAndDrawdownTests(unittest.TestCase):
    def test_overnight_stop_gap_can_exceed_planned_loss(self):
        bars = tuple(bar(d, price="50" if d >= DAYS[2] else "100") for d in DAYS)
        result = run((intent(risk_fraction="0.01"),), data(bars))
        self.assertEqual(decisions(result)[0].planned_loss, 100)
        self.assertEqual(result.fills[1].price, 50)
        self.assertEqual(result.fills[1].realized_pnl, -500)
        self.assertEqual(result.fills[1].execution_kind, "stop_gap")
        self.assertEqual(result.fills[1].trigger_price, 90)

    def test_intraday_stop_is_active_on_entry_day_with_costs(self):
        bars = tuple(bar(d, low="85" if d == DAYS[1] else None) for d in DAYS)
        result = run((intent(risk_fraction="0.01"),), data(bars), execution=ExecutionProfile("10"))
        self.assertEqual(result.fills[1].price, D("89.910"))
        self.assertEqual(result.fills[1].raw_open, 100)
        self.assertEqual(result.fills[1].raw_execution_price, 90)
        self.assertEqual(result.fills[1].execution_kind, "stop_intraday")
        self.assertFalse(result.equity[1].positions)

    def test_partial_sale_preserves_protection_for_remaining_shares(self):
        bars = tuple(bar(d, low="85" if d == DAYS[2] else None) for d in DAYS)
        result = run((raw(quantity="10"), raw(DAYS[1], side="sell", quantity="4")), data(bars))
        self.assertEqual([f.quantity for f in result.fills], [10, 4, 6])
        self.assertEqual(result.fills[-1].execution_kind, "stop_intraday")

    def test_full_market_exit_cancels_stop(self):
        bars = tuple(bar(d, low="85" if d == DAYS[2] else None) for d in DAYS)
        result = run((raw(quantity="10"), raw(DAYS[1], side="sell", quantity="10")), data(bars))
        self.assertEqual([f.execution_kind for f in result.fills], ["market_open", "market_open"])

    def test_intraday_exit_does_not_fund_morning_buy(self):
        bars = tuple(bar(d, a, low="85" if a == "A" and d == DAYS[2] else None)
                     for d in DAYS for a in ("A", "B"))
        # Risk-disabled mode isolates execution cash chronology; B is not resized.
        entries = (raw(quantity="100"), raw(DAYS[1], asset="B", quantity="1"))
        result = run_backtest(data(bars, assets=("A", "B")), OrderSchedule(entries),
                              RunConfig("10000", ExecutionProfile("0")))
        self.assertEqual(result.orders[1].reason_code, "insufficient_cash")
        self.assertEqual([f.security_id for f in result.fills], ["A", "A"])

    def test_pending_split_adjusts_quantity_stop_and_volume(self):
        bars = tuple(bar(d, price="50" if d >= DAYS[1] else "100",
                         low="44" if d == DAYS[2] else None, volume="20000" if d >= DAYS[1] else "10000")
                     for d in DAYS)
        result = run((raw(quantity="2"),), data(bars, actions=(Split("A", DAYS[1], "2"),)))
        self.assertEqual(result.fills[0].quantity, 4)
        self.assertEqual(result.orders[0].request.stop_price, 90)
        self.assertEqual(result.orders[0].adjusted_stop_price, 45)
        self.assertEqual(decisions(result, "open")[0].average_volume, 20000)
        self.assertEqual(result.fills[1].price, 45)
        self.assertEqual(result.fills[1].realized_pnl, -20)

    def test_pending_atr_entry_scales_frozen_atr_on_split(self):
        bars = tuple(bar(d, price="50" if d >= DAYS[2] else "100",
                         high="51" if d >= DAYS[2] else "102",
                         low="49" if d >= DAYS[2] else "98",
                         volume="20000" if d >= DAYS[2] else "10000") for d in DAYS)
        result = run((intent(DAYS[1], method="atr", atr_period=1, risk_fraction="0.01"),),
                     data(bars, actions=(Split("A", DAYS[2], "2"),)))
        self.assertEqual(decisions(result)[0].atr, 4)
        self.assertEqual(decisions(result)[0].stop_price, 92)
        self.assertEqual(decisions(result, "open")[0].atr, 2)
        self.assertEqual(decisions(result, "open")[0].stop_price, 46)
        self.assertEqual(result.fills[0].quantity, 24)
        self.assertEqual(decisions(result, "open")[0].planned_loss, 96)

    def test_held_reverse_split_scales_stop_and_retains_fractions(self):
        bars = tuple(bar(d, price="300" if d >= DAYS[2] else "100",
                         low="260" if d == DAYS[3] else None) for d in DAYS)
        result = run((raw(quantity="2"),), data(bars, actions=(Split("A", DAYS[2], "0.3333333333333333333333333333"),)))
        self.assertAlmostEqual(result.fills[1].quantity, D("2") / 3, places=25)
        self.assertAlmostEqual(result.fills[1].trigger_price, D("270"), places=24)

    def test_dividend_stop_is_unadjusted_and_income_reconciles(self):
        bars = tuple(bar(d, price="89" if d >= DAYS[2] else "100") for d in DAYS)
        result = run((raw(quantity="1"),),
                     data(bars, actions=(Dividend("A", DAYS[2], "11", DAYS[3]),)))
        self.assertEqual(result.fills[-1].execution_kind, "stop_gap")
        self.assertEqual(result.equity[-1].dividend_income, 11)
        self.assertEqual(result.summary.final_equity, 10000)

    def test_cash_delisting_removes_stop_before_execution(self):
        bars = tuple(bar(d) for d in DAYS[:2])
        snapshot = Snapshot(DAYS, bars, META,
                            (Security("A", "A", "SYNTHETIC", delisted_on=DAYS[2]),),
                            (CashDelisting("A", DAYS[2], "20"),))
        result = run((raw(quantity="1"),), snapshot)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.summary.final_equity, 9920)

    def test_zero_volume_stop_cannot_fill_and_is_retried_next_session(self):
        bars = tuple(bar(d, price="80" if d >= DAYS[2] else "100",
                         volume="0" if d == DAYS[2] else "10000") for d in DAYS)
        result = run((raw(quantity="1"),), data(bars))
        self.assertEqual(result.orders[1].reason_code, "zero_volume")
        self.assertEqual(result.fills[1].execution_date, DAYS[3])
        self.assertEqual(len([o for o in result.orders if o.processed_date == DAYS[2]]), 1)

    def test_unaffordable_stop_fee_is_audited_and_protection_remains(self):
        bars = tuple(bar(d, price="0.1" if d == DAYS[2] else "10",
                         low="4" if d == DAYS[3] else None) for d in DAYS)
        result = run((raw(quantity="1", stop="5"),), data(bars), cash="12",
                     execution=ExecutionProfile("0", "0", "2"))
        self.assertEqual(result.orders[1].reason_code, "insufficient_cash_for_fees")
        self.assertEqual(result.equity[2].positions[0].quantity, 1)
        self.assertEqual(result.fills[1].execution_date, DAYS[3])
        self.assertEqual(result.summary.final_equity, 3)
        self.assertEqual(result.summary.fees, 4)

    def test_drawdown_halt_liquidates_next_open_and_never_reenters(self):
        bars = tuple(bar(d, price="50" if d >= DAYS[3] else "100",
                         low="70" if d == DAYS[2] else None,
                         close="75" if d == DAYS[2] else None) for d in DAYS)
        entries = (intent(method="fixed_allocation", allocation="0.90", stop_price="1"),
                   intent(DAYS[2]), intent(DAYS[4]))
        result = run(entries, data(bars), risk=policy(drawdown_reduce="0.10", drawdown_halt="0.20"))
        self.assertEqual(result.equity[2].drawdown, D("0.225"))
        self.assertEqual(result.fills[-1].execution_date, DAYS[3])
        self.assertEqual(result.orders[1].request.reason, "drawdown_halt_liquidation")
        self.assertEqual(result.summary.max_drawdown, D("0.45"))
        self.assertTrue(all(r.halted for r in result.risk_decisions if r.session >= DAYS[2]))
        self.assertIn("drawdown_halt", decisions(result)[1].reason_codes)
        self.assertIn("drawdown_halt", decisions(result)[2].reason_codes)

    def test_drawdown_control_runs_without_any_new_alpha(self):
        bars = tuple(bar(d, price="70" if d >= DAYS[2] else "100") for d in DAYS)
        result = run((intent(method="fixed_allocation", allocation="0.90", stop_price="1"),),
                     data(bars), risk=policy(drawdown_reduce="0.10", drawdown_halt="0.20"))
        self.assertEqual([f.side for f in result.fills], ["buy", "sell"])
        self.assertEqual(result.fills[-1].execution_date, DAYS[3])

    def test_drawdown_reduction_scales_new_budget_and_recovers_before_halt(self):
        bars = tuple(bar(d, a, price="75" if a == "A" and d == DAYS[2] else "100")
                     for d in DAYS for a in ("A", "B"))
        result = run((intent(method="fixed_allocation", allocation="0.50", stop_price="1"),
                      intent(DAYS[2], asset="B", risk_fraction="0.01")), data(bars, assets=("A", "B")),
                     risk=policy(drawdown_reduce="0.10", drawdown_halt="0.20", reduced_budget_scale="0.50"))
        # Equity 8,750; .5% budget / $10 distance -> 4 shares.
        self.assertEqual(result.fills[-1].quantity, 4)
        self.assertEqual(decisions(result, asset="B")[0].budget_scale, D("0.50"))
        portfolio = [r for r in result.risk_decisions if r.phase == "portfolio"]
        self.assertEqual(portfolio[3].budget_scale, 1)

    def test_final_session_halt_expires_exit_without_fake_liquidation(self):
        bars = tuple(bar(d, price="70" if d == DAYS[-1] else "100") for d in DAYS)
        result = run((intent(method="fixed_allocation", allocation="0.90", stop_price="1"),),
                     data(bars), risk=policy(drawdown_reduce="0.10", drawdown_halt="0.20"))
        self.assertEqual(result.orders[-1].status, "expired")
        self.assertEqual(len(result.fills), 1)
        self.assertTrue(result.equity[-1].positions)

    def test_same_inputs_reproduce_even_with_different_caller_decimal_context(self):
        entries = (intent(risk_fraction="0.01234"),)
        first = run(entries, execution=ExecutionProfile("7", "3", "0.2"))
        with localcontext() as ctx:
            ctx.prec, ctx.rounding = 7, ROUND_UP
            second = run(entries, execution=ExecutionProfile("7", "3", "0.2"))
        self.assertEqual(first.result_hash, second.result_hash)


class RiskPersistenceTests(unittest.TestCase):
    def test_versioned_gap_fixture_matches_independent_expected_numbers(self):
        root = Path(__file__).parent / "fixtures" / "risk"
        snapshot = CsvSource(root / "bars.csv", root / "calendar.csv", root / "securities.csv",
                             META, root / "actions.csv").load()
        result = run_backtest(snapshot, load_schedule(root / "orders.json"),
                              RunConfig("10000", ExecutionProfile("0"), risk=load_policy(root / "policy.json")))
        expected = json.loads((root / "expected.json").read_text())
        self.assertEqual(result.summary.initial_cash, D(expected["initial_cash"]))
        self.assertEqual(result.fills[0].quantity, D(expected["approved_quantity"]))
        entry = decisions(result, asset="SYNTH-RISK")[0]
        self.assertEqual(entry.planned_loss, D(expected["planned_loss"]))
        self.assertEqual(result.fills[1].trigger_price, D(expected["stop_trigger"]))
        self.assertEqual(result.fills[1].price, D(expected["stop_gap_fill"]))
        self.assertEqual(result.fills[1].realized_pnl, D(expected["realized_pnl"]))
        self.assertEqual(result.summary.final_equity, D(expected["final_equity"]))
        self.assertEqual(result.summary.max_drawdown, D(expected["maximum_close_drawdown"]))
        self.assertIn(expected["blocked_reentry_reason"], decisions(result, asset="SYNTH-RISK")[1].reason_codes)

    def test_legacy_v1_bundle_remains_readable_without_rewriting(self):
        # Reconstruct the old shape and completion marker, then verify unchanged bytes.
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "run"
            result = run(())
            save_run(result, directory)
            payload = primitive(result)
            payload.pop("risk_decisions")
            payload.pop("signal_decisions")
            payload["manifest"]["schema_version"] = 1
            payload["manifest"]["config"].pop("risk")
            digest = content_hash(payload)
            (directory / "run.json").write_text(canonical_json(
                {"schema_version": 1, "result_hash": digest, "result": payload}))
            (directory / "manifest.json").write_text(canonical_json(payload["manifest"]))
            (directory / "COMPLETE.json").write_text(canonical_json({"schema_version": 1,
                "result_hash": digest, "files": {name: sha256((directory / name).read_bytes()).hexdigest()
                                                 for name in LEGACY_FILES}}))
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            self.assertEqual(verify_run(directory), payload)
            self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})

    def test_risk_bundle_is_versioned_and_integrity_checked(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "run"
            result = run((intent(),))
            save_run(result, directory)
            self.assertEqual(verify_run(directory), primitive(result))
            marker = json.loads((directory / "COMPLETE.json").read_text())
            self.assertEqual(marker["schema_version"], 3)
            self.assertIn("risk.csv", marker["files"])
            (directory / "risk.csv").write_text("modified\n")
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                verify_run(directory)

    def test_cli_loads_policy_and_v2_intents_and_verifies_saved_run(self):
        with TemporaryDirectory() as temporary, redirect_stdout(StringIO()):
            root = Path(temporary)
            snapshot, orders, risk, output = [root / name for name in ("data.json", "orders.json", "risk.json", "run")]
            save_snapshot(data(), snapshot)
            orders.write_text(json.dumps({"schema_version": 2, "name": "risk_fixture", "version": "1",
                "orders": [{"kind": "entry", "signal_date": DAYS[0].isoformat(), "security_id": "A",
                            "method": "fixed_fractional", "stop_price": "90", "risk_fraction": "0.01"}]}))
            risk.write_text(json.dumps({"schema_version": 1, "policy": primitive(policy())}))
            self.assertEqual(load_policy(risk), policy())
            self.assertEqual(main(["run", str(snapshot), "--orders", str(orders), "--risk-policy", str(risk),
                                   "--capital", "10000", "--slippage-bps", "0", "--output", str(output)]), 0)
            self.assertEqual(verify_run(output)["fills"][0]["quantity"], "10")
            self.assertEqual(main(["verify", str(output)]), 0)

    def test_policy_unknown_fields_and_non_integer_schema_reject(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "risk.json"
            for payload in ({"schema_version": True, "policy": {}},
                            {"schema_version": 1, "policy": {"kelly": "1"}}):
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    load_policy(path)


if __name__ == "__main__":
    unittest.main()
