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

This repository builds a commercial, local-first quantitative trading research
application for U.S. equities and ETFs. V1 is a paid product, not a prototype,
demo, notebook, or proof of concept.

Read `PROJECT.md` before making architectural or product decisions; it is the
product source of truth. This file defines how coding agents work here.

- **Requirements.** For substantial features, identify the supported PR-01–PR-15
  IDs and acceptance evidence. Preserve no-code Desktop strategy creation,
  explainable decisions, validation/risk discipline, local-only research data
  and perpetual purchased-version use. Do not market the product as AI trading
  software or treat profitable backtests, engine tests or an unfinished UI as
  delivery of the product promise.
- **Current milestone.** The V1 tester release (`PROJECT.md`, V1 Tester Release;
  [the roadmap](docs/ROADMAP.md)): four rule-based ETF plans plus one ML-ranked
  ETF rotation, the monthly order sheet, Rewind, Trader/Analyst views, Tiingo
  data, a local web app, Windows first.
- **Built-in strategies.** At least three distinct rule-based built-ins (target
  four) plus the ML-ranked rotation
  under [the evidence standard](docs/STRATEGY_EVIDENCE.md): disclosed evidence,
  no return, Sharpe or benchmark-beating threshold, ETF-based in V1, one
  registration and git tag per study, every outcome in
  [the research ledger](docs/RESEARCH_LEDGER.md). Engine tools,
  parameter/sizing variants and benchmarks do not count. Survivor-selected
  stock panels are never evidence. Where documents disagree, the standard governs.

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

- Windows 10/11 x64 is primary; Linux x86-64 is supported; macOS is deferred unless explicitly reprioritized.
- Daily-bar U.S. equities and major ETFs only. Tester-release plans decide monthly (optionally weekly) on daily data.
- Built-in universes: S&P 500, Nasdaq-100, Russell 1000, major U.S. ETFs and custom ticker lists (index universes come after the tester release).
- Historical universe membership must be point-in-time when the data source supports it. Never silently substitute current constituents for historical ones.
- V1 does not require broker execution, options, futures, forex, crypto, intraday/tick trading, news/LLM analysis, or cloud accounts.
- Customer-facing market data uses bring-your-own credentials and/or local CSV/Parquet imports.
- Official production models are trained by us and shipped with the application. Customer retraining is optional/advanced scope, never needed for normal use; the training pipeline and source access are required in commercial V1 Developer/Source.

## Preferred Architecture

### Build Roadmap

Follow the nine-stage sequence in `PROJECT.md` (Initial Development Sequence).
Build each foundation before its consumers; financial tests, provenance and
documentation accompany every stage. [The roadmap](docs/ROADMAP.md) holds the
current build order and status.

Keep domain boundaries explicit. A target structure is:

```text
apps/
  desktop/                 # UI shell + frontend (a local web app for the tester release)
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
```

Exact directories may evolve, but preserve the boundaries.

### Technology Direction

- Quant/research engine: Python. Local analytical storage: Parquet + DuckDB. No Docker requirement for ordinary customers.
- Dataframes/numerics: prefer Polars/NumPy; Pandas where ecosystem compatibility makes it preferable.
- ML: scikit-learn baselines; LightGBM, XGBoost, CatBoost as tabular candidates; neural models only after simpler baselines. Qlib may serve research/reference; do not couple the commercial runtime to it without an explicit architectural decision.
- Tester-release UI: a local web app (Python server plus browser) with an explicit API boundary to the engine; Windows build via GitHub Actions.
- Commercial desktop direction: React + TypeScript in a lightweight shell such as Tauri, talking to the local Python engine. Validate packaging/IPC before locking it in.

## Data Layer Rules

Define a provider-neutral interface. No strategy, model, risk, or backtest
module may call EODHD, Tiingo, Norgate, Alpaca, Massive, or any other vendor
directly. Normalized daily records support at least `symbol`, `session_date`,
`open`, `high`, `low`, `close`, `volume`, `adjusted_close` (when
supplied/derived), `dividend`, `split_factor`, `source` and `retrieved_at`.
Reference/universe data supports effective dates, ticker changes,
listing/delisting dates, exchange, sector/industry metadata where available,
and point-in-time membership.

