# Independent Data Qualification

Version 0.5.1 provides an offline action audit and frozen-retest input preflight
for PR-01, PR-05, PR-08–PR-10 and PR-13. These tools check concrete inputs before
any new portfolio experiment. They do not obtain a provider account, approve
research rights, prove source completeness, nominate a strategy or restore a
fresh temporal holdout.

## Audit saved EODHD actions

The [official action API](https://eodhd.com/financial-apis/api-splits-dividends)
documents `date` as the economic ex-date, `unadjustedValue` as historical cash
per share and `paymentDate` as a separate date. The importer uses those fields
for USD dividends. It never substitutes adjusted `value` or the ex-date for
missing inputs, converts currencies or silently accepts a missing payment date.
Future payment dates can be supplied for already-observed ex-date entitlements.
The original JSON retains announcement/record dates and all vendor fields.

The split endpoint also includes some reorganizations and spinoff adjustments.
A tidy ratio cannot establish that a holder actually received more shares.
Every proposed share split therefore needs independent classification, bound to
its exact returned ex-date and ratio text, before becoming a `Split`. The initial
import supports positive integer-valued original counts, including decimal
spellings such as `1.000000/3.000000`. Nonintegral counts require further reviewed
normalization and remain unresolved here. Duplicate ex-dates need explicit
reconciliation; they are rejected rather than counted twice or silently merged.

Save original `/splits/TICKER` and `/div/TICKER` JSON responses separately, with
the actual original retrieval time and inclusive query window. No authenticated
download occurs in this workflow. Supply a review JSON array only for events
verified to be **share splits**, for example:

```json
[
  {
    "session": "2024-01-03",
    "ratio_text": "1.000000/3.000000",
    "evidence_hash": "SHA256_OF_INDEPENDENT_EVENT_REVIEW"
  }
]
```

The hash placeholder must be replaced with 64 lowercase hexadecimal characters
from the actual retained review. The exact three fields are required; unsupported
classification fields cannot be ignored. This example is synthetic, not a real
TEST.US event or accepted accounting evidence.

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.data.eodhd_actions \
  --ticker TEST.US --security-id stable-id \
  --splits local/pilot/splits.json --dividends local/pilot/dividends.json \
  --start 2024-01-02 --end 2024-01-04 \
  --retrieved-at 2024-01-05T00:00:00+00:00 \
  --split-review local/pilot/split-review.json \
  --raw-cache local/pilot/raw \
  --output local/pilot/action-audit.json \
  --actions-output local/pilot/proposed-actions.csv
```

Status 0 means every **returned** event was resolved; 1 means unresolved rows
remain; 2 means malformed input or immutable file/cache conflict. The JSON audit
records proposed domain actions, each issue's endpoint/date/row, raw response
hashes and reviewed classifications. Raw bytes stay immutable. An identical
artifact can be verified/reused; changed content requires a new path. Structural
or provider-error bodies are rejected without echoing their contents. A CSV is
emitted only if all returned events are resolved, using the extended exact-count
action header from [the data contract](DATA_LAYER.md).

Empty arrays and a successful status **never** prove complete action coverage.
Noncash distributions, identities, terminal outcomes and provider correctness
still require review. In Python, `audit_actions(...).actions` can feed
`EodhdJsonSource` after the existing overall `actions_review_hash` requirement is
met. Include `ActionAudit.input_hashes` in `DataMetadata.input_hashes` so normalized
snapshots bind the original action responses and event classifications as well
as the overall review. Review the same-day post-split dividend basis explicitly.
The [price importer](DATA_INTEGRATION.md) does not infer that review or set
`actions_complete` automatically.

## Preflight the frozen retest

The frozen sample is the original 22 stocks plus SPY, with all 2,703 registered
sessions from 2016-01-04 through 2026-10-02. Its SMA200 recipe, references,
costs/delays, survivor disclosure and original selection history remain unchanged.

```bash
PYTHONPATH=python .venv/bin/python -m research.data_preflight \
  --campaign local/stock-campaign-2026-10-03-finalized \
  --source-archive local/frozen-stock-source-2026-10-03 \
  --snapshot local/independent.snapshot.json \
  --output local/independent-input-review-v1
```

The snapshot can also be a Parquet directory. To add a completed human review,
pass `--qualification local/reviewed-qualification.json`. The report checks
distinct dataset/provider, exact sessions/security IDs, declared complete
actions, strict quality, volume-basis conflicts, frozen snapshot compatibility
and the review's candidate/original dataset bindings. It retains all eight
capability records and all simultaneous blockers, without running portfolios.
Status 0 means the preflight input checks pass; 1 means blockers remain; 2 means
malformed input or file/binding failure. The original archived input gate and
full campaign verification still apply before execution.

The immutable output contains:

| File | Contents |
| --- | --- |
| `PREFLIGHT.json` | Mechanical checks, reviewed capabilities, input/runtime hashes and explicit limitations |
| `SCOPE.json` | Bound frozen recipes, panel, sessions and original-source observations |
| `QUALIFICATION_TEMPLATE.json` | Schema-1 review draft with every capability unresolved and reviewer/date blank |
| `COMPLETE.json` | Exact output file hashes; written last |

Prices, credentials and raw market data are not copied into this package.
`verify_package(directory)` checks the output files and all recorded input-file
bytes. A copied package needs its original bound inputs for that verification;
absolute paths are local provenance, not a portable dataset distribution.
Inputs are hashed before parsing, checked for changes before publication, and rechecked by package verification. Conflicting duplicate JSON fields are rejected, and CLI diagnostics do not echo malformed input text. Hashes establish integrity relative to trusted inputs, not authorship. The
frozen metadata check does not substitute for the full archived ledger verifier.

Two important compatibility limits remain explicit:

- EODHD supplies split-adjusted volume. A declared conflict blocks liquidity/
  capacity qualification even if a general review document says passed. No raw
  volume is reconstructed from incomplete split history. A reviewer must establish
  the actual basis and any separately recorded derivation.
- The original frozen runtime accepts schema-1 JSON. New exact-count splits
  produce schema 2, which this preflight blocks. Prepare explicitly reviewed
  schema-1 inputs only when the ratio is exactly representable, or register a new
  procedure/version. Do not approximate repeating ratios, rewrite the original
  registration, or feed a Parquet directory directly to the legacy retest script.

## Available data and next external inputs

The final cached-data preflight is in ignored `local/data-preflight-2026-10-05-v2/`; the first attempt is preserved separately.
The original Alpaca/SIP snapshot passes mechanical bar quality but is blocked
as an independent retest source: original dataset, original provider, incomplete
actions and no independent qualification review. All eight capabilities remain
unreviewed. Its bound original readiness evidence records **336 unknown payment
dates**; their modeled late receivables do not become actual historical dates.

For the independent pilot, retain the [registered input scope](INDEPENDENT_DATA_RETEST.md).
Start with AAPL/NVDA splits, SPY and a pre-2023 dividend payer, then inspect the
entire fixed panel. Required inputs remain raw OHLCV with a reviewed volume basis,
independent sessions, actual ex/pay cash events, complete noncash/terminal outcomes,
effective-dated identities and applicable research entitlement evidence. The
original full history remains exposed. No account, export, vendor quotation,
market-data purchase or independent performance run is supplied by this tooling.

## Verification — 2026-10-05

The subsequent [public-demo technical pilot](EODHD_PILOT.md) exercised the
importer against real EODHD responses and preserved both successful inputs and
vendor denials. Its selected-symbol diagnostic does not replace any qualification
capability or permit the full frozen retest.

The full unittest suite passes **536 tests**. A synthetic end-to-end audit/CSV/
normalization/portfolio check turns 300 shares into exactly 100 after a reverse
split, accrues USD 30 cash, and reconciles USD 300 ending equity after sale.
Its saved run verifies under ignored `local/action-qualification-smoke-2026-10-05/`.
The actual cached-data preflight package verifies with all four mechanical blockers
and eight unreviewed capabilities visible. The source-only archives for versions
0.5.0 (59 files) and 0.5.1 (61 files) verify; frozen research evidence is preserved.
Independent review found a parse/hash race, conflicting duplicate qualification
fields and a diagnostic text leak. All three were reproduced, fixed and included
in the passing regression suite. These are engineering/input checks, not market
performance or vendor qualification.
