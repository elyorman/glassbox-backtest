# AGENTS.md

## Project Ownership and Git Workflow

This is Elyorjon Mannonov's personal `elyorman/quant-platform` project. It is
independent of any employer or company workflow: no issue-tracker tickets,
ticket IDs or ticket-prefixed branch/commit names are required, and no
employer name, work account, work email or work tooling may appear in code,
docs, commit metadata or configuration. Use the personal git identity
configured for this repository. Do not block authorized work, commits or
pushes to request a ticket. Use concise descriptive commit messages. These
repository-specific instructions override generic workflow preferences from
other contexts.

Create branches, commit, push or open pull requests only when the user requests
those actions. Never include credentials or generated vendor research data.

## Purpose

This repository builds a commercial, local-first quantitative trading research application for U.S. equities and ETFs. V1 is a paid product, not a prototype, demo, notebook, or proof of concept.

Read `PROJECT.md` before making architectural or product decisions. Treat it as the product source of truth. This file defines how coding agents should work in the repository.

Its **Product Positioning and Differentiation** and **PR-01–PR-15 Product
Requirements and Acceptance Contract** define the build's user value and release
criteria. For substantial features, identify the supported requirement IDs and
acceptance evidence. Preserve no-code Desktop strategy creation, explainable
decisions, validation/risk discipline, local-only research data and perpetual
purchased-version use. Do not market the product as AI trading software or
treat profitable backtests, engine tests or an unfinished UI as delivery of the
complete product promise. Source access and the training pipeline are required
in V1 Developer/Source; richer Desktop retraining UI is optional.

V1 also requires **3–4 distinct, well-researched built-in strategies**
(minimum three; target four) under
[the built-in strategy evidence standard](docs/STRATEGY_EVIDENCE.md), adopted
2026-10-08: disclosed evidence packs, no return, Sharpe or benchmark-beating
threshold, ETF-based V1 built-ins, one registration and git tag per study, and
[the research ledger](docs/RESEARCH_LEDGER.md) for every outcome. Engine
tools, parameter/sizing variants and benchmarks do not count as strategies.
Where any other document disagrees with the standard, the standard governs.

## Core Principles

1. **Correctness before cleverness.** Financial calculations that look plausible but are wrong are unacceptable.
2. **No hidden look-ahead.** At timestamp `t`, strategies, features, models, and execution logic may only use information that was actually available at `t`.
3. **Reproducibility is a feature.** Backtests must record enough provenance to reproduce and audit results.
4. **Risk is deterministic.** ML/alpha models rank or score opportunities; they do not bypass portfolio, risk, or money-management rules.
5. **Models must earn their complexity.** Always compare ML against strong rule-based and linear baselines. Never prefer a neural network merely because it is more sophisticated.
6. **Provider independence.** Strategy and backtest code must not depend directly on a specific market-data vendor.
7. **Local-first.** Core analysis, models, storage, backtesting, risk calculations, and analytics run locally. No mandatory cloud service or LLM API.
8. **Commercial quality.** Included V1 features must be finished, documented, tested, and usable by a paying technical trader.
9. **Narrow is acceptable; half-built is not.** Defer features rather than shipping unreliable implementations.
10. **No performance hype.** Never encode UI/copy that implies guaranteed returns, certainty, or magical prediction.

## Product Constraints

- Primary platform: Windows 10/11 x64.
- Supported V1 platform: Linux x86-64.
- macOS is deferred unless explicitly reprioritized.
- Daily-bar U.S. equities and major ETFs only in V1.
- Built-in universes: S&P 500, Nasdaq-100, Russell 1000, major U.S. ETFs, plus custom ticker lists.
- Historical universe membership must be point-in-time when the selected data source supports it. Never silently substitute current constituents for historical constituents.
- V1 does not require broker execution, options, futures, forex, crypto, intraday/tick trading, news/LLM analysis, or cloud accounts.
- Customer-facing market data uses bring-your-own credentials and/or local CSV/Parquet imports.
- Official production models are trained by us and shipped with the application. Customer retraining is optional/advanced scope, not a dependency for normal use.

