"""Deterministic entry sizing; no alpha, vendor calls, or return optimization."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR

from quant_core.data import identity, number
from quant_core.data.adjustments import normalized_history  # Retained public import for Stage 3 callers.

ZERO = Decimal("0")


@dataclass(frozen=True)
class EntryIntent:
    security_id: str
    method: str = "atr"
    allocation: Decimal = Decimal("0.10")
    risk_fraction: Decimal = Decimal("0.005")
    stop_price: Decimal | None = None
    atr_period: int = 14
    atr_multiple: Decimal = Decimal("2")
    priority: int = 0
    reason: str = "entry_intent"

    def __post_init__(self):
        identity(self.security_id)
        for name in ("allocation", "risk_fraction", "atr_multiple"):
            object.__setattr__(self, name, number(getattr(self, name)))
        if self.stop_price is not None:
            object.__setattr__(self, "stop_price", number(self.stop_price))
        if self.method not in ("fixed_allocation", "fixed_fractional", "atr"):
            raise ValueError("Unsupported sizing method")
        if not 0 < self.allocation <= 1 or not 0 < self.risk_fraction <= 1 or self.atr_multiple <= 0:
            raise ValueError("Sizing fractions must be in (0, 1]; ATR multiple positive")
        if type(self.atr_period) is not int or self.atr_period <= 0:
            raise ValueError("ATR period must be a positive integer")
        if type(self.priority) is not int or not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Intent requires integer priority and a reason")
        if self.method == "atr" and self.stop_price is not None:
            raise ValueError("ATR sizing derives its stop; do not supply a stop price")
        if self.method != "atr" and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError("Allocation/fractional intents require a positive protective stop")


def wilder_atr(bars, period):
    """SMA seed of first n true ranges, then Wilder recursion; n+1 bars required."""
    if type(period) is not int or period <= 0:
        raise ValueError("ATR period must be a positive integer")
    if len(bars) <= period:
        return None
    ranges = tuple(max(b.high - b.low, abs(b.high - previous.close), abs(b.low - previous.close))
                   for previous, b in zip(bars, bars[1:]))
    atr = sum(ranges[:period], ZERO) / period
    for value in ranges[period:]:
        atr = (atr * (period - 1) + value) / period
    return atr


def floor_shares(value):
    return max(ZERO, value.to_integral_value(rounding=ROUND_FLOOR))


def allocation_shares(equity, allocation, reference, execution, scale=Decimal("1")):
    """Whole-share capital budget includes modeled entry costs at the signal reference."""
    entry, _, fee, _ = execution.quote(reference, Decimal("1"), "buy")
    flat = execution.fee_per_order
    return floor_shares((equity * allocation * scale - flat) / (entry + fee - flat))


def size_entry(intent, equity, reference, stop, execution, scale=Decimal("1")):
    """Whole shares including adverse entry/exit prices and percentage/flat fees."""
    entry, _, entry_fee, _ = execution.quote(reference, Decimal("1"), "buy")
    exit_price, _, exit_fee, _ = execution.quote(stop, Decimal("1"), "sell")
    flat = execution.fee_per_order
    if intent.method == "fixed_allocation":
        return allocation_shares(equity, intent.allocation, reference, execution, scale)
    unit_loss = entry + entry_fee - flat - exit_price + exit_fee - flat
    if unit_loss <= 0:
        return ZERO
    return floor_shares((equity * intent.risk_fraction * scale - 2 * flat) / unit_loss)
