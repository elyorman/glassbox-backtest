# Quant Platform — Codebase Audit

2026-10-04 · Elyorjon Mannonov

## Verdict

Codex built a careful, well-tested financial core for stages 1–5, and no critical bug turned up in it. One crash and two medium defects need fixing.

The bigger problems are process. Nothing is committed to git, reproducibility depends on gitignored copies, and the last day went to post-V1 SEC research. Stages 6–9 and the three required strategies are still at zero.

Scope: a read-only review of all code, tests and docs, plus a full test run. Four parallel reviewers reproduced every confirmed finding with throwaway scripts.

## Where the build stands

Stages 1–5 of the nine-stage roadmap have real, tested engine code. Stages 6–9 (ML, scanner, desktop UI, packaging) have not started. Zero of the minimum three built-in strategies have qualified. All 425 tests pass locally (24 s), which matches the README.

| Stage | Status | What exists (unit tests) | Main gaps vs PROJECT.md |
| --- | --- | --- | --- |
| 1. Market data | Partial | CSV import, immutable Decimal snapshots, data-quality checks, JSON snapshot storage (28) | No Parquet/DuckDB, no EODHD/Tiingo adapter, no point-in-time index membership |
| 2. Backtester | Built | Long-only next-open engine, shared cash, costs, splits/dividends/delistings, stops, audit bundles (60) | Target/trailing exits; Windows result check |
| 3. Risk & sizing | Built | Fixed allocation, fixed-fractional, ATR sizing; position/exposure/group/liquidity/heat limits; drawdown halt (55) | Real-data validation |
| 4. Strategies | Built | Five rule families, ten recipes, auditable signal decisions (47) | None qualified for release |
| 5. Validation | Partial | Frozen campaign framework, append-only trials, paired bootstrap, consumed-once holdout (49) | Only synthetic campaigns run; 0 of 3 required strategies qualified |
| 6. ML models | Not started | 67-line features module | No models, no training pipeline (a Developer/Source V1 deliverable) |
| 7. Scanner/analytics | Partial | Return metrics in core (Sharpe, Sortino, Calmar, drawdown, turnover) | No scanner, Trade Explorer or trade-level analytics |
| 8. Desktop UI | Not started | Nothing (no `apps/` directory) | Everything |
| 9. Packaging/licensing | Not started | Nothing | Everything |

The other 186 tests cover research scripts, not product code.

## Bugs

No critical bug was found: nothing we tested silently corrupts cash, P&L or causality. One high-severity crash and two medium defects are confirmed with reproduction scripts.

| Severity | Where | Defect | Concrete failure |
| --- | --- | --- | --- |
| High | `strategies/__init__.py:266-279`, `execution/__init__.py:23` | Rebalances buy "target minus held" shares. After a non-integer split the difference is fractional, and the order constructor raises instead of rejecting. | 9 shares, 3:2 split, 13.5 shares; month-end target 14, buy 0.5, `ValueError`, whole backtest aborts. Affects the equal-weight benchmark and every scheduled-slot recipe on real S&P/Russell history. |
| Medium | `data/quality.py:69` | The price-jump check uses a strict `> 0.50` and only warns. | An unrecorded 2:1 split (exactly −50%), 3:2 (−33%) or 5:4 (−20%) is never flagged; a held position takes a silent −50% mark. |
| Medium | `validation/campaign.py:331` | The nomination tie-break table omits `low_vol`. | An eligible low-volatility candidate raises `KeyError`, which the CLI does not catch. Campaigns bind the engine hash, so a later fix cannot rescue that campaign. Latent today. |

Smaller issues, all reproduced unless noted:

- If equity reaches zero mid-run, later returns are `None` and `summarize_run` crashes (`analytics/__init__.py:29`); `docs/VALIDATION.md` promises a CAGR of −1.
- A cost written `"10.0"` with primary `"10"` passes validation, then breaks the phase with a `KeyError`. Root cause: equal Decimals hash differently (`provenance/__init__.py:15`).
- A split ratio is one Decimal, so a 1-for-7 reverse split leaves 99.9999999999 shares and a 100-share sell is refused (`engine.py:169`).
- With risk on, a final-session buy is counted "rejected", not "expired" (`engine.py:409`), contradicting `docs/BACKTESTER.md`.
- No single trade record links entry to exit, and stop fills carry the entry's signal date (`engine.py:277`). The AGENTS.md trade-audit list implies one (from reading).
- The independent-data crosscheck reruns its search test with one candidate, ignoring the original selection search (`campaign.py:419`; from reading).

## Other mistakes and risks

The biggest problems are process, not code. Several followed explicit task instructions recorded in the docs ("no Git action"; each research step "authorized"), so they are steering issues as much as agent errors.

