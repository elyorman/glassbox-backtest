"""Frozen campaign budgets, qualification evidence, and nomination criteria."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from quant_core.data import identity, number
from quant_core.provenance import content_hash
from quant_core.strategies import BENCHMARKS, StrategyConfig
from quant_core.validation.temporal import Period

CAPABILITIES = ("research_usage_rights", "exchange_calendar", "raw_prices_and_open_convention",
                "split_and_dividend_coverage", "dividend_payment_dates", "security_identity",
                "universe_history_or_fixed_sample_disclosure", "delisting_treatment")


def digest(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Expected SHA-256 hex digest")


@dataclass(frozen=True)
class Capability:
    name: str
    status: str
    evidence: str

    def __post_init__(self):
        if self.name not in CAPABILITIES or self.status not in ("passed", "unresolved", "failed"):
            raise ValueError("Unknown capability/status")
        identity(self.evidence)


@dataclass(frozen=True)
class Qualification:
    dataset_hash: str
    scope: str
    reviewer: str
    reviewed_on: date
    capabilities: tuple[Capability, ...]
    limitations: tuple[str, ...]
    independent_from: str | None = None
    independence_evidence: str | None = None

    def __post_init__(self):
        digest(self.dataset_hash)
        if self.scope not in ("engineering_fixture", "exploratory_fixed_sample", "independent_retest_fixed_sample"):
            raise ValueError("Unsupported qualification scope; historical stock-universe scope is not implemented")
        identity(self.reviewer)
        if type(self.reviewed_on) is not date:
            raise ValueError("Review date required")
        caps, limits = tuple(self.capabilities), tuple(self.limitations)
        if any(not isinstance(c, Capability) for c in caps) or {c.name for c in caps} != set(CAPABILITIES) or len(caps) != len(CAPABILITIES):
            raise ValueError("Exactly one evidence record per required capability")
        if not limits:
            raise ValueError("Disclose limitations explicitly, including fixed surviving sample and execution approximation")
        for limitation in limits:
            identity(limitation)
        object.__setattr__(self, "capabilities", tuple(sorted(caps, key=lambda c: c.name)))
        object.__setattr__(self, "limitations", limits)
        if self.scope == "independent_retest_fixed_sample":
            digest(self.independent_from)
            identity(self.independence_evidence)
        elif self.independent_from is not None or self.independence_evidence is not None:
            raise ValueError("Independence fields require independent-retest scope")

    @property
    def passed(self):
        return all(c.status == "passed" for c in self.capabilities)


@dataclass(frozen=True)
class Criteria:
    max_drawdown: Decimal = Decimal("0.25")
    family_positive_fraction: Decimal = Decimal("0.50")
    removed_winner_sessions: int = 5
    minimum_sessions: int = 252
    minimum_defined_bootstrap_fraction: Decimal = Decimal("0.95")
    max_search_p_value: Decimal = Decimal("0.05")
    max_cross_provider_return_difference: Decimal = Decimal("0.05")
    max_cross_provider_daily_difference: Decimal = Decimal("0.005")

    def __post_init__(self):
        for name in ("max_drawdown", "family_positive_fraction", "minimum_defined_bootstrap_fraction",
                     "max_search_p_value",
                     "max_cross_provider_return_difference", "max_cross_provider_daily_difference"):
            object.__setattr__(self, name, number(getattr(self, name)))
            if not 0 < getattr(self, name) <= 1:
                raise ValueError("Criteria fractions must be in (0, 1]")
        for name in ("removed_winner_sessions", "minimum_sessions"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError("Criteria session counts must be positive integers")


@dataclass(frozen=True)
class CampaignSpec:
    name: str
    hypothesis: str
    dataset_hash: str
    candidates: tuple[StrategyConfig, ...]
    benchmarks: tuple[StrategyConfig, ...]
    development_folds: tuple[Period, ...]
    selection: Period
    holdout: Period
    criteria: Criteria = field(default_factory=Criteria)
    initial_cash: Decimal = Decimal("100000")
    costs_bps: tuple[Decimal, ...] = (Decimal(5), Decimal(10), Decimal(25))
    primary_cost_bps: Decimal = Decimal(10)
    stressed_cost_bps: Decimal = Decimal(25)
    bootstrap_blocks: tuple[int, ...] = (5, 20, 60)
    bootstrap_repetitions: int = 500
    seed: int = 1729
    purpose: str = "exploratory_research"
    prior_holdout_use: str = "unexposed"
    prior_holdout_disclosure: str = "No known strategy-performance use of the locked period"

    def __post_init__(self):
        identity(self.name)
        identity(self.hypothesis)
        digest(self.dataset_hash)
        if self.purpose not in ("engineering_fixture", "exploratory_research"):
            raise ValueError("Unsupported campaign purpose")
        if self.prior_holdout_use not in ("unexposed", "exposed", "unknown"):
            raise ValueError("Explicit prior holdout-use declaration required")
        identity(self.prior_holdout_disclosure)
        candidates, benchmarks, folds = tuple(self.candidates), tuple(self.benchmarks), tuple(self.development_folds)
        if not candidates or any(not isinstance(c, StrategyConfig) or c.family in BENCHMARKS for c in candidates):
            raise ValueError("Need rule-based candidate configurations")
        if any(not isinstance(b, StrategyConfig) for b in benchmarks):
            raise ValueError("Benchmarks require StrategyConfig")
        if self.purpose == "exploratory_research" and any(c.purpose != "research_candidate" for c in candidates):
            raise ValueError("Empirical candidates must declare research_candidate purpose")
        if any(c.profile != "scheduled_slots" for c in candidates + benchmarks):
            raise ValueError("Initial campaign supports scheduled-slots baselines; risk ablations need a new protocol")
        if len({c.name for c in candidates + benchmarks}) != len(candidates + benchmarks):
            raise ValueError("Recipe names must be unique")
        if len({c.universe for c in candidates}) != 1:
            raise ValueError("Candidates require the same frozen universe")
        names = {b.name: b for b in benchmarks}
        required = {"broad_market_buy_hold", "broad_market_buy_hold_reserve", "same_universe_equal_weight", "cash_control"}
        if set(names) != required:
            raise ValueError("Exactly the four registered benchmark references are required")
        if (names["same_universe_equal_weight"].family != "equal_weight"
                or names["same_universe_equal_weight"].universe != candidates[0].universe
                or names["cash_control"].family != "cash"
                or names["cash_control"].universe != candidates[0].universe
                or names["broad_market_buy_hold"].family != "buy_hold"
                or names["broad_market_buy_hold_reserve"].family != "buy_hold"
                or names["broad_market_buy_hold"].universe != names["broad_market_buy_hold_reserve"].universe
                or names["broad_market_buy_hold"].invested_fraction != 1
                or names["broad_market_buy_hold_reserve"].invested_fraction != Decimal("0.95")):
            raise ValueError("Benchmark roles/allocations must match the registered references")
        if not folds or any(not isinstance(p, Period) for p in folds + (self.selection, self.holdout)):
            raise ValueError("Need development folds, selection and locked holdout")
        periods = folds + (self.selection, self.holdout)
        if len({p.name for p in periods}) != len(periods) or any(a.end >= b.start for a, b in zip(periods, periods[1:])):
            raise ValueError("Periods must be uniquely named, disjoint and chronological")
        if not isinstance(self.criteria, Criteria):
            raise ValueError("Need frozen Criteria")
        for name, value in (("initial_cash", self.initial_cash), ("primary_cost_bps", self.primary_cost_bps),
                            ("stressed_cost_bps", self.stressed_cost_bps)):
            object.__setattr__(self, name, number(value))
        costs = tuple(sorted(set(map(number, self.costs_bps))))
        if self.initial_cash <= 0 or not costs or min(costs) <= 0 or max(costs) >= 10000:
            raise ValueError("Positive capital and nonzero cost ladder required")
        if self.primary_cost_bps not in costs or self.stressed_cost_bps not in costs or self.stressed_cost_bps <= self.primary_cost_bps:
            raise ValueError("Primary/stressed costs must be registered with stress > primary")
        blocks = tuple(sorted(set(self.bootstrap_blocks)))
        if not blocks or any(type(b) is not int or b < 1 for b in blocks):
            raise ValueError("Positive integer bootstrap block lengths required")
        if type(self.bootstrap_repetitions) is not int or self.bootstrap_repetitions < 100:
            raise ValueError("At least 100 bootstrap repetitions")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("Seed must be a nonnegative integer")
        for name, value in (("candidates", candidates), ("benchmarks", benchmarks), ("development_folds", folds),
                            ("costs_bps", costs), ("bootstrap_blocks", blocks)):
            object.__setattr__(self, name, value)

    @property
    def campaign_hash(self):
        return content_hash(self)


def _period(row):
    return Period(**dict(row, start=date.fromisoformat(row["start"]), end=date.fromisoformat(row["end"])))


def parse_spec(values):
    row = dict(values)
    row["candidates"] = tuple(StrategyConfig(**c) for c in row["candidates"])
    row["benchmarks"] = tuple(StrategyConfig(**c) for c in row["benchmarks"])
    row["development_folds"] = tuple(_period(p) for p in row["development_folds"])
    for name in ("selection", "holdout"):
        row[name] = _period(row[name])
    if "criteria" in row:
        row["criteria"] = Criteria(**row["criteria"])
    return CampaignSpec(**row)


def parse_qualification(values):
    row = dict(values)
    row["reviewed_on"] = date.fromisoformat(row["reviewed_on"])
    row["capabilities"] = tuple(Capability(**c) for c in row["capabilities"])
    return Qualification(**row)


def load_document(path, key, parser):
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
        if set(envelope) != {"schema_version", key} or type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
            raise ValueError("Unsupported document schema")
        return parser(envelope[key])
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed {key}: {exc}") from exc
