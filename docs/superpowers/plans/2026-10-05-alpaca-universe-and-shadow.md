# Alpaca universe transfer and forward signals

**Goal:** Test whether the four unchanged stock recipes transfer beyond the original 22-stock panel, and begin prospective operational tracking of the frozen SMA200 recipe.

**Architecture:** Research-only commands reuse the provider-neutral engine, existing recipes, immutable snapshots and verified run bundles. No production-core behavior, orders, paid feed, ML training or qualification gates change. This supports PR-01, PR-02, PR-05, PR-06, PR-08 and PR-13; it does not deliver their commercial release acceptance.

**Execution:** Implement inline under the user's existing authorization. No Git actions, delegation, additional approval gate or automatic workflow chain.

## Universe study

- [x] Preserve issuer roster probes. Require the date in the body, never assume a requested query date was honored. The first two probes did not return historical holdings.
- [x] Record a separate current-roster fallback before prices: 60 equity tickers selected by SHA-256 of `quant-platform-universe-transfer-v1-2026-10-05:<ticker>`, excluding the original requested 24-stock panel and SPY. Use issuer October 2, 2026 holdings; this remains retrospective survivor research, not historical index membership.
- [x] Download only Alpaca raw SIP daily bars and all action types for the fixed sample. Bound collection at 40 HTTP requests, including pagination; preserve failures, repeated tokens and exhausted budgets without hidden retries or replacements. Retain original response bytes and credential-free request metadata; refuse redirects and other hosts.
- [x] Assess each sampled name before performance. Require complete original 2,703-session coverage, valid bars and supported actions; retain all exclusions and unknown payment dates. Apply the existing withheld-receivable policy and strict discontinuity checks. At least ten eligible names are needed; otherwise retain infeasibility without substituting tickers.
- [x] Freeze source archive, coverage decisions, dataset and the existing 99-trial campaign protocol before outcomes. All four parents, neighbors, costs, delays, periods, cash conventions and economic objectives stay fixed; only the universe/data/source version changes.
- [x] Run and independently verify every portfolio. Compare all four outcomes with the original panel without treating comparison as independent validation or fresh OOS. Preserve originals and export coverage/results CSV and readable report.

## Forward SMA200 signals

- [x] Add research-only registration and append commands, using the exact frozen 22-stock SMA200 recipe and a zero-position $100,000 reference account for explainable signal/target diagnostics. This is a prospective signal journal, not a continuously simulated portfolio or broker account.
- [x] Start registration now, with no backdated records. Append only completed monthly signals after registration and before the next session opens; require a supplied calendar with timezone-aware close/open timestamps and snapshot retrieval before recording. Refuse stale, premature, incomplete, tampered and duplicate records.
- [x] Store recipe, source, calendar, dataset, decisions and input hashes in immutable locally chained records. Future bars/actions cannot affect decisions. No scheduling/cloud service or automatic orders.
- [x] Record that the current October 2 data cannot create a prospective signal. The next scheduled month-end is October 30; a short forward run tests operations, not statistical profitability.

## Verification and follow-up

- [x] Tests exercise ignored roster dates, deterministic sample independent of returns/weights, missing names, unsupported actions, unknown pay dates, causal forward signals, timestamp boundaries, input mutation and chain integrity.
- [x] Run focused tests, then the full unittest suite; verify campaign and original evidence hashes. Update current status and usage documentation.
- [x] Defer additional hypotheses until the transfer evidence is reviewed. If warranted, preregister a small distinct price-only hypothesis set before running it; do not sweep existing parameters to obtain passing results.

## Verified outcome

99/99 transfer portfolios verified; 47 of 60 sampled names simulated with no replacements. All four parents fail the full robustness rule. SMA200 passes the continuous objective but only one of three folds. Original evidence is unchanged. The original recipe is registered prospectively with zero records and an October 30 first window. Full suite: 562 passing tests. Additional hypotheses remain conditional follow-up under a new registration.
