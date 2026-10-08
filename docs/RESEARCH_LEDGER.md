# Research ledger

One line per study, past and future. Append only; never edit an outcome.
Counting rule: [evidence standard, Section 4](STRATEGY_EVIDENCE.md#4-trial-count-and-deflated-sharpe-ratio).
Studies before 2026-10-08 predate the git-tag process: their evidence and the
hash seals inside it remain under `local/` on the original machine.

Panels (all Alpaca SIP raw daily bars, with SPY as reference):

- **ETF-9:** XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY.
- **Stock-22:** 22 hand-picked surviving large caps (survivor-selected).
- **Stock-47:** 47 names sampled from current IVV holdings with complete
  2016 history (survivor-selected).

Every study below inspected data from 2016-01-04 through 2026-10-02 on its
panel. That whole window is exposed for those panels.

| Date | Study | Panel | Trials | Cumulative | Outcome | Evidence |
| --- | --- | --- | ---: | ---: | --- | --- |
| 2026-10-03 | ETF market backtest: momentum 252/21 top 3 | ETF-9 | 1 | 1 | Exploratory; no nominee | `local/market-backtest-2026-10-03/` |
| 2026-10-03 | All ten predefined recipes (momentum 252/21 top 3 already counted) | ETF-9 | 9 | 10 | No reliable benchmark superiority | `local/strategy-comparison-2026-10-03/` |
| 2026-10-03 | Robustness audit of two parents: momentum lookback ×2, top-k ×2, ATR risk profile (sizing, stops, admission controls); trend mean window ×2, ATR risk profile. The two 75%-invested variants are pure exposure scaling and are not counted. | ETF-9 | 8 | 18 | Both parents fail predeclared objectives | `local/robustness-audit-2026-10-03/` |
| 2026-10-03 | Stock campaign: 4 parents + 4 neighbours | Stock-22 | 8 | 26 | SMA200 passes defensive screen; others fail | `local/stock-campaign-2026-10-03/` (original attempt), `local/stock-campaign-2026-10-03-finalized/` |
| 2026-10-05 | Corrected-engine replay of the 99 stock portfolios | Stock-22 | 0 | 26 | No ledger, metric or decision changes | `local/stock-engine-replay-2026-10-05/` |
| 2026-10-05 | Universe transfer: same 8 configurations | Stock-47 | 8 | 34 | All four parents fail full rule | `local/universe-transfer-2026-10-05-v2/` |
| 2026-10-05 | 52-week-high proximity: parent + neighbour on each panel | Stock-22, Stock-47 | 4 | 38 | Rejected on both panels | `local/high-anchor-2026-10-05/` |
| 2026-10-05 | Five-family research decision review; volume specification frozen | — | 0 | 38 | Review; no simulations | `local/research-decision-2026-10-05/` |
| 2026-10-06 | Unusual dollar volume: 2 ranked + 1 control on each panel | Stock-22, Stock-47 | 6 | 44 | Rejected on both panels; direction check fails | `local/volume-2026-10-06/` (original attempt), `local/volume-2026-10-06-finalized/` |
| 2026-10-06 | Research design review; market-adjusted momentum specification frozen | — | 0 | 44 | Review; no simulations | `local/research-design-review-2026-10-06/` |
| 2026-10-08 | Qualification standard replaced (disclosed evidence, ETF-based built-ins); market-adjusted momentum paused, not run | — | 0 | 44 | Decision | [spec](superpowers/specs/2026-10-08-strategy-qualification-standard-design.md) |

Forward journals:

| Registered | Journal | Status |
| --- | --- | --- |
| 2026-10-05 | SMA200 trend, Stock-22 recipe | Zero records; first window after the 2026-10-30 close. See [forward journal](FORWARD_SHADOW.md). |
