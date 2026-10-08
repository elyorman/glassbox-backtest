# Research ledger

One line per study, past and future. Append only; never edit an outcome.
Counting rule: [evidence standard, Section 4](STRATEGY_EVIDENCE.md#4-trial-count-convention).
Studies before 2026-10-08 predate the git-tag process; their source archives
and evidence remain under `local/` on the original machine.

| Date | Study | Source | Trials | Cumulative | Outcome | Evidence |
| --- | --- | --- | ---: | ---: | --- | --- |
| 2026-10-03 | ETF market backtest (momentum 252/21 top 3 on 9 sector SPDRs) | pre-tag | 1 | 1 | Exploratory; no nominee | `local/market-backtest-2026-10-03/` |
| 2026-10-03 | All ten predefined recipes on the same sector-ETF panel (momentum 252/21 top 3 already counted) | pre-tag | 9 | 10 | No reliable benchmark superiority | `local/strategy-comparison-2026-10-03/` |
| 2026-10-03 | Robustness audit, two ETF parents: 6 momentum and 4 trend variants (lookback, top-k, mean window, ATR stop, 75% allocation; allocation variants counted conservatively) | pre-tag | 10 | 20 | Both parents fail predeclared objectives | `local/robustness-audit-2026-10-03/` |
| 2026-10-03 | Stock campaign, 22-stock survivor panel (4 parents + 4 neighbours) | pre-tag | 8 | 28 | SMA200 passes defensive screen; others fail | `local/stock-campaign-2026-10-03-finalized/` |
| 2026-10-05 | Corrected-engine replay of the 99 stock trials | pre-tag | 0 | 28 | Byte-identical outcomes | `local/stock-engine-replay-2026-10-05/` |
| 2026-10-05 | Universe transfer, 47-stock survivor panel (same 8 configurations) | pre-tag | 8 | 36 | All four parents fail full rule | `local/universe-transfer-2026-10-05-v2/` |
| 2026-10-05 | 52-week-high proximity, both panels (parent + neighbour × 2) | pre-tag | 4 | 40 | Rejected on both panels | `local/high-anchor-2026-10-05/` |
| 2026-10-06 | Unusual dollar volume, both panels (2 ranked + 1 control × 2) | pre-tag | 6 | 46 | Rejected on both panels; direction check fails | `local/volume-2026-10-06-finalized/` |
| 2026-10-06 | Research design review; market-adjusted momentum specification | pre-tag | 0 | 46 | Frozen, **paused 2026-10-08**, not run | `local/research-design-review-2026-10-06/` |
| 2026-10-08 | Qualification standard replaced (disclosed evidence, ETF-based built-ins) | commit 3f8c70f | 0 | 46 | Decision | [spec](superpowers/specs/2026-10-08-strategy-qualification-standard-design.md) |

Forward journals:

| Registered | Journal | Status |
| --- | --- | --- |
| 2026-10-05 | SMA200 trend, original 22-stock recipe | Zero records; first window after the 2026-10-30 close. See [forward journal](FORWARD_SHADOW.md). |
