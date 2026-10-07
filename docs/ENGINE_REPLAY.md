# Corrected-Engine Stock Replay — 2026-10-05

All 99 original stock trials were rerun using the corrected version-0.5.1
engine and verified against their saved results. **No equity paths, fill ledgers,
metrics, trial statuses or canonical parent decisions changed.** The audit fixes
cover important edge cases, but they did not alter this particular campaign.
This supports PR-02–PR-06, PR-08 and PR-13 engineering/reproducibility evidence.

## Frozen comparison

Before new simulation, the replay registered exactly the same Alpaca snapshot,
22 stocks plus SPY, recipes/neighbors, warmup, four periods, three continuous
cost/delay scenarios, two chronological cost scenarios, cash inputs, objectives
and uncertainty settings. Semantic plan comparison permits only the recorded
runtime/source change and removal of the old finalization-recovery annotation.
No parameters, criteria or data were tuned.

The registration pins all **1,412 original campaign files** and preserves the
current **61-source runtime** separately. All 99 portfolios were freshly
simulated rather than copied. Their configuration, cash/share ledgers, metrics,
statistical reports, trial identities and decisions were verified with the
existing campaign tooling. Original bundles were integrity-checked and all
original file hashes remained unchanged.

Verification covered **132,902 session valuations and 76,727 fills**. Comparison
checks distinguish real numerical changes from equivalent decimal spellings,
retain failures/missing values and report every trial rather than only winners.

## Results

Continuous evaluation is 2017-01-31 through 2026-10-02, after the original
2016 warmup. Figures below are unchanged original/corrected results at 10 bps
slippage per side, not forecasts or newly independent evidence.

| Canonical parent/reference | CAGR | Maximum drawdown | Original and replay decision |
| --- | ---: | ---: | --- |
| Momentum 252/skip21/top5 | 21.97% | 27.59% | Reject under registered objectives |
| Trend SMA200 | 11.06% | 13.19% | Promising defensive exploratory candidate |
| Reversal 5/SMA200/top5 | 6.43% | 31.46% | Reject under registered objectives |
| Low volatility 126/top5 | 8.71% | 17.42% | Reject under registered objectives |
| Reserve SPY buy-and-hold | 13.85% | 31.28% | Reference only |
| Same-panel equal weight | 18.25% | 28.48% | Reference only |

Momentum's higher CAGR still fails its required benchmark-aware Sharpe
advantage. Trend retains its defensive tradeoff under both costs, chronological
windows, the registered neighbor and delayed execution. The other canonical
parents remain rejected; a favorable variant cannot replace a failed parent.

## Interpretation and retained evidence

The user chose [Alpaca-based development and exploration](ALPACA_RESEARCH.md).
The replay uses the unchanged incomplete actions, including 336 originally
unknown payment dates modeled as late receivables. Survivor selection, exposed
history, calendar/identity/terminal-outcome and usage qualification limits remain.
No EODHD dates were spliced in, no paid data was purchased, and no model was
trained. Same-data replay cannot establish independent validation or a fresh
holdout. **Zero strategies are commercially qualified.**

Ignored evidence is in `local/stock-engine-replay-2026-10-05/`:
`REGISTRATION.json`, `CURRENT_PLAN.json`, `source-archive/`, 99 new `campaign/`
bundles, `COMPARISON.json`, all-trial `comparison.csv`, `REPORT.html` and
`COMPLETE.json`. The report links the registration and detailed comparisons.
The completion manifest binds the artifacts and unchanged original files.

The full suite passed **536 tests** before replay. All 99 new bundles passed
the complete campaign verifier; eight focused comparator checks covered cash
changes, missing values/fields, failure labels and decimal-equivalent spellings.
Production source files were not modified. The original 99-trial evidence and
its older runtime remain preserved; this is a separately registered replay.
