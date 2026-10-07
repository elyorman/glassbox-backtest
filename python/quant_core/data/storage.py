"""Versioned local snapshot persistence with integrity verification."""

from datetime import date, datetime
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from quant_core.data import (
    Bar, CashDelisting, DataMetadata, Dividend, Security, Snapshot, Split, snapshot_payload,
)
from quant_core.provenance import canonical_json, content_hash


def save_snapshot(snapshot: Snapshot, path: Path) -> None:
    payload = snapshot_payload(snapshot)
    serialized = canonical_json({"dataset_hash": content_hash(payload), "snapshot": payload}) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Publish a fully written file without replacing an existing dataset version.
    # A same-directory hard link is atomic and refuses an existing destination.
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                dir=path.parent, prefix=".snapshot-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_snapshot(path: Path) -> Snapshot:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if set(envelope) != {"dataset_hash", "snapshot"}:
            raise ValueError("Unexpected snapshot envelope fields")
        payload = envelope["snapshot"]
        if content_hash(payload) != envelope["dataset_hash"]:
            raise ValueError("Snapshot integrity hash mismatch")
        return snapshot_from_payload(payload)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed snapshot: {exc}") from exc


def snapshot_from_payload(payload) -> Snapshot:
    """Decode canonical schema-1/2 data identically for JSON and Parquet imports.

    Storage adapters verify their own envelope/file integrity before calling this
    function. Decimal spellings and optional exact split counts stay untouched.
    """
    try:
        if set(payload) != {"schema_version", "sessions", "bars", "metadata", "securities", "actions"}:
            raise ValueError("Unexpected snapshot fields")
        if type(payload["schema_version"]) is not int or payload["schema_version"] not in (1, 2):
            raise ValueError("Unsupported snapshot schema version")
        raw_meta = dict(payload["metadata"])
        raw_meta["retrieved_at"] = datetime.fromisoformat(raw_meta["retrieved_at"])
        metadata = DataMetadata(**raw_meta)
        bars = tuple(Bar(**dict(row, session=date.fromisoformat(row["session"]))) for row in payload["bars"])
        securities = tuple(Security(**dict(row,
            listed_on=date.fromisoformat(row["listed_on"]) if row["listed_on"] else None,
            delisted_on=date.fromisoformat(row["delisted_on"]) if row["delisted_on"] else None))
            for row in payload["securities"])
        actions = []
        constructors = {"Split": Split, "Dividend": Dividend, "CashDelisting": CashDelisting}
        for row in payload["actions"]:
            values = dict(row)
            kind = values.pop("kind")
            if kind not in constructors:
                raise ValueError(f"Unsupported action kind: {kind}")
            values["session"] = date.fromisoformat(values["session"])
            if kind == "Dividend":
                values["pay_date"] = date.fromisoformat(values["pay_date"])
            actions.append(constructors[kind](**values))
        snapshot = Snapshot(tuple(date.fromisoformat(d) for d in payload["sessions"]),
                            bars, metadata, securities, tuple(actions))
        if snapshot.dataset_hash != content_hash(payload):
            raise ValueError("Snapshot payload is not in canonical normalized form")
        return snapshot
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed snapshot: {exc}") from exc
