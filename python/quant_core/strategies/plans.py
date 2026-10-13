"""Built-in monthly plans: four published rules turned into target weights.

Rules, sources and departures are in docs/STRATEGIES.md (Built-in plans). A
rule sees only month-end values of the securities that passed the data checks,
oldest first, and T-bill growth per month; MonthlyPlan owns the data checks,
share counts and orders.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from quant_core.data import identity, number

ZERO, ONE = Decimal(0), Decimal(1)
PURPOSES = ("built_in_plan", "engineering_fixture")


def _count(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")


@dataclass(frozen=True)
class Target:
    """One security's outcome under a rule; the weight is a fraction of the plan's invested share."""
    weight: Decimal
    qualifies: bool
    score: Decimal | None
    rank: int | None
    reasons: tuple[str, ...]
    features: tuple[tuple[str, Decimal], ...] = ()


@dataclass(frozen=True, kw_only=True)
class PlanConfig:
    """Settings every plan shares; the decision offset moves each month-end decision by whole sessions."""
    RULE: ClassVar[str] = ""
    USES_BILLS: ClassVar[bool] = False
    name: str
    universe: tuple[str, ...]
    invested_fraction: Decimal = Decimal("0.95")
    decision_offset: int = 0
    volume_lookback: int = 20
    max_volume_participation: Decimal = Decimal("0.01")
    purpose: str = "built_in_plan"

    def __post_init__(self):
        identity(self.name)
        universe = tuple(self.universe)
        for asset in universe:
            identity(asset)
        if not universe or len(set(universe)) != len(universe):
            raise ValueError("Plan requires a nonempty unique explicit universe")
        object.__setattr__(self, "universe", tuple(sorted(universe)))
        for name in ("invested_fraction", "max_volume_participation"):
            object.__setattr__(self, name, number(getattr(self, name)))
        if not 0 < self.invested_fraction <= 1 or not 0 < self.max_volume_participation <= 1:
            raise ValueError("Invested fraction and volume participation must be in (0, 1]")
        if type(self.decision_offset) is not int or not -2 <= self.decision_offset <= 2:
            raise ValueError("Decision offset must be an integer from -2 to 2 sessions")
        _count(self.volume_lookback, "volume_lookback")
        if self.purpose not in PURPOSES:
            raise ValueError("Unsupported plan purpose")


@dataclass(frozen=True, kw_only=True)
class TrendPlan(PlanConfig):
    """Faber: each asset class holds an equal share while above its 10-month average, else cash."""
    RULE: ClassVar[str] = "trend"
    average_months: int = 10

    def __post_init__(self):
        super().__post_init__()
        _count(self.average_months, "average_months", 2)

    def samples(self, asset):
        return self.average_months

    def targets(self, values, bills=None):
        share = ONE / len(self.universe)  # A skipped asset's share stays in cash.
        targets = {}
        for asset, series in values.items():
            average = sum(series, ZERO) / len(series)
            above = series[-1] > average
            targets[asset] = Target(share if above else ZERO, above, series[-1] / average - ONE, None,
                                    ("above_average" if above else "not_above_average",),
                                    (("month_end_value", series[-1]), ("average_month_end_value", average)))
        return targets


@dataclass(frozen=True, kw_only=True)
class DualMomentumPlan(PlanConfig):
    """Antonacci, absolute momentum first: US stocks against T-bills, then US against non-US, else bonds."""
    RULE: ClassVar[str] = "dual_momentum"
    USES_BILLS: ClassVar[bool] = True
    us_stocks: str
    non_us_stocks: str
    bonds: str
    lookback_months: int = 12

    def __post_init__(self):
        super().__post_init__()
        _count(self.lookback_months, "lookback_months")
        roles = (self.us_stocks, self.non_us_stocks, self.bonds)
        if len(set(roles)) != 3 or set(roles) != set(self.universe):
            raise ValueError("Dual momentum needs distinct US stock, non-US stock and bond securities as its universe")

    def samples(self, asset):
        return 1 if asset == self.bonds else self.lookback_months + 1

    def targets(self, values, bills):
        if set(values) != set(self.universe):
            return {asset: Target(ZERO, False, None, None, ("plan_input_unavailable",)) for asset in values}
        if bills is None or len(bills) != self.lookback_months:
            raise ValueError("Dual momentum needs one T-bill growth factor per lookback month")
        growth = ONE
        for factor in bills:
            growth *= factor
        bill_return = growth - ONE
        returns = {a: values[a][-1] / values[a][0] - ONE for a in (self.us_stocks, self.non_us_stocks)}
        if returns[self.us_stocks] > bill_return:  # Stocks need a positive excess return, not a tie.
            branch = "us_stocks_beat_bills"
            chosen = (self.us_stocks if returns[self.us_stocks] >= returns[self.non_us_stocks]
                      else self.non_us_stocks)
        else:
            branch, chosen = "bills_beat_us_stocks", self.bonds
        targets = {}
        for asset in self.universe:
            reasons = (branch,)
            if asset in returns and chosen != self.bonds:
                reasons += ("higher_lookback_return" if asset == chosen else "lower_lookback_return",)
            elif asset == self.bonds and chosen == self.bonds:
                reasons += ("bond_fallback",)
            features = (("bill_lookback_return", bill_return),)
            if asset in returns:
                features += (("lookback_return", returns[asset]),)
            targets[asset] = Target(ONE if asset == chosen else ZERO, asset == chosen, returns.get(asset), None,
                                    reasons, features)
        return targets


@dataclass(frozen=True, kw_only=True)
class SectorRotationPlan(PlanConfig):
    """12-1 momentum (Asness, Moskowitz and Pedersen); top three equally weighted, monthly (Faber 2010)."""
    RULE: ClassVar[str] = "sector_rotation"
    lookback_months: int = 12
    skip_months: int = 1
    top: int = 3

    def __post_init__(self):
        super().__post_init__()
        _count(self.lookback_months, "lookback_months")
        _count(self.top, "top")
        if type(self.skip_months) is not int or not 0 <= self.skip_months < self.lookback_months:
            raise ValueError("skip_months must be an integer in [0, lookback_months)")

    def samples(self, asset):
        return self.lookback_months + 1

    def targets(self, values, bills=None):
        scores = {asset: series[-1 - self.skip_months] / series[0] - ONE for asset, series in values.items()}
        share = ONE / self.top  # With fewer ranked sectors, empty slots stay in cash.
        targets = {}
        for rank, asset in enumerate(sorted(scores, key=lambda a: (-scores[a], a)), 1):
            chosen = rank <= self.top
            targets[asset] = Target(share if chosen else ZERO, True, scores[asset], rank,
                                    ("top_ranked" if chosen else "below_selection_cutoff",),
                                    (("momentum_return", scores[asset]),))
        return targets


@dataclass(frozen=True, kw_only=True)
class InverseVolatilityPlan(PlanConfig):
    """Asness, Frazzini and Pedersen, unlevered: weights proportional to 1 / volatility of monthly excess returns."""
    RULE: ClassVar[str] = "inverse_volatility"
    USES_BILLS: ClassVar[bool] = True
    volatility_months: int = 36

    def __post_init__(self):
        super().__post_init__()
        _count(self.volatility_months, "volatility_months", 2)

    def samples(self, asset):
        return self.volatility_months + 1

    def targets(self, values, bills):
        if values and (bills is None or len(bills) != self.volatility_months):
            raise ValueError("Inverse volatility needs one T-bill growth factor per month")
        volatility = {}
        for asset, series in values.items():
            # Excess return: the asset's growth over the month minus the T-bills' growth.
            excess = tuple(b / a - growth for a, b, growth in zip(series, series[1:], bills))
            mean = sum(excess, ZERO) / len(excess)
            volatility[asset] = (sum(((e - mean) ** 2 for e in excess), ZERO) / (len(excess) - 1)).sqrt()
        inverse = {asset: ONE / sigma for asset, sigma in volatility.items() if sigma > 0}
        total = sum(inverse.values(), ZERO)  # Rescaled over the ETFs available this month.
        return {asset: Target(inverse[asset] / total if asset in inverse else ZERO, asset in inverse,
                              volatility[asset], None,
                              ("inverse_volatility_weight" if asset in inverse else "zero_volatility",),
                              (("monthly_excess_volatility", volatility[asset]),))
                for asset in values}


def builtin_plans():
    """The four tester-release configurations; see docs/STRATEGIES.md for their sources."""
    return (TrendPlan(name="multi_asset_trend", universe=("SPY", "EFA", "IEF", "VNQ", "GSG")),
            DualMomentumPlan(name="dual_momentum", universe=("SPY", "EFA", "AGG"),
                             us_stocks="SPY", non_us_stocks="EFA", bonds="AGG"),
            SectorRotationPlan(name="us_sector_rotation", universe=(
                "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")),
            InverseVolatilityPlan(name="inverse_volatility", universe=("SPY", "IEF", "LQD", "GSG")))