## Preferred Architecture

### Build Roadmap

Follow the development sequence in `PROJECT.md`: market-data layer → backtester → risk/money management → strategies → strategy validation → ML models → scanner/analytics → desktop UI → packaging/licensing/website. Implement the required foundation before its consumers. Financial tests, provenance, and documentation accompany each stage. Basic cash/position accounting is part of the backtester; configurable investment-risk and sizing methods follow it.

Keep domain boundaries explicit. A target structure is:

```text
apps/
  desktop/                 # desktop shell + frontend
python/
  quant_core/
    data/                  # provider interfaces, normalization, cache
    universes/             # point-in-time membership and eligibility
    features/              # deterministic feature computation
    models/                # training/inference adapters
    strategies/            # strategy definitions and signal generation
    execution/             # order/fill simulation
    portfolio/             # cash, holdings, exposure, accounting
    risk/                  # deterministic risk constraints
    sizing/                # money/position sizing
    backtest/              # event/portfolio simulation orchestration
    validation/            # walk-forward, OOS, sensitivity
    analytics/             # performance/risk/trade metrics
    provenance/            # hashes, manifests, reproducibility metadata
    storage/               # DuckDB/Parquet repositories
    reporting/             # exports/reports
  research/                # experiments; never imported by production runtime
tests/
  unit/
  integration/
  regression/
  fixtures/
docs/
```

Exact directories may evolve, but preserve the boundaries.

### Technology Direction

- Quant/research engine: Python.
- Local analytical storage: Parquet + DuckDB.
- Dataframes/numerics: prefer Polars/NumPy where appropriate; Pandas is acceptable where ecosystem compatibility makes it preferable.
- Baseline ML: scikit-learn.
- Candidate tabular ML: LightGBM, XGBoost, CatBoost.
- Neural models are research candidates only after simpler baselines.
- Qlib may be used as a research/reference framework; do not couple the commercial runtime to Qlib without an explicit architectural decision.
- Desktop UI direction: React + TypeScript in a lightweight cross-platform shell such as Tauri, communicating with the local Python quant engine. Validate packaging/IPC before locking this in.
- No Docker requirement for ordinary customers. Docker may later be an advanced deployment option.

## Data Layer Rules

Define a provider-neutral interface. No strategy, model, risk, or backtest module may call EODHD, Tiingo, Norgate, Alpaca, Massive, or any other vendor directly.

Normalized daily market records should support at least:

```text
symbol
session_date
open
high
low
close
volume
adjusted_close (when supplied/derived)
dividend
split_factor
source
retrieved_at
```

Reference/universe data should support effective dates, ticker changes, listing/delisting dates when available, exchange, sector/industry metadata where available, and point-in-time membership.

Rules:

- Preserve raw downloaded data separately from normalized/derived data.
- Never overwrite raw source observations during cleaning.
- Cache data locally; model training and repeated backtests should not repeatedly call remote APIs.
- Make adjustment policy explicit. Do not mix adjusted signals with unadjusted execution prices accidentally.
- Detect missing sessions, duplicate bars, impossible OHLC relationships, non-positive prices, suspicious volume, and corporate-action discontinuities.
- Data provenance must identify provider, retrieval time, adjustment policy, and dataset/version/hash where practical.
- Local CSV/Parquet import is a first-class provider.

### Provider Priorities

Current user decision (2026-10-08): build and research V1 ETF built-ins on
the existing Alpaca daily data. Before reference numbers are published, the
project owner decides whether an independent-provider cross-check (target:
Tiingo business plan) is feasible; the evidence pack records the decision,
its reason and any result. Do not buy data or skip the cross-check on your
own judgment. Survivorship-free point-in-time data and further EODHD
collection are deferred to a later stock-strategy stage. Confirming Alpaca's
terms for commercial research use is an open action item. See
`docs/STRATEGY_EVIDENCE.md`, Section 5.

