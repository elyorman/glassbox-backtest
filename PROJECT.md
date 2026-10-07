# PROJECT.md

## Project Summary

Build a commercial, local-first **Quantitative Trading Research & Risk Platform for U.S. equities and ETFs**.

The product helps a trader make systematic, reproducible decisions under uncertainty. It does **not** claim to predict markets with certainty. Its value is the disciplined combination of:

- quantitative alpha/strategy research;
- market scanning and cross-sectional ranking;
- portfolio-aware backtesting;
- out-of-sample and robustness validation;
- deterministic risk management;
- money/position management;
- transparent analytics and trade-level auditability.

V1 is the first paid production release, not an MVP/demo.

## Product Positioning and Differentiation

The central product promise is:

> **A serious quantitative stock research platform that gives traders institutional-style validation and risk discipline without requiring them to code or trust a black box.**

The customer-facing message is:

> **Find better opportunities. Test them properly. Understand the risk. Make more disciplined decisions.**

The product combines stock discovery, realistic portfolio testing, robustness
evaluation, risk controls, understandable position sizing, explainable
strategies/ML rankings, local research storage and a one-time software purchase.
Market it as a quantitative stock research platform; ML is a supporting
capability, not the product identity or a promise of market prediction.

The intended gap is between retail simplicity and quantitative rigor. Reasons
to choose the finished product should be:

- easier to use than assembling and maintaining a Python quant stack;
- more rigorous than a simple signal backtest, with shared portfolio cash,
  executable timing, explicit costs, corporate actions and rejected orders;
- validation-first, with chronological OOS/walk-forward, parameter sensitivity,
  cost stress and regime checks explained in plain language;
- stock discovery, testing, risk and sizing in one consistent workflow;
- 3–4 well-researched, validated built-in strategies and validated ML rankings with inspectable
  inputs, rules, scores and decisions;
- no-code rule-based strategy creation in Desktop;
- local-first research and private customer data, without recurring cloud lock-in;
- no mandatory software subscription; the purchased major version is perpetual;
- source access, extension capability and the model-training pipeline in
  Developer/Source Edition.

These are product commitments to demonstrate through acceptance evidence and
user evaluation, not verified claims of superiority over every competitor.
"Institutional-style" refers to validation/accounting/risk discipline; it does
not promise institutional data, execution access, certification or returns.
"Explainable" means users can inspect the basis, scope and limitations of an
output; model explanations are not proof of causality or predictive certainty.
Third-party data may require its own subscription, and future major software
versions may be optional paid upgrades under the commercial policy below.

## Product Philosophy

There is no “magic” algorithm that knows what happens next. The system should reduce avoidable decision errors by making rules explicit, testable, repeatable, and measurable.

The application should answer questions such as:

- What exactly caused this candidate to rank highly?
- What would the strategy have done historically using only information available at the time?
- How did it perform after realistic execution assumptions and costs?
- What was the worst drawdown and when did it fail?
- Does the result survive different periods, universes, parameters, and data providers?
- What happens if risk per trade, stops, slippage, or portfolio constraints change?
- How does it compare with a relevant benchmark and with simpler strategies?

## Product Requirements and Acceptance Contract

Confirmed with the user on **2026-10-03**. The following 15 groups are the
product acceptance contract. The subsystem sections below detail how to deliver
them; the development-stage notes describe current progress, not completion of
these requirements. Every substantial feature must identify the requirement
IDs it supports and the evidence that demonstrates its usefulness and
correctness. Features that do not improve usefulness, trust, usability or
decision quality should be questioned.

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

V1 must ship **3–4 distinct, well-researched, validated built-in strategies**
(minimum three; target four), usable without coding. The qualification and
delivery contract is specified under **Reference Strategies** below. Research
tools and user-created strategies do not substitute for this built-in offering.

A profitable historical backtest alone does not establish usefulness. Evaluate
the economic/behavioral hypothesis, expectancy after costs, CAGR/annual return,
drawdown, Sharpe/Sortino/Calmar, adequate trade count, period/universe/regime
stability, small parameter changes, OOS results and appropriate benchmarks.
There is no universal 20% CAGR pass requirement. CAGR around 15–20%+, drawdown
around 20–25% or lower, Sharpe around/above 1 and Calmar around/above 1 are
illustrative research targets only; they are neither promises nor automatic
pass/fail gates. Robustness has priority over maximizing historical return.

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
| PR-05, PR-06 | 4–5: Strategies/validation | Registered hypotheses, retained failures, honest OOS/walk-forward/stress evidence and understandable decisions. |
| PR-10 | 6: ML | Leakage-safe chronological fitting, baseline comparisons, net portfolio evidence and model provenance. |
| PR-07, PR-08, PR-09 | 7: Scanner/analytics; earlier engine support | Current/historical definition parity, reconciled metrics and inspectable candidate/trade explanations. |
| PR-11, PR-12 | 8: Desktop UI; strategy contracts from Stage 4 | Observed no-code install/configure/build/scan/test/validate/risk tasks and round-trip saved strategies. |
| PR-13, PR-14 | All stages | Reproducible runs, provenance/integrity tests and verified absence of research-data uploads. |
| PR-15 | All stages and 9: Release | Real-user usefulness/usability evidence and a supported requirement for each shipped feature. |

The nine-stage build order remains unchanged. This contract is not a claim
that the current CLI, ETF experiments or test suite already deliver the complete
stock-research desktop product. Engine correctness, empirical strategy/model
qualification and customer-facing usability are separate evidence requirements.

## Commercial Model

The product is sold primarily as **perpetual desktop software**, not SaaS. The business model deliberately separates ordinary use, source access, and commercial redistribution.

### Desktop Edition

The standard paid product includes:

- packaged Windows/Linux application;
- official production strategies/model artifacts;
- scanner, strategy configuration/builder, backtesting, validation, risk, sizing, analytics, Trade Explorer, persistence, and reporting;
- supported data-provider adapters and local CSV/Parquet import;
- documentation;
- a perpetual license to the purchased major version under the final EULA.

