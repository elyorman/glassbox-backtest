# Rule-based strategies

The strategy engine: rule families, allocation profiles, causal features and
the audit contract shared by every strategy. The four built-in plans of the
tester release (see [the roadmap](ROADMAP.md)) come first; they qualify under
[the evidence standard](STRATEGY_EVIDENCE.md). The research families after
them were built for the 2026-10 studies.

## Built-in plans

`quant_core/strategies/plans.py`; design and verified sources in
[the Plan D design](superpowers/specs/2026-10-12-rule-plans-design.md). Each
plan decides on month-end sessions from total-return signal values (the index
under "Causal feature and calendar contract", sampled on decision sessions),
trades at the next open and invests 95% of equity. A skipped ETF's weight stays
in cash unless its rule says otherwise. Before its first full decision (table
below) a plan trades whichever ETFs already pass the checks, so registered runs
start at the first full decision.

| Plan | ETFs | Rule | Sources | First full decision |
| --- | --- | --- | --- | --- |
| `multi_asset_trend` | SPY, EFA, IEF, VNQ, GSG | Each ETF holds a fifth while its month-end value is strictly above the average of its last 10; otherwise its fifth stays in cash | Faber 2007 (2013 update); Moskowitz, Ooi and Pedersen 2012 | 2007-04-30 |
| `dual_momentum` | SPY, EFA, AGG | If SPY's 12-month return beats T-bills over the same months, hold the stronger of SPY and EFA (SPY on a tie); otherwise AGG | Antonacci 2014, absolute momentum first; Asness, Moskowitz and Pedersen 2013 | 2003-10-31 |
| `us_sector_rotation` | XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY; XLRE and XLC once they have 13 month-ends | The top 3 by return from 12 month-ends ago to 1 month-end ago, a third each; negative returns stay eligible | Asness, Moskowitz and Pedersen 2013; Moskowitz and Grinblatt 1999; Faber 2010 | 1999-12-31 |
| `inverse_volatility` | SPY, IEF, LQD, GSG | Weights proportional to 1/σ of the last 36 monthly returns over T-bills, rescaled over the ETFs with 36 months of history | Asness, Frazzini and Pedersen 2012; Maillard, Roncalli and Teïletche 2010 | 2005-07-29 (GSG from 2009-07-31) |

Departures from the sources, none chosen from results: fills at the next open
rather than the signal close; a 5% cash cushion; EFA for ACWI ex-US (history
from 2001 rather than 2008); VNQ, IEF, LQD and the S&P 500 for the papers'
indexes; monthly sector re-ranking (Faber 2010) rather than Moskowitz and
Grinblatt's six-month hold.

- **Decision sessions.** `decision_sessions(calendar, offset)`: the last
  session of each completed month in the bound calendar, moved by −2 to +2
  sessions for the rebalance-day sensitivity. "10 months" means the current
  decision and the nine before it. `MonthlyPlan.evaluate` works on decision
  sessions only.
- **T-bills.** Dual momentum and inverse volatility bind their own
  `CashRateSeries` and compound it as the engine credits idle cash, so their
  decisions are the same whether the run's idle cash earns the Treasury rate or
  0%. Preflight refuses a run whose series does not cover every lookback.
- **Data checks and audit.** A security is skipped with a reason
  (`outside_security_lifetime`, `insufficient_history`, `missing_signal_bar`,
  `missing_history_session`, `liquidity_filter`). Each decision records one
  `SignalDecision` per ETF: the rule's reason (for example `above_average`,
  `us_stocks_beat_bills`, `bond_fallback`, `top_ranked`,
  `inverse_volatility_weight`), the numbers behind it, the target share of
  equity and the order. Orders come from `rebalance_order`, the whole-share
  arithmetic of the `scheduled_slots` profile below.
- **Comparison portfolios.** `FixedWeightPlan(weights)` holds constant
  weights, and a skipped ETF's weight stays in cash; the 60/40 reference is
  SPY 0.6 and IEF 0.4. `EqualWeightPlan(universe)` splits equally over the ETFs
  that pass the data checks at each decision. Both run on the same monthly
  runner, invest 95% and carry the purpose `benchmark`; SPY buy-and-hold is
  the `buy_hold` rule strategy at 95%.
- **Limitations pages** also cite evidence after publication (no rule depends
  on it): Hurst, Ooi and Pedersen 2017 on trend following since 1880; Daniel
  and Moskowitz 2016 on momentum crashes; Anderson, Bianchi and Goldberg 2012
  on risk parity's dependence on dates and costs; McLean and Pontiff 2016 on
  weaker returns after publication.

