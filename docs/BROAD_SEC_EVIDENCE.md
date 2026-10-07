# Broader SEC Evidence Collection and Audit

Authorized 2026-10-04 as the next step after the frozen
[broader discovery study](BROAD_UNIVERSE_RESEARCH.md). Supports PR-01, PR-05,
PR-06, PR-08, PR-13 and PR-14. This is input research, not performance validation.

## Scope and plan

Preserve the exact 198 CIKs and 1,000 issuer/formation sample rows. Never use
current tickers, SIC, exchange, returns or data coverage to replace a candidate.
Preserve the prior fixed-panel finding, all source archives, the ten-issuer
floor, annual 330–380-day periods, prior-calendar-year ends and exact December-31
shares. No market-data purchase, strategy launch, training or Git actions.

Use the repository Python environment and standard library. Two new research
modules leave every previous processing source unchanged:

1. `broad_sec_evidence.py`: filing-column validation, bounded historical archive
   selection, original annual reference joins, historical SGML-header extraction,
   component availability and explicit missing-input reporting.
2. `broad_sec_audit.py`: immutable registrations, declared sequential SEC client,
   retained terminal failures, source/input hashes, HTML and semantic verification.
3. Matching tests cover historical and failed issuers, unknown current tickers,
   malformed/unsafe archives, publication and fiscal boundaries, amendments,
   joint-filing header identity, missing/ambiguous SIC, exact December shares,
   immutable failures, orphan files and rehashed derived-report tampering.

Execution uses tests before implementation, followed by real collection,
archived-source reproduction, full-suite checks and independent code review.
The user has authorized implementation; no additional design approval is needed.

## Registrations and source rules

`INPUT_PLAN.json` binds the verified previous roster/report bytes, exact CIKs,
all sampled historical annual references, canonical rules and processing hashes
before requesting the 396 CompanyFacts/submissions roots. Current API metadata
is recorded only as present-day metadata; it cannot prove historical eligibility.

`HISTORY_PLAN.json` binds root response bytes before requesting only safe
issuer-specific historical submission archives whose advertised date ranges
intersect 2016-01-01 through 2026-06-30. Missing or malformed issuer responses
are retained and reported, not substituted. Columnar history includes primary
document names when supplied; conflicts invalidate that issuer's joined history.

`DOCUMENT_PLAN.json` binds all root/history response bytes before downloading
original annual SGML headers. Request every referenced issuer/accession whose
reported period could satisfy at least one sampled formation's prior-calendar-
year rule, plus references whose period is unknown. Missing history never
silently deletes an original reference. Headers provide accession/form/date,
issuer-specific original names and SIC where supplied. Joint filers remain
separate CIKs. Header SIC is evidence for review, not a security or strategy pass.
No primary filing financial statements or XBRL are claimed to be reconciled here.

The exact request universe is frozen before each collection phase. Successful
and failed terminal HTTP bodies are saved unchanged with URL/status/hash/time;
429/5xx retries retain status history. Oversize bodies are retained as bounded
failures. Cached terminal failures are never overwritten or retried as new
successes. Requests are sequential, <=2/sec, with a declared contact omitted
from saved metadata. All artifacts remain in ignored local storage.

`AUDIT_PLAN.json` binds every registered response, request manifest and source
before derived arithmetic. Verification recomputes the same manifests, filing
joins, header evidence, availability counts and HTML. Missing requests and
unregistered/orphan files fail verification; recorded HTTP/schema failures
remain valid evidence of missing inputs.

## Evidence interpretation

CIK identity agreement across API responses does not establish a historical
listed common stock, share classes, exchange or eligible nonfinancial issuer.
Original header observations cannot establish listing continuity or delistings.
Current API SIC/name/tickers never fill historical gaps. CompanyFacts is a
current aggregate extraction: accession/date joining and coherent components
are preliminary evidence requiring original-document and accounting review.
Known amendments and annual references with missing/failed proof remain visible.

Gross-profit/assets availability requires an annual 330–380-day period ending
in the prior calendar year, strictly earlier filing dates and a shared accession
and end date. Direct components and potential revenue-minus-cost mappings are
distinct. Outstanding-share observations must be exactly December 31; weighted
average shares and missing preferred amounts cannot substitute. Component
arithmetic never qualifies a provider, common book/market equity or strategy.

