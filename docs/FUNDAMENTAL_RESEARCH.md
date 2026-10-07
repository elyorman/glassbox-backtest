# Value and Gross-Profitability Research

Authorized 2026-10-03. Supports PR-01, PR-05, PR-06, PR-08–PR-10 and PR-13;
does not qualify a strategy or complete the three-to-four-strategy release gate.

The separately registered [2026-10-04 original-filing reconciliation](FUNDAMENTAL_RECONCILIATION.md)
follows this baseline audit. Findings below retain the original 2026-10-03 scope
and counts; new component evidence does not rewrite that audit or launch the
proposed performance campaign.

## Intent and boundaries

Investigate two different stock-selection hypotheses while preserving the frozen
SMA200 trend candidate. Follow free data → develop → freeze → qualified separate
data → retest. No purchase, Git action, model training or production nomination.
All 2016–2026 market dates have already been inspected. SEC facts improve the
fundamental inputs; they do not repair the Alpaca price/action qualification gaps.

This task is the approved feasibility study, source research and bounded plan.
Implement research-only retrieval, historical selection and accounting audits.
Do not run new strategy-performance experiments until the input gates pass and
the exact audited mapping/snapshot versions are registered.

## Sources and proposed adaptations

- Value: positive common book equity divided by prior-December market equity;
  fiscal year **ending in calendar year** t−1, June formation and annual holding.
  [French construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/six_portfolios.html).