Current plan, subject to hands-on validation and licensing review:

- Internal stock research (later stage): prioritize survivorship-aware point-in-time data. Norgate's current public business/commercial-use limitation pauses that option pending an applicable agreement; see `docs/INDEPENDENT_DATA_RETEST.md` for the conditional EODHD/Massive fixed-panel pilot.
- First customer-facing API adapter: EODHD.
- Second customer-facing adapter: Tiingo.
- Future integrations: Alpaca (especially paper/live trading roadmap), Massive/Polygon for richer real-time/intraday needs.

Do not hard-code commercial assumptions about a vendor. Pricing, entitlements, coverage, and licensing change.

## Universe and Eligibility Rules

Separate these concepts:

1. **Base universe** — e.g. S&P 500, Nasdaq-100, Russell 1000, ETFs, custom list.
2. **Point-in-time membership** — what belonged to the universe on the historical date.
3. **Tradability/eligibility filters** — price, average volume, dollar volume, history length, etc.
4. **Strategy conditions** — momentum/trend/volatility/model rules.
5. **Ranking** — ordering of eligible candidates.
6. **Risk acceptance** — portfolio-level permission to take a candidate.

Never collapse these stages into a single opaque filter.

## Backtesting Rules

Backtesting is a core product subsystem and requires especially strict engineering.

- Signal timestamp and executable timestamp must be distinct.
- Default daily-bar semantics should support signal-at-close / execute-next-session assumptions without look-ahead.
- Portfolio simulation must account for cash, concurrent positions, rejected orders, exposure, transaction costs, slippage, stops, exits, and position sizing.
- Never calculate each ticker independently and combine returns afterward as a substitute for portfolio simulation.
- Corporate actions and delistings must be handled according to the available dataset and documented assumptions.
- Every simulated order/trade must be auditable.
- Benchmark selection is independent of trading universe.
- Results must state assumptions, not bury them.

### Required Trade Audit Fields

At minimum retain:

```text
signal timestamp
execution timestamp
symbol
side
signal/reason
requested order
fill price
quantity
position value
risk at entry
stop/target where applicable
fees
slippage
exit timestamp
exit price
exit reason
realized P&L
strategy/model version
configuration hash
```

## Risk and Money Management

Keep alpha generation separate from capital allocation.

V1 should support deterministic controls including:

- maximum risk per trade;
- position-size caps;
- maximum number of positions;
- gross/net exposure constraints where relevant;
- sector/concentration constraints;
- drawdown-based controls;
- cash reserve;
- liquidity constraints.

V1 position-sizing methods should include:

- fixed allocation;
- fixed-fractional risk;
- volatility/ATR-based sizing.

A model may recommend a candidate. The risk engine may reject it. This is expected behavior.

## Quant/ML Research Rules

The primary ML framing is cross-sectional ranking/scoring, not exact future-price prediction.

Candidate prediction targets include:

- 5/10/20-day forward return;
- forward excess return vs benchmark/sector;
- cross-sectional forward-return rank;
- barrier/trade-outcome labels such as target-before-stop within a horizon.

Candidate feature families include:

- momentum/returns across horizons;
- trend and moving-average relationships;
- realized/downside volatility and ATR;
- volume/liquidity/relative-volume features;
- relative strength vs market/sector;
- cross-sectional ranks;
- market/sector regime and breadth;
- later: point-in-time fundamentals, earnings/events, news-derived features.

Model research order:

1. deterministic rule-based baseline;
2. linear/logistic/Ridge/Elastic Net baseline;
3. LightGBM;
4. XGBoost;
5. CatBoost;
6. MLP;
7. LSTM/GRU/TCN/Transformer candidates only if justified;
8. ensembles only when components add demonstrably independent value.

Do not use random shuffled train/test splits for temporal financial evaluation.

