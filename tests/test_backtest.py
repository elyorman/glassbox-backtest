"""Financial conformance tests; expected numbers are independent of the engine."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
from fractions import Fraction
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import quant_core
from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, SourceSpec, run_backtest
from quant_core.backtest.cli import main
from quant_core.backtest.sources import load_schedule
from quant_core.data import Bar, CashDelisting, DataMetadata, Dividend, Security, Snapshot, Split
from quant_core.data.csv_source import CsvSource
from quant_core.data.storage import save_snapshot
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.provenance import code_hash, content_hash, primitive
from quant_core.reporting import save_run, verify_run

DAYS = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5))
META = DataMetadata("synthetic", datetime(2024, 1, 6, tzinfo=timezone.utc),
                    "fixed_synthetic_universe", True, "synthetic_explicit_sessions")
FIXTURES = Path(__file__).parent / "fixtures"


def bar(day, price="10", asset="A", close=None, volume="1000"):
    close = price if close is None else close
    p, c = Decimal(price), Decimal(close)
    return Bar(asset, day, p, max(p, c), min(p, c), c, volume)


def data(bars=None, sessions=DAYS, actions=(), securities=None, metadata=META):
    bars = tuple(bar(d) for d in sessions) if bars is None else tuple(bars)
    securities = (Security("A", "AAA", "SYNTHETIC"),) if securities is None else tuple(securities)
    return Snapshot(tuple(sessions), bars, metadata, securities, tuple(actions))


def order(day, side="buy", quantity="1", asset="A", priority=0, reason="test_input"):
    return ScheduledOrder(day, OrderRequest(asset, side, quantity, priority, reason))


def run(snapshot=None, entries=(), cash="100", profile=None, **options):
    return run_backtest(data() if snapshot is None else snapshot, OrderSchedule(tuple(entries)),
                        RunConfig(cash, profile or ExecutionProfile("0"), **options))


class ContractTests(unittest.TestCase):
    def test_bad_order_quantities_sides_priorities_and_reasons(self):
        for values in (("buy", "0", 0, "reason"), ("buy", "-1", 0, "reason"),
                       ("buy", "0.5", 0, "reason"), ("short", "1", 0, "reason"),
                       ("buy", "1", True, "reason"), ("buy", "1", 0, "")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                OrderRequest("A", *values)

    def test_execution_contract_rejects_invalid_costs_and_conventions(self):
        for change in ({"slippage_bps": "-1"}, {"slippage_bps": "10000"}, {"fee_bps": "10000"},
                       {"fee_per_order": "-1"}, {"convention": "same_close"}, {"cash_policy": "settled_cash"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                ExecutionProfile(**change)

    def test_config_rejects_invalid_capital_universe_dates_and_policies(self):
        for change in ({"initial_cash": "0"}, {"initial_cash": 0.1}, {"universe": ("A", "A")},
                       {"start": DAYS[2], "end": DAYS[0]}, {"data_policy": "fill_missing"},
                       {"actions_policy": "ignore"}, {"start": "2024-01-02"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                RunConfig(**change)

    def test_unknown_universe_and_off_calendar_period_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown security"):
            run(universe=("X",))
        with self.assertRaisesRegex(ValueError, "calendar"):
            run(start=date(2024, 1, 6))

    def test_off_calendar_schedule_is_rejected_instead_of_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "Scheduled signal date"):
            run(entries=(order(date(2024, 1, 6)),))

    def test_quote_rejects_unsupported_side_and_invalid_prices(self):
        for values in (("0", "1", "buy"), ("10", "0", "buy"), ("10", "1", "short")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ExecutionProfile().quote(*values)

    def test_no_orders_is_a_complete_flat_cash_run(self):
        result = run()
        self.assertEqual(result.summary.final_equity, Decimal(100))
        self.assertEqual(result.summary.total_return, Decimal(0))
        self.assertEqual(result.summary.max_drawdown, Decimal(0))
        self.assertFalse(result.orders)
        self.assertEqual(len(result.equity), 4)

    def test_incomplete_actions_require_diagnostic_opt_in(self):
        snapshot = data(metadata=replace(META, actions_complete=False))
        with self.assertRaisesRegex(ValueError, "completeness"):
            run(snapshot)
        result = run(snapshot, actions_policy="allow_incomplete_diagnostic")
        self.assertIn("actions_incomplete", [i.code for i in result.manifest.quality_issues])
        self.assertTrue(any("unqualified" in a for a in result.manifest.assumptions))

    def test_strict_data_policy_blocks_missing_expected_bars(self):
        snapshot = data((bar(DAYS[0]), bar(DAYS[2]), bar(DAYS[3])))
        with self.assertRaisesRegex(ValueError, "missing_bar"):
            run(snapshot)


class ExecutionTests(unittest.TestCase):
    def test_next_session_open_not_signal_close(self):
        snapshot = data((bar(DAYS[0], "10"), bar(DAYS[1], "12", close="13"),
                         bar(DAYS[2], "13"), bar(DAYS[3], "13")))
        result = run(snapshot, (order(DAYS[0], quantity="2"),))
        self.assertEqual(result.fills[0].signal_date, DAYS[0])
        self.assertEqual(result.fills[0].execution_date, DAYS[1])
        self.assertEqual(result.fills[0].price, Decimal(12))
        self.assertEqual(result.equity[1].equity, Decimal(102))

    def test_weekend_and_holiday_follow_explicit_session_calendar(self):
        sessions = (date(2024, 1, 12), date(2024, 1, 16))
        result = run(data(sessions=sessions), (order(sessions[0]),))
        self.assertEqual(result.fills[0].execution_date, date(2024, 1, 16))

    def test_gap_rejects_entire_buy_without_resizing(self):
        snapshot = data((bar(DAYS[0], "10"),) + tuple(bar(d, "11") for d in DAYS[1:]))
        result = run(snapshot, (order(DAYS[0], quantity="10"),))
        self.assertEqual(result.orders[0].reason_code, "insufficient_cash")
        self.assertEqual(result.orders[0].adjusted_quantity, Decimal(10))
        self.assertFalse(result.fills)
        self.assertEqual(result.equity[-1].cash, Decimal(100))

    def test_priority_controls_two_buys_competing_for_shared_cash(self):
        securities = (Security("A", "AAA", "X"), Security("B", "BBB", "X"))
        snapshot = data(tuple(bar(d, asset=a) for d in DAYS for a in ("A", "B")), securities=securities)
        result = run(snapshot, (order(DAYS[0], quantity="10", asset="A", priority=2),
                                order(DAYS[0], quantity="10", asset="B", priority=1)))
        self.assertEqual([f.security_id for f in result.fills], ["B"])
        self.assertEqual(result.orders[1].reason_code, "insufficient_cash")

    def test_equal_priority_ties_and_permuted_inputs_are_deterministic(self):
        securities = (Security("A", "AAA", "X"), Security("B", "BBB", "X"))
        snapshot = data(tuple(bar(d, asset=a) for d in DAYS for a in ("B", "A")), securities=securities)
        entries = (order(DAYS[0], quantity="10", asset="B"), order(DAYS[0], quantity="10", asset="A"))
        first = run(snapshot, entries)
        second = run(replace(snapshot, bars=tuple(reversed(snapshot.bars)), securities=tuple(reversed(securities))),
                     tuple(reversed(entries)))
        self.assertEqual(first, second)
        self.assertEqual([f.security_id for f in first.fills], ["A"])

    def test_sells_fund_buys_before_ranked_buy_processing(self):
        securities = (Security("A", "AAA", "X"), Security("B", "BBB", "X"))
        snapshot = data(tuple(bar(d, asset=a) for d in DAYS for a in ("A", "B")), securities=securities)
        result = run(snapshot, (order(DAYS[0], quantity="10"), order(DAYS[1], quantity="10", asset="B"),
                                order(DAYS[1], "sell", "10", priority=999)))
        self.assertEqual([(f.side, f.security_id) for f in result.fills], [("buy", "A"), ("sell", "A"), ("buy", "B")])
        self.assertEqual(result.equity[2].cash, Decimal(0))
        self.assertEqual(result.equity[2].positions[0].security_id, "B")

    def test_overselling_and_shorting_rejected(self):
        result = run(entries=(order(DAYS[0], "sell", "1"), order(DAYS[1], quantity="2"),
                              order(DAYS[2], "sell", "3")))
        self.assertEqual([o.reason_code for o in result.orders], ["insufficient_position", "filled", "insufficient_position"])
        self.assertEqual(result.equity[-1].positions[0].quantity, Decimal(2))

    def test_fees_and_adverse_slippage_have_hand_calculated_round_trip(self):
        # Buy: 2*10.1 + (20.2*1% + 1) = 21.402; cash 78.598.
        # Sell: 2*9.9 - (19.8*1% + 1) = 18.602; cash 97.200.
        result = run(entries=(order(DAYS[0], quantity="2"), order(DAYS[1], "sell", "2")),
                     profile=ExecutionProfile("100", "100", "1"))
        self.assertEqual(result.equity[1].cash, Decimal("78.598"))
        self.assertEqual(result.equity[-1].cash, Decimal("97.200"))
        self.assertEqual(result.fills[1].realized_pnl, Decimal("-2.800"))
        self.assertEqual(result.summary.fees, Decimal("2.400"))
        self.assertEqual(result.summary.slippage, Decimal("0.4"))

    def test_average_cost_basis_survives_partial_exits(self):
        snapshot = data((bar(DAYS[0], "10"), bar(DAYS[1], "10"), bar(DAYS[2], "20"), bar(DAYS[3], "30")))
        result = run(snapshot, (order(DAYS[0], quantity="2"), order(DAYS[1], quantity="2"),
                                order(DAYS[2], "sell", "1")))
        self.assertEqual(result.equity[-1].positions[0].basis, Decimal(45))
        self.assertEqual(result.equity[-1].positions[0].quantity, Decimal(3))
        self.assertEqual(result.fills[-1].realized_pnl, Decimal(15))
        self.assertEqual(result.equity[-1].unrealized_pnl, Decimal(45))
        self.assertEqual(result.summary.final_equity, Decimal(160))

    def test_missing_unheld_execution_bar_rejects_in_diagnostic_mode(self):
        snapshot = data((bar(DAYS[0]), bar(DAYS[2]), bar(DAYS[3])))
        result = run(snapshot, (order(DAYS[0]),), data_policy="allow_missing_unheld_diagnostic")
        self.assertEqual(result.orders[0].reason_code, "missing_execution_bar")
        self.assertFalse(result.fills)

    def test_missing_held_bar_invalidates_diagnostic_run(self):
        snapshot = data((bar(DAYS[0]), bar(DAYS[1]), bar(DAYS[3])))
        with self.assertRaisesRegex(ValueError, "Missing held-security"):
            run(snapshot, (order(DAYS[0]),), data_policy="allow_missing_unheld_diagnostic")

    def test_zero_volume_cannot_fill(self):
        snapshot = data(tuple(bar(d, volume="0" if d == DAYS[1] else "1000") for d in DAYS))
        result = run(snapshot, (order(DAYS[0]),))
        self.assertEqual(result.orders[0].reason_code, "zero_volume")

    def test_unknown_security_and_outside_universe_are_audited(self):
        securities = (Security("A", "AAA", "X"), Security("B", "BBB", "X"))
        snapshot = data(tuple(bar(d, asset=a) for d in DAYS for a in ("A", "B")), securities=securities)
        result = run(snapshot, (order(DAYS[0], asset="X"), order(DAYS[0], asset="B")), universe=("A",))
        self.assertEqual({o.reason_code for o in result.orders}, {"unknown_security", "outside_universe"})

    def test_final_orders_expire_and_open_holdings_remain_marked(self):
        result = run(entries=(order(DAYS[0], quantity="2"), order(DAYS[-1], "sell", "2")))
        self.assertEqual(result.orders[-1].status, "expired")
        self.assertEqual(result.orders[-1].reason_code, "no_next_session")
        self.assertEqual(result.equity[-1].positions[0].quantity, Decimal(2))
        self.assertEqual(len(result.fills), 1)

    def test_explicit_period_does_not_execute_outside_end(self):
        result = run(entries=(order(DAYS[1]), order(DAYS[2], "sell")), start=DAYS[1], end=DAYS[2])
        self.assertEqual([s.session for s in result.equity], [DAYS[1], DAYS[2]])
        self.assertEqual(result.orders[-1].status, "expired")
        self.assertEqual(result.manifest.config.start, DAYS[1])

    def test_sale_with_unaffordable_flat_fee_cannot_create_negative_cash(self):
        snapshot = data((bar(DAYS[0]), bar(DAYS[1]), bar(DAYS[2], "1"), bar(DAYS[3], "1")))
        result = run(snapshot, (order(DAYS[0]), order(DAYS[1], "sell")), profile=ExecutionProfile("0", "0", "50"))
        self.assertEqual(result.orders[-1].reason_code, "insufficient_cash_for_fees")
        self.assertEqual(result.equity[-1].cash, Decimal(40))
        self.assertEqual(result.summary.final_equity, Decimal(41))


class CorporateActionTests(unittest.TestCase):
    def test_split_adjusts_pending_buy_preserving_original_request(self):
        snapshot = data(tuple(bar(d, "10" if d == DAYS[0] else "5") for d in DAYS),
                        actions=(Split("A", DAYS[1], "2"),))
        result = run(snapshot, (order(DAYS[0], quantity="2"),))
        self.assertEqual(result.orders[0].request.quantity, Decimal(2))
        self.assertEqual(result.orders[0].adjusted_quantity, Decimal(4))
        self.assertEqual(result.fills[0].quantity, Decimal(4))
        self.assertEqual(result.summary.final_equity, Decimal(100))

    def test_split_adjusts_holdings_and_pending_sale_without_gain(self):
        snapshot = data(tuple(bar(d, "10" if d <= DAYS[1] else "5") for d in DAYS),
                        actions=(Split("A", DAYS[2], "2"),))
        result = run(snapshot, (order(DAYS[0], quantity="2"), order(DAYS[1], "sell", "1")))
        self.assertEqual(result.fills[-1].quantity, Decimal(2))
        self.assertEqual(result.fills[-1].realized_pnl, Decimal(0))
        self.assertEqual(result.equity[-1].positions[0].basis, Decimal(10))
        self.assertEqual(result.equity[-1].positions[0].quantity, Decimal(2))
        self.assertEqual(result.summary.final_equity, Decimal(100))

    def test_reverse_split_retains_fractional_share_without_cash_in_lieu(self):
        snapshot = data(tuple(bar(d, "10" if d <= DAYS[1] else "20") for d in DAYS),
                        actions=(Split("A", DAYS[2], "0.5"),))
        result = run(snapshot, (order(DAYS[0]),))
        self.assertEqual(result.equity[-1].positions[0].quantity, Decimal("0.5"))
        self.assertEqual(result.equity[-1].positions[0].basis, Decimal(10))
        self.assertEqual(result.summary.final_equity, Decimal(100))

    def test_dividend_accrual_and_payment_do_not_double_count_equity(self):
        snapshot = data(tuple(bar(d, "10" if d <= DAYS[1] else "9") for d in DAYS),
                        actions=(Dividend("A", DAYS[2], "1", DAYS[3]),))
        result = run(snapshot, (order(DAYS[0], quantity="2"),))
        self.assertEqual(result.equity[2].cash, Decimal(80))
        self.assertEqual(result.equity[2].receivables, Decimal(2))
        self.assertEqual(result.equity[3].cash, Decimal(82))
        self.assertEqual(result.equity[3].receivables, Decimal(0))
        self.assertEqual([s.equity for s in result.equity], [Decimal(100)] * 4)
        self.assertEqual(result.equity[-1].dividend_income, Decimal(2))

    def test_sale_on_ex_date_keeps_entitlement_until_payment(self):
        snapshot = data(tuple(bar(d, "10" if d <= DAYS[1] else "9") for d in DAYS),
                        actions=(Dividend("A", DAYS[2], "1", DAYS[3]),))
        result = run(snapshot, (order(DAYS[0], quantity="2"), order(DAYS[1], "sell", "2")))
        self.assertFalse(result.equity[2].positions)
        self.assertEqual(result.equity[2].cash, Decimal(98))
        self.assertEqual(result.equity[2].receivables, Decimal(2))
        self.assertEqual(result.equity[-1].cash, Decimal(100))

    def test_buy_on_ex_date_does_not_receive_dividend(self):
        snapshot = data(actions=(Dividend("A", DAYS[1], "1", DAYS[2]),))
        result = run(snapshot, (order(DAYS[0], quantity="2"),))
        self.assertEqual(result.equity[-1].dividend_income, Decimal(0))
        self.assertFalse(result.outstanding_receivables)

    def test_payment_becomes_spendable_before_that_sessions_pending_orders(self):
        snapshot = data(tuple(bar(d, "10" if d <= DAYS[1] else "9") for d in DAYS),
                        actions=(Dividend("A", DAYS[2], "1", DAYS[3]),))
        result = run(snapshot, (order(DAYS[0], quantity="10"), order(DAYS[2])), cash="100")
        self.assertEqual(result.orders[-1].status, "filled")
        self.assertEqual(result.equity[-1].cash, Decimal(1))
        self.assertEqual(result.equity[-1].positions[0].quantity, Decimal(11))

    def test_delisting_does_not_erase_an_earlier_dividend_receivable(self):
        sessions = (date(2023, 12, 29),) + DAYS
        snapshot = data((bar(sessions[0]), bar(DAYS[0]), bar(DAYS[1])), sessions=sessions,
                        actions=(Dividend("A", DAYS[1], "1", DAYS[3]), CashDelisting("A", DAYS[2], "0")),
                        securities=(Security("A", "AAA", "X", delisted_on=DAYS[2]),))
        result = run(snapshot, (order(sessions[0], quantity="10"),))
        self.assertEqual(result.equity[-1].cash, Decimal(10))
        self.assertEqual(result.equity[-1].dividend_income, Decimal(10))
        self.assertFalse(result.outstanding_receivables)
        self.assertFalse(result.equity[-1].positions)

    def test_same_day_split_dividend_uses_post_split_share_amount(self):
        snapshot = data(tuple(bar(d, "10" if d <= DAYS[1] else "4") for d in DAYS),
                        actions=(Dividend("A", DAYS[2], "1", DAYS[3]), Split("A", DAYS[2], "2")))
        result = run(snapshot, (order(DAYS[0], quantity="2"),))
        self.assertEqual(result.equity[2].positions[0].quantity, Decimal(4))
        self.assertEqual(result.equity[2].dividend_income, Decimal(4))
        self.assertEqual(result.summary.final_equity, Decimal(100))

    def test_receivable_survives_final_date_and_is_not_spendable(self):
        snapshot = data(tuple(bar(d, "10" if d <= DAYS[1] else "9") for d in DAYS),
                        actions=(Dividend("A", DAYS[2], "1", date(2024, 1, 10)),))
        result = run(snapshot, (order(DAYS[0], quantity="10"), order(DAYS[2])), cash="100")
        self.assertEqual(result.orders[-1].reason_code, "insufficient_cash")
        self.assertEqual(sum(r.amount for r in result.outstanding_receivables), Decimal(10))
        self.assertEqual(result.summary.final_equity, Decimal(100))

    def test_non_session_payment_is_credited_at_next_session(self):
        sessions = (date(2024, 1, 11), date(2024, 1, 12), date(2024, 1, 16), date(2024, 1, 17))
        # A payment after ex-date falling on a weekend is exercised on a longer calendar.
        sessions = sessions + (date(2024, 1, 22),)
        snapshot = data(sessions=sessions, actions=(Dividend("A", sessions[2], "1", date(2024, 1, 20)),))
        result = run(snapshot, (order(sessions[0]),))
        payments = [c for c in result.cash_movements if c.kind == "dividend_payment"]
        self.assertEqual(payments[0].session, date(2024, 1, 22))

    def test_cash_delisting_settles_position_and_pending_sale_is_rejected(self):
        snapshot = data((bar(DAYS[0]), bar(DAYS[1])),
                        actions=(CashDelisting("A", DAYS[2], "3"),),
                        securities=(Security("A", "AAA", "X", delisted_on=DAYS[2]),))
        result = run(snapshot, (order(DAYS[0], quantity="2"), order(DAYS[1], "sell", "2")))
        self.assertFalse(result.equity[-1].positions)
        self.assertEqual(result.summary.final_equity, Decimal(86))
        self.assertEqual(result.equity[-1].realized_pnl, Decimal(-14))
        self.assertEqual(result.orders[-1].reason_code, "outside_security_lifetime")

    def test_zero_settlement_is_explicit_writeoff_with_full_drawdown(self):
        snapshot = data((bar(DAYS[0]), bar(DAYS[1])), actions=(CashDelisting("A", DAYS[2], "0"),),
                        securities=(Security("A", "AAA", "X", delisted_on=DAYS[2]),))
        result = run(snapshot, (order(DAYS[0], quantity="10"),))
        self.assertEqual(result.summary.final_equity, Decimal(0))
        self.assertEqual(result.summary.total_return, Decimal(-1))
        self.assertEqual(result.summary.max_drawdown, Decimal(1))
        self.assertIsNone(result.equity[-1].session_return)

    def test_unresolved_held_delisting_invalidates_run(self):
        snapshot = data((bar(DAYS[0]), bar(DAYS[1])),
                        securities=(Security("A", "AAA", "X", delisted_on=DAYS[2]),))
        with self.assertRaisesRegex(ValueError, "Unresolved held delisting"):
            run(snapshot, (order(DAYS[0]),))


class CloseBasedSource:
    @property
    def spec(self):
        return SourceSpec("test_close_based", "1", content_hash("close_based_test_v1"))

    def orders(self, context):
        bars = context.history("A", 2)
        assert all(bar.session <= context.as_of for bar in bars)
        assert all(split.session <= context.as_of for split in context.splits)
        if len(bars) == 2 and bars[-1].close > bars[-2].close and not context.positions:
            return (OrderRequest("A", "buy", "1", reason="past_close_increase"),)
        return ()


class CausalityAndAccountingTests(unittest.TestCase):
    def test_future_splits_are_not_visible_to_earlier_callbacks(self):
        class SplitCheckingSource(CloseBasedSource):
            def __init__(self):
                self.observed = []

            def orders(self, context):
                self.observed.append((context.as_of, context.splits))
                return ()

        source = SplitCheckingSource()
        snapshot = data(actions=(Split("A", DAYS[2], "2"),))
        run_backtest(snapshot, source)
        self.assertFalse(source.observed[0][1])
        self.assertFalse(source.observed[1][1])
        self.assertEqual(source.observed[2][1], snapshot.actions)

    def test_source_cannot_mutate_public_history_or_position_values(self):
        class ReadOnlyCheckingSource(CloseBasedSource):
            def orders(self, context):
                with self_test.assertRaises(FrozenInstanceError):
                    context.as_of = DAYS[-1]
                with self_test.assertRaises(FrozenInstanceError):
                    context.history("A")[-1].close = Decimal(999)
                with self_test.assertRaises(ValueError):
                    context.history("outside_universe")
                if context.positions:
                    with self_test.assertRaises(FrozenInstanceError):
                        context.positions[0].quantity = Decimal(999)
                if len(context.history("A")) == 1:
                    return (OrderRequest("A", "buy", "1"),)
                return ()

        self_test = self
        result = run_backtest(data(), ReadOnlyCheckingSource())
        self.assertEqual(result.equity[-1].positions[0].quantity, Decimal(1))

    def test_source_metadata_changes_are_rejected(self):
        class ChangingSource(CloseBasedSource):
            changed = False

            @property
            def spec(self):
                return SourceSpec("changing", "1", content_hash(self.changed))

            def orders(self, context):
                self.changed = True
                return ()

        with self.assertRaisesRegex(ValueError, "metadata changed"):
            run_backtest(data(), ChangingSource())

    def test_invalid_source_return_is_an_explicit_contract_error(self):
        class InvalidSource(CloseBasedSource):
            def orders(self, context):
                return None

        with self.assertRaisesRegex(ValueError, "iterable"):
            run_backtest(data(), InvalidSource())

    def test_benchmark_security_can_run_independently_of_trading_universe(self):
        securities = (Security("A", "AAA", "X"), Security("B", "BBB", "X"))
        snapshot = data(tuple(bar(d, asset=a) for d in DAYS for a in ("A", "B")), securities=securities)
        main_result = run(snapshot, (order(DAYS[0], asset="A"),), universe=("A",))
        benchmark = run(snapshot, (order(DAYS[0], asset="B"),), universe=("B",))
        self.assertEqual(main_result.manifest.config.universe, ("A",))
        self.assertEqual(benchmark.manifest.config.universe, ("B",))
        self.assertEqual(benchmark.fills[0].security_id, "B")

    def test_future_prices_do_not_change_earlier_decisions_or_equity(self):
        snapshot = data(tuple(bar(d, str(10 + index)) for index, d in enumerate(DAYS)))
        changed = replace(snapshot, bars=tuple(bar(d, "1000" if d == DAYS[-1] else str(10 + i))
                                              for i, d in enumerate(DAYS)))
        first = run_backtest(snapshot, CloseBasedSource(), RunConfig("100", ExecutionProfile("0")))
        second = run_backtest(changed, CloseBasedSource(), RunConfig("100", ExecutionProfile("0")))
        self.assertEqual(first.equity[:3], second.equity[:3])
        self.assertEqual([o for o in first.orders if o.signal_date < DAYS[-1]],
                         [o for o in second.orders if o.signal_date < DAYS[-1]])

    def test_prefix_invariance_ignores_deliberate_end_expiration_difference(self):
        snapshot = data(tuple(bar(d, str(10 + index)) for index, d in enumerate(DAYS)))
        first = run_backtest(snapshot, CloseBasedSource(), RunConfig("100", ExecutionProfile("0")))
        prefix = replace(snapshot, sessions=DAYS[:2], bars=snapshot.bars[:2])
        second = run_backtest(prefix, CloseBasedSource(), RunConfig("100", ExecutionProfile("0")))
        self.assertEqual(first.equity[:2], second.equity)
        self.assertEqual([(o.signal_date, o.request) for o in first.orders if o.signal_date <= DAYS[1]],
                         [(o.signal_date, o.request) for o in second.orders])

    def test_warmup_history_is_available_without_pre_period_trades(self):
        snapshot = data(tuple(bar(d, str(10 + index)) for index, d in enumerate(DAYS)))
        result = run_backtest(snapshot, CloseBasedSource(), RunConfig("100", ExecutionProfile("0"), start=DAYS[1]))
        self.assertEqual(result.orders[0].signal_date, DAYS[1])
        self.assertEqual(result.fills[0].execution_date, DAYS[2])
        self.assertEqual(result.equity[0].cash, Decimal(100))

    def test_numeric_context_changes_do_not_change_financial_results(self):
        entries = (order(DAYS[0], quantity="3"), order(DAYS[1], "sell", "1"))
        baseline = run(entries=entries, profile=ExecutionProfile("13.7", "2.3", "0.017"))
        with localcontext() as ctx:
            ctx.prec = 6
            ctx.rounding = ROUND_DOWN
            changed = run(entries=entries, profile=ExecutionProfile("13.7", "2.3", "0.017"))
        self.assertEqual(baseline, changed)

    def test_cost_stress_for_fixed_fills_has_exact_expected_wealth_difference(self):
        entries = (order(DAYS[0], quantity="2"), order(DAYS[1], "sell", "2"))
        zero = run(entries=entries)
        costly = run(entries=entries, profile=ExecutionProfile("0", "100", "1"))
        self.assertEqual(zero.summary.final_equity - costly.summary.final_equity, Decimal("2.4"))
        self.assertEqual([(f.side, f.quantity) for f in zero.fills], [(f.side, f.quantity) for f in costly.fills])

    def test_cash_and_equity_reconcile_from_public_audit_records(self):
        result = run(entries=(order(DAYS[0], quantity="3"), order(DAYS[1], "sell", "1")),
                     profile=ExecutionProfile("11", "7", "0.5"))
        cash = Decimal(0)
        for movement in result.cash_movements:
            cash += movement.amount
            self.assertEqual(cash, movement.cash_after)
        for state in result.equity:
            self.assertEqual(state.cash + state.market_value + state.receivables, state.equity)
            self.assertEqual(Decimal(100) + state.realized_pnl + state.unrealized_pnl + state.dividend_income,
                             state.equity)

    def test_drawdown_peak_includes_starting_capital(self):
        result = run(entries=(order(DAYS[0], quantity="1"),), profile=ExecutionProfile("0", "0", "10"))
        self.assertEqual(result.summary.final_equity, Decimal(90))
        self.assertEqual(result.summary.max_drawdown, Decimal("0.1"))

    def test_independent_fraction_cash_and_holdings_reference(self):
        # Fraction arithmetic independently reconstructs cash and shares across many order paths.
        for seed in range(10):
            rng = random.Random(seed)
            assets = ("A", "B")
            sessions = tuple(date(2024, 2, day) for day in range(1, 13))
            securities = tuple(Security(a, a, "SYNTHETIC") for a in assets)
            snapshot = data(tuple(bar(d, "10" if a == "A" else "17", a) for d in sessions for a in assets),
                            sessions=sessions, securities=securities)
            entries = tuple(order(d, rng.choice(("buy", "sell")), str(rng.randint(1, 6)), a)
                            for d in sessions[:-1] for a in assets)
            result = run(snapshot, entries, cash="200", profile=ExecutionProfile("100", "50", "0.25"))
            cash = Fraction(200)
            held = {a: 0 for a in assets}
            for i, state in enumerate(result.equity):
                if i:
                    pending = [e.request for e in entries if e.signal_date == sessions[i - 1]]
                    for request in sorted(pending, key=lambda r: (r.side == "buy", r.security_id)):
                        qty = int(request.quantity)
                        raw_price = 10 if request.security_id == "A" else 17
                        price = Fraction(raw_price) * (Fraction(101, 100) if request.side == "buy" else Fraction(99, 100))
                        value = price * qty
                        fee = value * Fraction(1, 200) + Fraction(1, 4)
                        if request.side == "buy" and value + fee <= cash:
                            cash -= value + fee
                            held[request.security_id] += qty
                        elif request.side == "sell" and qty <= held[request.security_id] and cash + value >= fee:
                            cash += value - fee
                            held[request.security_id] -= qty
                expected_cash = Decimal(cash.numerator) / Decimal(cash.denominator)
                self.assertEqual(state.cash, expected_cash)
                self.assertEqual({p.security_id: int(p.quantity) for p in state.positions},
                                 {a: q for a, q in held.items() if q})


class GoldenAndReportingTests(unittest.TestCase):
    def golden(self):
        f = FIXTURES / "data"
        snapshot = CsvSource(f / "bars.csv", f / "calendar.csv", f / "securities.csv", META, f / "actions.csv").load()
        expected = json.loads((FIXTURES / "backtest" / "expected.json").read_text(encoding="utf-8"))
        result = run_backtest(snapshot, load_schedule(FIXTURES / "backtest" / "orders.json"),
                              RunConfig(expected["capital"], ExecutionProfile(expected["slippage_bps"], expected["fee_bps"])))
        return snapshot, result, expected

    def test_complete_hand_calculated_split_dividend_portfolio(self):
        _, result, expected = self.golden()
        for state, row in zip(result.equity, expected["daily"], strict=True):
            self.assertEqual(state.session.isoformat(), row["session"])
            for field in ("cash", "receivables", "market_value", "equity"):
                self.assertEqual(getattr(state, field), Decimal(row[field]))
        for fill, row in zip(result.fills, expected["fills"], strict=True):
            self.assertEqual((fill.security_id, fill.side), (row["security_id"], row["side"]))
            self.assertEqual(fill.quantity, Decimal(row["quantity"]))
            self.assertEqual(fill.price, Decimal(row["price"]))
        for field, key in (("realized_pnl", "final_realized_pnl"), ("unrealized_pnl", "final_unrealized_pnl"),
                           ("dividend_income", "dividend_income")):
            self.assertEqual(getattr(result.equity[-1], field), Decimal(expected[key]))
        self.assertEqual(result.summary.expired_order_count, expected["expired_orders"])

    def test_repeated_runs_and_saved_results_are_reproducible(self):
        snapshot, result, _ = self.golden()
        again = run_backtest(snapshot, load_schedule(FIXTURES / "backtest" / "orders.json"),
                             RunConfig("1000", ExecutionProfile("0")))
        self.assertEqual(result.result_hash, again.result_hash)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result"
            save_run(result, path)
            self.assertEqual(verify_run(path), primitive(result))
            self.assertIn("signal_reason", (path / "orders.csv").read_text(encoding="utf-8"))
            self.assertIn("realized_pnl", (path / "fills.csv").read_text(encoding="utf-8"))

    def test_corrupted_csv_or_json_is_detected(self):
        _, result, _ = self.golden()
        for filename in ("fills.csv", "run.json"):
            with TemporaryDirectory() as directory:
                path = Path(directory) / "result"
                save_run(result, path)
                with (path / filename).open("a", encoding="utf-8") as stream:
                    stream.write("corrupted")
                with self.assertRaisesRegex(ValueError, "integrity"):
                    verify_run(path)

    def test_existing_run_is_never_overwritten(self):
        _, result, _ = self.golden()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result"
            save_run(result, path)
            before = (path / "run.json").read_bytes()
            with self.assertRaises(FileExistsError):
                save_run(result, path)
            self.assertEqual((path / "run.json").read_bytes(), before)

    def test_manifest_consistency_is_checked_even_if_file_hash_is_updated(self):
        _, result, _ = self.golden()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result"
            save_run(result, path)
            manifest_path = path / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["data"]["source"] = "inconsistent_source"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            marker_path = path / "COMPLETE.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["files"]["manifest.json"] = sha256(manifest_path.read_bytes()).hexdigest()
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest disagrees"):
                verify_run(path)

    def test_failed_export_has_no_completion_marker(self):
        _, result, _ = self.golden()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result"
            with patch("quant_core.reporting._csv", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    save_run(result, path)
            self.assertFalse((path / "COMPLETE.json").exists())
            with self.assertRaises(OSError):
                verify_run(path)

    def test_results_and_manifests_are_immutable_and_include_assumptions(self):
        _, result, _ = self.golden()
        with self.assertRaises(FrozenInstanceError):
            result.summary.final_equity = Decimal(0)
        self.assertEqual(result.manifest.engine_hash, code_hash())
        root = Path(quant_core.__file__).parent  # Every source file, as run manifests have always hashed them.
        paths = sorted(root.rglob("*.py"))  # Linux order; code_hash sorts by parts so Windows agrees.
        self.assertEqual(code_hash(), content_hash(tuple((path.relative_to(root).as_posix(),
                                                          path.read_text(encoding="utf-8")) for path in paths)))
        self.assertEqual([p.relative_to(root).parts for p in paths],
                         sorted(p.relative_to(root).parts for p in paths))
        self.assertEqual(result.manifest.data.adjustment_policy, "raw")
        self.assertEqual(result.manifest.config.execution.cash_policy, "economic_proceeds_reuse")
        self.assertTrue(result.manifest.assumptions)

    def test_cli_run_then_verify_and_actionable_failure(self):
        snapshot, _, _ = self.golden()
        with TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(snapshot, path / "snapshot.json")
            output = StringIO()
            with redirect_stdout(output):
                code = main(["run", str(path / "snapshot.json"), "--orders", str(FIXTURES / "backtest" / "orders.json"),
                             "--capital", "1000", "--slippage-bps", "0", "--output", str(path / "run")])
            self.assertEqual(code, 0)
            result_hash = json.loads(output.getvalue())["result_hash"]
            verification = StringIO()
            with redirect_stdout(verification):
                self.assertEqual(main(["verify", str(path / "run")]), 0)
            self.assertEqual(json.loads(verification.getvalue())["result_hash"], result_hash)
            error = StringIO()
            with redirect_stderr(error):
                self.assertEqual(main(["verify", str(path / "missing")]), 2)
            self.assertIn("Backtest error:", error.getvalue())
            self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
