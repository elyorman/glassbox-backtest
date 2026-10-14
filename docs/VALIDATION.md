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
(below) and [CSCV/PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
address additional selection questions. CSCV/PBO remains a diagnostic to
implement and qualify; this workflow does not relabel its block-bootstrap
output as either one. Future ML comparisons also require leakage-safe fitting,
not just resampling returns from models already trained on the whole history.

## Deflated Sharpe ratio

`quant_core.validation.statistics` implements Bailey and López de Prado
(2014) for the evidence packs ([the evidence standard](STRATEGY_EVIDENCE.md),
Section 4). With SR̂ the per-period Sharpe ratio of T per-period returns
(daily excess returns in a pack), γ̂₃ their skewness, γ̂₄ their raw kurtosis
(3 for normal returns), N trials and V the sample variance (dividing by n − 1)
of the trials' per-period Sharpe ratios:

```text
SR0 = sqrt(V) × ((1 − γ) Φ⁻¹(1 − 1/N) + γ Φ⁻¹(1 − 1/(N·e)))      γ = 0.5772… (Euler–Mascheroni)
DSR = Φ((SR̂ − SR0) × sqrt(T − 1) / sqrt(1 − γ̂₃·SR̂ + (γ̂₄ − 1)/4 · SR̂²))
```

- `return_moments(returns)`: SR̂ as mean over sample standard deviation;
  skewness m₃/m₂^1.5 and kurtosis m₄/m₂² from population central moments.
- `sharpe_variance(sharpes)`: V, the sample variance of per-period Sharpe
  ratios; the evidence standard decides which trials it covers.
- `expected_maximum_sharpe(trials, sharpe_variance)`: SR0 (Eq. 1 with zero
  mean, as the paper uses it for the null of no skill).
- `deflated_sharpe_ratio(sharpe, observations, skewness, kurtosis, trials,
  sharpe_variance)`: Eq. 2, a probability.
- `deflated_sharpe(returns, trials, sharpe_variance)`: both, with every input
  and intermediate value for the pack, including the z statistic inside Φ.

Sharpe ratios and their variance are per period; annualized values give wrong
answers. Inputs are refused when N < 2, V < 0, T < 2, the returns have zero
variance, or the skewness and kurtosis leave a non-positive term under the
square root. Moments are 28-digit decimals; Φ and Φ⁻¹ use the standard
library's `NormalDist` in binary floating point, whose last digits can depend
on the platform's maths library, so SR0 and DSR are rounded to 12 decimal
places. Packs show and compare four. Tests reproduce the paper's example
(SR0 ≈ 0.1132, DSR ≈ 0.9004).

## Evidence metrics

`quant_core.analytics.evidence` computes an evidence pack's numbers
([the evidence standard](STRATEGY_EVIDENCE.md), Section 2) from one run.

- `run_series(result)`: sessions, daily returns r, excess returns x = r − c
  (c is what one unit of idle cash earned over the same interval under the
  run's own rate series, zero without one), equity, and holdings as position
  value over equity. x keeps 20 decimal places, so cash minus cash is exactly
  zero rather than the engine's rounding noise near 1e-28; under the 0% cash
  variant x is r at that precision.
- `results(result)`: calendar CAGR; volatility (√252 × sample deviation of
  r); Sharpe and Sortino over T-bills (the formulas below applied to x);
  maximum drawdown and the longest underwater period (from r, with initial
  capital as the first peak); Calmar; average gross exposure; annual turnover
  (filled notional over equity per 365.2425 days); trades (`round_trips`);
  whole-share shortfalls (selected lines whose budget buys no whole share:
  target zero shares, whether or not shares are held); opening-gap
  rejections (buys rejected for insufficient cash at the open, including a
  buy short because a same-session sale was rejected); interest.
- `periods(series, publication, segments)`: each calendar year, the windows
  2016–2019, 2020–2022 and 2023 to the end, since publication and any
  registered segments (each with the return, maximum drawdown and Sharpe over
  T-bills of its own sessions); the best and worst returns between month-end
  sessions twelve calendar months apart (the series' last month counts as
  unfinished); the five deepest drawdowns with peak, trough and recovery
  sessions, depth, and sessions to trough and to recovery, both counted from
  the peak (a peak of initial capital has no peak session).
- `bootstrap(series, reference, block_lengths, repetitions, seed)`: for each
  block length the stationary bootstrap above, restarted at the seed. Each
  replicate gives the 252-session annualized return, Sharpe over T-bills, the
  resampled path's maximum drawdown and, with a reference on the same
  sessions resampled with the same indices, the Sharpe difference. Intervals
  are the nearest-rank 2.5% and 97.5% values; undefined Sharpe replicates are
  counted, not used. Read the return interval next to the 252-session
  annualized return, not the calendar CAGR, and the drawdown interval next to
  the observed drawdown: resampling breaks dependence longer than the block,
  so long bear markets are under-represented in it.
- `deflated(parent, neighbours, trials, floor)`: the study's own V (sample
  variance of the daily Sharpe ratios of the parent and at least two
  neighbours) and the deflated Sharpe ratio under the larger of V and the
  historical floor (primary) and under the smaller.
- `correlation(a, b)` and `holdings_overlap(a, b)`: Pearson correlation of
  daily excess returns on shared sessions, and the mean over shared month-end
  sessions of the sum of min(weight in a, weight in b).

Under the 0% cash variant c = 0, so the ratios are measured against a zero
reference rate, as the standard's secondary variant requires.

## Registered studies

A registered study runs one built-in plan once on a frozen dataset and writes
its evidence pack ([the evidence standard](STRATEGY_EVIDENCE.md), Sections 2
and 3).

**Registration.** `docs/registrations/<study>.json` holds exactly these
fields; `load_registration` refuses anything else and the registration hash
is the content hash of the file's JSON value, whatever its layout.

- `schema_version` (1), `study` (lower-case words joined by hyphens), `role`
  (one of the standard's five roles, word for word), `registered_at` (ISO
  time with zone) and `tag` (`study/<study>-<YYYY-MM-DD>`, dated the day of
  `registered_at`).
- `code_hash`: `quant_core.provenance.code_hash()` at the tag. `dataset`:
  the frozen dataset's `id` and its distinct `tickers`, which must include
  every ticker of the plans plus SPY and IEF.
- `plan` and `neighbours`: full plan configurations (`plan_to_dict`, with a
  `rule` field), so each configuration's hash follows from the file. At least
  two neighbours of the parent's rule; all built-in plans without a decision
  offset, named in lower-case letters, digits and underscores, with distinct
  names, and differing in more than their names and invested fraction (pure
  exposure scaling is not a trial). A comparison rule (`fixed_weight`,
  `equal_weight`) cannot be the parent.
- `rebalance_shifts`: −2 and 2. `period` (start, end), `publication` (date,
  source), `segments` (distinct names, start, end); dates are YYYY-MM-DD.
- `costs_bps`: 10, 25 and 50; `primary_cost_bps`: 10, where the standard
  computes the study's own V; `initial_cash`. All are decimal strings (JSON
  integers also parse; floats are refused). `primary_reference`:
  `spy_buy_hold`, `sixty_forty` or `equal_weight`.
