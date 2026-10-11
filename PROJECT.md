# PROJECT.md

## Project Summary

Build a commercial, local-first **Quantitative Trading Research & Risk Platform
for U.S. equities and ETFs**. It helps a trader make systematic, reproducible
decisions under uncertainty and does **not** claim to predict markets with
certainty. Its value is the disciplined combination of strategy research,
market scanning and cross-sectional ranking, portfolio-aware backtesting,
out-of-sample and robustness validation, deterministic risk management,
money/position management, and transparent analytics with trade-level
auditability.

V1 is the first paid production release, not an MVP/demo; its scope may be
narrow but not provisional. A tester release comes first (see **V1 Tester
Release**). Build order and status are in [the roadmap](docs/ROADMAP.md). Every
past study, including failures, is in [the research ledger](docs/RESEARCH_LEDGER.md);
the git tag `archive/research-2026-10` keeps the removed research documents and scripts.

## Product Positioning and Differentiation

The central product promise is:

> **A serious quantitative stock research platform that gives traders institutional-style validation and risk discipline without requiring them to code or trust a black box.**

The customer-facing message is:

> **Find better opportunities. Test them properly. Understand the risk. Make more disciplined decisions.**

Market it as a quantitative stock research platform, not AI trading software;
ML is a supporting capability, not the product identity or a promise of market
prediction. The intended gap is between retail simplicity and quantitative
rigor. Reasons to choose the finished product should be:

- easier to use than assembling and maintaining a Python quant stack;
- more rigorous than a simple signal backtest, with shared portfolio cash,
  executable timing, explicit costs, corporate actions and rejected orders;
- validation-first, with chronological OOS/walk-forward, parameter sensitivity,
  cost stress and regime checks explained in plain language;
- stock discovery, testing, risk and sizing in one consistent workflow;
- well-researched built-in plans, rule-based and ML-ranked, with disclosed evidence packs, and
  validated ML rankings, with inspectable inputs, rules, scores and decisions;
- no-code rule-based strategy creation in Desktop;
- local-first research and private customer data, without recurring cloud lock-in;
- no mandatory software subscription; the purchased major version is perpetual;
- source access, extension capability and the model-training pipeline in
  Developer/Source Edition.

These are commitments to demonstrate through acceptance evidence and user
evaluation, not verified claims of superiority over every competitor.
"Institutional-style" refers to validation, accounting and risk discipline, not
institutional data, execution access, certification or returns. "Explainable"
means users can inspect the basis, scope and limitations of an output; model
explanations are not proof of causality or predictive certainty.

## Product Philosophy

There is no “magic” algorithm that knows what happens next. The system should
reduce avoidable decision errors by making rules explicit, testable, repeatable,
and measurable. It should answer questions such as:

- What exactly caused this candidate to rank highly?
- What would the strategy have done historically using only information available at the time?
- How did it perform after realistic execution assumptions and costs?
- What was the worst drawdown and when did it fail?
- Does the result survive different periods, universes, parameters, and data providers?
- What happens if risk per trade, stops, slippage, or portfolio constraints change?
- How does it compare with a relevant benchmark and with simpler strategies?

## V1 Tester Release

Decided 2026-10-08 to 2026-10-11. The first release goes to a small group of
testers. It must show the product's value end to end, honestly, on one data
provider and one platform. The full V1 scope in this document remains the
commercial target; [the roadmap](docs/ROADMAP.md) holds build order and status.

- **Five built-in plans**, each qualified under
  [the evidence standard](docs/STRATEGY_EVIDENCE.md): four rule-based ETF plans
  (multi-asset trend, dual momentum, US sector rotation, inverse-volatility
  allocation) and one **ML-ranked ETF rotation**.
- The ML plan ranks ETFs by expected relative next-month return. It is trained
  chronologically, compared against the plain rule, shown as ranks (never
  probabilities) and shipped as a fixed, versioned model. Customers do not
  retrain it.
- **"This month"**: what to buy today for a new account, then each month's
  changes, as an order sheet with share counts and the reason for each line.
- **"Rewind"**: import the user's own trade history and compare it, honestly,
  with a plan on the same cash flows. The comparison must be able to say the
  user did better.
- Trader view by default, Analyst view on demand (see **UI Direction**).
- Monthly decisions (weekly optional) on daily data; no intraday.
- Data: Tiingo only, with the user's own key (see **Data Provider Strategy**).
- Platform: local web app (Python server plus browser) on the user's machine;
  Windows build first, produced by GitHub Actions.
- Nothing leaves the user's machine: no account, no telemetry, no trading.

Deferred past the tester release: Developer/Source edition, customer model
training, the visual strategy builder, stock screener, index universes, EODHD
and CSV/Parquet adapters, licensing and storefront, and in-app or paper trading.

## Product Requirements and Acceptance Contract

