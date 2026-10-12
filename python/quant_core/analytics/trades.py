"""Entry-to-exit trade records rebuilt from a finished run's audit ledgers.

A trade is one holding period: it opens with a buy into a flat position and
closes when the position returns to zero shares (sale, stop or cash delisting).
Partial sales and added buys stay inside the same trade. Splits change share
counts but not money, so they need no handling here.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from quant_core.analytics import CONTEXT, ZERO
from quant_core.portfolio import reconciles

STOP_KINDS = ("stop_gap", "stop_intraday")


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    security_id: str
    symbol: str
    status: str  # "closed" or "open".
    entry_signal_date: date
    entry_date: date
    entry_reason: str
    exit_signal_date: date | None  # Stops trigger on their fill session; delistings have no signal.
    exit_date: date | None
    exit_reason: str | None  # Sell reason, stop kind or "cash_delisting".
    buy_fills: int
    sell_fills: int
    cost_basis: Decimal  # Buy notional plus buy fees.
    proceeds: Decimal  # Sell notional minus sell fees, plus delisting cash.
    dividends: Decimal  # Entitlements while held, paid or not.
    fees: Decimal
    slippage: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal  # Open trades only, at the final close.
    total_pnl: Decimal  # Realized + unrealized + dividends.
    return_on_cost: Decimal  # Total P&L over total purchases, not over peak capital.
    holding_days: int  # Calendar days from entry to exit, or to the final session.
    fill_ids: tuple[str, ...]  # Every fill in the trade, in execution order.


class _Holding:
    def __init__(self, trade_id, fill, reason):
        self.trade_id, self.security_id, self.symbol = trade_id, fill.security_id, fill.symbol
        self.entry_signal_date, self.entry_date, self.entry_reason = fill.signal_date, fill.execution_date, reason
        self.buy_fills = self.sell_fills = 0
        self.cost_basis = self.proceeds = self.dividends = ZERO
        self.fees = self.slippage = self.realized_pnl = ZERO
        self.fill_ids = []

    def record(self, status, exit_signal_date, exit_date, exit_reason, unrealized, end):
        total = self.realized_pnl + unrealized + self.dividends
        return TradeRecord(self.trade_id, self.security_id, self.symbol, status, self.entry_signal_date,
                           self.entry_date, self.entry_reason, exit_signal_date, exit_date, exit_reason,
                           self.buy_fills, self.sell_fills, self.cost_basis, self.proceeds, self.dividends,
                           self.fees, self.slippage, self.realized_pnl, unrealized, total,
                           total / self.cost_basis, (end - self.entry_date).days, tuple(self.fill_ids))


def round_trips(result) -> tuple[TradeRecord, ...]:
    """Trades in opening order. Corporate actions precede fills within a session, as in the engine."""
    reasons = {o.order_id: o.request.reason for o in result.orders}
    events = [(a.session, 0, a.sequence, a) for a in result.corporate_actions
              if a.kind in ("dividend_entitlement", "cash_delisting")]
    events += [(f.execution_date, 1, index, f) for index, f in enumerate(result.fills)]
    events.sort(key=lambda event: event[:3])
    holdings, records, count = {}, [], 0
    with localcontext(CONTEXT):
        for day, phase, _, event in events:
            holding = holdings.get(event.security_id)
            if phase == 0:
                if holding is None:
                    if event.amount:
                        raise ArithmeticError("Corporate-action cash for a security without an open trade")
                    continue
                if event.kind == "dividend_entitlement":
                    holding.dividends += event.amount
                else:
                    holding.proceeds += event.amount
                    holding.realized_pnl += event.realized_pnl
                    records.append(holding.record("closed", None, day, "cash_delisting", ZERO, day))
                    del holdings[event.security_id]
                continue
            if event.side == "buy":
                if holding is None:
                    count += 1
                    holding = holdings[event.security_id] = _Holding(
                        f"trade-{count:06d}", event, reasons[event.order_id])
                holding.buy_fills += 1
                holding.cost_basis += event.notional + event.fees
            else:
                if holding is None:
                    raise ArithmeticError("Sale without an open trade")
                holding.sell_fills += 1
                holding.proceeds += event.notional - event.fees
                holding.realized_pnl += event.realized_pnl
            holding.fees += event.fees
            holding.slippage += event.slippage
            holding.fill_ids.append(event.fill_id)
            if event.side == "sell" and event.position_quantity_after == 0:
                signal = day if event.execution_kind in STOP_KINDS else event.signal_date
                records.append(holding.record("closed", signal, day, reasons[event.order_id], ZERO, day))
                del holdings[event.security_id]
        final = result.equity[-1]
        positions = {p.security_id: p for p in final.positions}
        if set(holdings) != set(positions):
            raise ArithmeticError("Open trades disagree with final positions")
        for asset, holding in holdings.items():
            records.append(holding.record("open", None, None, None, positions[asset].unrealized_pnl, final.session))
        explained = sum((r.total_pnl for r in records), ZERO) + final.interest_income
        if not reconciles(explained, final.equity - result.summary.initial_cash, final.equity):
            raise ArithmeticError("Trades and interest do not reconcile to the run's P&L")
    return tuple(sorted(records, key=lambda record: record.trade_id))
