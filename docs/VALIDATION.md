# Chronological Strategy Validation

Stage 5 rule-strategy workflow, version 0.4.0, 2026-10-03. It registers a finite
campaign before performance runs, evaluates every declared recipe through the
shared portfolio simulator, and retains unsuccessful and invalid experiments.
Its qualification records are reviewed evidence supplied by the researcher;
the software does not verify provider rights or independent sourcing merely
because a field says `passed`.

This campaign workflow is a research tool. Built-in strategies qualify under
[the evidence standard](STRATEGY_EVIDENCE.md), not under the nomination gates
described here; every study, including the 2026-10 campaigns that used this
tool, is listed in [the research ledger](RESEARCH_LEDGER.md).

## Research basis and implemented choices

A campaign declares its hypotheses, periods and recipe budget before any run.
The implementation makes these choices visible rather than optimizing the
simulator against the strategy.

Sharpe's original discussion distinguishes differential-return conventions and
the assumptions behind time aggregation. We report a conventional daily ratio
with a declared zero reference rate; square-root annualization does not remove
serial dependence. [Sharpe](https://web.stanford.edu/~wfsharpe/art/sr/sr.htm).

Politis and Romano's stationary bootstrap resamples random-length date blocks
for weakly dependent stationary observations. Our paired implementation uses
the same indices for candidate and benchmark; the search diagnostic uses one
shared index sample across the whole candidate panel. Stationarity and observed
history remain assumptions; resampling does not create unseen crises.
[Original paper](https://users.ssc.wisc.edu/~behansen/718/Politis%20Romano.pdf).

White addresses data snooping across a collection of alternatives. Our explicit
diagnostic compares the largest mean daily excess return with a stationary
bootstrap distribution after centering every candidate's excess returns to
zero. It is a conservative least-favorable maximum-mean diagnostic, with a
finite-sample correction, rather than a Sharpe test or proof of future profit.
[White](https://onlinelibrary.wiley.com/doi/10.1111/1468-0262.00152).

The [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
and [CSCV/PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) address
additional selection questions. They remain separate research diagnostics to
implement and qualify; this workflow does not relabel its block-bootstrap
output as either one. Future ML comparisons also require leakage-safe fitting,
not just resampling returns from models already trained on the whole history.

## Frozen campaign and qualification contract

`CampaignSpec` records the hypothesis, dataset hash, complete candidate and
benchmark configurations, chronological periods, criteria, capital, cost
ladder, bootstrap block lengths/repetitions/seed, and prior holdout exposure.
The ten proposed recipes remain the initial rule-strategy budget. Register a
different budget explicitly before testing another universe, filter or rule.
The runner currently supports scheduled-slots baselines; risk/stop/ML ablations
require a separately specified protocol rather than an implicit change here.

Equivalent decimal cost spellings share a scenario label locally; the underlying
configuration serialization/hashes remain unchanged. Low-volatility candidates
participate in the declared family tie-break alongside the other supported rules.
A full capital loss remains a saved adverse trial. Trailing undefined returns
give it `undefined_returns` status and make the phase incomplete, preventing
nomination. Later periods beginning with zero capital report null return metrics
and `zero_equity_at_period_start`, rather than invented zero returns or another
100% loss. Other complete candidate comparisons remain visible, but the full
registered search diagnostic is withheld with an explicit limitation whenever a
registered trial is incomplete, invalid or has undefined returns.

All candidates use the same fixed universe. Benchmarks are the full-budget
broad-market buy-and-hold, 5%-reserve broad-market buy-and-hold, same-universe
equal-weight and cash references from [Stage 4](STRATEGIES.md). Benchmark
selection is independent of the trading universe. A rejected benchmark order
or an unfilled buy-and-hold entry makes the campaign incomplete; cash left by a
failed entry is not accepted as an invested-market reference. Do not move the
start date or silently resize the benchmark to make it work after seeing this.

The qualification document binds reviewed evidence to the **exact** snapshot:

| Capability | Required evidence |
| --- | --- |
| Research usage rights | Actual applicable provider terms/entitlements for the intended use, with reviewer context. Payment later is not retrospective permission. |
| Exchange calendar | Reconciliation with a separately sourced exchange calendar, not inference from existing bars. |
| Raw prices/open convention | Feed, adjustment, timestamp and regular-session/aggregated-open conventions. |
| Split/dividend coverage | Reconciled events and adjustment behavior, not an `actions_complete` flag alone. |
| Dividend payment dates | Source/convention for when credited receivables become usable cash. |
| Security identity | Stable instrument IDs, histories and any ticker changes. |
| Universe history or fixed-sample disclosure | Historical membership evidence or an explicit retrospectively chosen surviving-sample limitation. |
| Delisting treatment | Coverage and terminal-settlement convention, or justified applicability for the frozen sample. |

Every capability is `passed`, `unresolved` or `failed`, with nonempty evidence.
An unresolved/failed capability blocks execution. Limitations are mandatory.
Scopes are `engineering_fixture`, `exploratory_fixed_sample`, and
`independent_retest_fixed_sample`. This is not a qualified historical index
universe implementation. An engineering qualification cannot authorize an
empirical campaign, and engineering campaigns cannot nominate a strategy.

An independent qualification must identify the original dataset hash and
provide independence evidence, including underlying-feed relationships and
intended usage rights. A changed retrieval timestamp or different vendor name
alone is not such evidence. No API key or download is needed for fixture work.

## Chronology and state transitions

```text
register → development → selection → nominate/freeze
                                    ↓ eligible nominee only
                              independent crosscheck
                                    ↓ passed only
                               final (consumed once)
```

Registration is saved before qualification checks so failures remain visible.
All boundaries must be supplied sessions; folds and phases must be disjoint and
chronological. All recipes/benchmarks must have common-start feature warmup.
The template maps the proposed 2019/2020/2021 development folds, 2022–2023
selection and 2024-01-01–2026-09-30 final period to actual calendar sessions.
Its prior-holdout-use field is deliberately `unknown` until reviewed. Earlier
data supplies warmup. These rule strategies have no fitted training parameters;
annual folds evaluate fixed rules, not an adaptive winner portfolio.

Development runs a **continuous shared-cash portfolio** across consecutive
folds. Year/fold reports slice its actual returns without resetting holdings.
Selection and final evaluation each start from the registered capital in cash,
with earlier bars available for features but no inherited positions. That reset
is an explicit convention, not a stitched simulated deployment.

For each phase the simulator receives only bars/actions through its end, plus
one later **calendar-only** session so an actual period boundary remains known.
The full input hash is retained, but later prices/actions never reach the
strategy callback or simulation. Registration checks final calendar/warmup
availability without inspecting final returns. This boundary is not an OS
sandbox: a researcher can still inspect their own original data outside it.

A started phase cannot be run again, including after failure or interruption.
Selection requires a complete development phase. Nomination is decided once.
A runtime change after registration blocks new execution under that manifest;
existing saved bundles remain verifiable. Preserve the original research
history when registering a new version and record which dates were exposed.

`FREEZE.json` binds at most one nominee, code, complete campaign/evaluation
rules and both phase reports. Crosscheck repeats that nominee and its
benchmarks on independent data over development/selection dates, before any
final-period results. It checks registered return differences and retained
evidence criteria; a collapse is reported as a failure, not repaired by tuning.
Parameter-family stability was tested in the original complete campaign; the
independent retest does not search that family again.

Final evaluation runs only the frozen nominee and declared references on both
datasets. `final_consumed` is recorded **before** execution; even a crash or
failed result cannot make those dates untouched again. This is not an automatic
shipping decision. Provider comparisons over the same dates are one market
history, not two independent temporal samples. Use the exposure command if
final-period performance is inspected outside the workflow.

## Trials, sensitivity and nomination

Default scenarios are zero-cost gross diagnostic, 5/10/25 bps per traded side,
10-bps execution at the second supplied session open, and 10-bps half entry
participation. The cost rate is modeled as adverse slippage with zero separate
fee; it is a combined exploratory assumption, not a measured fill estimate.
Every candidate and benchmark receives every scenario: **84 runs per phase**
for ten candidates and four benchmarks. The zero-cost portfolio is simulated
separately; gross is not invented by adding costs to net returns.

The delay preserves original signal dates, original quantities and their split
adjustments; no decision is recalculated with later information. Delay two
currently requires risk disabled. Missing execution bars, gaps, unaffordable
orders and end-of-run expirations keep the engine's rejection rules. The
participation test halves the lagged entry-share cap only; exits remain full
fills. This is a declared capacity proxy, not an opening-auction capacity model.

Paired uncertainty uses declared expected block lengths (5/20/60 by default),
500 repetitions and seed 1729. A new seed or block choice is a research choice,
not a way to shop for a favorable interval. The search diagnostic includes all
completed registered candidates; incomplete panels cannot nominate. Confidence
intervals use nearest-rank 2.5%/97.5% percentiles, excluding undefined Sharpe
replicates and reporting their count. Inference is conditional on this history
and this declared search, including dependent/correlated trials.

Nomination defaults are proposed research preferences, not investment advice:

- Positive candidate-minus-equal-weight Sharpe difference in development and
  selection under both primary and stressed costs.
- Positive lower paired 95% Sharpe-difference interval for every block length,
  with at least 95% defined replicates; maximum-mean search p-value at most 5%
  for every block length in both phases.
- Maximum drawdown at most 25% in every nonzero-cost scenario.
- Positive median annual development-fold Sharpe difference and at least 50%
  of registered same-family recipes having positive aggregate development
  Sharpe advantage.
- Positive mean daily excess after replacing the five largest positive excess
  sessions with zero, and positive Sharpe advantage under delay/capacity tests.
  This concentration diagnostic is not a replay with trades removed.

Eligible recipes rank by median development-fold Sharpe advantage. Paired
within-fold resampling checks the difference of those median scores against
the leading recipe. If that advantage is unresolved, prefer lower development
turnover, then the declared simplicity ordering (trend, momentum/high,
reversal), then recipe ID. Selection-period returns never break the tie.
Reports retain these checks and every candidate's decision/reasons. No eligible
candidate means rejection or inconclusive evidence; thresholds are not relaxed.
Known/unknown prior holdout use prevents a fresh-final-evidence nomination.

Independent crosscheck defaults allow at most five percentage points of total
return difference and 0.5 percentage points of maximum daily-return difference
on matching dates. Passing numerical agreement alone is insufficient: the
frozen nominee must retain the other evidence gates. These tolerances are
explicit engineering/research defaults to review **before** empirical runs.

## Metrics and artifacts

Daily returns use the actual portfolio equity including receivables, starting
from initial capital; the first cash-only session contributes its actual zero
return. Total return compounds `product(1+r)-1`. Volatility is sample standard
deviation (`n-1`) times `sqrt(252)`; Sharpe is arithmetic daily mean divided by
sample deviation times `sqrt(252)`, with zero reference rate. These conventional
annualized statistics are not serial-dependence corrections.

Sortino uses `sqrt(252 * mean(min(r,0)^2))` for downside deviation. Full-run Calmar
uses calendar CAGR divided by maximum drawdown. Return-only year/fold summaries
instead label their ratio `calmar_session_annualized`. Calendar CAGR uses
`(final/initial)^(365.2425/inclusive_calendar_days)-1`, with the declared
inclusive start/end day convention; `annualized_return_252` is separately
labeled. A zero denominator/insufficient sample gives `null`, never infinity
or a fabricated zero Sharpe. A terminal -100% return gives CAGR/total return -1.

After a complete loss, later daily returns with zero previous equity remain
`null` in the equity ledger. Full-run summaries retain all supplied sessions,
total return and CAGR of -1, and the continuing drawdown duration; volatility,
Sharpe, Sortino and both Calmar ratios are `null` for that undefined-return
interval. Return-only analytics accept trailing undefined returns only after a
complete loss and reject arbitrary missing returns or a resumed return series.
Paired Sharpe differences, mean daily excess and beta are also `null` when
either validated series contains such undefined returns; dates are never dropped.

Drawdown includes initial capital in the peak; duration counts consecutive
supplied sessions strictly below that peak. Year/fold statistics rebase the
local return interval, while full-run statistics retain the full-run peak.
Beta is sample covariance with the matched benchmark divided by its sample
variance. Paired comparison is a difference of net Sharpes, not an information
ratio. Cash yield and the reference rate both remain 0%.

Turnover sums actual filled notional divided by same-session closing equity.
Average gross exposure/cash fractions use daily closing equity; receivables can
make their sum below one. Each asset's contribution reconciles net purchase/
sale proceeds, dividend entitlements, delisting settlement and ending marked
holdings to total portfolio P&L. Sale-fill win rate/expectancy/profit factor are
labeled **sale-fill** statistics, not round-trip trade counts. Partial exits,
open positions and action settlements preclude pretending these are completed
trade distributions. Full Trade Explorer analytics remain Stage 7 work.

Each trial gets the existing schema-3 JSON/CSV accounting bundle plus a
`trial_started` and completed/failed event. Campaign schema 1 stores:

- `CAMPAIGN.json`: configuration, qualification, code/calendar hashes and budget.
- `events/000001.json`, etc.: immutable sequence with previous-event/content
  hashes, UTC audit timestamps, hypotheses, bindings, seeds, metrics and failures.
- `development.json`/`.csv` and `selection.json`/`.csv`: every attempted
  recipe/scenario, matched returns, year/fold metrics, comparisons and inference.
- `FREEZE.json`: nomination or rejection/inconclusive decision and evidence hashes.
- Optional `crosscheck.json`/`.csv` and `final.json`/`.csv`, anchored in the chain.

CSV undefined metrics are blank. Hashes cover reports, CSVs and each accounting
bundle. They detect accidental changes; they are not signatures or protection
against a researcher rewriting all files. Failed/unfinished trials remain
auditable. Exclusive locking prevents concurrent campaign mutations. Publication
requires same-filesystem hard links, as with snapshots. A killed process can
leave `ACTIVE.lock`: inspect its PID and unfinished event history before removing
an abandoned lock; removing it does not authorize rerunning a consumed phase.

## Runnable synthetic example

Run from the repository with its virtual environment:

```bash
PYTHONPATH=python .venv/bin/python python/research/validation_fixture.py \
  --output local/validation-reference

PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli verify \
  local/validation-reference/campaign
```

The script writes a known synthetic 90-session/three-asset snapshot, two small
fixture recipes, four references and explicit engineering qualifications. It
performs 36 trials per development/selection phase, verifies all **72** bundles,
and reports `engineering_only` with no nominee or final-period consumption.
Use a new directory to repeat engineering checks; these are not empirical trials
and do not reset any real research budget.

## Empirical CLI sequence

After separately caching appropriate raw data, actions and an authoritative
calendar into a normalized snapshot, export the **proposed** specification:

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli template \
  local/sector-etfs.snapshot.json \
  --universe XLB XLE XLF XLI XLK XLP XLU XLV XLY --benchmark SPY \
  --reviewed-on 2026-10-03 --output local/sector-etf-registration
```

Review periods, criteria, rights/capability evidence and prior holdout use in the
two generated files before registering. The generated qualification is entirely
`unresolved`; the command does not approve the data or run returns.

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli register \
  local/sector-etf-registration/specification.json local/sector-etfs.snapshot.json \
  --qualification local/sector-etf-registration/qualification.json \
  --output local/sector-etf-campaign

PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli development \
  local/sector-etf-campaign local/sector-etfs.snapshot.json
PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli selection \
  local/sector-etf-campaign local/sector-etfs.snapshot.json
PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli nominate \
  local/sector-etf-campaign
```

Only an eligible frozen nomination permits the next commands:

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli crosscheck \
  local/sector-etf-campaign local/independent-sector-etfs.snapshot.json \
  --qualification local/independent-qualification.json
PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli final \
  local/sector-etf-campaign local/sector-etfs.snapshot.json \
  local/independent-sector-etfs.snapshot.json
PYTHONPATH=python .venv/bin/python -m quant_core.validation.cli verify \
  local/sector-etf-campaign
```

`record-experiment CAMPAIGN EXPERIMENT.json` retains extra/manual hypotheses,
configuration, dataset hash, seed, status and decision reason. It prevents
automatic nomination under the original budget. `record-holdout-exposure
CAMPAIGN --reason TEXT` records accidental/external performance exposure,
including after freezing, and blocks fresh-final-evidence claims.
