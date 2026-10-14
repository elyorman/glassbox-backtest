"""A study's registration: everything fixed before its one registered run (docs/STRATEGY_EVIDENCE.md, Section 3).

The file is docs/registrations/<study>.json, committed and tagged before the run.
`load_registration` refuses anything incomplete or inconsistent; the registration hash
is the content hash of the file's JSON value.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import re

from quant_core.data import identity, number
from quant_core.provenance import content_hash
from quant_core.strategies.plans import PlanConfig, plan_from_dict

SCHEMA_VERSION = 1
REFERENCES = ("spy_buy_hold", "sixty_forty", "equal_weight", "tbills")
REFERENCE_TICKERS = ("IEF", "SPY")
FIELDS = frozenset((
    "schema_version", "study", "role", "tag", "registered_at", "code_hash", "dataset", "plan", "neighbours",
    "rebalance_shifts", "period", "publication", "segments", "costs_bps", "primary_cost_bps", "initial_cash",
    "primary_reference", "bootstrap", "trials", "sources", "departures", "related_ledger_rows", "cross_check",
    "disclosures", "earlier_studies"))
_HEX = re.compile(r"[0-9a-f]{64}")
_STUDY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class Registration:
    study: str
    role: str
    tag: str
    registered_at: datetime
    code_hash: str
    dataset_id: str
    tickers: tuple[str, ...]
    plan: PlanConfig
    neighbours: tuple[PlanConfig, ...]
    rebalance_shifts: tuple[int, ...]
    start: date
    end: date
    publication: date
    segments: tuple[tuple[str, date, date], ...]
    costs_bps: tuple[Decimal, ...]
    primary_cost_bps: Decimal
    initial_cash: Decimal
    primary_reference: str
    block_lengths: tuple[int, ...]
    repetitions: int
    seed: int
    trials: int
    trials_this_study: int
    trials_per_role: int
    historical_floor: Decimal
    disclosures: tuple[str, ...]
    earlier_studies: tuple[tuple[str, str], ...]
    hash: str
    payload: dict = field(repr=False, compare=False)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Registration {name} must be nonempty text")
    return value


def _texts(value, name, minimum=0):
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"Registration {name} must be a list of at least {minimum} item(s)")
    return tuple(_text(item, name) for item in value)


def _record(value, name, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"Registration {name} must have exactly the fields {', '.join(keys)}")
    return value


def _day(value, name):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Registration {name} must be a YYYY-MM-DD date") from None


def _count(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"Registration {name} must be an integer of at least {minimum}")
    return value


def parse_registration(payload) -> Registration:
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError("Registration must have exactly the documented fields")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported registration schema version")
    study = _text(payload["study"], "study")
    if _STUDY.fullmatch(study) is None:
        raise ValueError("Registration study must be lower-case words joined by hyphens")
    tag = _text(payload["tag"], "tag")
    if re.fullmatch(re.escape(f"study/{study}-") + r"\d{4}-\d{2}-\d{2}", tag) is None:
        raise ValueError("Registration tag must be study/<study>-<YYYY-MM-DD>")
    try:
        registered_at = datetime.fromisoformat(_text(payload["registered_at"], "registered_at"))
    except ValueError:
        raise ValueError("Registration registered_at must be an ISO time") from None
    if registered_at.utcoffset() is None:
        raise ValueError("Registration registered_at must include its time zone")
    if not isinstance(payload["code_hash"], str) or _HEX.fullmatch(payload["code_hash"]) is None:
        raise ValueError("Registration code_hash must be a SHA-256 hex digest")
    dataset = _record(payload["dataset"], "dataset", ("id", "tickers"))
    if not isinstance(dataset["id"], str) or _HEX.fullmatch(dataset["id"]) is None:
        raise ValueError("Registration dataset id must be a SHA-256 hex digest")
    tickers = _texts(dataset["tickers"], "dataset tickers", 1)
    for ticker in tickers:
        identity(ticker)
    plan = plan_from_dict(payload["plan"])
    if not isinstance(payload["neighbours"], list):
        raise ValueError("Registration neighbours must be a list")
    neighbours = tuple(plan_from_dict(values) for values in payload["neighbours"])
    if len(neighbours) < 2 or any(type(n) is not type(plan) for n in neighbours):
        raise ValueError("Registration needs at least two neighbours of the parent's rule")
    configurations = (plan,) + neighbours
    if (any(c.purpose != "built_in_plan" or c.decision_offset != 0 for c in configurations)
            or len(set(configurations)) != len(configurations)):
        raise ValueError("The parent and its neighbours must be distinct built-in plans without a decision offset")
    needed = set(REFERENCE_TICKERS).union(*(c.universe for c in configurations))
    if not needed <= set(tickers):
        raise ValueError(f"Registration dataset tickers lack {', '.join(sorted(needed - set(tickers)))}")
    shifts = payload["rebalance_shifts"]
    if (not isinstance(shifts, list) or any(type(s) is not int or s == 0 or not -2 <= s <= 2 for s in shifts)
            or len(set(shifts)) != len(shifts)):
        raise ValueError("Registration rebalance shifts must be distinct nonzero sessions from -2 to 2")
    period = _record(payload["period"], "period", ("start", "end"))
    start, end = _day(period["start"], "period start"), _day(period["end"], "period end")
    if start >= end:
        raise ValueError("Registration period must start before it ends")
    publication = _record(payload["publication"], "publication", ("date", "source"))
    published = _day(publication["date"], "publication date")
    _text(publication["source"], "publication source")
    if published > end:
        raise ValueError("Registration publication date must not follow the period end")
    if not isinstance(payload["segments"], list):
        raise ValueError("Registration segments must be a list")
    segments = []
    for values in payload["segments"]:
        values = _record(values, "segment", ("name", "start", "end"))
        segment = (_text(values["name"], "segment name"), _day(values["start"], "segment start"),
                   _day(values["end"], "segment end"))
        if segment[1] > segment[2]:
            raise ValueError("Registration segment must start before it ends")
        segments.append(segment)
    try:
        costs = tuple(number(value) for value in payload["costs_bps"])
        primary_cost, initial_cash = number(payload["primary_cost_bps"]), number(payload["initial_cash"])
        floor = number(_record(payload["trials"], "trials",
                               ("cumulative", "this_study", "per_role", "historical_floor"))["historical_floor"])
    except (TypeError, ValueError):
        raise ValueError("Registration costs, initial cash and floor must be decimal strings") from None
    if not costs or len(set(costs)) != len(costs) or any(c < 0 for c in costs) or primary_cost not in costs:
        raise ValueError("Registration costs must be distinct and nonnegative and include the primary cost")
    if initial_cash <= 0 or floor < 0:
        raise ValueError("Registration initial cash must be positive and the floor nonnegative")
    if payload["primary_reference"] not in REFERENCES[:3]:
        raise ValueError(f"Registration primary reference must be one of {', '.join(REFERENCES[:3])}")
    bootstrap = _record(payload["bootstrap"], "bootstrap", ("block_lengths", "repetitions", "seed"))
    blocks = bootstrap["block_lengths"]
    if not isinstance(blocks, list) or not blocks or len(set(blocks)) != len(blocks):
        raise ValueError("Registration bootstrap block lengths must be distinct")
    blocks = tuple(_count(b, "bootstrap block length", 1) for b in blocks)
    repetitions, seed = _count(bootstrap["repetitions"], "repetitions", 100), _count(bootstrap["seed"], "seed")
    trials = payload["trials"]
    this_study = _count(trials["this_study"], "this study's trial count", 1)
    if this_study != len(configurations) + len(shifts):
        raise ValueError("This study's trial count must be the parent, its neighbours and its shifts")
    cumulative = _count(trials["cumulative"], "cumulative trial count", this_study)
    per_role = _count(trials["per_role"], "per-role trial count", 1)
    if per_role > cumulative:
        raise ValueError("The per-role trial count cannot exceed the cumulative count")
    if not isinstance(payload["sources"], list) or not payload["sources"]:
        raise ValueError("Registration needs at least one parameter source")
    for values in payload["sources"]:
        values = _record(values, "source", ("parameter", "source"))
        _text(values["parameter"], "source parameter")
        _text(values["source"], "source")
    if not isinstance(payload["departures"], list):
        raise ValueError("Registration departures must be a list")
    for values in payload["departures"]:
        values = _record(values, "departure", ("what", "reason"))
        _text(values["what"], "departure")
        _text(values["reason"], "departure reason")
    _texts(payload["related_ledger_rows"], "related ledger rows")
    cross_check = _record(payload["cross_check"], "cross-check", ("decision", "reason"))
    _text(cross_check["decision"], "cross-check decision")
    _text(cross_check["reason"], "cross-check reason")
    if not isinstance(payload["earlier_studies"], list):
        raise ValueError("Registration earlier studies must be a list")
    earlier = []
    for values in payload["earlier_studies"]:
        values = _record(values, "earlier study", ("study", "runs"))
        earlier.append((_text(values["study"], "earlier study"), _text(values["runs"], "earlier study runs")))
    return Registration(
        study, _text(payload["role"], "role"), tag, registered_at, payload["code_hash"], dataset["id"], tickers,
        plan, neighbours, tuple(shifts), start, end, published, tuple(segments), costs, primary_cost,
        initial_cash, payload["primary_reference"], blocks, repetitions, seed, cumulative, this_study, per_role,
        floor, _texts(payload["disclosures"], "disclosures"), tuple(earlier), content_hash(payload), payload)


def load_registration(path: Path) -> Registration:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Registration {path} is not JSON: {exc}") from None
    return parse_registration(payload)
