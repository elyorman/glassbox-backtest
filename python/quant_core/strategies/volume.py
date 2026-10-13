"""Explicit monthly dollar-volume ranking using shared portfolio contracts."""
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from quant_core.backtest.contracts import SignalDecision, SourceSpec
from quant_core.backtest.sources import OrderBatch
from quant_core.data import Security, identity, number, session
from quant_core.data.adjustments import adjusted_quantity
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.features.volume import dollar_volume_percentile
from quant_core.provenance import content_hash
from quant_core.strategies import RuleStrategy, rebalance_dates, rebalance_order

ZERO = Decimal(0)
POLICY = "raw_close_times_contemporaneous_raw_shares_midpoint_percentile_exact_calendar_v1"


@dataclass(frozen=True)
class VolumeConfig:
    name: str
    universe: tuple[str, ...]
    window_sessions: int = 50
    direction: str = "descending"
    top_k: int = 5
    invested_fraction: Decimal = Decimal(".95")
    min_price: Decimal = ZERO
    volume_lookback: int = 20
    min_average_dollar_volume: Decimal = ZERO
    max_volume_participation: Decimal = Decimal(".01")
    purpose: str = "research_candidate"
    family: str = "unusual_dollar_volume"
    profile: str = "scheduled_slots"

    def __post_init__(self):
        identity(self.name)
        identity(self.purpose)
        universe = tuple(sorted(self.universe))
        if not universe or len(set(universe)) != len(universe):
            raise ValueError("Volume strategy requires unique explicit securities")
        for asset in universe:
            identity(asset)
        object.__setattr__(self, "universe", universe)
        if self.family != "unusual_dollar_volume" or self.profile != "scheduled_slots":
            raise ValueError("Volume strategy supports its explicit family and scheduled slots")
        if self.direction not in ("ascending", "descending"):
            raise ValueError("Volume ranking direction must be ascending or descending")
        for name, minimum in (("window_sessions", 2), ("volume_lookback", 1), ("top_k", 1)):
            if type(getattr(self, name)) is not int or getattr(self, name) < minimum:
                raise ValueError(f"Invalid {name}")
        for name in ("invested_fraction", "min_price", "min_average_dollar_volume", "max_volume_participation"):
            value = number(getattr(self, name))
            if value < 0:
                raise ValueError(f"Negative {name}")
            object.__setattr__(self, name, value)
        if not 0 < self.invested_fraction <= 1 or not 0 < self.max_volume_participation <= 1:
            raise ValueError("Allocation and participation must be in (0,1]")

    @property
    def required_history(self):
        return max(self.window_sessions, self.volume_lookback)


@dataclass(frozen=True, kw_only=True)
class VolumeSpec(SourceSpec):
    configuration: VolumeConfig
    signal_price_policy: str
    calendar: tuple[date, ...]
    securities: tuple[Security, ...]
    first_signal_session: date
    rebalance_sessions: tuple[date, ...]
    allocation_execution: ExecutionProfile


