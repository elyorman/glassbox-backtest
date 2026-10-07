# Next Experiment: Unusual Dollar-Volume Ranking

Specification v1, fixed on 2026-10-05 before any outcomes from this rule.
Supports PR-05, PR-06, PR-08 and PR-13. This is the next **exploratory hypothesis**,
not a strategy selection or a claim of profitability. The runtime and campaign
still need implementation and byte-bound registration before execution.

## Decision and research basis

Test whether unusually high trading activity predicts subsequent performance
in our existing liquid-stock panels. This introduces a volume observable absent
from the five tested ranking/condition hypotheses. Volume is already used for
eligibility and execution capacity; using it as a predictive score is new here.
Selection is based on input feasibility and a different proposed mechanism,
not an expectation that this rule will outperform.

[Gervais, Kaniel and Mingelgrin's Wharton working paper](https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf)
motivates an attention/visibility hypothesis. Its daily analysis ranks formation
day dollar volume against 49 preceding days and studies subsequent 20-session
returns. It uses size groups and also examines weekly formations and long-short
portfolios. Its execution analysis finds that bid/ask costs can erase results;
its limit-order results cannot be imported into our next-open simulator.
The later publication is [listed by the author](https://sites.duke.edu/sgervais/research/).

Our monthly top-five, long-only rule is an **adaptation**, not a replication.
It does not use paper size groups, firm-announcement exclusions, short positions,
transaction-level volume or quote-based limit orders. A dollar-volume percentile
does not establish that attention caused the signal. An unusual-volume effect
and a usable net portfolio edge are separate questions.

## Frozen inputs and universe

Use exactly both existing stock panels, with unchanged SPY and Treasury-reference
inputs, calendar, raw bars, action policy, cash convention and exclusions:

| Panel | Stocks | Dataset SHA-256 |
| --- | ---: | --- |
| Original | 22 | `d8f9b4013f4073a47ebf5c80bda9e162bc53405d9a9b44a8e044191b7782cae2` |
| Broader | 47 | `30d63eb7800c8dacad3b440186ec6536e8fa45109717ab0985d6420c3fe458bc` |

Names and file paths are taken from the sealed campaign plans, not reselected.
No replacements, historical-index claim or merging the panels to improve results.
Original 336 and broader 602 unknown dividend payment dates retain the existing
withheld-receivable convention. This limits deployable inference even though
volume scoring itself does not require dividend payment dates. Independent
source/action/identity/delisting/use qualification remains outstanding.

## Exact parent and controls

At the completed calendar month-end session `t`, define each stock's approximate
daily traded dollar value as `DV[s] = raw_close[s] × raw_share_volume[s]`, in USD.
Use raw price and its contemporaneous raw volume together. Do not multiply a
total-return signal index by raw volume or mix adjusted price with raw volume.
Price × volume is a daily-close approximation, not actual transaction value.

For a window `W`, the reference is the preceding `W−1` **calendar sessions**,
excluding `t`. Define:

```text
percentile[t, W] = (count(DV[s] < DV[t]) + 0.5 × count(DV[s] == DV[t])) / (W−1)
                  for s in the preceding W−1 sessions
```

Values range from 0 to 1. Equal historical values receive midpoint mass; an
entirely constant positive-volume series yields 0.5. Missing calendar bars,
nonpositive/invalid volume or insufficient history are explicit ineligibility,
not zeros, skipped sessions or substituted observations. Retain each required
raw bar and completed session in feature provenance. All rows through `t` are
allowed; later bars/actions cannot change an earlier decision.

| Recipe | Role | Window | Ranking |
| --- | --- | ---: | --- |
| `stock_unusual_dollar_volume50_top5` | Parent | 50 sessions | Descending percentile |
| `stock_unusual_dollar_volume55_top5` | One-factor sensitivity neighbor | 55 sessions | Descending percentile |
| `stock_low_dollar_volume50_top5` | Directional falsification control | 50 sessions | Ascending percentile |

Select up to five eligible stocks. Exact cross-stock ties break by ascending
stable security ID. Do not add a price-return, trend, minimum-percentile,
announcement, volatility or market-timing filter. In particular, a top-five
selection is not necessarily five extreme-volume events. Report the fraction
of selected scores below 0.90, cross-stock tie frequency and score dispersion;
none may trigger a new threshold, rule change or rerun.

Preserve the existing scheduled-slot allocation and execution semantics:

- $100,000 initial cash for each independent portfolio; long-only, no leverage.
- 95% target investment split into five 19% slots. Unfilled/ineligible slots
  stay cash. This is an allocation target; market moves and open gaps may change
  actual weights. No new stop or optimized risk overlay.
- Signal raw close at least $5; average raw dollar volume over the last 20
  completed sessions at least $10 million; existing split-aware average-share
  volume entry participation cap of 1%.
- Rebalance monthly, liquidating unselected holdings under existing order logic.
  Fills use the next session's raw aggregated open; changed target quantities,
  affordability, rejections and partial/unfilled orders stay audited.
- Idle cash earns zero. The existing lagged Treasury ACT/365 returns are only
  the performance reference. Economic portfolio dividends follow receivable
  and payment accounting, separately from signal/index adjustments.

The neighbor and reversed-direction control are not independent product
strategies and cannot replace a failed parent.

## Fixed periods, references and finite budget

Keep the same already exposed periods; the shorter feature window does not
move the start earlier or turn inspected dates into new validation:

| Period | Start | End | Scenarios |
| --- | --- | --- | --- |
| Continuous | 2017-01-31 | 2026-10-02 | 10 bps, 25 bps, delayed 10 bps |
| Fold 1 | 2017-01-31 | 2019-12-31 | 10 bps, 25 bps |
| Fold 2 | 2020-01-31 | 2022-12-30 | 10 bps, 25 bps |
| Fold 3 | 2023-01-31 | 2026-10-02 | 10 bps, 25 bps |

Costs are per side, with the unchanged zero additional commission and spread
settings. Standard delay is one session; delayed execution is two sessions.
Folds reset to the same initial cash and allow only causal warmup data.
They are chronological robustness checks, not fitted walk-forward or fresh OOS.

Required references are unchanged SPY with reserve, same-universe monthly equal
weight and zero-yield cash. Each panel has six recipes over nine combinations:
**54 scenario entries each, 108 combined**. This is **54 new simulations** for
the parent/neighbor/directional control and **54 reused reference scenarios**.
Reuse is allowed only after exact data, source, configuration, costs, starting
cash, period, execution/action policy, bundle hashes and origin checks. Any
unresolved mismatch stops the campaign; it does not authorize new references
or a larger trial budget. Every failed/invalid/incomplete attempt stays visible.

This is one proposed economic hypothesis, one neighbor and one falsification
control. Preserve the five earlier stock parents, their neighbors, original
and broader campaigns, ETF work, prior robustness searches and all exposed dates
in the cumulative experiment ledger. The budget is not a statistical correction
for that earlier search.

## Predeclared decisions

Keep the existing **return-seeking** objective: positive CAGR and defined
historical-reference Sharpe strictly above **both** equity references at
**both** 10 and 25 bps. Freezing additionally requires the neighbor positive
at both costs, at least two of three folds passing at both costs and delayed
execution passing the same objective. Both panels must meet the full rule.
No rounding tolerance or benchmark substitution.

Add a hypothesis-direction check before any result: for continuous parent vs
low-volume control, the mean of identically aligned **net daily return
differences must be strictly positive at both costs on both panels**. Undefined
observations or an invalid control make that evidence incomplete. Report the
direction comparison in all folds/delay as well; these reports do not create
additional selection rules. If the control wins, retain the counterexample;
do not invert and promote it after inspection.

A full-rule plus direction pass can freeze only this parent as a promising
exploratory candidate for further research. Any economic failure rejects the
parent under this specification; required missing evidence produces incomplete
status. Neither outcome qualifies a strategy. These are design screens, not
proof of statistical significance or scientifically universal thresholds.

Use the existing paired stationary-bootstrap settings: 500 resamples, seed
1729, expected blocks 20 and 60 sessions, on the continuous primary panel.
Report uncertainty against both equity references and the directional control.
Any centered maximum-mean search diagnostic must disclose all three new
recipes, including the control, and that prior searches are excluded. No combined
search significance, DSR/PBO or effective trial count may be fabricated.

Compare parent monthly selections/scores and daily returns to the original
momentum and high-anchor parents on each panel, using exact matching dates and
security panels, average-tie rank Spearman, set Jaccard and daily-return Pearson.
Use the prior caution thresholds 0.60 / 0.80 / 0.80 respectively. Missing or
constant cases remain undefined. Report overlap even if performance fails.
Neither absence of a warning nor a new observable establishes distinctness for
the minimum-three/target-four release requirement.

## Implementation and registration gate

The proposed implementation adds a causal raw-dollar-volume feature, one
explicit strategy family with ranking direction, and a research-only campaign
adapter. Do not change existing family defaults or saved financial results.
Production strategies remain vendor-independent. Necessary checks include
hand-calculated percentile/ties, exact window boundaries, constant series,
missing calendar bars, nonpositive inputs, raw price/volume split invariance,
future-prefix invariance, deterministic ranking/control direction, and audited
next-open portfolio integration. Existing financial checks still apply.

Before the first portfolio outcome, verify the immutable specification hash,
all input hashes/readiness, protocol, controls and finite budget; archive and
bind the complete implemented runtime; record registration time and exact
recipe/configuration/source hashes. A specification freeze is not a runtime
registration. If implementation cannot honor this contract, preserve it and
issue an explicit amendment **before** outcomes; do not silently modify it.

Run once, retain all outcomes and stop at the registered budget. No threshold,
window, rebalance-frequency, normal-return filter, sizing or stop search follows
failure within this study. New research needs a separate registration and
retained search history.

Independent licensed-data retesting and genuinely uninspected temporal evidence
remain required before production/reference claims. Paid acquisition remains
deferred under the user's Alpaca decision. The SMA200 forward **signal/target**
journal remains unchanged; it is not a prospective portfolio return series.

Ignored frozen specification and review evidence:
`local/research-decision-2026-10-05/NEXT_EXPERIMENT_SPEC.json`,
`INPUT_BINDINGS.json`, `COMPARISON.json`, `REPORT.html` and `COMPLETE.json`.
No new strategy performance has been run during this review.