Confirmed with the user on **2026-10-03**. These 15 groups are the product
acceptance contract; the sections below detail how to deliver them. Every
substantial feature must identify the requirement IDs it supports and the
evidence that demonstrates its usefulness and correctness. Features that do not
improve usefulness, trust, usability or decision quality should be questioned.

### PR-01 — Reliable Data Handling

Customers bring supported provider data or local files; the product is not a
market-data service. Correctly distinguish raw/adjusted prices, process
splits/dividends, and detect missing, invalid, duplicate or inconsistent bars.
Respect an explicit trading calendar instead of inferring sessions from
available bars. Support security identity/ticker changes, delistings, relevant
corporate actions and point-in-time membership when supplied. Record provider,
dataset/version/hash, retrieval date and assumptions. Surface incomplete or
unsuitable data, prevent trustworthy-result claims where coverage is inadequate,
and never silently repair data in a way that changes results.

### PR-02 — Trustworthy Backtesting

Prevent look-ahead and accidental same-bar signal/execution. Support explicit
next-session execution, shared cash, concurrent positions, commissions,
slippage, corporate actions and delistings under the supported data contract.
Reject impossible orders rather than silently changing them. Reconcile cash,
holdings, realized/unrealized P&L and equity, with a complete order/trade ledger
and deterministic results for identical inputs. Each trade must explain its
signal reason/time, execution time/source/price, quantity calculation, exit reason,
costs and resulting P&L.

### PR-03 — Risk Management

Support per-trade planned risk, position size/count, portfolio exposure,
sector/concentration, liquidity, volatility-aware controls and drawdown-based
risk reduction. Define execution semantics for supported stops and other exits.
Risk may reject an otherwise valid strategy signal, with a visible reason.
Planned stop risk is not a guaranteed maximum realized loss.

### PR-04 — Money Management / Position Sizing

Support fixed allocation, equal weighting, fixed fractional risk, ATR/volatility
sizing and portfolio allocation constraints. Show requested/accepted shares,
capital committed, planned capital at risk, relevant assumptions and the
calculation/reason for the selected quantity.

### PR-05 — Strategy Quality

V1 must ship **at least three distinct rule-based built-ins (target four) plus
the ML-ranked rotation**, usable without coding and qualified under
[the evidence standard](docs/STRATEGY_EVIDENCE.md) (see **Reference Strategies**).
Research tools and user-created strategies do not substitute for them.

A profitable historical backtest alone does not establish usefulness. Evaluate
the economic/behavioral hypothesis, expectancy after costs, CAGR/annual return,
drawdown, Sharpe/Sortino/Calmar, adequate trade count, period/universe/regime
stability, small parameter changes, OOS results and appropriate benchmarks.
CAGR around 15–20%+, drawdown around 20–25% or lower, and Sharpe and Calmar
around/above 1 are illustrative research targets only, never promises or
pass/fail gates. Robustness has priority over maximizing historical return. For
built-ins these metrics are disclosed in the evidence pack; they never decide
inclusion or select among registered configurations.

### PR-06 — Strategy Validation

Provide clear in-sample/OOS separation, walk-forward testing, parameter
sensitivity, market-regime and applicable universe comparisons, transaction-cost
and slippage stress, benchmark comparison and visible robustness warnings.
Include Monte Carlo/resampling analysis where it answers a defined question,
with its assumptions and limitations explained. Present understandable findings,
including rejected and inconclusive outcomes, without requiring quant expertise.
Previously examined history must not be relabelled as untouched OOS evidence.

### PR-07 — Stock Discovery

Answer "What stocks should I investigate?" through universe scanning,
eligibility filters, strategy screening, relative-strength/momentum/factor
ranking, validated ML ranking, custom watchlists and historical scans. The same
supported strategy/filter definition must answer both "What matches today?"
and "What matched historically, and what happened afterward?" under the
corresponding dated data/universe assumptions.

### PR-08 — Explainability

For each candidate, show why it qualified, passed/failed rules, indicator values,
rank/score, model score where applicable, risk conditions and historical
behavior of similar signals where evidence exists. Disclose insufficient
evidence. Frame ML outputs as relative rankings/opportunity scores or validated
probabilities, never guaranteed prices or returns; an arbitrary score must not
be presented as a probability.

### PR-09 — Useful Analytics

Provide total return, CAGR, annual/monthly returns, maximum/average drawdown,
volatility, downside deviation, Sharpe, Sortino, Calmar, win rate, profit factor,
expectancy, average win/loss, payoff ratio, largest win/loss, holding period,
winning/losing streaks, exposure, turnover, cash utilization, concentration and
benchmark comparison. Include visual equity/drawdown analysis and the underlying
trade ledger. Define formulas, trade/holding conventions, averaging, annualization,
cash reference and undefined values so metrics can be independently recalculated.

### PR-10 — ML Models