Use chronological train/validation/test separation and walk-forward evaluation. Protect a genuinely untouched final test period during model development. Avoid leakage from overlapping labels, revised data, universe membership, preprocessing, feature normalization, or hyperparameter selection.

Evaluate models on both predictive and economic metrics, including rank IC where applicable, calibration where applicable, CAGR, volatility, Sharpe, Sortino, Calmar, maximum drawdown, turnover, expectancy, profit factor, stability across regimes/universes, and sensitivity to costs/parameters.

A simpler model wins if it is more robust out of sample after costs.

## Analytics Requirements

V1 analytics should include at least:

- total return and CAGR;
- annual/monthly returns;
- equity curve;
- drawdown curve and maximum drawdown;
- volatility/downside deviation;
- Sharpe, Sortino, Calmar;
- win/loss rate;
- average win/loss and payoff ratio;
- expectancy;
- profit factor;
- trade count and holding period;
- consecutive wins/losses;
- exposure, turnover, cash utilization, concentration;
- benchmark comparison;
- rolling performance where useful.

Metrics must have documented formulas and tests.

## Validation Requirements

The campaign API/CLI in `docs/VALIDATION.md` remains available as a research
tool; built-in qualification follows `docs/STRATEGY_EVIDENCE.md` instead of
its nomination gates. Keep failure history and evidence hashes intact. Do not
relabel synthetic engineering campaigns as empirical validation or a
maximum-mean bootstrap diagnostic as DSR. Changing a configuration after
inspecting results, or correcting the engine after a registered run, is a new
registration with a new git tag that cites the prior trial count; both
outcomes stay on record and the fix carries a regression test.

V1 must support serious validation, not just a single historical equity curve:

- in-sample vs out-of-sample reporting;
- walk-forward testing;
- parameter sensitivity;
- transaction-cost/slippage stress tests;
- regime/time-period breakdowns;
- universe comparison where appropriate;
- comparison against benchmark and simple baselines.

Never optimize solely for maximum historical return.

## Provenance and Reproducibility

Every saved backtest/report should capture a manifest comparable to:

```text
strategy name/version
model name/version/hash
configuration hash
data provider
data retrieval timestamp
dataset hash/version where practical
universe and point-in-time policy
period
adjustment policy
execution convention
fees/slippage
benchmark
application version
```

Given the same dataset, configuration, model, and application version, Windows and Linux should produce materially identical financial results.

## UI/UX Requirements

The application should look like a professional research workstation, not a notebook wrapper.

Core V1 areas:

- Dashboard
- Scanner
- Strategy/Model configuration
- Backtest setup
- Backtest results & analytics
- Validation/robustness
- Trade Explorer
- Risk/position-sizing configuration
- Data Sources & data health
- Saved runs/configurations
- Export/reporting

Expose advanced detail without forcing it on every workflow. Technical users should be able to inspect why a trade occurred, what data/model/configuration generated it, and how assumptions affect results.

Do not display uncalibrated ranking scores as probabilities. Do not label a model score `87% confidence` unless it has a precise, validated probabilistic interpretation.

## Commercial, Licensing & Evaluation Requirements

V1 is a one-time-purchase product. Licensing is a product concern, but licensing must not contaminate quant-domain logic. Keep entitlement checks at application/service boundaries rather than scattering them through backtest, data, strategy, model, risk, or analytics code.

### Desktop Edition

- Packaged Windows/Linux application; source code is not included.
- Perpetual right to use the purchased major version.
- No mandatory subscription to us.
- Maintenance releases for that major version are included while that major version is supported; do not promise a fixed number/cadence of updates or lifetime maintenance.
- Major future versions may be optional paid upgrades. The purchased version must not expire merely because a newer major version exists.
- Customer supplies third-party market-data credentials when required; local CSV/Parquet remains supported.
- Current pricing hypothesis, not a hard-coded product invariant: $599 normal Desktop price, with **$399 Early Bird pricing while the shared first-50 Founding Customer pool remains open**. The storefront should show the normal and Early Bird prices together. Pricing/counts must remain configuration/business metadata, never quant/application-domain logic.

