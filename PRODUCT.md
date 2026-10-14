# Product

A local app that turns four published investing rules into an exact monthly
instruction, with an honest, fully traceable backtest and built-in risk and
money management.

> Pick a proven rule, see honestly how it did, set your risk limits, and get
> exactly what to buy each month.

## Who it is for

Long-term investors and part-time traders who want a rules-based plan for their
money and don't want to watch the market every day. They can install an app and
paste an API key; they are not finance experts.

It is not for day traders, stock pickers or anyone looking for predictions.

## What V1 is

- A local web app: a Python engine plus the user's browser, on the user's own
  computer. No account. Nothing leaves the machine.
- Data from Tiingo with the user's own free key, stored locally.
- Four built-in ETF plans, and a trend test on any single US stock or ETF.
- Monthly decisions from daily prices. Decide at the month-end close, trade at
  the next open.
- The app says what to trade and why. The user places orders at their own
  broker.

## Screens

| Screen | What it does |
| --- | --- |
| Setup | Paste the Tiingo key; download and check price history. |
| Plans | The four plans as cards: what they hold, how often they trade, worst year. |
| Backtest | Run a plan with your dates, amount, costs and risk settings; see results, trades, decisions and assumptions. |
| Test a ticker | The trend rule on any stock or ETF (QQQ, AAPL…) against simply holding it. |
| This month | The order sheet: shares to buy and sell, the reason for each line, the estimated cost. |
| Holdings | Your positions and cash, typed in or imported from CSV; how to move onto a plan. |
| Settings | Data key and refresh, default costs, risk settings. |

## Built-in plans

| Plan | Rule | ETFs |
| --- | --- | --- |
| Multi-asset trend | Hold each asset class only while it is above its 10-month average; otherwise cash. | SPY, EFA, IEF, VNQ, GSG |
| Dual momentum | Hold US or foreign stocks, whichever did better over 12 months; bonds if US stocks didn't beat T-bills. | SPY, EFA, AGG |
| US sector rotation | Hold the 3 sectors with the best 12-month return, skipping the latest month. | 11 sector ETFs |
| Inverse volatility | Spread money across stocks, bonds and commodities, more into the calmer ones. | SPY, IEF, LQD, GSG |

Each plan has a limits page: the years it lost money, the data and period it was
tested on, the costs assumed, and what it does not promise.

## Risk and money management

Every order passes through this layer. Defaults keep each plan as published; the
user switches controls on and compares "as published" with "with my settings".

| Control | What it does | Default |
| --- | --- | --- |
| Amount managed | The part of the account the plan runs. | Whole account |
| Cash reserve | Always kept in cash. | 5% |
| Whole shares | Buys rounded down to whole shares. | Always |
| Minimum trade | Skips rebalancing trades smaller than this. | 2% of account (to confirm) |
| Costs | Slippage and fees on every trade. | 10 bps per side |
| Position cap | No single ETF above this share. | Off |
| Drawdown brake | Hold half after a set fall from the peak, cash after a larger one; re-enter by a stated rule. | Off |
| Stop per holding | Sell a holding that falls a set amount below entry; cash until the next decision. | Off |

Results say plainly when a control made things worse.

## Not a black box

Every number can be traced to its inputs and recomputed:

- **Every trade** with the rule and numbers that caused it.
- **Share math** for each trade: account × target ÷ close, rounded down, minus
  shares held, plus any cap, skip or brake, and the fill price with slippage.
- **Monthly decision log**: every ETF every month, including those that didn't
  trade.
- **Rejected orders** with their reason. Nothing is resized silently.
- **Where every dollar went**: gains, dividends, interest, costs. Cash, holdings
  and value reconcile every trading day.
- **Assumptions** the engine writes into every run, in plain words.
- **Run details**: data, settings and engine fingerprints, and the command that
  reproduces the run.
- **Audit bundle**: every order, fill, cash movement, daily value and decision as
  CSV and JSON.

## How people use it

### New user

1. Install and open; the app opens in the browser.
2. Paste a Tiingo key; prices download and are checked.
3. Read the plan cards and compare them.
4. Backtest a plan; read the results and the limits page.
5. Try risk settings and compare.
6. Enter the cash for the plan; get the day-one order sheet.
7. Place the orders at the broker; mark them done, correcting any fill that
   differed.

### Already holding positions

1. Enter holdings and cash, or import the CSV template.
2. The app splits them into "in the plan" and "outside the plan".
3. Choose how to start:
   - **Full switch:** sell what is outside, buy the plan.
   - **Part of the account:** the plan runs a set amount; nothing else is touched.
   - **Gradual:** cash and in-plan ETFs follow the plan; other holdings stay until
     sold.
4. See the trades and costs of each choice, with a tax warning (no tax
   calculation).
5. The order sheet starts from real holdings and lists only what must change.

Positions outside the plan are never managed, but each can be checked with
"Test a ticker".

### Every month

After the month-end close: refresh data, open "This month", place the orders,
mark them done.

### Other situations

| Situation | What the app does |
| --- | --- |
| Mid-month check-in | Shows holdings and value; lists an action only if a stop or the brake triggered. |
| Adding or taking out money | The order sheet moves toward the targets to use or raise it. |
| Missed a month | Uses the latest decision and current prices, and says how late the trades are. |
| An order filled differently | The user enters actual shares; next month corrects the gap. |
| Plan holds cash or bonds | Shows the rule and number that caused it. |
| Switching plans or settings | Backtests both side by side, then shows the trades to switch. |
| Short-history ticker | Runs it and warns how few years it covers. |
| Data refresh fails | Says what failed and how to fix it; keeps the last good data; no order sheet from incomplete data. |
| Missing or suspicious price | Names the ticker and date; blocks the order sheet until resolved. |
| Month-end holiday | The trading calendar picks the last real session. |

## Architecture

```text
Browser app            Plans · Backtest · Test a ticker · This month · Holdings · Settings
      │
Local server           one API; a thin CLI calls the same API
      │
Engine (Python)
  Data ──► Plans ──► Risk and money ──┬──► Backtest
  Tiingo,  target     reserve, caps,  │    next-open fills, costs, dividends, T-bill interest
  checks,  weights    brake, stops,   └──► Order sheet
  calendar            min. trade           from real holdings, with reasons
      │
Local storage          price cache · holdings · settings · saved runs
```

- Backtest and order sheet share one path, so the order sheet always matches the
  backtest the user chose.
- Only price data comes in from outside, fetched with the user's key.
- Windows first, Linux supported.

## Not in V1

| Left out | Why |
| --- | --- |
| Broker connection, auto-trading | The user stays in control; no broker credentials to protect. |
| Picking stocks from an index | Needs historical index membership; otherwise results are inflated by survivorship. |
| ML ranking | Unlikely to improve monthly ETF rules; revisit if paying users ask. |
| Rewind (your past trades vs a plan) | Needs trade-history import from each broker. |
| Intraday, futures, options, forex, crypto | The engine is built for daily stocks and ETFs. |
| Tax calculation | Depends on country and account; the app only warns. |
| Alerts, accounts, cloud sync, macOS | Local-first; the user opens the app. |
| Strategy builder | The four plans, "Test a ticker" and the risk settings cover V1. |

## Open questions

- Tiingo: are published backtest results allowed, and when is each day's data
  final?
- Default levels for the drawdown brake, its re-entry rule, the stop and the
  minimum trade.
- Do testers want a weekly option?
- Price, and how the first buyers pay.