```python
from quant_core.strategies.plans import build_plan, builtin_plans

trend, dual, sectors, inverse = builtin_plans()
settings = RunConfig(execution=ExecutionProfile("10"), universe=dual.universe, start=start, cash_rates=bills)
source = build_plan(snapshot, dual, start=settings.start, execution=settings.execution, cash_rates=bills)
result = run_backtest(snapshot, source, settings)
```

## Research basis and exact rules

Jegadeesh/Titman study stock winner/loser momentum; Moskowitz/Ooi/Pedersen study
own-return momentum in futures; George/Hwang study nearness to the 52-week high.
These motivate different hypotheses rather than identify our best strategy.
Our long-only ETF rules, signal-price convention and daily execution are our
adaptations. The moving-average trend rule is not a replication of the futures
study. [Stock momentum](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x),
[time-series momentum](https://fairmodel.econ.yale.edu/ec439/mosk.pdf),
[52-week high](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00695.x).

AQR's implementation study finds especially important trading-cost constraints
for short-term reversal at institutional scale. Its costs are not our fill
estimates. Reversal is a cost-sensitive challenger, not a preferred production
strategy. [Trading costs study](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies).

Here `P[t]` is the causal signal index at the completed session, `L` lookback,
`S` skipped sessions, `K` selected slots and `N` the frozen universe size.

| Family | Schedule, score and condition | Proposed recipes |
| --- | --- | --- |
| `trend` | Month-end; select every instrument with `P[t] > mean(P[t-W+1:t])`. Score is distance above mean. Fixed fraction `0.95/N` per selected instrument. | W=100 or 200: 2 |
| `momentum` | Month-end; rank `P[t-S]/P[t-L] - 1` descending; select top K. Negative winners remain eligible; no hidden absolute-momentum filter. | L=126 or 252, S=21, K=3 or 5: 4 |
| `nearness_high` | Month-end; rank `P[t]/max(P[t-W+1:t])` descending; select top K. This is highest signal **close**, not raw intraday high. | W=252, K=3 or 5: 2 |
| `low_vol` | Month-end; ascending population standard deviation of the last W arithmetic total-return signal returns; select top K. Requires W+1 prices; zero volatility is defined. | Separately registered stock W=126/105, K=5 |
| `reversal` | Week-end; keep instruments strictly above their trailing 200-session signal mean; rank `P[t]/P[t-W] - 1` ascending and select top 3. No additional negative-return requirement. | W=3 or 5: 2 |

Mean/high windows include the current completed session; return lookbacks count
intervals, requiring `L+1` prices. Momentum skip excludes the most recent S
intervals. Ties use stable security ID ascending. Ranked strategies use fixed
fraction `0.95/K`; fewer candidates leave unused slots in cash. Trend weights
are not expanded to compensate for instruments below their mean.

Benchmarks: a single separately specified broad-market security buys once at
the first evaluation close, with full capital budget and with a 95% budget;
the same-universe equal-weight portfolio rebalances monthly with 95% budget;
cash remains cash. They account for their own costs/actions. Benchmark IDs are
independent of candidate universe IDs. Buy-and-hold makes one opening attempt;
an unaffordable gap is audited rather than silently resized/retried. Stage 5
must check benchmark execution before interpreting a comparison.

`initial_recipes(universe)` returns exactly ten frozen configurations.
`benchmark_recipes(universe, benchmark_id)` returns four. The full-investment
and reserve buy-and-hold references satisfy the research plan's comparable
capital convention. The example parameters below are deliberately small
engineering fixtures and are outside that empirical recipe budget.

## Causal feature and calendar contract

Signal prices use raw closes and events effective by the evaluation date:

```text
I[first observed session] = 1
I[t] = I[previous] × (raw_close[t] + dividend_per_post_split_share[t])
                      × split_ratio_between_sessions / raw_close[previous]
```

This models dividend reinvestment at ex-date close **for signals**. The portfolio
still uses raw execution/valuation prices and separately accrues/pays dividends;
signals never credit portfolio cash or supply adjusted fill prices. A dividend
on the first observed bar has no preceding holding interval in the index.
Future splits/dividends do not recalculate previous index values. Signal indices
are locally based at the first bar of the required window; the scores/conditions
are invariant to that base. Do not concatenate locally based index values into
a continuous performance chart.

Absolute-price eligibility uses current raw close. Liquidity uses completed
sessions through signal close: share volume is expressed in current split units;
dollar volume is mean raw close × raw volume. Default history is 20 sessions,
minimum price/dollar volume zero, and new-entry participation at most 1% of
average shares/day. Zero mean volume, insufficient history, a missing expected
session, and inactive/missing signal observations are explicit eligibility
failures, separate from the strategy condition and rank.

Every strategy binds an immutable supplied trading calendar and security
registry. Month/week-end is the session immediately before the next supplied
session crosses that calendar period. The final unknown/truncated period is
not treated as a rebalance. Holidays are represented by the supplied calendar,
not guessed from weekdays or available price rows. Calendar dates are known
schedule metadata; no future OHLC is inspected. The entire bound calendar and
derived rebalance sessions are in source provenance. Freeze this calendar when
testing price-prefix invariance; changing a calendar is an input change.

Warmup may precede the evaluation start. A clipped period does not create an
extra startup/end rebalance. Buy-and-hold/cash act on the explicit first
evaluation close; other families retain the fixed monthly/weekly schedule.
Stage 5 must choose a common start after all required feature/risk warmup,
rather than letting each candidate choose a favorable start.

## Two explicit allocation profiles

`scheduled_slots` implements the signal-isolation baseline. It requires
`RunConfig.risk=None`; it has no protective stops, drawdown halt or investment
risk cap. Basic long-only accounting and order affordability still apply.
For each selected slot, estimate entry cost at the signal close:

```text
target_shares = floor((equity × slot_fraction - flat_entry_fee)
                      / (raw_close × (1 + slippage) × (1 + percentage_fee)))
delta = target_shares - held_shares
buy_request = floor(delta) if delta > 0 else 0
sell_request = -delta if delta < 0 else 0
```

The target capital budget includes estimated entry costs, including when
computing retained positions' targets. Positive deltas are whole-share buys,
capped by past average-volume participation. Negative deltas sell, including
split-created fractions. Selected retained positions can be trimmed/topped up;
fractional buy remainders stay unfilled and receive the auditable
`whole_share_buy_rounding` reason. A buy delta below one share emits no order.
A selected security whose budget buys no share and that is not held is
recorded as `skip` with `below_one_share` (before 0.7.0 the record said `hold`
with a zero target; orders and fills are unchanged).
Unselected holdings exit fully. Sells execute before buys, permitting reuse of
actual opening proceeds. No future proceeds or prices are used to determine
quantities. Opening gaps can still reject buys; targets are not automatically
resized at execution. Participation applies to new entries, not a realistic
exit-capacity model. Weights/reserves are intended capital budgets, not bounds
that remain true after gaps, costs and price changes.

`atr_protected` is an explicitly different research variant. It requires an
enabled [risk policy](RISK_MANAGEMENT.md). It uses the same eligibility/ranking
but emits ATR `EntryIntent` records for selected unheld instruments, holds
selected existing positions without pyramiding/resizing, and exits unselected
holdings. Risk determines quantities or rejects candidates. There is no
automatic promotion of a lower-ranked candidate after risk rejects a winner.
The ATR stop, risk budget, cost model, slot changes and conservative reservation
convention must be registered as an ablation; its returns cannot be attributed
to the original signal alone. The protected profile has null allocation/share
targets in signal audits because risk sizes entries.

## Public API and audit

```python
from quant_core.backtest import RunConfig, run_backtest
from quant_core.execution import ExecutionProfile
from quant_core.strategies import StrategyConfig, build_strategy

recipe = StrategyConfig("momentum252_skip21_top3", "momentum", explicit_security_ids)
settings = RunConfig(execution=ExecutionProfile("10"), universe=recipe.universe,
                     start=evaluation_start)
source = build_strategy(snapshot, recipe, start=settings.start, execution=settings.execution)
result = run_backtest(snapshot, source, settings)
```

`RuleStrategy.orders(context)` emits an `OrderBatch` only on scheduled dates.
`evaluate(context)` projects the same ranking/selection/rebalance on any bound
completed session for later scanner/model integration; it does not execute it.
The source is immutable/reusable and has no learned state, random seed or
parameter search. Preflight checks its run binding, universe, execution costs,
action-completeness declaration and allocation/risk profile pairing.

The source spec records the complete recipe, version, price convention,
calendar, first signal date, rebalance schedule, allocation cost assumptions
and artifact hash. The normal manifest retains dataset, runtime code and
backtest/risk configuration hashes. No current-constituent substitution,
historical sector inference or provider qualification is performed by a strategy.

`signal_decisions` / `signals.csv` record one row per instrument per evaluation:
eligibility, condition qualification, score, rank, selection, targets, existing
shares, requested action/quantity, reasons and feature values. Scores are not
probabilities. `entry_intent` rows leave quantities to risk; match subsequent
risk/order/fill records by signal session and security ID. Orders may reject
after a valid selection; those failures are part of the output.

Saved bundle schema 3 adds signals to the schema-2 risk outputs. Both schema-1
backtester and schema-2 risk runs still verify without rewriting files. Existing
output destinations are refused, and completion-marker hashes cover signals.

## Run the engineering fixture

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.cli import-csv \
  --bars tests/fixtures/strategies/bars.csv \
  --calendar tests/fixtures/strategies/calendar.csv \
  --securities tests/fixtures/strategies/securities.csv \
  --actions tests/fixtures/strategies/actions.csv \
  --source synthetic_strategy_fixture --retrieved-at 2026-10-02T00:00:00+00:00 \
  --universe-policy fixed_engineering_sample \
  --calendar-name synthetic_explicit_sessions --actions-complete \
  --limitation 'Synthetic engineering data; no strategy-performance evidence' \
  --output local/strategy-reference.snapshot.json

PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli run \
  local/strategy-reference.snapshot.json \
  --strategy tests/fixtures/strategies/momentum.json \
  --capital 1000 --slippage-bps 0 --output local/strategy-reference

PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli verify local/strategy-reference
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests
```

The zero-cost synthetic fixture ranks A's January 31 two-interval return
(20%) above B's (-10%), requests four shares against its $120 close and
50% capital slot, then buys at the next $125 open. Final cash is $500 and
four shares mark at $130: equity $1,020. Expected numbers are independently
recorded in `tests/fixtures/strategies/expected.json`. This is a constructed
correctness scenario, not an empirical strategy result or a winning recipe.

Export the proposed research configuration registry without running returns:

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.strategies.cli \
  --universe EXPLICIT-ID-1 EXPLICIT-ID-2 --benchmark BENCHMARK-ID \
  --output local/proposed-recipes
```

This writes ten candidate/four benchmark configuration files and a registry of
configuration hashes. It is a recipe manifest, not the complete append-only
experiment/outcome tracker or selection procedure required in Stage 5. The
registered real campaign still needs qualified inputs, objective, date folds,
cost scenarios, failure reporting and an untouched final period.

## Verification and limits

The strategy tests run on Linux/Python 3.12.7. They cover exact endpoints,
dividend/split units, future-action/index prefix invariance, ties, negative
momentum, condition/eligibility separation, calendar boundaries, warmup,
independent initial/rotating/rebalanced portfolios, cost-aware benchmarks,
liquidity caps, risk rejection and gap stops, reusable sources, numeric contexts,
CLI fixtures, recipe hashes and report integrity/backward compatibility.

`python/research/benchmark_strategies.py` checks the 200-asset, 1,260-session,
252,000-bar constant-price momentum workload. It independently expects three
316-share holdings, $99,905.20 ending equity after slippage, and identical
repeated results. This exercises actual monthly ranking/feature calculations,
not just scheduled orders. Generated measurements live in ignored local storage.

On this Linux x86-64/Python 3.12.7 machine with 12 logical CPUs, the strategy
workload measured 4.25 seconds initially and 4.27 seconds repeated, with 310.1 MiB
peak whole-process memory including both retained results. It recorded 11,400
signal decisions and matched the independent final-equity/ranking calculation.
Timing includes validation, hashes, indexing, features and simulation; export
is excluded. Exact provenance and measurements are in ignored
`local/strategy-benchmark.json`. This is a synthetic scaling check, not a
comparison of profitable strategies or a general performance guarantee.

The [Stage 5 validation workflow](VALIDATION.md) now provides campaign/experiment
tracking and comparison reports. Its empirical campaign still requires
real-provider/calendar/action qualification. Historical stock membership/delistings,
full analytics, Windows verification and commercial execution gates remain
outstanding. No
development, selection-validation or locked-final market-performance period
has been consumed by this implementation.

Exploratory comparisons of these recipes are recorded in
[the research ledger](RESEARCH_LEDGER.md); none qualified a built-in.