- Preserve raw downloaded data separately from normalized/derived data; never overwrite raw observations during cleaning.
- Cache data locally; training and repeated backtests should not repeatedly call remote APIs.
- Make adjustment policy explicit. Do not mix adjusted signals with unadjusted execution prices accidentally.
- Detect missing sessions, duplicate bars, impossible OHLC relationships, non-positive prices, suspicious volume, and corporate-action discontinuities.
- Provenance identifies provider, retrieval time, adjustment policy, and dataset/version/hash where practical.
- Local CSV/Parquet import is a first-class provider. Never redistribute third-party datasets unless the license explicitly permits it.
- Never present free-data results as validated or independently verified. Treat cross-provider differences as a signal to investigate data assumptions, corporate actions, survivorship, timestamps, normalization, or overfitting.

### V1 Data Decision

- Tester release: Tiingo only, with the user's own free-tier key, cached locally (Tiingo's developer docs exempt bring-your-own-token software that distributes no data from licensing).
- Alpaca daily data stays internal development/research data; confirming its terms for commercial research use is open.
- Before a built-in's reference numbers are published, the project owner decides on an independent-provider cross-check; the evidence pack records it. Do not buy data or skip the cross-check on your own judgment.
- EODHD and CSV/Parquet adapters, and survivorship-free point-in-time data for stock strategies, come after the tester release. Do not hard-code vendor pricing, entitlements, coverage or licensing.

## Universe and Eligibility Rules

Keep these stages separate; never collapse them into a single opaque filter:

1. **Base universe** — e.g. S&P 500, Nasdaq-100, Russell 1000, ETFs, custom list.
2. **Point-in-time membership** — what belonged to the universe on the historical date.
3. **Tradability/eligibility filters** — price, average volume, dollar volume, history length, etc.
4. **Strategy conditions** — momentum/trend/volatility/model rules.
5. **Ranking** — ordering of eligible candidates.
6. **Risk acceptance** — portfolio-level permission to take a candidate.

## Backtesting Rules

- Signal timestamp and executable timestamp must be distinct.
- Default daily-bar semantics support signal-at-close / execute-next-session without look-ahead.
- Portfolio simulation accounts for cash, concurrent positions, rejected orders, exposure, transaction costs, slippage, stops, exits, and position sizing.
- Never calculate each ticker independently and combine returns afterward as a substitute for portfolio simulation.
- Handle corporate actions and delistings according to the available dataset and documented assumptions. Benchmark selection is independent of trading universe. Results state assumptions, not bury them.
- Every simulated order/trade is auditable and retains at least: signal and
  execution timestamps, symbol, side, signal/reason, requested order, fill
  price, quantity, position value, risk at entry, stop/target where applicable,
  fees, slippage, exit timestamp, price and reason, realized P&L,
  strategy/model version and configuration hash.

## Risk and Money Management

Keep alpha generation separate from capital allocation. Support deterministic
controls (risk per trade, position-size caps, maximum positions, gross/net
exposure, sector/concentration, drawdown-based controls, cash reserve,
liquidity) and sizing (fixed allocation, fixed-fractional risk,
volatility/ATR-based). A model may recommend a candidate; the risk engine may
reject it. This is expected behavior.

## Quant/ML Research Rules

Targets, features and the model tournament: `PROJECT.md` (Quant Algorithm / Model Plan).

- Frame ML as cross-sectional ranking/scoring, not exact price prediction.
- Research order: rule-based baseline → linear/logistic/Ridge/Elastic Net →
  LightGBM, XGBoost, CatBoost → MLP → temporal neural models only if justified →
  ensembles only when components add independent value.
- Never shuffle temporal data into train/test splits. Use chronological
  separation and walk-forward evaluation; protect an untouched final test
  period; avoid leakage from overlapping labels, revised data, universe
  membership, preprocessing, feature normalization or hyperparameter selection.
- Evaluate predictive and economic metrics after costs (rank IC, calibration
  where applicable, CAGR, Sharpe/Sortino/Calmar, drawdown, turnover, stability,
  cost/parameter sensitivity). A simpler model wins if it is more robust out of
  sample after costs.
- The tester-release ML plan is compared against the plain rule, shown as
  ranks, and shipped as a fixed, versioned model.

## Analytics Requirements

Implement the PR-09 metric set in `PROJECT.md`, plus equity and drawdown curves
and rolling performance where useful, each with a documented formula and tests.

## Validation Requirements

Built-in qualification follows [the evidence standard](docs/STRATEGY_EVIDENCE.md);
the campaign API/CLI in [the validation contract](docs/VALIDATION.md) remains a
research tool, not a qualification gate. Keep failure history and evidence
hashes intact. Do not relabel synthetic engineering campaigns as empirical
validation, or a maximum-mean bootstrap diagnostic as a deflated Sharpe ratio.
Changing a configuration after inspecting results, or correcting the engine
after a registered run, is a new registration with a new git tag that cites the
prior trial count; both outcomes stay on record and the fix carries a
regression test.

