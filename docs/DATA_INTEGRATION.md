# Provider integration: Tiingo, Treasury, EODHD and local Parquet

This implements part of PR-01's provider/local-file contract. The tests establish
normalization, exact values, identity/calendar boundaries, provenance and local
integrity. They do not establish live-provider reliability, historical coverage,
licensing, empirical strategy quality or release readiness.

The `eodhd_actions` module audits saved split/dividend responses into
reviewed action proposals with unresolved rows listed; it does not qualify
coverage by itself.

## Tiingo (tester release)

`quant_core.data.tiingo` is the tester release's only market-data provider.
Users supply their own Tiingo key; the free tier allows 50 requests an hour,
1,000 a day and 500 different symbols a month.

- **Download.** `TiingoClient(api_token, cache_dir)` has `prices(ticker, start,
  end)` and `metadata(ticker)`; each sends one request, without redirects or
  retries. The key travels only in the `Authorization` header and never appears
  in URLs, cache files, manifests or error messages. A validated price response
  is cached, and its request never sent again, once it contains the end date's
  bar or the end date is at least seven days before the latest final day;
  otherwise the request is sent again next time. Metadata is always cached.
  Every validated response body is kept under its SHA-256; revised data needs a
  new cache directory. Errors say what to do: key rejected (HTTP 401/403),
  unknown ticker (404), rate limit (429: resume later; cached tickers are kept).
- **Normalization.** `TiingoJsonSource(prices, metadata).load()` turns saved
  responses into a raw-price `Snapshot`:
  - Bars use raw `open`, `high`, `low`, `close` and raw share `volume`
    (`adjustment_policy = raw`).
  - `divCash > 0` becomes a `Dividend` on the ex-date. Tiingo gives no payment
    date, so payment is assumed on the ex-date, and the snapshot says so.
  - `splitFactor ≠ 1` becomes a `Split` with exact share counts (both at most
    1000; a 1-for-1 result is refused). A factor with float noise, such as EEM's
    3.000003, is treated as 3-for-1, and the snapshot says so.
  - Corporate actions are declared complete and cross-checked against
    `adjClose` using Tiingo's own dividend formula, ex-date close / (ex-date
    close + dividend), within 0.001% plus rounding; an unexplained adjustment
    stops the import, and pairs rounded too coarsely to check are disclosed.
  - The calendar is one ticker's trading days (`SPY` by default); a bar on any
    other day stops the import. A security's listing date is its first bar.
  - A bar is accepted only if it was retrieved after 23:00 UTC on its date
    (18:00 New York standard time, 19:00 daylight time), so a partial session
    never enters a snapshot. When each day's data is final is an open question
    for Tiingo (see [the roadmap](ROADMAP.md)).
- **Checked on real data (2026-10-12, current rule).** SPY, IEF, TLT, GLD, EFA,
  EEM, VNQ, XLK and BIL from inception, and AAPL around its 2020 split: 55,828
  bars and 1,116 corporate actions with no cross-check mismatches; each of the
  1,110 dividends, removed one at a time, is detected; no invalid OHLC rows;
  every ticker's dates inside SPY's; the nine ETFs have no data-quality errors;
  raw volume confirmed unadjusted (AAPL's pre-split volume is a quarter of
  `adjVolume`). Tiingo's adjusted closes follow its dividend formula to about
  1e-11.

There is no download command yet; it is roadmap step E.

## Treasury cash rates

`quant_core.data.treasury` reads the U.S. Treasury Daily Par Yield Curve, one
public CSV per year (1990 onward). `TreasuryClient(cache_dir).year(year)`
downloads a year. A completed year (from 8 January of the next year) must cover
early January to late December, or the download is refused and nothing is
cached; once cached it is frozen, and a later Treasury correction needs a new
cache directory. The current year is downloaded
each time. `parse_year` reads the "3 Mo" column by name (the
column set changes between years), converts percent to a fraction and skips
blank cells (holidays and a few missing days). `cash_rate_series(responses)`
combines years into the `CashRateSeries` that `RunConfig.cash_rates` takes; see
[the backtester](BACKTESTER.md). From 2003 to 2026 the latest observation before
any SPY session was at most 4 days old; the engine refuses one older than 10
days.

## EODHD price semantics

