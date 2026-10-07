"""Local CSV adapter. Input bytes are read once, hashed, and never modified."""

import csv
from dataclasses import dataclass, replace
from datetime import date
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Protocol

from quant_core.data import (
    Bar, CashDelisting, DataMetadata, Dividend, Security, Snapshot, Split,
)


class SnapshotSource(Protocol):
    def load(self) -> Snapshot: ...


def _rows(path: Path, expected: tuple[str, ...], optional: tuple[str, ...] = ()):
    raw = path.read_bytes()
    reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError(f"{path.name}: missing or duplicate CSV headers")
    if set(reader.fieldnames) not in (set(expected), set(expected + optional)):
        raise ValueError(f"{path.name}: expected columns {', '.join(expected)}")
    rows = []
    for line, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path.name}:{line}: column count does not match header")
        rows.append((line, row))
    return rows, sha256(raw).hexdigest()


def _convert(path, rows, factory):
    result = []
    for line, row in rows:
        try:
            result.append(factory(row))
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"{path.name}:{line}: {exc}") from exc
    return tuple(result)


def _action(row):
    kind = row["kind"]
    asset = row["security_id"]
    day = date.fromisoformat(row["session_date"])
    if kind == "Split":
        if row["amount"] or row["pay_date"]:
            raise ValueError("Split requires ratio; amount and pay_date must be empty")
        counts = row.get("new_shares", ""), row.get("old_shares", "")
        if any(counts):
            if not all(counts):
                raise ValueError("Exact split counts must be supplied together")
            return Split(asset, day, row["ratio"] or None,
                         new_shares=int(counts[0]), old_shares=int(counts[1]))
        return Split(asset, day, row["ratio"])
    if row.get("new_shares") or row.get("old_shares"):
        raise ValueError("Only splits may contain share counts")
    if kind == "Dividend":
        if row["ratio"]:
            raise ValueError("Dividend ratio must be empty")
        return Dividend(asset, day, row["amount"], date.fromisoformat(row["pay_date"]))
    if kind == "CashDelisting":
        if row["ratio"] or row["pay_date"]:
            raise ValueError("CashDelisting requires amount; ratio and pay_date must be empty")
        return CashDelisting(asset, day, row["amount"])
    raise ValueError(f"Unsupported action kind: {kind}")


def load_calendar(path: Path):
    rows, digest = _rows(path, ("session_date",))
    return _convert(path, rows, lambda row: date.fromisoformat(row["session_date"])), digest


def load_securities(path: Path):
    rows, digest = _rows(path, ("security_id", "symbol", "exchange", "listed_on", "delisted_on"))
    records = _convert(path, rows, lambda row: Security(
        row["security_id"], row["symbol"], row["exchange"],
        date.fromisoformat(row["listed_on"]) if row["listed_on"] else None,
        date.fromisoformat(row["delisted_on"]) if row["delisted_on"] else None))
    return records, digest


def load_actions(path: Path):
    rows, digest = _rows(path, ("kind", "security_id", "session_date", "ratio", "amount", "pay_date"),
                         ("new_shares", "old_shares"))
    return _convert(path, rows, _action), digest


@dataclass(frozen=True)
class CsvSource:
    bars_path: Path
    calendar_path: Path
    securities_path: Path
    metadata: DataMetadata
    actions_path: Path | None = None

    def load(self) -> Snapshot:
        bar_rows, bar_hash = _rows(self.bars_path,
                                  ("security_id", "session_date", "open", "high", "low", "close", "volume"))
        calendar_rows, calendar_hash = _rows(self.calendar_path, ("session_date",))
        security_rows, security_hash = _rows(self.securities_path,
                                            ("security_id", "symbol", "exchange", "listed_on", "delisted_on"))
        sessions = _convert(self.calendar_path, calendar_rows,
                            lambda row: date.fromisoformat(row["session_date"]))
        bars = _convert(self.bars_path, bar_rows, lambda row: Bar(
            row["security_id"], date.fromisoformat(row["session_date"]),
            row["open"], row["high"], row["low"], row["close"], row["volume"]))
        securities = _convert(self.securities_path, security_rows, lambda row: Security(
            row["security_id"], row["symbol"], row["exchange"],
            date.fromisoformat(row["listed_on"]) if row["listed_on"] else None,
            date.fromisoformat(row["delisted_on"]) if row["delisted_on"] else None))
        hashes = [("bars", bar_hash), ("calendar", calendar_hash), ("securities", security_hash)]
        actions = ()
        if self.actions_path is not None:
            actions, action_hash = load_actions(self.actions_path)
            hashes.append(("actions", action_hash))
        metadata = replace(self.metadata, input_hashes=tuple(hashes))
        return Snapshot(sessions, bars, metadata, securities, actions)
