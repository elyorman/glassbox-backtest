"""Versioned long-only daily-market execution contract."""

from dataclasses import dataclass
from decimal import Decimal

from quant_core.data import identity, number


@dataclass(frozen=True)
class OrderRequest:
    security_id: str
    side: str
    quantity: Decimal
    priority: int = 0  # Smaller values execute first within each side.
    reason: str = "explicit_order"
    stop_price: Decimal | None = None  # Initial long protective stop-market trigger.

    def __post_init__(self):
        identity(self.security_id)
        object.__setattr__(self, "quantity", number(self.quantity))
        if self.side not in ("buy", "sell") or self.quantity <= 0:
            raise ValueError("Orders require buy/sell and positive quantity")
        if self.side == "buy" and self.quantity != self.quantity.to_integral_value():
            raise ValueError("New buy requests require whole shares")
        if type(self.priority) is not int or not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Orders require integer priority and a nonempty reason")
        if self.stop_price is not None:
            object.__setattr__(self, "stop_price", number(self.stop_price))
            if self.side != "buy" or self.stop_price <= 0:
                raise ValueError("Only buys may attach a positive protective stop")


@dataclass(frozen=True)
class ExecutionProfile:
    slippage_bps: Decimal = Decimal("10")
    fee_bps: Decimal = Decimal("0")
    fee_per_order: Decimal = Decimal("0")
    convention: str = "next_session_open_v1"
    cash_policy: str = "economic_proceeds_reuse"

    def __post_init__(self):
        for name in ("slippage_bps", "fee_bps", "fee_per_order"):
            object.__setattr__(self, name, number(getattr(self, name)))
        if min(self.slippage_bps, self.fee_bps, self.fee_per_order) < 0:
            raise ValueError("Costs cannot be negative")
        if max(self.slippage_bps, self.fee_bps) >= 10000:
            raise ValueError("Cost rates must be below 10000 bps")
        if self.convention != "next_session_open_v1" or self.cash_policy != "economic_proceeds_reuse":
            raise ValueError("Unsupported execution or cash convention")

    def quote(self, open_price: Decimal, quantity: Decimal, side: str):
        """Called under the engine's fixed decimal context."""
        open_price, quantity = number(open_price), number(quantity)
        if open_price <= 0 or quantity <= 0 or side not in ("buy", "sell"):
            raise ValueError("Quote requires positive prices/quantity and buy/sell")
        sign = 1 if side == "buy" else -1
        price = open_price * (1 + sign * self.slippage_bps / 10000)
        notional = price * quantity
        fees = notional * self.fee_bps / 10000 + self.fee_per_order
        slippage = abs(price - open_price) * quantity
        return price, notional, fees, slippage