Source code is **not** included. Third-party market data is also not bundled unless redistribution rights are explicitly secured. Customers normally bring their own API credentials/data.

**Current pricing hypothesis:** $599 normal price; **$399 Early Bird price while the shared Founding Customer pool remains open**. The storefront should show the normal price alongside the current Early Bird price. These numbers remain market-test hypotheses and may change before launch; pricing belongs in commercial configuration, not quant logic.

### Developer / Source Edition

Offer a separate Source Edition for technical users who value inspectability, extension, and private/internal modification. The intended package includes the Desktop product plus application/platform source code, build instructions, tests, architecture documentation, and extension documentation.

**Current pricing hypothesis:** $2,499 normal price; **$1,499 Early Bird price while the shared Founding Customer pool remains open**. The storefront should show both prices clearly. Pricing remains configurable commercial metadata.

The final source license should permit the agreed internal/private use and modification while **not** granting redistribution, sublicensing, resale, OEM, or competing commercial-product rights. Commercial/OEM redistribution is negotiated separately.

The **production-model training pipeline is included in the V1 Developer/Source Edition**, enabling technical buyers to train and modify their own models. Proprietary third-party training datasets are not included unless redistribution rights are explicitly secured. Internal research artifacts may be packaged only when deliberately approved for that edition.

### Founding Customer / Early Bird Offer

The Early Bird offer uses **one shared pool across Desktop and Developer/Source**: the first **50 unique paying customers** qualify, regardless of which paid edition they buy. A customer purchasing multiple editions/licenses still counts once toward the 50-customer pool.

The storefront should display the offer live, for example `34 / 50 claimed`, together with the struck-through/reference normal price and current Early Bird price. The counter advances only for completed qualifying purchases, not trial downloads, email registrations, or abandoned checkouts. When customer #50 qualifies, Early Bird pricing ends rather than resetting into another artificial scarcity campaign.

The count and prices are commercial configuration/state, not quant-engine logic.

### OEM / Commercial Redistribution

No fixed public price initially. Handle commercial embedding, redistribution, white-labeling, fund/company deployment beyond standard terms, or OEM rights as negotiated agreements.

### Evaluation Edition

The evaluation experience is a core sales mechanism, especially for skeptical/technical traders. It must allow the prospect to verify the product rather than merely view a demo.

**Settled requirements:**

- **14 days from first activation**;
- same application/codebase and same Desktop capabilities as the paid Desktop Edition;
- no artificial limits on tickers, backtest period, trade count, supplied strategies/models, strategy configuration, validation, Trade Explorer, or exports;
- supports the prospect's own market-data API credentials and local datasets;
- all local projects, cached data, configurations, and prior results survive expiration;
- purchase converts/unlocks the existing installation without requiring reinstall or loss of work;
- evaluation is non-commercial under the final license terms.

After expiry the application should stop new research execution (exact expired/read-only UX to be finalized) while preserving the user's work. Trial enforcement should be reasonable but must not become an elaborate DRM project.

A verification/reference project and evaluation checklist should ship with the product so a prospect can reproduce a known backtest, inspect trades, alter costs/slippage/stops, test difficult periods, run walk-forward/OOS analysis, connect their own data, and independently recalculate selected P&L results.

### Updates & Major Versions

Do **not** promise “12 updates,” monthly releases, lifetime updates, or indefinite support.

The intended policy is:

- the purchased major version is perpetual and does not expire;
- maintenance/bug-fix/minor releases for that major version are included while that major version remains supported;
- future major versions may be optional paid upgrades;
- releasing V2 must not remotely disable V1;
- support lifecycle and upgrade pricing must be published before broad public sale.

### V1 Editions & Distribution

V1 must be commercially deliverable in **three forms at launch**: Evaluation, Desktop, and Developer/Source. Customer #1 may purchase either paid edition; Developer/Source must therefore be genuinely shippable rather than a future promise.

V1 should also include a lightweight public download/storefront experience. Preferred architecture:

- **Vercel**: public product/pricing/download frontend;
- **Supabase**: verified-email flow, paid customer accounts, license/entitlement/purchase metadata only;
- **Cloudflare R2**: private object storage for Windows/Linux installers, release artifacts, and protected Developer/Source archives;
- **customer computer only**: market data, API credentials, portfolios, positions, strategies, backtests, trade history, models/model inputs, research projects, caches, and other trading/research data.

Customer trading/research data must **never** be uploaded to or stored in Supabase, R2, Vercel, or another product backend. This is a product/privacy invariant, not merely a V1 shortcut.

Evaluation download flow: visitor clicks Download Evaluation → supplies an email → verifies the email → receives/accesses a short-lived authorized download → installs the same Desktop application → 14-day evaluation begins on first activation. No full account is required merely to evaluate.

Paid Desktop/Developer flow: payment and email establish the customer's account/entitlement; authenticated access provides eligible installers/source packages, license information, documentation, and release history. Paid accounts exist for software ownership/distribution, not for storing trading data.

Release buckets should remain private; downloads should use short-lived/signed authorization rather than permanent public object URLs. A sophisticated automatic updater is not required initially; the application may check for an eligible newer release and direct the customer to the authenticated download page.

For customer #1, manual delivery/payment/license issuance remains an acceptable fallback if the storefront is not ready, but the lightweight storefront/distribution path is part of the V1 product target.

Custom strategy implementation, custom models, data-provider adapters, broker integrations, and related professional work are separate paid services rather than entitlements of the base Desktop license.

## Target Customer

Primary V1 customer profile:

- serious retail/professional-adjacent stock trader or investor who should not
  need coding or quantitative-finance expertise;
- understands that backtests do not guarantee future performance;
- wants systematic research rather than “AI stock picks”;
- values inspectability, configuration, robustness, and risk controls;
- may already have a market-data subscription or historical dataset.

Developer/Source additionally serves technical users who want source access,
custom extensions and model training; those skills are not a Desktop prerequisite.

