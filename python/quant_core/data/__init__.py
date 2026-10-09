"""Immutable raw-price snapshots; adapters are outside the simulation."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext

from quant_core.provenance import content_hash


def number(value) -> Decimal:
    """Parse exact decimal inputs; binary floats are deliberately rejected."""
    if isinstance(value, (float, bool)):
        raise ValueError("Use Decimal, integer, or decimal strings; not float/bool")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("Decimal values must be finite")
    return result


def session(value):
    if type(value) is not date:
        raise ValueError("Sessions must be datetime.date values")


def identity(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("security_id must be a nonempty stable identifier")


@dataclass(frozen=True)
class Bar:
    security_id: str
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self):
        identity(self.security_id)
        session(self.session)
        for name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, name, number(getattr(self, name)))
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("Prices must be positive")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Invalid OHLC relationship")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")


@dataclass(frozen=True)
class Split:
    security_id: str
    session: date
    ratio: Decimal | None = None  # Legacy scalar; repeating ratios are approximate.
    new_shares: int | None = None  # Original exact new/old counts, when supplied.
    old_shares: int | None = None

    def __post_init__(self):
        identity(self.security_id)
        session(self.session)
        if self.new_shares is not None or self.old_shares is not None:
            if any(type(v) is not int or v <= 0 for v in (self.new_shares, self.old_shares)):
                raise ValueError("Exact split counts must both be positive integers")
            with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
                ratio = Decimal(self.new_shares) / self.old_shares
            if self.ratio is not None and number(self.ratio) != ratio:
                raise ValueError("Split ratio disagrees with exact new/old counts")
        else:
            ratio = number(self.ratio)
        object.__setattr__(self, "ratio", ratio)
        if self.ratio <= 0:
            raise ValueError("Split ratio must be positive")

    def adjust_quantity(self, value):
        """Convert shares/volume using original counts before Decimal division."""
        return (value * self.new_shares / self.old_shares if self.new_shares is not None
                else value * self.ratio)

    def adjust_price(self, value):
        """Convert price/stop units; scalar-only actions retain legacy arithmetic."""
        return (value * self.old_shares / self.new_shares if self.new_shares is not None
                else value / self.ratio)


@dataclass(frozen=True)
class Dividend:
    security_id: str
    session: date  # Ex-date; entitlement before opening fills.
    amount: Decimal  # Per post-split share if a split occurs on the ex-date.
    pay_date: date

    def __post_init__(self):
        identity(self.security_id)
        session(self.session)
        session(self.pay_date)
        object.__setattr__(self, "amount", number(self.amount))
        if self.amount < 0 or self.pay_date < self.session:
            raise ValueError("Dividend must be nonnegative, with pay date >= ex-date")


@dataclass(frozen=True)
class CashDelisting:
    security_id: str
    session: date  # Explicit effective date; held shares settle before trading.
    amount: Decimal  # Cash per share; zero represents a documented write-off.

    def __post_init__(self):
        identity(self.security_id)
        session(self.session)
        object.__setattr__(self, "amount", number(self.amount))
        if self.amount < 0:
            raise ValueError("Delisting settlement cannot be negative")


RAW_PRICES_SPLIT_ADJUSTED_VOLUME = "raw_prices_split_adjusted_volume"
ADJUSTMENT_POLICIES = ("raw", RAW_PRICES_SPLIT_ADJUSTED_VOLUME)  # Prices are always raw.


@dataclass(frozen=True)
class DataMetadata:
    source: str
    retrieved_at: datetime
    universe_policy: str
    actions_complete: bool
    calendar_name: str
    adjustment_policy: str = "raw"  # Volume basis: "raw" or RAW_PRICES_SPLIT_ADJUSTED_VOLUME.
    limitations: tuple[str, ...] = ()
    input_hashes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.source, self.universe_policy, self.calendar_name)):
            raise ValueError("Source, universe policy, and calendar name are required")
        if not isinstance(self.retrieved_at, datetime) or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if type(self.actions_complete) is not bool:
            raise ValueError("actions_complete must explicitly be True or False")
        if self.adjustment_policy not in ADJUSTMENT_POLICIES:
            raise ValueError("Execution snapshots must contain raw prices")
        if isinstance(self.limitations, str) or any(not isinstance(v, str) for v in self.limitations):
            raise ValueError("limitations must be a sequence of strings")
        object.__setattr__(self, "limitations", tuple(self.limitations))
        hashes = tuple(sorted(tuple(pair) for pair in self.input_hashes))
        if any(len(pair) != 2 or not all(isinstance(v, str) for v in pair) for pair in hashes):
            raise ValueError("input_hashes must contain string name/hash pairs")
        if len({pair[0] for pair in hashes}) != len(hashes):
            raise ValueError("Duplicate input hash name")
        if any(not name or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
               for name, digest in hashes):
            raise ValueError("input_hashes requires names and SHA-256 hex digests")
        object.__setattr__(self, "input_hashes", hashes)


def require_raw_volume(metadata: DataMetadata, purpose: str) -> None:
    """Liquidity rules count shares in each bar's own units; adjusted volume would double-count splits."""
    if metadata.adjustment_policy != "raw":
        raise ValueError(f"{purpose}: raw share volume required, but this snapshot's volume is "
                         f"split-adjusted (adjustment_policy={metadata.adjustment_policy}); reconstruct raw "
                         "volume from reviewed complete splits or use a raw-volume source")