- Gross profitability: annual gross profits divided by same-period assets.
  [Author's paper](https://mysimon.rochester.edu/novy-marx/research/OSoV.pdf),
  [NBER research](https://www.nber.org/papers/w15940).
- Modern book equity uses parent-attributable shareholders' equity less
  preferred stock. French's August 2016 update removes deferred-tax/investment-
  tax-credit add-backs for fiscal years ending 1993 onward. Missing preferred
  facts do not establish zero preferred obligations.
  [Definitions](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/variable_definitions.html),
  [methodology update](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html).
- Our concentrated long-only equal-capital portfolios would be adaptations of
  the published broad-universe portfolio studies, not replications.

The proposed canonical recipes select five fixed capital slots with 95%
allocation; one top-four neighbor each tests concentration. June's final
completed session generates signals; execution is at the next open. No monthly
refresh, stop search, composite factor or ML variant is added to this batch.

## Frozen feasibility scope

Audit the existing 19 nonfinancial issuers from the 22-stock survivor panel:
AAPL, MSFT, AMZN, GOOGL, NVDA, CSCO, XOM, CVX, JNJ, PG, KO, PEP, WMT,
COST, HD, CAT, UNP, UPS, MCD. JPM/BAC/GS are excluded for accounting scope,
not performance. PFE/MRK's prior unsupported distributions remain excluded.

Proposed common strategy panel: those 19 less GOOGL and UPS, **17 issuers**.
Alphabet has multiple listed share classes; UPS has listed/unlisted classes.
One class price times company-total shares is not automatically market equity.
Retain their audit evidence; do not replace them or quietly reinstate a proxy.
This remains a deliberately surviving custom sample, not historical membership.

Audit June formations 2017–2026. Prices start in 2016, so June 2017 is the
earliest formation with prior-December price data. Determine fiscal years by
actual period start/end, not the SEC `fy` label. Annual durations are explicitly
330–380 days; transitional periods outside that range are unresolved.

## Historical fact contract

`python/research/sec_fundamentals.py` uses SEC CompanyFacts and submissions
history, including older submission files where needed. No SEC Frames input:
Frames selects last-filed facts and does not reconstruct historical availability.
[SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

- Cache original bytes and endpoint/status/retrieval-time/body hashes. Do not
  export the identifying request contact. Reuse cached bytes for repeated audits.
- Join each fact to its filing accession and check form/filing-date agreement.
- Conservative daily availability: official filing date must be **strictly
  before** the decision date. Preserve acceptance timestamps for review; do not
  claim exact public dissemination timing or use a date-only record intraday.
- Amendments and comparative restatements become eligible only when their own
  filing is available. Conflicting same-accession/context values are errors.
- Require coherent accession, USD units, accounting scope and fiscal period for
  numerator/denominator components; never combine unrelated vintage rows.
- Prefer direct gross profit. Report possible revenue/cost pairs, but derived
  gross profit requires reviewed issuer-specific mappings. Do not substitute
  operating income, EBITDA or net income for missing gross profit.
- Parent equity cannot silently use equity including noncontrolling interests.
  Preferred redemption/liquidation/par and minority-interest scope need review.
- Market equity needs December raw prices and correctly scoped December shares,
  available by formation. EPS weighted-average shares, public float, issued/
  authorized shares and later cover-page counts are not substitutes. Changes in
  comparative share counts can reflect split restatements; audit share vintage.
- Missing history/components stay missing. No future backfill, zero fill or
  performance-based security replacement. Emit readiness/status reasons.

SEC public filing content is free to access/reuse; automated access needs a
declared client and moderated requests. This statement does not qualify the
separate market-price provider or every third-party dataset.
[SEC FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions).

## Implementation and verification plan

- [x] Add research-only collector and immutable input plan for the 19 CIKs.
  Retrieve CompanyFacts and current/required historical submission indexes;
  verify issuer identity without treating current tickers as historical proof.
- [x] Test historical selection with later restatements, amendments, same-day
  filings, conflicting duplicates, units, mismatched accessions, fiscal-year
  labels and coherent component selection using hand-derived synthetic facts.
- [x] Run the real-data audit; export yearly issuer coverage, raw selected
  component evidence, explicit accounting/share gaps and a hash-verified report.
- [x] Prepare provider-specific retest input requirements for frozen trend,
  using official documentation; do not buy or fabricate passed qualification.
- [x] Update repository documentation and run relevant/full verification.

Verification: **320 tests passed**, including 16 SEC tests. The real audit's
190 rows and report pass semantic verification; all 99 original stock bundles
pass using the unchanged archived source. A separate read-only code review
found no critical/important issue within the documented feasibility scope.
No strategy/data qualification is inferred from these engineering checks.

## Feasibility findings — 2026-10-03

The fixed input scope was published before collection. All **57 public JSON
responses** (19 CompanyFacts, 19 current indexes, 19 historical indexes) are
cached unchanged with request/body hashes. A separately registered audit plan
pins the processing sources and raw evidence before computing the report.
`verify` checks the complete file registries, snapshot/scope, sources and every
derived row, then reproduces the HTML. It rejects a changed score even when
someone updates the report's byte-hash registry. These checks ensure internal
consistency; they do not certify the SEC extraction as historical ground truth.

The audit covers **190 issuer/formation rows**:

| Component status | Rows |
| --- | ---: |
| Direct gross-profit/assets pair available, still unqualified | 80 |
| Possible revenue/cost derivation requiring mapping review | 67 |
| No coherent annual pair available under these rules | 43 |
| Invalid/ambiguous rows | 0 |

On the proposed 17-stock common panel, direct-pair coverage is 8, 8, 8, 9,
7, 8, 8, 8, 8, 8 for June 2017–2026. This falls below the proposed ten-eligible-
issuer floor even before original-filing qualification. **Do not lower the
floor or start the performance campaign.** Review the 67 possible derivations
and original filings first; unexplained components stay unavailable.

Parent-equity components appear in 160 rows, December outstanding-share records
in 70, and at least one preferred-stock value tag in 72. These are availability
counts, not qualified book/market equity. Some tags can describe authorized
preferred stock or stale comparative contexts; absent preferred tags cannot
prove zero outstanding preferred stock. All value rows remain unready.

The first collection stopped at XOM because its old issuer no longer has a
current ticker. Official filings establish the July 1, 2026 successor,
CIK `0002115436`, and 1:1 common-share exchange. The old CIK `0000034088`
remains the relevant annual source for this audit's formations through June
2026. The explicit exception rejects dates at/after the transition and retains
the source link in each XOM row. It does not certify the market provider's
identity/action processing or silently join successor facts.
[Successor filing](https://www.sec.gov/Archives/edgar/data/2115436/000119312526291990/d71068d8k12b.htm).

Private artifacts: `local/sec-fundamentals-2026-10-03/INPUT_PLAN.json`,
`AUDIT_PLAN.json`, `FEASIBILITY.json`, `REPORT.html`, raw JSON/request metadata,
and input/report hash registries. No strategy-performance trial has run.

```bash
PYTHONPATH=python .venv/bin/python python/research/sec_fundamentals.py verify \
  --output local/sec-fundamentals-2026-10-03
```

The [independent-data input brief](INDEPENDENT_DATA_RETEST.md) records the
conditional EODHD pilot, Massive fallback, actual input/review requirements
and archived-source commands. No provider/purchase/qualification is implied.
The original trend procedure is preserved in
`local/frozen-stock-source-2026-10-03/`; do not rewrite old registrations to
admit these new SEC research modules.

## Proposed performance campaign — not launched

After accounting readiness, bind the exact feature mappings, source/price/fact
hashes and coverage gates in a machine-readable registration before outcomes.
Both parents are return-seeking: positive CAGR and historical-reference Sharpe
above reserve SPY and their accounting-eligible equal-weight reference at both
10 and 25 bps. Preserve the existing strict economic standard.

Proposed budget: four parent/neighbor recipes plus reserve SPY, static common-
panel annual equal weight, value-eligible annual equal weight, profitability-
eligible annual equal weight and zero-yield cash: **nine configurations**.
Three continuous cost/delay scenarios give 27 trials; three cash-reset windows
at two costs give 54, for **81 total**. Annual formation windows begin in June
2017, June 2020 and June 2023, ending in 2019, 2022 and the sample end. Existing
history provides causal warmup; these are exposed diagnostics, not fresh OOS.

Each formation must have at least ten coherent, eligible issuer records on the
common panel; fewer blocks that hypothesis/window rather than becoming a
favorable cash portfolio. Negative book equity is an economic value exclusion,
not missing data, and is reflected in its dynamic matched reference. Freeze
only parents meeting objectives at both costs, positive neighbors at both,
objectives in at least two of three windows at both costs and delayed execution.
Neighbors never replace failed parents. This proposed budget does not include
already performed ETF/stock searches; disclose the complete search history.

Actual registrations/performance remain pending until accounting, market-equity
and historical-availability inputs are reviewable. No claim of ready-to-backtest
value or profitability is made by downloading public facts alone.

## Accounting and capital evidence — 2026-10-04

The [bounded extension](FUNDAMENTAL_CAPITAL.md) preserves the original SEC/stock processing
sources and reports. It adds exact dimensional accounting, body-bound
nonfinancial-amendment exemptions, reviewed issued/treasury shares, preferred
zero/hierarchy evidence and explicit original/split-basis gates. The new
190-row audit has 99 profitability records and 103 December share records;
common-panel coverage remains 9–10 and 9–11, below the unchanged ten-issuer
requirements in one/eight formations respectively. The fixed-panel study is
infeasible under the registered scope. No strategy performance, market-data
purchase or ML training launches. Component arithmetic cannot qualify a
provider or strategy; a broader study requires separate preregistration.
The then-current suite passed 388 tests, including 84 SEC tests. Capital evidence:
`local/sec-capital-2026-10-04/REPORT.html` and `CAPITAL.json`.

## Broader filing-candidate study — 2026-10-04

The separately registered [broader study](BROAD_UNIVERSE_RESEARCH.md) preserves the infeasible
fixed panel and uses 42 original SEC quarterly indexes, 2016Q1–2026Q2.
Filing-date selection yields 7,154–8,162 candidates per June formation;
a frozen hash rule samples 100 each, totaling 1,000 issuer/formation rows
and 198 distinct CIKs. Current tickers, returns and data availability do
not influence selection, and missing candidates are never replaced.
Historical listing/identity/classification, accounting, price/action/delisting
and project-use checks remain missing. Current quarterly-index corrections
also remain unresolved: filing candidates are not qualified historical stocks.
No strategy performance or ML training launches. Its then-current suite passed
407 tests, including 19 broader-study tests. Local evidence is
`local/broad-universe-2026-10-04-v2/REPORT.html` and `ROSTER.json`; original
failed registration, source archive and all 84 response files are preserved.

## Broader SEC input evidence — 2026-10-04

The [evidence audit](BROAD_SEC_EVIDENCE.md) keeps the exact 198 CIKs and 1,000 sample
rows. All 1,400 registered requests were attempted: 396 API roots, nine
historical archives and 995 original annual headers. Preserve the 32
CompanyFacts 404s and nine issuer/year publication-metadata disagreements;
missing candidates are never replaced. There are 246 preliminary GP/assets
rows and 430 exact December-share observations, with no qualified issuers.
Original header names/SIC are unreviewed evidence, not historical listing
or share-class proof. All 10,000 qualification checks remain missing.
Original financial/amendment and historical security review precede market-
data qualification and any separately registered performance campaign.
The full suite passes 425 tests, including 18 new evidence-stage tests.
Current local evidence: `local/broad-sec-evidence-2026-10-04-v2/REPORT.html`
and `EVIDENCE.json`. Both 40-source archives and original format/transport
finding records remain preserved; no purchase, performance or ML launch.
