# Initial Market-Data Layer

Status: initial Stage 1 foundation implemented, 2026-10-02. The nine-stage build roadmap is in [PROJECT.md](../PROJECT.md#initial-development-sequence).

## Implemented contract

The core uses the Python standard library; optional Parquet storage uses PyArrow. `SnapshotSource.load()` returns an immutable `Snapshot`, independently of the eventual vendor adapter. The CSV and EODHD adapters preserve raw bytes and input hashes. [Provider/Parquet commands](DATA_INTEGRATION.md) and [dated membership](UNIVERSES.md) extend this foundation without establishing empirical coverage or licensing qualification.

A snapshot includes an explicit ascending session calendar, security registry, raw OHLCV bars, typed corporate actions, and metadata. Every bar must have a known security ID, valid positive prices and OHLC relationships, nonnegative volume, and a session within both the calendar and its security's lifetime. Duplicate bars/actions and adjusted execution inputs are rejected.

Security IDs are the identity keys, not ticker strings. The registry supplies display symbols and listing/delisting boundaries. A delisting date is the first untradable date; bars on that date or later are rejected. An explicit cash-delisting event must match that date and a supplied session. Non-session settlement events and ticker-history mappings need further adapter design before they are supported.

Calendar sessions must be supplied independently of observed bars. Deriving them from available bars would hide missing observations. The checker validates consistency against the supplied calendar, not the calendar's correctness against an exchange. Production exchange-calendar qualification remains pending.

Corporate actions are split ratios (new shares / old shares), dividend ex-dates with cash amounts and pay dates, and explicit cash-per-share delisting settlements. Missing payment dates cannot be silently replaced with ex-dates. Same-day split/dividend data declares the dividend per post-split share. This schema records events; portfolio processing belongs to the backtester stage.

The Python split contract also accepts original positive integer `new_shares`
and `old_shares` together, for example `Split(id, day, new_shares=1,
old_shares=7)`. Its displayed ratio is calculated at precision 28; an explicitly
supplied ratio must agree. Exact counts drive portfolio, pending-order, stop,
historical-price and volume conversions before division. Decimal-only ratios
retain their original approximate semantics; no counts are inferred.
JSON snapshots containing exact counts use schema 2. Snapshots with only legacy
actions retain schema 1, original action fields, and existing dataset hashes.

## Local CSV files

Use UTF-8 CSV with exactly these named columns. Column order may vary; unknown/duplicate headers or mismatched row lengths are errors.

| File | Columns |
| --- | --- |
| Bars | `security_id,session_date,open,high,low,close,volume` |
| Calendar | `session_date` |
| Securities | `security_id,symbol,exchange,listed_on,delisted_on` |
| Actions (optional) | `kind,security_id,session_date,ratio,amount,pay_date` |

Dates use `YYYY-MM-DD`. Numeric values use exact decimal strings. Listing/delisting dates may be empty when unknown; unknown boundaries mean all supplied sessions are expected, not that historical coverage is proven. `Split` uses `ratio` with other action-value fields blank. `Dividend` uses `amount,pay_date` and a blank ratio. `CashDelisting` uses `amount` with ratio/pay date blank. Aggregate multiple distributions for the same security/ex-date before import under this initial schema.

Actions may instead use the extended header with both `new_shares,old_shares`
columns appended. A split can supply these positive integer counts and leave
`ratio` empty, or supply a matching ratio. Other actions leave both counts empty.
For example, an exact one-for-three reverse split is:

```csv
kind,security_id,session_date,ratio,amount,pay_date,new_shares,old_shares
Split,A,2024-01-03,,,,1,3
```

The bundled CSV fixture is entirely synthetic. Its first asset has a 2:1 split, then a dividend; it contains no provider data or investment claim.

## Quality and persistence

Missing bars during an expected lifetime are errors. An entirely absent registered security is detected. Zero-volume bars, large raw opening discontinuities after accounting for known splits and dividend ex-dates, unresolved delisting settlement, declared incomplete corporate actions, and supplied limitations are reported without repairing observations.

The jump threshold is inclusive. The checker also flags opening prices within 3%
of common split ratios (1:2, 2:3, 3:4, 4:5 and their inverses) after adjusting
for known actions, so missed splits with ordinary opening gaps are caught. These
are review prompts, not inferred splits, and genuine large moves near those
ratios are flagged too. `check_quality(..., strict_discontinuities=True)` or the
data CLI's `--strict-discontinuities` makes every flag an error; use it for
short, reviewed histories. For long histories prefer a provider adjustment
cross-check (see [data integration](DATA_INTEGRATION.md)) and review warnings.

`DataMetadata.adjustment_policy` states the volume basis; prices are always raw.
`raw` means raw share volume. `raw_prices_split_adjusted_volume` (set by the
EODHD importer) means volume already reflects later splits: strategies and
risk-enabled backtests refuse such snapshots, because their liquidity filters and
participation caps would double-count splits and see splits after the signal
date. Explicit order schedules without risk limits still run.
Known dividends subtract from the comparison reference after same-day splits,
in post-split units. If distributions exhaust that reference, the percentage-gap
check is undefined and a warning states that limitation; raw bars stay unchanged.

`actions_complete` is a source/user assertion. Passing checks does not verify that a vendor supplied all historical events, point-in-time members, or delisted securities. A warning-free synthetic fixture is not evidence of market-data completeness. Snapshots with incomplete actions can support explicitly limited diagnostics, but cannot qualify total-return research.

The initial persistence format is canonical, schema-versioned JSON with an integrity hash. Loading revalidates the hash, schema, and financial fields; saving publishes a fully written file and refuses to replace existing snapshots. Publication uses a same-directory hard link and requires a filesystem supporting hard links; unsupported filesystems return an error. Hashes detect accidental changes and identify inputs; they do not authenticate a third-party source. Optional Parquet bundles preserve the same normalized snapshot hash and exact decimal values; DuckDB/query storage and larger-data qualification remain Stage 1 work. See [storage commands](DATA_INTEGRATION.md). Input hashes include source bytes; the dataset hash also includes normalized observations, actions, calendar, registry, and provenance metadata.

## Development commands

Create/reuse the repository virtual environment. Core JSON/CSV workflows use the standard library. Install the optional Parquet dependency to exercise the Parquet tests and commands; reuse an existing virtual environment.

```bash
python3 -m venv .venv
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests -v

PYTHONPATH=python .venv/bin/python -m quant_core.cli import-csv \
  --bars tests/fixtures/data/bars.csv \
  --calendar tests/fixtures/data/calendar.csv \
  --securities tests/fixtures/data/securities.csv \
  --actions tests/fixtures/data/actions.csv \
  --source synthetic \
  --retrieved-at 2024-01-05T00:00:00+00:00 \
  --universe-policy fixed_synthetic_universe \
  --calendar-name synthetic_explicit_sessions \
  --actions-complete \
  --output local/synthetic.snapshot.json

PYTHONPATH=python .venv/bin/python -m quant_core.cli inspect local/synthetic.snapshot.json
```

The JSON output contains the dataset hash, counts, declared action coverage, and quality issues. Exit code 0 means the import/inspection completed without quality errors; 1 means quality errors; 2 means malformed input or a file operation failed. Imports with quality errors are not saved. Warnings remain visible in output and snapshot metadata and do not imply qualification. Repeating an import to an existing output fails instead of replacing it.

For a Windows developer environment, use `.venv\Scripts\python.exe` and set `$env:PYTHONPATH = "python"` in PowerShell. The code has been tested on Linux here; Windows execution has not yet been verified. These are development commands, not the eventual customer onboarding experience.

## Remaining Stage 1 work

Research-only collection is now available in `python/research/alpaca_download.py`;
it caches raw API bodies and request hashes under ignored storage and uses saved
credentials without printing them. `market_backtest.py` normalizes the frozen
ten-symbol dataset, reconciles issuer cash distributions/payment dates, and
retains vendor discrepancies. This is a narrow exploratory script, not the
production provider adapter. The V1 product adapter is Tiingo (see
[provider integration](DATA_INTEGRATION.md)); `market_backtest.py` and the other 2026-10
research scripts are retained under the git tag `archive/research-2026-10`.

- Alpaca development adapter, immutable raw downloads, retries/rate limits, and qualified daily-open/feed semantics.
- Verified exchange calendars and completed-session handling.
- Corporate-action, dividend-payment, security-identity, and historical universe coverage checks against the actual provider.
- DuckDB/query storage and larger-dataset performance measurements; full-snapshot Parquet persistence is implemented.
- Qualified historical membership and benchmark inputs; the dated local membership interface is implemented.
- Cross-platform tests and environment/package validation.

The local contract now feeds [the initial Stage 2 backtester](BACKTESTER.md), [Stage 3 risk/sizing](RISK_MANAGEMENT.md), [Stage 4 strategy rules](STRATEGIES.md) and [Stage 5 validation campaigns](VALIDATION.md), verified using synthetic financial fixtures. Stage 5 binds reviewed capability evidence to snapshot hashes; the software does not turn declarations into provider/rights verification. Provider qualification remains required before the empirical campaign. Implemented strategy rules are candidates, not selected production models.

## Private stock-data audit — 2026-10-03

`python/research/stock_data.py` caches raw SIP stock bars and all returned
corporate-action types with request/body hashes. Processing-date queries extend
beyond the price window; economic ex-dates determine inclusion. Public data is
reused locally; credentials remain outside exports. This is a narrow research
collector, not the finished customer provider integration.

The requested 24 survivors were chosen before price download. PFE/VTRS and
MRK/OGN unsupported share distributions exclude PFE and MRK before testing,
without replacements. The frozen version has 22 stocks plus SPY, 62,169 bars
and 2,703 sessions across 2016-01-04–2026-10-02. Initial failed/provisional
versions remain preserved. Acquirer-only mergers do not distribute income to
existing acquirer holders; same-symbol identity changes remain metadata.

336 dividends lack observed payment dates. Their receivables remain unavailable
through the sample under an explicit conservative research convention, with
original null dates retained. This is not proof of conservative bias in every
strategy result. All eight qualification capabilities remain unresolved,
including complete actions, identity, delisting treatment and usage evidence.
Current survivors are not historical index membership. No qualified independent
dataset or purchased data is supplied by this implementation.
