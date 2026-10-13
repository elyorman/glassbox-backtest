"""A frozen research dataset: Tiingo prices and Treasury cash rates saved once, identified by one hash.

The directory holds snapshot.json, rates.json and manifest.json (written last).
The manifest records every response's SHA-256 and retrieval time, the code that
built the dataset, and `dataset_id`, a hash over the whole manifest.
"""

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path

from quant_core import __version__
from quant_core.data import Snapshot
from quant_core.data.quality import check_quality
from quant_core.data.rates import CashRateSeries
from quant_core.data.remote import RequestBudgetExhausted
from quant_core.data.storage import load_cash_rates, load_snapshot, save_cash_rates, save_snapshot
from quant_core.data.tiingo import TiingoJsonSource, check_ticker, metadata_start
from quant_core.data.treasury import FIRST_YEAR, cash_rate_series
from quant_core.provenance import canonical_json, code_hash, content_hash

CALENDAR_TICKER = "SPY"


class DownloadIncomplete(ValueError):
    """The request budget ran out; `remaining` lists the tickers still to download."""

    def __init__(self, remaining):
        self.remaining = tuple(remaining)
        super().__init__(f"{len(self.remaining)} ticker(s) still to download: {', '.join(self.remaining)}. "
                         "Finished requests are cached; run the same command again after an hour.")


@dataclass(frozen=True)
class Dataset:
    snapshot: Snapshot
    rates: CashRateSeries
    manifest: dict


def _record(response, **fields):
    return {**fields, "sha256": sha256(response.raw).hexdigest(), "retrieved_at": response.retrieved_at.isoformat()}


def download_dataset(tickers, end, tiingo, treasury) -> Dataset:
    """Prices from each ticker's first trading day to `end`, and Treasury rates to `end`; nothing is saved."""
    tickers = tuple(sorted(set(tickers)))
    for ticker in tickers:
        check_ticker(ticker)
    if CALENDAR_TICKER not in tickers:
        raise ValueError(f"A dataset needs {CALENDAR_TICKER}, whose trading days are its calendar")
    if type(end) is not date:
        raise ValueError("Dataset end must be a date")
    prices, metadata, requests, remaining = {}, {}, [], []
    for ticker in tickers:
        try:
            metadata[ticker] = tiingo.metadata(ticker)
            start = metadata_start(metadata[ticker].raw, ticker)
            if start > end:
                raise ValueError(f"{ticker} starts trading on {start}, after the dataset end {end}")
            prices[ticker] = tiingo.prices(ticker, start, end)
        except RequestBudgetExhausted:
            remaining.append(ticker)  # Later tickers may still be cached, so keep going.
            continue
        requests += [_record(metadata[ticker], endpoint="metadata", ticker=ticker),
                     _record(prices[ticker], endpoint="prices", ticker=ticker, start=start.isoformat(),
                             end=end.isoformat())]
    if remaining:
        raise DownloadIncomplete(remaining)
    snapshot = TiingoJsonSource(prices, metadata).load()
    report = check_quality(snapshot)
    errors = [issue for issue in report.issues if issue.severity == "error"]
    if errors:
        first = errors[0]
        raise ValueError(f"Data quality error: {first.code} for {first.security_id} on {first.session}; "
                         "the dataset was not saved")
    years = tuple(treasury.year(year) for year in range(FIRST_YEAR, end.year + 1))
    combined = cash_rate_series(years)
    rates = CashRateSeries(combined.source, combined.series, combined.retrieved_at,
                           tuple(o for o in combined.observations if o[0] <= end))
    warnings = {}
    for issue in report.issues:
        warnings[issue.code] = warnings.get(issue.code, 0) + 1
    securities = {}
    for bar in snapshot.bars:
        entry = securities.setdefault(bar.security_id, {"first_session": bar.session.isoformat(), "bars": 0})
        entry["last_session"] = bar.session.isoformat()
        entry["bars"] += 1
    manifest = {
        "schema_version": 1, "kind": "tiingo_treasury_dataset", "program_version": __version__,
        "code_hash": code_hash(), "tickers": list(tickers), "end": end.isoformat(), "requests": requests,
        "treasury_years": [_record(response, year=response.year) for response in years],
        "snapshot": {"file": "snapshot.json", "dataset_hash": snapshot.dataset_hash, "sessions": len(snapshot.sessions),
                     "first_session": snapshot.sessions[0].isoformat(),
                     "last_session": snapshot.sessions[-1].isoformat(), "actions": len(snapshot.actions)},
        "securities": securities,
        "rates": {"file": "rates.json", "rates_hash": content_hash(rates), "series": rates.series,
                  "observations": len(rates.observations), "first": rates.observations[0][0].isoformat(),
                  "last": rates.observations[-1][0].isoformat()},
        "quality_warnings": warnings,
    }
    manifest["dataset_id"] = content_hash(manifest)
    return Dataset(snapshot, rates, manifest)


def save_dataset(directory: Path, dataset: Dataset) -> str:
    """Write a new dataset directory; an existing one is never overwritten. Returns the dataset ID."""
    directory = Path(directory)
    try:
        directory.mkdir(parents=True)
    except FileExistsError:
        raise ValueError(f"Dataset directory {directory} already exists; datasets are never overwritten") from None
    save_snapshot(dataset.snapshot, directory / "snapshot.json")
    save_cash_rates(dataset.rates, directory / "rates.json")
    with open(directory / "manifest.json", "x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(dataset.manifest) + "\n")  # Written last: its presence marks completion.
        stream.flush()
        os.fsync(stream.fileno())
    return dataset.manifest["dataset_id"]


def load_dataset(directory: Path) -> Dataset:
    """Reload a dataset after checking the manifest, the snapshot and the rates against each other."""
    directory = Path(directory)
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        body = {key: value for key, value in manifest.items() if key != "dataset_id"}
        if manifest.get("schema_version") != 1 or manifest.get("dataset_id") != content_hash(body):
            raise ValueError("Dataset manifest integrity check failed")
        snapshot = load_snapshot(directory / "snapshot.json")
        rates = load_cash_rates(directory / "rates.json")
        if (snapshot.dataset_hash != manifest["snapshot"]["dataset_hash"]
                or content_hash(rates) != manifest["rates"]["rates_hash"]):
            raise ValueError("Dataset files do not match its manifest")
        return Dataset(snapshot, rates, manifest)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed dataset: {exc}") from exc
