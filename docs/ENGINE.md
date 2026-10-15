# Engine reference

The technical reference for `python/quant_core`; where it and the code disagree, the page is the bug.
Money is USD, quantities are shares, returns are fractions. Inputs are `Decimal`, integers or decimal
strings (floats are refused); the engine runs in its own 28-digit, half-even `Decimal` context.

## Data

**Snapshots.** A `Snapshot` holds a supplied session calendar (never inferred from bars), a security
registry (stable IDs, listing and delisting dates), raw OHLCV bars, actions and metadata. Bars need a
known security, valid positive OHLC, nonnegative volume and a session inside the security's lifetime.
Actions are `Split` (exact `new_shares`/`old_shares` counts), `Dividend` (ex-date, amount per
post-split share, pay date) and `CashDelisting`. Saved snapshots are canonical JSON with a
`dataset_hash` over the normalized contents; Parquet bundles keep the same hash.

**Tiingo** (`data/tiingo.py`), the only market-data provider, with the user's own key:

- One request per call, no redirects or retries. The key travels only in the `Authorization` header
  and never appears in URLs, caches, manifests, output or errors.
- A price response is cached once it contains the end date's bar, or ends at least 7 days before the
  latest final day; metadata is always cached. Bodies are kept under their SHA-256.
- Normalization: raw `open/high/low/close` and raw share `volume` (`adjustment_policy = raw`);
  `divCash > 0` becomes a `Dividend` paid on the ex-date (Tiingo gives no pay date; the snapshot says
  so); `splitFactor ≠ 1` becomes a `Split` with exact counts up to 1000 (float noise such as 3.000003
  reads as 3-for-1, disclosed). Actions are cross-checked against `adjClose` with Tiingo's dividend
  formula, ex-date close / (ex-date close + dividend), within 0.001% plus rounding; an unexplained
  adjustment stops the import.
- The calendar is SPY's trading days; a security's listing date is its first bar. A bar counts only
  if retrieved after 23:00 UTC on its date, so a partial session never enters a snapshot.

**Treasury rates** (`data/treasury.py`): the Daily Par Yield Curve "3 Mo" column, one CSV per year
from 1990, as fractions. A completed year (from 8 January of the next year) must cover early January
to late December and is then frozen in the cache. Idle cash and the T-bill plans use the last rate
observed strictly before the previous session; a run is refused if it is more than 10 days old.

**Frozen datasets** (`data/dataset.py`, `quant-data download-tiingo`): Treasury years first (no key
needed), then SPY, then each other ticker up to SPY's last session, so every request ends on a trading
day. Default tickers: every ticker the built-in plans trade. The key comes from `TIINGO_API_KEY`, else
the last `TIINGO_API_KEY=` line of `.env`. At most `--max-requests` (45) are sent per run; cached
responses cost nothing. The directory holds `snapshot.json`, `rates.json` and
`manifest.json` (written last; `dataset_id` is its hash). `load_dataset` checks all three against each
other. Exit codes: 0 saved; 2 refused; 3 incomplete, run again with the printed `--end`.

**Quality checks** (`data/quality.py`). Errors block a dataset or run; warnings are counted and kept.
Plans and risk-enabled runs also refuse snapshots whose volume is not raw shares.

| Code | Severity | Meaning |
| --- | --- | --- |
| `missing_bar` | error | A session inside a security's lifetime has no bar |
| `zero_volume` | warning | A bar with no volume (orders on it are rejected) |
| `price_discontinuity` | warning, error if strict | Open moved ≥ 50% after known splits and dividends |
| `suspected_missing_split` | warning, error if strict | Open within 3% of a common split ratio |
| `nonpositive_action_adjusted_reference` | warning | Dividends exhaust the gap check's reference |
| `missing_delisting_settlement`, `actions_incomplete`, `source_limitation` | warning | Unsettled delisting; limits declared by the source |

## Backtest

`run_backtest(snapshot, source, RunConfig)` simulates a long-only USD portfolio with shared cash and no
leverage. Each session runs these phases in order (`backtest/engine.py`):

