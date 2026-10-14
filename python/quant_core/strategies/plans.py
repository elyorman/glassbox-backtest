"""Built-in monthly plans: four published rules turned into target weights.

Rules, sources and departures are in docs/STRATEGIES.md (Built-in plans). A
rule sees only month-end values of the securities that passed the data checks,
oldest first, and T-bill growth per month; MonthlyPlan owns the data checks,
share counts and orders.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import ClassVar, Mapping

from quant_core.backtest.contracts import SignalDecision, SourceSpec
from quant_core.backtest.sources import OrderBatch
from quant_core.data import Security, identity, number, require_raw_volume, session
from quant_core.data.adjustments import adjusted_quantity
from quant_core.data.rates import CashRateSeries
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.features import PRICE_POLICY, signal_prices
from quant_core.provenance import content_hash, primitive
from quant_core.strategies import rebalance_dates, rebalance_order

ZERO, ONE = Decimal(0), Decimal(1)
PURPOSES = ("built_in_plan", "benchmark", "engineering_fixture")


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

    def _check_values(self, values):
        """Rules take exactly `samples(asset)` month-end values for securities in the universe."""
        for asset, series in values.items():
            if asset not in self.universe or len(series) != self.samples(asset):
                raise ValueError(f"{self.RULE} needs {self.samples(asset) if asset in self.universe else 'no'} "
                                 f"month-end values for {asset}, got {len(series)}")


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
        self._check_values(values)
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
        self._check_values(values)
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
                tied = returns[self.us_stocks] == returns[self.non_us_stocks]  # The US is held on a tie.
                reasons += ("equal_lookback_return" if tied else
                            "higher_lookback_return" if asset == chosen else "lower_lookback_return",)
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
        self._check_values(values)
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
        self._check_values(values)
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


@dataclass(frozen=True, kw_only=True)
class FixedWeightPlan(PlanConfig):
    """A comparison portfolio with constant target weights; a skipped ETF's weight stays in cash."""
    RULE: ClassVar[str] = "fixed_weight"
    weights: tuple[tuple[str, Decimal], ...]
    purpose: str = "benchmark"

    def __post_init__(self):
        super().__post_init__()
        weights = tuple(sorted((asset, number(weight)) for asset, weight in self.weights))
        if (tuple(asset for asset, _ in weights) != self.universe or any(weight <= 0 for _, weight in weights)
                or sum((weight for _, weight in weights), ZERO) > 1):
            raise ValueError("Fixed weights must be positive, one per universe security, and sum to at most 1")
        object.__setattr__(self, "weights", weights)

    def samples(self, asset):
        return 1

    def targets(self, values, bills=None):
        self._check_values(values)
        weights = dict(self.weights)
        return {asset: Target(weights[asset], True, None, None, ("fixed_weight",)) for asset in values}


@dataclass(frozen=True, kw_only=True)
class EqualWeightPlan(PlanConfig):
    """A comparison portfolio with equal weights over the ETFs that pass the data checks at each decision."""
    RULE: ClassVar[str] = "equal_weight"
    purpose: str = "benchmark"

    def samples(self, asset):
        return 1

    def targets(self, values, bills=None):
        self._check_values(values)
        share = ONE / len(values) if values else ZERO
        return {asset: Target(share, True, None, None, ("equal_weight",)) for asset in values}


def plan_to_dict(plan):
    """A plan configuration as plain JSON values, with its rule; `plan_from_dict` reverses it exactly."""
    if not isinstance(plan, PlanConfig) or not plan.RULE:
        raise ValueError("Only a plan configuration can be written")
    return {"rule": plan.RULE, **primitive(plan)}


def plan_from_dict(values):
    rules = {cls.RULE: cls for cls in (TrendPlan, DualMomentumPlan, SectorRotationPlan, InverseVolatilityPlan,
                                       FixedWeightPlan, EqualWeightPlan)}
    if not isinstance(values, dict) or not isinstance(values.get("rule"), str) or values["rule"] not in rules:
        raise ValueError("Unknown plan rule")
    fields = {key: value for key, value in values.items() if key != "rule"}
    for key in ("universe", "weights"):
        if key in fields and not isinstance(fields[key], list):
            raise ValueError(f"Plan {key} must be a list")
    try:
        return rules[values["rule"]](**fields)
    except TypeError as exc:
        raise ValueError(f"Malformed plan configuration: {exc}") from None


def builtin_plans():
    """The four tester-release configurations; see docs/STRATEGIES.md for their sources."""
    return (TrendPlan(name="multi_asset_trend", universe=("SPY", "EFA", "IEF", "VNQ", "GSG")),
            DualMomentumPlan(name="dual_momentum", universe=("SPY", "EFA", "AGG"),
                             us_stocks="SPY", non_us_stocks="EFA", bonds="AGG"),
            SectorRotationPlan(name="us_sector_rotation", universe=(
                "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")),
            InverseVolatilityPlan(name="inverse_volatility", universe=("SPY", "IEF", "LQD", "GSG")))