Use ML to rank eligible stocks by historically supported relative future
outcomes, including return/excess-return ranking, trade-outcome probability and
opportunity scoring. Fit only information available at the time, use
chronological/OOS validation, avoid shuffled temporal leakage, and compare with
simple baselines. Evaluate net portfolio results as well as predictive metrics;
record model/version/training-data provenance. Models remain subordinate to
deterministic risk/portfolio controls. Retain additional complexity only when
it improves robust OOS results over simpler approaches.

### PR-11 — Ease of Use

A serious stock trader/investor must be able to use Desktop without Python,
coding or quantitative-finance expertise. The primary workflow must answer:
"What should I look at?", "Why is it interesting?", "Has this idea worked
historically?", "What can go wrong?", "How much should I risk?", and "Can I
trust the evidence?" Advanced details belong in drill-downs; material financial
assumptions and limitations remain visible. Validate this through observed user
tasks rather than assuming that a completed UI is easy to use.

### PR-12 — Strategy Creation

Desktop users can create rule-based strategies without editing source code.
The visual builder must cover universe selection, eligibility, supported
indicators/operators, entry/exit rules, ranking, sizing, portfolio/risk
constraints, parameters, and save/duplicate/import/export. Its saved definition
must be usable by scanning, backtesting and validation without rewriting rules.
Arbitrary code/custom extensions belong to Developer/Source Edition; the
Desktop builder need not expose every possible indicator or programming construct.

### PR-13 — Auditability and Reproducibility

Every run identifies strategy/configuration, provider, dataset/hash, universe,
period, adjustment mode, execution assumptions, slippage, fees, risk policy,
model/version/hash and engine/version/hash. Preserve enough evidence to rerun
and inspect results; meaningful input changes must produce a distinguishable
run. Failed/rejected experiments remain in the research history.

### PR-14 — Privacy / Local-First

Customer market data, API keys, strategies, portfolios, positions, trade history,
backtest results, research projects and model inputs/artifacts remain on the
customer's machine. Product backends must never store them, including through
telemetry or diagnostics. Cloud records are limited to commercial/account data:
email/customer ID, purchases, licenses, software/download entitlements and
activation information. Software distribution/licensing is separate from local
research execution.

### PR-15 — Overall Product Test

Accept a feature when it materially helps a user find an opportunity, understand
it, test it, validate it, manage risk, size it correctly or understand the
evidence. Optimize for **useful + trustworthy + easy to use + actually demanded
by stock traders/investors**, not feature count. Correctly rejecting an apparent
edge is a useful result. Product value must not depend on a secret strategy,
an attractive backtest or mandatory use of ML.

### Requirement Ownership and Release Evidence

| Requirement IDs | Primary roadmap stages | Evidence required before claiming delivery |
| --- | --- | --- |
| PR-01 | 1: Data layer | Qualified provider/local-file behavior, calendar/action/identity fixtures, provenance and visible data-health failures. |
| PR-02 | 2: Backtester | Hand-reconciled financial cases, causal/deterministic execution and inspectable complete ledgers. |
| PR-03, PR-04 | 3: Risk/sizing | Tested sizing/rejection/exit semantics and user-visible risk/quantity calculations. |
| PR-05, PR-06 | 4–5: Strategies/validation | Built-ins: registrations, the research ledger including failures, and complete evidence packs per [the evidence standard](docs/STRATEGY_EVIDENCE.md). Product: working OOS/walk-forward/stress validation tools and understandable decisions. |
| PR-10 | 6: ML | Leakage-safe chronological fitting, baseline comparisons, net portfolio evidence and model provenance. |
| PR-07, PR-08, PR-09 | 7: Scanner/analytics; earlier engine support | Current/historical definition parity, reconciled metrics and inspectable candidate/trade explanations. |
| PR-11, PR-12 | 8: Desktop UI; strategy contracts from Stage 4 | Observed no-code install/configure/build/scan/test/validate/risk tasks and round-trip saved strategies. |
| PR-13, PR-14 | All stages | Reproducible runs, provenance/integrity tests and verified absence of research-data uploads. |
| PR-15 | All stages and 9: Release | Real-user usefulness/usability evidence and a supported requirement for each shipped feature. |

Engine correctness, empirical strategy/model qualification and customer-facing
usability are separate evidence requirements; passing engine tests does not
deliver the product promise.

## Commercial Model

The product is sold primarily as **perpetual desktop software**, not SaaS,
deliberately separating ordinary use, source access and commercial
redistribution. Prices and counts below are market-test hypotheses that may
change before launch; they live in commercial configuration, never in quant logic.

### Desktop Edition

The packaged Windows/Linux application with official production
strategies/model artifacts; scanner, strategy configuration/builder,
backtesting, validation, risk, sizing, analytics, Trade Explorer, persistence
and reporting; supported data-provider adapters and local CSV/Parquet import;
documentation; and a perpetual license to the purchased major version under the
final EULA. Source code is **not** included. Third-party market data is not
bundled unless redistribution rights are secured; customers normally bring
their own API credentials/data.

