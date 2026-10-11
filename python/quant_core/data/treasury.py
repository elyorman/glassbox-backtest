"""U.S. Treasury daily par yield curve: the 3-month yield as the idle-cash rate.

Public data, no key. One CSV per calendar year, newest row first, values in
percent; the column set changes between years, so columns are read by name.
Completed years are cached by request. The current year grows every day, so it
is downloaded again on each call; every body is still kept under its SHA-256.
"""

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import io
from pathlib import Path

from quant_core.data import number
from quant_core.data.rates import CashRateSeries
from quant_core.data.remote import RequestCache, fetch, publish_bytes

SOURCE = "us_treasury_daily_par_yield_curve"
SERIES = "treasury_3_month_par_yield"
COLUMN = "3 Mo"
FIRST_YEAR = 1990
URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
       "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
       "&field_tdr_date_value={year}&page&_format=csv")


def _now():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TreasuryResponse:
    year: int
    raw: bytes = field(repr=False)
    retrieved_at: datetime


def parse_year(raw: bytes, year: int) -> tuple[tuple[date, Decimal], ...]:
    """Ascending 3-month observations as fractions; a blank cell means no value that day."""
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fieldnames = reader.fieldnames
        rows = list(reader)
    except (UnicodeError, csv.Error):
        raise ValueError(f"Treasury {year} response is not a CSV file") from None
    if not fieldnames or "Date" not in fieldnames or COLUMN not in fieldnames:
        raise ValueError(f"Treasury {year} CSV lacks the Date and {COLUMN} columns")
    observations = []
    for line, row in enumerate(rows, 2):
        value = row[COLUMN]
        try:
            day = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            if value is None or not value.strip():
                continue
            rate = number(value.strip()) / 100
        except (TypeError, ValueError):
            raise ValueError(f"Invalid Treasury {year} CSV line {line}") from None
        if day.year != year:
            raise ValueError(f"Treasury {year} CSV line {line} is dated {day}")
        observations.append((day, rate))
    observations.sort()
    if len({day for day, _ in observations}) != len(observations):
        raise ValueError(f"Treasury {year} CSV repeats a date")
    return tuple(observations)


def cash_rate_series(responses) -> CashRateSeries:
    """Combine yearly responses into one series; years need not be supplied in order."""
    responses = tuple(responses)
    if not responses or any(not isinstance(r, TreasuryResponse) for r in responses):
        raise ValueError("Treasury cash rates require yearly TreasuryResponse values")
    if len({r.year for r in responses}) != len(responses):
        raise ValueError("Duplicate Treasury year")
    observations = sorted(o for r in responses for o in parse_year(r.raw, r.year))
    return CashRateSeries(SOURCE, SERIES, max(r.retrieved_at for r in responses), tuple(observations))


@dataclass(frozen=True)
class TreasuryClient:
    cache_dir: Path
    timeout: int = 30

    def __post_init__(self):
        if type(self.timeout) is not int or self.timeout <= 0:
            raise ValueError("Treasury timeout must be a positive number of seconds")
        object.__setattr__(self, "cache_dir", Path(self.cache_dir))

    def year(self, year: int) -> TreasuryResponse:
        now = _now()
        if type(year) is not int or not FIRST_YEAR <= year <= now.year:
            raise ValueError(f"Treasury year must be an integer from {FIRST_YEAR} to {now.year}")
        # A week of grace lets late year-end publications land before a year is treated as final.
        final = now.date() >= date(year + 1, 1, 8)
        cache = RequestCache(self.cache_dir, "Treasury", ".csv")
        request = {"provider": "us_treasury", "dataset": "daily_treasury_yield_curve", "year": year}
        if final:
            cached = cache.load(request)
            if cached is not None:
                parse_year(cached[0], year)
                return TreasuryResponse(year, *cached)
        raw = fetch(URL.format(year=year), {"Accept": "text/csv", "User-Agent": "quant-platform-core"},
                    self.timeout, "Treasury")
        retrieved_at = _now()
        parse_year(raw, year)
        if final:
            cache.store(request, raw, retrieved_at)
        else:
            publish_bytes(raw, self.cache_dir / (sha256(raw).hexdigest() + ".csv"), "Treasury")
        return TreasuryResponse(year, raw, retrieved_at)