The first customer is also a useful design partner, but receives the same core commercial product intended for subsequent customers rather than a one-off custom script.

## V1 Asset Coverage

### Asset class

- U.S. listed equities
- major U.S.-accessible ETFs

### Frequency

- daily bars

Intraday/tick data is explicitly deferred.

### Built-in universes

V1 should support:

1. **S&P 500** — primary reference large-cap universe.
2. **Nasdaq-100** — concentrated growth/technology-heavy universe.
3. **Russell 1000** — broader large/mid-cap opportunity universe, subject to data/licensing feasibility.
4. **Major ETFs** — broad-market, sector, style/asset-allocation instruments as appropriate.
5. **Custom universe/watchlist** — paste tickers and/or import CSV.

Universe selection and tradability filters are separate concepts.

Example flow:

```text
Russell 1000 point-in-time membership
              ↓
Tradability filters
(price / volume / dollar volume / history)
              ↓
Strategy/model eligibility
              ↓
Cross-sectional ranking
              ↓
Portfolio/risk constraints
              ↓
Orders/positions
```

### Historical membership

For index-based historical tests, use point-in-time membership when available. Never silently use today's constituents throughout history.

If a provider cannot supply a survivorship-aware universe, the UI/report must clearly disclose the limitation.

### Benchmarks

Benchmark is selected independently of trading universe. Initial benchmark options should include:

- S&P 500 proxy/index data;
- Nasdaq-100 proxy/index data;
- custom benchmark ticker/data where supported.

Russell benchmark support can be added when licensing/data coverage is confirmed.

## V1 User Experience

A normal customer should not need Python, a terminal, Docker, or ML knowledge.

Expected onboarding:

```text
Install application
      ↓
Launch
      ↓
Configure market-data API key OR local dataset
      ↓
Download/validate/cache data
      ↓
Choose universe + strategy/model
      ↓
Scan / backtest / validate
```

The product should feel like a quantitative research workstation rather than a collection of scripts.

The primary workflow is **discover → understand → test → validate → assess
risk/size → save evidence**. User-facing decisions and explanations must satisfy
PR-07 through PR-12; advanced details are available through drill-down.

## Core V1 Product Areas

### 1. Data Sources & Data Health

Capabilities:

- configure supported market-data provider credentials;
- import local CSV/Parquet datasets;
- download/cache historical and current daily data;
- display download/update status;
- detect missing/invalid data;
- expose adjustment/source metadata;
- manage local cache/storage;
- show data provenance for saved runs.

### 2. Universe Manager

Capabilities:

- choose built-in universe;
- choose date-aware historical membership where supported;
- create/import custom watchlists;
- apply tradability filters such as minimum price, average daily volume, dollar volume, and minimum trading history;
- optionally filter by sector/industry when reliable metadata exists.

### 3. Strategy / Alpha Engine

The engine must support both deterministic strategies and ML-assisted ranking.

Conceptual pipeline:

```text
Universe
  ↓
Tradability
  ↓
Features
  ↓
Strategy / Alpha Model
  ↓
Candidate Score / Rank
  ↓
Entry/Exit Rules
  ↓
Risk Engine
  ↓
Sizing
  ↓
Portfolio
```

Strategies should be configurable rather than hard-coded into UI logic.

Desktop includes the PR-12 no-code visual strategy builder: supported universe,
filter, indicator, entry/exit, ranking, sizing and risk components; parameter
configuration; and save/duplicate/import/export. The saved strategy definition
is shared by current/historical scanning, backtesting and validation. Arbitrary
code extensions are a Developer/Source capability, not required for Desktop use.

### 4. Market Scanner

Run the same production strategy/model definitions used by the backtester against the latest available data.

Also support historical scans with dated universe/data inputs and subsequent
outcome inspection, preserving the same supported filter/strategy definition.

Scanner output should support:

- symbol;
- rank/score;
- strategy/model that generated it;
- relevant feature/condition explanation;
- risk/volatility context;
- reason a candidate qualified or was rejected;
- drill-down into historical behavior/backtest where practical.

Do not represent an arbitrary ranking score as a probability.

### 5. Portfolio Backtester

The backtester is a first-class product, not a charting afterthought.

Required behavior:

- portfolio-level cash and positions;
- simultaneous positions;
- explicit signal vs execution timing;
- next-session execution semantics for daily strategies;
- configurable fees and slippage;
- stop/target/trailing/time-based exits;
- rejected orders and insufficient-capital handling;
- position sizing and portfolio constraints;
- benchmark comparison;
- complete trade/order ledger;
- deterministic reproducibility given identical inputs.

### 6. Risk Engine

Initial controls:

- maximum risk per trade;
- maximum position size;
- maximum positions;
- maximum portfolio exposure;
- cash reserve;
- sector/concentration limits;
- liquidity constraints;
- drawdown-based risk reduction/stop rules where configured.

Risk decisions should be logged and explainable.

### 7. Money / Position Management

V1 methods:

- fixed allocation;
- equal weighting;
- fixed-fractional risk sizing;
- ATR/volatility-based sizing.

Future candidates such as volatility targeting, risk parity, or Kelly-derived methods may be researched later.

### 8. Analytics

At minimum:

**Return**
- total return;
- CAGR;
- annual/monthly returns.

**Risk**
- maximum drawdown;
- average drawdown with its averaging convention documented;
- drawdown series;
- realized volatility;
- downside deviation;
- VaR/CVaR only if clearly defined and appropriately caveated.

**Risk-adjusted**
- Sharpe;
- Sortino;
- Calmar.

**Trade statistics**
- win/loss rate;
- average winner/loser;
- payoff ratio;
- expectancy;
- profit factor;
- largest winner/loss;
- average holding period;
- consecutive wins/losses;
- trade count.

**Portfolio**
- exposure;
- turnover;
- cash utilization;
- concentration.

**Comparison**
- benchmark return/risk comparison;
- rolling performance where useful.

### 9. Validation & Robustness

V1 should allow the user to challenge a strategy rather than merely admire its equity curve.

Required capabilities:

