# Backtester Research and Design Proposal

Research date: 2026-10-02. Status: source-backed design with an initial reference engine implemented and tested. See [the executable contract](BACKTESTER.md). A synthetic scaling measurement is available; no comparative engine benchmark or completed reuse evaluation is claimed.

Build order follows the nine-stage roadmap in `PROJECT.md`. The market-data layer is Stage 1; the backtester is Stage 2, followed by risk/money management and strategies. The sequence below describes dependencies inside the backtester/research work, not a competing product roadmap. The local data contract supports the implemented synthetic simulation core; real-provider qualification and the reuse evaluation remain pending.

This document complements [the strategy research plan](RESEARCH_PLAN.md). `PROJECT.md` remains the product source of truth. The immediate scope is daily US stock and ETF portfolio research, with a local Python engine and eventual Windows/Linux desktop distribution.

## Finding: simplicity and rigor can coexist

The claim that capable backtesters are necessarily too complicated, while simple ones are necessarily unreliable, is too broad. Existing products already offer compact strategy definitions, portfolio accounting, and layers of customization. The opportunity we should test is whether our specific audience can configure, understand, and reproduce a defensible daily portfolio experiment with less effort.

Our recommendation is to simplify setup through a bounded scope and progressive disclosure while keeping financially consequential assumptions visible. A short strategy definition does not establish correctness; a large execution framework does not establish realistic results either.

This review uses primary documentation. It establishes documented capabilities and defaults, not comparative usability, speed, defect rates, or demand. Those require hands-on evaluation and user observation.

## Existing approaches and lessons

