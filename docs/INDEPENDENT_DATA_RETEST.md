# Frozen Trend: Independent-Data Input Brief

> Superseded by the [2026-10-08 strategy qualification standard](STRATEGY_EVIDENCE.md); retained as research history. Outcomes recorded here are unchanged and are counted in [the research ledger](RESEARCH_LEDGER.md).

Current direction — 2026-10-05: the user chose to [continue with Alpaca](ALPACA_RESEARCH.md)
until promising customer interest. Independent paid acquisition is deferred;
this brief remains a later acceptance contract, not an active purchase task.

Reviewed 2026-10-03. This prepares the next data check; no provider has passed,
no purchase has been made and no independent-market retest has run. Supports
PR-05, PR-08–PR-10 and PR-13. Keep downloaded data and evidence in ignored storage.

Update 2026-10-05: the [action audit and input preflight](DATA_QUALIFICATION.md)
now make this scope executable as a local input review. Provider qualification
and the actual frozen retest remain pending. The original research registration,
candidate rules and tolerances have not changed.

The later broader fundamental study has a separate
[paid-data brief](#broader-fundamental-study-paid-data-brief--2026-10-04) below.
It does not change this frozen trend retest or its original sample.

## What is frozen

The existing `stock_trend_sma200` defensive candidate, its original 22-stock
panel, references, simulator/risk sources, costs and delays remain unchanged.
Its verified campaign is `local/stock-campaign-2026-10-03-finalized/`.
The panel is AAPL, AMZN, BAC, CAT, COST, CSCO, CVX, GOOGL, GS, HD, JNJ,
JPM, KO, MCD, MSFT, NVDA, PEP, PG, UNP, UPS, WMT, XOM, with SPY as reference.
This is a surviving custom sample, not a historical index-membership claim.

Inputs must cover **2016-01-04–2026-10-02**, including warmup. Evaluation and
window definitions are those in the frozen campaign. Obtain raw daily OHLCV,
an independently supplied exchange calendar, splits, per-share cash dividends
with actual ex/payment dates, and effective-dated security identity evidence.
The 336 unresolved Alpaca payment dates must not be copied into the new source
or substituted with ex-dates. Complete actions include noncash distributions
and continuity through XOM's July 2026 successor-company transition.

## Provider findings and pilot choice

Official documentation supports a **conditional EODHD pilot**. It does not
establish complete coverage or qualifying rights for our account. Massive is
the alternative when exchange-sourced raw prices/history are required. Do not
buy a retail plan on the assumption that payment establishes commercial rights.

| Source | Relevant documented features | Material issue to resolve |
| --- | --- | --- |
| EODHD | Raw OHLC, splits and dividends with `unadjustedValue` and payment dates | Volume is split-adjusted; reconstruct the raw-volume basis from complete split history. Obtain commercial internal-research entitlement. Dataset-specific source clarification and complete historical identities/calendar/payments need a pilot. |
| Massive | `adjusted=false` bars, historical actions, unadjusted dividend cash and payment dates | Full early-2016 history requires the appropriate history entitlement; obtain business-use rights and independently review actions/calendar/identities. |
| Tiingo | Raw/adjusted EOD, dividend/split fields and a richer dividend endpoint | Detailed dividend history starts in 2023 and dates can be unavailable; unresolved 2016–2022 payments limit this exact retest unless independently supplied. |
| Norgate | Historical constituents, delisted securities and stable asset identifiers | Current FAQ says no business/commercial-use license; direct action-event/payment-date inputs also need review. Earlier preference is paused pending an applicable supplier agreement. |

Sources: EODHD [price/volume semantics](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes),
[actions](https://eodhd.com/financial-apis/api-splits-dividends),
[commercial use](https://eodhd.com/financial-apis/commercial-vs-personal-license-use),
[sources](https://eodhd.com/financial-apis/our-data-sources-and-data-partners),
[symbol changes](https://eodhd.com/financial-apis/us-stock-symbol-rename-history-api),
[calendar](https://eodhd.com/financial-apis/exchanges-api-trading-hours-and-stock-market-holidays);
Massive [bars](https://massive.com/docs/rest/stocks/aggregates/custom-bars),
[dividends](https://massive.com/docs/rest/stocks/corporate-actions/dividends),
[split adjustment](https://massive.com/knowledge-base/article/does-massive-adjust-historic-dividends-for-splits),
[entitlements](https://massive.com/stocks);
Tiingo [EOD](https://www.tiingo.com/documentation/end-of-day),
[dividend history](https://www.tiingo.com/products/corporate-actions/stock-etf-mutual-fund-dividend-api);
Norgate [usage FAQ](https://norgatedata.com/faq.php),
[data FAQ](https://norgatedata.com/data-package-faq.php).

EODHD documentation identifies Nasdaq sources, while its site footer describes
nonexchange OTC/P2P indicative prices. Clarify the source of the exact historical
dataset before declaring raw daily open/feed semantics passed. Symbol-rename
history starts in July 2022; an identifier lookup alone does not establish the
2016–2022 historical chain. Calendar availability must cover exceptional
closures across the full window. These are documented limitations/questions,
not conclusions from a completed data download.

## Concrete pilot inputs and acceptance

1. An account/export entitled for this project's internal commercial research,
   plus the applicable usage evidence. An API credential stays in `.env`; it
   never belongs in reports, source control or request URLs in exported logs.
2. Original JSON/CSV bodies, endpoint/query details with credentials removed,
   retrieval timestamps and byte hashes. Start with AAPL/NVDA splits, SPY ETF
   dividends and a pre-2023 dividend payer; then inspect the complete fixed panel.
3. For EODHD, request historical EOD, dividend and split endpoints for `SYM.US`
   and independent US exchange sessions for the full window. Preserve both
   adjusted/raw dividend fields; never treat adjusted volume as historical raw
   volume without reconstruction. Split bases can depend on later events, so
   retain the provider's complete adjustment history and basis date.
4. Independently reconcile split ratios, per-ex-date dividend amounts/payment
   dates, issuer identity transitions and all exceptional exchange sessions.
   If using Massive instead, explicitly request unadjusted aggregates and the
   full-history business entitlement. No outcome-driven provider replacement.
5. Normalize only after review. Bind a schema-1 qualification to both snapshot
   hashes with scope `independent_retest_fixed_sample`, evidence for all eight
   capabilities, reviewer/date, limitations and provider/feed independence.
   Do not mark missing evidence passed just to run the script.

Two vendors can use the same underlying exchange tape. Document the independence
of acquisition, processing and corporate-action sources rather than implying
entirely independent market observations. Same-date provider testing is a data
cross-check; it cannot restore a fresh temporal holdout or remove survivor bias.

## Preserve and execute the original procedure

Before new research modules were added, the exact 43 registered source files
were archived under `local/frozen-stock-source-2026-10-03/`, with their original
hashes in `SOURCE_ARCHIVE.json`. Use that archive for the old campaign and retest;
adding modules to the live source tree deliberately changes its source registry.
Never rewrite the original campaign registration to admit new research code.

```bash
PYTHONPATH=python .venv/bin/python -m research.source_archive verify-stock \
  --archive local/frozen-stock-source-2026-10-03 \
  --campaign local/stock-campaign-2026-10-03-finalized
```

That verifier executes a clean copy of only the hashed Python sources.
For retest execution, prepare an equivalent verified **source-only** runtime
copy, without bytecode/native artifacts, and use it as `CLEAN_FROZEN_RUNTIME`
below. Setting `PYTHONDONTWRITEBYTECODE` alone does not prevent loading an
existing unchecked cached module. The input preflight runs no retest.

```bash

PYTHONPATH=CLEAN_FROZEN_RUNTIME .venv/bin/python \
  CLEAN_FROZEN_RUNTIME/research/stock_campaign.py retest \
  --campaign local/stock-campaign-2026-10-03-finalized \
  --snapshot PATH_TO_QUALIFIED_INDEPENDENT_SNAPSHOT \
  --qualification PATH_TO_REVIEWED_QUALIFICATION_JSON \
  --output local/stock-independent-retest
```

The existing retest compares the frozen parent and references at registered
costs/delays without retuning. Limits remain 0.05 total-return difference and
0.005 maximum daily-return difference, as fractions. Investigate divergences
before any reference claim; passing agreement still does not automatically
qualify a strategy. Genuinely new temporal evidence remains separate work.

## Broader fundamental study: paid-data brief — 2026-10-04

The [bounded review](BROAD_SEC_EVIDENCE.md#bounded-readiness-review--2026-10-04)
found the current free setup insufficient for the new registered GP/value study.
This brief is for initial exploratory development inputs. After any promising
strategy is frozen, better independent data and fresh temporal evidence remain
separate validation work. Paying for development data does not itself validate
an edge or make that same provider an independent retest.

### Shortlist and recommendation

**First choice for a coverage/licensing enquiry: Sharadar through Nasdaq Data
Link, requesting SF1 + SEP + SFP and the applicable metadata/actions tables with
full history and project research rights.** This is the closest documented
combination of as-reported fundamentals, active/delisted prices and securities
metadata. The commercial price/contract is unconfirmed; no account/export has
passed. Use its documentation to define a pilot, not as evidence that every
sampled issuer is covered. Preserve all 198 CIKs, including documented ineligible
or unsupported cases.

| Offering | Published price / licensing route checked | Fit and remaining uncertainty |
| --- | --- | --- |
| Sharadar via Nasdaq Data Link | Commercial research quote/order needed; applicable price not verified | Best combined-input candidate; confirm delivered tables, full historical coverage, CIK/class mapping, action settlement dates and local retention/replay rights. |
| EODHD Internal Use | Official commercial page lists **USD 399/month**, or a custom arrangement from USD 399/month | Lower published-price alternative. Delisted EOD data exists, but symbol-change history begins 2022-07-22. Requires additional pre-2022 identity evidence, raw-volume reconstruction and dataset-specific source/rights confirmation. |
| Massive Stocks Business | **USD 2,499/month**, 20+ years history; custom/enterprise quote also offered | Raw exchange-market prices/reference/actions alternative. Confirm complete security lineage, terminal proceeds and research rights; SEC accounting or a separate suitable fundamental feed remains needed. |

Prices were checked on 2026-10-04; taxes, minimums, custom discounts and extra
entitlements require a quote. EODHD's commercial page timed out on direct browser
fetch; USD 399 is the official page's search-indexed published listing, not a
live checkout confirmation. Massive's base business price was visible directly.
Its exchange-feed expansions are separate and are not required merely to get
historical daily bars. Sources: [EODHD commercial pricing](https://eodhd.com/commercial-pricing),
[EODHD commercial-use documentation](https://eodhd.com/financial-apis/commercial-vs-personal-license-use),
[Massive business pricing](https://massive.com/business).

Do not treat Sharadar's direct USD 49/month ten-year or USD 69/month full-history
Bundle as applicable project pricing: these are explicitly personal-use plans.
Its terms exclude professional research/business technology development and
direct commercial users to Nasdaq or a separate agreement. Also, a rolling
ten-year entitlement bought in October 2026 may omit early 2016, even before
warmup requirements. Sources: [direct subscription prices](https://sharadar.com/subscribe),
[personal-use terms and Nasdaq route](https://sharadar.com/terms).

Sharadar documents ARY/ARQ/ART observations indexed by filing date for
as-reported research; MR dimensions include later restatements. Its stock
schema provides split-adjusted OHLCV, unadjusted close and a separately
split/dividend/spinoff-adjusted close; full unadjusted OHLCV requires imputation.
Consequently we must review split factors, precision and raw execution/volume
basis, rather than pass adjusted bars directly to cash execution. The current
documentation is for the direct offering; Nasdaq must confirm the semantics of
the actual commercially delivered tables. Sources: [fundamentals](https://sharadar.com/docs/fundamentals),
[stock price schema](https://sharadar.com/docs/stocks),
[securities metadata](https://sharadar.com/docs/tickers),
[action types](https://sharadar.com/docs/actions).

Sharadar's metadata is a present-day snapshot with stable security identifiers;
it does not alone prove historical class/exchange eligibility. Its documented
action schema also does not establish every payment/settlement field needed by
our ledger. EODHD's historical delisted endpoint likewise does not prove
terminal shareholder outcomes. Massive's unadjusted flat files do not eliminate
the need for action/identity review. Sources:
[EODHD delisted coverage](https://eodhd.com/financial-apis/delisted-stock-companies-data-2),
[EODHD rename-history start](https://eodhd.com/financial-apis/us-stock-symbol-rename-history-api),
[Massive unadjusted flat files](https://massive.com/docs/flat-files/stocks/overview),
[Massive historical ticker query](https://massive.com/docs/rest/stocks/tickers/all-tickers).

### Ready-to-use scope and acceptance request

The exact roster is saved in
`local/readiness-review-2026-10-04/VENDOR_SCOPE.csv`: 1,000 rows, 198 unique CIKs,
ten fixed June formations from 2017 through 2026. It contains historical names
and issuer IDs, without current ticker substitutions or return-selected names.
No vendor request has been sent and no purchase has been made.

Request an internal research pilot for this commercial local-first software
project, covering **2016-01-04 through 2026-10-02**, with enough earlier
accounting/history for the registered formation inputs and any explicitly
registered warmup. Include SPY for an independently matched reference. Quote
daily historical inputs, not real-time/intraday features. Request:

1. Historical CIK-to-security/class/ticker/exchange mappings with effective dates,
   listing/delisting dates, reuse/rename/spinoff/merger chains and coverage reasons
   for every roster row. Distinguish an issuer that genuinely fails historical
   eligibility from a vendor coverage failure. Provider availability is not an
   eligibility rule; unsupported eligible securities must not silently disappear.
2. Historical daily OHLCV and its exact adjustment/volume basis, exchange
   sessions, splits, cash dividends with original amounts and ex/payment dates,
   noncash distributions and terminal cash/security outcomes with settlement
   dates. Missing daily sessions need explicit no-trade/suspension/coverage
   explanations; never forward-fill terminal holdings or invent a zero return.
3. For a fundamental feed, as-reported financials with filing/publication dates,
   period dates, fiscal duration, amendment behavior, units and class/share basis.
   Review GP/assets first; value additionally needs positive common equity,
   preferred deductions and exact December shares/market equity under its existing
   contract. Preserve SEC original filings as accounting cross-check evidence.
4. Written entitlement covering internal commercial R&D/backtesting, local
   downloads/cache, development training, retention and frozen replays after any
   subscription ends, and conditions for publishing derived performance or
   distributing trained models. Request these rights individually rather than
   assuming a business account grants all of them. No raw-data redistribution is
   needed for the product's BYO credentials/local-import workflow.

Start the technical pilot with the same three registered diagnostic issuers:
SANM, HWCC and historical SPAR/SHYF. Check their original 2016 statements and
historical identities, HWCC's 2021 cash acquisition, SPAR's 2020 rename and any
later transitions through the study endpoint. Add a split/dividend event and SPY
reference check as predeclared event diagnostics, not new investment candidates.
Specific failures remain failures; do not swap in easy survivors. Then inspect
the **entire fixed roster** for eligible missing securities and per-formation
coverage before registering performance.

For GP, stop with an infeasibility result if reviewed eligibility and required
inputs cannot support at least ten issuers at every registered formation, or if
unresolved coverage would change the investable selection. Do not compensate by
lowering the floor, loosening dates or choosing names that produce attractive
returns. If a paid pilot passes the input checks, register and run the first
exploratory GP portfolio and references with the existing simulator. Value has
its own additional capital requirements. A changed universe or accounting rule
requires a separately registered study; the original result remains visible.

The present review ends at this bounded decision and concrete pilot scope.
Further bulk SEC collection cannot supply market prices, complete terminal
outcomes or a provider entitlement. Keep free SEC originals for accounting proof,
obtain suitable market/reference inputs, and spend the next implementation work
on the first actual portfolio experiment after the data passes.