**Pricing hypothesis:** $599 normal; **$399 Early Bird while the shared Founding
Customer pool remains open**. The storefront shows both prices together.

### Developer / Source Edition

For technical users who value inspection, extension and private/internal
modification: the Desktop product plus application/platform source code, build
instructions, tests, architecture and extension documentation. The V1 edition
**includes the production-model training pipeline**. Proprietary third-party
training datasets are excluded unless redistribution rights are secured;
internal research artifacts are included only when deliberately approved.

**Pricing hypothesis:** $2,499 normal; **$1,499 Early Bird while the shared
Founding Customer pool remains open**. The storefront shows both prices clearly.

The final source license permits the agreed internal/private use and
modification but **not** redistribution, sublicensing, resale, OEM, or
competing commercial-product rights.

### Founding Customer / Early Bird Offer

One shared pool covers Desktop and Developer/Source: the first **50 unique
paying customers** qualify, whichever paid edition they buy, and a customer
buying several editions/licenses counts once. The storefront shows a live
counter (for example `34 / 50 claimed`) with the reference normal price and the
current Early Bird price. Only completed qualifying purchases advance it, not
trial downloads, email registrations or abandoned checkouts. At customer #50
Early Bird pricing ends; it never resets into another artificial scarcity campaign.

### OEM / Commercial Redistribution

No fixed public price initially. Commercial embedding, redistribution,
white-labeling, fund/company deployment beyond standard terms, and OEM rights
are negotiated agreements.

### Evaluation Edition

The evaluation is a core sales mechanism, especially for skeptical/technical
traders: the prospect verifies the product rather than views a demo.

- **14 days from first activation**;
- same application/codebase and Desktop capabilities as the paid Desktop Edition;
- no artificial limits on tickers, backtest period, trade count, supplied strategies/models, strategy configuration, validation, Trade Explorer, or exports;
- supports the prospect's own market-data credentials and local datasets;
- all local projects, cached data, configurations, and prior results survive expiration;
- purchase unlocks the existing installation without reinstall or loss of work;
- evaluation is non-commercial under the final license terms.

After expiry the application stops new research execution (exact
expired/read-only UX to be finalized) while preserving the user's work. Trial enforcement should be
reasonable, not an elaborate DRM project. A verification/reference project and
evaluation checklist ship with the product so a prospect can reproduce a known
backtest, inspect trades, alter costs/slippage/stops, test difficult periods,
run walk-forward/OOS analysis, connect their own data, and independently
recalculate selected P&L results.

### Updates & Major Versions

Do **not** promise “12 updates,” monthly releases, lifetime updates, or
indefinite support. The purchased major version is perpetual and does not
expire; its maintenance/bug-fix/minor releases are included while it remains
supported; future major versions may be optional paid upgrades; releasing V2
must not remotely disable V1. Publish the support lifecycle and upgrade pricing
before broad public sale.

### V1 Editions & Distribution

Commercial V1 is deliverable in **three forms at launch**: Evaluation, Desktop,
and Developer/Source. Customer #1 may buy either paid edition, so
Developer/Source must be genuinely shippable. The lightweight storefront uses:

- **Vercel** for the public product/pricing/download frontend;
- **Supabase** for verified-email flow, paid customer accounts and license/entitlement/purchase metadata only;
- **Cloudflare R2** for private storage of Windows/Linux installers, release artifacts and protected source archives.

**Privacy invariant:** market data, API credentials, portfolios, positions,
strategies, backtests, trade history, models/model inputs, research projects
and caches stay on the customer's computer. They are **never** uploaded to or
stored in Supabase, R2, Vercel, telemetry or another product backend. This is a
product invariant, not a V1 shortcut.

Evaluation: Download Evaluation → email → verification → short-lived authorized
download → install the same Desktop application → 14 days from first
activation; no full account required.
Paid purchases create an account for software ownership, entitlements,
downloads, license information, documentation and releases, never for trading
data. Downloads use short-lived/signed authorization, not permanent public URLs.
No sophisticated updater is needed; the application may point to the
authenticated download page. Manual delivery/licensing is an acceptable fallback
for customer #1, but the storefront path is part of the V1 target. Custom
strategies, models, data adapters and broker integrations are separate paid services.

### Early Acquisition

After customer #1 and the tester round, seek technically serious evaluators in
quant/systematic communities before paid advertising, leading with reproducible
research produced by the product rather than return claims.

## Target Customer

- a serious retail/professional-adjacent stock trader or investor who should not
  need coding or quantitative-finance expertise;
- understands that backtests do not guarantee future performance;
- wants systematic research rather than “AI stock picks”;
- values inspectability, configuration, robustness, and risk controls;
- may already have a market-data subscription or historical dataset.

Developer/Source additionally serves technical users who want source access,
custom extensions and model training. The first customer is also a design
partner but receives the same core product as later customers, not a one-off script.