### Developer / Source Edition

- Separate higher-priced license; current pricing hypothesis is $2,499 normal / **$1,499 Early Bird while the shared first-50 Founding Customer pool remains open**. Show normal and Early Bird prices together; keep the limit configurable.
- Includes the Desktop product plus source for the application/platform and appropriate build/extension documentation.
- Intended to permit inspection and internal/private modification under the final license.
- Source access does **not** imply redistribution, sublicensing, resale, OEM, or competing-product rights.
- V1 Developer/Source **includes the production-model training pipeline**, allowing technical buyers to train/modify their own models. Never assume third-party training datasets may be redistributed. Internal research artifacts require deliberate inclusion approval.
- Commercial redistribution/OEM rights are negotiated separately and are not a public fixed-price tier for now.

### Founding Customer Offer

- One shared pool covers Desktop and Developer/Source: the first **50 unique paying customers** qualify for Early Bird pricing.
- Count completed qualifying purchases only; trials, registrations, and abandoned checkouts do not increment the counter.
- One customer counts once even if they purchase multiple editions/licenses.
- Storefront should show a live `X / 50 claimed` indicator plus normal and Early Bird prices.
- At customer #50 the offer ends; do not reset or manufacture another “first 50” campaign.
- Keep price/count state in commercial configuration/backend metadata, outside the quant engine.

### Evaluation Edition

Evaluation must use the same Desktop application/codebase and the same quant capabilities as the paid Desktop Edition. Do not maintain a crippled demo fork.

- Duration: **14 days from first activation**.
- All Desktop research features are enabled: data providers/imports, scanner, supplied strategies/models, custom strategy configuration, backtesting, risk/sizing, validation, Trade Explorer, saved research, and exports.
- The purpose is genuine verification; do not impose artificial ticker, history, trade-count, strategy, or validation limits.
- Evaluation status is a license state, not a separate quant engine.
- After expiration, prevent new research execution as defined by the final UX, but preserve the user's local data, projects, configurations, and previous results. Never delete customer work on trial expiry.
- Purchasing Desktop should activate/unlock the existing installation without requiring a reinstall or migration.
- Evaluation/paid entitlement logic must remain outside the quant engine. Manual licensing remains an acceptable fallback for customer #1; do not let licensing infrastructure block quant correctness or release readiness.
- Basic tamper resistance is acceptable; anti-piracy work must not take priority over product correctness and usability.

### V1 Editions, Storefront & Distribution

V1 must be deliverable as **Evaluation, Desktop, and Developer/Source**. The first customer may buy Developer/Source, so source packaging, build documentation, tests, and the training pipeline cannot be deferred beyond V1.

Target lightweight distribution architecture:

- Vercel for the public product/pricing/download UI;
- Supabase only for verified-email, account, purchase, license, and entitlement metadata;
- private Cloudflare R2 for installers, release artifacts, and protected source archives;
- short-lived/signed download authorization rather than permanent public file URLs.

**Privacy invariant:** never upload or store customer market data, API credentials, portfolios, positions, strategies, backtests, trades, model inputs/models, research projects, or caches in Supabase, R2, Vercel, telemetry, or another product backend. Those remain local to the customer's computer. Backend records are limited to the minimum commercial/account metadata needed to distribute and license software.

Evaluation UX: Download Evaluation → email → verification → authorized download. Do not require a full account merely to evaluate. Paid Desktop/Developer purchases may create/use an authenticated customer account for software ownership, entitlements, downloads, license information, documentation, and releases.

Customer #1 may still be served manually if the storefront is unfinished, but do not design a disposable distribution path. A complex self-updater is unnecessary for V1; update discovery may redirect to the authenticated download page.

Custom strategy/features/integrations are separate paid work. OEM/commercial redistribution is negotiated case-by-case.

## Research Data Cost & Validation Discipline

