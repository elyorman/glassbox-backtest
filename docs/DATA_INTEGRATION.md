# EODHD and local Parquet integration

This implements part of PR-01's provider/local-file contract. The tests establish
normalization, exact values, identity/calendar boundaries, provenance and local
integrity. They do not establish live-provider reliability, historical coverage,
licensing, empirical strategy quality or release readiness.

Version 0.5.1 adds [saved split/dividend auditing and frozen input preflight](DATA_QUALIFICATION.md).
It produces reviewed action proposals and concrete unresolved rows without
automatically qualifying their coverage or the account.

## EODHD price semantics

The [official daily-data API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
documents raw `open`, `high`, `low`, `close`, an adjusted `adjusted_close`, and
split-adjusted `volume`. The adapter uses the raw OHLC fields for execution and
retains provider volume unchanged. Every imported snapshot discloses that
historical liquidity and dollar-volume qualification need independent review.
It does not silently reconstruct historical volume from an incomplete action
history. Adjusted close remains in original response bytes and is not an
execution price or an automatically built signal series.

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
