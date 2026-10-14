# Roadmap: V1 tester release

Decided 2026-10-11. The first release goes to a small group of testers (smart,
technical people who have traded without a system). It must show the product's
value end to end, honestly, on one data provider, one platform. The full V1
scope in `PROJECT.md` remains the target; items marked deferred come after the
tester round.

## Scope of the tester release

- Five built-in plans: multi-asset trend, dual momentum, US sector rotation,
  inverse-volatility allocation, and an ML-ranked ETF rotation. Each qualifies
  under [the evidence standard](STRATEGY_EVIDENCE.md).
- "This month": current holdings, the order sheet with share counts and the
  reason for each line, a day-one order sheet for a new account.
- "Rewind": import the user's own trade history and compare it with a plan on
  the same cash flows. The comparison must be able to say the user did better.
- Backtest with user-controlled costs, dates, cash yield and safety limits;
  evidence pack per plan; every trade explained.
- Trader view by default (plain language, money, worst falls); Analyst view
  adds statistics, settings and manifests.
- Data: Tiingo only, the user's own free key, cached locally. Daily data;
  monthly decisions (weekly optional); no intraday.
- Platform: local web app (Python server plus browser), Windows build first.
- Nothing leaves the user's machine. No account, no telemetry, no trading.

Deferred past the tester round: Developer/Source edition, customer model
training, visual strategy builder, stock screener, index universes,
EODHD/CSV adapters, licensing and storefront, in-app or paper trading.

## Build order

| # | Work | Status |
| --- | --- | --- |
| C | Engine prerequisites: Tiingo adapter; idle cash earns Treasury 3-month yield; read-only reference series; entry-to-exit trade records ([design](superpowers/specs/2026-10-11-engine-prerequisites-design.md)) | done (version 0.6.0) |
| D | The four rule plans with hand-checked tests; deflated Sharpe ratio ([design](superpowers/specs/2026-10-12-rule-plans-design.md)) | done (version 0.7.0) |
| E | ETF data download; historical V[SR] floor; registered runs of the four plans; evidence-pack report. E1 frozen dataset ([design](superpowers/specs/2026-10-13-etf-dataset-design.md)), E2 evidence machinery, E3 registered studies | in progress (E1 done: frozen dataset of 2026-10-12; E2a evidence numbers and E2b registered-study runner and evidence pack done) |
| F | ML-ranked rotation: frozen ~60-ETF list (owner approves before training); features and labels; Ridge then LightGBM, walk-forward; comparison with the plain rule; fifth evidence pack; versioned shipped model | |
| G | "This month" order sheet, day-one sheet, mark as done | |
| H | Rewind: deposits and withdrawals in the engine; trade-history import (template, then testers' brokers); replay with cash flows; honest comparison report | |
| I | Local web app with the Trader/Analyst toggle and the seven screens of the demo | |
| J | Windows build via GitHub Actions; smoke test; install guide | |
| K | Tester round: the ten-minute test, feedback, fixes | |

Done before this roadmap: market-data layer, daily portfolio backtester,
risk and sizing, validation framework, data quality and corporate-action
cross-checks, the evidence standard, the research ledger (44 trials, none
qualified), repository cleanup (tag `archive/research-2026-10` holds the
removed research docs, scripts and tests).

## Decisions behind the scope

- Public, published rule sets are the point, not a weakness: the value is a
  correct implementation, an honest record including losing years, a monthly
  instruction, and a tool that keeps the user doing it.
- The ML plan predicts which ETFs are likely to do relatively better next
  month. It is shown as ranks with its measured hit rate, never as
  probabilities or forecasts, and it ships with the same evidence as the rule
  plans, including the case where it does not beat them.
- The product tells the user what to buy, how much, and why. The "why" is
  always the rule and the number that triggered it, never an opinion.
- Monthly over daily: more frequent decisions multiply costs and trade on
  noise; the backtester lets a user see that for themselves.
- Tiingo over Alpaca for V1: history from each ETF's launch (1993 for SPY,
  1998 for the sector funds, 2001–2006 for the rest; 2008 is in every backtest),
  raw and adjusted prices in one response for the corporate-action
  cross-check, and documented licence terms that cover bring-your-own-key
  software. Alpaca stays as internal development data.
- Windows first because testers use it; Linux is where development runs.

## Open items for the owner

- Approve the ~60-ETF universe before any ML training (step F).
- Name the brokers testers use, and supply one or two anonymised exported
  histories, before step H.
- Confirm with Tiingo, before publishing reference numbers or shipping the ML
  model, that derived results (returns, drawdowns) and model weights trained on
  the data are not treated as data redistribution; also ask when each day's
  bar, `divCash` and `adjClose` are final (the importer assumes 18:00 New York
  time).
- Run the SMA200 forward-journal capture after the 2026-10-30 close (see
  [the forward journal](FORWARD_SHADOW.md)).
