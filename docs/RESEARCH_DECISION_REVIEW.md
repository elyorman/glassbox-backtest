# Stock Research Decision Review — 2026-10-05

> Superseded by the [2026-10-08 strategy qualification standard](STRATEGY_EVIDENCE.md); retained as research history. Outcomes recorded here are unchanged and are counted in [the research ledger](RESEARCH_LEDGER.md).

This review consolidates five stock-family hypotheses on the original 22-stock
and broader 47-stock panels. It supports PR-05, PR-06, PR-08 and PR-13.
It uses existing sealed outcomes and adds **zero portfolio simulations**.

**Decision:** Keep all current rejections. Preserve SMA200's original defensive
finding and its broader fold failure. Specify one new unusual-dollar-volume
hypothesis with a reversed-direction control; do not tune rejected rules or
launch ML to rescue them. The [next experiment specification](NEXT_EXPERIMENT.md)
is frozen before its outcomes, but its implementation/runtime registration and
performance campaign remain future work. Production qualification is still zero.

## Evidence and verification scope

Inputs are the corrected original-engine replay, broader universe transfer and
two-panel high-anchor experiment, each with its prior completion hash manifest.
Their 288 recorded scenario entries include 54 duplicated reference entries.
After checking that duplicate reference financial results are identical, the
consolidation retains **234 unique parent/neighbor/reference scenarios**, with
all costs, delays and folds. This is five parent hypotheses, not 234 independent
ideas. Earlier ETF and robustness searches remain part of the selection history.

The reporting workflow checks all three source completion manifests and their
archives, original 1,412-file stock evidence, snapshots/readiness/cash hashes,
and the forward journal's initial evidence. It recalculates the registered
parent decisions and each unmet criterion, verifies all ten continuous primary
parent bundles, and reconciles their asset P&L to final portfolio wealth.
It does not claim a fresh complete financial resimulation or repeat of every
campaign verifier. Those checks belong to the sealed preceding stages.
The 64-file current runtime is unchanged.

Ignored evidence: `local/research-decision-2026-10-05/REPORT.html`,
`COMPARISON.json`, `parents.csv`, `scenarios.csv`, `unmet_criteria.csv`,
`INPUT_BINDINGS.json`, the frozen next specification and `COMPLETE.json`.

## Registered results

Continuous portfolios span 2017-01-31–2026-10-02. Costs are per side; Sharpe
uses the existing strictly lagged Treasury reference and actual cash earns zero.
Folds must pass at both costs, with at least two of three required. Full rules
also require continuous objective, positive neighbor and delayed execution.

| Parent | Panel | CAGR 10 bps | CAGR 25 bps | Drawdown 10 bps | Sharpe 10 bps | Folds passing | Full registered decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Momentum | Original | 21.97% | 20.95% | 27.59% | 0.890 | 0/3 | Reject |
| Momentum | Broader | 24.15% | 22.87% | 35.22% | 0.814 | 1/3 | Reject |
| SMA200 | Original | 11.06% | 10.66% | 13.19% | 0.890 | 3/3 | Exploratory retest candidate only |
| SMA200 | Broader | 10.33% | 9.97% | 14.96% | 0.790 | 1/3 | Reject |
| Short reversal | Original | 6.43% | −3.15% | 31.46% | 0.296 | 0/3 | Reject |
| Short reversal | Broader | 9.55% | −2.27% | 34.53% | 0.405 | 0/3 | Reject |
| Low volatility | Original | 8.71% | 8.39% | 17.42% | 0.513 | 1/3 | Reject |
| Low volatility | Broader | 9.87% | 9.16% | 37.06% | 0.494 | 0/3 | Reject |
| Nearness to high | Original | 14.01% | 12.25% | 24.34% | 0.719 | 1/3 | Reject |
| Nearness to high | Broader | 9.47% | 6.73% | 28.19% | 0.433 | 0/3 | Reject |

At 10 bps, SPY with reserve has CAGR 13.85%, drawdown 31.28%, Sharpe 0.719
on both panels. Original equal weight has 18.25%, 28.48%, 0.972; broader equal
weight has 17.01%, 33.35%, 0.830. Comparisons use unrounded numbers. In particular,
original high-anchor Sharpe is below SPY despite the same displayed rounding.

## What each failure actually tells us

**Momentum:** Its continuous return-seeking failure is Sharpe below equal weight,
not negative returns or failure to beat SPY's Sharpe. The observed SPY regression
betas are 1.144 and 1.271. Positive descriptive regression intercepts coexist
with this rejection; a single-market fit neither removes all factor exposures
nor establishes statistically significant selection alpha. NVDA provides 29.40%
of original positive asset P&L; AMD provides 27.35% on the broader panel, whose
top three positive contributors total 60.70%. These are concentration facts,
not proof that removing those names would erase performance: a rebalanced
portfolio without them has not been simulated.

**SMA200:** It meets its continuous defensive objective on both panels. Average
gross exposure is 67.05% / 61.35%, and average cash fraction 30.12% / 36.74%.
The remaining difference includes receivables, so cash is not simply one minus
exposure. Defensive behavior includes reduced market exposure. The lagged
exposure-matched diagnostic still shows positive mean daily differences, but
it is a non-executable mix without actual portfolio costs, not a new tradable
benchmark. Its broader failure is two 25-bps fold CAGR floors: 2020–2022 misses
half of equal-weight CAGR by approximately **0.014 percentage points**;
2023–2026 misses half of SPY CAGR by approximately **0.405 percentage points**.
The first miss is small; do not describe it as a collapse or change the rule
after seeing it. The prospective journal remains an operational signal/target
record, not forward-return evidence.

