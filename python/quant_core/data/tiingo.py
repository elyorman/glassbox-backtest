"""Tiingo end-of-day prices: offline normalization into a raw-price Snapshot.

Raw open/high/low/close/volume are the execution prices and raw share volume.
Tiingo reports cash dividends (`divCash`, ex-date) and splits (`splitFactor`,
new/old shares) on each bar; `adjClose` is used only to cross-check them.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
import re

from quant_core.data import Bar, DataMetadata, Dividend, Security, Snapshot, Split, number
from quant_core.data.adjustments import provider_adjustment_disagreements
from quant_core.data.remote import unique_object

TICKER = re.compile(r"[A-Z][A-Z0-9-]{0,9}")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})T00:00:00(?:\.0+)?Z")
_FIELDS = frozenset(("date", "open", "high", "low", "close", "volume", "adjClose", "divCash", "splitFactor"))
NO_PAYMENT_DATES = "Tiingo supplies no dividend payment dates; dividends are assumed paid on the ex-date."
PROVIDER_ACTIONS = ("Corporate actions are Tiingo's reported cash dividends and splits, cross-checked against "
                    "Tiingo's adjusted close; they are not verified against an independent source.")
CURRENT_TICKERS = "Securities are identified by current ticker; renamed or delisted tickers are not tracked."


def check_ticker(value):
    if not isinstance(value, str) or TICKER.fullmatch(value) is None:
        raise ValueError("Tiingo tickers are 1-10 upper-case letters, digits or '-', starting with a letter")
    return value


def last_final_day(retrieved_at: datetime) -> date:
    """Latest session whose bar is final when retrieved: 23:00 UTC is 18:00 New York standard time
    (19:00 in daylight time), after the close and Tiingo's end-of-day update."""
    return (retrieved_at.astimezone(timezone.utc) - timedelta(hours=23)).date()


@dataclass(frozen=True)
class TiingoResponse:
    raw: bytes = field(repr=False)
    retrieved_at: datetime


@dataclass(frozen=True)
class _Row:
    day: date
    bar: Bar
    adjusted_close: Decimal
    dividend: Decimal
    split_factor: Decimal
    split: tuple[int, int] | None  # Exact (new, old) share counts.


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError("Expected a JSON number")
    return number(value)


def _split_counts(factor):
    exact = Fraction(factor)
    counts = exact.limit_denominator(1000)
    if counts <= 0 or abs(exact / counts - 1) > Fraction(1, 100000):
        raise ValueError("Split factor is not a ratio of whole share counts")
    return counts.numerator, counts.denominator


def price_rows(raw, ticker, retrieved_at, start=None, end=None):
    """Validated rows of one prices response; a bar that may still change is refused."""
    try:
        rows = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique_object)
    except ValueError:
        raise ValueError(f"Tiingo prices for {ticker} are not valid JSON") from None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Tiingo prices for {ticker} are not a nonempty daily array")
    final = last_final_day(retrieved_at)
    parsed = []
    for index, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict) or not _FIELDS <= set(row):
                raise ValueError
            match = _DATE.fullmatch(row["date"]) if isinstance(row["date"], str) else None
            if match is None:
                raise ValueError
            day = date.fromisoformat(match.group(1))
            volume = _decimal(row["volume"])
            if volume != volume.to_integral_value():
                raise ValueError
            bar = Bar(ticker, day, *(_decimal(row[name]) for name in ("open", "high", "low", "close")), volume)
            adjusted, dividend, factor = (_decimal(row[name]) for name in ("adjClose", "divCash", "splitFactor"))
            if adjusted <= 0 or dividend < 0 or factor <= 0:
                raise ValueError
            split = None if factor == 1 else _split_counts(factor)
        except (ValueError, TypeError, ArithmeticError):
            raise ValueError(f"Invalid Tiingo price row {index} for {ticker}") from None
        if day > final:
            raise ValueError(f"Tiingo bar {day} for {ticker} may be a partial session: it was retrieved before "
                             "18:00 New York time that day. Request an end date before today.")
        if (start is not None and day < start) or (end is not None and day > end):
            raise ValueError(f"Tiingo bar {day} for {ticker} lies outside the requested dates")
        parsed.append(_Row(day, bar, adjusted, dividend, factor, split))
    if any(a.day >= b.day for a, b in zip(parsed, parsed[1:])):
        raise ValueError(f"Tiingo bars for {ticker} are not in ascending unique date order")
    return tuple(parsed)


