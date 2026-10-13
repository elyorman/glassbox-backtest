# Evidence machinery (Plan E2) — design

Date: 2026-10-14. Approved by the owner the same day. Roadmap step E, part
E2, between E1 (the frozen dataset, done) and E3 (the registered studies).
Everything here is built and tested on synthetic data; nothing runs on real
prices until E3. Normative requirements are in
[the evidence standard](../../STRATEGY_EVIDENCE.md), Sections 2–4.

Built as three plans, each with its own dry run and reviews: **E2a** the
numbers and comparison portfolios, **E2b** registration, study runner and
evidence pack, **E2c** the historical V[SR] floor.

## 1. Conventions

- **Excess return.** For session t after the first, x_t = r_t − c_t, where
  r_t is the engine's `session_return` and c_t =
  `cash_rates.accrual(1, previous session, t)`: the same lagged ACT/365 rate
  idle cash earns. The first session has x = r = 0. Under the 0% cash variant
  c_t = 0.
- **Annualization.** Sharpe = mean(x) / sample deviation(x) × √252; Sortino =
  252 × mean(x) / √(252 × mean(min(x, 0)²)); volatility = sample deviation(r)
  × √252; CAGR on calendar days (365.2425), as `summarize_run` already
  computes. Calmar = CAGR / maximum drawdown.
- **Capital and costs.** $100,000 initial cash; costs as slippage of 10, 25
  and 50 bps per side (10 is primary); plans and comparison portfolios invest
  95% and earn the dataset's T-bill rate on idle cash.

## 2. Numbers (E2a) — `quant_core/analytics/evidence.py`

Pure functions over a `BacktestResult` (or its saved bundle) and the dataset's
`CashRateSeries`; each tested on hand-worked synthetic runs.

- **Results:** CAGR, volatility, Sharpe and Sortino over T-bills, maximum
  drawdown, Calmar, longest underwater period (sessions), average gross
  exposure, annual turnover (filled notional over equity per calendar year),
  trade count (`round_trips`), whole-share shortfalls (selected lines with
  `below_one_share`) and opening-gap rejections (orders rejected for
  insufficient cash).
- **Periods:** each calendar year (return, maximum drawdown, Sharpe over
  T-bills); the windows 2016–2019, 2020–2022 and 2023 to the end; since the
  registered publication date; any registered segments (inverse volatility's
  three-ETF and four-ETF years); best and worst 12 months from month-end
  equity; the five largest drawdowns (peak, trough and recovery dates, depth,
  sessions to trough and to recovery, or "not recovered").
- **Uncertainty:** a paired stationary bootstrap of session indices (the
  existing `stationary_indices`), per registered block length (default 5, 20
  and 60 sessions), repetitions (500) and seed (1729). Each replicate gives the
  252-session annualized return, Sharpe over T-bills, maximum drawdown of the
  resampled path, and Sharpe over T-bills minus the primary reference's;
  intervals are the existing nearest-rank 2.5% and 97.5% percentiles.
- **Deflated Sharpe ratio:** N, the study's own V (sample variance of the
  daily excess Sharpe of the parent and its neighbours at 10 bps; shift copies
  excluded), the historical floor, T and moments from the parent's daily
  excess returns; DSR under the larger V (primary) and the smaller.
- **Overlap with earlier built-ins:** Pearson correlation of daily excess
  returns on common sessions, and mean holdings overlap Σ min(w_a, w_b) over
  common month-end sessions (w = position value / equity).

**Comparison portfolios** (on the Plan D monthly runner, 95% invested,
monthly decisions):

- `FixedWeightPlan(weights)`: constant target weights; a skipped ETF's weight
  stays in cash. The 60/40 reference is SPY 0.6, IEF 0.4.
- `EqualWeightPlan(universe)`: equal weights over the ETFs that pass the data
  checks at each decision.
- SPY buy-and-hold: the existing `buy_hold` rule strategy at 95%.
- T-bills: a source that never trades, so equity is cash earning the rate.

## 3. Registration, runner and pack (E2b)

- **Registration** (`docs/registrations/<study>.json`, written in E3):
  schema version; study name, role and tag; registration time; code hash;
  dataset ID and tickers; the parent plan configuration, its neighbours and
  the rebalance shifts (−2, +2), each with its hash; period (start = the first
  full decision); publication date; segments; cost levels; initial cash;
  references and the primary one (60/40 for the allocation roles, SPY for
  sector rotation); bootstrap settings; trial counts (cumulative N, this
  study's count, per-role count) and the historical floor; sources and
  departures; related ledger rows; the cross-check decision and its reason;
  plain-language disclosures written before the run; earlier studies for the
  overlap section. `load_registration` validates every field and computes the
  registration hash; plan configurations round-trip through
  `plan_to_dict` / `plan_from_dict`.
- **Runner** (`quant_core/validation/study.py`): refuses to start unless the
  dataset ID and the code hash equal the registration's and the output
  directory is new. It runs the parent at each cost; at 10 bps the
  second-open delay, the 0% cash variant, each shift and each neighbour; and
  every comparison portfolio at each cost and under 0% cash. Each run is saved
  once with `save_run` under `local/<study>/runs/<key>/`.
- **Pack** (`quant_core/reporting/evidence.py`): `pack.json` with every number
  and `PACK.md` for reading: registration summary, results by cost,
  references, uncertainty, deflated Sharpe ratio, periods, sensitivity
  (parent, neighbours, shifts, delay, costs, 0% cash), overlap, cash
  convention, limitations and reproduction (one command plus the registration
  hash, dataset ID, code hash and every run's result hash).
- **Limitations page:** generated, never written after results: data limits
  (provider, history per ETF, the snapshot's limitations and warnings), the
  calendar years with losses and the five largest drawdowns with dates, a
  fixed statement of what the plan does not promise (no guarantee; past
  results; no taxes; opening fills approximated; whole-share, all-or-nothing
  orders), and the registration's disclosures (for example EFA for ACWI
  ex-US, the open-gap note, sector rotation's earlier trial).
- **Command:** `python -m quant_core.validation.study run REGISTRATION
  --dataset DIR --output local/<study>` produces the runs and the pack;
  `check REGISTRATION` validates a registration before it is tagged.

## 4. Historical V[SR] floor (E2c)

- `python/research/historical_sharpe_floor.py` (research code, never imported
  by the product) verifies each study's seal manifests (file SHA-256s), reads
  the 44 counted trials' zero-reference Sharpe at 10 bps from the sealed
  results, divides each by √252 and takes the sample variance (n − 1).
- The list of trials (study, configuration, file, field, value, file
  SHA-256) is committed as `docs/registrations/historical-sharpe-floor.json`;
  the value goes in the research ledger header before the first registration.
- Study 2 (2026-10-03, all ten recipes) ran two 10 bps windows; its declared
  primary window, `common_warmup`, is used. It also gives the larger variance
  (1.97e-4 against 1.91e-4 for `ten_year`), the more conservative choice; the
  ledger states both.

## Testing

Synthetic snapshots with a few sessions a month, hand-worked expected values:
excess returns with a changing rate; each results metric; a calendar year,
window and segment; month-end 12-month extremes; drawdown episodes including
one not recovered; bootstrap determinism by seed and interval bounds on a
series with a known answer; correlation and overlap on two small runs; each
comparison portfolio's trades; registration validation and every refusal; an
end-to-end study and pack on a synthetic registration; the floor script on a
synthetic sealed tree, including a tampered file.

## Not in this step

Writing the four registrations, choosing neighbours, tagging, the real runs
and ledger rows (E3); the app's rendering of packs (step I); forward signal
journals (when a plan ships).
