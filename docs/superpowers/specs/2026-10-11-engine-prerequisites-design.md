# Engine prerequisites (Plan C) — design

Date: 2026-10-11. Approved by the owner the same day. Roadmap step C
(`docs/ROADMAP.md`). Next step: write the implementation plan, dry-run it on a
scratch copy, execute task by task with subagents and reviews (as Plan B).

## Verified facts this design relies on

- Tiingo daily prices (`/tiingo/daily/<ticker>/prices`, header
  `Authorization: Token <key>`): `open/high/low/close/volume` are raw;
  `adjClose/adjVolume` adjusted; `divCash` is cash per share on the ex-date
  (SPY 2024-12-20: 1.965548); `splitFactor` is new/old shares on the ex-date
  (AAPL 2020-08-31: 4.0); no dividend payment date. Dates look like
  `2003-01-02T00:00:00.000Z`. Metadata (`/tiingo/daily/<ticker>`): `startDate`,
  `endDate`, `exchangeCode`, `name`. Free tier: 50 requests/hour, 1,000/day,
  500 symbols/month. Docs: software where users supply their own token and no
  data is distributed needs no licence.
- History: SPY 1993, XLK/XLE 1998, EFA 2001, IEF/TLT 2002, EEM 2003, VNQ 2004,
  GLD 2004-11-18, BIL 2007.
- Treasury "Daily Treasury Par Yield Curve" yearly CSV:
  `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/<YEAR>/all?type=daily_treasury_yield_curve&field_tdr_date_value=<YEAR>&page&_format=csv`.
  Header `Date,"1 Mo",...,"3 Mo",...`; column set varies by year (read by
  name); dates `MM/DD/YYYY`; values are percent. 2003 is available. Earlier
  research used the "3 Mo" column with strictly lagged ACT/365 accrual
  (archived `research/robustness_metrics.py`, tag `archive/research-2026-10`).

## 1. Tiingo adapter — `quant_core/data/tiingo.py`

- `TiingoClient(api_token, cache_dir, timeout=30)`: `prices(ticker, start, end)`
  and `metadata(ticker)`. Token only in the header, never in URLs, logs,
  manifests or error text. Raw bodies cached content-addressed; a request
  manifest (without the token) maps request → body hash and retrieval time.
  Cached requests are never re-sent. Errors: 401/403 → "key rejected",
  404 → "unknown ticker", 429 → "rate limit; cached tickers are kept, resume
  later". Ticker pattern validated; redirects refused.
- `TiingoJsonSource(price_responses, metadata_responses, sessions, metadata)`
  → `Snapshot`:
  - Bars from raw OHLCV; `adjustment_policy="raw"`.
  - `divCash > 0` → `Dividend(ex=date, amount=divCash, pay_date=date)`;
    limitation: "Tiingo supplies no payment dates; dividends are assumed paid on
    the ex-date."
  - `splitFactor != 1` → `Split` with exact counts from
    `Fraction(str(splitFactor)).limit_denominator(1000)` (4.0 → 4/1).
  - `actions_complete=True` with limitation "provider-reported actions";
    cross-check with `provider_adjustment_disagreements` against `adjClose`;
    any `factor_mismatch` stops the import.
  - Security from metadata: `security_id=symbol=ticker`, `exchange`,
    `listed_on = first bar date`.
  - Refuse bars dated on/after the retrieval date in New York unless retrieved
    after 18:00 ET (no partial sessions).
- Calendar helper: sessions = SPY's trading dates (disclosed limitation
  "calendar derived from SPY trading days"); check every other ticker's dates
  are a subset. An exchange-calendar library can replace this later.
- No CLI in Plan C (data download command is Plan E).

## 2. Interest on idle cash

- `quant_core/data/treasury.py`: download yearly CSVs (public, no key,
  cached), parse by column name, `CashRateSeries(source, series, retrieved_at,
  observations=((date, annual_fraction), ...))` with strict validation
  (ascending unique dates, finite, -1 < rate <= 1, percent → fraction).
- `RunConfig.cash_rates: CashRateSeries | None = None`. None → behaviour and
  results identical to today.
- Accrual: at the start of each session after the first, before corporate
  actions and orders, `interest = cash_at_previous_close × rate × days / 365`,
  where `rate` is the latest observation strictly before the previous session
  (stale > 10 days → run refused at preflight) and `days` is calendar days
  between sessions. Credited as cash movement kind `interest`; ledger tracks
  `interest_income`; accounting identity becomes
  `equity = initial + realized + dividends + interest + unrealized`.
- `DailyState` gains `interest_income` (last field, default 0). `RunSummary`
  unchanged (keeps old bundle verification valid).
- Manifest assumptions state the cash convention; `summarize_run` includes
  interest in the P&L reconciliation and reports `interest_income`.

## 3. Read-only reference series

- `RunConfig.references: tuple[str, ...] = ()` — registry securities a strategy
  may read but not trade. `SessionContext.history()` allows universe ∪
  references; orders for references are refused (existing `outside_universe`).
  Quality errors on references block the run like universe errors.
- `SessionContext.cash_growth(start, end)` → compounded growth factor of the
  same lagged accrual between two calendar sessions, `end <= as_of`; error if
  no `cash_rates` configured.

## 4. Entry-to-exit trade records — `quant_core/analytics/trades.py`

- `round_trips(result) -> tuple[TradeRecord, ...]`, computed after the run from
  fills, orders (for reasons), corporate-action records and the final state.
- One record per holding period (flat → held → flat), with: trade id, security,
  symbol, status (closed/open), entry signal date, entry date, entry reason,
  exit signal date, exit date, exit reason (sell reason, stop kind or
  delisting), buy/sell fill counts, cost basis (buy notional + fees), proceeds
  (sell notional − fees, plus delisting cash), dividends entitled during the
  holding, fees, slippage, realized P&L, unrealized P&L (open only, from the
  final state), total P&L, return on cost basis, holding days.
- Partial sells, re-adds, splits, stops and delistings handled; the engine loop
  is not changed.

## Moved or dropped

- Deposits and withdrawals move to Plan H (Rewind): they change return and
  drawdown measurement and only Rewind needs them.
- The bar-frequency metadata field is dropped (intraday is out of scope).

## Testing

Hand-calculated tests for each part (e.g. $10,000 cash at 5% for 3 calendar
days earns exactly 10000 × 0.05 × 3 / 365); offline fixtures from small real
Tiingo and Treasury responses; no-look-ahead tests for the rate lag and the
reference series; identity reconciliation with interest; unchanged results
when `cash_rates` is None; token never present in cache, manifest or errors.