- in-sample/out-of-sample separation;
- chronological validation;
- walk-forward evaluation;
- parameter sensitivity;
- slippage/transaction-cost stress testing;
- performance by time period/regime;
- comparison across supported universes where meaningful;
- comparison with simple baselines/benchmark;
- plain-language robustness warnings, including insufficient and inconclusive evidence;
- Monte Carlo/resampling analysis where useful, with the question, method and assumptions stated.

### 10. Trade Explorer

Every historical trade should be inspectable.

Show at least:

- signal date/time;
- execution date/time;
- entry price and quantity;
- entry reason/features/conditions;
- risk and sizing calculation;
- stop/target if applicable;
- exit date/price;
- exit reason;
- costs/slippage;
- realized P&L;
- strategy/model/configuration version.

### 11. Saved Research

Persist locally:

- strategy configurations;
- risk/sizing configurations;
- data-source configuration excluding secrets where inappropriate;
- saved backtest runs;
- model metadata;
- analytics results;
- provenance manifests.

### 12. Export / Reporting

Support exporting at least:

- trade ledger to CSV;
- analytics/results to CSV and/or XLSX where useful;
- a professional backtest report format;
- reproducibility/provenance manifest.

Exact report format can be finalized during UI/report design.

## Quant Algorithm / Model Plan

### Core framing

Do not begin by trying to predict exact future stock prices.

The primary research framing is:

> Given information available at date `t`, rank eligible stocks by expected opportunity over a defined forward horizon, then apply deterministic strategy, risk, and money-management rules.

The alpha layer proposes/ranks opportunities. The portfolio/risk layer decides what can actually be traded.

### Candidate horizons

Research at least:

- 5 trading days;
- 10 trading days;
- 20 trading days.

Do not assume all horizons require separate production models until research demonstrates value.

### Candidate targets

Test several formulations:

1. forward raw return;
2. forward excess return vs market/sector;
3. cross-sectional forward-return rank;
4. target-before-stop/barrier outcome within a fixed horizon.

Cross-sectional ranking and excess-return targets are especially aligned with the scanner/product design.

### Feature families

Initial price-derived feature research should include:

**Momentum/returns**
- 1/5/20/60/120-day returns as appropriate;
- momentum acceleration;
- distance from recent highs/lows;
- relative strength.

**Trend**
- SMA/EMA relationships;
- distance from moving averages;
- trend slopes;
- breakout measures.

**Volatility/risk**
- ATR;
- realized volatility;
- downside volatility;
- volatility changes/regimes.

**Volume/liquidity**
- relative volume;
- volume trend;
- dollar volume;
- turnover/liquidity proxies where available.

**Cross-sectional/context**
- percentile/rank transformations;
- market-relative momentum;
- sector-relative momentum;
- sector strength;
- market breadth;
- market regime.

Later versions may add point-in-time fundamentals, earnings/analyst revisions, and news/event features.

### Model tournament

Do not select the production model based on aesthetics or complexity. Evaluate:

1. rule-based momentum/trend/volatility baseline;
2. linear/logistic/Ridge/Elastic Net;
3. LightGBM;
4. XGBoost;
5. CatBoost;
6. MLP;
7. LSTM/GRU and other temporal neural candidates;
8. Transformer/TCN-style candidates only if justified;
9. ensembles when components demonstrate complementary signal.

Qlib can accelerate research and provide reference implementations/benchmarks, but the final production runtime should remain under our control unless a deliberate decision is made otherwise.

Reinforcement learning is not a V1 requirement.

### Selection criteria

Do not choose a model solely on total historical return.

Evaluate:

- rank IC/predictive ranking quality where applicable;
- calibration for actual probabilistic outputs;
- CAGR;
- Sharpe/Sortino/Calmar;
- maximum drawdown;
- turnover and transaction-cost sensitivity;
- expectancy/profit factor;
- stability across walk-forward periods;
- stability across universes;
- regime robustness;
- parameter sensitivity;
- training/inference cost;
- explainability/operability.

A simpler model is preferred when performance is comparable and robustness/interpretability are better.

## Training and Validation Data

### Data source

Use high-quality historical market data obtained through our own development/research subscription(s). The API/provider is a source of raw observations; training should operate primarily on a locally cached, versioned dataset.

Initial desired history: approximately **10–20 years of clean daily U.S. equity data**, depending on provider coverage and point-in-time quality.

Required/desired raw fields and metadata:

- daily OHLCV;
- adjusted/unadjusted price information;
- splits;
- dividends;
- ticker changes;
- listing/delisting information when available;
- point-in-time universe membership;
- benchmark/index/ETF data;
- sector/industry metadata when reliable.

### Training workflow

```text
Provider download(s)
       ↓
Immutable raw store
       ↓
Normalization / quality checks
       ↓
Point-in-time research dataset
       ↓
Feature generation
       ↓
Chronological training/validation
       ↓
Walk-forward predictions
       ↓
Portfolio backtest
       ↓
Robustness / stress tests
       ↓
Production model candidate
```

### Leakage controls

Never randomly shuffle the entire time series into train/test sets.

Use chronological partitions and walk-forward evaluation. During each historical prediction, only data available at that timestamp may contribute to:

- features;
- universe membership;
- normalization/scaling;
- model training;
- parameter selection;
- fundamentals/events when those are later introduced.

Keep a genuinely untouched final test period during research.

### Independent data verification

Prefer validating final strategy/model behavior against a second provider/dataset before commercial release. Provider-to-provider results need not be numerically identical, but large discrepancies must be investigated.

## Cost-Conscious Research Data Workflow

During initial development, use legally permitted **free/free-tier historical data** to build the engine, feature pipeline, strategies, ML training workflow, automated tests, and exploratory backtests. Do not treat results from a free development dataset as final commercial evidence.

Once a strategy/model is promising, freeze the important methodology/configuration and obtain an inexpensive higher-quality paid dataset/provider (initial target roughly the low tens of dollars per month where suitable). Re-run the important experiments from scratch and, where feasible, cross-check with an independent provider. A material performance collapse across providers is a research/data-quality finding to investigate before shipping, not something to hide.