Every sampled issuer/year remains in the report, including HTTP failures,
unavailable facts and conflicting history. All ten previous qualification gates
remain missing until substantively reviewed. Performance and production flags
are always false. This collection does not restore untouched historical OOS.

## Official references

- [SEC API schemas and current metadata](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC access, original-header paths, joint filer accession semantics and index corrections](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

## Implementation checklist

- [x] Add failing pure evidence fixtures; implement joins/header/availability.
- [x] Add failing lifecycle fixtures; implement registrations/collection/audit.
- [x] Register and collect real evidence without candidate replacement.
- [x] Freeze/archive processing sources, audit and reproduce from raw bodies.
- [x] Run full tests and independent review; record actual evidence and blockers.
- [x] Update repository progress documentation without rewriting prior results.

## Commands and reproducibility

```bash
PYTHONPATH=python .venv/bin/python -m research.broad_sec_audit plan \
  --parent local/broad-universe-2026-10-04-v2 \
  --output local/broad-sec-evidence-2026-10-04-v2
PYTHONPATH=python .venv/bin/python -m research.broad_sec_audit collect \
  --output local/broad-sec-evidence-2026-10-04-v2
PYTHONPATH=python .venv/bin/python -m research.broad_sec_audit audit \
  --output local/broad-sec-evidence-2026-10-04-v2
PYTHONPATH=local/broad-sec-evidence-2026-10-04-v2/source-archive/python \
  .venv/bin/python -m research.broad_sec_audit verify \
  --output local/broad-sec-evidence-2026-10-04-v2
```

Contact comes from `SEC_CONTACT_EMAIL` or the repository Git contact, without
logging it. `SOURCE_ARCHIVE.json` and `source-archive/python/` preserve the exact
40 processing files before collection. Reproduce with those archived modules,
the retained raw responses and unchanged parent evidence. Existing 38-file
discovery, 36-file SEC and 43-file frozen-stock source sets remain unchanged.

Review before real collection found two schema handling issues: SEC's valid
XSL subfolder primary-document paths and malformed `filings:null` responses.
Regression tests now retain the former and isolate the latter to an issuer
error without dropping sample rows. Other new cases include malformed numeric
facts and explicit fallback encoding for non-UTF8 original header names. The then-current
17 new tests and full 424-test suite passed. Independent review reports no
remaining critical or important blocker for this bounded collection stage.

The first real original-header preview exposed the tagged `.hdr.sgml` endpoint
format, distinct from colon-format full-submission headers. The original
registration, 40-source archive, responses and `FORMAT_FINDING.json` remain
at `local/broad-sec-evidence-2026-10-04/`; no derived report was written there.
The corrected v2 parser accepts both explicit formats and scopes tagged names,
CIKs and SIC to each FILER company-data block. A literal downloaded-header
fixture, joint-filer and form/CIK conflict tests cover the correction. The
full suite now passes 425 tests, including 18 new evidence-stage tests.

A temporary DNS failure interrupted original collection after 688 responses.
Its log and `TRANSPORT_FAILURE.json` remain preserved; resumption uses the
original archived processing source and leaves every cached response unchanged.
The v2 audit reuses exactly those response bytes and original acquisition
timestamps under a new source registration, without candidate replacement.

## Completed evidence audit — 2026-10-04

All 1,400 registered requests were attempted: 396 API roots, nine historical
submission archives and 995 original annual headers. There are 1,368 successful
responses and 32 retained CompanyFacts 404s. All 198 submissions roots and nine
archives joined without history errors. Every registered header was downloaded
and parsed; 2,800 original body/request files are preserved unchanged in both
versions. The sample remains exactly 198 CIKs and 1,000 issuer/formation rows.

| Formation | Sample rows | Direct GP/assets observations | Exact December-share observations | Rows with header evidence | Qualified issuers |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2017-06-30 | 100 | 25 | 42 | 85 | 0 |
| 2018-06-29 | 100 | 29 | 42 | 99 | 0 |
| 2019-06-28 | 100 | 32 | 47 | 100 | 0 |
| 2020-06-30 | 100 | 28 | 45 | 98 | 0 |
| 2021-06-30 | 100 | 22 | 44 | 98 | 0 |
| 2022-06-30 | 100 | 21 | 39 | 98 | 0 |
| 2023-06-30 | 100 | 23 | 46 | 99 | 0 |
| 2024-06-28 | 100 | 23 | 42 | 100 | 0 |
| 2025-06-30 | 100 | 21 | 42 | 98 | 0 |
| 2026-06-30 | 100 | 22 | 41 | 98 | 0 |

The totals are 246 preliminary direct GP/assets rows and 430 rows with exact
December-31 share observations. These are component observations, not reviewed
investment inputs: missing latest-vintage/amendment, accounting comparability,
preferred/common equity, share-class and split-basis proof can still block use.
Missing CompanyFacts affects 158 sample rows. Nine additional issuer/year rows
have explicit fact-accession/publication disagreements; none are repaired by
tag preference or date substitution. All 10,000 qualification checks remain
missing and every formation has zero qualified issuers.

Of the 995 header observations, 610 have SIC outside the 6000–6999 range,
370 are inside it and 15 have no recognized SIC. These are original-header
observations for review; they are not counts of eligible historical stocks.
Current API names/tickers/SIC never replace historical evidence. The previous
infeasible fixed-panel result and the minimum-three/target-four validated
strategy release requirement remain unchanged. No strategy performance,
market-data purchase or ML training was launched.

Final local evidence: `local/broad-sec-evidence-2026-10-04-v2/REPORT.html` and
`EVIDENCE.json`. The latter retains every sampled row, original reference,
header, component and missing qualification gate. Next is bounded review of
the identified original financial statements/XBRL, amendments and historical
listing/share-class evidence. Price/action/delisting and project-use proof still
need independent qualification before registering any performance campaign.

The archived-source semantic verifier successfully reproduced the full evidence
JSON, coverage and HTML from the original responses. A fresh full-suite run
after session recovery passed all 425 tests. Both processing archives and all
2,800 reused body/metadata files match their recorded hashes; the earlier
36 SEC and 43 frozen-stock source hashes remain unchanged. All generated
artifacts are ignored by Git.

## Bounded readiness review — 2026-10-04

**Decision: the current free inputs cannot yet support the registered fundamental
backtest. Move to a paid-data coverage/licensing pilot rather than another broad
SEC collection.** This is a finding about our saved inputs and reviewed providers,
not proof that no free source could ever supply the data. Existing price-based
exploratory backtests remain available; this decision concerns the new broader
gross-profitability/value study. No new strategy return was calculated.

The review preserved the 198 CIKs, 1,000 sample rows, fixed selection order and
ten-issuer floor. Before requesting documents it registered the first three
direct GP observations in the 2017 sample: Sanmina, Houston Wire & Cable and
Spartan Motors. It used no returns, current-ticker filter or replacement. Nine
public SEC requests retrieved each original primary filing, directory index and
XBRL instance, using the existing downloader/parser. All nine returned HTTP 200;
the original bodies, timestamps, hashes and processing source are retained.

| Original issuer/ticker | Fiscal end | Filed | Gross profit (USD) | Assets (USD) | Original listing observation |
| --- | --- | --- | ---: | ---: | --- |
| Sanmina / SANM | 2016-10-01 | 2016-11-18 | 514,282,000 | 3,625,222,000 | Common stock, Nasdaq Global Select |
| Houston Wire & Cable / HWCC | 2016-12-31 | 2017-03-24 | 52,950,000 | 175,870,000 | Common stock, Nasdaq Global Market |
| Spartan Motors / SPAR | 2016-12-31 | 2017-03-03 | 72,528,000 | 243,294,000 | Common stock, Nasdaq Global Select |

All six aggregate numeric observations match exact non-dimensional original
XBRL facts and the displayed consolidated statements, with the statements'
thousand-dollar units respected. Business descriptions support nonfinancial
classification at those filings. The original filing covers/Item 5 establish
common-stock listing observations at filing time, not complete continuity to
formation or through a holding period. No relevant annual amendment appears in
the saved pre-formation references for these three selected fiscal years; this
limited check does not certify every amendment or historical filing-index vintage.

Original sources: [Sanmina 2016 10-K](https://www.sec.gov/Archives/edgar/data/897723/000089772316000049/sanmina10-k_oct12016.htm),
[Houston Wire & Cable 2016 10-K](https://www.sec.gov/Archives/edgar/data/1356949/000161577417001229/s105507_10k.htm),
[Spartan Motors 2016 10-K](https://www.sec.gov/Archives/edgar/data/743238/000143774917003752/spar20161231_10k.htm).

Spartan illustrates why an unreviewed revenue-minus-cost mapping is unsafe:
its reported gross profit also deducts USD 136,000 of restructuring costs above
gross profit. Omitting that line would overstate the numerator. These spot
checks support continued accounting research, not full accounting qualification.

The market-data problem is concrete. Nasdaq records HWCC's last trading date
as 2021-06-15, suspension on June 16 and USD 5.30 cash merger consideration per
share. The payment date still requires separate evidence. Spartan became Shyft
and changed SPAR to SHYF in June 2020. Neither a current-ticker lookup nor
forward-filled final prices supplies those cash/security transitions. Sources:
[Nasdaq's HWCC merger notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2021-99),
[the issuer's name/ticker announcement](https://www.prnewswire.com/news-releases/spartan-motors-announces-new-corporate-name-the-shyft-group-301068309.html),
[Shyft's subsequent original 10-Q](https://www.sec.gov/Archives/edgar/data/743238/000143774920022774/spar20200930_10q.htm).

The available stock-price snapshot contains 22 surviving stocks plus SPY. None
of its 19 mapped nonfinancial issuer CIKs occurs in the broader sample; none of
the three reviewed original symbols has cached bars. It is not a substitute for
matched broader-sample prices. Across all ten formations, 20–32 preliminary
direct GP observations also have matching original nonfinancial header SIC.
That is a potentially useful review pool, not 20–32 eligible stocks: original
accounting, listing/class continuity, tradability, price/action/delisting data and
project-use entitlement remain incomplete. No formation has ten demonstrated
usable issuers, so the performance campaign remains unlaunched.

Gross-profitability does **not** need value-specific December-31 outstanding
shares or preferred-equity deductions. Those requirements continue to constrain
value research, but must not unnecessarily delay a separate GP campaign.
Historical identities, accounting, prices/actions and research-use rights are
still necessary for GP. Preserve the existing audit; register the family-specific
performance requirements only when its inputs are available. Ten annual formation
dates from June 2017 to June 2026 are not ten completed holding years: the last
holding period is partial at 2026-10-02.

The free-path review also separates history from usable coverage. Alpaca Basic
documents history since 2016, so it is not rejected merely for insufficient
history; full historical identity/action/outcome coverage and this project's
entitlement have not been demonstrated. EODHD's current free plan offers one
year, Massive Basic two years, and Sharadar's free sample only the current Dow
30. Those do not supply this fixed broader study. Sources:
[Alpaca plan documentation](https://docs.alpaca.markets/us/docs/about-market-data-api),
[EODHD plans](https://eodhd.com/pricing),
[Massive stock plans](https://massive.com/stocks),
[Sharadar sample scope](https://sharadar.com/).

The concrete paid shortlist and acceptance brief are in the
[independent-data document](INDEPENDENT_DATA_RETEST.md#broader-fundamental-study-paid-data-brief--2026-10-04).
First seek the appropriate Nasdaq/Sharadar commercial research offering, with
EODHD Internal Use as the lower published-price alternative subject to its
historical identity gaps. A price-only upgrade is not sufficient by itself.

Local evidence is `local/readiness-review-2026-10-04/`: `REGISTRATION.json`, nine
body/request pairs, `ORIGINAL_RECONCILIATION.json`, `MANUAL_REVIEW.json`,
`ASSESSMENT.json`, integrity manifests and the exact 1,000-row `VENDOR_SCOPE.csv`.
The standalone scripts use the repository environment and existing research
parsers; no production or frozen processing source changed. Offline reproduction:

```bash
PYTHONPATH=python .venv/bin/python \
  local/readiness-review-2026-10-04/assessment.py
```

Fresh archived-source verification reproduced the parent 1,000-row SEC audit,
including its 32 retained HTTP failures. The bounded assessment independently
reparsed all three original instances and checked all six facts, nine successful
requests, input hashes, exact vendor scope and coverage counts. The 36-file SEC,
38-file broader discovery, 40-file broader SEC and 43-file frozen-stock processing
archives remain unchanged. No new production logic was added; the prior 425-test
suite result is historical, not a new test run for this documentation review.
