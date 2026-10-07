"""Frozen rule-based research candidates, allocation adapters and benchmarks."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from quant_core.backtest.contracts import SignalDecision, SourceSpec
from quant_core.backtest.sources import OrderBatch
from quant_core.data import Security, Snapshot, identity, number, session
from quant_core.data.adjustments import adjusted_quantity
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.features import PRICE_POLICY, nearness_to_high, signal_prices, trailing_mean, trailing_return, realized_volatility
from quant_core.provenance import canonical_json, content_hash
from quant_core.sizing import EntryIntent, allocation_shares, floor_shares
from quant_core.universes import DatedUniverse

ZERO, ONE = Decimal("0"), Decimal("1")
FAMILIES = ("trend", "momentum", "nearness_high", "reversal", "low_vol", "equal_weight", "buy_hold", "cash")
BENCHMARKS = ("equal_weight", "buy_hold", "cash")


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    family: str
    universe: tuple[str, ...]
    profile: str = "scheduled_slots"
    mean_window: int = 200
    momentum_lookback: int = 252
    momentum_skip: int = 21
    high_window: int = 252
    reversal_window: int = 5
    volatility_window: int = 126
    top_k: int = 3
    invested_fraction: Decimal = Decimal("0.95")
    min_price: Decimal = ZERO
    volume_lookback: int = 20
    min_average_dollar_volume: Decimal = ZERO
    max_volume_participation: Decimal = Decimal("0.01")
    risk_fraction: Decimal = Decimal("0.005")
    atr_period: int = 14
    atr_multiple: Decimal = Decimal("2")
    purpose: str = "research_candidate"

    def __post_init__(self):
        identity(self.name)
        if self.family not in FAMILIES or self.profile not in ("scheduled_slots", "atr_protected"):
            raise ValueError("Unsupported strategy family/profile")
        universe = tuple(self.universe)
        for asset in universe:
            identity(asset)
        if not universe or len(set(universe)) != len(universe):
            raise ValueError("Strategy requires a nonempty unique explicit universe")
        object.__setattr__(self, "universe", tuple(sorted(universe)))
        for name in ("mean_window", "momentum_lookback", "high_window", "reversal_window", "volatility_window",
                     "top_k", "volume_lookback", "atr_period"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.momentum_skip) is not int or not 0 <= self.momentum_skip < self.momentum_lookback:
            raise ValueError("Momentum skip must be in [0, lookback)")
        for name in ("invested_fraction", "min_price", "min_average_dollar_volume",
                     "max_volume_participation", "risk_fraction", "atr_multiple"):
            object.__setattr__(self, name, number(getattr(self, name)))
        if not 0 < self.invested_fraction <= 1 or min(self.min_price, self.min_average_dollar_volume) < 0:
            raise ValueError("Invalid strategy allocation/eligibility threshold")
        if not 0 < self.max_volume_participation <= 1 or not 0 < self.risk_fraction <= 1 or self.atr_multiple <= 0:
            raise ValueError("Invalid strategy liquidity/protected sizing parameters")
        if self.purpose not in ("research_candidate", "benchmark", "engineering_fixture"):
            raise ValueError("Unsupported strategy purpose")
        if self.family in BENCHMARKS and self.profile != "scheduled_slots":
            raise ValueError("Registered benchmarks require the scheduled-slots profile")
        if self.family == "buy_hold" and len(self.universe) != 1:
            raise ValueError("Buy-and-hold benchmark requires one explicit security")

    @property
    def required_history(self):
        required = {"trend": self.mean_window, "momentum": self.momentum_lookback + 1,
                    "nearness_high": self.high_window,
                    "low_vol": self.volatility_window + 1,
                    "reversal": max(self.mean_window, self.reversal_window + 1)}.get(self.family, 1)
        return max(required, self.volume_lookback)


def rebalance_dates(calendar, frequency):
    """Predeclared exchange sessions, including next-period evidence; no price access."""
    calendar = tuple(calendar)
    if frequency not in ("month_end", "week_end"):
        raise ValueError("Unsupported rebalance frequency")
    if any(type(d) is not date for d in calendar) or any(a >= b for a, b in zip(calendar, calendar[1:])):
        raise ValueError("Rebalance calendar requires unique increasing dates")
    key = (lambda d: (d.year, d.month)) if frequency == "month_end" else (lambda d: d.isocalendar()[:2])
    # A truncated final period is not silently treated as a completed rebalance.
    return tuple(previous for previous, following in zip(calendar, calendar[1:]) if key(previous) != key(following))


@dataclass(frozen=True, kw_only=True)
class StrategySpec(SourceSpec):
    configuration: StrategyConfig
    signal_price_policy: str
    calendar: tuple[date, ...]
    first_signal_session: date
    rebalance_sessions: tuple[date, ...]
    allocation_execution: ExecutionProfile


@dataclass(frozen=True, kw_only=True)
class DatedStrategySpec(StrategySpec):
    membership: DatedUniverse


@dataclass(frozen=True)
class RuleStrategy:
    configuration: StrategyConfig
    calendar: tuple[date, ...]
    securities: tuple[Security, ...]
    first_signal_session: date
    execution: ExecutionProfile = field(default_factory=ExecutionProfile)
    membership: DatedUniverse | None = None
    _spec: StrategySpec = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.configuration, StrategyConfig):
            raise ValueError("Rule strategy requires StrategyConfig")
        if not isinstance(self.execution, ExecutionProfile):
            raise ValueError("Rule strategy requires an allocation execution profile")
        if self.membership is not None:
            if not isinstance(self.membership, DatedUniverse):
                raise ValueError("Strategy membership requires DatedUniverse")
            if not set(self.membership.security_ids) <= set(self.configuration.universe):
                raise ValueError("Dated universe contains a security outside the strategy universe")
            if self.configuration.family in ("buy_hold", "cash"):
                raise ValueError("Static buy-hold/cash references do not use dated membership")
        calendar = tuple(self.calendar)
        session(self.first_signal_session)
        if self.first_signal_session not in calendar:
            raise ValueError("First signal session is outside the supplied calendar")
        frequency = "week_end" if self.configuration.family == "reversal" else "month_end"
        rebalances = rebalance_dates(calendar, frequency)
        securities = tuple(sorted(self.securities, key=lambda s: s.security_id))
        if {s.security_id for s in securities} != set(self.configuration.universe) or len(securities) != len(self.configuration.universe):
            raise ValueError("Strategy registry must match the explicit strategy universe")
        object.__setattr__(self, "calendar", calendar)
        object.__setattr__(self, "securities", securities)
        if self.configuration.family in ("buy_hold", "cash"):
            rebalances = (self.first_signal_session,)
        digest = content_hash(("rule_strategy_v1", PRICE_POLICY, self.configuration, calendar,
                               securities, self.first_signal_session, rebalances, self.execution))
        spec_class = DatedStrategySpec if self.membership is not None else StrategySpec
        if self.membership is not None:
            digest = content_hash((digest, "dated_universe_v1", self.membership.to_dict()))
        object.__setattr__(self, "_spec", spec_class(
            name=self.configuration.name, version="2" if self.membership is not None else "1", artifact_hash=digest,
            purpose=self.configuration.purpose, configuration=self.configuration,
            signal_price_policy=PRICE_POLICY, calendar=calendar,
            first_signal_session=self.first_signal_session, rebalance_sessions=rebalances,
            allocation_execution=self.execution,
            **({"membership": self.membership} if self.membership is not None else {})))

    @property
    def spec(self):
        return self._spec

    def validate_run(self, snapshot, run_config):
        """Optional source preflight hook; never reads outcomes or changes configuration."""
        if tuple(snapshot.sessions) != self.calendar or run_config.start != self.first_signal_session:
            raise ValueError("Strategy calendar/start must match its frozen run binding")
        registry = {s.security_id: s for s in snapshot.securities}
        if any(registry.get(s.security_id) != s for s in self.securities):
            raise ValueError("Strategy security registry disagrees with the dataset")
        if not set(self.configuration.universe) <= set(run_config.universe):
            raise ValueError("Strategy universe is outside the run universe")
        if self.execution != run_config.execution:
            raise ValueError("Strategy allocation costs must match the frozen execution profile")
        if self.membership is not None:
            if self.membership.coverage_start > run_config.start or self.membership.coverage_end < run_config.end:
                raise ValueError("Dated universe coverage does not cover the run")
            for day in self.spec.rebalance_sessions:
                if run_config.start <= day <= run_config.end:
                    self.membership.members_on(day)
        if not snapshot.metadata.actions_complete and run_config.actions_policy != "allow_incomplete_diagnostic":
            raise ValueError("Total-return strategy signals require declared complete corporate actions")
        protected = self.configuration.profile == "atr_protected"
        if protected != (run_config.risk is not None):
            raise ValueError("ATR-protected strategies require risk; scheduled-slots baselines require risk=None")

    def orders(self, context):
        if context.as_of not in self.spec.rebalance_sessions or context.as_of < self.first_signal_session:
            return OrderBatch((), ())
        return self.evaluate(context)

    def evaluate(self, context):
        """Project a rebalance using this completed session; scheduling stays in orders()."""
        if context.as_of not in self.calendar:
            raise ValueError("Strategy evaluation requires a bound calendar session")
        cfg = self.configuration
        members = set(self.membership.members_on(context.as_of)) if self.membership is not None else set(cfg.universe)
        splits_by_asset, dividends_by_asset = defaultdict(list), defaultdict(list)
        for event in context.splits:
            splits_by_asset[event.security_id].append(event)
        for event in context.dividends:
            dividends_by_asset[event.security_id].append(event)
        held = {p.security_id: p.quantity for p in context.positions}
        features, reasons, scores, qualified = {}, {}, {}, []
        registry = {s.security_id: s for s in self.securities}
        calendar_stop = bisect_right(self.calendar, context.as_of)
        expected = self.calendar[max(0, calendar_stop - cfg.required_history):calendar_stop]
        for asset in cfg.universe:
            reason = []
            values = {}
            history = context.history(asset, cfg.required_history)
            if asset not in members:
                reason.append("outside_dated_universe")
            elif not registry[asset].active_on(context.as_of):
                reason.append("outside_security_lifetime")
            elif not history or history[-1].session != context.as_of:
                reason.append("missing_signal_bar")
            elif len(history) < cfg.required_history:
                reason.append("insufficient_history")
            elif tuple(b.session for b in history) != expected:
                reason.append("missing_history_session")
            else:
                price = history[-1].close
                splits = splits_by_asset[asset]
                window = history[-cfg.volume_lookback:]
                volume = sum((adjusted_quantity(b.volume, asset, b.session, context.as_of, splits)
                              for b in window), ZERO) / cfg.volume_lookback
                dollars = sum((b.close * b.volume for b in window), ZERO) / cfg.volume_lookback
                values.update(raw_close=price, average_volume=volume, average_dollar_volume=dollars)
                if price < cfg.min_price:
                    reason.append("price_filter")
                if volume <= 0 or dollars < cfg.min_average_dollar_volume:
                    reason.append("liquidity_filter")
                if not reason:
                    prices = signal_prices(history, splits, dividends_by_asset[asset])
                    values["signal_index"] = prices[-1]
                    family = cfg.family
                    if family in ("trend", "reversal"):
                        mean = trailing_mean(prices, cfg.mean_window)
                        values["signal_mean"] = mean
                        values["trend_distance"] = prices[-1] / mean - ONE
                    score = (values["trend_distance"] if family == "trend" else
                             trailing_return(prices, cfg.momentum_lookback, cfg.momentum_skip) if family == "momentum" else
                             nearness_to_high(prices, cfg.high_window) if family == "nearness_high" else
                             trailing_return(prices, cfg.reversal_window) if family == "reversal" else ZERO)
                    if family == "low_vol":
                        score = realized_volatility(prices, cfg.volatility_window)
                        values["realized_volatility_population_daily"] = score
                    scores[asset] = score
                    if family in ("trend", "reversal") and values["trend_distance"] <= 0:
                        reason.append("trend_condition_failed")
                    elif family == "cash":
                        reason.append("cash_benchmark")
                    else:
                        qualified.append(asset)
            features[asset], reasons[asset] = values, reason
        ascending = cfg.family in ("reversal", "low_vol")
        ranked = sorted(qualified, key=lambda a: (scores[a] if ascending else -scores[a], a))
        ranks = {asset: rank for rank, asset in enumerate(ranked, 1)}
        ranked_family = cfg.family in ("momentum", "nearness_high", "reversal", "low_vol")
        chosen = set(ranked[:cfg.top_k] if ranked_family else ranked)
        slots = cfg.top_k if ranked_family else len(members)
        slot_fraction = cfg.invested_fraction / slots if slots else ZERO
        requests, decisions = [], []
        for asset in cfg.universe:
            selected = asset in chosen
            eligible = not any(code not in ("trend_condition_failed", "cash_benchmark") for code in reasons[asset])
            qualifies = asset in ranks
            quantity = held.get(asset, ZERO)
            target_fraction = slot_fraction if selected else ZERO
            priority = ranks.get(asset, 0)
            reason = list(reasons[asset])
            action, requested, target = "skip", ZERO, None
            if selected:
                reason.append("selected")
            elif qualifies:
                reason.append("below_selection_cutoff")
            if cfg.profile == "atr_protected":
                if quantity and not selected:
                    action, requested = "sell", quantity
                elif selected and not quantity:
                    action = "entry_intent"
                    requests.append(EntryIntent(asset, "atr", risk_fraction=cfg.risk_fraction,
                                                atr_period=cfg.atr_period, atr_multiple=cfg.atr_multiple,
                                                priority=priority, reason=f"{cfg.name}:selected"))
                elif selected:
                    action = "hold"
            else:
                price = features[asset].get("raw_close")
                target = allocation_shares(context.equity, target_fraction, price, self.execution) if selected else ZERO
                delta = target - quantity
                if delta < 0:
                    action, requested = "sell", -delta
                elif delta > 0:
                    volume_limit = floor_shares(features[asset]["average_volume"] * cfg.max_volume_participation)
                    whole_delta = floor_shares(delta)
                    if whole_delta < delta:
                        reason.append("whole_share_buy_rounding")
                    requested = min(whole_delta, volume_limit)
                    if requested < whole_delta:
                        reason.append("entry_participation_cap")
                    action = "buy" if requested else "skip"
                elif selected:
                    action = "hold"
            if action in ("buy", "sell"):
                requests.append(OrderRequest(asset, action, requested, priority,
                                             f"{cfg.name}:rebalance_{action}"))
            if selected and action == "skip":
                reason.append("below_one_share")
            decisions.append(SignalDecision(
                context.as_of, asset, cfg.name, eligible, qualifies, selected, scores.get(asset),
                ranks.get(asset), target_fraction if cfg.profile == "scheduled_slots" else None,
                quantity, target, action, requested,
                tuple(reason) or ("not_selected",), tuple(features[asset].items())))
        return OrderBatch(tuple(requests), tuple(decisions))


def build_strategy(snapshot: Snapshot, configuration: StrategyConfig, start=None, execution=None, *, membership=None):
    registry = {s.security_id: s for s in snapshot.securities}
    if any(asset not in registry for asset in configuration.universe):
        raise ValueError("Strategy contains unknown security IDs")
    return RuleStrategy(configuration, snapshot.sessions,
                        tuple(registry[a] for a in configuration.universe), start or snapshot.sessions[0],
                        execution if execution is not None else ExecutionProfile(), membership)


def load_config(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if set(payload) != {"schema_version", "configuration"} or type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("Unsupported strategy configuration schema")
        return StrategyConfig(**payload["configuration"])
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f"Malformed strategy configuration: {exc}") from exc


def initial_recipes(universe):
    """The ten proposed research recipes; no results or optimization in this registry."""
    records = []
    for window in (100, 200):
        records.append(StrategyConfig(f"trend_sma_{window}", "trend", universe, mean_window=window))
    for lookback in (126, 252):
        for count in (3, 5):
            records.append(StrategyConfig(f"momentum_{lookback}_skip21_top{count}", "momentum", universe,
                                           momentum_lookback=lookback, top_k=count))
    for count in (3, 5):
        records.append(StrategyConfig(f"high252_top{count}", "nearness_high", universe, top_k=count))
    for window in (3, 5):
        records.append(StrategyConfig(f"reversal_{window}_sma200_top3", "reversal", universe, reversal_window=window))
    return tuple(records)


def benchmark_recipes(universe, benchmark_id):
    return (StrategyConfig("broad_market_buy_hold", "buy_hold", (benchmark_id,), invested_fraction="1", purpose="benchmark"),
            StrategyConfig("broad_market_buy_hold_reserve", "buy_hold", (benchmark_id,), invested_fraction="0.95", purpose="benchmark"),
            StrategyConfig("same_universe_equal_weight", "equal_weight", universe, purpose="benchmark"),
            StrategyConfig("cash_control", "cash", universe, purpose="benchmark"))


def save_recipe_registry(universe, benchmark_id, directory: Path):
    recipes = initial_recipes(tuple(universe)) + benchmark_recipes(tuple(universe), benchmark_id)
    directory.mkdir(parents=True, exist_ok=False)
    entries = []
    for recipe in recipes:
        filename = recipe.name + ".json"
        (directory / filename).write_text(canonical_json({"schema_version": 1, "configuration": recipe}) + "\n", encoding="utf-8")
        entries.append({"name": recipe.name, "file": filename, "configuration_hash": content_hash(recipe)})
    (directory / "REGISTRY.json").write_text(canonical_json({
        "schema_version": 1, "purpose": "proposed_recipes_no_performance_runs",
        "signal_price_policy": PRICE_POLICY, "recipes": entries,
        "registry_hash": content_hash(entries)}) + "\n", encoding="utf-8")