Preferred sequence: **free data → develop/train/backtest → freeze candidate methodology → paid/better independent data → re-test/validate → ship/reference results**. Customer-facing use remains BYO-provider/local-data oriented; we do not redistribute provider datasets unless licensing explicitly permits it.

## Data Provider Strategy

The application must abstract market-data providers behind a normalized interface.

### Internal research candidate

Point-in-time index membership, delisted securities, and survivorship-aware
historical testing remain priorities for internal research. Norgate was the
initial candidate, but its current public FAQ excludes business/commercial use;
that route is paused pending an applicable agreement. The 2026-10-03
[provider review](docs/INDEPENDENT_DATA_RETEST.md) proposes a conditional EODHD
pilot and Massive alternative for the frozen fixed-panel retest. Neither is
qualified for historical universes or this project's account by documentation
alone. Quality, coverage, licensing, and cost review remain required.

### Customer-facing Provider #1

**EODHD** is the leading first adapter candidate because it combines historical EOD data, corporate actions, bulk access, and historical index-component functionality at a customer-accessible price point.

Must verify before locking:

- exact S&P 500 coverage/history;
- exact Nasdaq-100 coverage/history;
- Russell 1000 availability/licensing;
- delisted securities/ticker-change behavior;
- adjustment semantics;
- commercial/BYO-key terms;
- API throughput/reliability.

### Customer-facing Provider #2

**Tiingo** is a strong second adapter candidate for high-quality EOD price/corporate-action data. Confirm entitlement and customer-use terms before launch.

### Future adapters

- **Alpaca** — strategically useful for a later paper/live brokerage roadmap.
- **Massive/Polygon** — potentially useful if future versions require richer real-time/intraday data.

### Local data

CSV/Parquet import is required in V1 so users with existing data can use the platform and the product is not locked to one vendor.

### Customer API requirements

Normal V1 usage should require **at most one market-data API account/key** for current data and provider-backed historical backtests.

The customer should not need:

- OpenAI/Anthropic API;
- hosted ML inference;
- GPU cloud services;
- brokerage credentials;
- news API;
- fundamentals API;

for the core V1 product.

Official trained models run locally.

## Bundled Benchmark Dataset

We may include a benchmark/reference dataset if redistribution/licensing permits it.

Purpose:

- allow immediate product demonstration/reproduction;
- provide known regression fixtures/reference results;
- let users explore the application before configuring an external provider.

The customer must also be able to rerun supported strategies using their own provider/local data to independently verify behavior.

Never bundle third-party data without confirmed redistribution rights.

## Backtest Provenance

Every saved run/report should include a provenance manifest similar to:

```text
Application version
Strategy name/version
Model name/version/hash
Strategy/config hash
Risk/sizing configuration
Data provider
Data retrieval timestamp
Dataset version/hash where practical
Universe
Point-in-time membership policy
Backtest period
Adjustment policy
Signal timing
Execution timing
Slippage
Commission/fees
Benchmark
Engine version/hash
```

This is a product feature, not merely debugging metadata.

## Reference Strategies

V1 must ship **3–4 distinct, well-researched, validated built-in strategies**
(minimum three; target four). They must be ready to configure, scan, backtest,
validate and inspect through Desktop, with explainable risk/sizing defaults.
This is a release requirement, not an optional collection of example scripts.

Exact strategies will be selected after research, but likely categories include:

- momentum/trend strategy;
- cross-sectional alpha/ranking strategy, potentially ML-assisted;
- ETF/sector rotation strategy.

Only ship strategies whose implementation and historical validation meet the project's quality bar.

Each included strategy needs a versioned research/usage dossier containing:

- primary research sources and a clear economic or behavioral hypothesis;
- exact entry/exit/ranking rules, supported universe, holding horizon and data requirements;
- defined execution/cost assumptions, risk controls and sizing calculations;
- predeclared objectives and appropriate benchmark/baseline comparisons;
- honest net-of-cost chronological OOS/walk-forward results, parameter/cost
  sensitivity, regime behavior and applicable universe checks;
- frozen methodology and a retest on qualified better independent data before
  production/reference claims, preserving prior searches and exposed periods;
- documented drawdowns, recovery, failure modes, limitations and intended use;
- reproducible configurations/results and an understandable user explanation.

The strategies must represent meaningfully different hypotheses or portfolio
roles. Nearby parameter settings, different sizing presets, benchmarks and cash
controls do not count as separate qualified strategies. An ML ranking may be
part of a strategy, but adding a model does not automatically create another
qualified strategy. A defensive strategy can have a different objective from
a return-seeking one; each must meet its own predeclared, benchmark-aware
acceptance criteria rather than an invented universal CAGR requirement.

The current ten rule recipes and the audited momentum/trend parents remain
research candidates; none is currently a qualified production strategy. If
fewer than three qualify, retain that finding and continue bounded, logged
research before release. Do not fill the quota with failed candidates, change
criteria after seeing results or relabel examined history as fresh validation.

## Production Models

Official production models are trained by us and packaged with the application.

Normal customer workflow is inference only:

```text
Latest market data
      ↓
Production feature pipeline
      ↓
Packaged production model
      ↓
Scores/ranks
      ↓
Strategy rules
      ↓
Risk + sizing
```

The model-training pipeline is required in V1 Developer/Source Edition.
An integrated Desktop retraining UI is optional advanced scope; ordinary
Desktop use must not require training a model. A richer retraining UI may be
deferred without deferring the Developer/Source training pipeline.

If included, custom models must be clearly separated from official production models and automatically evaluated before being promoted/used.

## UI Direction

Preferred architecture to evaluate:

- React + TypeScript frontend;
- lightweight cross-platform desktop shell such as Tauri;
- local Python quant engine;
- local DuckDB/Parquet storage;
- explicit IPC/API boundary between UI and engine.

The choice should be validated with a packaging spike before large UI investment.

### Primary screens