@dataclass(frozen=True)
class VolumeStrategy:
    configuration: VolumeConfig
    calendar: tuple[date, ...]
    securities: tuple[Security, ...]
    first_signal_session: date
    execution: ExecutionProfile = field(default_factory=ExecutionProfile)
    _spec: VolumeSpec = field(init=False, repr=False, compare=False)

    # These preflight/scheduling methods depend only on the common properties,
    # never on the closed family registry or on price-feature implementation.
    membership = None
    validate_run = RuleStrategy.validate_run
    orders = RuleStrategy.orders

    def __post_init__(self):
        if not isinstance(self.configuration, VolumeConfig) or not isinstance(self.execution, ExecutionProfile):
            raise ValueError("Volume strategy requires VolumeConfig and ExecutionProfile")
        calendar = tuple(self.calendar)
        session(self.first_signal_session)
        rebalances = rebalance_dates(calendar, "month_end")
        if self.first_signal_session not in calendar:
            raise ValueError("First signal must be a bound calendar session")
        securities = tuple(sorted(self.securities, key=lambda s: s.security_id))
        if tuple(s.security_id for s in securities) != self.configuration.universe:
            raise ValueError("Volume registry must match the explicit universe")
        object.__setattr__(self, "calendar", calendar)
        object.__setattr__(self, "securities", securities)
        fields = dict(configuration=self.configuration, signal_price_policy=POLICY,
                      calendar=calendar, securities=securities, first_signal_session=self.first_signal_session,
                      rebalance_sessions=rebalances, allocation_execution=self.execution)
        object.__setattr__(self, "_spec", VolumeSpec(name=self.configuration.name, version="1",
            artifact_hash=content_hash(("volume_strategy_v1", fields)), purpose=self.configuration.purpose, **fields))

    @property
    def spec(self):
        return self._spec

    def evaluate(self, context):
        if context.as_of not in self.calendar:
            raise ValueError("Volume evaluation requires a bound calendar session")
        cfg = self.configuration
        stop = bisect_right(self.calendar, context.as_of)
        completed = self.calendar[:stop]
        expected = completed[-cfg.required_history:]
        registry = {s.security_id: s for s in self.securities}
        held = {p.security_id: p.quantity for p in context.positions}
        features, reasons, scores = {}, {}, {}
        for asset in cfg.universe:
            values, reason = {}, []
            history = context.history(asset, cfg.required_history)
            if not registry[asset].active_on(context.as_of):
                reason.append("outside_security_lifetime")
            elif not history or history[-1].session != context.as_of:
                reason.append("missing_signal_bar")
            elif len(expected) < cfg.required_history or len(history) < cfg.required_history:
                reason.append("insufficient_history")
            elif tuple(b.session for b in history) != expected:
                reason.append("missing_history_session")
            else:
                feature = dollar_volume_percentile(history, completed, cfg.window_sessions)
                # Retain raw input pairs and explicit calendar indices. The saved
                # manifest binds the calendar and snapshot, so each row is resolvable.
                for lag, bar in enumerate(reversed(feature.observations)):
                    values[f"volume_raw_close_lag{lag}"] = bar.close
                    values[f"volume_raw_shares_lag{lag}"] = bar.volume
                    values[f"volume_calendar_ordinal_lag{lag}"] = Decimal(stop - 1 - lag)
                window = history[-cfg.volume_lookback:]
                splits = tuple(s for s in context.splits if s.security_id == asset)
                shares = sum((adjusted_quantity(b.volume, asset, b.session, context.as_of, splits)
                              for b in window), ZERO) / cfg.volume_lookback
                dollars = sum((b.close * b.volume for b in window), ZERO) / cfg.volume_lookback
                values.update(raw_close=history[-1].close, average_volume=shares,
                              average_dollar_volume=dollars, dollar_volume_percentile=feature.score,
                              volume_reference_lower=Decimal(feature.lower_count),
                              volume_reference_equal=Decimal(feature.equal_count),
                              volume_window_sessions=Decimal(cfg.window_sessions))
                if feature.reason:
                    reason.append(feature.reason)
                if history[-1].close < cfg.min_price:
                    reason.append("price_filter")
                if any(b.volume <= 0 for b in window) or shares <= 0 or dollars < cfg.min_average_dollar_volume:
                    reason.append("liquidity_filter")
                if not reason:
                    scores[asset] = feature.score
            features[asset], reasons[asset] = values, reason
        ranked = sorted(scores, key=lambda a: (scores[a] if cfg.direction == "ascending" else -scores[a], a))
        ranks = {asset: rank for rank, asset in enumerate(ranked, 1)}
        chosen = set(ranked[:cfg.top_k])
        fraction = cfg.invested_fraction / cfg.top_k
        decisions, requests = [], []
        for asset in cfg.universe:
            selected = asset in chosen
            quantity = held.get(asset, ZERO)
            target_fraction = fraction if selected else ZERO
            reason = list(reasons[asset])
            reason.append("selected" if selected else "below_selection_cutoff" if asset in ranks else "not_selected")
            action, requested, target, extra = rebalance_order(
                context.equity, target_fraction, features[asset].get("raw_close"), quantity,
                features[asset].get("average_volume"), cfg.max_volume_participation, self.execution)
            reason.extend(extra)
            if action in ("buy", "sell"):
                requests.append(OrderRequest(asset, action, requested, ranks.get(asset, 0), f"{cfg.name}:rebalance_{action}"))
            decisions.append(SignalDecision(context.as_of, asset, cfg.name, not reasons[asset], asset in ranks,
                selected, scores.get(asset), ranks.get(asset), target_fraction, quantity, target,
                action, requested, tuple(reason), tuple(features[asset].items())))
        return OrderBatch(tuple(requests), tuple(decisions))


def build_volume_strategy(snapshot, configuration, start=None, execution=None):
    registry = {s.security_id: s for s in snapshot.securities}
    if not isinstance(configuration, VolumeConfig) or any(a not in registry for a in configuration.universe):
        raise ValueError("Volume configuration contains unknown securities")
    return VolumeStrategy(configuration, snapshot.sessions, tuple(registry[a] for a in configuration.universe),
                          start or snapshot.sessions[0], execution if execution is not None else ExecutionProfile())
