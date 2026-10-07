"""Audit saved EODHD actions; propose reviewed USD cash/share events only."""

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re
import sys

from quant_core.data import Dividend, Split, identity, number, session
from quant_core.data.eodhd import _cache_bytes, _publish_bytes, _unique_object, _valid_ticker
from quant_core.provenance import canonical_json, content_hash


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Invalid action date")
    return date.fromisoformat(value)


def _counts(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.0+)?/\d+(?:\.0+)?", value):
        raise ValueError("Split needs original positive integer-valued counts")
    new, old = (int(Decimal(v)) for v in value.split("/"))
    if new <= 0 or old <= 0:
        raise ValueError("Split counts must be positive")
    return new, old


@dataclass(frozen=True)
class ReviewedSplit:
    session: date
    ratio_text: str
    evidence_hash: str

    def __post_init__(self):
        session(self.session)
        _counts(self.ratio_text)
        if not isinstance(self.evidence_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_hash):
            raise ValueError("Split review needs a SHA-256 evidence hash")


@dataclass(frozen=True)
class ActionIssue:
    code: str
    endpoint: str
    session: date
    row_index: int


@dataclass(frozen=True)
class ActionAudit:
    ticker: str
    security_id: str
    start: date
    end: date
    retrieved_at: datetime
    actions: tuple
    issues: tuple[ActionIssue, ...]
    input_hashes: tuple[tuple[str, str], ...]
    observations: tuple[tuple[str, int], ...]
    split_reviews: tuple[ReviewedSplit, ...]
    coverage_qualified: bool = False
    limitations: tuple[str, ...] = (
        "Returned events are proposals; endpoint responses do not prove historical completeness",
        "Review noncash distributions, reorganizations, identities and terminal outcomes separately",
        "USD cash only; no currency conversion or adjusted-dividend fallback",
        "Historical raw-volume basis and account research rights remain separate qualification inputs",
    )

    @property
    def has_unresolved(self):
        return bool(self.issues)


def _action_rows(raw, start, end, retrieved_at):
    """Reject structural/date errors without echoing provider bodies."""
    try:
        if not isinstance(raw, bytes):
            raise ValueError("Original bytes required")
        rows = json.loads(raw, parse_float=Decimal, object_pairs_hook=_unique_object)
        if not isinstance(rows, list):
            raise ValueError("Array required")
        days = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Object required")
            day = _day(row.get("date"))
            if not start <= day <= end or day > retrieved_at.astimezone(timezone.utc).date():
                raise ValueError("Event outside requested/observed dates")
            days.append(day)
        if len(set(days)) != len(days):
            raise ValueError("Duplicate action ex-date needs explicit reconciliation")
        return tuple(zip(days, rows))
    except (ValueError, TypeError, UnicodeError, ArithmeticError):
        raise ValueError("EODHD action response has invalid structure, duplicate events or dates") from None


