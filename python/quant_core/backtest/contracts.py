"""Immutable inputs, audit records, and results for the reference simulator."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from quant_core.data import DataMetadata, identity, number, session
from quant_core.data.quality import QualityIssue
from quant_core.data.rates import CashRateSeries
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.portfolio import PositionValue, Receivable
from quant_core.provenance import content_hash
from quant_core.risk import RiskDecision, RiskPolicy


@dataclass(frozen=True)
class RunConfig:
    initial_cash: Decimal = Decimal("100000")
    execution: ExecutionProfile = field(default_factory=ExecutionProfile)
    universe: tuple[str, ...] = ()  # Empty selects the complete explicit registry.
    start: date | None = None
    end: date | None = None
    data_policy: str = "strict"
    actions_policy: str = "require_complete"
    risk: RiskPolicy | None = None
    execution_delay_sessions: int = 1
    strict_discontinuities: bool = False
    cash_rates: CashRateSeries | None = None  # None: idle cash earns nothing.
    references: tuple[str, ...] = ()  # Registry securities a source may read but never trade.

    def __post_init__(self):
        object.__setattr__(self, "initial_cash", number(self.initial_cash))
        if self.initial_cash <= 0 or not isinstance(self.execution, ExecutionProfile):
            raise ValueError("Positive initial capital and ExecutionProfile are required")
        universe = tuple(self.universe)
        for asset in universe:
            identity(asset)
        if len(set(universe)) != len(universe):
            raise ValueError("Duplicate universe security")
        object.__setattr__(self, "universe", tuple(sorted(universe)))
        references = tuple(self.references)
        for asset in references:
            identity(asset)
        if len(set(references)) != len(references):
            raise ValueError("Duplicate reference security")
        object.__setattr__(self, "references", tuple(sorted(references)))
        for day in (self.start, self.end):
            if day is not None:
                session(day)
        if self.start and self.end and self.start > self.end:
            raise ValueError("Start must not follow end")
        if self.data_policy not in ("strict", "allow_missing_unheld_diagnostic"):
            raise ValueError("Unsupported data policy")
        if self.actions_policy not in ("require_complete", "allow_incomplete_diagnostic"):
            raise ValueError("Unsupported corporate-action policy")
        if self.risk is not None and not isinstance(self.risk, RiskPolicy):
            raise ValueError("Risk controls require RiskPolicy")
        if type(self.execution_delay_sessions) is not int or self.execution_delay_sessions not in (1, 2):
            raise ValueError("Execution delay must be one or two sessions")
        if self.risk is not None and self.execution_delay_sessions != 1:
            raise ValueError("Delayed execution diagnostic currently requires risk=None")
        if type(self.strict_discontinuities) is not bool:
            raise ValueError("strict_discontinuities must be an explicit boolean")
        if self.cash_rates is not None and not isinstance(self.cash_rates, CashRateSeries):
            raise ValueError("Cash yield requires CashRateSeries")


@dataclass(frozen=True)
class SourceSpec:
    name: str
    version: str
    artifact_hash: str
    purpose: str = "engineering_fixture"

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in (self.name, self.version, self.purpose)):
            raise ValueError("Order source requires name, version, and purpose")
        if (not isinstance(self.artifact_hash, str) or len(self.artifact_hash) != 64
                or any(c not in "0123456789abcdef" for c in self.artifact_hash)):
            raise ValueError("Order source requires a SHA-256 artifact hash")


@dataclass(frozen=True)
class SignalDecision:
    session: date
    security_id: str
    strategy: str
    eligible: bool
    qualifies: bool
    selected: bool
    score: Decimal | None
    rank: int | None
    target_fraction: Decimal | None
    held_quantity: Decimal
    target_quantity: Decimal | None
    action: str
    requested_quantity: Decimal
    reason_codes: tuple[str, ...]
    features: tuple[tuple[str, Decimal | None], ...] = ()

    def __post_init__(self):
        session(self.session)
        identity(self.security_id)
        identity(self.strategy)
        if any(type(v) is not bool for v in (self.eligible, self.qualifies, self.selected)):
            raise ValueError("Signal eligibility/qualification/selection require booleans")
        if self.qualifies and not self.eligible or self.selected and not self.qualifies:
            raise ValueError("Selection requires qualification and eligibility")
        if self.rank is not None and (type(self.rank) is not int or self.rank <= 0):
            raise ValueError("Signal rank must be a positive integer")
        for name in ("score", "target_fraction", "held_quantity", "target_quantity", "requested_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, number(value))
        if ((self.target_fraction is not None and not 0 <= self.target_fraction <= 1)
                or min(self.held_quantity, self.requested_quantity) < 0):
            raise ValueError("Invalid signal allocation/quantities")
        if self.target_quantity is not None and self.target_quantity < 0:
            raise ValueError("Signal target cannot be negative")
        if self.action not in ("buy", "sell", "hold", "skip", "entry_intent"):
            raise ValueError("Unsupported signal action")
        reasons = tuple(self.reason_codes)
        for reason in reasons:
            identity(reason)
        if not reasons:
            raise ValueError("Signal decision requires reasons")
        object.__setattr__(self, "reason_codes", reasons)
        features = tuple((name, number(value) if value is not None else None) for name, value in self.features)
        for name, _ in features:
            identity(name)
        if len({name for name, _ in features}) != len(features):
            raise ValueError("Duplicate signal feature")
        object.__setattr__(self, "features", tuple(sorted(features)))


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    signal_date: date
    eligible_date: date | None
    processed_date: date | None
    request: OrderRequest
    adjusted_quantity: Decimal
    status: str
    reason_code: str
    fill_id: str | None = None
    adjusted_stop_price: Decimal | None = None


@dataclass(frozen=True)
class FillRecord:
    fill_id: str
    order_id: str
    signal_date: date
    execution_date: date
    security_id: str
    symbol: str
    side: str
    quantity: Decimal
    raw_open: Decimal
    price: Decimal
    notional: Decimal
    fees: Decimal
    slippage: Decimal
    realized_pnl: Decimal | None
    cash_after: Decimal
    position_quantity_after: Decimal
    execution_kind: str = "market_open"
    trigger_price: Decimal | None = None
    raw_execution_price: Decimal | None = None


@dataclass(frozen=True)
class CashMovement:
    sequence: int
    session: date
    kind: str
    security_id: str | None
    amount: Decimal
    cash_after: Decimal
    order_id: str | None = None


@dataclass(frozen=True)
class CorporateActionRecord:
    sequence: int
    session: date
    kind: str
    security_id: str
    quantity: Decimal
    amount: Decimal
    ratio: Decimal | None = None
    pay_date: date | None = None
    realized_pnl: Decimal | None = None


@dataclass(frozen=True)
class DailyState:
    session: date
    cash: Decimal
    receivables: Decimal
    market_value: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    dividend_income: Decimal
    fees: Decimal
    slippage: Decimal
    session_return: Decimal | None
    drawdown: Decimal  # Positive fraction below the initial-capital-inclusive peak.
    positions: tuple[PositionValue, ...]
    interest_income: Decimal = Decimal(0)  # Cumulative idle-cash interest.


@dataclass(frozen=True)
class RunManifest:
    schema_version: int
    engine_version: str
    python_version: str
    engine_hash: str
    dataset_hash: str
    config_hash: str
    source: SourceSpec
    data: DataMetadata
    config: RunConfig
    quality_issues: tuple[QualityIssue, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class RunSummary:
    initial_cash: Decimal
    final_equity: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    fill_count: int
    rejected_order_count: int
    expired_order_count: int
    fees: Decimal
    slippage: Decimal


@dataclass(frozen=True)
class BacktestResult:
    manifest: RunManifest
    orders: tuple[OrderRecord, ...]
    fills: tuple[FillRecord, ...]
    cash_movements: tuple[CashMovement, ...]
    corporate_actions: tuple[CorporateActionRecord, ...]
    equity: tuple[DailyState, ...]
    outstanding_receivables: tuple[Receivable, ...]
    summary: RunSummary
    risk_decisions: tuple[RiskDecision, ...] = ()
    signal_decisions: tuple[SignalDecision, ...] = ()

    @property
    def result_hash(self):
        return content_hash(self)
