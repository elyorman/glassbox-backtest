"""A frozen research dataset: Tiingo prices and Treasury cash rates saved once, identified by one hash.

The directory holds snapshot.json, rates.json and manifest.json (written last).
The manifest records every response's SHA-256 and retrieval time, the code that
built the dataset, and `dataset_id`, a hash over the whole manifest. The raw
responses themselves stay in the download caches under those hashes.
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
from quant_core.data.tiingo import TiingoJsonSource, check_ticker, metadata_start, price_rows
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
    """Treasury years to `end`, then SPY to `end`, then each other ticker to SPY's last session; nothing is saved.

    Ending the other requests on SPY's last session means they end on a trading
    day, so their responses are final and cached even when `end` is a weekend.
    """
    tickers = tuple(sorted(set(tickers)))
    for ticker in tickers:
        check_ticker(ticker)
    if CALENDAR_TICKER not in tickers:
        raise ValueError(f"A dataset needs {CALENDAR_TICKER}, whose trading days are its calendar")
    if type(end) is not date:
        raise ValueError("Dataset end must be a date")
    years = tuple(treasury.year(year) for year in range(FIRST_YEAR, end.year + 1))  # Fails before Tiingo is used.
    prices, metadata, requests, remaining, last = {}, {}, [], [], None
    for ticker in (CALENDAR_TICKER,) + tuple(t for t in tickers if t != CALENDAR_TICKER):
        until = end if ticker == CALENDAR_TICKER else last
        if until is None:
            remaining.append(ticker)  # Without SPY's last session no other request can be formed.
            continue
        try:
            metadata[ticker] = tiingo.metadata(ticker)
            start = metadata_start(metadata[ticker].raw, ticker)
            if start > until:
                raise ValueError(f"starts trading on {start}, after the dataset end {until}")
            prices[ticker] = tiingo.prices(ticker, start, until)
        except RequestBudgetExhausted:
            remaining.append(ticker)  # Later tickers may still be cached, so keep going.
            continue
        except ValueError as exc:
            raise ValueError(f"{ticker}: {exc}") from None
        if ticker == CALENDAR_TICKER:
            last = price_rows(prices[ticker].raw, ticker, prices[ticker].retrieved_at)[-1].day
        requests += [_record(metadata[ticker], endpoint="metadata", ticker=ticker),
                     _record(prices[ticker], endpoint="prices", ticker=ticker, start=start.isoformat(),
                             end=until.isoformat())]
    if remaining:
        raise DownloadIncomplete(remaining)
    snapshot = TiingoJsonSource(prices, metadata).load()
    report = check_quality(snapshot)
    errors = [issue for issue in report.issues if issue.severity == "error"]
    if errors:
        first = errors[0]
        raise ValueError(f"Data quality error: {first.code} for {first.security_id} on {first.session}; "
                         "the dataset was not saved")
    combined = cash_rate_series(years)
    rates = CashRateSeries(combined.source, combined.series, combined.retrieved_at,
                           tuple(o for o in combined.observations if o[0] <= last))
    for day in snapshot.sessions:
        try:
            rates.rate_before(day)  # Runs refuse a missing or stale rate; find out now, not at study time.
        except ValueError as exc:
            raise ValueError(f"Treasury rates do not cover the dataset: {exc}; the dataset was not saved") from None
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
        "code_hash": code_hash(), "tickers": list(tickers), "requested_end": end.isoformat(),
        "end": last.isoformat(), "requests": requests,
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


def _verify(dataset):
    """The manifest matches its ID, and the snapshot and rates match the manifest."""
    manifest = dataset.manifest
    body = {key: value for key, value in manifest.items() if key != "dataset_id"}
    if manifest.get("schema_version") != 1 or manifest.get("dataset_id") != content_hash(body):
        raise ValueError("Dataset manifest integrity check failed")
    if dataset.snapshot.dataset_hash != manifest["snapshot"]["dataset_hash"]:
        raise ValueError("Dataset snapshot.json does not match its manifest")
    if content_hash(dataset.rates) != manifest["rates"]["rates_hash"]:
        raise ValueError("Dataset rates.json does not match its manifest")


def existing_directory_error(directory: Path) -> str | None:
    """Why `directory` cannot receive a new dataset, or None when it does not exist."""
    directory = Path(directory)
    if not directory.exists():
        return None
    names = {path.name for path in directory.iterdir()} if directory.is_dir() else set()
    if names and all(name in ("snapshot.json", "rates.json") or name.startswith((".snapshot-", ".rates-"))
                     for name in names):
        return (f"Dataset directory {directory} exists but is incomplete (no manifest.json): a save failed; "
                "delete it and run again")
    return f"Dataset directory {directory} already exists; datasets are never overwritten"


def save_dataset(directory: Path, dataset: Dataset) -> str:
    """Write a new dataset directory; an existing one is never overwritten. Returns the dataset ID."""
    directory = Path(directory)
    _verify(dataset)
    try:
        directory.mkdir(parents=True)
    except FileExistsError:
        raise ValueError(existing_directory_error(directory)) from None
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
        if not isinstance(manifest, dict):
            raise ValueError("Dataset manifest integrity check failed")
        body = {key: value for key, value in manifest.items() if key != "dataset_id"}
        if manifest.get("schema_version") != 1 or manifest.get("dataset_id") != content_hash(body):
            raise ValueError("Dataset manifest integrity check failed")  # Before reading the large snapshot.
        dataset = Dataset(load_snapshot(directory / "snapshot.json"), load_cash_rates(directory / "rates.json"),
                          manifest)
        _verify(dataset)
        return dataset
    except OSError as exc:
        raise ValueError(f"Dataset {directory} is incomplete or unreadable: {exc}") from None
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed dataset: {exc}") from exc
