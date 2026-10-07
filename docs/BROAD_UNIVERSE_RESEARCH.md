# Broader Fundamental Universe Study

Authorized 2026-10-04 following the infeasible fixed-panel
[capital audit](FUNDAMENTAL_CAPITAL.md). Supports PR-01, PR-05, PR-06,
PR-08, PR-13 and PR-14. This is a separately registered, research-only
candidate-discovery and data-readiness stage, not a performance campaign.

## Design and decisions

Keep June formations 2017–2026, annual 330–380-day accounting periods ending
in calendar year t−1, exact December-31 common shares, strict filing-before-
formation availability and the ten-eligible-issuer floor. The old 17-stock
study remains infeasible and unchanged. Do not expand its registrations.

Three approaches were considered: enlarging today's ticker list (retains
survivor bias); buying a historical security master now (requires an entitled
supplier/account and purchase authorization); and using historical SEC filing
indexes to discover candidates while enforcing separate security/data gates.
Choose the third for this free-data development stage. A filing candidate is
not necessarily an exchange-listed common stock: private issuers, financials,
funds and multiple classes require historical evidence and explicit review.
No name heuristic or current ticker/exchange/SIC membership can substitute.

Collect the 42 fixed SEC quarterly `master.gz` indexes, 2016Q1–2026Q2. For each
formation, candidate CIKs must have a 10-K or 10-K/A dated from January 1 of the
prior calendar year through strictly before formation. This trailing window
is discovery only; it never asserts the filing's financial period is eligible.
Retain all original annual accession/path/name/date evidence. Deduplicate by issuer CIK plus accession and reject conflicting annual-candidate
identities, malformed rows and wrong quarters. Shared submissions under distinct
CIKs remain separate entities; combined nonannual schedules remain noncandidates.
Missing original names remain empty, including for annual candidates; they are
never filled using today's metadata or used to remove a CIK from discovery.
An accession's leading CIK can be a filing agent, different from issuer CIK.
Never merge issuer identities or successor CIKs from company names.

Choose at most 100 review candidates per formation by ascending SHA-256 of
`quant-platform-broad-fundamentals-v1:<zero-padded-CIK>`, with CIK as tie-break.
This deterministic sampling is unrelated to returns, current existence,
accounting availability or provider coverage. It is a feasibility workload
limit, not an investment rank. Missing/rejected candidates are not replaced.
The complete roster and all unselected candidates remain available locally.
Membership can vary historically; do not take the future union as an earlier
formation's universe. The same issuer can be sampled at several formations.