## V1 Asset Coverage

- **Assets:** U.S. listed equities and major U.S.-accessible ETFs.
- **Frequency:** daily bars; intraday/tick data is deferred.
- **Built-in universes:** S&P 500 (primary large-cap reference), Nasdaq-100,
  Russell 1000 (subject to data/licensing feasibility), major ETFs
  (broad-market, sector, style/asset-allocation), and custom watchlists (pasted
  tickers and/or CSV).
- **Benchmarks** are chosen independently of the trading universe: S&P 500 and
  Nasdaq-100 proxy/index data and custom tickers; Russell once licensing/coverage
  is confirmed.

Universe membership, tradability filters, strategy eligibility, ranking and
portfolio/risk constraints are separate stages. Use point-in-time membership
for index-based historical tests when available, never today's constituents
silently applied to history, and disclose when a provider cannot supply a
survivorship-aware universe.

## V1 User Experience

A normal customer needs no Python, terminal, Docker, or ML knowledge:
install → configure a market-data key or local dataset → download, validate and
cache data → choose universe and strategy/model → scan, backtest, validate. The
primary workflow is **discover → understand → test → validate → assess
risk/size → save evidence**, satisfying PR-07 to PR-12, with advanced detail in
drill-downs. It should feel like a research workstation, not a set of scripts.

## Core V1 Product Areas

Every strategy, ML ranking and portfolio decision flows through one pipeline:

```text
Universe → Tradability → Features → Strategy / Alpha Model → Score / Rank
  → Entry/Exit Rules → Risk Engine → Sizing → Portfolio
```

| Area | V1 scope | PRs |
| --- | --- | --- |
| Data Sources & Data Health | Provider credentials, local CSV/Parquet import, download/cache with update status, missing/invalid-data detection, adjustment/source metadata, cache management, provenance for saved runs. | 01, 13 |
| Universe Manager | Built-in universes with date-aware membership where supported, custom watchlists, tradability filters (price, average volume, dollar volume, history), sector/industry filters when metadata is reliable. | 01, 07 |
| Strategy / Alpha Engine | Configurable deterministic strategies and ML-assisted ranking; the no-code visual builder (universe, filters, indicators, entry/exit, ranking, sizing, risk, parameters, save/duplicate/import/export) whose saved definition drives scanning, backtesting and validation. | 05, 10, 12 |
| Market Scanner | The same definitions as the backtester on the latest data, plus historical scans with outcomes; rank/score, generating strategy/model, explanation, risk context, reason qualified or rejected. | 07, 08 |
| Portfolio Backtester | Shared cash and simultaneous positions; next-session execution; fees and slippage; stop/target/trailing/time exits; rejected orders; sizing and constraints; benchmark; complete ledger; deterministic results. | 02 |
| Risk Engine | Risk per trade, position size and count, exposure, cash reserve, sector/concentration, liquidity, drawdown-based reduction; every decision logged and explainable. | 03 |
| Money / Position Management | Fixed allocation, equal weighting, fixed-fractional risk, ATR/volatility sizing. Volatility targeting, risk parity or Kelly-derived methods may be researched later. | 04 |
| Analytics | The PR-09 metrics plus trade count, drawdown series, rolling performance where useful, and VaR/CVaR only if clearly defined and caveated. | 09 |
| Validation & Robustness | In-sample/OOS, walk-forward, parameter sensitivity, cost/slippage stress, period/regime and universe comparisons, simple baselines, plain-language warnings, Monte Carlo/resampling with stated question and assumptions. | 06 |
| Trade Explorer | Every trade: signal and execution times, price, quantity, reasons, risk and sizing calculation, stop/target, exit, costs, P&L, strategy/model/configuration version. | 02, 08 |
| Saved Research | Local strategy, risk/sizing and data-source configurations (excluding secrets), runs, model metadata, analytics and provenance manifests. | 13, 14 |
| Export / Reporting | Trade ledger CSV, results CSV/XLSX where useful, a professional backtest report, the provenance manifest. | 09, 13 |

## Quant Algorithm / Model Plan

Do not begin by predicting exact future prices. The primary framing is:

> Given information available at date `t`, rank eligible stocks by expected opportunity over a defined forward horizon, then apply deterministic strategy, risk, and money-management rules.

The alpha layer proposes/ranks opportunities; the portfolio/risk layer decides
what can be traded.

- **Horizons:** 5, 10 and 20 trading days; separate production models per
  horizon only if research shows value.
- **Targets:** forward raw return; forward excess return vs market/sector;
  cross-sectional forward-return rank; target-before-stop/barrier outcome.
  Cross-sectional rank and excess-return targets fit the scanner design best.
- **Features:** 1–120-day returns, momentum acceleration, distance from recent
  highs/lows, relative strength; moving-average relationships, slopes and
  breakouts; ATR, realized/downside volatility and volatility regimes; relative
  volume, volume trend, dollar volume and liquidity proxies; cross-sectional
  ranks, market- and sector-relative momentum, sector strength, breadth and
  market regime. Later: point-in-time fundamentals, earnings/analyst revisions,
  news/event features.