The [official daily-data API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
documents raw `open`, `high`, `low`, `close`, an adjusted `adjusted_close`, and
split-adjusted `volume`. The adapter uses the raw OHLC fields for execution and
retains provider volume unchanged. Every imported snapshot discloses that
historical liquidity and dollar-volume qualification need independent review.
It does not silently reconstruct historical volume from an incomplete action
history. Adjusted close remains in original response bytes and is never an execution
price or signal series. The importer uses it only to cross-check supplied
splits and cash dividends: between consecutive sessions the provider's implied
adjustment must match the declared actions within 0.1% plus half a unit of the
finest decimal it prints; sessions whose rounding is too coarse to verify are
reported as such (disclosed, not fatal), and sessions without a usable or
plausible adjusted close are excluded visibly. Only real factor mismatches stop
an import with complete actions. Because limitations are part of the dataset
hash, re-importing an existing EODHD cache with 0.5.2 yields a new dataset hash. For adjusted values below about 0.1 a 4-decimal series is rounded more
coarsely than 0.1%, so a small missing dividend there can pass; splits remain
checked. With actions declared complete, a disagreement stops the import and
names the ticker and date; with incomplete actions it is recorded as a
limitation. Missing `adjusted_close` skips the check visibly. Imported snapshots
carry `adjustment_policy = raw_prices_split_adjusted_volume`; strategies and
risk-enabled runs refuse them until raw volume is reconstructed from reviewed
complete splits (not yet implemented). EODHD snapshots imported before 0.5.2
are labelled `raw` but carry the importer's split-adjusted-volume limitation;
they are refused the same way. Re-import them from the raw response cache. CSV
imports cannot yet declare a split-adjusted volume basis; that option is
planned before customer CSV import ships. The guard runs in strategy and campaign
preflight and risk-enabled runs; a future scanner or any direct caller of
`RuleStrategy.evaluate()` must call `require_raw_volume` itself, and custom
order sources cannot yet see the volume basis through `SessionContext`.

An explicit calendar and stable security registry must come from reviewed
inputs. Ticker-to-security mapping is supplied separately; dates or current
constituents are never used to manufacture calendar sessions, listing dates,
delistings or historical index membership. Missing bars remain missing for
`check_quality` to report.

## Offline original-response import

`EodhdJsonSource` implements the `SnapshotSource.load()` contract. It accepts
original JSON bytes rather than already-decoded Python floats. Decimal JSON
numbers are parsed directly as `Decimal`; invalid OHLC, fractional/negative
volume, duplicate dates/JSON fields, non-ISO dates, future observations relative
to retrieval time, unknown identities and calendar/lifetime violations fail.
Provider error messages are never echoed in diagnostics.

```python
from datetime import date, datetime
from pathlib import Path

from quant_core.data import DataMetadata, Security
from quant_core.data.eodhd import EodhdJsonSource
from quant_core.data.quality import check_quality

# Example reviewed inputs; use your dataset's actual original retrieval time,
# independent calendar, stable identities and universe policy.
metadata = DataMetadata(
    source="eodhd",
    retrieved_at=datetime.fromisoformat("2024-01-04T00:00:00+00:00"),
    universe_policy="reviewed_custom_panel_not_historical_index",
    actions_complete=False,
    calendar_name="reviewed_explicit_sessions",
)
data = EodhdJsonSource(
    responses={"SYNTH.US": Path("local/eodhd-response.json").read_bytes()},
    ticker_security_ids={"SYNTH.US": "stable-security-1"},
    sessions=(date(2024, 1, 2), date(2024, 1, 3)),
    securities=(Security("stable-security-1", "SYNTH", "XNAS"),),
    metadata=metadata,
    cache_dir=Path("local/raw/eodhd/version-1"),
).load()
health = check_quality(data)
```

The optional raw cache stores the exact original bytes as `<sha256>.json`.
Existing observations are verified and reused; corrupted entries fail without
replacement. Fully written temporary files are linked atomically, and caught
publication failures remove temporary files. No response text or token becomes
a cache filename. Metadata binds original response hashes, calendar, registry,
ticker mapping and supplied actions. Source data stays separate from normalized
snapshots and quality checks.

## Explicit API download

`EodhdClient` makes a single explicit daily-price request to
`https://eodhd.com/api/eod/{ticker}` with `fmt=json`, `period=d`, `order=a` and
inclusive `from`/`to` date bounds. The caller supplies the token; the library does
not discover credentials or read `.env`. Constructing it does not download.

```python
from dataclasses import replace
from quant_core.data.eodhd import EodhdClient

# customer_token is supplied by the caller's credential interface.
client = EodhdClient(customer_token, Path("local/raw/eodhd/version-1"))
download = client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))
# Supply download.raw to EodhdJsonSource and preserve this timestamp:
metadata = replace(metadata, retrieved_at=download.retrieved_at)
```

The original successful response and retrieval timestamp are bound to a
token-free request manifest named `<request-sha256>.request.json`. A repeated
request in the same cache version reads those original bytes without another
API call. To intentionally retrieve revisions, choose a new cache version;
existing observations are never refreshed in place. Cached bytes are checked
against both their digest and the requested/date/row contract. Incomplete or
corrupted caches fail instead of silently downloading replacement data.

Authentication/entitlement, rate-limit and transport failures return safe
diagnostics without URLs, tokens or provider bodies. Redirects are refused.
No retries, corporate-action requests, bulk downloads or purchases occur
implicitly. Each explicit uncached request may consume provider entitlement;
the offline tests issue no vendor requests. Responses above 64 MiB are rejected.

## Reviewed corporate actions

The [official action feed](https://eodhd.com/financial-apis/api-splits-dividends)
can have unknown payable dates and distinguishes historical unadjusted dividend
amounts from restated amounts. This integration deliberately accepts reviewed
domain action objects, not an automatic interpretation of that feed.

Pass `actions=(Split(...), Dividend(...), CashDelisting(...))` and
`actions_review_hash=<sha256 of reviewed evidence>` to import supplied actions.
Exact splits support `Split(id, day, new_shares=1, old_shares=3)`; retain the two
integer counts rather than truncating a nonterminating ratio yourself.
`Dividend` requires the historical amount and a known explicit payable date.
Do not substitute ex-date for an unknown payable date or guess a delisting
settlement. Unsupported/unknown events remain a visible coverage limitation.

`actions_complete=True` is a caller's reviewed coverage assertion and requires
an evidence hash even for a reviewed action-free period. Supplied actions also
require review evidence when coverage is partial. Without a reviewed complete
set, `actions_complete` stays false and metadata explicitly discloses missing
corporate-action outcomes. Neither an adjusted-close column nor a price jump
proves completeness.

## Optional Parquet bundles

From the repository root, import saved responses using explicit local inputs:

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.cli import-eodhd \
  --response SYNTH.US=local/eodhd-response.json \
  --security-map SYNTH.US=stable-security-1 \
  --calendar local/calendar.csv --securities local/securities.csv \
  --retrieved-at 2024-01-04T00:00:00+00:00 \
  --universe-policy reviewed_custom_panel_not_historical_index \
  --calendar-name reviewed_explicit_sessions \
  --raw-cache local/raw/eodhd/version-1 \
  --output local/eodhd.snapshot.json

PYTHONPATH=python .venv/bin/python -m quant_core.cli export-parquet \
  local/eodhd.snapshot.json --output local/eodhd-parquet-v1
PYTHONPATH=python .venv/bin/python -m quant_core.cli inspect local/eodhd-parquet-v1
PYTHONPATH=python .venv/bin/python -m quant_core.cli import-parquet \
  local/eodhd-parquet-v1 --output local/eodhd-roundtrip.json
```

Repeat `--response` and `--security-map` for each ticker. `--parquet` on an
import writes a bundle directly. `--actions local/actions.csv` requires
`--action-review local/review.txt`; `--actions-complete` requires that review
even for an action-free period. The review's hash binds supplied evidence,
without automatically qualifying it. `--strict-discontinuities` blocks unresolved
suspicious gaps; no import rewrites source observations. The API download remains
an explicit Python call so credentials need not appear in shell arguments.

Install the optional dependency in the repository environment:

```bash
.venv/bin/python -m pip install -e '.[parquet]'
```

Importing the data/core modules does not require PyArrow. Attempting Parquet
operations without it gives an actionable missing-dependency error. JSON
snapshot workflows keep the existing core-only dependency contract.

```python
from quant_core.data.parquet import (
    ParquetSource, load_parquet_snapshot, save_parquet_snapshot,
)

output = Path("local/snapshots/reviewed-version-1")
save_parquet_snapshot(data, output)
restored = ParquetSource(output).load()
assert restored.dataset_hash == data.dataset_hash
```

A bundle directory contains exactly `bars.parquet` and `manifest.json`:

- `bars.parquet` uses required string columns for identity, ISO session date and
  decimal OHLCV. Arbitrary decimal precision is preserved as text without
  binary floats or a fixed decimal precision/scale cap.
- The manifest binds every Parquet byte by SHA-256 and size, its row count,
  snapshot header/metadata/security registry/actions, and the original snapshot
  hash. The manifest envelope binds its canonical contents with a further hash.
- Loading verifies the file set, regular files, hashes, strict Arrow schema,
  null/value/date constraints, shared snapshot-schema validation and original
  normalized dataset hash before returning a snapshot. Hashes detect integrity
  failures; they are not signatures authenticating an untrusted producer.

JSON schema 1 snapshots and schema 2 exact-share-count actions round-trip through
Parquet without changing the normalized dataset hash. Original provider response
bytes stay in the separate raw cache; the bundle preserves their provenance
hashes without copying raw observations or credentials.

Writers stage and flush all bytes before reserving the output directory
exclusively, publish bars first and the manifest last, and never replace an
existing file or directory, including an empty directory. Caught publication
failures remove the created output. A process/power interruption during
publication may leave an incomplete directory; imports reject it, and exports
will not overwrite it. Keep generated bundles/cache versions in ignored `local/`
storage. Parquet here is a full-snapshot import/export contract; DuckDB, indexed
queries, partition pruning, UI credential flows and provider qualification remain
additional work.