def metadata_exchange(raw, ticker):
    """The exchange named in a Tiingo metadata response for `ticker`."""
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
    except ValueError:
        raise ValueError(f"Tiingo metadata for {ticker} is not valid JSON") from None
    if (not isinstance(value, dict) or not isinstance(value.get("ticker"), str)
            or value["ticker"].upper() != ticker or not isinstance(value.get("exchangeCode"), str)
            or not value["exchangeCode"].strip()):
        raise ValueError(f"Tiingo metadata for {ticker} lacks its ticker or exchange")
    return value["exchangeCode"].strip()


def _crosscheck(ticker, rows, actions):
    observations = tuple((row.day, row.bar.close, row.adjusted_close) for row in rows)
    try:
        found = provider_adjustment_disagreements(observations, actions)
    except ArithmeticError:
        raise ValueError(f"Tiingo adjClose for {ticker} could not be compared numerically") from None
    mismatches = [f for f in found if f.reason == "factor_mismatch"]
    if mismatches:
        first = mismatches[0]
        raise ValueError(f"Tiingo adjClose for {ticker} disagrees with its reported dividends and splits in "
                         f"{len(mismatches)} session pair(s) (first {first.previous_session} to {first.session}: "
                         f"provider factor {first.implied_factor:.6g}, reported {first.expected_factor:.6g})")
    if found:
        return [f"Tiingo adjClose for {ticker} is too coarsely rounded to verify {len(found)} session pair(s)."]
    return []


@dataclass(frozen=True)
class TiingoJsonSource:
    """Saved Tiingo responses for a static ticker list; the calendar is one ticker's trading days."""
    prices: Mapping[str, TiingoResponse]
    metadata: Mapping[str, TiingoResponse]
    universe_policy: str = "supplied_static_etf_list"
    calendar_ticker: str = "SPY"

    def load(self) -> Snapshot:
        if (not isinstance(self.prices, Mapping) or not isinstance(self.metadata, Mapping) or not self.prices
                or set(self.prices) != set(self.metadata)):
            raise ValueError("Tiingo source requires price and metadata responses for the same tickers")
        responses = tuple(self.prices.values()) + tuple(self.metadata.values())
        if any(not isinstance(r, TiingoResponse) for r in responses):
            raise ValueError("Tiingo source requires TiingoResponse values")
        if self.calendar_ticker not in self.prices:
            raise ValueError(f"Calendar ticker {self.calendar_ticker} must be among the downloaded tickers")
        bars, actions, securities, dates = [], [], [], {}
        hashes = []
        limitations = [NO_PAYMENT_DATES, PROVIDER_ACTIONS, CURRENT_TICKERS,
                       f"Trading calendar is the {self.calendar_ticker} trading days in the Tiingo response; "
                       "no exchange calendar is consulted."]
        for ticker in sorted(self.prices):
            check_ticker(ticker)
            exchange = metadata_exchange(self.metadata[ticker].raw, ticker)
            rows = price_rows(self.prices[ticker].raw, ticker, self.prices[ticker].retrieved_at)
            reported = []
            for row in rows:
                bars.append(row.bar)
                if row.split is not None:
                    new, old = row.split
                    reported.append(Split(ticker, row.day, new_shares=new, old_shares=old))
                    if Fraction(new, old) != Fraction(row.split_factor):
                        limitations.append(f"Tiingo split factor {row.split_factor} for {ticker} on {row.day} "
                                           f"is treated as {new}-for-{old}.")
                if row.dividend:
                    reported.append(Dividend(ticker, row.day, row.dividend, row.day))
            limitations.extend(_crosscheck(ticker, rows, reported))
            actions.extend(reported)
            securities.append(Security(ticker, ticker, exchange, listed_on=rows[0].day))
            dates[ticker] = {row.day for row in rows}
            hashes.append((f"tiingo:prices:{ticker}", sha256(self.prices[ticker].raw).hexdigest()))
            hashes.append((f"tiingo:metadata:{ticker}", sha256(self.metadata[ticker].raw).hexdigest()))
        sessions = tuple(sorted(dates[self.calendar_ticker]))
        calendar = set(sessions)
        for ticker, days in sorted(dates.items()):
            outside = sorted(days - calendar)
            if outside:
                raise ValueError(f"Tiingo bar {outside[0]} for {ticker} is not a {self.calendar_ticker} trading day")
        metadata = DataMetadata("tiingo", max(r.retrieved_at for r in responses), self.universe_policy, True,
                                f"{self.calendar_ticker.lower()}_trading_days_tiingo", "raw",
                                tuple(dict.fromkeys(limitations)), tuple(hashes))
        return Snapshot(sessions, tuple(bars), metadata, tuple(securities), tuple(actions))