**Dashboard**
- data freshness/health;
- saved/recent runs;
- portfolio/research summary as appropriate;
- quick actions.

**Scanner**
- universe selection;
- strategy/model selection;
- ranked candidates;
- filters and explanations.

**Strategy / Model**
- strategy configuration;
- entry/exit rules;
- model/horizon selection;
- advanced model metadata.

**Backtest**
- period;
- universe;
- capital;
- execution assumptions;
- costs/slippage;
- risk/sizing;
- benchmark;
- run/save.

**Results**
- equity/drawdown;
- metrics;
- benchmark comparison;
- monthly/annual results;
- exposure/turnover.

**Validation**
- OOS/walk-forward;
- sensitivity;
- stress tests;
- regime/period analysis.

**Trade Explorer**
- complete trade ledger;
- drill-down into each decision.

**Data Sources**
- provider credentials;
- local imports;
- cache/storage;
- health/coverage/provenance.

**Settings / Saved Research**
- saved configurations/runs;
- export;
- application/system settings.

## Platform and Packaging

### V1

- Windows 10/11 x64: primary, fully tested release.
- Linux x86-64: supported release.

### Deferred

- macOS;
- cloud/browser SaaS edition;
- mobile.

Installation must not require users to install Python or manually manage environments.

Potential packaging targets:

- signed Windows installer when commercially ready;
- appropriate Linux packaged application/AppImage or equivalent.

The Python engine and model dependencies must be bundled reproducibly.

## Security / Secrets

- Store API credentials using OS-appropriate secure storage where practical.
- Never write API keys into logs, reports, exported configs, telemetry, or provenance manifests.
- Core product should not require sending portfolio/research data to our servers.
- Avoid unnecessary telemetry in V1; if introduced later, make it explicit and privacy-conscious.

## Reliability and Error Handling

Commercial V1 must handle gracefully:

- invalid/expired API key;
- provider rate limit/outage;
- missing symbol/history;
- incomplete universe membership;
- malformed local files;
- stale cache;
- incompatible model/feature schema;
- corrupted saved run/config;
- insufficient history for an indicator/model;
- insufficient cash/risk capacity for a simulated order.

Users should receive actionable errors, not raw stack traces.

## Testing / Quality Bar

Required before sale:

- unit coverage for critical financial math;
- hand-verifiable synthetic backtests;
- no-look-ahead/leakage tests;
- provider normalization integration tests;
- corporate-action tests;
- deterministic regression/golden tests;
- cross-platform numerical consistency checks;
- model/schema compatibility tests;
- realistic end-to-end backtest tests;
- independent data-provider comparison on selected reference runs;
- installer/update/uninstall smoke tests on supported OSes.

Any material discrepancy in financial results is a release blocker until understood.

## V1 Non-Goals

Do not allow these to expand V1 unless the project plan is explicitly changed:

- guaranteed-return or “winning stock” prediction;
- live automated trading;
- broker order execution;
- options;
- futures;
- forex;
- crypto;
- intraday/tick backtesting;
- social-media sentiment;
- mandatory news intelligence;
- LLM stock prediction;
- reinforcement-learning production strategy;
- cloud accounts/SaaS backend;
- mobile application;
- macOS support;
- elaborate DRM;
- source-code delivery in the standard product.

## Likely Post-V1 Roadmap

Potential later additions, prioritized by demonstrated customer demand and research value:

- point-in-time fundamentals and multi-factor models;
- earnings/analyst revision data;
- news/event classification and optional LLM-assisted text structuring;
- expanded customer-facing model-training/retraining UX if not included in the initial Developer Edition;
- additional model ensembles;
- paper trading;
- broker integrations such as Alpaca/IBKR;
- richer real-time/intraday data;
- additional universes/markets;
- macOS;
- optional Docker/self-hosted deployment for advanced users.

## Initial Development Sequence

The agreed build roadmap is **1. Market-data layer → 2. Backtester → 3. Risk/money management → 4. Strategies → 5. Validate strategies → 6. ML models → 7. Scanner/analytics → 8. Desktop UI → 9. Packaging/licensing/website**.

Each stage must have a usable, tested foundation before the next depends on it. Tests, provenance, documentation, and error handling accompany the implementation throughout. This sequence does not defer financial accounting tests to Stage 5 or all numerical reporting to Stage 7. Small fixtures and scripted orders are engineering inputs, not selected production strategies.

### Stage 1 — Market-data layer

- provider-neutral raw-price, security-identity, calendar, and corporate-action contracts;
- immutable raw/normalized snapshots, local storage, source hashes, and retrieval metadata;
- local CSV/Parquet imports and the initial development-provider adapter;
- data-health checks and explicit limits on calendar, adjustments, delistings, and universe coverage;
- point-in-time universe and benchmark data interfaces, with qualified scope or disclosed restrictions.

Current implementation includes local CSV/JSON and optional Parquet snapshots, EODHD original-response/API access, snapshot integrity, and dated membership connected to strategy eligibility. Synthetic integration tests cover those boundaries. Provider qualification, actual historical membership evidence, DuckDB/query storage and larger-data performance remain additional Stage 1 work. See [the data-layer contract](docs/DATA_LAYER.md).

Version 0.5.1 adds [offline corporate-action auditing and frozen-data preflight](docs/DATA_QUALIFICATION.md).
It preserves raw historical cash/payment fields, requires reviewed share-split
classification, and reports all input/evidence blockers without executing a
strategy. Qualified independent market inputs and the unchanged original retest
gate remain required; this does not complete provider qualification.

