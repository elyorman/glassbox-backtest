# Independent Data Qualification Implementation Plan

**Goal:** Make saved provider actions auditable and produce a concrete, fail-closed preflight package for the frozen SMA200 retest.

**Architecture:** Provider normalization stays in the data layer; retest readiness stays in research tooling. Audit original split/dividend bytes before supplying reviewed domain actions. Compare candidate snapshots and reviewed qualification against the exact frozen scope without running or changing the strategy.

**Tech stack:** Existing Python 3.12 virtual environment, unittest, Decimal; existing JSON/Parquet loaders.

**Spec:** PROJECT.md PR-01, PR-05, PR-08–PR-10, PR-13; docs/INDEPENDENT_DATA_RETEST.md; official EODHD price/action documentation checked 2026-10-05.

## Constraints and rulings

- Existing user authorization covers local implementation and read-only research. No purchases, messages to vendors, live authenticated downloads, Git actions, credential reads or changes to frozen evidence.
- Use inline execution; the standing user instructions override skill Git/approval/worktree defaults. Request one independent final code review after meaningful implementation.
- The existing frozen strategy, survivor sample, eight qualification capabilities and provider tolerances remain unchanged. A preflight is not a fresh temporal holdout, full campaign verification, rights approval or strategy qualification.
- Split-endpoint ratios can describe reorganizations/spinoff adjustments, not only share splits. Require an exact-date/ratio-bound independent share-split classification before creating Split objects. Never infer event type from a tidy ratio.
- Preserve raw bytes and historical unadjusted dividend cash. No adjusted-value fallback, guessed payment date, currency conversion, raw-volume reconstruction or inferred action completeness.
- New schema-2 exact-count snapshots must be flagged as incompatible with the schema-1 frozen runtime. Do not silently approximate or rewrite the registered procedure to admit them.

## Review focus

- Missing historical dividend amount, missing/invalid payment date, currency mismatch and duplicate ex-dates remain visible or fail safely.
- Ratio-only adjustments that are not reviewed share splits must not create portfolio shares.
- Malformed/provider error bodies must never echo raw content or credentials; empty action arrays do not prove no actions.
- Candidate dataset/provider independence, calendar, stable security set, strict data quality and frozen JSON schema compatibility must be checked independently.
- Missing/mismatched qualification and the EODHD adjusted-volume limitation cannot yield an input-ready status; original artifacts remain immutable.

## Task 1 — Offline corporate-action audit

Files: new python/quant_core/data/eodhd_actions.py; tests/test_eodhd_actions.py.

Interfaces: audit_actions(ticker, security_id, splits_raw, dividends_raw, *, start, end, retrieved_at, split_reviews=(), cache_dir=None) -> ActionAudit. ReviewedSplit binds session, original ratio text and SHA-256 review evidence. ActionAudit exposes proposed domain actions, per-row unresolved issues, source hashes and has_unresolved; never asserts complete coverage.

- [x] Add failing hand-calculated tests for exact reviewed 1-for-3 shares, same-date split/dividend, unadjusted cash/payable dates, empty responses, missing amount/payment/currency, reorganization ratios, stale reviews, duplicate fields/dates, redacted malformed input and immutable raw cache.
- [x] Implement the minimal action audit with exact Decimal parsing and explicit per-event review bindings. Retain omissions as rows/issues, not fabricated actions.
- [x] Add a standalone developer CLI to save an immutable JSON audit and optionally export proposed CSV actions only when every returned event is resolved. Export is not coverage/rights qualification.
- [x] Run the narrow tests; ensure supplied audited actions work with EodhdJsonSource through an explicit overall review hash.

## Task 2 — Frozen retest input preflight

Files: new python/research/data_preflight.py; tests/test_data_preflight.py.

Interfaces: preflight(snapshot, frozen_plan, qualification=None) -> dict; qualification_template(snapshot, frozen_plan) -> schema-1 unresolved qualification envelope. CLI accepts --campaign, --snapshot, optional --qualification, --output directory; it saves input-bound report, frozen scope and unresolved review template without executing portfolios.

- [x] Add failing tests: complete distinct reviewed input passes mechanical preflight; same-provider/data, mismatched sessions/IDs, incomplete actions, unreviewed capability, stale qualification, strict gap errors, adjusted-volume limitation and schema-2 snapshot each block it. All checks remain in the report together.
- [x] Implement mechanical checks, explicit interpretation and binding to the frozen campaign artifacts/source manifest. Templates keep every capability unresolved and preserve the fixed-sample/exposed-history disclosures.
- [x] Test JSON/Parquet CLI inputs, refusal to overwrite evidence and malformed/changed campaign bindings. The package contains hashes/metadata, never prices, secrets or whole dataset copies.
- [x] Run preflight on the existing cached development snapshot and save the actual blockers. Do not mark a development source independently qualified.

## Task 3 — Documentation and verification

Files: docs/DATA_QUALIFICATION.md; docs/DATA_INTEGRATION.md; docs/INDEPENDENT_DATA_RETEST.md; README.md; this ledger.

- [x] Document source semantics, commands, reviewed action classification, frozen-runtime compatibility and exact remaining pilot inputs. Update only current status; preserve historical findings.
- [x] Obtain one independent final review; reproduce/fix material findings with regression tests.
- [x] Run the full unittest suite, actual CLI preflight on cached data and synthetic end-to-end action import. Verify the preserved version-0.5.0 source archive. Record concrete results and remaining external-input dependency.

## Execution ledger

- Source baseline: verified version-0.5.0 archive at local/source-archives/core-0.5.0 (59 files); 505 tests and all 99 frozen backtests passed before this task.
- Available local inputs: existing Alpaca/SIP development snapshot and SEC originals; no independent EODHD market export found in local top-level artifacts. Asked an optional account/export question while implementation proceeds; no account or rights assumption is made.

- Completed 2026-10-05: 15 action tests plus 16 preflight tests were observed failing before implementation/fixes, then passed. The full 536-test suite passes in 37.533 seconds, including Parquet.
- Actual preflight v2 retains the original scope and source bindings. Mechanical blocks: original dataset/provider, incomplete actions and no qualified review. All eight capability records remain unresolved; original payment-date count 336 is bound to the registered readiness hash. Exit 1 is the expected blocked-input outcome, not a failed tool run. The original preflight attempt remains preserved.
- Independent final review: reproduced/fixed snapshot/qualification/campaign/readiness parse/hash changes, conflicting duplicate review fields and secret-bearing malformed diagnostic text. Six additional regressions pass. No vendor/rights claim is inferred from those engineering tests.
- Synthetic saved-response audit → exact-count CSV → EODHD normalization → portfolio → saved-run verification passes: 300 old shares become 100, dividend cash USD 30, final equity USD 300. It explicitly allows incomplete-action diagnostics and claims no market qualification.
- Version-0.5.0 archive (59 files) and all four historical source manifests remain unchanged. New version-0.5.1 archive (61 files) verifies and matches live source. Seven changed documents have no missing local file targets.
- Final evidence/logs: local/data-qualification-verification-2026-10-05.json, local/data-qualification-tests-2026-10-05.log, local/data-preflight-2026-10-05-v2 and local/action-qualification-smoke-2026-10-05. No provider acquisition, purchases, external messages, Git operations or new strategy performance.
- Remaining external dependency: independent market exports and actual reviewed entitlement/source/action/calendar/identity/volume evidence. No EODHD account/export answer arrived during this stage. The completed tooling does not mark those unavailable inputs qualified.
