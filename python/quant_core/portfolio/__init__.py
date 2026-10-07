"""Average-cost ledger used by the daily simulator, under its decimal context."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal(0)


@dataclass
class Position:
    quantity: Decimal
    basis: Decimal  # Total acquisition cost including entry fees.


@dataclass(frozen=True)
class Receivable:
    security_id: str
    ex_date: date
    pay_date: date
    amount: Decimal


@dataclass(frozen=True)
class PositionValue:
    security_id: str
    quantity: Decimal
    basis: Decimal
    close: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


class PortfolioLedger:
    def __init__(self, initial_cash: Decimal):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.receivables: list[Receivable] = []
        self.realized_pnl = ZERO
        self.dividend_income = ZERO
        self.fees = ZERO
        self.slippage = ZERO

    def buy(self, asset, quantity, notional, fees, slippage):
        debit = notional + fees
        if quantity <= 0 or debit > self.cash:
            raise ValueError("Invalid or unaffordable buy")
        position = self.positions.setdefault(asset, Position(ZERO, ZERO))
        position.quantity += quantity
        position.basis += debit
        self.cash -= debit
        self.fees += fees
        self.slippage += slippage

    def sell(self, asset, quantity, notional, fees=ZERO, slippage=ZERO):
        position = self.positions[asset]
        if quantity <= 0 or quantity > position.quantity or self.cash + notional < fees:
            raise ValueError("Invalid or unaffordable sell")
        removed_basis = (position.basis if quantity == position.quantity
                         else position.basis * quantity / position.quantity)
        pnl = notional - fees - removed_basis
        self.cash += notional - fees
        position.quantity -= quantity
        position.basis -= removed_basis
        self.realized_pnl += pnl
        self.fees += fees
        self.slippage += slippage
        if position.quantity == 0:
            del self.positions[asset]
        return pnl

    def values(self, marks):
        return tuple(PositionValue(asset, p.quantity, p.basis, marks[asset],
                                   p.quantity * marks[asset], p.quantity * marks[asset] - p.basis)
                     for asset, p in sorted(self.positions.items()))

    def assert_identity(self, values):
        if self.cash < 0 or any(p.quantity <= 0 or p.basis < 0 for p in self.positions.values()):
            raise ArithmeticError("Invalid portfolio cash, quantity, or basis")
        receivables = sum((r.amount for r in self.receivables), ZERO)
        equity = self.cash + receivables + sum((v.market_value for v in values), ZERO)
        reconciled = (self.initial_cash + self.realized_pnl + self.dividend_income
                      + sum((v.unrealized_pnl for v in values), ZERO))
        # Relative tolerance accommodates decimal rounding on partial basis disposal.
        if abs(equity - reconciled) > max(Decimal("1e-18"), abs(equity) * Decimal("1e-24")):
            raise ArithmeticError("Cash + positions + receivables does not reconcile to P&L")
        return equity
