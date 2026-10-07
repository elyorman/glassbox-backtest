"""Dated, source-bound historical membership, separate from tradability filters."""

from dataclasses import dataclass, fields
from datetime import date, datetime
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from quant_core.data import identity, session
from quant_core.provenance import canonical_json, content_hash, primitive


class UniverseCoverageError(ValueError):
    """The source does not assert complete membership for the requested date."""


class UniverseAvailabilityError(ValueError):
    """An effective membership fact was not available on the requested date."""


@dataclass(frozen=True)
class MembershipInterval:
    security_id: str
    entered_on: date  # Inclusive effective date.
    entry_available_on: date
    left_on: date | None = None  # Exclusive effective date.
    exit_available_on: date | None = None

    def __post_init__(self):
        identity(self.security_id)
        session(self.entered_on)
        session(self.entry_available_on)
        if (self.left_on is None) != (self.exit_available_on is None):
            raise ValueError("A removal requires both effective and availability dates")
        if self.left_on is not None:
            session(self.left_on)
            session(self.exit_available_on)
            if self.left_on <= self.entered_on:
                raise ValueError("Membership removal must follow entry")


@dataclass(frozen=True)
class DatedUniverse:
    universe_id: str
    coverage_start: date  # Complete membership asserted, inclusive.
    coverage_end: date  # Inclusive; no inference beyond this date.
    intervals: tuple[MembershipInterval, ...]
    source: str
    retrieved_at: datetime
    coverage_available_on: date  # Availability of the coverage baseline.
    limitations: tuple[str, ...] = ()
    input_hashes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        identity(self.universe_id)
        for value in (self.coverage_start, self.coverage_end, self.coverage_available_on):
            session(value)
        if self.coverage_start > self.coverage_end:
            raise ValueError("Universe coverage start must not follow end")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("Membership source is required")
        if not isinstance(self.retrieved_at, datetime) or self.retrieved_at.utcoffset() is None:
            raise ValueError("Membership retrieved_at must be timezone-aware")
        if isinstance(self.limitations, str) or any(not isinstance(item, str) for item in self.limitations):
            raise ValueError("Membership limitations must be a sequence of strings")
        object.__setattr__(self, "limitations", tuple(self.limitations))
        try:
            hashes = tuple(sorted(tuple(pair) for pair in self.input_hashes))
        except TypeError as exc:
            raise ValueError("Membership input_hashes requires name/hash pairs") from exc
        if any(len(pair) != 2 or not all(isinstance(value, str) for value in pair) for pair in hashes):
            raise ValueError("Membership input_hashes requires string name/hash pairs")
        if len({pair[0] for pair in hashes}) != len(hashes):
            raise ValueError("Duplicate membership input hash name")
        if any(not name or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
               for name, digest in hashes):
            raise ValueError("Membership input_hashes requires names and SHA-256 hex digests")
        object.__setattr__(self, "input_hashes", hashes)
        intervals = tuple(self.intervals)
        if any(not isinstance(item, MembershipInterval) for item in intervals):
            raise ValueError("Universe requires MembershipInterval records")
        intervals = tuple(sorted(intervals, key=lambda item: (item.security_id, item.entered_on)))
        previous = None
        for item in intervals:
            if previous is not None and previous.security_id == item.security_id:
                if previous.left_on is None or item.entered_on < previous.left_on:
                    raise ValueError(f"Overlapping membership for {item.security_id}")
            previous = item
        object.__setattr__(self, "intervals", intervals)

    @property
    def security_ids(self) -> tuple[str, ...]:
        """All stable IDs needed by a consumer's security registry."""
        return tuple(sorted({item.security_id for item in self.intervals}))

    def members_on(self, day: date) -> tuple[str, ...]:
        """Return effective members only when the full dated state was available.

        Announcements of future changes do not change current membership. A
        future removal need not be known at entry; it is checked when effective.
        Late imported corrections block affected dates instead of leaking the
        correction or quietly reverting to incomplete/current membership.
        """
        session(day)
        if not self.coverage_start <= day <= self.coverage_end:
            raise UniverseCoverageError(f"{self.universe_id}: no historical coverage for {day}")
        if day < self.coverage_available_on:
            raise UniverseAvailabilityError(f"{self.universe_id}: coverage baseline unavailable on {day}")
        members = set()
        for item in self.intervals:
            if day < item.entered_on:
                continue
            if day < item.entry_available_on:
                raise UniverseAvailabilityError(f"{item.security_id}: effective entry unavailable on {day}")
            if item.left_on is not None and day >= item.left_on:
                if day < item.exit_available_on:
                    raise UniverseAvailabilityError(f"{item.security_id}: effective removal unavailable on {day}")
                continue
            members.add(item.security_id)
        return tuple(sorted(members))

    def to_dict(self) -> dict:
        return dict(primitive(self), schema_version=1)

    def content_hash(self) -> str:
        return content_hash(self.to_dict())

    @classmethod
    def from_dict(cls, payload: dict) -> "DatedUniverse":
        try:
            if set(payload) != {field.name for field in fields(cls)} | {"schema_version"}:
                raise ValueError("Unexpected dated universe fields")
            if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
                raise ValueError("Unsupported dated universe schema version")
            values = dict(payload)
            values.pop("schema_version")
            for name in ("coverage_start", "coverage_end", "coverage_available_on"):
                values[name] = date.fromisoformat(values[name])
            values["retrieved_at"] = datetime.fromisoformat(values["retrieved_at"])
            intervals = []
            for row in values["intervals"]:
                if set(row) != {field.name for field in fields(MembershipInterval)}:
                    raise ValueError("Unexpected membership interval fields")
                interval = dict(row)
                for name in ("entered_on", "entry_available_on"):
                    interval[name] = date.fromisoformat(interval[name])
                for name in ("left_on", "exit_available_on"):
                    interval[name] = date.fromisoformat(interval[name]) if interval[name] is not None else None
                intervals.append(MembershipInterval(**interval))
            values["intervals"] = tuple(intervals)
            return cls(**values)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"Malformed dated universe: {exc}") from exc

    def save(self, path: Path) -> None:
        """Atomically publish a hashed immutable artifact; refuse any overwrite."""
        path = Path(path)
        serialized = canonical_json({"universe_hash": self.content_hash(), "universe": self.to_dict()}) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                    prefix=".universe-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, path: Path) -> "DatedUniverse":
        try:
            envelope = json.loads(Path(path).read_text(encoding="utf-8"))
            if set(envelope) != {"universe_hash", "universe"}:
                raise ValueError("Unexpected dated universe envelope fields")
            if content_hash(envelope["universe"]) != envelope["universe_hash"]:
                raise ValueError("Dated universe integrity hash mismatch")
            result = cls.from_dict(envelope["universe"])
            if result.content_hash() != envelope["universe_hash"]:
                raise ValueError("Dated universe is not in canonical normalized form")
            return result
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"Malformed dated universe: {exc}") from exc