@dataclass(frozen=True)
class Security:
    security_id: str
    symbol: str
    exchange: str
    listed_on: date | None = None
    delisted_on: date | None = None  # First untradable date, not last trading session.

    def __post_init__(self):
        identity(self.security_id)
        if not all(isinstance(v, str) and v.strip() for v in (self.symbol, self.exchange)):
            raise ValueError("Symbol and exchange are required")
        for value in (self.listed_on, self.delisted_on):
            if value is not None:
                session(value)
        if self.listed_on and self.delisted_on and self.listed_on >= self.delisted_on:
            raise ValueError("Listing must precede delisting")

    def active_on(self, day: date) -> bool:
        return ((self.listed_on is None or day >= self.listed_on)
                and (self.delisted_on is None or day < self.delisted_on))


@dataclass(frozen=True)
class Snapshot:
    sessions: tuple[date, ...]  # Explicit calendar, including sessions with absent bars.
    bars: tuple[Bar, ...]
    metadata: DataMetadata
    securities: tuple[Security, ...]
    actions: tuple[Split | Dividend | CashDelisting, ...] = ()

    def __post_init__(self):
        if not isinstance(self.metadata, DataMetadata):
            raise ValueError("Snapshot requires DataMetadata")
        object.__setattr__(self, "sessions", tuple(self.sessions))
        object.__setattr__(self, "securities", tuple(self.securities))
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(self, "actions", tuple(self.actions))
        for value in self.sessions:
            session(value)
        if not self.sessions or tuple(sorted(set(self.sessions))) != self.sessions:
            raise ValueError("Sessions must be nonempty, unique, and ascending")
        if any(not isinstance(s, Security) for s in self.securities):
            raise ValueError("Snapshot requires Security records")
        securities = tuple(sorted(self.securities, key=lambda s: s.security_id))
        object.__setattr__(self, "securities", securities)
        if not securities or len({s.security_id for s in securities}) != len(securities):
            raise ValueError("Security registry must be nonempty with unique identifiers")
        registry = {s.security_id: s for s in securities}
        if any(not isinstance(bar, Bar) for bar in self.bars):
            raise ValueError("Snapshot requires Bar records")
        bars = tuple(sorted(self.bars, key=lambda bar: (bar.session, bar.security_id)))
        object.__setattr__(self, "bars", bars)
        keys = {(bar.session, bar.security_id) for bar in bars}
        if len(keys) != len(bars):
            raise ValueError("Duplicate security/session bar")
        calendar = set(self.sessions)
        if any(bar.session not in calendar for bar in bars):
            raise ValueError("Bar lies outside the supplied calendar")
        if any(bar.security_id not in registry for bar in bars):
            raise ValueError("Bar references an unknown security")
        if any(not registry[bar.security_id].active_on(bar.session) for bar in bars):
            raise ValueError("Bar lies outside security lifetime")
        if any(not isinstance(a, (Split, Dividend, CashDelisting)) for a in self.actions):
            raise ValueError("Unsupported corporate action")
        actions = tuple(sorted(self.actions, key=lambda a: (a.session, a.security_id, type(a).__name__)))
        object.__setattr__(self, "actions", actions)
        action_keys = {(a.session, a.security_id, type(a).__name__) for a in actions}
        if len(action_keys) != len(actions):
            raise ValueError("Duplicate corporate action; aggregate same-date distributions first")
        assets = set(registry)
        for action in actions:
            if action.session not in calendar or action.security_id not in assets:
                raise ValueError("Action outside calendar or unknown security")
            security = registry[action.security_id]
            if isinstance(action, CashDelisting):
                if security.delisted_on != action.session:
                    raise ValueError("Delisting action must match registry effective date")
            elif not security.active_on(action.session):
                raise ValueError("Action lies outside security lifetime")

    @property
    def dataset_hash(self):
        return content_hash(snapshot_payload(self))


def snapshot_payload(snapshot: Snapshot):
    """Typed, versioned canonical payload; action kinds survive persistence."""
    from quant_core.provenance import primitive

    payload = primitive(snapshot)
    payload["schema_version"] = 2 if any(isinstance(a, Split) and a.new_shares is not None
                                         for a in snapshot.actions) else 1
    actions = []
    for action in snapshot.actions:
        row = dict(primitive(action), kind=type(action).__name__)
        if isinstance(action, Split) and action.new_shares is None:
            # Existing normalized datasets retain their exact schema-1 hashes.
            row.pop("new_shares")
            row.pop("old_shares")
        actions.append(row)
    payload["actions"] = actions
    return payload
