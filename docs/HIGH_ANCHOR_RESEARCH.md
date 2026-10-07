# High-anchor stock hypothesis — 2026-10-05

This separately registered study evaluates one additional stock hypothesis on
the frozen 22-stock and 47-stock Alpaca panels. It supports PR-05, PR-06, PR-08
and PR-13. It does not modify production trading/accounting behavior or qualify
a strategy. The existing engine already implements `nearness_high`.

## Research basis and exact adaptation

[George and Hwang (2004)](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf)
motivate ranking by price relative to its prior one-year high through investor
anchoring. Their methodology uses CRSP stocks over 1963–2001, winner/loser
30% portfolios and overlapping six-month holdings, including long-short tests.
Their findings are historical research, not a promise about our sample or costs.

Our **long-only adaptation** selects the top five names by latest signal close
divided by the maximum of the last **252 signal closes**, rebalances monthly,
and executes at the next session's raw aggregated open. Signal closes are the
existing split-aware, ex-date dividend-reinvestment total-return index. They
are not raw prices, intraday highs or a reconstruction of the paper's exact
price measure. Dividends in the portfolio separately follow payment-date and
receivable accounting. This is not a literal paper replication or a generic
"breakout" rule requiring a new high.

The one sensitivity neighbor changes only the window to **231**. Ties use the
existing deterministic security-ID ordering. Both recipes keep $100,000 starting
cash, 95% target investment split over five slots, minimum price $5, 20-session
average dollar volume at least $10 million and 1% average-share-volume entry
participation. No trend filter, shorting, new stop, model or parameter search
is introduced. Unselected holdings exit under the existing rebalance logic.

## Registered scope

Registration precedes new performance and binds a full **64-file source archive**,
both existing dataset/readiness records and all prior sealed evidence. Original
2,703-session calendars and evaluation periods stay fixed: continuous
2017-01-31–2026-10-02 plus the same three independent-cash-reset chronological
folds. Those dates are already exposed. Current/surviving stock panels, missing
payment dates, provider revisions, identities and incomplete actions retain
their original limitations. There is no new market-data collection or independent
holdout in this study.

There are **36 new simulations**, 18 on each sample: parent and neighbor across
nine period/scenario combinations. Costs remain **10/25 bps per side**, plus
the same 10-bps delayed-execution scenario. **54 existing reference scenarios**
are copied after byte-integrity and configuration/data/cash/core-source checks,
with explicit origin recorded. These are SPY with reserve, same-universe equal
weight and zero-yield cash. Each panel has 45 auditable scenario entries; the
combined 90 entries are not 90 independent ideas. Four earlier stock parents
and prior ETF/library work remain part of the search history.

The return-seeking objective is unchanged: positive CAGR and historical-reference
Sharpe above **both equity references at both costs**. Freezing additionally
requires positive neighbor at both costs, at least two of three folds passing
at both costs and delayed execution passing. A cross-sample candidate must pass
both samples. Idle cash earns zero; lagged Treasury returns are a Sharpe reference.

Existing block-bootstrap diagnostics are conditional on this parent/neighbor
panel. They do not correct for the full earlier search, establish DSR or provide
new significance/independent-validation evidence. Every rejection/incomplete
result stays in the record. The neighbor never counts as a separate strategy.

## Overlap with momentum

The continuous primary parent is compared against the unchanged 252/skip21/top5
momentum parent on the corresponding sample. Calendar sessions and security
decision panels must match exactly; no missing dates are dropped.

Report monthly selected-set Jaccard and exact-set frequency, monthly score-rank
Spearman using average ranks for ties, and aligned daily-return Pearson
correlation. Empty selected unions have undefined overlap rather than perfect
similarity; constant/sparse ranks and missing return observations stay undefined.

The preregistered overlap warning triggers at mean Jaccard >=0.60, mean score-rank
Spearman >=0.80 or daily-return correlation >=0.80. These are research caution
thresholds, not statistical proof of independent economic hypotheses. Even a
low overlap value cannot make an unqualified recipe a distinct shipped strategy.

## Reproducible commands

```bash
PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.high_campaign register \
  --output local/high-anchor-2026-10-05
PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.high_campaign run \
  --output local/high-anchor-2026-10-05
PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.high_campaign verify \
  --output local/high-anchor-2026-10-05
```

Registration and run directories refuse replacement. Preserve an interrupted
attempt; restarting after code/method changes requires a new version. The verify
command executes both complete campaign verifiers, checks benchmark origins and
recalculates overlap from verified run ledgers. It publishes verification once;
if that artifact already exists, use the archived sources and
`verify_campaigns(Path(...))` API for a read-only repeat. Do not create or alter
a registration merely to verify existing results. The frozen original SMA200 journal
continues to require its own 63-source runtime for future append/capture.

## Verified outcomes

Registration was recorded at **2026-10-05 13:32:04 UTC**, before the new runs.
All **36 new simulations and 54 reused reference scenarios** completed. Both
complete campaign verifiers passed for all 90 bundles, recomputing metrics,
decisions, uncertainty, diagnostics and independent cash/share ledger audits.
The full unittest suite passed **577 tests**, including 15 new campaign tests.

Continuous results, 2017-01-31–2026-10-02:

| Panel | High CAGR, 10 bps | High CAGR, 25 bps | High drawdown, 10 bps | High Sharpe, 10 bps | Equal-weight CAGR, 10 bps | Equal-weight Sharpe, 10 bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original 22 stocks | 14.01% | 12.25% | 24.34% | 0.719 | 18.25% | 0.972 |
| Broader 47 stocks | 9.47% | 6.73% | 28.19% | 0.433 | 17.01% | 0.830 |

Costs are per side. Sharpe here uses the registered lagged historical Treasury
reference, while actual idle cash earns zero. SPY with reserve returns 13.85%
with Sharpe 0.719 at 10 bps on both panels. The original high recipe's unrounded
Sharpe is below SPY's, despite both rounding to 0.719.

**Both panels reject the parent under the unchanged return-seeking rule.**
The original panel passes one of three chronological folds at both costs;
the broader panel passes none. Both delayed-execution scenarios fail the
objective. The neighbor remains positive at both costs, which does not rescue
the other failures. Zero cross-sample candidates are frozen for retest.

Overlap with momentum spans 117 monthly signal dates and 2,432 aligned daily
return intervals on each panel, with no empty/undefined/missing observations:

| Panel | Mean selected-set Jaccard | Exact selected sets | Mean rank Spearman | Daily return Pearson |
| --- | ---: | ---: | ---: | ---: |
| Original 22 stocks | 0.214 | 0% | 0.399 | 0.714 |
| Broader 47 stocks | 0.129 | 0% | 0.495 | 0.704 |

Neither panel triggers the preregistered overlap warning. Their selections
differ, but returns still share market exposure and these diagnostics do not
establish an independent economic strategy or qualify this rejected recipe.

Stop this bounded experiment and retain the failure; do not tune the high window
to improve the inspected result. A future hypothesis requires a separate
registration. This rejects this implementation/sample/objective, not the entire
academic family. Production qualification remains zero, and independent-data
validation and a fresh final test remain pending.

Ignored evidence is `local/high-anchor-2026-10-05/`: registration, runtime,
both campaigns, `VERIFICATION.json`, `SUMMARY.json`, all 90 entries in
`trials.csv`, monthly `overlap.csv`, readable `REPORT.html` and immutable
`COMPLETE.json`. Original stock campaigns, transfer results and forward
registration remain unchanged.
