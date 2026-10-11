"""Entry-to-exit trade records; every expected number is calculated by hand."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from quant_core.analytics.trades import round_trips
from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.data import Bar, CashDelisting, DataMetadata, Dividend, Security, Snapshot, Split
from quant_core.data.rates import CashRateSeries
from quant_core.execution import ExecutionProfile, OrderRequest

META = DataMetadata("synthetic", datetime(2024, 1, 20, tzinfo=timezone.utc),
                    "fixed_synthetic_universe", True, "synthetic_explicit_sessions")
D = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9))


def bar(day, open_, close=None, low=None, asset="A"):
    close = open_ if close is None else close
    o, c = Decimal(open_), Decimal(close)
    return Bar(asset, day, o, max(o, c), Decimal(low) if low else min(o, c), c, "1000")


def order(day, side, quantity, reason="test_input", stop=None):
    return ScheduledOrder(day, OrderRequest("A", side, quantity, reason=reason, stop_price=stop))


def run(bars, orders, actions=(), security=None, profile=None, **options):
    """`orders` holds order() argument tuples; the calendar is every bar or action date."""
    sessions = tuple(sorted({b.session for b in bars} | {a.session for a in actions}))
    data = Snapshot(sessions, tuple(bars), META, (security or Security("A", "AAA", "SYNTHETIC"),), tuple(actions))
    schedule = OrderSchedule(tuple(order(*o) for o in orders))
    return run_backtest(data, schedule, RunConfig("1000", profile or ExecutionProfile("0"), **options))


class RoundTripTests(unittest.TestCase):
    def test_one_round_trip_with_fees(self):
        result = run([bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "12"), bar(D[3], "12")],
                     [(D[0], "buy", "10", "enter"), (D[1], "sell", "10", "leave")],
                     profile=ExecutionProfile("0", fee_per_order="1"))
        (trade,) = round_trips(result)
        # Buy 10 at 10 plus 1 fee = 101; sell 10 at 12 less 1 fee = 119; P&L 18.
        self.assertEqual((trade.trade_id, trade.security_id, trade.symbol, trade.status),
                         ("trade-000001", "A", "AAA", "closed"))
        self.assertEqual((trade.entry_signal_date, trade.entry_date, trade.entry_reason), (D[0], D[1], "enter"))
        self.assertEqual((trade.exit_signal_date, trade.exit_date, trade.exit_reason), (D[1], D[2], "leave"))
        self.assertEqual((trade.buy_fills, trade.sell_fills), (1, 1))
        self.assertEqual((trade.cost_basis, trade.proceeds, trade.dividends, trade.fees, trade.slippage),
                         (101, 119, 0, 2, 0))
        self.assertEqual((trade.realized_pnl, trade.unrealized_pnl, trade.total_pnl), (18, 0, 18))
        self.assertEqual(trade.return_on_cost, Decimal(18) / 101)
        self.assertEqual((trade.holding_days, trade.fill_ids), (1, ("fill-000001", "fill-000002")))

    def test_slippage_fees_and_order_across_securities(self):
        bars = [bar(day, "20", asset="B") for day in D[:4]]
        bars += [bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "10"), bar(D[3], "12")]
        data = Snapshot(D[:4], tuple(bars), META, (Security("A", "AAA", "SYNTHETIC"), Security("B", "BBB", "SYNTHETIC")))
        schedule = OrderSchedule((ScheduledOrder(D[0], OrderRequest("B", "buy", "10", reason="enter_b")),
                                  order(D[1], "buy", "10", "enter_a"), order(D[2], "sell", "10", "leave_a")))
        result = run_backtest(data, schedule, RunConfig("1000", ExecutionProfile("10", fee_bps="10")))
        b, a = round_trips(result)
        # B opened first and is still open: 10 at 20.02 plus 0.2002 fee, marked at 20.
        self.assertEqual((b.trade_id, b.security_id, b.status, b.entry_reason), ("trade-000001", "B", "open", "enter_b"))
        self.assertEqual((b.cost_basis, b.unrealized_pnl, b.fill_ids), (Decimal("200.4002"), Decimal("-0.4002"),
                                                                         ("fill-000001",)))
        # A: buy 10 at 10.01 plus 0.1001 fee; sell 10 at 11.988 less 0.11988 fee.
        self.assertEqual((a.trade_id, a.status, a.fill_ids), ("trade-000002", "closed", ("fill-000002", "fill-000003")))
        self.assertEqual((a.cost_basis, a.proceeds, a.fees, a.slippage, a.realized_pnl),
                         (Decimal("100.2001"), Decimal("119.76012"), Decimal("0.21998"), Decimal("0.22"),
                          Decimal("19.56002")))

    def test_partial_sale_add_and_dividend_stay_in_one_trade(self):
        bars = [bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "10"), bar(D[3], "11"), bar(D[4], "12"), bar(D[5], "13")]
        result = run(bars, [(D[0], "buy", "10"), (D[2], "sell", "4"), (D[3], "buy", "2", "add"), (D[4], "sell", "8")],
                     actions=(Dividend("A", D[2], "0.5", D[2]),))
        (trade,) = round_trips(result)
        # Cost 100 + 24; proceeds 44 + 104; dividend 10 x 0.5; realized (44 - 40) + (104 - 84).
        self.assertEqual((trade.buy_fills, trade.sell_fills, trade.entry_reason), (2, 2, "test_input"))
        self.assertEqual((trade.cost_basis, trade.proceeds, trade.dividends), (124, 148, 5))
        self.assertEqual((trade.realized_pnl, trade.total_pnl), (24, 29))
        self.assertEqual((trade.exit_date, trade.holding_days), (D[5], 6))

    def test_same_session_exit_and_reentry_make_two_trades(self):
        bars = [bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "10"), bar(D[3], "10", close="15")]
        result = run(bars, [(D[0], "buy", "1"), (D[1], "sell", "1"), (D[1], "buy", "1")])
        first, second = round_trips(result)
        self.assertEqual((first.trade_id, first.status, first.exit_date), ("trade-000001", "closed", D[2]))
        self.assertEqual((second.trade_id, second.status, second.entry_date), ("trade-000002", "open", D[2]))
        # Open trade: bought at 10, marked at the final close of 15.
        self.assertEqual((second.unrealized_pnl, second.total_pnl, second.holding_days), (5, 5, 1))
        self.assertEqual((second.exit_signal_date, second.exit_date, second.exit_reason), (None, None, None))

    def test_stop_exit_uses_the_trigger_session_as_its_signal(self):
        bars = [bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "9.5", close="9", low="8.5"), bar(D[3], "9")]
        result = run(bars, [(D[0], "buy", "10", "enter", "9")])
        (trade,) = round_trips(result)
        self.assertEqual((trade.exit_signal_date, trade.exit_date, trade.exit_reason), (D[2], D[2], "stop_intraday"))
        self.assertEqual((trade.proceeds, trade.realized_pnl), (90, -10))

    def test_gap_stop_exit_fills_at_the_open(self):
        bars = [bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "8.5"), bar(D[3], "8.5")]
        (trade,) = round_trips(run(bars, [(D[0], "buy", "10", "enter", "9")]))
        self.assertEqual((trade.exit_signal_date, trade.exit_date, trade.exit_reason), (D[2], D[2], "stop_gap"))
        self.assertEqual((trade.proceeds, trade.realized_pnl), (85, -15))

    def test_cash_delisting_closes_the_trade(self):
        security = Security("A", "AAA", "SYNTHETIC", delisted_on=D[3])
        result = run([bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "10")], [(D[0], "buy", "10")],
                     actions=(CashDelisting("A", D[3], "12"),), security=security)
        (trade,) = round_trips(result)
        self.assertEqual((trade.exit_signal_date, trade.exit_date, trade.exit_reason), (None, D[3], "cash_delisting"))
        self.assertEqual((trade.sell_fills, trade.proceeds, trade.realized_pnl), (0, 120, 20))
        self.assertEqual(trade.holding_days, 2)  # Bought Wednesday, settled Friday.

    def test_split_shares_are_sold_in_new_units(self):
        bars = [bar(D[0], "100"), bar(D[1], "100"), bar(D[2], "50"), bar(D[3], "52")]
        result = run(bars, [(D[0], "buy", "2"), (D[2], "sell", "4")],
                     actions=(Split("A", D[2], new_shares=2, old_shares=1),),
                     profile=ExecutionProfile("0", fee_per_order="1"))
        (trade,) = round_trips(result)
        # Cost 2 x 100 + 1 = 201; four post-split shares at 52 less 1 = 207.
        self.assertEqual((trade.status, trade.cost_basis, trade.proceeds, trade.realized_pnl), ("closed", 201, 207, 6))

    def test_trades_and_interest_reconcile_to_equity(self):
        rates = CashRateSeries("test_source", "test_3m", META.retrieved_at, ((date(2023, 12, 29), "0.0365"),))
        bars = [bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "11"), bar(D[3], "12", close="13")]
        result = run(bars, [(D[0], "buy", "5"), (D[1], "sell", "5"), (D[2], "buy", "3")],
                     actions=(Dividend("A", D[2], "1", D[2]),), cash_rates=rates)
        trades = round_trips(result)
        final = result.equity[-1]
        self.assertGreater(final.interest_income, 0)
        self.assertEqual(sum(t.total_pnl for t in trades) + final.interest_income, final.equity - 1000)

    def test_inconsistent_ledgers_are_refused(self):
        result = run([bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "10")], [(D[0], "buy", "1"), (D[1], "sell", "1")])
        with self.assertRaisesRegex(ArithmeticError, "Sale without an open trade"):
            round_trips(replace(result, fills=result.fills[1:]))
        security = Security("A", "AAA", "SYNTHETIC", delisted_on=D[3])
        delisted = run([bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "10")], [(D[0], "buy", "10")],
                       actions=(CashDelisting("A", D[3], "12"),), security=security)
        with self.assertRaisesRegex(ArithmeticError, "without an open trade"):
            round_trips(replace(delisted, fills=()))
        held = run([bar(D[0], "10"), bar(D[1], "10"), bar(D[2], "10")], [(D[0], "buy", "1")],
                   actions=(Dividend("A", D[2], "1", D[2]),))
        final = held.equity[-1]
        with self.assertRaisesRegex(ArithmeticError, "disagree with final positions"):
            round_trips(replace(held, equity=held.equity[:-1] + (replace(final, positions=()),)))
        without_dividend = tuple(a for a in held.corporate_actions if a.kind != "dividend_entitlement")
        with self.assertRaisesRegex(ArithmeticError, "do not reconcile"):
            round_trips(replace(held, corporate_actions=without_dividend))


if __name__ == "__main__":
    unittest.main()