**Short reversal:** Both equity-reference Sharpe comparisons fail at 10 bps;
25-bps CAGR becomes negative on both panels. Its primary total notional-turnover
statistic is **605.41 / 775.42**, versus momentum's **50.77 / 65.15** and SMA's
**21.62 / 21.00** over the same full period. These are the engine's aggregate
turnover ratios, not annualized turnover or portfolio counts. CAGR declines
**9.58 / 11.82 percentage points** across the paired cost scenarios. This is
strong evidence of cost sensitivity, not proof of a positive gross edge:
costs also change quantities, later orders and compounding, and no zero-cost
portfolio is inferred. A daily-bar limit-fill assumption would not solve this
without independently justified execution evidence.

**Low volatility:** Original drawdown meets the defensive limits, but 8.71%
CAGR is below half of equal weight's 18.25% (the floor is 9.12%). On the broader
panel, 37.06% drawdown exceeds **both** defensive limits: approximately 23.46%
from SPY and 25.01% from equal weight. Low realized-volatility selection has not
provided portable portfolio downside protection in this implementation.
Its cost-related CAGR declines are only 0.31 / 0.71 percentage points; costs
are not enough to explain those particular acceptance failures.

**Nearness to high:** Both equity-reference Sharpe comparisons fail on both
panels. Gross exposure remains near 94–95%; its failures cannot be summarized
as excessive idle cash. Cost-related CAGR declines are 1.76 / 2.74 percentage
points. Original descriptive regression alpha is positive and broader is
negative, with betas 0.723 / 0.815; these are sample-dependent fits, not a causal
attribution. Original mean daily excess over SPY changes sign after zeroing the
five best positive excess days. That is a concentration diagnostic, not removal
of trades or an executable portfolio. Its lower selection overlap with momentum
does not rescue poor net performance or prove independent alpha.

## What this review cannot establish

All 2016–2026 data have already been exposed. Current/surviving-stock selection,
complete-history/action exclusions, identities, corporate-action coverage,
unknown dividend pay dates, provider revisions and project-use qualification
remain unresolved. This review cannot quantify the bias or divide the observed
failure into precise percentages caused by data and strategy. Better paid data
can address specific gaps; it cannot guarantee an edge or create a fresh
temporal holdout from already inspected history.

Cash overlays, market regressions, zeroed-day concentration and overlapping
rolling windows are descriptive diagnostics. They are not causal proofs,
independent trials or executable counterfactuals. Positive asset contribution
shares divide by the **sum of positive asset P&Ls**, not total net P&L, and count
unpaid entitlements as part of portfolio wealth. Conditional bootstrap results
retain their original search limitations; we do not combine different runtime
studies into a newly significant result.

Repeated selection on the same history increases false-discovery risk. Retaining
the cumulative search and inspecting a finite, predeclared comparison is
necessary; neither alone proves robustness. [Bailey and coauthors](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## Primary-source shortlist

| Hypothesis | Required observable | Feasibility and concern | Decision |
| --- | --- | --- | --- |
| Unusual-volume/attention | Current dollar volume ranked against its own recent history | Cached raw closes/volumes suffice for a clearly labeled long-only adaptation. Costs and the liquid-stock sample may erase an effect. | Specify one bounded parent/neighbor/directional-control study next. |
| Illiquidity premium | Average absolute daily return divided by daily dollar volume | The basic measure is computable. Original controls include size and share turnover; those inputs and executable impact are not qualified here. Our liquid-stock restriction narrows the relevant variation. | Defer performance testing; keep as a separate liquidity/risk research lead. |
| Calendar-specific return persistence | Prior returns from the same calendar month in earlier years | Computable, but a years-2–5 specification consumes around five years of warmup, shortens evaluation and prevents reuse of the original early folds. It adds another substantial exposure/search issue. | Defer until a separately justified longer-history design. |

The [Wharton volume paper](https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf)
and [author publication list](https://sites.duke.edu/sgervais/research/) support
the volume lead and its execution caveat. The [Amihud NYU working paper](https://archive.nyu.edu/bitstream/2451/27420/2/S-AM-00-10.pdf)
defines ILLIQ from absolute return/dollar volume; it also considers share turnover
and size. [NYU V-Lab](https://vlab.stern.nyu.edu/docs/liquidity/ILLIQ-HIST)
documents a daily-data liquidity measure, not proof of profitable stock ranking.
For seasonality, [Chen and Zimmermann's primary reproduction paper](https://www.federalreserve.gov/econres/feds/files/2021-037pap.pdf),
Table 2, distinguishes Heston–Sadka's years-2–5 and other horizons. The original
seasonality publisher/author links did not yield full text in this review;
the shortlist uses the reproduction evidence rather than claiming a full
original-paper methodology review.

We did not run the three shortlisted hypotheses, scan an anomaly database for
the best observed returns or use paper t-statistics as our acceptance evidence.
The liquidity and seasonality measures being computable does not make them
better choices for this panel. The recommendation is a **feasibility and design
judgment**, not an empirical ranking of their profitability.

## Next action

Implement and preregister the [unusual-dollar-volume specification](NEXT_EXPERIMENT.md)
with causal-feature and portfolio tests. Its future budget is **54 new
simulations plus 54 verified reference scenarios**, one parent hypothesis,
one sensitivity neighbor and one low-volume directional control across both
panels. Keep the existing benchmark-aware objective and add the predeclared
direction check. Never substitute a winning neighbor/control after failure.
Both panels must pass; a pass can freeze an exploratory candidate only.

The development roadmap and 3–4 distinct-qualified-strategy release requirement
remain unchanged. ML selection waits for a properly defined research design;
new models do not fix these rejected rules automatically. Any eventual
production claim still needs qualified independent-data retesting and genuinely
uninspected evidence. This review spends no money and downloads no market data.