- **Tournament, in order:** rule-based baseline; linear/logistic/Ridge/Elastic
  Net; LightGBM, XGBoost, CatBoost; MLP; LSTM/GRU, with Transformer/TCN only if
  justified; ensembles only when components add complementary signal.
  Reinforcement learning is not a V1 requirement.
- **Selection:** never on total historical return alone. Weigh rank IC,
  calibration for real probabilities, CAGR, Sharpe/Sortino/Calmar, drawdown,
  turnover and cost sensitivity, expectancy/profit factor, stability across
  walk-forward periods, universes and regimes, parameter sensitivity, cost to
  train/run, and explainability. Prefer the simpler model when performance is comparable.

Qlib may accelerate research, but the production runtime stays under our
control unless a deliberate decision is made otherwise.

## Training and Validation Data

Use high-quality data from our own development/research subscriptions and train
on a locally cached, versioned dataset; the provider API is only a source of raw
observations. Desired history is roughly **10–20 years of clean daily U.S.
equity data**, depending on provider coverage and point-in-time quality, with
OHLCV, adjusted/unadjusted prices, splits, dividends, ticker changes,
listings/delistings, point-in-time membership, benchmark/ETF data and reliable
sector metadata where available.

```text
Provider download → immutable raw store → normalization/quality checks → point-in-time dataset → features
  → chronological training/validation → walk-forward predictions → portfolio backtest → stress tests → candidate
```

Never randomly shuffle the time series. At each historical prediction only data
available at that timestamp may feed features, universe membership,
normalization, training, parameter selection, and fundamentals/events when
introduced. Keep a genuinely untouched final test period during research.

## Cost-Conscious Research Data Workflow

Legally permitted free/free-tier data may be used to build the engine,
features, strategies, ML workflow, tests and exploratory backtests, and to
research V1 ETF built-ins. Its results are never presented as validated or
independently verified; evidence packs state the provider and its limitations.

Before reference numbers for a built-in are published, the project owner
decides whether an independent-provider cross-check is feasible; the evidence
pack records the decision, its reason and any result
([the evidence standard](docs/STRATEGY_EVIDENCE.md), Section 5). Another vendor
over the same dates is a data cross-check, not a new temporal holdout; a
material difference is a data-quality finding to investigate and disclose.

The V1 ML model is trained on Tiingo data from our own key. Its ETF universe,
features and methodology are frozen and registered before training, and it
follows the same cross-check decision as the rule plans. Never redistribute
provider datasets unless licensing explicitly permits it.

## Data Provider Strategy

All market data passes through a provider-neutral, normalized interface. Do not
hard-code commercial assumptions about a vendor; pricing, entitlements,
coverage and licensing change.

**V1 tester release (decided 2026-10-11):** Tiingo is the only customer-facing
provider, used with the user's own free-tier key and cached locally. Tiingo's
developer documentation states that software where users bring their own token
and no data is distributed needs no licence. Alpaca daily data remains internal
development and research data; confirming Alpaca's terms for commercial
research use is an open action item.

After the tester release:

- **EODHD** — candidate adapter (EOD prices, corporate actions, bulk access,
  historical index components at a customer-accessible price). Verify before
  locking: S&P 500/Nasdaq-100 coverage and history, Russell 1000
  availability/licensing, delistings and ticker changes, adjustment semantics,
  commercial/BYO-key terms, throughput.
- **Local CSV/Parquet import** — required in commercial V1, so users with
  existing data are not locked to one vendor.
- **Alpaca** for a later paper/live brokerage roadmap; **Massive/Polygon** if
  richer real-time/intraday data is needed.
- **Survivorship-aware point-in-time data** for later stock research. Norgate's
  public FAQ excludes business/commercial use, so it is paused pending an
  applicable agreement; EODHD and Massive are unqualified alternatives.
  Quality, coverage, licensing and cost review remain required.

Normal V1 use requires **at most one market-data API key**. The core product
needs no OpenAI/Anthropic API, hosted inference, GPU cloud, brokerage
credentials, news or fundamentals API. Official trained models run locally.

## Bundled Benchmark Dataset

A reference dataset may ship only with confirmed redistribution rights, for
immediate demonstration, regression fixtures and exploration before a provider
is configured. Customers must still be able to rerun supported strategies on
their own provider/local data.

## Backtest Provenance

Every saved run/report carries a manifest: application version; strategy
name/version; model name/version/hash; strategy/config hash; risk/sizing
configuration; data provider; retrieval timestamp; dataset version/hash where
practical; universe and point-in-time policy; period; adjustment policy; signal
and execution timing; slippage; commission/fees; benchmark; engine
version/hash. This is a product feature, not debugging metadata. See
[reproducibility](docs/REPRODUCIBILITY.md).