def decision_sessions(calendar, offset=0):
    """Month-end sessions moved by `offset` sessions; a moved session outside the calendar is dropped."""
    calendar = tuple(calendar)
    index = {day: position for position, day in enumerate(calendar)}
    return tuple(calendar[index[day] + offset] for day in rebalance_dates(calendar, "month_end")
                 if 0 <= index[day] + offset < len(calendar))


@dataclass(frozen=True, kw_only=True)
class PlanSpec(SourceSpec):
    plan: PlanConfig
    rule: str
    signal_price_policy: str
    calendar: tuple[date, ...]
    first_signal_session: date
    decision_sessions: tuple[date, ...]
    allocation_execution: ExecutionProfile
    cash_rates: CashRateSeries | None


@dataclass(frozen=True)
class MonthlyPlan:
    """Order source for a built-in plan: data checks, month-end values, the rule, then whole-share orders."""
    plan: PlanConfig
    calendar: tuple[date, ...]
    securities: tuple[Security, ...]
    first_signal_session: date
    execution: ExecutionProfile = field(default_factory=ExecutionProfile)
    cash_rates: CashRateSeries | None = None  # The plan's own T-bill series, independent of idle-cash interest.
    _spec: PlanSpec = field(init=False, repr=False, compare=False)
    _decisions: Mapping = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.plan, PlanConfig) or not self.plan.RULE:
            raise ValueError("Monthly plan requires a plan configuration")
        if not isinstance(self.execution, ExecutionProfile):
            raise ValueError("Monthly plan requires an allocation execution profile")
        if self.cash_rates is not None and not isinstance(self.cash_rates, CashRateSeries):
            raise ValueError("Plan T-bill rates require CashRateSeries")
        if self.plan.USES_BILLS != (self.cash_rates is not None):
            raise ValueError("Dual momentum and inverse volatility need their own T-bill rates; other plans take none")
        calendar = tuple(self.calendar)
        session(self.first_signal_session)
        if self.first_signal_session not in calendar:
            raise ValueError("First signal session is outside the supplied calendar")
        securities = tuple(sorted(self.securities, key=lambda s: s.security_id))
        if tuple(s.security_id for s in securities) != self.plan.universe:
            raise ValueError("Plan securities must match its universe")
        decisions = decision_sessions(calendar, self.plan.decision_offset)
        object.__setattr__(self, "calendar", calendar)
        object.__setattr__(self, "securities", securities)
        object.__setattr__(self, "_decisions", MappingProxyType({day: k for k, day in enumerate(decisions)}))
        digest = content_hash(("monthly_plan_v1", self.plan.RULE, PRICE_POLICY, self.plan, calendar, securities,
                               self.first_signal_session, decisions, self.execution, self.cash_rates))
        object.__setattr__(self, "_spec", PlanSpec(
            name=self.plan.name, version="1", artifact_hash=digest, purpose=self.plan.purpose, plan=self.plan,
            rule=self.plan.RULE, signal_price_policy=PRICE_POLICY, calendar=calendar,
            first_signal_session=self.first_signal_session, decision_sessions=decisions,
            allocation_execution=self.execution, cash_rates=self.cash_rates))

    @property
    def spec(self):
        return self._spec

    @property
    def _window(self):
        return max(self.plan.samples(asset) for asset in self.plan.universe)

    def validate_run(self, snapshot, run_config):
        """Preflight hook: bindings, data declarations and T-bill coverage; never reads outcomes."""
        require_raw_volume(snapshot.metadata, "Plan liquidity rules")
        if tuple(snapshot.sessions) != self.calendar or run_config.start != self.first_signal_session:
            raise ValueError("Plan calendar/start must match its frozen run binding")
        registry = {s.security_id: s for s in snapshot.securities}
        if any(registry.get(s.security_id) != s for s in self.securities):
            raise ValueError("Plan security registry disagrees with the dataset")
        if not set(self.plan.universe) <= set(run_config.universe):
            raise ValueError("Plan universe is outside the run universe")
        if self.execution != run_config.execution:
            raise ValueError("Plan allocation costs must match the frozen execution profile")
        if not snapshot.metadata.actions_complete and run_config.actions_policy != "allow_incomplete_diagnostic":
            raise ValueError("Total-return plan signals require declared complete corporate actions")
        if run_config.risk is not None:
            raise ValueError("Built-in plans size by target weight and require risk=None")
        decisions = self.spec.decision_sessions
        inside = [k for k, day in enumerate(decisions) if run_config.start <= day <= run_config.end]
        if self.cash_rates is not None and inside:
            # The engine checks rates for the run's sessions; lookbacks reach back before the run start.
            first, last = decisions[max(0, inside[0] + 1 - self._window)], decisions[inside[-1]]
            for day in self.calendar[bisect_left(self.calendar, first):bisect_left(self.calendar, last)]:
                try:
                    self.cash_rates.rate_before(day)
                except ValueError as exc:
                    raise ValueError(f"Plan T-bill rates must cover every lookback in the run: {exc}") from None

    def orders(self, context):
        if context.as_of not in self._decisions or context.as_of < self.first_signal_session:
            return OrderBatch((), ())
        return self.evaluate(context)

    def evaluate(self, context):
        """The plan's decision on one of its decision sessions; scheduling stays in orders()."""
        k = self._decisions.get(context.as_of)
        if k is None:
            raise ValueError("Plan evaluation requires one of its decision sessions")
        plan, decisions = self.plan, self.spec.decision_sessions
        registry = {s.security_id: s for s in self.securities}
        splits, dividends = defaultdict(list), defaultdict(list)
        for event in context.splits:
            splits[event.security_id].append(event)
        for event in context.dividends:
            dividends[event.security_id].append(event)
        stop = bisect_right(self.calendar, context.as_of)
        values, checks, data = {}, {}, {}
        for asset in plan.universe:
            needed, reasons, features = plan.samples(asset), [], {}
            if not registry[asset].active_on(context.as_of):
                reasons.append("outside_security_lifetime")
            elif k + 1 < needed:
                reasons.append("insufficient_history")
            else:
                samples = decisions[k + 1 - needed:k + 1]
                span = stop - bisect_left(self.calendar, samples[0])
                count = max(span, plan.volume_lookback)
                history = context.history(asset, count)
                if not history or history[-1].session != context.as_of:
                    reasons.append("missing_signal_bar")
                elif len(history) < count:
                    reasons.append("insufficient_history")
                elif tuple(b.session for b in history) != self.calendar[stop - count:stop]:
                    reasons.append("missing_history_session")
                else:
                    recent = history[-plan.volume_lookback:]
                    volume = sum((adjusted_quantity(b.volume, asset, b.session, context.as_of, splits[asset])
                                  for b in recent), ZERO) / plan.volume_lookback
                    features.update(raw_close=history[-1].close, average_volume=volume)
                    if volume <= 0:
                        reasons.append("liquidity_filter")
                    else:
                        index = signal_prices(history[-span:], splits[asset], dividends[asset])
                        position = {bar.session: i for i, bar in enumerate(history[-span:])}
                        values[asset] = tuple(index[position[day]] for day in samples)
            checks[asset], data[asset] = tuple(reasons), features
        bills = None
        if self.cash_rates is not None and k + 1 >= self._window:
            months = decisions[k + 1 - self._window:k + 1]
            bills = tuple(self.cash_rates.growth(self.calendar[bisect_left(self.calendar, a):
                                                               bisect_left(self.calendar, b) + 1])
                          for a, b in zip(months, months[1:]))
        targets = plan.targets(values, bills)
        held = {p.security_id: p.quantity for p in context.positions}
        requests, records = [], []
        for asset in plan.universe:
            target = targets.get(asset)
            weight = target.weight if target else ZERO
            fraction, quantity = weight * plan.invested_fraction, held.get(asset, ZERO)
            action, requested, shares, extra = rebalance_order(
                context.equity, fraction, data[asset].get("raw_close"), quantity,
                data[asset].get("average_volume"), plan.max_volume_participation, self.execution)
            rank = target.rank if target else None
            if action in ("buy", "sell"):
                requests.append(OrderRequest(asset, action, requested, rank or 0, f"{plan.name}:rebalance_{action}"))
            reasons = checks[asset] + (target.reasons if target else ()) + extra
            records.append(SignalDecision(
                context.as_of, asset, plan.name, asset in values, bool(target and target.qualifies), weight > 0,
                target.score if target else None, rank, fraction, quantity, shares, action, requested,
                reasons or ("not_selected",), tuple(data[asset].items()) + (target.features if target else ())))
        return OrderBatch(tuple(requests), tuple(records))


def build_plan(snapshot, plan, start=None, execution=None, cash_rates=None):
    """Bind a plan to a snapshot's calendar and registry; the start defaults to the first session."""
    registry = {s.security_id: s for s in snapshot.securities}
    if any(asset not in registry for asset in plan.universe):
        raise ValueError("Plan contains unknown security IDs")
    return MonthlyPlan(plan, snapshot.sessions, tuple(registry[a] for a in plan.universe),
                       start or snapshot.sessions[0], execution if execution is not None else ExecutionProfile(),
                       cash_rates)