def audit_actions(ticker, security_id, splits_raw, dividends_raw, *, start, end,
                  retrieved_at, split_reviews=(), cache_dir=None):
    if not _valid_ticker(ticker):
        raise ValueError("Invalid EODHD ticker")
    identity(security_id)
    session(start)
    session(end)
    if start > end or not isinstance(retrieved_at, datetime) or retrieved_at.utcoffset() is None:
        raise ValueError("Ordered window and timezone-aware retrieval required")
    reviews = tuple(split_reviews)
    if any(not isinstance(r, ReviewedSplit) for r in reviews) or len({r.session for r in reviews}) != len(reviews):
        raise ValueError("Unique split reviews required")
    by_day = {r.session: r for r in reviews}
    split_rows = _action_rows(splits_raw, start, end, retrieved_at)
    dividend_rows = _action_rows(dividends_raw, start, end, retrieved_at)
    supplied = {day: row.get("split") for day, row in split_rows}
    if any(supplied.get(r.session) != r.ratio_text for r in reviews):
        raise ValueError("Split review differs from returned date/ratio")
    actions, issues = [], []
    for index, (day, row) in enumerate(split_rows):
        try:
            new, old = _counts(row.get("split"))
        except (ValueError, ArithmeticError):
            issues.append(ActionIssue("invalid_split_ratio", "splits", day, index))
            continue
        if day not in by_day:
            issues.append(ActionIssue("unclassified_split_event", "splits", day, index))
        else:
            actions.append(Split(security_id, day, new_shares=new, old_shares=old))
    for index, (day, row) in enumerate(dividend_rows):
        codes = []
        cash = row.get("unadjustedValue")
        if cash is None:
            codes.append("missing_unadjusted_cash")
        else:
            try:
                cash = number(cash)
                if cash < 0:
                    raise ValueError("Negative cash")
            except (ValueError, ArithmeticError):
                codes.append("invalid_cash_amount")
        if row.get("currency") != "USD":
            codes.append("unsupported_currency")
        payable = row.get("paymentDate")
        if payable in (None, ""):
            codes.append("missing_payment_date")
        else:
            try:
                payable = _day(payable)
                if payable < day:
                    raise ValueError("Pay date before ex-date")
            except ValueError:
                codes.append("invalid_payment_date")
        if codes:
            issues.extend(ActionIssue(code, "dividends", day, index) for code in codes)
        else:
            actions.append(Dividend(security_id, day, cash, payable))
    # Raw bytes remain intact; even unresolved valid responses are evidence.
    if cache_dir is not None:
        _cache_bytes(splits_raw, Path(cache_dir))
        _cache_bytes(dividends_raw, Path(cache_dir))
    actions.sort(key=lambda a: (a.session, type(a).__name__))
    return ActionAudit(ticker, security_id, start, end, retrieved_at, tuple(actions), tuple(issues),
                       (("eodhd:splits:"+ticker, sha256(splits_raw).hexdigest()),
                        ("eodhd:dividends:"+ticker, sha256(dividends_raw).hexdigest()),
                        ("eodhd:split_reviews:"+ticker, content_hash(reviews))),
                       (("splits", len(split_rows)), ("dividends", len(dividend_rows))), reviews)


def _actions_csv(actions):
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(("kind", "security_id", "session_date", "ratio", "amount", "pay_date", "new_shares", "old_shares"))
    for action in actions:
        if isinstance(action, Split):
            writer.writerow(("Split", action.security_id, action.session, "", "", "", action.new_shares, action.old_shares))
        else:
            writer.writerow(("Dividend", action.security_id, action.session, "", action.amount, action.pay_date, "", ""))
    return stream.getvalue().encode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("ticker", "security-id", "retrieved-at"):
        parser.add_argument("--"+field, required=True)
    for field in ("splits", "dividends", "output"):
        parser.add_argument("--"+field, type=Path, required=True)
    for field in ("start", "end"):
        parser.add_argument("--"+field, type=date.fromisoformat, required=True)
    parser.add_argument("--split-review", type=Path, help="JSON array of date/ratio-bound ReviewedSplit records")
    parser.add_argument("--raw-cache", type=Path)
    parser.add_argument("--actions-output", type=Path, help="Proposed CSV; emitted only when returned events are resolved")
    args = parser.parse_args(argv)
    try:
        reviews = []
        if args.split_review:
            rows = json.loads(args.split_review.read_bytes(), object_pairs_hook=_unique_object)
            if not isinstance(rows, list):
                raise ValueError("Split review must be an array")
            if any(not isinstance(r, dict) or set(r) != {"session", "ratio_text", "evidence_hash"} for r in rows):
                raise ValueError("Split review requires exactly the documented fields")
            reviews = [ReviewedSplit(_day(r["session"]), r["ratio_text"], r["evidence_hash"]) for r in rows]
        result = audit_actions(args.ticker, args.security_id, args.splits.read_bytes(), args.dividends.read_bytes(),
                               start=args.start, end=args.end, retrieved_at=datetime.fromisoformat(args.retrieved_at),
                               split_reviews=reviews, cache_dir=args.raw_cache)
        _publish_bytes((canonical_json(result)+"\n").encode(), args.output)
        if args.actions_output and not result.has_unresolved:
            _publish_bytes(_actions_csv(result.actions), args.actions_output)
        print(canonical_json({"unresolved": len(result.issues), "proposed_actions": len(result.actions),
                              "coverage_qualified": False, "audit_hash": content_hash(result)}))
        return 1 if result.has_unresolved else 0
    except (ValueError, OSError, TypeError, KeyError):
        # Do not expose parser strings from supplied review artifacts either.
        print("Action audit error: malformed input or immutable output/cache conflict", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