## Reference Strategies

V1 must ship **at least three distinct rule-based built-ins (target four) plus
the ML-ranked rotation**, ready to configure, scan, backtest, validate and inspect
with explainable risk/sizing defaults. [The evidence standard](docs/STRATEGY_EVIDENCE.md),
adopted 2026-10-08, is the qualification and delivery contract and governs
wherever this document disagrees. A built-in needs an economic rationale with
two independent published sources; fixed rules registered before the run, each
parameter from a named publication; a verified implementation (hand-calculated
and no-look-ahead tests, byte-for-byte reproduction); a complete evidence pack
(three cost levels, bootstrap uncertainty, deflated Sharpe ratio with the
disclosed trial count, period/drawdown breakdowns, sensitivity, primary, SPY,
60/40 and equal-weight references, T-bill cash yield, forward signal journal,
reproduction command); one of the V1 roles in the standard, not shared; and a
plain-language limitations page.

There is **no return, Sharpe or benchmark-beating threshold**: honest evidence
that a strategy underperformed in some regime is a deliverable. V1 built-ins
are ETF-based (see **V1 Tester Release**). Survivor-selected stock panels are
never evidence for a built-in; stock strategies need survivorship-free
point-in-time data. Every study, including failures, is recorded in
[the research ledger](docs/RESEARCH_LEDGER.md). Do not fill the quota with
parameter variants, change a registered configuration after seeing results, or
relabel inspected history as untouched.

## Production Models

Official production models are trained by us, packaged with the application
and used for inference only: latest data → production features → packaged
model → scores/ranks → strategy rules → risk and sizing. The training pipeline
is required in V1 Developer/Source; a Desktop retraining UI is optional and may
be deferred without deferring that pipeline. Ordinary Desktop use never
requires training. Custom models, if supported, stay separate from official
ones and are evaluated automatically before use.

## UI Direction

**Trader/Analyst rule:** every screen is simple by default (Trader view: plain
language, money, worst falls) with full detail on demand (Analyst view:
statistics, settings, manifests).

The tester release is a local web app: a Python server on the user's machine,
the browser as UI, and an explicit API boundary to the engine. For the
commercial desktop shell, React + TypeScript in a lightweight shell such as
Tauri, with the local Python engine and local DuckDB/Parquet storage, remains
the direction to validate with a packaging spike before large UI investment.

Primary screens follow the product areas: Dashboard (data health, recent runs,
quick actions), Scanner, Strategy/Model, Backtest, Results, Validation, Trade
Explorer, Data Sources, and Settings/Saved Research.

## Platform and Packaging

- **V1:** Windows 10/11 x64 is primary and fully tested; Linux x86-64 is
  supported. The tester release ships a Windows build first, built by GitHub Actions.
- **Deferred:** macOS; a hosted cloud/browser SaaS edition; mobile.

Users never install Python or manage environments. Targets: a signed Windows
installer when commercially ready and a packaged Linux application (AppImage or
equivalent), with the engine and model dependencies bundled reproducibly.

## Security / Secrets

- Store API credentials in OS-appropriate secure storage where practical.
- Never write API keys into logs, reports, exported configs, telemetry, or provenance manifests.
- The core product never requires sending portfolio/research data to our servers.
- Avoid unnecessary telemetry; if introduced later, make it explicit and privacy-conscious.

## Reliability and Error Handling

Handle gracefully: invalid/expired keys, provider rate limits/outages, missing
symbols/history, incomplete membership, malformed files, stale cache,
incompatible model/feature schema, corrupted saved runs, insufficient history,
and insufficient cash/risk capacity. Users get actionable errors, not stack traces.

## Testing / Quality Bar

Required before sale: unit coverage of critical financial math; hand-verifiable
synthetic backtests; no-look-ahead/leakage tests; provider normalization and
corporate-action tests; deterministic regression/golden tests; cross-platform
numerical consistency; model/schema compatibility; realistic end-to-end
backtests; independent-provider comparison on selected reference runs where the
project owner has decided it is feasible; installer/update/uninstall smoke tests
on supported OSes. Any material discrepancy in financial results blocks release
until understood.

## V1 Non-Goals

Unless the plan is explicitly changed: guaranteed-return or “winning stock”
prediction; live automated trading; broker order execution; options, futures,
forex or crypto; intraday/tick backtesting; social-media sentiment; mandatory
news intelligence; LLM stock prediction; reinforcement-learning production
strategies; cloud accounts/SaaS backend; mobile; macOS; elaborate DRM;
source code in the standard product.

## Likely Post-V1 Roadmap

By demonstrated demand and research value: point-in-time fundamentals and
multi-factor models; earnings/analyst revisions; news/event classification with
optional LLM-assisted text structuring; richer retraining UX; model ensembles;
paper trading; broker integrations such as Alpaca/IBKR; real-time/intraday data;
more universes/markets; macOS; optional Docker/self-hosted deployment.

