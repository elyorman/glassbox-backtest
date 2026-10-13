# Frozen ETF dataset (Plan E1) — design

Date: 2026-10-13. Approved by the owner the same day. Roadmap step E is split
into E1 (this dataset), E2 (evidence machinery, synthetic data only) and E3
(the registered studies, the only part that sees real results). Next step:
the implementation plan, a dry run on a scratch copy, then task-by-task
execution with subagents and reviews.

E1 downloads, checks and freezes the data the four plans and their comparison
portfolios need. Registrations in E3 cite the dataset by its hash. No plan or
strategy runs in E1.

## What is downloaded

- **ETFs.** The union of the four built-in plans' universes, read from
  `builtin_plans()` rather than typed by hand: SPY, EFA, IEF, VNQ, GSG, AGG,
  LQD and the eleven Select Sector SPDRs (18 tickers). SPY and IEF also cover
  the 60/40 reference. An explicit ticker list may replace the default.
- **Per ticker:** Tiingo metadata, then prices from the metadata `startDate`
  to the end date. The end date defaults to the latest final day
  (`last_final_day`), so no partial session is requested. 18 tickers need 36
  requests, inside the free tier's 50 an hour.
- **T-bills:** the Treasury 3-month par yield, every year from 1990 to the
  end date's year (public, no key).

## What is saved

A new directory, refused if it exists (`local/data/<name>/`, git-ignored):

- `snapshot.json`: `TiingoJsonSource(...).load()`, the existing normalization:
  raw prices, dividends and splits cross-checked against Tiingo's adjusted
  closes, SPY trading days as the calendar. A data-quality error refuses the
  dataset; warnings are counted in the manifest.
- `rates.json`: the `CashRateSeries`, stored like a snapshot with an integrity
  hash (`save_cash_rates` / `load_cash_rates`). The saved file is the series'
  identity, which settles the step E note about freezing the rate series.
- `manifest.json`, written last: schema version, program version and source
  code hash, tickers, each request (endpoint, ticker, dates, body SHA-256,
  retrieval time), each Treasury year (body SHA-256, retrieval time), the
  snapshot's dataset hash and session range, the rates hash and range, the
  quality warning count, and a `dataset_id` hash over all of it.

`load_dataset(directory)` verifies the manifest, the snapshot and the rates
against each other and returns all three. A registration cites `dataset_id`.

## Command

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.cli download-tiingo \
  --output local/data/tester-etfs-2026-10-12
```

Options: `--tickers`, `--end`, `--tiingo-cache` and `--treasury-cache`
(defaults under `local/cache/`), `--max-requests` (default 45),
`--env-file` (default `.env`). It prints a summary: dataset ID, each ticker's
first and last session and bar count, the rate range and the warning count.

## Safety

- **Key.** `TIINGO_API_KEY` from the environment, else from the env file. It
  travels only in the request header, as the Tiingo client already enforces;
  it never appears in output, files or error messages.
- **Request budget.** A `RequestBudget` in the shared download plumbing
  counts only requests actually sent (cache hits are free). When it is spent,
  the command stops with exit code 3 and lists the tickers still missing.
  Finished requests are cached, so running the same command later continues.
- **Frozen.** A dataset directory is never overwritten; a new download is a
  new dataset with a new ID.

## Code shape

- `quant_core/data/remote.py`: `RequestBudget` and `RequestBudgetExhausted`
  (a `ValueError`).
- `quant_core/data/tiingo.py`: `TiingoClient` takes an optional budget,
  spent once per request sent.
- `quant_core/data/storage.py`: `save_cash_rates`, `load_cash_rates`.
- `quant_core/data/dataset.py` (new): `download_dataset(tickers, end, tiingo,
  treasury)` returns the snapshot, rates and manifest records;
  `save_dataset(directory, ...)`, `load_dataset(directory)`.
- `quant_core/provenance`: `code_hash()`, the source hash the engine already
  computes privately; the engine calls it, unchanged in value.
- `quant_core/cli.py`: the `download-tiingo` command.

## Testing

Offline only, with fake clients and the existing synthetic Tiingo rows and
public Treasury fixtures: a complete download and its manifest; the budget
stopping a run, listing the remaining tickers, and a second run finishing
from the cache; a quality error refusing the dataset; an existing directory
refused; the rates file and the dataset refusing any tampered file; the key
never in output, files or errors; the command's exit codes.

## Real check (after review, nothing committed)

Run the command once for real. Check only the data: all 18 tickers present,
first sessions equal to Tiingo's start dates, last session the end date, no
quality errors, rates from 1990 to the end date. No plan runs.

## Not in this step

The study runner, references, metrics and evidence packs (E2); registrations,
tags and runs (E3); pacing across hours for the ~60-ETF ML universe (step F);
the download screen of the web app (step I).
