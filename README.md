# Quantitative Research Platform

Local daily US equity and ETF research software under development. [PROJECT.md](PROJECT.md) defines the product scope and commercial release requirements.

Continuing from another account? Start with the [repository handoff](docs/HANDOFF.md).
Source, tests and methods are in Git; credentials and generated research/data
under `local/` remain on the existing machine and are absent from a fresh clone.

The product promise is **serious quantitative stock research with
institutional-style validation and risk discipline, without requiring coding or
trust in a black box**. The intended workflow combines discovery, explanation,
realistic testing, robustness, risk/sizing and local saved evidence. Desktop
includes no-code rule-based strategy creation and perpetual purchased-version
use; Developer/Source adds source access and model training. Third-party data
and optional major upgrades may cost separately. The [15 requirement groups](PROJECT.md#product-requirements-and-acceptance-contract)
define acceptance criteria; they describe the product we must deliver, not
capabilities already completed by the current engine.

V1 must include **3–4 distinct, well-researched, validated built-in strategies**
(minimum three; target four), ready for no-code use. The [qualification contract](PROJECT.md#reference-strategies)
requires documented rules, costs/risk, honest OOS/robustness evidence and an
independent-data retest. The current experimental recipes have not yet qualified.

The agreed build order is:

1. Market-data layer
2. Backtester
3. Risk/money management
4. Strategies
5. Validate strategies
6. ML models
7. Scanner/analytics
8. Desktop UI
9. Packaging/licensing/website

Current implementation: the local market-data foundation, daily portfolio backtester, risk/money-management layer, five rule-based strategy families and the Stage 5 chronological validation workflow. Campaigns freeze their recipes/criteria, retain every attempt and failure, compare declared benchmarks/costs, report paired block-bootstrap uncertainty, and gate final evaluation on a frozen nominee and independent-data crosscheck. Signals, risk decisions and results are exported in reproducible JSON/CSV audit bundles and checked with synthetic hand-calculated portfolios. Actual-provider qualification, the qualified empirical strategy campaign and commercial qualification remain pending; no profitable strategy has been selected.

See [the data-layer contract](docs/DATA_LAYER.md), [backtester API](docs/BACKTESTER.md), [risk research and contract](docs/RISK_MANAGEMENT.md), [strategy rules](docs/STRATEGIES.md), [validation workflow and runnable example](docs/VALIDATION.md), [backtester design](docs/BACKTESTER_DESIGN.md), and [strategy research plan](docs/RESEARCH_PLAN.md).

Version 0.5.0 adds the [audit corrections](docs/AUDIT_REMEDIATION.md),
[EODHD response/API and optional Parquet integration](docs/DATA_INTEGRATION.md),
[dated historical membership](docs/UNIVERSES.md), and
[exact-runtime source preservation](docs/REPRODUCIBILITY.md). The developer
backtest CLI accepts JSON or Parquet and can apply dated membership before
strategy ranking. Tests cover synthetic accounting and causality; these
foundations do not establish historical provider or strategy qualification.

Version 0.5.1 adds [corporate-action auditing and a frozen-data preflight](docs/DATA_QUALIFICATION.md),
with visible missing dates, reviewed split classifications and immutable input
bindings. Independent market exports and human qualification evidence are still
required before the frozen retest can run.

The [EODHD public-demo pilot](docs/EODHD_PILOT.md) now verifies real price/action
imports and records missing access and unresolved open/volume conventions.
Its selected-symbol sample does not qualify the full independent retest.

Current research uses [the existing Alpaca data](docs/ALPACA_RESEARCH.md).
The [universe-transfer study](docs/UNIVERSE_TRANSFER.md) tests unchanged recipes
on a mechanically sampled broader panel, with all exclusions and survivor
limitations retained. The [forward SMA200 journal](docs/FORWARD_SHADOW.md)
records prospective monthly signals locally; its first window is October 30.
The separately registered [52-week-high adaptation](docs/HIGH_ANCHOR_RESEARCH.md)
adds 36 new simulations across both panels, with 54 verified reference scenarios.
Both panels reject this recipe under unchanged criteria; all 90 result entries
pass verification. That stage passed 577 tests, with zero qualified strategies.
The [five-family decision review](docs/RESEARCH_DECISION_REVIEW.md) consolidates
the existing failures and freezes a [next volume-ranking specification](docs/NEXT_EXPERIMENT.md),
including a reversed-direction control. The [volume experiment](docs/VOLUME_RESEARCH.md)
has now run 54 new portfolios plus 54 verified references. Both samples reject
the parent on benchmark-relative Sharpe and the direction screen; all 108 saved
bundles pass full verification. A verifier-ordering repair reused the original
outcomes with no financial reruns and retained every failure record. The full
suite passes 604 tests. Zero strategies are qualified; no post-result tuning.
Paid independent acquisition is deferred until promising customer interest;
development and exploratory backtests continue with disclosed data limitations.

The [research design review](docs/RESEARCH_DESIGN_REVIEW.md) checks all six stock
hypotheses and distinguishes implementation, portfolio-role and data limitations.
It freezes a [market-adjusted momentum specification](docs/MARKET_ADJUSTED_EXPERIMENT.md)
with matched ordinary/scaled momentum controls and a future 126-portfolio budget.
Cached inputs are mechanically sufficient; no new portfolio or model was run.
Implementation/runtime registration remain next work. This momentum-family
adaptation does not automatically add a distinct qualified strategy.

The [corrected-engine replay](docs/ENGINE_REPLAY.md) freshly reran and verified
all 99 stock trials. Equity paths, fills, metrics and parent decisions are
unchanged; the original campaign remains preserved.

The frozen [stock campaign](docs/RESEARCH_PLAN.md#stock-campaign-results--2026-10-03)
retains 99 portfolios. SMA200 passed its original-panel defensive exploratory
screens, but fails the broader transfer study's fold-stability requirement;
zero strategies are commercially qualified. Previously inspected history stays exposed. The
[research status](docs/RESEARCH_STATUS.md) consolidates SEC/fundamental study
findings and links the original evidence. New transfer results are separately
registered; no model training was run.

```bash
python3 -m venv .venv
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests -v
```

Keep downloaded data and generated artifacts in ignored `local/` storage. Never put API credentials or third-party research datasets in Git.