SEC quarterly indexes are retrieved now and can be rebuilt for post-acceptance
corrections/deletions. Historical filing-date filtering is **not** certified
historical security membership or an original as-of index snapshot. This
limitation remains in registration/report/readiness gates. Daily dissemination
archives or independently reviewed historical membership would be needed to
address it. Current SEC ticker files are never joined to create this roster.
[SEC access and index semantics](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

No performance is evaluated during candidate discovery. Existing 2016–2026
history has already been examined; a new universe does not reset the search
history or restore untouched temporal OOS. Preserve the proposed value and
gross-profitability economic hypotheses and do not tune sample selection to
make their results attractive. Performance recipes, full trial budget and
matched benchmarks must be registered separately after actual input readiness.

## Architecture and implementation plan

Python standard library, repository virtual environment, exclusive-create
JSON/raw registries and standalone HTML. New research modules leave all
previous processing sources unchanged. No dependency install, branch, commit,
purchase, model training or network upload of research data.

1. `python/research/broad_universe.py`, `tests/test_broad_universe.py`:
   - [x] Write failing hand-sized index fixtures for same-day/future filings,
     discontinued issuers, private-like names, unrelated forms, duplicate and
     conflicting accessions, malformed paths/quarters, agent CIKs and amendments.
   - [x] Implement `parse_index(bytes, year, quarter)`, `candidate_panel(plan,
     indexes)` and `input_readiness(plan, panel, evidence)`; no price input in
     the selection interface. Retain per-formation provenance and sample ranks.
   - [x] Test deterministic sampling under row-order/future-index changes,
     no replacement on absent evidence, complete qualification/missing gates,
     hash/date/scope binding, class ambiguities and unchanged ten-issuer floor.
2. `python/research/broad_universe_audit.py`, `tests/test_broad_universe_audit.py`:
   - [x] Freeze study scope and exact 42 URLs before collection, parent evidence
     hashes, new processing-source hashes and canonical rules. Parent financial
     audit is already verified; verify its bytes/sources, do not rewrite it.
   - [x] Implement CLI `plan|collect|audit|verify` with declared SEC client,
     <=2 requests/sec, timeout/retry, original gzip bytes and status/URL/body
     hashes, orphan/partial detection and deterministic resumability.
   - [x] Freeze audit input hashes before arithmetic; export full roster,
     per-formation sample, unique-CIK follow-up requests, readiness blockers and
     HTML. Verify every derived row and report from original index bodies.
   - [x] Test partial/missing/changed requests, source/scope tampering, failed
     HTTP retention, orphan files and resealed roster/arithmetic tampering.
3. Real evidence and documentation:
   - [x] Register and collect the complete bounded index set; never infer
     success from synthetic tests. Preserve failed collections if applicable.
   - [x] Run audit, semantic verification, appropriate full suite and independent
     review. Archive exact new source files and preserve old audit/source hashes.
   - [x] Record actual coverage separately from eligible stocks. Report missing
     listing/identity, fiscal/class/accounting, raw-price/action/delisting and
     project-use evidence. Update current repository documentation.

## Input readiness contract

The optional evidence JSON contains `schema_version: 1`, exact `study_plan_hash`,
`candidate_panel_hash` and `checks` entries for every formation/sample CIK.
Each check binds the target formation and issuer, has `status` of `passed`,
`failed` or `missing`, and, when passed, names locally hashed evidence files
and a reviewer/date. Review cannot happen after the audit input registration. Evidence files
are copied into a registered input area; no arbitrary path or remote fetch is
allowed during arithmetic. Duplicate, unknown, missing or malformed checks do
not quietly become passes. A self-attested JSON is not independent verification:
its evidence and meaning still require review before any performance launch.

Required checks per issuer/formation are `historical_common_listing`,
`security_identity_and_classes`, `historical_nonfinancial_classification`,
`original_annual_accounting`, `preferred_and_december_market_equity`,
`raw_prices_and_complete_actions`, `delisting_outcomes`, `project_use_rights`, `coherent_gross_profit_and_assets`,
and `positive_common_book_and_market_equity`.
Qualified profitability additionally needs a reviewed coherent GP/assets pair;
value additionally needs positive common book equity and reviewed market equity.
Neither a SEC filing nor a successful request proves these facts. Readiness
without supplied/reviewed evidence is false, and performance is always disabled
in this discovery CLI. No fabricated qualification or sample replacement.

## Commands and outputs

```bash
PYTHONPATH=python .venv/bin/python -m research.broad_universe_audit plan \
  --parent local/sec-capital-2026-10-04 \
  --output local/broad-universe-2026-10-04-v2
PYTHONPATH=python .venv/bin/python -m research.broad_universe_audit collect \
  --output local/broad-universe-2026-10-04-v2
PYTHONPATH=python .venv/bin/python -m research.broad_universe_audit audit \
  --output local/broad-universe-2026-10-04-v2
PYTHONPATH=python .venv/bin/python -m research.broad_universe_audit verify \
  --output local/broad-universe-2026-10-04-v2
```

The declared SEC request contact uses `SEC_CONTACT_EMAIL` or the repository's
Git contact, kept out of evidence metadata. Collection uses sequential bounded
requests, cache reuse and retained HTTP failures. Every terminal HTTP response body is retained, including failures. Transient
429/5xx retries keep their status history; intermediate bodies are not archived.
A cached terminal failure is never overwritten by a later success. Resume only
complete successful requests and use a new output registration to retry a
terminal failure. Retrieval timestamps require explicit offsets, precede the
frozen audit, and cannot predate completion of the requested quarter. Cached
acquisitions may precede study registration; their original timestamps remain
unchanged, rather than being relabelled as new downloads.
Study and audit registrations and outputs use exclusive creation.

An optional `audit --evidence PATH` imports a reviewed evidence JSON and its
locally referenced proof files into the immutable audit input set. The actual
study currently supplies no qualification; absence is reported honestly.
Proof bodies and metadata are hashed, but review metadata alone cannot prove
their substantive correctness or enable performance. Follow-up CompanyFacts and
submissions URLs are planning outputs only; this stage does not automatically
download hundreds of unqualified issuers' filings or silently replace them.

`STUDY_PLAN.json` freezes the exact selection/source/scope before collection.
`AUDIT_INPUTS.json` fixes all successful responses/request metadata and any
review evidence before publishing derived results. `ROSTER.json` contains the
full roster at every formation, the deterministic samples, missing readiness
checks and unique-CIK follow-up URLs; `REPORT.html` is standalone. All generated
files stay in ignored `local/`. Semantic verification recomputes the complete
panel, readiness and report and rejects rehashed sample/count tampering.

## Real-data compatibility correction

All 42 registered responses downloaded successfully. The initial parser check
failed because it treated one accession as one indexed entity. The original
registration, 38-file processing archive, all 84 body/request files and the
failure record remain at `local/broad-universe-2026-10-04/`; it has no derived
roster or performance results. Do not rewrite that study's source hashes.

The corrected v2 study reuses the exact original bytes with original retrieval
timestamps. Real 2016Q1 rows show Ameren and Union Electric indexed separately
under a shared 10-K accession. Raw ledgers now use issuer plus accession and
preserve all identities. They reject different metadata whenever an annual
candidate is involved, including a conflicting 10-Q across another quarter.

The real index also contains combined nonannual schedules. SEC expressly allows
combined Schedule 13E-3/TO filings. These rows are validated structurally and
retained in the raw identity ledger, but do not enter annual candidate selection
or invalidate unrelated candidates. Literal original-row fixtures test both
cases; no returns, feature availability or provider coverage informed the
correction. [SEC combined-schedule interpretation](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations-cfis/going-private-transactions-exchange-act-rule-13e-3-schedule-13e-3).

An independent scan of all 42 responses also found one empty original company
name on a nonannual 485BPOS row in 2016Q1. The parser preserves the absence
verbatim. A regression fixture also checks that a hypothetical unnamed annual
candidate is retained without becoming qualified. Malformed CIKs, forms, dates
and paths still fail; a display name is not historical security identity proof.

The compact sorted ledger and streaming merge avoid retaining millions of full
metadata dictionaries across quarters. Physical submissions may be co-indexed
for several entities: annual counts are issuer/filing rows, not distinct legal
stock issuers or qualified tradable observations.

## Actual discovery results — 2026-10-04

The separate v2 study reuses all 84 original response/body metadata files and
archives its 38 exact processing sources. All 42 indexes contribute 11,522,189
indexed rows and 87,471 annual issuer/filing rows. Discovery coverage is:

| June formation | Filing candidates | Fixed review sample | Complete input reviews |
| --- | ---: | ---: | ---: |
| 2017-06-30 | 7,919 | 100 | 0 |
| 2018-06-29 | 7,612 | 100 | 0 |
| 2019-06-28 | 7,429 | 100 | 0 |
| 2020-06-30 | 7,269 | 100 | 0 |
| 2021-06-30 | 7,432 | 100 | 0 |
| 2022-06-30 | 8,162 | 100 | 0 |
| 2023-06-30 | 8,068 | 100 | 0 |
| 2024-06-28 | 7,622 | 100 | 0 |
| 2025-06-30 | 7,202 | 100 | 0 |
| 2026-06-30 | 7,154 | 100 | 0 |

There are 1,000 issuer/formation sample rows and 198 distinct review CIKs.
All 10,000 required input checks remain missing; no qualified universe or
strategy-performance result is inferred from these discovery counts. The
100-candidate cap limits work and does not guarantee the unchanged ten-issuer
floor will pass. The full suite passes 407 tests, including 19 focused broader-
study cases. Independent code review found no remaining important finding.

The archived-source verifier successfully recomputed the entire roster,
readiness and report from all 42 original bodies. Both 38-file broad-study
archives, all 84 reused response files, the old 36 SEC processing sources and
the 43 frozen stock-campaign sources match their original registered hashes.
The failed v1 registration and failure record remain unchanged. All generated
artifacts are ignored by Git.

Local report: `local/broad-universe-2026-10-04-v2/REPORT.html`. `ROSTER.json`
preserves the full per-formation roster, sampled historical filings and all
missing checks; unique-CIK follow-up URLs remain uncollected planning outputs.
Reproduce the completed audit using the frozen processing sources:

```bash
PYTHONPATH=local/broad-universe-2026-10-04-v2/source-archive/python \
  .venv/bin/python -m research.broad_universe_audit verify \
  --output local/broad-universe-2026-10-04-v2
```

The next bounded task was to collect historical SEC submissions/CompanyFacts
for these exact 198 CIKs, identify original annual documents and record
historical security/classification evidence. Keep every rejection and missing
input, without substituting attractive or data-rich issuers. Market prices,
actions, delisting coverage and project-use rights then need actual evidence;
SEC discovery alone cannot clear those gates. Register any performance study
only after independent input review, retaining all previously exposed history.

That [evidence-collection stage](BROAD_SEC_EVIDENCE.md) is now implemented for
the same 198 CIKs and 1,000 sampled rows. Its 396 API roots, nine archives and
995 original headers are retained separately, including 32 CompanyFacts 404s.
Preliminary component/header observations do not clear the qualification gates
or modify this discovery study. Original financial and historical security
review is the next bounded task; no performance campaign has launched.
