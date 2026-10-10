# Daily Portfolio Backtester

Implemented: initial reference engine, 2026-10-02. This is the Stage 2 simulation foundation using Stage 1 local snapshots. The synthetic scope is supported; actual-provider qualification, the existing-engine reuse evaluation, and Windows execution checks remain pending. Production engine selection is not finalized by this implementation.

## Public interface

```python
from pathlib import Path
from quant_core.backtest import RunConfig, run_backtest
from quant_core.backtest.sources import load_schedule
from quant_core.data.storage import load_snapshot
from quant_core.execution import ExecutionProfile

snapshot = load_snapshot(Path("local/synthetic.snapshot.json"))
orders = load_schedule(Path("tests/fixtures/backtest/orders.json"))
result = run_backtest(snapshot, orders, RunConfig("1000", ExecutionProfile("0")))
print(result.summary)
print(result.orders)  # Every requested order, including rejections and expirations.
```

`OrderSource.orders(context)` accepts a completed-session context and returns `OrderRequest`/`EntryIntent` records, or an `OrderBatch` containing those requests plus immutable signal decisions. [The risk/sizing layer](RISK_MANAGEMENT.md) translates accepted intents into protected buys; intents require an enabled risk policy. [Stage 4 rule strategies](STRATEGIES.md) provide scheduled rankings and rebalancing. The supplied `OrderSchedule` remains an engineering fixture, not evidence of a profitable strategy. An optional read-only `validate_run(snapshot, normalized_config)` source hook checks bindings before simulation; metadata may not change during preflight or execution.

An order requests a security ID, buy/sell side, quantity, integer execution priority, reason, and optional initial buy-side `stop_price`. Buy requests require whole shares; fractional sales and split-adjusted quantities are supported under the explicitly stated fractional-entitlement model. The engine does not infer allocation or scores from explicit quantities. With risk enabled, all buys require stops and pass the same portfolio gates, including explicit requests.

## Execution contract

All dates below are supplied calendar sessions. The calendar is never inferred from whichever bars happen to exist.

Version 0.4.0 adds the registered Stage 5 delay diagnostic. `RunConfig.execution_delay_sessions`
defaults to 1; setting 2 executes original close signals/quantities at the second
session open. Pending orders retain intervening split adjustments. An unavailable
eligible session expires the request; quantities are not re-created using later
prices. Delay 2 currently requires risk disabled. The CLI exposes
`--execution-delay-sessions 2`. See [the validation workflow](VALIDATION.md).

| Phase | Behavior |
| --- | --- |
| Before open | Apply effective splits to holdings, pending quantities and stops, retaining acquisition basis. |
| Before open | Accrue dividend entitlement from shares owned before opening fills, using post-split share units for same-day events. |
| Before open | Process explicit cash-delisting settlements; reject later trading in the delisted security. |
| Before open | Pay receivables whose payment date has arrived. A non-session payment date credits cash at the next supplied session. |
| Open | Execute held protective stops gapped through at raw open plus adverse costs. |
| Open | Execute eligible close-generated requests: sells first, then buys; within each side use priority, security ID, and canonical request hash. Default eligibility is the next session. |
| Intraday | Execute triggered protective stops, including opening entries, at trigger plus adverse costs. These proceeds cannot fund preceding opening buys. |
| Close | Mark every held position using the current raw close. Missing held marks or unresolved held delistings invalidate the run. |
| Close | Reconcile portfolio equity and cash, then give the order source its completed-session context. |
| Close | If enabled, monitor portfolio/drawdown limits, translate sized entries, reserve shared cash, and generate latched-halt next-open exits. |
| Close | Record newly requested orders for the next run session; expire valid final-session requests when there is no next session inside the period. |

Close-generated entries/exits do not fill at their signal close. Each market request has one execution attempt; a missing opening bar does not postpone it until a more convenient price. Rejections include unknown security, outside universe/lifetime, absent signal or execution bar, zero volume, insufficient cash, insufficient position, unaffordable exit fees, invalid stops, protected-position pyramiding, and enabled risk gates. Rejected orders incur no costs and are never automatically reduced at execution. Protective stops remain active after an unfilled attempt; no-volume or unaffordable-fee attempts are recorded explicitly.

With risk enabled, final-session buys and entry intents undergo the same close
validation and sizing as earlier entries. Valid requests expire with
`no_next_session`, retaining their stop and linked approved/capped risk decision.
Invalid requests retain their actual risk rejection reason.

The portfolio is long-only USD with shared cash, no leverage, and zero cash yield. Sales may fund later buys at the same simulated open. This is an economic capital model; it does not simulate historical brokerage settled-cash rules. Arbitrary sell quantities cannot create short positions.