- Free/free-tier historical data may be used for engine development, model training, exploratory backtesting, test construction and V1 ETF built-in research (Alpaca daily data; `docs/STRATEGY_EVIDENCE.md` Section 5) where provider terms permit.
- Do not present free-dataset results as validated or independently verified; evidence packs disclose the provider and its limitations.
- Before reference numbers for a built-in are published, the project owner decides whether an independent-provider cross-check is feasible; the evidence pack records the decision, its reason and any result. Survivorship-free point-in-time data is required before stock-based strategies can become built-ins.
- Treat cross-provider degradation as a signal to investigate data assumptions, corporate actions, survivorship, timestamps, normalization, or overfitting.
- Never redistribute third-party market datasets unless the license explicitly permits it; normal customer use remains BYO provider/local data.

## Early Commercial Acquisition Principles

- After customer #1/office testers, seek technically serious external evaluators in relevant quant/systematic/algo communities before spending meaningfully on paid advertising.
- Lead marketing with reproducible research produced by the product (bias demonstrations, walk-forward studies, robustness tests, realistic-cost comparisons, model comparisons), not hype or return promises.
- Respect each community's self-promotion rules.
- Use trial behavior and paid conversion to learn which customer profile/edition converts before scaling acquisition spend.

## Testing Standard

Financial logic requires tests before UI polish.

Required categories:

- unit tests for indicators/features, sizing, P&L, fees, slippage, stops, metrics, corporate-action transformations;
- integration tests for provider normalization, feature → signal → order → fill → portfolio flow;
- deterministic synthetic scenarios with hand-calculated expected results;
- regression/golden tests for known backtests;
- no-look-ahead tests;
- missing/bad-data tests;
- cross-platform result checks;
- model feature-schema/version compatibility tests.

For any bug affecting historical results, add a regression test before or with the fix.

## Engineering Workflow for Agents

Before substantial implementation:

1. Read `PROJECT.md` and this file.
2. Identify the relevant subsystem and invariants.
3. Inspect existing interfaces/tests before adding abstractions.
4. Prefer small, testable changes over broad rewrites.
5. Add/modify tests alongside financial logic.
6. Run the narrowest relevant tests, then broader tests when warranted.
7. Update documentation when behavior, assumptions, schema, or public configuration changes.

When uncertain about a financial assumption, **do not silently choose one**. Encode it as an explicit configuration or document the decision for review.

## Definition of Done

A feature is not done merely because the happy path works. For commercial V1 it should have:

- correct domain behavior;
- automated tests;
- error handling;
- persistence/versioning where applicable;
- provenance/auditability where applicable;
- clear UI state and useful errors;
- documentation of assumptions;
- no unresolved critical correctness issues.

## Deferred Scope

Unless `PROJECT.md` is explicitly revised, do not expand V1 to include:

- automated live brokerage execution;
- options/futures/forex/crypto;
- intraday/tick backtesting;
- reinforcement-learning trading agents;
- LLM-based stock prediction;
- mandatory news/sentiment APIs;
- mobile apps;
- cloud accounts/SaaS infrastructure;
- macOS packaging;
- complex DRM.

Research spikes are allowed when they answer a concrete architectural or product question, but they must not quietly become V1 dependencies.

## Current implementation and research status

See [audit remediation](docs/AUDIT_REMEDIATION.md) for corrected engine/data behavior, [the research ledger](docs/RESEARCH_LEDGER.md) for every study and its trial count, and [research status](docs/RESEARCH_STATUS.md) for dated historical evidence (superseded rules noted at its top). Keep historical logs out of this instruction file. Preserve frozen sources/results; new code or data requires distinct evidence. EODHD response import, optional Parquet and dated membership are implemented foundations, not empirical provider/strategy qualification.

The [action audit and input preflight](docs/DATA_QUALIFICATION.md) retain missing
cash/payment fields and reviewed event classifications. Preflight templates stay
unresolved until reviewed; schema-2 and adjusted-volume conflicts must not be
silently bypassed to admit data to the schema-1 frozen retest.
