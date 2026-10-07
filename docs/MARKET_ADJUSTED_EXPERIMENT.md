# Market-adjusted momentum experiment

Specification v1, frozen on 2026-10-06 before this experiment's feature scores,
rankings or portfolio outcomes. Supports PR-05, PR-06, PR-08 and PR-13.
The [design review](RESEARCH_DESIGN_REVIEW.md) retains motivation, alternatives,
prior failures and exposed-history limits. Implementation/runtime registration
remain future work. This is an adaptation, not an academic replication.

## Question and fixed inputs

Test whether standardized stock performance unexplained by an estimated market
component improves net portfolios over matched ordinary and standardized
momentum. Prior exposure diagnostics inform the question; they do not prove
market exposure caused failure or that reducing it will help.

Use the exact original 22-stock and broader 47-stock panels from the finalized
volume registration, unchanged names/exclusions/calendar/raw bars/actions/Treasury:

| Panel | Dataset SHA-256 |
| --- | --- |
| Original | `d8f9b4013f4073a47ebf5c80bda9e162bc53405d9a9b44a8e044191b7782cae2` |
| Broader | `30d63eb7800c8dacad3b440186ec6536e8fa45109717ab0985d6420c3fe458bc` |

No replacement, download, merged sample or historical-index claim.
[Blitz, Huij and Martens](https://repub.eur.nl/pub/22252/ResidualMomentum-2011.pdf)
motivate residual ranking. This rule substitutes SPY for their three-factor
model and retains long-only mechanics. Size/value/industry exposures may remain;
residual-ranked long-only holdings are not market neutral. The historical lagged
Treasury accrual proxy differs from the paper's risk-free series.

Signal returns use the existing split-aware ex-date-dividend-reinvested index,
never adjusted execution prices or synthetic available cash. Unknown pay dates
retain withheld receivables (336/602). Source/use/action/identity/historical-
membership/delisting qualification remains outstanding.

## Exact feature and controls

Let `m` be the latest completed month at its last supplied session `E[m]`.
Confirm completion by a calendar session in the next month. October 2 is not
an October month end. `P[i,j]` is the causal signal index at `E[j]`:

```text
r[i,j] = P[i,j] / P[i,j-1] - 1
```

Require every daily calendar bar for stock and SPY from the oldest required
month-end anchor through signal close. Missing sessions/anchors are ineligible;
no interpolation, month dropping or row-count substitution. Later bars/actions
cannot alter an earlier decision.

For monthly `f[j]`, compound existing strictly lagged Treasury ACT/365 daily
accruals over `(E[j-1], E[j]]`. Begin interval calculation at the preceding
month-end anchor so the first interval is included; retain observation dates.
Actual idle portfolio cash earns zero.

At `E[m]`, fit an intercept and slope using completed observations:

```text
y[i,j] = r[i,j] - f[j]       x[j] = r[SPY,j] - f[j]
fit_window(W) = j = m-W+1, ..., m
beta = sum((x-mean(x)) * (y-mean(y))) / sum((x-mean(x))**2)
alpha = mean(y) - beta * mean(x)
e[i,j] = y[i,j] - alpha - beta*x[j]
formation = j = m-11, ..., m-1                 # exactly eleven months
score_residual(W) = mean(e over formation) / population_std(e over formation)
score_raw = P[i,m-1] / P[i,m-12] - 1
score_standardized_total = mean(r over formation) / population_std(r over formation)
```

The latest month's return enters the exposure fit and is excluded from
formation. All observations precede execution. This is deterministic causal
feature estimation, not a fitted forward-return model. Never add fitted alpha
to the residual score, clip beta, fit on future data or reestimate old decisions
with later coefficients. The scaling control uses total returns, not excess
returns; it is not a perfect causal decomposition of OLS.

Use Decimal precision 28. Population formation standard deviation divides
centered squares by eleven. The OLS variance check uses centered market squares
divided by W. Market variance `<= 1e-12`, or residual/total standard deviation
`<= 1e-12`, is undefined. These fixed numerical guards are not tuned thresholds.

Four ranked recipes share one eligibility mask: complete 36-return history,
valid W=36 and W=30 fits/formation residual dispersions, valid formation total
dispersion, and ordinary price/liquidity checks. Retain each exclusion reason.
Controls therefore use the same available stocks. Dependence on both fits is
a disclosed research choice; later simplification requires new evidence.

| Recipe | Role | Score |
| --- | --- | --- |
| `stock_market_adjusted36_top5` | Only selectable parent | `score_residual(36)` |
| `stock_market_adjusted30_top5` | Sensitivity neighbor | `score_residual(30)` |
| `stock_monthly_momentum12_skip1_top5` | Ordinary-momentum control | `score_raw` |
| `stock_monthly_standardized12_skip1_top5` | Scaling control | `score_standardized_total` |

Rank descending, break exact ties by ascending stable security ID, choose up to
five eligible stocks. Negative scores remain allowed. No positive-score gate,
trend/sector filter, blacklist, beta hedge, volatility sizing, stop or new overlay.

## Portfolio, references and budget

Use $100,000 initial cash per independent portfolio; long-only/no leverage;
monthly rebalance; 95% target investment in five 19% slots; cash for empty slots.
Raw close at least $5; last-20-session mean raw dollar volume at least $10 million.
Preserve split-aware 1% average-share-volume entry participation, raw aggregated-
open fills, existing sell/buy/priority ordering, affordability/opening-gap
rejections and auditable partial/unfilled orders. Entry capacity is not proof
of realistic exit capacity or an auction-price qualification.

References: SPY with 5% initial reserve, existing same-universe monthly equal
weight, and cash. Equal weight retains fixed-stock slots and ordinary price/
liquidity eligibility; it does not acquire the fitted-feature mask. No full-
budget SPY or cash-yield overlays. Sharpe retains the strictly lagged historical
Treasury reference, without crediting portfolio cash.

Common first signal: **2019-01-31**, the first completed month with 36 returns
from the January 2016 anchor. The shorter neighbor starts on the same date.
Folds start at their first completed month-end, reset cash independently and may
use earlier history only for feature warmup:

| Period | Start | End | Scenarios |
| --- | --- | --- | --- |
| Continuous | 2019-01-31 | 2026-10-02 | 10 bps next open; 25 bps next open; 10 bps second open |
| 2019–2020 | 2019-01-31 | 2020-12-31 | 10/25 bps next open |
| 2021–2023 | 2021-01-29 | 2023-12-29 | 10/25 bps next open |
| 2024–2026 | 2024-01-31 | 2026-10-02 | 10/25 bps next open |

Costs are basis points per traded side. Windows accommodate warmup; they are
fixed-rule screens on exposed history, not fitted walk-forward or fresh OOS.
Earlier periods/results remain unchanged.

Seven recipes × nine combinations × two panels = **126 new simulations**:
72 ranked portfolios and 54 references. Changed starts/resets prohibit reusing
or splicing old reference curves. Failed attempts consume slots and stay recorded.
Saved-outcome recovery needs disclosed provenance without financial reruns;
no automatic retries/replacements exceed the budget.

## Frozen decision and diagnostics

For each period/scenario, the parent's objective requires positive calendar CAGR
and historical-reference Sharpe strictly greater than **all four** equity
comparisons: SPY reserve, same-universe equal weight, ordinary momentum control,
and scaling control. Use unrounded metrics.

Full rule: continuous objective at both costs; neighbor CAGR positive at both
continuous costs; at least two of three folds meeting the objective at both
costs; continuous second-open delay meeting the objective. Both panels must
pass to freeze only this parent as an exploratory retest candidate. Complete
evidence with any failed component rejects it. Missing/undefined required
metrics, invalid references or missing bundles yield incomplete status, with
observed economic failures still reported. Winning neighbors/controls cannot
replace the parent. No screen qualifies a production strategy.

Report paired stationary-bootstrap mean net daily and historical-reference
Sharpe differences against all four equity comparisons, on exactly aligned
primary continuous daily returns: 500 repetitions, seed 1729, expected blocks
20/60 sessions. Centered maximum-mean diagnostics include all four ranked
recipes and disclose exclusion of earlier searches. No DSR/PBO, effective trial
count, combined significance or fresh-holdout claim. Intervals are reporting,
not extra outcome-dependent gates.

Retain fit alpha/beta, input months, reference observations, residuals and
formation dispersion in decisions. Report common-mask failures; exposure,
turnover, portfolio SPY beta, asset P&L/concentration; annual/fold/regime results;
score/selection/return overlap with matched controls. Use existing caution
thresholds 0.60 Jaccard, 0.80 rank Spearman and 0.80 daily-return correlation.
Undefined cases remain undefined. Diagnostics cannot establish causal mechanism,
factor neutrality or distinctness for the release quota.

## Implementation and stopping gates

Before outcomes: verify byte-frozen method/input hashes; implement and test
month/skip boundaries, action-continuous returns, monthly lagged cash accrual,
hand-calculated OLS/residual/population dispersion, degeneracy, shared eligibility,
future-prefix invariance, ranking and next-open accounting; review; archive/
register the complete implemented runtime, calendars, configurations, references
and 126-slot budget. Method freeze is not runtime registration.

Run once and stop. No alternate estimator/factors/lookback/normalization/top-k/
rebalance/filter/cost/risk/fold/threshold search follows within this study. Any
incompatibility needs a preserved pre-outcome amendment. Outcome-informed
revisions need new studies with these dates still recorded as consumed.

Qualified independent-data/use evidence, genuinely uninspected temporal evidence
and customer delivery remain required for production. Paid acquisition stays
deferred; this specification launches no collection or forecasting-model
training. It researches the momentum family, potentially replacing a candidate;
it does not automatically add a distinct qualified strategy toward the
minimum-three/target-four release requirement.