The default profile uses 10 basis points of adverse slippage per side, zero percentage fees, and zero flat fees. These are configurable research assumptions. Execution price is `reference × (1 ± slippage_bps / 10000)`; reference is raw open for market/gap-stop fills and trigger for intraday stops. Fees are `executed_notional × fee_bps / 10000 + fee_per_order`. Slippage is embedded in execution price and separately reported; it is not debited again. The engine does not clamp modeled costs to bar highs/lows or claim actual auction fills. Positive daily volume does not prove capacity; Stage 3 adds prior-volume entry participation limits, not a modeled auction or emergency-exit capacity guarantee.

Pending quantities multiply by a split's new/old-share ratio and stop prices divide by it, while the original request stays in the audit record. Split-created fractions are retained, with no cash-in-lieu payment, fractional rounding, or broker-specific pending-order rules. Ordinary cash dividends do not adjust stop triggers. Explicit delisting proceeds are corporate-action cash movements and realized P&L, rather than ordinary market fills.

When original exact split counts are supplied, quantity/volume adjustments use
`amount × new_shares / old_shares`, and prices/stops use
`price × old_shares / new_shares`. This avoids first rounding a repeating scalar:
700 shares in a 1-for-7 split become exactly 100. Scalar-only legacy actions
remain approximate; counts are never guessed from a rounded ratio. Truly
repeating resulting entitlements still use the declared Decimal precision.