The tested local contract supports synthetic backtester development and a private, explicitly unqualified fixed-ETF market diagnostic requested on 2026-10-03. Complete actual-provider qualification before the registered empirical campaign or production claims; neither synthetic fixtures nor exploratory downloads establish qualified market coverage. The research-only collector and issuer normalization are documented in [the research plan](docs/RESEARCH_PLAN.md#first-real-market-exploratory-run); they are not a production API adapter.

### Stage 2 — Backtester

- specify signal and next-session execution timing;
- evaluate reuse against the hand-calculated conformance fixtures;
- implement shared-cash portfolio accounting, concurrent positions, costs, and rejected orders;
- handle supported corporate actions, missing data, and end-of-test positions explicitly;
- retain orders, fills, cash movements, positions, and reproducibility manifests;
- verify the simulator with synthetic ledgers and causality tests before using returns for research.

The simulator necessarily includes basic cash/position accounting and order affordability. Configurable investment-risk controls and sizing methods belong to Stage 3.

Current implementation: a reference long-only next-session market-order engine with shared cash, explicit costs, split/dividend/receivable/cash-delisting accounting, audit bundles, and hand-calculated/causality tests. Stage 3 adds protective stop-market execution with adverse gap handling. See [the implemented contract](docs/BACKTESTER.md). Target/trailing and broader execution profiles, production reuse selection, and Windows checks remain pending before Stage 2/commercial release completion. The initial engine does not imply those gates have passed.

### Stage 3 — Risk/money management

- fixed allocation, fixed-fractional risk, and ATR/volatility-based sizing;
- position, exposure, concentration, liquidity, reserve, and drawdown controls;
- portfolio-aware decisions and recorded rejection reasons;
- verified interaction between sizing, cash, stops, and execution.

Current implementation: fixed allocation, fixed-fractional/ATR stop-risk sizing, shared-cash reservations, entry position/exposure/group/reserve/liquidity/heat limits, next-open rechecks, daily drift audits, and close-observed drawdown reduction/latched next-open liquidation. See [the sourced research and implementation contract](docs/RISK_MANAGEMENT.md). Defaults are engineering examples, not optimized recommendations; stop/drawdown budgets are not maximum-loss guarantees. Historical group/ETF look-through qualification, richer exit-capacity modeling and real-data/Windows validation remain release work.

### Stage 4 — Strategies

- deterministic features and rule-based reference approaches;
- explicit ranking, entry/exit, and rebalancing contracts;
- registered configurations and benchmarks;
- common interfaces for subsequent ML scores and scanner use.

Current implementation: five rule-based families, including the original ten proposed recipes and a separately registered stock low-volatility family, full-budget/reserve buy-and-hold, same-universe equal-weight and cash references, causal split/dividend signal features, deterministic ranking, scheduled rebalancing and an explicit ATR-protected risk variant. Full configurations and signal decisions are versioned/audited; schema-1/2 saved runs remain readable. See [the strategy contract](docs/STRATEGIES.md). Synthetic correctness checks, one private ten-year momentum diagnostic, and an untuned exploratory comparison of all ten recipes have run. The comparison retains 70 trials and establishes no reliable benchmark superiority or production nominee; see [its evidence](docs/RESEARCH_PLAN.md#all-predefined-strategy-comparison). Real-data qualification and Stage 5 validation remain required before selecting production strategies or making commercial performance claims.

### Stage 5 — Validate strategies

- chronological development/selection partitions and protected final evaluation;
- walk-forward, parameter/cost sensitivity, regime breakdowns, and benchmark comparisons;
- a complete experiment registry including failed configurations;
- nominate, reject, or mark candidates inconclusive using predefined criteria.

Current implementation: frozen finite rule-strategy campaigns, snapshot-bound capability evidence, chronological continuous development folds and separate selection portfolios, append-only trial/failure records, matched benchmark/cost/delay/participation comparisons, exact metrics and asset-P&L reconciliation, paired stationary bootstrap and a centered maximum-mean search diagnostic, predefined nomination criteria and a single frozen nominee, independent-data crosschecks, and consumed-once final evaluation. JSON/CSV reports and accounting bundles are integrity-checked. See [the validation contract](docs/VALIDATION.md). Only synthetic engineering campaigns have been run; actual-provider qualification and empirical strategy validation remain required. DSR/PBO, qualified historical stock universes, measured execution/cash-rate assumptions, ML refitting and full commercial validation remain separate work.

The separate private [robustness audit](docs/RESEARCH_PLAN.md#robustness-audit-results--2026-10-03) has also run on already exposed history: 30 registered parameter/control/cost trials and five reused original portfolios. It implements reconciled asset/holding attribution, rolling returns, recovery, lagged historical-cash and exposure diagnostics with independently checked stop fills and verified report exports. Both fixed parents pass the limited positive-CAGR neighbor rule but fail their predeclared objectives; no production nominee is created. The audit and all-ten comparison remain exploratory evidence outside the qualified campaign and preserve the original search history.

Freeze promising candidates and re-test with better independent data before commercial reference claims. Another vendor over the same dates does not constitute a new temporal holdout. The separately recorded 2026-10-03 full-period exploratory run exposes 2024–2026, so those dates can no longer serve as untouched final evidence for future selection.

The separate [stock campaign](docs/RESEARCH_PLAN.md#stock-campaign-results--2026-10-03)
now implements the five-step research workflow on an explicitly surviving
22-stock sample. All 99 portfolios pass ledger reconstruction; the then-current
304-test suite passed.
SMA200 trend meets its predeclared defensive screens and is frozen only for
independent retesting; the three other canonical parents fail their objectives.
Unknown dividend payment dates and provider/sample qualification gaps remain
visible. The independent-data workflow is executable and tested, but actual
qualified independent market data and fresh temporal evidence remain pending.
There are zero qualified built-in strategies; the minimum-three/target-four
release requirement remains outstanding. Original registrations and a reported
finalization repair are preserved without financial resimulation or retuning.

The authorized fundamental feasibility and SEC evidence studies remain research-only and unqualified. Dated findings are consolidated in [research status](docs/RESEARCH_STATUS.md), preserving links to their detailed registrations and original evidence. Further bulk collection is deferred while correctness and data integration take priority; purchasing data is conditional on verified coverage and usage requirements.

The [audit remediation](docs/AUDIT_REMEDIATION.md) adds financial edge-case fixes, portable source preservation, EODHD response/API access, optional Parquet snapshots and dated membership integrated into strategy eligibility. These are engineering foundations, not qualified historical data, new strategy returns or release completion.

### Stage 6 — ML models

- leakage-safe feature/label, training, and chronological prediction pipelines;
- linear baselines, bounded tree-model experiments, and neural candidates only when justified;
- compare every model through the verified simulator and Stage 5 validation process;
- select production artifacts only from documented out-of-sample evidence.

### Stage 7 — Scanner/analytics

- scanner using the same strategy/model/risk definitions as historical research;
- full analytics, benchmarks, Trade Explorer, validation reports, and exports;
- local saved research and explanations derived from recorded decisions.

### Stage 8 — Desktop UI

- Windows/Linux desktop shell and local Python-engine integration;
- data-source setup, scanner, configuration, backtest, validation, and saved-research workflows;
- progressive disclosure of advanced settings with visible financial assumptions;
- observed usability, packaging feasibility, and failure-state checks.

### Stage 9 — Packaging/licensing/website

- reproducible Windows/Linux installers and smoke tests;
- Evaluation, Desktop, and Developer/Source delivery, including the training pipeline;
- secure credential storage, licensing/EULA, permitted reference artifacts, and release documentation;
- website, purchase/download flow, private release distribution, and entitlement boundaries;
- final commercial release-gate validation with first customer/design partner.

## Release Gate for Commercial V1

V1 is ready to sell only when:

1. supported data sources work reliably and licensing is understood;
2. at least three distinct built-in strategies (target four) meet the Reference Strategies qualification/delivery contract, with documented methodology and honest OOS/walk-forward evidence; supplied models meet the same relevant evidence standard;
3. backtesting semantics are explicit and covered by tests;
4. risk/sizing/portfolio accounting are verified;
5. results are reproducible and provenance is recorded;
6. the customer can inspect every trade and major assumption;
7. Windows installation is straightforward and Linux support meets the declared support level;
8. no mandatory developer tooling is required by the customer;
9. failures produce useful errors rather than crashes/stack traces;
10. documentation explains setup, data assumptions, strategy/model behavior, backtesting assumptions, metrics, and limitations;
11. a final strategy/model has been checked against an independent data source where feasible;
12. the product is something we would deliver unchanged at its core to customer #2 rather than rebuild after customer #1;
13. PR-01 through PR-15 have acceptance evidence for the declared supported scope, including observed no-code strategy creation and the discover/test/validate/risk workflow; requirements are not marked complete solely because engine tests pass.

## Decision Log — Current Settled Direction

- Build in the nine-stage roadmap above, starting with the market-data layer before the backtester.
- The 2026-10-03 product positioning and PR-01–PR-15 acceptance contract guide every substantial feature and release claim.
- V1 requires 3–4 distinct, well-researched, validated built-in strategies (minimum three; target four); the research platform and custom builder do not replace this requirement.
- Product is a paid local desktop quant research system, not SaaS.
- One-time purchase/perpetual use of delivered release is the intended commercial model.
- Windows is primary; Linux is supported; macOS later.
- U.S. equities + major ETFs, daily frequency.
- S&P 500 + Nasdaq-100 + Russell 1000 + ETFs + custom universes.
- Point-in-time universe handling is important for credible historical testing.
- Core application does not require AI/LLM services.
- ML is an alpha/ranking research component, not a replacement for deterministic risk management.
- Official models are trained by us and run locally for customers.
- Simple/rule-based models remain first-class and may outperform more complex ML.
- Historical data is cached/versioned locally for training/backtesting.
- Use chronological/walk-forward validation, never naive shuffled temporal splits.
- EODHD is the leading first customer-facing API candidate; Tiingo is a likely second adapter.
- Survivorship-aware internal research data remains a priority; Norgate's public commercial-use limitation pauses that option pending an applicable agreement. EODHD/Massive fixed-panel pilots remain unqualified.
- Local CSV/Parquet import is required.
- Prefer independent provider verification before shipping.
- Use free/free-tier market data for initial development/training/backtesting where permitted, then re-test frozen promising candidates on a paid/higher-quality and preferably independent dataset before commercial reference claims.
- Data-provider abstraction is mandatory.
- React/TypeScript + Tauri-like shell + local Python engine is the preferred UI architecture to validate.
- DuckDB + Parquet is the preferred local analytical storage direction.
- V1 ships three commercial forms: Evaluation, Desktop, and Developer/Source. Developer/Source is a real V1 deliverable and includes the model-training pipeline.
- No source code in standard Desktop delivery; Developer/Source Edition is a separate product/license.
- Current pricing hypotheses: Desktop $599 normal / $399 Early Bird; Developer/Source $2,499 normal / $1,499 Early Bird. Early Bird pricing uses one shared pool of the first 50 unique paying customers across Desktop and Developer/Source; the UI shows both normal and current prices plus a live claimed counter. Validate pricing with real buyers rather than treating it as immutable.
- OEM/commercial redistribution is negotiated separately rather than publicly fixed-price.
- Evaluation Edition is fully functional Desktop for 14 days from first activation, with no research-feature gating.
- Evaluation expiry preserves all customer work; purchase should unlock the same installation without reinstall/migration.
- V1 targets a lightweight storefront/download flow using Vercel + Supabase identity/license metadata + private Cloudflare R2 release storage. Customer trading/research data remains local-only and is never stored in our backend. Manual delivery remains acceptable for customer #1 if needed.
- Trial download requires only verified email, not a full account; paid customers may use accounts for ownership, entitlements, downloads, licenses, docs, and releases.
- The shared first-50 Founding Customer counter increments only on completed purchases and never resets as fake scarcity.
- Early external acquisition should emphasize technical research/content and quant communities before paid advertising.
- Purchased major versions are perpetual; maintenance releases are included while supported, while future major versions may be paid upgrades.
- Product positioning centers on control, rigor, reproducibility, accessibility, and serious quant research without requiring the customer to build a Python quant stack—not on novelty or “AI magic.”
- V1 is production/commercial quality; scope may be narrow but not provisional.
