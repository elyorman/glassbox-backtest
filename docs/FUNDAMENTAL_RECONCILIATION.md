# Original-Filing Reconciliation

Authorized 2026-10-04 as the next step after the
[fundamental feasibility study](FUNDAMENTAL_RESEARCH.md). Supports PR-01,
PR-05, PR-06, PR-08 and PR-13. No purchase or Git action is included.

## Goal and design

Reconcile discovered annual and December-share facts against the original
filing, record reviewed accounting mappings, and recompute data readiness before
any strategy-performance experiment. Preserve the previous 190-row audit,
the frozen trend sources and the proposed 17-stock panel/ten-issuer floor.
Use a separate research-only module, mapping file and versioned local output.
The standard-library Python implementation does not change the trading engine.

This is an SEC-as-reported accounting adaptation, not an exact Compustat or
Novy-Marx replication. Do not invent depreciation allocations to mimic another
database's normalized COGS. Do not add a composite factor or search parameters.
Original facts support data reconciliation, not provider/strategy qualification.

## Accounting decisions before outcomes

- Direct annual gross-profit/assets pairs can be reconciled to original standard
  concepts with matching issuer, USD units, period and dimensionless entity scope.
- P&G: reviewed reported-GAAP sales minus production cost; account for the
  2019 taxonomy/accounting change without rewriting earlier filing vintages.
- Costco: accept a bounded issuer-reported adaptation, net sales minus
  merchandise costs excluding membership. Use the reviewed standard net-sales
  formula in FY2016–2017, and direct original gross profit only in FY2018–2025.
  Later net-sales/membership facts use product/member dimensions, which the
  whole-entity reader excludes; dimension-to-total arithmetic needs review.
  Distribution/fulfillment/manufacturing and selected depreciation are included,
  while warehouse staff and substantial depreciation remain in SG&A. This
  mapping is not proof of normalized cross-company cost comparability.
- Amazon, Walmart and Caterpillar: keep simple whole-company derivations blocked
  where production-cost or financial/industrial scope is incompatible. Preserve
  the source/rationale; exclusions are unrelated to strategy returns.
- JNJ's FY2020 ended 2021-01-03. That does not satisfy the registered prior-
  calendar-year-end rule at June 2021. Do not silently use its fiscal label.
- Value needs exact December-31 outstanding shares, including explicitly dated
  DEI cover facts when supported. December 27 or a January cover date is not
  equivalent. Split-restated comparisons are not raw-price-basis shares.
- Missing preferred facts never prove zero; zero requires affirmative issuer
  evidence at the annual numerator date. Authorized shares and investment assets
  are not issuer preferred obligations. Nonzero valuation requires the registered
  redemption/liquidation/par hierarchy and consistent issuer/date/class scope.

## Implementation plan

1. Add `docs/fundamental_mappings.json` with reviewed issuer/tag/date decisions
   and primary source links. Register original-document requests before
   collection, then freeze exact reviewed mappings before deriving features;
   retain prior audit hashes. Collection scope does not depend on mappings.
2. Add `python/research/sec_reconcile.py`: discover original XBRL instance files
   through filing directories, cache original bytes/request hashes, parse
   contexts/units with explicit issuer/dimension/period checks, and reconcile
   each selected value. Fail on contradictory contexts, unknown units,
   incompatible period lengths or later unavailable filings.
3. Add `tests/test_sec_reconcile.py` with hand-derived original XML examples:
   coherent annual arithmetic, scaling/units, duplicate conflicts, issuer/class
   scope, later vintages, exact December dates, DEI versus authorized/issued
   shares, split-basis conflicts and tampered/resealed evidence.
   Add `python/research/sec_inline.py` and `tests/test_sec_inline.py` to read
   displayed primary-filing numbers independently of SEC-extracted XML,
   including scale, sign, nested facts and explicit transformations.
4. Collect and audit the registered original documents. Export component proof,
   rejected mapping reasons, annual coverage and value blockers. Review originals
   before marking a share basis/preferred deduction ready; missing inputs stay
   missing. No backtest is launched just because a mapping improves coverage.
5. Verify the complete report against raw inputs and pinned sources, run focused
   and full tests, obtain a code review, and update current project documentation.

The performance campaign remains unlaunched unless the predeclared data gates
pass and exact feature/data versions are registered. A calendar-policy gap or
inadequate panel is a research finding; it is not permission to reduce the floor,
change the historical dates or substitute a stock after inspecting results.

## Evidence contract

