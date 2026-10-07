# Risk and money management

Stage 3 design and implementation contract, 2026-10-02. Scope: daily, USD,
long-only stocks/ETFs, whole-share entries, shared cash, no leverage. This
layer accepts opportunities; it never manufactures alpha or tunes itself on returns.

## Research and choices

| Approach / evidence | Implementation decision |
| --- | --- |
| Fixed allocation is an interpretable control baseline. CME describes sizing from a loss budget and stop distance; its familiar 2% threshold is explicitly arbitrary. [Position sizing](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size), [2% rule](https://www.cmegroup.com/education/courses/trade-and-risk-management/the-2-percent-rule) | Compare fixed allocation with fixed-fractional stop-risk sizing. Percentages are explicit policy preferences, not optimal settings inferred from a paper. |
| Wilder ATR measures range and overnight gaps, rather than direction. [Fidelity formula](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr) | ATR sets an initial stop distance, then the same fractional risk budget sizes shares. Use causal, split-normalized history; insufficient or zero ATR rejects entry. |
| Moreira/Muir find benefits from inverse-variance factor scaling. Cederburg et al. find no systematic direct outperformance across 103 equity strategies and weak implementable out-of-sample combinations. [Moreira/Muir](https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf), [Cederburg et al.](https://www.lehigh.edu/~xuy219/research/COWY.pdf) | Volatility controls must earn their value in chronological comparisons after costs. ATR stop sizing does not replicate monthly inverse-variance factor scaling. Defer portfolio volatility targeting and covariance optimization. |
| Stop-loss value depends on the underlying process and rule. [Kaminski/Lo](https://dspace.mit.edu/entities/publication/bb69ca4b-0cdc-487f-831d-63b2e84fafee) | Stops are a declared execution/risk rule, not a promise to improve returns. Retain a risk-disabled scheduled-exit baseline for later ablations. |
| A stop-market order can execute below its trigger during a gap; a stop-limit may not execute. [FINRA](https://www.finra.org/investors/insights/stop-orders-factors-consider-during-volatile-markets) | Implement long protective stop-market orders with adverse gap fills and costs. Planned loss to stop and drawdown thresholds are not maximum-loss guarantees. |
| Correlated holdings and overlapping fund exposures create concentration. [FINRA](https://www.finra.org/investors/insights/concentration-risk) | Combine position-count, position-value, gross-exposure, cash-reserve, and explicit group limits. Group labels are user-supplied assumptions, not inferred historical sectors or ETF look-through. |
| LEAN separates portfolio construction, risk and execution; its portfolio drawdown model resets after liquidation. [Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview), [Models](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/supported-models) | Keep sizing/risk separate from signals. Our close-observed drawdown halt stays latched for the rest of the run, independent of whether alpha emits targets. |
| Kelly maximizes a growth objective under specified odds/probabilities. [Original paper](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.1538-7305.1956.tb03809.x) | Defer Kelly: our strategy edge/probabilities are not yet validated. This is our engineering choice, not a conclusion that the original paper tested our system. |

## Build and verification plan

1. Immutable policy and entry intents; pure Decimal sizing, Wilder ATR and
   split-normalized trailing volume/dollar-volume calculations.
2. Shared portfolio admission controls, sequential reservations, and a second
   check at next-open prices. Explicit-quantity buys cannot bypass these controls.
3. Protective stop execution and close-observed drawdown reduction/liquidation.
4. Versioned JSON/CSV audits, CLI inputs, hand calculations, adverse-gap,
   causality, corporate-action and backward-compatibility tests.

No strategy/model is selected here. Freeze the risk policy with each experiment
recipe before viewing strategy results. Changing risk settings creates another
trial; report failed settings as well as winners.

## Implemented API

`RunConfig(risk=RiskPolicy(...))` enables controls. `risk=None` retains the
explicit-order baseline. `OrderSource.orders(context)` may return `EntryIntent`
alongside explicit `OrderRequest` sales/buys. Intents require enabled risk;
explicit-quantity buys pass the same admission gates and reject in full if they
fail. There is no alpha score threshold, optimizer, random sizing or vendor call.

```python
from quant_core.backtest import RunConfig, run_backtest
from quant_core.risk import RiskPolicy
from quant_core.sizing import EntryIntent

# Returned by a future strategy at a completed-session close:
EntryIntent("SECURITY-ID", method="fixed_allocation",
            allocation="0.10", stop_price="90")
EntryIntent("SECURITY-ID", method="fixed_fractional",
            risk_fraction="0.005", stop_price="90")
EntryIntent("SECURITY-ID", method="atr", risk_fraction="0.005",
            atr_period=14, atr_multiple="2")

result = run_backtest(snapshot, order_source, RunConfig(risk=RiskPolicy()))
```

Allocation and fractional intents require an explicit protective stop. ATR
intents derive one and reject an explicit stop override. Every risk-enabled buy
requires protection, including fixed-allocation entries, so portfolio heat has
a defined basis. This restriction is explicit; risk-disabled scheduled-exit
experiments remain available. Pyramiding is unsupported for protected holdings.
Partial sales retain the remaining position's stop; full exits/delistings cancel it.

The defaults below are engineering examples. They have not been selected from
historical performance and are not investment recommendations.

| Policy field | Default / meaning |
| --- | --- |
| `max_trade_risk` | 0.005 of pre-entry marked equity, including modeled round-trip costs |
| `max_position_fraction` | 0.20 of post-entry equity at the reference raw price |
| `max_positions` | 10 simultaneous holdings/reserved entries |
| `max_gross_fraction` | 0.90 of post-entry equity; net equals gross in this long-only profile |
| `cash_reserve_fraction` | 0.10 of post-entry equity in spendable cash |
| `max_portfolio_heat` | 0.03 of pre-entry equity in remaining modeled stop-loss budget |
| `volume_lookback` | 20 trailing supplied sessions, through signal close |
| `max_volume_participation` | 0.01 of trailing average shares/day for each new entry |
| `min_average_dollar_volume` | 0; configurable minimum trailing mean of raw close × volume |
| `max_group_fraction` | Disabled; when enabled, all candidate/held IDs need an explicit group |
| `security_groups` | Empty; immutable security-ID/group pairs, one group per instrument |
| `drawdown_reduce`, `drawdown_halt` | 0.10 / 0.20 from the initial-capital-inclusive closing equity peak |
| `reduced_budget_scale` | 0.50 while reduction threshold is breached, before halt |

Group mapping order is canonicalized and recorded in the configuration/hash.
Groups are instrument-level buckets: an ETF receives one explicit bucket, not
an invented set of underlying exposures. Historical sector revisions and fund
look-through require independently qualified point-in-time metadata later.

## Calculations and admission

All financial inputs accept Decimal, decimal strings or integers; floats,
booleans and nonfinite values are rejected. The engine uses its existing fresh
28-digit half-even Decimal context. Whole shares round down.

Let `p` be signal close, `s` stop, `u` adverse slippage fraction, `f` percentage
commission fraction, `F` flat fee, `E` current book equity, and `b` drawdown scale.

```text
entry unit debit = p(1 + u)(1 + f)
stop unit proceeds = s(1 - u)(1 - f)
modeled entry loss(q) = q(entry unit debit - stop unit proceeds) + 2F
allocation shares = floor((E × allocation × b - F) / entry unit debit)
fractional shares = floor((E × risk_fraction × b - 2F)
                          / (entry unit debit - stop unit proceeds))
ATR stop = p - atr_multiple × Wilder_ATR
```

Invalid stop distance, nonpositive/insufficient ATR, insufficient liquidity
history, missing risk observations, below-one-share budgets and invalid IDs
reject entries explicitly. Wilder ATR needs `period + 1` observations: seed
with the mean of the first `period` true ranges, then recursively smooth all
subsequent ranges. True range is the maximum of high-low, |high-previous close|,
and |low-previous close|. Splits effective by the signal date divide earlier
prices and multiply earlier volumes into current share units. Future splits
are unavailable. Ordinary dividend drops remain in raw-price true range.

Admission checks the full proposed quantity. A sized intent may be reduced to
the largest admissible whole-share quantity by monotone integer search. Audit
reasons describe constraints violated by its initial quantity. A zero result
rejects. Explicit quantities never resize automatically.

Checks include modeled loss per trade, marked position value, count, aggregate
gross/group value, cash reserve after modeled entry costs, past average volume,
and portfolio heat. Existing-position heat is
`max(0, marked value - modeled net stop proceeds)` per holding, including exit
costs. Add a new candidate's full modeled entry loss before admission. This is
a loss-to-stop estimate, not VaR, CVaR, a correlation model or a worst-case bound.

Within a signal batch, sells sort first, then entries by priority, ID and
canonical input hash. Approved entries reserve cash and marked positions;
subsequent entries use equity after those modeled entry fees/slippage. Scheduled
sales do not release cash or slots during close planning. This deliberately
means an otherwise cash-starved replacement may need another session; register
that convention with the strategy instead of quietly assuming favorable proceeds.

At execution, recheck the original approved quantity against actual available
cash, current opening marks for all holdings, costs and the split-adjusted stop.
Past liquidity estimates stay frozen; current high, low, close and total daily
volume do not determine the admission quantity. The engine retains its explicit
ex-post zero-volume no-fill check. A gap that breaks a limit rejects the entire
entry, rather than resizing it after seeing the opening outcome. An open at or
below the attached stop rejects entry. Opening admissions use the last observed
close's drawdown state.

Price changes can push existing weights, reserves or heat beyond their entry
limits. Daily portfolio audit rows report that drift, gross/cash/heat fractions
and drawdown state. This version does not automatically rebalance existing
holdings to cure every drift. Those limits are admission controls; the drawdown
halt is the explicit portfolio liquidation rule.

## Stops and drawdown timing

Session order: corporate actions/payment → existing opening-gap stops → pending
market exits/entries → intraday stops → closing valuation/monitoring → signals.

- For a held long opening at/below its trigger, sell at raw open plus adverse
  execution costs. Otherwise, if the daily low touches the trigger, sell at
  trigger plus adverse costs. Stops activate immediately after an opening entry.
- Intraday stop proceeds cannot fund earlier opening buys. An opening gap stop
  can fund a later already-approved opening request. If a gap stop consumes a
  holding, a separate pending sell rejects for insufficient position.
- Splits adjust pending/held quantities, stop prices and frozen share-volume/ATR
  references consistently. Original requested quantity/stop remain auditable.
  Ordinary cash dividends do not change triggers; entitlement accrues before exits.
- Zero-volume stops cannot fill; an unaffordable exit fee also rejects that
  attempt. Protection remains active and is attempted again when triggered on
  a later session. Missing held observations invalidate the run.
- Drawdown reduction scales new allocation/fractional budgets, trade-risk and
  heat admission budgets. It does not shrink existing holdings. It can recover
  when closing drawdown falls below the reduction threshold.
- At the halt threshold, block all entries and submit full next-open exits
  independently of alpha output. Halt remains latched for the rest of the run;
  there is no automatic reset or re-entry. User exits are recorded as superseded
  by the circuit-breaker exits. Failed liquidation is attempted on subsequent
  closes; the orders remain auditable.
- A final-session liquidation request expires, leaving the actual marked
  holding. Never fabricate a closing fill to make the drawdown look smaller.

Thresholds are observed at closes and can be overshot intraday or at the next
open. A stop loss is also not a maximum realized loss. Targets, trailing stops,
stop-limit orders, partial fills, exit-capacity limits and broker-specific
corporate-action stop handling remain separate execution/release work. Entry
ADV participation is a daily capacity proxy, not a guarantee of executable
opening or emergency-exit liquidity.

## Audits and runnable example

Result bundle schema 2 introduced `risk.csv` and `risk_decisions` in `run.json`;
current [Stage 4 schema 3](STRATEGIES.md#public-api-and-audit) also includes signal
decisions and continues to verify schema-1/2 bundles. Each risk
decision records phase, source method, order link where available, target and
approved shares, reference/stop, ATR, liquidity, equity reference, planned loss,
budget scale, drawdown/halt and reasons. Unassessed numbers are null. Rejected
intents create risk decisions without inventing zero-share market orders;
`summary.rejected_order_count` counts actual order records, so inspect rejected
risk decisions separately. Stops also create ordinary order/fill/cash records.
Fills distinguish market-open, stop-gap and intraday-stop execution, preserving
both raw session open and raw execution reference/trigger.

All config, source, dataset and runtime code hashes remain in the manifest.
Schema-1 saved bundles still verify without rewriting their files. Existing
destinations are refused; use fresh ignored paths when repeating these commands.
Schedule schema 1 remains valid for explicit requests. Schema 2 requires `kind`
to be `entry` or `order` on each row; entry rows contain the `EntryIntent` fields.
Risk-policy JSON has `schema_version: 1` and a `policy` object with policy fields.

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.cli import-csv \
  --bars tests/fixtures/risk/bars.csv \
  --calendar tests/fixtures/risk/calendar.csv \
  --securities tests/fixtures/risk/securities.csv \
  --actions tests/fixtures/risk/actions.csv \
  --source synthetic_risk_fixture --retrieved-at 2026-10-02T00:00:00+00:00 \
  --universe-policy fixed_engineering_universe \
  --calendar-name synthetic_explicit_sessions --actions-complete \
  --limitation 'Synthetic engineering data; no strategy-performance evidence' \
  --output local/risk-reference.snapshot.json

PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli run \
  local/risk-reference.snapshot.json --orders tests/fixtures/risk/orders.json \
  --risk-policy tests/fixtures/risk/policy.json --capital 10000 \
  --slippage-bps 0 --output local/risk-reference

PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli verify local/risk-reference
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests
```

Independent expected values are in `tests/fixtures/risk/expected.json`. Starting
cash is $10,000. A 1% loss budget and $100 entry/$90 stop permit 10 shares, with
$100 planned loss at zero costs. The next held-session open gaps to $50, so the
stop realizes a $500 loss and equity ends at $9,500. Closing drawdown is 5%,
crossing the fixture's 4% halt; the next candidate is rejected. These deliberately
synthetic thresholds/prices demonstrate failure handling, not a trading strategy.

## Verification and remaining qualification

The Stage 3 checkpoint passed 143 tests on Linux/Python 3.12.7; Stage 4 extends
the suite, with its current count in [the strategy contract](STRATEGIES.md).
The risk tests cover
hand-calculated sizing/costs, all caps, shared-cash reservations,
group omissions, history/ATR insufficiency, warmup, caller numeric contexts,
deterministic ordering, future-price/split perturbations, opening rechecks,
same-day/gap stops, partial/full exits, splits/reverse splits, dividends,
delistings, no-volume rejection, drawdown recovery/latching/overshoot and report
integrity/backward compatibility. Existing data/backtester financial tests remain
in the suite. Real-provider qualification, Windows checks, broader execution
profiles and independent strategy validation remain release requirements.

The risk-enabled synthetic scaling run can be reproduced with
`PYTHONPATH=python .venv/bin/python python/research/benchmark_backtest.py --risk
--output local/risk-backtest-benchmark.json`. It holds up to ten protected
positions after a 20-session liquidity warmup on the 200-asset, 1,260-session,
252,000-bar dataset. It checks repeated equality and independent final equity;
it does not measure a fully rebalancing strategy or promise emergency liquidity.

On this Linux x86-64/Python 3.12.7 machine with 12 logical CPUs, the risk-enabled
version 0.2.0 run measured 3.06 seconds initially and 3.15 seconds repeated, with
329.6 MiB peak whole-process memory including both retained results. Repeated
results matched and ending equity was the independently expected $99,999.
Validation, hashing, indexing, simulation and result construction are timed;
CSV export is excluded. The exact engine hash, configuration and measurements
are in ignored `local/risk-backtest-benchmark.json`. Single measurements with
different workloads/versions do not establish a comparative speed advantage.