| Phase | What happens |
| --- | --- |
| Before open | Interest on the previous close's cash: `cash × rate × calendar days / 365` |
| Before open | Splits adjust holdings, pending quantities and stops; dividends accrue on shares held before the open; cash delistings settle; receivables due today are paid |
| Open | Held stops gapped through fill at the raw open plus adverse costs |
| Open | Requests eligible today fill: sells first, then buys, by priority, security ID and request hash |
| Intraday | Triggered stops fill at the trigger plus adverse costs; their proceeds cannot fund this open's buys |
| Close | Positions marked at the raw close; the accounting identities are checked |
| Close | The order source sees the completed session and submits requests for the next session (the second with `execution_delay_sessions=2`) |

**Fills and rejections.** Each request gets one attempt and is never resized. At submission:
`unknown_security`, `outside_universe`, `outside_security_lifetime`, `missing_signal_bar`. At the open:
`outside_security_lifetime`, `missing_execution_bar`, `zero_volume`, `insufficient_position`,
`pyramiding_unsupported`, `entry_open_below_stop`, `risk:<codes>`, `insufficient_cash`,
`insufficient_cash_for_fees`. A request with no next session expires as `no_next_session`. Rejected
orders cost nothing. Sales fund later buys at the same open (an economic capital model; brokerage
settlement is not simulated).

**Costs** (`execution.ExecutionProfile`): price = raw open (or stop trigger) × (1 ± slippage
bps/10000); fees = notional × `fee_bps`/10000 + `fee_per_order`. Defaults: 10 bps per side, no fees.
Slippage sits in the price and is reported separately, never debited twice.

**Accounting.** Average-cost basis includes fees; realized P&L is net proceeds minus disposed basis;
dividends are income at entitlement, cash at payment. Every close checks, within max(1e-18,
1e-24 × equity):

```text
equity = cash + position market value + unpaid dividend receivables
equity = initial cash + realized P&L + unrealized P&L + dividend income + interest income
```

**Assumptions.** Positions are marked at raw closes; a missing held mark or an unsettled held
delisting stops the run. Split fractions are kept, with no cash in lieu; final positions stay open.
Interest is off unless `RunConfig.cash_rates` is set; with it on, `summarize_run` gives no Sharpe or
Sortino (the evidence metrics give them over T-bills). Every run writes its assumptions to the manifest.

**Outputs.** A result holds every order, fill, cash movement, action record, daily state, receivable,
risk and signal decision, and the manifest. `save_run` writes `run.json`, `manifest.json`, CSV ledgers
and, last, `COMPLETE.json` with every file's hash; `verify_run` rejects a changed or incomplete bundle.
`analytics.trades.round_trips` rebuilds entry-to-exit trades that sum, with interest, to the gain.

## Plans

`strategies/plans.py`. Each plan decides on month-end sessions (the last session of each completed
month; `decision_offset` moves it −2 to +2 sessions), trades at the next open and invests 95% of
equity. Signals use a total-return index built from raw closes and the actions known by that day:
`I[t] = I[t−1] × (close[t] + dividend[t]) × split ratio / close[t−1]`. Orders come from
`rebalance_order`: target shares = floor((equity × weight × 0.95 − flat fee) / (close × (1 + slippage)
× (1 + fee))), buys capped at 1% of the 20-session average volume, whole shares only. An ETF is skipped
with a reason (`outside_security_lifetime`, `insufficient_history`, `missing_signal_bar`,
`missing_history_session`, `liquidity_filter`); its weight stays in cash unless its rule says otherwise.
Every decision records one `SignalDecision` per ETF with the rule's reason and numbers.

| Plan | ETFs | Rule | Sources | First full decision |
| --- | --- | --- | --- | --- |
| `multi_asset_trend` | SPY, EFA, IEF, VNQ, GSG | Each ETF holds a fifth while its month-end value is strictly above the average of its last 10, else that fifth is cash | Faber 2007 (2013 update); Moskowitz, Ooi and Pedersen 2012 | 2007-04-30 |
| `dual_momentum` | SPY, EFA, AGG | If SPY's 12-month return beats T-bills, hold the stronger of SPY and EFA (SPY on a tie); otherwise AGG | Antonacci 2014; Asness, Moskowitz and Pedersen 2013 | 2003-10-31 |
| `us_sector_rotation` | XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY; XLRE and XLC once they have 13 month-ends | Top 3 by return from 12 month-ends ago to 1 month-end ago, a third each | Asness, Moskowitz and Pedersen 2013; Moskowitz and Grinblatt 1999; Faber 2010 | 1999-12-31 |
| `inverse_volatility` | SPY, IEF, LQD, GSG | Weights ∝ 1/σ of the last 36 monthly returns over T-bills, over the ETFs with 36 months of history | Asness, Frazzini and Pedersen 2012; Maillard, Roncalli and Teïletche 2010 | 2005-07-29 (GSG from 2009-07-31) |