`INPUT_PLAN.json` binds the previous audit, snapshot and 218 requested filing
accessions. `COLLECTION.json` records directory discovery, original instance and
primary-filing endpoints. Raw bodies and request metadata are immutable. Missing
or ambiguous instances remain unavailable, including the registered amendments;
the collector preserves the primary document and continues without inventing
structured facts. It uses declared SEC contact identification and bounded
request pacing, with no contact email written into artifacts.

`MAPPINGS.json` is a copy of the reviewed mapping file, frozen before feature
arithmetic. `AUDIT_PLAN.json` pins it, every raw input and exact computational
sources before deriving component scores. Verification checks byte manifests,
the registered document set and endpoints, issuer/units/period/dimensional
context, arithmetic, eligibility, coverage and rendered outputs. It recomputes
the report from the retained originals; resealing an altered score is rejected.
Request metadata's `collector_source_hash` is the source-file hash observed on
disk at retrieval, not an assertion about a running process's loaded code.
The audit source registry is the execution/reproduction contract.

For inline filings, both the primary HTML and SEC-extracted XML must agree on
every selected dimensionless component. This bounded reader is not a general
XBRL validator. Unknown transformations, unsupported continuations and
contradictory facts fail closed. Consistent rounded duplicates retain the most
precise observation. Explicit nil remains missing. Missing preferred facts do
not become zero; numeric zero must be affirmatively tagged in the original.

