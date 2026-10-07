"""Portfolio admission rules. Planned stop losses are budgets, not guarantees."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from quant_core.data import identity, number

ZERO = Decimal("0")


@dataclass(frozen=True)
class RiskPolicy:
    # Engineering defaults, not optimized investment recommendations.
    max_trade_risk: Decimal = Decimal("0.005")
    max_position_fraction: Decimal = Decimal("0.20")
    max_gross_fraction: Decimal = Decimal("0.90")
    cash_reserve_fraction: Decimal = Decimal("0.10")
    max_portfolio_heat: Decimal = Decimal("0.03")
    max_positions: int = 10
    volume_lookback: int = 20
    max_volume_participation: Decimal = Decimal("0.01")
    min_average_dollar_volume: Decimal = ZERO
    max_group_fraction: Decimal | None = None
    security_groups: tuple[tuple[str, str], ...] = ()
    drawdown_reduce: Decimal = Decimal("0.10")
    drawdown_halt: Decimal = Decimal("0.20")
    reduced_budget_scale: Decimal = Decimal("0.50")

    def __post_init__(self):
        fractions = ("max_trade_risk", "max_position_fraction", "max_gross_fraction",
                     "cash_reserve_fraction", "max_portfolio_heat", "max_volume_participation",
                     "drawdown_reduce", "drawdown_halt", "reduced_budget_scale")
        for name in fractions:
            object.__setattr__(self, name, number(getattr(self, name)))
            lower_ok = getattr(self, name) >= 0 if name == "cash_reserve_fraction" else getattr(self, name) > 0
            if not lower_ok or getattr(self, name) > 1:
                raise ValueError(f"Invalid risk fraction: {name}")
        if self.cash_reserve_fraction >= 1 or self.drawdown_reduce >= self.drawdown_halt:
            raise ValueError("Reserve must be below 1; reduction threshold below halt")
        for name in ("max_positions", "volume_lookback"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        object.__setattr__(self, "min_average_dollar_volume", number(self.min_average_dollar_volume))
        if self.min_average_dollar_volume < 0:
            raise ValueError("Minimum dollar volume cannot be negative")
        if self.max_group_fraction is not None:
            object.__setattr__(self, "max_group_fraction", number(self.max_group_fraction))
            if not 0 < self.max_group_fraction <= 1:
                raise ValueError("Group fraction must be in (0, 1]")
        groups = tuple(tuple(pair) for pair in self.security_groups)
        if any(len(pair) != 2 for pair in groups):
            raise ValueError("Group mapping requires security/group pairs")
        for asset, group in groups:
            identity(asset)
            identity(group)
        if len({asset for asset, _ in groups}) != len(groups):
            raise ValueError("One explicit group per security is supported")
        object.__setattr__(self, "security_groups", tuple(sorted(groups)))


@dataclass
class RiskBook:
    """Internal admission snapshot/reservations; never exposed to strategy callbacks."""
    cash: Decimal
    equity: Decimal
    values: dict[str, Decimal] = field(default_factory=dict)
    quantities: dict[str, Decimal] = field(default_factory=dict)
    stops: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskDecision:
    sequence: int
    session: date
    phase: str
    security_id: str | None
    order_id: str | None
    method: str
    status: str
    reason_codes: tuple[str, ...]
    requested_quantity: Decimal
    approved_quantity: Decimal
    reference_price: Decimal | None
    stop_price: Decimal | None
    atr: Decimal | None
    average_volume: Decimal | None
    average_dollar_volume: Decimal | None
    equity_reference: Decimal | None
    planned_loss: Decimal | None
    budget_scale: Decimal
    drawdown: Decimal
    halted: bool
    gross_fraction: Decimal | None = None
    cash_fraction: Decimal | None = None
    heat_fraction: Decimal | None = None


def planned_loss(execution, reference, stop, quantity):
    _, notional, entry_fees, _ = execution.quote(reference, quantity, "buy")
    _, proceeds, exit_fees, _ = execution.quote(stop, quantity, "sell")
    return max(ZERO, notional + entry_fees - proceeds + exit_fees)


def portfolio_heat(book, execution):
    """Remaining marked-value loss to modeled stop proceeds, plus exit costs."""
    heat = ZERO
    for asset, value in book.values.items():
        stop = book.stops.get(asset)
        if stop is None:
            raise ValueError(f"Protected portfolio is missing a stop: {asset}")
        _, proceeds, fees, _ = execution.quote(stop, book.quantities[asset], "sell")
        heat += max(ZERO, value - proceeds + fees)
    return heat


def assess_buy(policy, execution, book, asset, quantity, reference, stop, average_volume, scale):
    """Return every failed admission constraint for the specified full quantity."""
    if stop is None:
        return ("missing_protective_stop",), ZERO
    if stop <= 0 or stop >= reference:
        return ("invalid_stop_distance",), ZERO
    if asset in book.values:
        return ("pyramiding_unsupported",), ZERO
    _, notional, fees, slippage = execution.quote(reference, quantity, "buy")
    loss = planned_loss(execution, reference, stop, quantity)
    after_equity = book.equity - fees - slippage
    value = reference * quantity
    codes = []
    if after_equity <= 0:
        return ("nonpositive_equity",), loss
    if len(book.values) >= policy.max_positions:
        codes.append("max_positions")
    if notional + fees > book.cash:
        codes.append("insufficient_cash")
    if book.cash - notional - fees < policy.cash_reserve_fraction * after_equity:
        codes.append("cash_reserve")
    if value > policy.max_position_fraction * after_equity:
        codes.append("position_cap")
    if sum(book.values.values(), ZERO) + value > policy.max_gross_fraction * after_equity:
        codes.append("gross_exposure")
    if loss > policy.max_trade_risk * book.equity * scale:
        codes.append("trade_risk")
    if portfolio_heat(book, execution) + loss > policy.max_portfolio_heat * book.equity * scale:
        codes.append("portfolio_heat")
    if average_volume is None or quantity > average_volume * policy.max_volume_participation:
        codes.append("volume_participation")
    if policy.max_group_fraction is not None:
        groups = dict(policy.security_groups)
        if asset not in groups or any(a not in groups for a in book.values):
            codes.append("missing_group")
        elif value + sum((v for a, v in book.values.items() if groups[a] == groups[asset]), ZERO) > policy.max_group_fraction * after_equity:
            codes.append("group_exposure")
    return tuple(codes), loss


def reserve_buy(book, execution, asset, quantity, reference, stop):
    _, notional, fees, slippage = execution.quote(reference, quantity, "buy")
    book.cash -= notional + fees
    book.equity -= fees + slippage
    book.values[asset] = reference * quantity
    book.quantities[asset] = quantity
    book.stops[asset] = stop


def portfolio_breaches(policy, execution, book, scale):
    """Observe drift at close; admission caps do not force immediate rebalancing."""
    if book.equity <= 0:
        return ("nonpositive_equity",)
    codes = []
    if len(book.values) > policy.max_positions:
        codes.append("position_count_drift")
    if any(v > policy.max_position_fraction * book.equity for v in book.values.values()):
        codes.append("position_weight_drift")
    if sum(book.values.values(), ZERO) > policy.max_gross_fraction * book.equity:
        codes.append("gross_exposure_drift")
    if book.cash < policy.cash_reserve_fraction * book.equity:
        codes.append("cash_reserve_drift")
    if portfolio_heat(book, execution) > policy.max_portfolio_heat * book.equity * scale:
        codes.append("portfolio_heat_drift")
    if policy.max_group_fraction is not None:
        groups = dict(policy.security_groups)
        if any(asset not in groups for asset in book.values):
            codes.append("missing_group")
        else:
            totals = {}
            for asset, value in book.values.items():
                totals[groups[asset]] = totals.get(groups[asset], ZERO) + value
            if any(v > policy.max_group_fraction * book.equity for v in totals.values()):
                codes.append("group_exposure_drift")
    return tuple(codes)


def load_policy(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if set(payload) != {"schema_version", "policy"} or type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("Unsupported risk policy schema")
        return RiskPolicy(**payload["policy"])
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f"Malformed risk policy: {exc}") from exc