Product validation goes beyond one equity curve: in-sample vs out-of-sample,
walk-forward, parameter sensitivity, cost/slippage stress, regime/period and
universe comparisons, benchmark and simple baselines. Never optimize solely for
maximum historical return.

## Provenance and Reproducibility

Every saved backtest/report captures the manifest listed in `PROJECT.md`
(Backtest Provenance); see [reproducibility](docs/REPRODUCIBILITY.md). Given
the same dataset, configuration, model, and application version, Windows and
Linux must produce materially identical financial results.

## UI/UX Requirements

- The application looks like a professional research workstation, not a notebook wrapper.
- Trader/Analyst rule: simple by default, full detail on demand.
- Users can inspect why a trade occurred, what data/model/configuration generated it, and how assumptions affect results.
- Do not display uncalibrated ranking scores as probabilities. Do not label a model score `87% confidence` unless it has a precise, validated probabilistic interpretation.

## Commercial, Licensing & Evaluation Requirements

Terms, prices and editions are in `PROJECT.md` (Commercial Model). Engineering rules:

- Keep licensing and entitlement checks at application/service boundaries, never in backtest, data, strategy, model, risk, or analytics code.
- Prices and the shared first-50 Early Bird count are commercial configuration/backend metadata, never quant/application-domain logic. The counter counts completed purchases only and never resets.
- Evaluation is a license state on the same codebase, not a crippled demo fork: 14 days from first activation, no artificial ticker, history, trade-count, strategy, or validation limits.
- Trial expiry stops new research but never deletes customer work; purchase unlocks the existing installation without reinstall or migration.
- Basic tamper resistance is acceptable; anti-piracy work never takes priority over correctness and usability.
- **Privacy invariant:** never upload or store customer market data, API credentials, portfolios, positions, strategies, backtests, trades, model inputs/models, research projects, or caches in Supabase, R2, Vercel, telemetry, or another product backend. Backend records hold only the commercial/account metadata needed to distribute and license software.
- Do not promise a fixed number or cadence of updates or lifetime maintenance.
- Developer/Source source access grants no redistribution, sublicensing, resale, OEM, or competing-product rights. Never assume third-party training datasets may be redistributed; internal research artifacts need deliberate inclusion approval.
- Manual licensing is acceptable for customer #1, but do not design a disposable distribution path or let licensing infrastructure block quant correctness or release readiness. No complex self-updater is needed.
- Early acquisition: after customer #1 and the tester round, seek technically serious evaluators in quant/systematic/algo communities before meaningful paid advertising. Lead with reproducible research produced by the product (bias demonstrations, walk-forward studies, robustness tests, realistic-cost and model comparisons), not hype or return promises; respect each community's self-promotion rules; use trial behavior and paid conversion to learn which profile/edition converts before scaling spend.

## Testing Standard

Financial logic requires tests before UI polish. Required categories:

- unit tests for indicators/features, sizing, P&L, fees, slippage, stops, metrics, corporate-action transformations;
- integration tests for provider normalization, feature → signal → order → fill → portfolio flow;
- deterministic synthetic scenarios with hand-calculated expected results;
- regression/golden tests for known backtests;
- no-look-ahead, missing/bad-data and cross-platform result tests;
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

A feature is not done merely because the happy path works. For commercial V1
it needs correct domain behavior, automated tests, error handling,
persistence/versioning and provenance/auditability where applicable, clear UI
state and useful errors, documented assumptions, and no unresolved critical
correctness issues.

## Deferred Scope

Unless `PROJECT.md` is explicitly revised, do not expand V1 to include
automated live brokerage execution; options, futures, forex or crypto;
intraday/tick backtesting; reinforcement-learning trading agents; LLM-based
stock prediction; mandatory news/sentiment APIs; mobile apps; cloud
accounts/SaaS infrastructure; macOS packaging; or complex DRM. Items deferred
past the tester release are listed in `PROJECT.md` (V1 Tester Release).

Research spikes are allowed when they answer a concrete architectural or product question, but they must not quietly become V1 dependencies.

## Current Status

[The roadmap](docs/ROADMAP.md) holds build order and status;
[the evidence standard](docs/STRATEGY_EVIDENCE.md) governs built-ins; every
study and its trial count is in [the research ledger](docs/RESEARCH_LEDGER.md),
with earlier research under the git tag `archive/research-2026-10`. Keep status
and historical logs out of this file.