The reader follows [XBRL's nested-fact specification](https://specifications.xbrl.org/work-product-index-inline-xbrl-inline-xbrl-1.1.html)
and [Transformation Registry 4](https://www.xbrl.org/Specification/inlineXBRL-transformationRegistry/REC-2020-02-12/inlineXBRL-transformationRegistry-REC-2020-02-12.html):
each nested fact retains its own context, scale and sign; `fixed-zero` explicitly
transforms a string to zero. The [SEC Filer Manual](https://www.sec.gov/file/efmvol2-v57),
section 5.2.5.12, defines `numwordsen` for `no` and `None` as zero. Other word
numbers are deliberately unsupported. Plain untransformed text is never zero.
These rules were tested before the real audit was registered.

Aggregate/original disagreements, failed registered annual documents and
conflicting annual contexts block profitability coverage. A conflicting share
context blocks share evidence; a conflicting equity context blocks parent
evidence. None silently falls back to another document to satisfy coverage.
Components remain unqualified even when reconciled.

## Reviewed accounting and share evidence

P&G's reported production costs cover manufacturing, distribution, warehousing
and shipping. The mapping changes from `SalesRevenueNet − CostOfGoodsSold`
(FY2016–2018) to `Revenues − CostOfGoodsAndServicesSold` (FY2019–2025).
Its FY2019 pension reclassification also changes comparative costs: preserve
the original available vintage rather than backfilling that presentation into
earlier formations. See the [FY2016 filing](https://www.sec.gov/Archives/edgar/data/80424/000008042416000212/fy151610-kreport.htm),
[FY2019 filing](https://www.sec.gov/Archives/edgar/data/80424/000008042419000050/fy181910-kreport.htm)
and [FY2025 filing](https://www.sec.gov/Archives/edgar/data/80424/000008042425000076/pg-20250630.htm).

Costco's [FY2018 original statement](https://www.sec.gov/Archives/edgar/data/909832/000090983218000013/cost10k9218.htm)
distinguishes net sales $138,434m, membership $3,142m and total revenue
$141,576m; merchandise cost is $123,152m. Total revenue minus that cost gives
$18,424m rather than the issuer's merchandise gross margin of $15,282m.
The archived XML tags net sales and membership using
`RevenueFromContractWithCustomerExcludingAssessedTax` under the respective
Product/Member dimensions; these cannot supply a whole-entity fact under the
current reader. An explicit dimension/member accounting review would be needed
to use those amounts in a consolidated formula. This is a bounded parser gap,
not an assertion that the original observations are absent.
FY2019's original direct `GrossProfit` is usable component evidence; do not
extrapolate its availability. Its [FY2025 accounting policy](https://www.sec.gov/Archives/edgar/data/909832/000090983225000101/cost-20250831.htm)
defines cost scope and confirms the limits of cross-company comparability.
The [FY2016 amendment](https://www.sec.gov/Archives/edgar/data/909832/000090983216000034/cost10ka82816.htm)
corrects purchase obligations only and says other information is unaffected.
The current bounded audit still blocks it for lack of an unambiguous structured
instance; a future explicit, hash-bound nonfinancial-amendment review would be
needed to reuse the earlier components. This is a parser/review limitation,
not a claim that Costco restated its gross profit.

Amazon's [FY2016 policy](https://www.sec.gov/Archives/edgar/data/1018724/000101872417000011/amzn-20161231x10k.htm)
and [FY2025 policy](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000004/amzn-20251231.htm)
put fulfillment and significant AWS infrastructure outside tagged cost of
sales. Adding every technology expense would also subtract research; no
allocation is invented. Walmart's [FY2025 filing](https://www.sec.gov/Archives/edgar/data/104169/000010416925000021/wmt-20250131.htm)
distinguishes net sales from membership/other income and locates substantial
distribution costs in SG&A. Caterpillar's [original FY2016 report](https://www.sec.gov/Archives/edgar/data/18230/000001823017000041/cat10k2016a01.pdf)
separates industrial sales/costs from Financial Products. Their simple
whole-company formulas remain blocked pending comparable accounting inputs.

Exact-dated cover facts are valid discovery evidence: P&G's
[December 2025 cover](https://www.sec.gov/Archives/edgar/data/80424/000008042426000011/pg-20251231.htm)
reports common outstanding shares on December 31. Apple's
[December 2025 quarter](https://www.sec.gov/Archives/edgar/data/320193/000032019326000006/aapl-20251227.htm)
instead ends December 27, with a January 16 cover count. Neither proves
December 31. Issued shares, public float and weighted averages stay excluded;
later split-adjusted comparative counts require reconciliation to raw prices.

Preferred values need the [French valuation hierarchy](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/variable_definitions.html).
P&G's FY2025 ESOP note shows nonzero preferred liquidation obligations: rounded
carrying value, stated par and authorized shares are different quantities.
No automatic deduction is inferred. SEC reported GAAP and normalized Compustat
inputs are also distinct; [Ball et al., section 6](https://www.ivey.uwo.ca/media/3775544/linnainmaa.pdf)
discusses cost/depreciation adjustments. This stage claims an explicitly
documented adaptation only.

## Local commands

Run from the repository root using the existing virtual environment. `collect`
needs SEC identification via `SEC_CONTACT_EMAIL` or existing Git email config;
audit and verification are offline. Use a new output directory for a changed
scope, mapping or computational source; never overwrite a sealed audit.

```bash
PYTHONPATH=python .venv/bin/python python/research/sec_reconcile.py plan \
  --output local/sec-reconciliation-2026-10-04
PYTHONPATH=python .venv/bin/python python/research/sec_reconcile.py collect \
  --output local/sec-reconciliation-2026-10-04
PYTHONPATH=python .venv/bin/python python/research/sec_reconcile.py audit \
  --output local/sec-reconciliation-2026-10-04-v3
PYTHONPATH=python .venv/bin/python python/research/sec_reconcile.py verify \
  --output local/sec-reconciliation-2026-10-04-v3
```

The existing sealed output is verified with the last command; the preceding
commands document how it was created. Report and context evidence remain in
ignored `local/` storage.

## Preserved first-attempt failure

The initial real audit failed before writing any derived result because the
split check expected `session_date`, while the actual `Split` schema serializes
`session`. The earlier synthetic test had mistakenly hand-shaped a different
dictionary. The regression now uses a real `Split` through the same serializer
as the snapshot; it reproduced the failure before the one-field fix.

The initial `AUDIT_PLAN.json`, frozen mappings, all 33 registered computational
source files, raw evidence and failure record remain in
`local/sec-reconciliation-2026-10-04/`. The brief initial failure note mistakenly
called the actual field `ex_date`; `FAILURE_CORRECTION.json` records the exact
`session` schema and the Costco dimensional-fact clarification. Neither change
alters prior strategy performance. The separate `-v2` output reuses all 1,172
identical raw files and unchanged collection/request scope without new requests;
its reviewed mappings and corrected sources are registered independently.

The v2 audit and semantic verifier completed with 190 rows. Original Caterpillar
filings then established that its ten flagged share disagreements were
consistent rounding: e.g. December 2016 `CommonStockSharesOutstanding`
586,500,000 at decimals −5 and `EntityCommonStockSharesOutstanding` 586,486,024
at decimals INF share the original issuer/context/date. The exact number falls
inside the rounded observation's accuracy interval. The final v3 reader applies
the existing accuracy-interval reconciliation across these two outstanding
concepts, preserves both originals and selects the most precise value without
tag preference. True conflicts still fail. Share class/split basis remains
unqualified. A new realistic order-independent regression failed before this
fix and passed afterward. Every actual Caterpillar year then reconciled.

The v2 report, registry and exact 33-file source archive remain under
`local/sec-reconciliation-2026-10-04-v2/`. The v3 audit again uses unchanged
requests/raw bytes and independently freezes its corrected sources. These are
data-correctness revisions without strategy-performance experiments. For the
earlier v2 procedure, use its archived source directory as `PYTHONPATH` and its
archived `research/sec_reconcile.py` as the entrypoint.

## Final component findings — 2026-10-04

The final v3 audit retains **218 original accessions**, 216 parsed XML instances,
150 independent inline/primary crosschecks, two unavailable amendment instances
and **1,172 raw body/request files**. The fixed 19-issuer audit has 190 rows;
strategy coverage is measured only on the unchanged 17-issuer common panel.

| June formation | Profitability components | Exact December-share components | Required minimum |
|---|---:|---:|---:|
| 2017 | 9 | 7 | 10 |
| 2018 | 10 | 6 | 10 |
| 2019 | 9 | 6 | 10 |
| 2020 | 10 | 6 | 10 |
| 2021 | 8 | 6 | 10 |
| 2022 | 9 | 6 | 10 |
| 2023 | 9 | 7 | 10 |
| 2024 | 9 | 6 | 10 |
| 2025 | 9 | 6 | 10 |
| 2026 | 9 | 6 | 10 |

There are **91 reconciled profitability observations**: 79 original direct,
11 reviewed derived (ten P&G plus Costco FY2017), and one reviewed Costco direct.
Ninety issuer/formation rows retain blocked accounting mappings, nine lack
eligible original components. Only two formations reach the component floor;
the full profitability gate is **false**. Accounting comparability and data
qualification would still be required even if component coverage passed.

The full audit retains **158 parent-equity and 71 exact-date share observations**,
including nine Alphabet observations outside the common panel. Share count
coverage is six common issuers each year plus Apple where its quarter ends on
December 31. P&G adds exact-date DEI evidence; Caterpillar's compatible rounded
and exact records are reconciled. Class and raw-price/split basis stay unreviewed.
There are 42 affirmative annual zero-preferred component observations, 23
observations with issuer preferred values requiring valuation review, and 125
unresolved annual preferred states. None qualifies a common book-equity value
or complete book/market denominator. **Value ready is false.**

The two unavailable amendment instances affect Costco June 2017 and Alphabet
June 2019; the latter is outside the common strategy panel. Original available
values are not silently reused to satisfy these records. No remaining numeric
conflicts are asserted by the final audit. JNJ June 2021 remains a calendar-rule
gap; most later Costco years remain a dimensional-accounting mapping gap.

Standalone evidence: `local/sec-reconciliation-2026-10-04-v3/REPORT.html` and
`RECONCILIATION.json`, with frozen mappings, plans, input/report hashes and raw
contexts. Previous audits and stock results remain unchanged. No new strategy
backtest, model training, provider purchase or production nomination occurred;
zero strategies are commercially qualified and the three-to-four release gate
remains outstanding.

## Next bounded task

Review original product/member dimensions for Costco before defining any
consolidated net-sales-minus-cost recipe; review expressly nonfinancial
amendments before permitting hash-bound reuse. For value, recover exact
December outstanding counts from original class-matched issued/treasury facts
where supported, then review annual preferred notes and split/raw-price basis.
Do not treat missing share inputs as a reason to optimize strategy returns.

If the fixed panel still cannot satisfy the floor, record the current campaign
as infeasible. Any broader universe or changed calendar/accounting methodology
needs a separately registered study and untouched rules before performance.
Existing survivorship, price/action/provider qualification and independent
retest requirements also remain. These follow-ups are now implemented in the separately registered
[accounting/capital extension](FUNDAMENTAL_CAPITAL.md), preserving this report
and its sources. The fixed panel remains infeasible under its unchanged floor;
no performance or qualification follows from the component recovery.

## Completed verification

All five implementation tasks above are complete for this bounded research
stage. The Linux/Python 3.12 suite passes **357 tests**, including **53 SEC
tests**. The final semantic verifier reproduces all **190 rows**, 218 original
document records, coverage and the standalone report from frozen evidence and
sources. Both readiness gates remain false as reported. Independent code
review found no remaining critical/important issue after the regression fixes.

The prior 190-row CompanyFacts audit still verifies, and all 43 original
stock-campaign source files retain their archived and live hashes. Frozen v3
mapping bytes match the reviewed repository mapping; every archived v2 source
matches its original registration. Documentation links and ignored storage were
checked. Engineering verification does not qualify the data or a strategy.