| Severity | Issue | Why it matters |
| --- | --- | --- |
| High | **No version control.** Zero commits: about 14,500 lines of code and 400 KB of docs have sat untracked for three days. | One `git clean -fdx` or disk failure (the disk is 96% full) loses everything. There is no review trail, and it bypasses the team's ticket-branch workflow. |
| High | **Reproducibility lives outside the repo.** Research checks hash the whole live code tree (`research/robustness_audit.py:55`), so adding the SEC modules already broke `stock_campaign.py verify`. Frozen sources survive only as 8 copied trees in gitignored `local/`, and two cited results come from untested scripts there. | The frozen SMA200 retest can now run only from an archive copy. Git tags would replace all of this. |
| High | **Effort went off the critical path.** About 20 of 52 hours went to SEC fundamentals research: 2,398 lines (63% of the core's size), 121 tests, 83 KB of docs and 2.4 GB of local data. PROJECT.md lists fundamentals as post-V1. | Outcome: the study was found infeasible, with zero qualified issuers. Meanwhile the Stage 1 gaps stayed open and product code has not changed since Oct 3. |
| Medium | **The only surviving candidate rests on a hindsight-picked panel:** 24 of today's mega-caps, chosen on 2026-10-03 (`research/stock_data.py:19`). The planned retest reuses the same panel and window. | A second vendor can confirm the numbers but cannot remove survivorship bias. |
| Medium | **No point-in-time index membership.** `universe_policy` is free text that nothing enforces. | S&P 500 and Russell history is a V1 requirement and a precondition for credible strategy qualification. |
| Medium | **Docs have turned into changelogs.** The same dated SEC status sections are copied into AGENTS.md, DATA_LAYER.md and VALIDATION.md and paraphrased in three more files, in prose like "body-bound nonfinancial-amendment exemptions". | AGENTS.md is loaded into every agent session, so the rules get buried; humans cannot skim any of it. |
| Medium | **Storage will not scale as built.** Pure-stdlib Decimal and JSON snapshots, no Parquet/DuckDB. A 100-stock decade is a 32 MB snapshot that takes 4.4 s to load, at about 1.3 KB of memory per bar. | The engine itself scales (about 37 ms per stock-decade), but Russell-1000 panels and a scanner need the Parquet layer first. |
| Low | **Research code is much rougher than core:** 406 multi-statement lines versus 4. Also, `.env` is mode 664, one download spoofs a browser User-Agent, and `local/` holds about 1 GB of identical copies. | Developer/Source ships source and the training pipeline, so this style must not reach product code. |

## Strengths

The financial core is unusually disciplined for three days of work. The engine is the strongest part of the repo, and the claims made about it hold up.

- **Exact, isolated arithmetic.** Decimal everywhere, binary floats rejected at the boundary (`data/__init__.py:10`), and a fixed 28-digit context per run (`engine.py:39`). A test proves the caller's decimal settings cannot change results.
- **Self-reconciling ledger.** Cash is reconciled after every movement and two equity identities at every close (`portfolio/__init__.py:78`). A 40-seed random stress run with splits, dividends and fees rebuilt cash independently to within 4e-23.
- **Look-ahead guarded by design and by test.** History is sliced by date, and splits and dividends are filtered to the signal date (`backtest/sources.py:37-47`). Tests mutate future prices and splits and assert earlier decisions do not change.
- **Hand-calculated tests, not self-generated golden files.** Reviewers re-derived the backtest fixture, round-trip costs, the ATR seed (4.25) and a loss budget (86.806) by hand. Sharpe, Sortino, CAGR and drawdown match NumPy to about 1e-14.
- **Realistic, stated execution rules.** Signals use the close and fill at the next open with adverse slippage; stops fill at the gap open, zero-volume bars cannot fill, and sells precede buys. Every run manifest lists 18 or more assumptions.
- **Honest research hygiene.** An append-only, hash-chained trial registry, a consumed-once holdout, and honestly labelled statistics (the search diagnostic is "not a DSR"; win rate is per sale fill). The README states that zero strategies qualified, with no performance hype.
- **Credential hygiene.** `.env` is gitignored, and the Alpaca key values appear nowhere in code, docs or the 4.4 GB of generated output.

## Fix first

Committing the work comes before any code fix: it is the one risk that can erase everything else.

1. **Commit today.** Put the repo under git on a ticket branch in reviewable commits (data, backtester, risk, strategies, validation, research). Tag the frozen campaign sources, then delete the archive copies in `local/`.
2. **Fix the split-rebalance crash.** Floor the buy amount in `strategies/__init__.py:267`, have the engine reject rather than raise on a fractional buy, and add a 3:2-split rebalance test.
3. **Harden the split check.** Catch exact 2:1, 3:2 and 5:4 gaps, and make an unexplained split-sized jump an error in strict mode.
4. **Add `low_vol` to the nomination tie-break table**, with a test that nominates a low-volatility candidate.
5. **Pause the SEC track and clean the docs.** Move dated status logs out of AGENTS.md and PROJECT.md into one research log.
6. **Return to the critical path.** Build the EODHD adapter, Parquet import and point-in-time universes. Then run a fresh, survivorship-aware campaign for the three required strategies.