Departures from the sources, none chosen from results: fills at the next open, not the signal close;
the 5% cash cushion; EFA for ACWI ex-US; VNQ, IEF, LQD and the S&P 500 for the papers' indexes;
monthly sector re-ranking (Faber 2010), not a six-month hold. The T-bill plans bind their own rate
series, so idle-cash interest never changes a decision. Comparison portfolios: `FixedWeightPlan` (60/40
SPY/IEF; SPY alone, reset monthly so dividends are reinvested), `EqualWeightPlan`, the `cash` strategy.

## Risk and money management

`RunConfig(risk=RiskPolicy(...))` puts every buy through admission checks (defaults are examples):

| Field | Default | Field | Default |
| --- | --- | --- | --- |
| `max_trade_risk` | 0.005 of equity | `max_positions` | 10 |
| `max_position_fraction` | 0.20 | `max_portfolio_heat` | 0.03 |
| `max_gross_fraction` | 0.90 | `cash_reserve_fraction` | 0.10 |
| `max_volume_participation` | 0.01 of 20-session volume | `min_average_dollar_volume` | 0 |
| `drawdown_reduce` / `drawdown_halt` | 0.10 / 0.20 | `reduced_budget_scale` | 0.50 |
| `max_group_fraction` | off | `security_groups` | none |

- **Sizing** (`EntryIntent`): `fixed_allocation`, `fixed_fractional` (shares = risk budget / loss per
  share to the stop, after costs) and `atr` (stop = close − multiple × Wilder ATR). Whole shares round
  down; a sized entry may shrink to the largest admissible quantity, an explicit one never does.
- **Stops:** protective stop-market orders; a gap below the stop fills at the open. Every risk-enabled
  buy needs a stop; adding to a protected holding is refused.
- **Drawdown:** from the closing-equity peak including initial cash; at `drawdown_reduce` new budgets
  scale down, at `drawdown_halt` all positions exit at the next open and the halt stays latched.
- **Built-in plans currently require `risk=None`**: `MonthlyPlan.validate_run` refuses a risk policy.
  Their money management today is the 95% invested fraction, whole shares and the 1% volume cap; the
  product's position cap, drawdown brake, per-holding stop and minimum trade are not yet wired to them.

## Evidence

**A qualified built-in** has (1) an economic rationale with at least two published sources; (2) rules
fixed in a registration before its run, each parameter citing its source, departures explained (never
by results already seen) and related ledger rows cited; (3) hand-checked tests, a no-look-ahead test
and a byte-for-byte reproducible run; (4) one complete evidence pack, with no tuning after inspection;
(5) a distinct role (`registration.ROLES`; the model-ranked role is not in V1), with correlation and
holdings overlap against every earlier built-in; (6) a plain-language limitations page. No return,
Sharpe or benchmark-beating threshold applies.

### Evidence metrics

`analytics/evidence.py`. Daily return r is the change in equity; excess return x = r − c, where c is
what one unit of idle cash earned over the same interval under the run's rate series (0 without one),
kept to 20 decimal places. Sharpe = mean(x) / sample sd(x) × √252; Sortino = 252 × mean(x) /
√(252 × mean(min(x, 0)²)); volatility = sample sd(r) × √252; CAGR = (final / initial)^(365.2425 /
inclusive calendar days) − 1; maximum drawdown and the longest underwater spell come from r with
initial cash as the first peak; Calmar = CAGR / maximum drawdown; annual turnover = filled notional over
same-day equity per 365.2425 days. Whole-share shortfalls are selected lines whose budget buys no
share; opening-gap rejections are buys refused for insufficient cash at the open. Periods: calendar
years, 2016–2019, 2020–2022, 2023 to the end, since publication, registered segments, best and worst
12 months between month ends, the five deepest drawdowns. The stationary bootstrap restarts at the
seed for each block length and gives nearest-rank 2.5–97.5% intervals for the 252-session return,
Sharpe, maximum drawdown and the Sharpe difference to the primary reference; resampling
under-represents long falls. Correlation is Pearson on daily excess returns; holdings overlap is the
mean over month ends of Σ min(weight in a, weight in b). Under 0% cash, c = 0.

