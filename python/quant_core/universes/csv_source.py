"""Local historical-membership import; preserve raw-byte provenance."""

import csv
from datetime import date, datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path

from quant_core.universes import DatedUniverse, MembershipInterval


def import_membership_csv(path: Path, *, universe_id: str, coverage_start: date,
                          coverage_end: date, coverage_available_on: date, source: str,
                          retrieved_at: datetime, limitations: tuple[str, ...] = ()) -> DatedUniverse:
    path = Path(path)
    raw = path.read_bytes()
    reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
    expected = {"security_id", "entered_on", "entry_available_on", "left_on", "exit_available_on"}
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError(f"{path.name}: missing or duplicate CSV headers")
    if set(reader.fieldnames) != expected:
        raise ValueError(f"{path.name}: expected columns {', '.join(sorted(expected))}")
    intervals = []
    for line, row in enumerate(reader, 2):
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("column count does not match header")
            intervals.append(MembershipInterval(row["security_id"], date.fromisoformat(row["entered_on"]),
                date.fromisoformat(row["entry_available_on"]),
                date.fromisoformat(row["left_on"]) if row["left_on"] else None,
                date.fromisoformat(row["exit_available_on"]) if row["exit_available_on"] else None))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path.name}:{line}: {exc}") from exc
    return DatedUniverse(universe_id, coverage_start, coverage_end, tuple(intervals), source,
                         retrieved_at, coverage_available_on, limitations,
                         (("membership_csv", sha256(raw).hexdigest()),))
