# Research ledger

One line per study, past and future. Append only; never edit an outcome.
Counting rule: [evidence standard, Section 4](STRATEGY_EVIDENCE.md#4-trial-count-and-deflated-sharpe-ratio).
Studies before 2026-10-08 predate the git-tag process: their evidence and the
hash seals inside it remain under `local/` on the original machine, and their
docs, scripts and tests are kept at the git tag `archive/research-2026-10`.

Historical V[SR] floor for the deflated Sharpe ratio: **not yet computed**.
It is computed once from the sealed evidence and recorded here before the
first registration under the standard.

Panels (all Alpaca SIP raw daily bars, with SPY as reference):

- **ETF-9:** XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY.
- **Stock-22:** 22 hand-picked surviving large caps (survivor-selected).
- **Stock-47:** 47 of 60 names sampled from current IVV holdings, retained
  after requiring complete 2,703-session coverage and passing action and
  discontinuity checks (survivor-selected).

| Date | Study | Panel | Inspected period | Tag / registration | Trials | Cumulative | Outcome | Evidence |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| 2026-10-03 | ETF market backtest: momentum 252/21 top 3 | ETF-9 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 1 | 1 | Exploratory; no nominee | `local/market-backtest-2026-10-03/` |
| 2026-10-03 | All ten predefined recipes (momentum 252/21 top 3 already counted) | ETF-9 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 9 | 10 | No reliable benchmark superiority | `local/strategy-comparison-2026-10-03/` |
| 2026-10-03 | Robustness audit of two parents: momentum lookback ×2, top-k ×2, ATR risk profile (sizing, stops, admission controls); trend mean window ×2, ATR risk profile. The two 75%-invested variants are pure exposure scaling and are not counted. | ETF-9 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 8 | 18 | Both parents fail predeclared objectives | `local/robustness-audit-2026-10-03/` |
| 2026-10-03 | Stock campaign: 4 parents + 4 neighbours | Stock-22 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 8 | 26 | SMA200 passes defensive screen; others fail | `local/stock-campaign-2026-10-03/` (original attempt), `local/stock-campaign-2026-10-03-finalized/` |
| 2026-10-05 | Corrected-engine replay of the 99 stock portfolios | Stock-22 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 0 | 26 | No ledger, metric or decision changes | `local/stock-engine-replay-2026-10-05/` |
| 2026-10-05 | Universe transfer: same 8 configurations | Stock-47 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 8 | 34 | All four parents fail full rule | `local/universe-transfer-2026-10-05-v2/` |
| 2026-10-05 | 52-week-high proximity: parent + neighbour on each panel | Stock-22, Stock-47 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 4 | 38 | Rejected on both panels | `local/high-anchor-2026-10-05/` |
| 2026-10-05 | Five-family research decision review; volume specification frozen | — | — | pre-tag; seals in `local/` | 0 | 38 | Review; no simulations | `local/research-decision-2026-10-05/` |
| 2026-10-06 | Unusual dollar volume: 2 ranked + 1 control on each panel | Stock-22, Stock-47 | 2016-01-04 – 2026-10-02 | pre-tag; seals in `local/` | 6 | 44 | Rejected on both panels; direction check fails | `local/volume-2026-10-06/` (original attempt), `local/volume-2026-10-06-finalized/` |
| 2026-10-06 | Research design review; market-adjusted momentum specification frozen | — | — | pre-tag; seals in `local/` | 0 | 44 | Review; no simulations | `local/research-design-review-2026-10-06/` |
| 2026-10-08 | Qualification standard replaced (disclosed evidence, ETF-based built-ins); market-adjusted momentum paused, not run | — | — | commit cd92788 | 0 | 44 | Decision | [spec](superpowers/specs/2026-10-08-strategy-qualification-standard-design.md) |
| 2026-10-11 | Repository cleanup: closed-study docs, scripts and tests removed from the working tree | — | — | tag `archive/research-2026-10` | 0 | 44 | Housekeeping; no outcome changed | [roadmap](ROADMAP.md) |

Forward journals:

| Registered | Journal | Status |
| --- | --- | --- |
| 2026-10-05 | SMA200 trend, Stock-22 recipe | Zero records; first window after the 2026-10-30 close. See [forward journal](FORWARD_SHADOW.md). |
