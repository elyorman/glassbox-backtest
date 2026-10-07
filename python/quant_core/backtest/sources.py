"""Scheduled engineering inputs and a causal callback boundary for later strategies."""

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol

from quant_core.data import Bar, Dividend, Split, session
from quant_core.execution import OrderRequest
from quant_core.sizing import EntryIntent
from quant_core.portfolio import PositionValue
from quant_core.provenance import content_hash
from quant_core.backtest.contracts import SignalDecision, SourceSpec


@dataclass(frozen=True)
class SessionContext:
    as_of: date
    universe: tuple[str, ...]
    cash: Decimal
    equity: Decimal
    positions: tuple[PositionValue, ...]
    _bars: Mapping[str, tuple[Bar, ...]] = field(repr=False)
    _dates: Mapping[str, tuple[date, ...]] = field(repr=False)
    _splits: tuple[Split, ...] = field(repr=False)
    _dividends: tuple[Dividend, ...] = field(default=(), repr=False)

    def history(self, security_id: str, limit: int | None = None) -> tuple[Bar, ...]:
        if security_id not in self.universe:
            raise ValueError("Historical access requires a security in the trading universe")
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("History limit must be a positive integer")
        stop = bisect_right(self._dates.get(security_id, ()), self.as_of)
        start = max(0, stop - limit) if limit is not None else 0
        return self._bars.get(security_id, ())[start:stop]

    @property
    def splits(self):
        return tuple(s for s in self._splits if s.session <= self.as_of and s.security_id in self.universe)

    @property
    def dividends(self):
        return tuple(d for d in self._dividends if d.session <= self.as_of and d.security_id in self.universe)


@dataclass(frozen=True)
class OrderBatch:
    requests: tuple[OrderRequest | EntryIntent, ...]
    decisions: tuple[SignalDecision, ...]

    def __post_init__(self):
        for name in ("requests", "decisions"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if any(not isinstance(r, (OrderRequest, EntryIntent)) for r in self.requests):
            raise ValueError("Batch contains unsupported request")
        if any(not isinstance(d, SignalDecision) for d in self.decisions):
            raise ValueError("Batch contains unsupported decision")


class OrderSource(Protocol):
    @property
    def spec(self) -> SourceSpec: ...

    def orders(self, context: SessionContext) -> tuple[OrderRequest | EntryIntent, ...] | OrderBatch: ...


@dataclass(frozen=True)
class ScheduledOrder:
    signal_date: date
    request: OrderRequest | EntryIntent

    def __post_init__(self):
        session(self.signal_date)
        if not isinstance(self.request, (OrderRequest, EntryIntent)):
            raise ValueError("Scheduled input requires OrderRequest or EntryIntent")


@dataclass(frozen=True)
class OrderSchedule:
    entries: tuple[ScheduledOrder, ...]
    name: str = "explicit_engineering_orders"
    version: str = "1"
    _by_date: Mapping = field(init=False, repr=False, compare=False)
    _spec: SourceSpec = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        entries = tuple(self.entries)
        if any(not isinstance(entry, ScheduledOrder) for entry in entries):
            raise ValueError("Schedule requires ScheduledOrder records")
        entries = tuple(sorted(entries, key=lambda e: (e.signal_date, content_hash(e.request))))
        object.__setattr__(self, "entries", entries)
        by_date = {}
        for entry in entries:
            by_date.setdefault(entry.signal_date, []).append(entry.request)
        object.__setattr__(self, "_by_date", MappingProxyType({d: tuple(v) for d, v in by_date.items()}))
        object.__setattr__(self, "_spec", SourceSpec(self.name, self.version,
                                                    content_hash((self.name, self.version, self.entries))))

    @property
    def spec(self):
        return self._spec

    def orders(self, context):
        return self._by_date.get(context.as_of, ())


def load_schedule(path: Path) -> OrderSchedule:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if set(payload) != {"schema_version", "name", "version", "orders"}:
            raise ValueError("Schedule requires schema_version, name, version, orders")
        if type(payload["schema_version"]) is not int or payload["schema_version"] not in (1, 2):
            raise ValueError("Unsupported schedule schema")
        entries = []
        for row in payload["orders"]:
            values = dict(row)
            signal_date = date.fromisoformat(values.pop("signal_date"))
            kind = values.pop("kind") if payload["schema_version"] == 2 else "order"
            if kind not in ("order", "entry"):
                raise ValueError("Unsupported schedule input kind")
            entries.append(ScheduledOrder(signal_date, (EntryIntent if kind == "entry" else OrderRequest)(**values)))
        return OrderSchedule(tuple(entries), payload["name"], payload["version"])
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed order schedule: {exc}") from exc