| Tool | Documented approach | Implication for our design |
| --- | --- | --- |
| backtesting.py | Compact `Strategy`/`Backtest` interface; configurable commissions, next-open versus close execution, and end-of-test liquidation. | Good reference for a small research API. Warmup and terminal-position settings must remain visible because they affect comparisons. [API](https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html) |
| VectorBT | Array-oriented portfolio simulation with order records, shared-cash groups, and configurable order sequencing. | Fast experiment interfaces can retain portfolio state. Cash sharing and sell/buy ordering must be explicit; independent asset columns are not automatically a joint portfolio. [Portfolio API](https://vectorbt.dev/api/portfolio/base/) |
| Backtrader | Event-driven broker simulation with extensible execution and volume fillers; its default ignores volume. | Execution realism depends on configuration and inputs. Merely choosing an event-driven engine does not establish fill realism. [Volume fillers](https://www.backtrader.com/docu/filler/) |
| LEAN | Separate fill, fee, slippage, and brokerage models. | Useful reference for separating accounting from execution assumptions, and a candidate for a reuse experiment. [Reality models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts) |
| Zipline Reloaded | Ingested, timestamped data bundles; asset metadata, calendars, and corporate-action adjustments. | Adopt reproducible data snapshots and security identity. Hide ingestion machinery behind a provider-neutral desktop workflow. [Data bundles](https://zipline.ml4trading.io/bundles.html) |
| RealTest | Date/strategy/security simulation passes; precomputed data separated from portfolio-dependent test calculations. | Strong prior art for combining efficient feature calculation with sequential portfolio decisions. Study this before inventing a strategy language. [Loop](https://www.mhptrading.com/docs/topics/idh-topic1071.htm), [TestData](https://www.mhptrading.com/docs/topics/idh-topic531.htm) |
| AmiBroker | Portfolio backtesting with ranking and sizing, plus multiple levels of custom backtest control. | Simple rules and advanced portfolio behavior can share a product. Extension levels should expose only the control a user needs. [Portfolio guide](https://www.amibroker.com/guide/h_portfolio.html), [Custom backtester](https://www.amibroker.com/guide/a_custombacktest.html) |
| TradingView | Chart-linked strategy reports and trades; documented broker-emulator assumptions and optional lower-timeframe Bar Magnifier. | Make results inspectable at the trade level. Daily OHLC cannot establish the true sequence of intraday prices. [Strategies](https://www.tradingview.com/pine-script-docs/concepts/strategies/) |

These lessons are our design inferences, not claims that these tools lack the features we propose.

## Product contract

The initial workflow should require five understandable choices: dataset/universe, strategy, dates, starting capital/risk limits, and execution profile. A readable summary must show costs, signal/fill timing, allocation, cash policy, corporate-action coverage, and known data limitations before running. Advanced controls edit the same configuration used by the basic workflow.

The result should answer:

1. What happened to capital, including costs, cash, distributions, and open positions?
2. Why did each proposed trade execute, change size, or get rejected?
3. Which observations and model versions were available when the decision was made?
4. How does performance compare with an appropriate benchmark and other chronological periods?
5. Which assumptions or missing data could materially change the conclusion?

For example, a rejected order should say “Rank 6; maximum positions 5” or “Requested 10 shares; opening gap plus costs exceeded available buying power.” Explanations should come from recorded decisions, not reconstructed guesses or generated narratives.

## One simulation core

Use provider adapters to produce immutable normalized snapshots. Compute causal features in batches, then process portfolio events chronologically through one authoritative ledger. Parallelize independent runs and feature work before considering acceleration of the stateful loop.

The public research interface should accept a data snapshot, strategy definition or prediction stream, portfolio policy, and execution profile. It should return a run manifest, decision records, orders, fills, corporate-action events, cash movements, positions, equity, and derived metrics.

Rule-based strategies and ML models should produce comparable scores or target allocations. A shared allocation/risk layer turns those into orders. Advanced strategies may use a restricted historical-data interface, but arbitrary Python and externally computed predictions cannot be made leakage-free merely by an API boundary. Record prediction availability, training cutoffs, feature versions, and preprocessing provenance; test causality independently.

Keep fees, slippage, sizing, calendars, and corporate actions as explicit components. Avoid a general plugin framework until concrete requirements demand it. Use stable security identifiers, stable tie-breaking, documented numerical precision and rounding, and versioned event ordering. Persist inputs and outputs locally; no vendor calls inside strategy or simulation code.

Caching must include data snapshot, feature/model versions, configuration, and relevant code versions. A changed dataset or execution rule must never reuse a stale result silently.

## First execution profile

These are proposed engineering semantics, consistent with the research campaign. They must be specified and tested before comparing strategies.

| Concern | Initial policy |
| --- | --- |
| Instruments | Long-only USD stocks/ETFs, no leverage; start with the fixed ETF research universe and disclose retrospective selection. |
| Decision timing | Completed-session information produces orders for the next eligible session. Size using information available at decision time. |
| Execution | Next daily open with explicit adverse costs. This is a daily-bar approximation, not a claim to reproduce an opening auction. |
| Shared capital | One portfolio ledger. Process scheduled sells, then ranked buys with stable security-ID tie-breaking. Reject unaffordable orders; do not silently resize. |
| Costs | Research scenarios of 5/10/25 basis points per side, 10 primary, as assumptions rather than measured execution estimates. Distinguish aggregate friction from separately configured fees to prevent double charging. |
| Liquidity | Prior-data participation checks; the proposed 1% lagged average daily volume cap is a screening proxy, not evidence of opening liquidity. |
| Prices/actions | Raw execution prices; explicit splits and dividend entitlements/receivables/payments. Separate signal adjustments from cash accounting to avoid double counting. |
| Missing data | Never forward-fill a tradable price into a fill. Track stale valuation explicitly. Unresolved held-security events can invalidate a run rather than silently remove the position. |
| End of test | Mark open positions to the final valid valuation and report them. Optional liquidation is a separate labeled scenario with its own execution and costs. |
| Cash return | Initially zero and disclosed; historical cash-return sensitivity is needed before strategy qualification. |

The initial research capital model permits proceeds reuse after simulated sales. It must be labeled an economic portfolio model, not a faithful brokerage cash-account simulation. A brokerage profile needs dated settlement rules and separate settled/unsettled cash and buying power. For example, the US transition to T+1 took effect on May 28, 2024; applying one settlement lag across the whole research history would be wrong. [SEC T+1 FAQ](https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq)

The first vertical slice used scheduled market orders only. Stage 3 now adds protective stop-market orders with adverse gap handling and opening/intraday phase separation, specified in [the risk contract](RISK_MANAGEMENT.md). Targets and trailing stops remain later execution work. Specify next-session trailing updates and an explicit ambiguous-bar policy before adding them. If both stop and target lie inside a daily bar, report the ambiguity and compare adverse/favorable sequencing; neither assumption recovers the actual path. Reject order features that the selected profile cannot support.

Missing corporate-action inputs must prevent a run from being presented as a qualified total-return study. A separately labeled price-only diagnostic may still help engineering. Likewise, a current constituent list cannot support claims about a historical point-in-time stock universe.

## Correctness before strategy selection

Build synthetic, hand-calculated fixtures before assessing strategy returns. Required cases include:

- Next-session execution across weekends, holidays, and missing bars; no same-close leakage.
- Two simultaneous buys competing for cash; sells funding later buys; stable outcomes under input-column permutation.
- Opening gaps, unaffordable orders, integer-share rounding, fees, and partial allocation.
- Splits affecting holdings and pending orders without inventing portfolio gains.
- Dividend entitlement, receivable valuation, payment, and sale between ex-date and payment date.
- Stale marks, missing held-security prices, and explicit delisting handling.
- Open positions at the final date and optional terminal liquidation.
- Known cash/position/equity identities after every event, including zero-trade runs.
- Warmup periods and common evaluation windows across different indicators.
- Predictions with future training dates and overlapping-label split violations.

Add future-data perturbation and prefix-invariance tests: changing observations after a decision must not alter that earlier decision. Compare a small independent ledger calculation and a second engine under matched assumptions; agreement is useful evidence, not proof. Investigate differences at the first divergent event rather than adjusting final returns to match.

For fixed orders and fills, increasing fees should reduce ending wealth by the expected amount. Do not assume monotonic performance when higher costs change sizing, eligibility, or subsequent orders.

Every financial bug gets a regression fixture and invalidates affected saved results. Re-run the registered strategy set after a relevant fix, including losers. Never change execution behavior because it makes a candidate look stronger.

## Research integrity is part of the workflow

Use the chronological partitions, trial limits, and selection rules in the research plan. Save unsuccessful experiments and manual parameter changes. Show net returns, drawdown, turnover, exposure, costs, annual/fold results, and benchmark comparisons together. Keep final-holdout results out of the development dashboard until the declared evaluation step.

Freeze strategy, feature, training/refit recipe, data conventions, and execution profile before the independent-data re-test. A second vendor over the same dates checks data dependence; it is not a fresh temporal holdout. No result receives a “profitable” or “safe” certification from passing engine tests.

## Build versus reuse

Provisional preference: a small daily portfolio core with a narrow, auditable contract. This fits the Python/local scope, but it creates an ongoing financial-correctness maintenance obligation. Do not commit to a full custom engine solely from this documentation review.

Before final production selection, run a bounded reuse evaluation of LEAN and Zipline Reloaded against the same small fixture suite. Compare event semantics, corporate-action inputs, decision tracing, adapter effort, reproducibility, and Windows/Linux packaging. Inspect source and pinned dependency licenses before embedding anything. The initial reference core establishes those fixtures and an executable contract using the standard library; it does not finalize this selection. Require measured evidence that adaptation is smaller and maintainable, or retain the bounded core with selected independent-engine cross-checks.

The standard LEAN CLI workflow involves Docker and organization requirements; that does not mean the independently packaged LEAN engine inherently requires that workflow. Our customer application must meet the repository's no-terminal/no-Docker requirement regardless of implementation. [LEAN CLI setup](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started)

Commercial embedding needs particular care with source-available dependencies. VectorBT's repository describes Apache 2.0 with the Commons Clause; do not assume its redistribution terms match ordinary Apache 2.0. Verify the exact pinned version and intended use before adoption. [Repository license](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md)

## Staged implementation and acceptance

| Stage | Deliverable | Exit condition |
| --- | --- | --- |
| 1. Contract and fixtures | Event ordering, schemas, account profile, hand-calculated synthetic datasets, expected ledgers. | Expected outcomes are independently reviewable without strategy-performance results. |
| 2. Reuse evaluation | Small comparable LEAN/Zipline runs and integration/packaging findings. | Recorded engine choice based on correctness, fit, and maintenance burden. |
| 3. Working vertical slice | Snapshot → one transparent strategy → shared-cash simulation → ledger/report. | Fixtures and causality checks pass; every order outcome is traceable; identical inputs reproduce results. |
| 4. Data qualification | Alpaca adapter, local snapshots, capability checks, action/calendar validation. | Dataset limitations gate the claims and strategy families it can support. |
| 5. Research campaign | Benchmarks, deterministic strategy configurations, cost stress, walk-forward runner, experiment registry. | Every candidate uses the same frozen financial contract; unsuccessful runs remain visible. |
| 6. ML and desktop workflow | Prediction provenance, training boundaries, template setup and Trade Explorer. | Models use the same engine; observed users can explain assumptions and trace a trade without developer help. |

Measure runtime and peak memory on a published machine/dataset/configuration for cold and warm runs. Include a multi-year, hundreds-of-assets workload and repeated experiments. Set performance targets from those measurements; do not claim superiority from library marketing or incomparable examples.

For usability, observe an initial small group of technical traders completing setup, changing costs, explaining a rejected order, and reproducing a saved run. A proposed target is a first template backtest within ten minutes without a terminal. Record errors and misunderstanding, not only completion time. This validates the claimed simplicity advantage before substantial UI investment.

The local data contract, reference market-order core, and synthetic conformance fixtures are implemented. The next gates include actual-provider qualification, richer execution profiles, reuse/cross-engine evaluation, and Windows result checks. No production strategy has been trained or selected from these engineering runs.