### Deflated Sharpe ratio

`validation/statistics.py`, Bailey and López de Prado (2014), on per-session (never annualized) values:

```text
SR0 = sqrt(V) × ((1 − γ) Φ⁻¹(1 − 1/N) + γ Φ⁻¹(1 − 1/(N·e)))        γ = 0.5772… (Euler–Mascheroni)
DSR = Φ((SR − SR0) × sqrt(T − 1) / sqrt(1 − skew·SR + (kurt − 1)/4 · SR²))
```

SR is mean over sample sd of T daily excess returns; skewness and raw kurtosis (3 for normal) come
from population moments. N is the ledger's cumulative trial count including this study. V is the
larger of the study's own sample variance of daily Sharpe ratios (the parent and at least two
neighbours at 10 bps, shift copies excluded) and the historical floor (one zero-reference 10 bps Sharpe
per counted ledger trial, ÷ √252, computed once and recorded in the ledger); the pack also gives DSR
under the smaller. SR0 and DSR are rounded to 12 decimals because Φ uses binary floats.

### Trial counts

Count one per (configuration, panel) declared in a registration or run, whether or not its outcome
was seen; a panel is an instrument set with a provider dataset. Configurations differing in signal,
universe, rebalance schedule (including ±2-session shifts), exits, stops, risk overlays or sizing
method count, as do neighbours, controls and reversed variants. Cost levels, execution delay,
evaluation period, cash-yield convention, pure exposure scaling, references and exact replays do not.
The same configuration on another panel counts again, except a cross-check declared in advance. When
in doubt, record the larger defensible number and say why in the ledger.

### Registered studies

`validation/registration.py` defines the registration file (`docs/registrations/<study>.json`): its
fields and rules are in that module. Its commit gets the annotated tag `study/<study>-<YYYY-MM-DD>`,
never moved, and the study a ledger row. `planned_runs`
declares, in order: the parent at 10, 25 and 50 bps; at 10 bps the parent with fills at the second
open, with idle cash at 0%, with decisions −2 and +2 sessions from month end (the −2 copy starts two
sessions early) and as each neighbour; then SPY, 60/40, equal weight and T-bills at each cost and with
0% cash. `simulate_study` refuses another dataset or code hash, missing tickers, a start that is not
the parent's first decision, and a start inside any configuration's warmup, then completes every run
in memory. `build_pack` adds the registration, results, comparisons, bootstrap intervals, DSR,
periods, sensitivity, cash convention, overlap with earlier built-ins, the generated limitations page
and the reproduction hashes; `pack_files` renders `pack.json` and `PACK.md` before anything is saved.

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli check \
  docs/registrations/<study>.json --dataset local/data/<dataset>
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli run \
  docs/registrations/<study>.json --dataset local/data/<dataset> --output local/<study>
```

`check` rehearses everything and saves nothing; `run` also saves the runs and the pack (exit 0, or 2
with the reason). Every configuration `check` runs counts as a trial; a replaced one goes in the ledger.

## Reproducibility

`dataset_hash` covers a snapshot's normalized contents and `dataset_id` a frozen dataset's manifest
(request hashes, snapshot and rate hashes, ranges, warnings). `code_hash()` hashes every `quant_core`
source file in path order; run manifests record it as the engine hash, with the Python version,
configuration hash, source artifact hash and quality issues. `result_hash` is the content hash of a
run's result, and `COMPLETE.json` binds every saved file. A study binds its registration hash, dataset
ID, code hash, each configuration's hash and every run's result hash; `write_pack` returns
`pack.json`'s SHA-256. Hashes are over canonical JSON (sorted keys, decimals as text); they detect
change but do not authenticate a source. Decimal arithmetic is platform-independent; only Φ uses
floats, so DSR values are rounded.

## Known limits

- Tiingo covers today's tickers only, dividends are assumed paid on the ex-date, and the calendar is
  SPY's trading days. When each day's data is final, and whether published results count as
  redistribution, are open questions.
- Fills are modelled at the open with fixed slippage, no auction or exit-capacity model, no taxes, no
  settlement timing. Buys are whole shares and all-or-nothing: one the cash cannot cover waits a month.
- Dated index membership (`universes/`) exists, but no qualified survivorship-free history; V1 trades
  ETFs only.
- The historical V floor is not computed yet, no built-in has been registered or run on real data,
  and Windows runs are not yet verified.
