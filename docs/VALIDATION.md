# Chronological Strategy Validation

Stage 5 rule-strategy workflow, version 0.4.0, 2026-10-03. It registers a finite
campaign before performance runs, evaluates every declared recipe through the
shared portfolio simulator, and retains unsuccessful and invalid experiments.
Its qualification records are reviewed evidence supplied by the researcher;
the software does not verify provider rights or independent sourcing merely
because a field says `passed`.

The gated campaign workflow has been exercised on synthetic fixtures only.
No empirical strategy has been nominated or passed a gated real-data final
evaluation. A separate private ten-year momentum diagnostic was requested and
run on 2026-10-03, with its plan/trials/limitations retained in ignored storage.
That diagnostic exposes the proposed 2024–2026 holdout; those dates cannot be
claimed as untouched in a future empirical campaign. See the
[research evidence](RESEARCH_PLAN.md#first-real-market-exploratory-run).

## Research basis and implemented choices

The [research plan](RESEARCH_PLAN.md) defines the hypotheses, proposed periods,
recipe budgets and independent-data discipline. The implementation makes these
choices visible rather than optimizing the simulator against the strategy.

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

## Verification and remaining scope

The earlier **276-test** foundation passed on Linux/Python 3.12.7. The saved Stage 5 fixture at
`local/validation-reference-final/campaign` verifies 72 accounting bundles and
151 audit events, with `engineering_only`, no nominee, no external holdout
exposure and `final_consumed=false`. Its campaign hash is
`604aa937acfa7b84ca022378e943ca3da00d55868efd31b02810ca2830cc15d2`.
The earlier schema-1/2/3 backtest, risk and strategy reference bundles also
remain verifiable with their original hashes.

The current suite includes independent financial examples, zero-variance/
bankruptcy cases, contribution reconciliation through splits/dividends/delisting,
paired and fold bootstrap invariants, timestamp label purging, phase gates,
failure retention, benchmark rejection, future-price exclusion, CSV/bundle
tampering, code changes, provider degradation and one-time final consumption.
State-transition tests use explicitly fabricated nominations to exercise final
gates; those mocks are not evidence that the synthetic alpha passes nomination.

The market diagnostic retains 20 bundles, including one invalid benchmark.
Independent reconstruction checks 50,280 daily cash/share/receivable/equity
valuations and 5,656 next/second-open fill prices against the raw snapshot.
An analytics regression test covers zero-dollar outside-universe dividend audit
records; unexpected nonzero outside-universe income remains an error. The first
saved simulation was recovered after that reporting fix, without re-simulation
or parameter tuning; the recovery is separately recorded.

The subsequent private [all-ten-recipe comparison](RESEARCH_PLAN.md#all-predefined-strategy-comparison)
retains 70 trials: 67 completed portfolios and three invalid full-budget SPY
references after opening-gap rejection. All 70 ledger reconstructions passed,
covering 171,388 session valuations and 52,238 fills. Five matching decade
bundles were verified and reused; 65 simulations are new. All 12 report-artifact
hashes were checked. Three comparison tests cover price-independent common
warmup, deterministic descriptive ranking/exclusions, and invested-reference
validity. This is separate exploratory evidence on exposed dates, not a gated
campaign, nominee, or fresh final evaluation.

The private [robustness audit](RESEARCH_PLAN.md#robustness-audit-results--2026-10-03)
adds 30 bounded, preregistered trials for two unchanged parents, six one-factor
neighbors, four allocation/ATR controls and three references at two costs.
Five original portfolios are reused; all 35 independent ledger checks pass,
covering 84,550 session valuations and 15,974 fills, including 30 gap stops and
155 intraday stops. Its 28 tests cover independent split/dividend/partial-sale
attribution, open holdings and underwater episodes, rolling windows, historical
cash timing/staleness, exposure matching, zero-variance regression, omitted or
altered stops/fills, incomplete panels, mutable-plan aliasing and artifact
tampering. Report export verifies bundles, exact registered configurations,
core metrics, immutable records and decisions before producing CSV/PNG/PDF/HTML.
All 66 evidence-file and 22 report-artifact hashes were checked. Both parents
pass the limited positive-CAGR neighbor rule but fail their own stated
objectives; no nominee or fresh final evaluation is created. The cash overlay
and exposure-matched return mix are separately labelled diagnostics, not new
executable strategies or retrospective changes to the decision rules.

Actual Alpaca/provider qualification and the registered ten-recipe empirical
campaign remain required. There is no normalized real-provider snapshot with
qualified actions/calendar/rights in this repository yet. Historical cash-rate
qualification beyond the private Treasury overlay, richer measured execution/
exit capacity, qualified point-in-time stock universes, DSR/PBO,
independent-engine/Windows checks, prospective shadow
recording and ML refitting remain separate work. ML can reuse these contracts
and label-interval checks in Stage 6, but production model selection still
requires empirical evidence under PROJECT.md's ML data workflow; built-in
strategies follow [the evidence standard](STRATEGY_EVIDENCE.md).

## Frozen stock campaign and separate-provider retest

`python/research/stock_campaign.py` extends private exploratory research with
four distinct stock hypotheses, four one-factor neighbors and three references.
It publishes the exact source/data hashes and 99-trial budget before execution,
retains every started/completed/failed attempt, and does not mutate outcomes or
select a different neighbor after failures. Three chronological portfolios reset
cash and holdings; previous prices provide causal feature warmup. These windows
are exposed fixed-rule diagnostics, not a fresh OOS model-training evaluation.

`verify` reconstructs exact source/configuration bindings, historical-reference
Sharpe, annual/core metrics, benchmark validity and independent raw-price
ledgers. Frozen entries must match the registered decision rule. `report`
verifies before creating exclusive CSV/PNG/PDF/HTML exports with artifact hashes.
Attribution, rolling/recovery/concentration and conditional bootstrap results
remain diagnostics, not strategy variants. Upstream unknown dividends, missing
security history and the deliberately surviving panel remain explicit.

```bash
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py run \
  --output local/stock-campaign-2026-10-03
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py verify \
  --output local/stock-campaign-2026-10-03
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py report \
  --output local/stock-campaign-2026-10-03
```

Reruns require new output directories; existing evidence is never overwritten.
Current source changes deliberately invalidate the earlier audit's current-code
reproduction gate; its saved bundles/evidence remain preserved. Do not rewrite
old source registrations to approve new code.

The separate independent-data entrypoint reruns only promising frozen parents
and their references on exactly the registered panel/window/cost/delay settings.
It rejects absent candidates, reused providers, unreviewed capabilities, missing
actions or changed panels/calendars. Qualification is the existing schema-1
`Qualification` contract with scope `independent_retest_fixed_sample`, all eight
capabilities passed, bound snapshot and original snapshot hashes, reviewer/date,
limitations and evidence of feed independence. Provider-specific upstream input
locations still require review; the normalized snapshot hash is verified.

```bash
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py retest \
  --campaign local/stock-campaign-2026-10-03 \
  --snapshot PATH_TO_QUALIFIED_INDEPENDENT_SNAPSHOT \
  --qualification PATH_TO_REVIEWED_QUALIFICATION_JSON \
  --output local/stock-independent-retest
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py verify \
  --output local/stock-independent-retest
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py report \
  --output local/stock-independent-retest
```

Retest verification/reporting dispatches to `research.stock_retest`. Exact
original frozen procedures, qualification bytes, complete-action ledgers,
objective comparisons and daily/total cross-provider differences are checked.
Limits are declared before outcomes: 0.05 total-return difference and 0.005
maximum daily-return difference, measured as fractions. Agreement does not
automatically qualify a built-in strategy or supply fresh temporal evidence.
No independent market dataset, review approval or purchase is fabricated.

The stock extension raises the current suite to **304 passing tests**. The
actual campaign's 99 ledgers pass independent reconstruction. See
[its results, limitations and reported finalization recovery](RESEARCH_PLAN.md#stock-campaign-results--2026-10-03).
The report-repair path preserves 204 original file hashes and exact financial
results; no rules or engine sources can change during reuse. Uncertainty,
attribution, frozen entries and retest requirements are numerically reconciled
to verified evidence. Actual separate-provider retesting remains pending.

The subsequently added SEC feasibility module changes the live research source
set. Exact prior sources are preserved at `local/frozen-stock-source-2026-10-03/`
with all 43 registered hashes; use the [archived verification/retest commands](INDEPENDENT_DATA_RETEST.md#preserve-and-execute-the-original-procedure)
against `local/stock-campaign-2026-10-03-finalized/`. Original plans stay unchanged.
The new [fundamental audit](FUNDAMENTAL_RESEARCH.md) is component feasibility,
not a strategy campaign or qualification. Its 81 proposed trials remain unrun
until accounting, shares, original-filings and coverage gates are satisfied.

The [original-filing reconciliation](FUNDAMENTAL_RECONCILIATION.md) adds 37 tests
for original XML/inline numbers, reviewed formulas, exact-date shares,
contradictory contexts and changed/resealed evidence. The then-current suite totaled
**357 passing tests**. Three review findings now have regression coverage:
aggregate/original disagreements block coverage; failed annual documents cannot
select an older score; component-context conflicts block the affected measure.
Independent review found no remaining critical/important issue in this bounded
research stage. Original component agreement is distinct from accounting
comparability, share/preferred qualification and strategy validation.
The first real audit also exposed an incorrectly hand-shaped split fixture;
the corrected test uses the actual serialized `Split.session` schema. The failed
registration/sources are preserved and the separate v2 audit reuses unchanged
original inputs. No strategy results were produced by the failed attempt.
Its verified source/report is also retained: the final v3 audit reconciles
consistent rounded GAAP and exact DEI share observations using declared
accuracy intervals. It never resolves a true conflict by tag preference;
tests use realistic counts in both input orders and retain basis-unqualified
status. No performance results inform that data correction.

## Research status

Dated SEC evidence is consolidated in [research status](RESEARCH_STATUS.md). The qualification criteria and frozen studies remain unchanged. Nominee-only crosschecks explicitly retain original search bindings and do not claim to repeat the full candidate search. New audit corrections are documented in [audit remediation](AUDIT_REMEDIATION.md).
