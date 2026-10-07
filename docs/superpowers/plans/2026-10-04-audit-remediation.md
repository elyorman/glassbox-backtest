# Audit Remediation Implementation Plan

**Goal:** Correct the verified audit defects, preserve frozen evidence, and add usable data/provider and historical-universe foundations.

**Architecture:** Keep provider access outside strategy/backtest code. Preserve legacy snapshots and frozen source archives; corrections produce new engine evidence, never rewrite old results. Add explicit dated membership and optional Parquet storage without claiming vendor or historical-universe qualification.

**Tech stack:** Python 3.12, unittest, Decimal; optional PyArrow for Parquet.

**Spec:** `CODEX_AUDIT_2026-10-04.md`, `PROJECT.md` PR-01–PR-06, PR-08, PR-13.

## Constraints

- No commits, branches, purchases, provider downloads, external writes or archive deletion.
- Work in the authorized existing repository; Git-based skill bookkeeping is replaced by the source baseline and this ledger.
- Baseline source/tests/docs are preserved in `local/audit-remediation-2026-10-04/baseline-source.tar.gz` with a verified manifest.
- New results must be distinguishable from old results. No silent retuning, invented corporate actions, current-member historical fallback, or data qualification inferred from payment.
- Run regression tests before fixes; use the existing virtual environment and unittest.

## Review focus

- Fractional split holdings, repeating reverse-split ratios, pending orders and stops.
- Wipeouts followed by undefined returns, and unexplained price discontinuities.
- Equivalent numeric configuration spellings, all supported candidate families, and preservation of search history.
- Malformed/provider error responses, unknown dividend payment dates, credential leakage and adjusted-price contamination.
- Entry/removal/re-entry membership boundaries, unknown history, stale data and immutable Parquet publication.

## Task 1 — Financial regression fixes

Files: `quant_core/strategies`, `backtest`, `analytics`, `data` split contract/storage/adjustments; corresponding unittest files.

- [x] Add failing regressions for fractional rebalance buys, exact reverse splits, wipeout reporting and final-session risk buys.
- [x] Emit whole-share buys while retaining fractional holdings/sells; support explicit exact new/old split counts rather than guessing ratios from prices or truncated decimals.
- [x] Keep undefined returns visible after zero equity, report total loss correctly, and return null undefined ratios.
- [x] Classify otherwise valid final-session orders consistently; preserve risk and stop provenance.
- [x] Verify affected suites and legacy snapshot/run compatibility.

## Task 2 — Validation and data-quality fixes

Files: `quant_core/validation/campaign.py`, `contracts.py`, `quant_core/data/quality.py`, validation/data regression tests.

- [x] Add failing regressions for `low_vol` nomination and equivalent cost spellings.
- [x] Normalize scenario labels locally, cover all research-family tie-breaks, and keep legacy content hashes stable.
- [x] Explicitly retain original search context in provider crosschecks; never present nominee-only diagnostics as a repeat of the full search.
- [x] Flag exact threshold and suspicious common split-sized discontinuities without inventing repairs; block unresolved suspicious events in strict runs.
- [x] Verify narrow suites and full suite.

## Task 3 — Preservation and reproducibility

Files: new `research/source_archive.py`, tests, `docs/REPRODUCIBILITY.md`.

- [x] Add failing tests for exact source-set archive integrity, tampering, safe paths and unchanged existing output.
- [x] Add source-only archival/verification/replay commands, with no secrets, extraction over live code, arbitrary runtime evaluation, or deletion.
- [x] Allow legacy verification via its exact archived runtime; do not relax frozen hashes or recompute old evidence with corrected code.
- [x] Provide a portable baseline package; clarify that a same-disk archive is not protection against disk failure.

## Task 4 — Data integration and storage

Files: new data EODHD adapter and Parquet modules/tests; CLI integration and optional dependency.

- [x] Write failing offline fixture tests for API normalization, provider error handling, raw-price semantics, action incompleteness, precision and provenance.
- [x] Implement EODHD raw daily-price adapter with cached original response bytes and explicit supplied calendar/security identity. Never fetch corporate-action data implicitly or expose API tokens in errors/cache names.
- [x] Implement optional Parquet snapshot persistence/import with exact decimal text and hashed manifests; preserve JSON compatibility and immutable writes.
- [x] Test full round trips, corruption, malformed schemas and missing optional dependency behavior.

## Task 5 — Dated universe foundation

Files: new `quant_core/universes`, tests and CLI/API integration.

- [x] Add failing tests for membership intervals, re-entry, inclusive/exclusive boundaries, availability dates and unknown coverage.
- [x] Implement validated CSV/JSON dated membership with stable security IDs and explicit coverage; reject unknown historical membership instead of substituting current constituents.
- [x] Connect dated membership to strategy eligibility while allowing removed holdings to exit. Preserve custom static-universe behavior.
- [x] Demonstrate provider/import → membership → strategy → portfolio flow on hand-calculated synthetic data.

## Task 6 — Documentation, integration and review

- [x] Consolidate repeated SEC dated status into a research status document; keep stable requirements in AGENTS/PROJECT and preserve linked historical evidence.
- [x] Document data commands, precise split semantics, wipeout metrics and remaining production limitations.
- [x] Run full suite and archived 99-bundle verification; compare preserved source/archive hashes.
- [x] Request one independent final code review, address material findings with regression tests, and report remaining limitations.

## Execution ledger

- Baseline: source/tests/docs (113 files) archived and content-verified before edits. Previous fresh verification: 425 tests; 99 archived portfolio bundles; 40 stress runs.
- Ruling: user authorization is for implementation; no plan approval pause, worktree, Git actions, or destructive cleanup.
- Ruling: independent data/provider, universe, and financial tasks may run in parallel with separate file ownership. Integration and review remain sequential.

- 2026-10-05 resumed completion: 505 tests passed (40.974 seconds), including optional Parquet tests with PyArrow 23.0.1. Actual CLI smoke import → Parquet → dated strategy → saved/verified portfolio has the expected 10-share A buy, 10-share A sale and 20-share B buy; ending equity USD 1,000. This is synthetic, unqualified evidence.
- Independent final review identified known-dividend false discontinuities, the missing-bar opt-in bypassing the strict discontinuity gate, and unchecked cached bytecode during archived replay. Each was reproduced with a failing regression and corrected; all regressions and the full suite pass. No additional material findings were reported in that review pass.
- Original baseline archive and all 113 contents still match their recorded hashes. Frozen source manifests verify: stock 43 files; SEC original/corrected 40 each; broader universe 38. A new 59-file version-0.5.0 source archive verifies under ignored `local/source-archives/core-0.5.0`.
- The 99-bundle verification passed again through the hardened clean-copy replay path, with exit status 0. The current 59-file source archive also matches every live Python source hash. Final evidence: `local/audit-remediation-2026-10-04/FINAL_VERIFICATION.json`. All scoped tasks are complete.
- Documentation is consolidated and 11 changed documents have no missing local link targets. No Git actions, market-data purchases/downloads, evidence deletion or external backup transfer were performed.