Final positions remain open and marked. There is no automatic terminal-close sale. Initial protective stop-market execution is implemented; [its gap and phase rules](RISK_MANAGEMENT.md#stops-and-drawdown-timing) are explicit. Targets, trailing stops, stop-limit orders and richer intrabar ambiguity policies remain unsupported. Time-based exits can be expressed as a close-generated sell request.

## Data and causality boundaries

Default execution requires a declaration of complete corporate actions and rejects missing expected bars in selected assets' history through the run end, including potential warmup data. Those checks do not independently qualify a provider, universe, adjustment convention, or exchange calendar.

`allow_missing_unheld_diagnostic` permits absent unheld observations while preserving rejection records. `allow_incomplete_diagnostic` permits research with declared incomplete actions. Both are explicit and recorded as unqualified diagnostics. Missing held valuations are fatal under either mode. All data-health issues and source limitations remain in the manifest.

Run boundaries must be supplied sessions. Historical callbacks may read earlier warmup observations, but the simulated portfolio starts with cash on the requested start session. Scheduled entries outside a clipped run period are unused; an entry outside the dataset calendar is an input error.

The context exposes immutable portfolio values, raw history through `as_of`, and splits/dividends effective by that date. `history(asset, limit)` limits both date and trading universe. The implementation indexes data once and slices history only on request. Private implementation state is not a security sandbox: arbitrary Python can inspect internals or use external future data. Source authors must hash/version their artifacts and prove causal preprocessing, training, and predictions. Rule-strategy known calendar schedules are bound and recorded separately; they do not expose future prices. ML provenance and label-boundary validation remain Stage 6 work.

## Accounting and audit outputs

All money is USD; quantities are shares; returns and drawdowns are fractions. The engine runs in a fresh 28-significant-digit Decimal context with half-even rounding, independently of the caller's context. Financial intermediates are not rounded to cents. API numeric inputs use Decimal, integers, or decimal strings; binary floats are rejected.

Average-cost basis includes acquisition fees. On a partial sale, dispose of the corresponding fraction of basis; on a full sale, remove it completely. Realized sale P&L is net proceeds minus disposed basis. Dividend income accrues at entitlement, rather than again at payment. Each closing state checks:

```text
equity = cash + position market value + unpaid dividend receivables
equity = initial capital + realized P&L + unrealized P&L + accrued dividend income
```

Cash movements reconcile after every cash event. The equity identity allows a tiny explicit tolerance for Decimal rounding in partial basis disposal; that tolerance does not change reported values or trade decisions.

The result contains every order/status, fill, cash movement, corporate-action processing record, daily equity/position state, outstanding receivable, summary, risk/signal decision and provenance manifest. Orders preserve original/adjusted quantities and stops, signal/eligible/processed dates, priorities, reasons, and related fill IDs. Fills include raw open, raw execution reference, execution kind/trigger, modeled price, quantity, costs, realized P&L on sales, and resulting cash/position quantity. Rejected entry intents remain risk decisions rather than invented zero-share orders. Signal decisions record eligibility, features, ranks, selected targets and planned actions independently of subsequent risk/fill outcomes.

The manifest includes the normalized dataset hash, metadata/input hashes, normalized configuration/hash, source version/artifact hash, engine/Python versions and source hash, quality issues, and explicit assumptions. The source hash is the author's declaration of all relevant source/model/configuration artifacts. The engine hash covers runtime package Python sources. Changed data, configuration, or artifacts produce a distinguishable run.

## Hand-calculated reference

The fixture uses zero costs solely to make its accounting easy to verify. Starting cash is USD 1,000. At the January 2 close, request 4 pre-split shares of A and 5 shares of B. A splits 2:1 before January 3 fills, so buy 8 shares at USD 50 and B at USD 20. Request a sale of 2 A shares at that close. January 4 is A's USD 1 ex-date; accrue USD 8, then sell 2 shares at USD 49.

| Session | Cash (USD) | Receivables (USD) | Holdings value (USD) | Equity (USD) |
| --- | ---: | ---: | ---: | ---: |
| 2024-01-02 | 1,000 | 0 | 0 | 1,000 |
| 2024-01-03 | 500 | 0 | 500 | 1,000 |
| 2024-01-04 | 598 | 8 | 394 | 1,000 |

Final realized P&L is USD -2, unrealized P&L USD -6, and dividend income USD 8. A final-session buy request expires. The receivable remains outstanding because payment is after the run. Expected values are versioned independently in `tests/fixtures/backtest/expected.json`.

## Run and inspect locally

First import the synthetic snapshot using [the data-layer commands](DATA_LAYER.md#development-commands), then:

```bash
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests -v

PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli run \
  local/synthetic.snapshot.json \
  --orders tests/fixtures/backtest/orders.json \
  --capital 1000 --slippage-bps 0 \
  --output local/backtest-reference

PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli verify local/backtest-reference
```

The saved schema-3 directory contains `run.json`, `manifest.json`, and CSV ledgers for orders, fills, cash, actions, equity, positions, receivables, risk decisions (`risk.csv`) and signal decisions (`signals.csv`). `COMPLETE.json` is written last and contains each file's hash. Schema-1/2 saved runs still verify unchanged. Existing output directories are refused. A failed export remains incomplete and verification rejects it. Integrity verification detects changed or incomplete files; it does not authenticate a source or independently prove financial correctness. The runner accepts either `--orders` or `--strategy`; see [the strategy example](STRATEGIES.md#run-the-engineering-fixture).

The snapshot argument also accepts a [Parquet bundle](DATA_INTEGRATION.md).
Rule strategies can supply `--membership universe.json`; see [dated membership
and removal timing](UNIVERSES.md#strategy-and-portfolio-integration).
`RunConfig(strict_discontinuities=True)` / `--strict-discontinuities` makes
unresolved suspicious price discontinuities blocking errors. This stricter
policy is recorded in the run configuration; it defaults to false for older
diagnostic semantics.
`--allow-missing-unheld` exempts only missing bars; it does not bypass a separately
requested strict discontinuity check.
Rule strategies and risk-enabled runs also require raw share volume
(`adjustment_policy = raw`); snapshots with split-adjusted volume are refused
with an explanatory error rather than silently mixing share bases.

These are developer entry points. The eventual desktop uses the same API and requires no customer terminal. A benchmark can run independently with a different security universe and order source; automatic benchmark construction/comparison and full analytics are later work.

## Verification and scaling

The automated suite covers hand-calculated costs/basis, shared-capital competition and sequencing, gaps, missing/zero-volume bars, partial exits, calendar boundaries, splits, dividends/receivables/payments, delistings/write-offs, and accounting identities. It also covers future-price perturbation, prefix invariance, future split visibility, immutable public inputs, metadata stability, numerical-context independence, reproducibility, and report integrity. An independent Fraction-based calculation verifies cash and holdings across ten generated order paths.

`python/research/benchmark_backtest.py` measures a synthetic 200-asset, 1,260-session workload with 252,000 bars, ten held assets, constant raw prices, and no corporate actions. Run it with `PYTHONPATH=python .venv/bin/python python/research/benchmark_backtest.py`. It checks identical repeated results and hand-calculated ending equity, then records validation/hash/indexing/simulation time and whole-process peak memory in ignored local storage. This is a scaling baseline, not a comparison against another engine or an execution-realism benchmark. CSV export is excluded from timing. Use a fresh output path when repeating.

The Stage 2 version 0.1.0 baseline on this Linux x86-64 machine with Python 3.12.7 and 12 logical CPUs measured first run 4.19 seconds, repeated run 3.56 seconds, and peak whole-process memory 307.7 MiB. Both retained results were identical and matched the hand-calculated ending equity. The exact configuration, engine hash, and timings are saved in ignored `local/backtest-benchmark-final.json`; these historical numbers describe that synthetic workload/engine on this machine only. [The risk-enabled measurement](RISK_MANAGEMENT.md#verification-and-remaining-qualification) covers the Stage 3 version.

Financial tests and the developer CLI have run on Linux/Python 3.12 here. Cross-platform result checks, real-data qualification, richer execution profiles, a second-engine comparison, and commercial packaging remain release gates. Passing engineering tests is not evidence of profitable strategies.