## Initial Development Sequence

The agreed build roadmap is **1. Market-data layer → 2. Backtester → 3. Risk/money management → 4. Strategies → 5. Validate strategies → 6. ML models → 7. Scanner/analytics → 8. Desktop UI → 9. Packaging/licensing/website**.

Each stage needs a usable, tested foundation before the next depends on it.
Tests, provenance, documentation and error handling accompany every stage;
accounting tests are not deferred to Stage 5, nor numerical reporting to Stage
7. Small fixtures and scripted orders are engineering inputs, not production
strategies. Status and the tester-release build order are in
[the roadmap](docs/ROADMAP.md).

1. **Market-data layer** — provider-neutral price, identity, calendar and
   corporate-action contracts; immutable raw/normalized snapshots with hashes
   and retrieval metadata; local imports and provider adapters; data-health
   checks with explicit limits; point-in-time universe and benchmark
   interfaces. Contracts: [data layer](docs/DATA_LAYER.md),
   [data integration](docs/DATA_INTEGRATION.md), [universes](docs/UNIVERSES.md).
2. **Backtester** — signal vs next-session execution timing; reuse of existing
   engines evaluated against hand-calculated conformance fixtures; shared-cash
   accounting, concurrent positions, costs and rejected orders; explicit
   corporate actions, missing data and end-of-test positions; retained orders,
   fills, cash movements and manifests; verified by synthetic ledgers and
   causality tests before research use. Basic cash accounting and order
   affordability live here; investment-risk controls and sizing are Stage 3.
   Contract: [backtester](docs/BACKTESTER.md).
3. **Risk/money management** — fixed allocation, fixed-fractional and
   ATR/volatility sizing; position, exposure, concentration, liquidity, reserve
   and drawdown controls; recorded rejection reasons; verified interaction of
   sizing, cash, stops and execution. Contract: [risk management](docs/RISK_MANAGEMENT.md).
4. **Strategies** — deterministic features and rule-based approaches; explicit
   ranking, entry/exit and rebalancing contracts; registered configurations and
   benchmarks; common interfaces for ML scores and the scanner.
   Contract: [strategies](docs/STRATEGIES.md).
5. **Validate strategies** — registrations, study tags and the research ledger
   for every study; complete evidence packs for built-ins; walk-forward,
   sensitivity, regime and benchmark tools for users; forward signal journals
   ([example](docs/FORWARD_SHADOW.md)). Contract: [validation](docs/VALIDATION.md).
6. **ML models** — leakage-safe feature/label, training and chronological
   prediction pipelines; linear baselines, bounded tree models, neural
   candidates only when justified; every model compared through the verified
   simulator and Stage 5; production artifacts chosen only from documented OOS evidence.
7. **Scanner/analytics** — scanner on the same strategy/model/risk definitions
   as research; full analytics, benchmarks, Trade Explorer, validation reports
   and exports; saved research and explanations from recorded decisions.
8. **Desktop UI** — application shell (a local web app for the tester release)
   with local engine integration; setup, scanner, configuration, backtest,
   validation and saved-research workflows; progressive disclosure with visible
   assumptions; observed usability, packaging and failure-state checks.
9. **Packaging/licensing/website** — reproducible Windows/Linux installers and
   smoke tests; Evaluation, Desktop and Developer/Source delivery with the
   training pipeline; secure credentials, licensing/EULA, permitted reference
   artifacts and release docs; website, purchase/download flow, private
   distribution and entitlements; final release-gate validation with the first
   customer/design partner.

## Release Gate for Commercial V1

V1 is ready to sell only when:

1. supported data sources work reliably and licensing is understood;
2. at least three distinct built-in strategies (target four) meet [the evidence standard](docs/STRATEGY_EVIDENCE.md), each with its complete evidence pack and limitations page, and supplied models meet PR-10 and Stage 6 (leakage-safe chronological fitting, baseline comparisons, documented out-of-sample evidence);
3. backtesting semantics are explicit and covered by tests;
4. risk/sizing/portfolio accounting are verified;
5. results are reproducible and provenance is recorded;
6. the customer can inspect every trade and major assumption;
7. Windows installation is straightforward and Linux support meets the declared support level;
8. no mandatory developer tooling is required by the customer;
9. failures produce useful errors rather than crashes/stack traces;
10. documentation explains setup, data assumptions, strategy/model behavior, backtesting assumptions, metrics, and limitations;
11. each built-in's evidence pack records the project owner's independent-provider cross-check decision, its reason and any result; supplied models have been checked against an independent data source where feasible;
12. the product is something we would deliver unchanged at its core to customer #2 rather than rebuild after customer #1;
13. PR-01 through PR-15 have acceptance evidence for the declared supported scope, including observed no-code strategy creation and the discover/test/validate/risk workflow; requirements are not marked complete solely because engine tests pass.