- `bootstrap`: distinct block lengths, at least 100 repetitions, a seed.
- `trials`: the cumulative count, this study's count (the parent, its
  neighbours and its two shifts), the per-role count (at least this study's
  count, which it includes, and at most the cumulative count) and the
  historical V floor (Section 4 of the standard).
- `sources` (at least one parameter source), `departures` (what and why),
  `related_ledger_rows`, `cross_check` (decision and reason), `disclosures`
  (plain-language text for the limitations page) and `earlier_studies`
  (each earlier built-in's study name and the directory of its primary run,
  written with forward slashes).

**Runs.** `planned_runs` lists every run in a fixed order: the parent at each
cost; at the primary cost the parent with fills at the second open, with idle
cash at 0%, with each rebalance shift and as each neighbour; then each
comparison portfolio at each cost and with 0% cash. The −2 shift copy starts
two sessions before the period, so it keeps its first month. The comparison
portfolios run 95% invested with the plan's costs and idle-cash interest:
SPY set back to 95% at each month end (so its dividends are reinvested, not
left in cash), 60/40 SPY/IEF rebalanced monthly (57% SPY, 38% IEF, 5% cash),
equal weights over the plan's ETFs, and T-bills alone (the `cash`
benchmark, which holds nothing). `simulate_study` refuses a dataset whose ID,
code whose hash differs from the registration, or a dataset without the
registered tickers, then completes every run in memory. It also refuses a
start inside a warmup: at the first decision the parent and every neighbour
must have enough history for the same ETFs, so the study's own V compares one
period. `run_study` does the same and only then saves each run with
`save_run` under `<output>/runs/<key>/`, refusing an existing output
directory. The guard is per directory: the tag and the ledger are what make
a study's one run auditable.

**Pack.** `build_pack` computes every number from the runs: the registration
file itself and each configuration's hash; results by cost; the comparison
portfolios with what each holds; the plan minus each at the primary cost;
the observed values and bootstrap intervals against the primary reference,
naming any observed value outside its interval (resampling under-represents
long falls); the deflated Sharpe ratio (refused, naming the configuration,
when the parent or a neighbour has no Sharpe ratio); the first decision and
the ETFs without enough history then; periods; sensitivity (costs, delay,
0% cash, shifts, neighbours); the cash convention; overlap with earlier
built-ins, with the earlier run's result hash; and reproduction (the command,
the tag, the registration hash, dataset ID, code hash and each run's result
hash). The limitations page is generated, never written after the results:
provider, dataset and each ETF's first session, the snapshot's limitations
and the dataset's quality warnings, the losing calendar years, the five
largest drawdowns, a fixed list of what the plan does not promise and the
registration's disclosures. `write_pack` writes `pack.json` (every number at
full precision) and `PACK.md` (the registration and the main numbers, rounded
for reading; a probability never shows as 1.0000 or 0.0000) and never
replaces either.

**Commands.** From the repository root at the registration's tag:

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli check \
  docs/registrations/<study>.json --dataset local/data/tester-etfs-2026-10-12
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli run \
  docs/registrations/<study>.json --dataset local/data/tester-etfs-2026-10-12 \
  --output local/<study>
```

Both load the registration, the dataset and each earlier study's primary run
(refusing any other run of it), complete every run and build the pack in
memory. `check` then shows and saves nothing, so a registration that cannot
run is found before it is tagged. `run` refuses an existing output directory
before anything runs, and only after the pack is built saves the runs and
writes `pack.json` and `PACK.md`. Both print a JSON summary and exit 0, or
explain the refusal and exit 2; nothing is saved after a refusal. Earlier
studies' run directories are relative to the working directory. If saving
itself fails (a full disk), the results exist: record it in the ledger
before running again.

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
