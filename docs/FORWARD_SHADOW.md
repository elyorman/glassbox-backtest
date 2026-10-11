# Prospective SMA200 signal journal

The original 22-stock SMA200 recipe is registered on October 5, 2026 for local,
prospective monthly signal tracking. This supports PR-06, PR-08 and PR-13.
It places no broker orders and makes no production-strategy claim.
The broader 47-stock transfer study (research ledger, 2026-10-05) rejected
SMA200 under its fold-stability rule. Preserve that finding: this journal
continues as an operational timing/explainability experiment, not endorsement
of an edge. Its runtime is the frozen archive under `local/`; the live
repository no longer contains the research scripts it uses (git tag
`archive/research-2026-10`).

The journal uses the **exact original recipe**: SMA200, monthly close signals,
95% invested fraction divided over the 22 fixed slots, minimum price $5,
20-session average dollar volume at least $10 million and 1% participation cap.
It retains the original ticker-identity and incomplete-action limitations.
Each record shows eligible/selected names, indicator values, explanations and
target quantities against a **separate, zero-position $100,000 reference account**.
This is a signal/target journal, not a continuously held simulated portfolio,
paper brokerage account or prospective return series. A later portfolio tracker
must separately register its holdings, cash, fills, dividends and valuation policy.

## First window and operation

The first prospective scheduled signal is **October 30, 2026**, after the
16:00 New York close. Record it before the next regular-session open on
**November 2 at 09:30 New York time**. Those timestamps are in different daylight
saving offsets: October 30 close is 20:00 UTC; November 2 open is 14:30 UTC.
The pinned Alpaca calendar includes session-specific closes and future sessions
through April 30, 2027; it is not independently exchange-qualified. Extend the
journal through a separately registered version before that calendar expires.

Nothing is scheduled automatically. Run the capture command in the window:

```bash
PYTHONPATH=local/sma200-forward-2026-10-05/source-archive PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.forward_shadow capture \
  --journal local/sma200-forward-2026-10-05 \
  --signal-session 2026-10-30 \
  --output local/sma200-forward-inputs-2026-10-30
```

The capture refuses to run from the live source tree once any registered file
has changed; the journal's frozen archive is the required runtime. Run it from
the repository root (the `.env` path is relative), between 16:15 ET on the
signal day and 09:00 ET on the next session; the record timestamp is taken
after collection and must precede the 09:30 ET open. Avoid 16:00–16:15 ET: the free
Alpaca plan may refuse the most recent bars, and a failed response is cached
and blocks that output directory. Use a fresh `--output` directory after any
HTTP error.

It reads the existing `.env` credentials, requests only raw Alpaca SIP daily bars
and corporate actions for the fixed names plus SPY, saves original response
bytes/metadata, normalizes a distinct snapshot and appends a record. Collection
has a 40-request ceiling including pagination, no hidden retries and no
credential-bearing redirects. Unsupported actions, missing/invalid trailing
observations or exhausted request budgets fail visibly. Known supplied cash
payment dates remain provider observations; unknown dates remain modeled
receivables, including SPY's fresh provider observations. Raw originals are
never overwritten.

If transport fails before receiving a response, rerun the same command to reuse
verified cached successes. An HTTP failure is retained and blocks reuse; record
a separate acquisition version if collection needs to change. An already
published snapshot/record cannot be overwritten. If the time window is missed,
retain a missed operational observation; do not backdate a signal.

An independently acquired local normalized snapshot can instead be passed to
`append --snapshot PATH --signal-session YYYY-MM-DD`. Its retrieval time must
follow that session's close and precede recording; this is a local metadata
check, not provider-authenticated proof of publication time.

Verify at any time:

```bash
PYTHONPATH=local/sma200-forward-2026-10-05/source-archive PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.forward_shadow verify \
  --journal local/sma200-forward-2026-10-05
```

## Integrity and causal boundaries

Registration binds the recipe, calendar and full 63-file Python source archive.
Records bind the input snapshot bytes, dataset, configuration, signal/execution
dates and explainable decisions, and form a consecutive local hash chain. The
verifier checks archived source bytes and inputs and recalculates decisions with
the active runtime. Use the original archived runtime for verification after
source changes; append requires the registered source hashes. Future bars/actions
cannot affect a current decision. Append rejects
signals before registration, non-month-end dates, premature/late timestamps,
duplicate periods and incomplete trailing history.

New source code requires a new journal version, or running the existing journal
with its frozen source archive on `PYTHONPATH`. Local hashes detect corruption
and accidental editing; they do not provide an independently timestamped,
tamper-proof public record. No data is uploaded.

`append` has the same requirement: run it with
`PYTHONPATH=local/sma200-forward-2026-10-05/source-archive`.

Current state: registered, **zero prospective signals**. The existing October 2
snapshot cannot be presented as a prospective October signal. A short journal
tests reproducibility and timing discipline, not profitability or production
qualification. Paid independent validation remains deferred under the user's
Alpaca-first policy.

Ignored evidence: `local/sma200-forward-2026-10-05/` and
`local/sma200-forward-2026-10-05-inputs/`. The raw future calendar and prior
calendar byte bindings are retained separately. Unit scenarios test early/late
records, DST-aware calendar behavior, causal decisions, corrupted records,
future actions, duplicate dates and withheld cash; these are engineering tests,
not forward market observations.
