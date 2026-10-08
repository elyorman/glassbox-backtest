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

V1 must include **3–4 distinct, well-researched built-in strategies** (minimum
three; target four), ready for no-code use. They qualify under
[the built-in strategy evidence standard](docs/STRATEGY_EVIDENCE.md): disclosed
evidence packs with uncertainty and limitations, no return, Sharpe or
benchmark-beating threshold. V1 built-ins are ETF-based (candidates:
multi-asset trend, dual momentum, sector rotation, inverse-volatility
allocation). **No built-in is qualified yet.**

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

## Status

| Stage | State |
| --- | --- |
| 1 Data | Built: CSV/JSON/Parquet snapshots, EODHD import, dated index membership, action audit. Open: provider qualification, DuckDB query storage, memory and speed at index scale (all bars load as Python Decimal objects). |
| 2 Backtester | Built: next-open execution, shared cash, costs, splits/dividends/delistings, stops, audit bundles. Open: target/trailing exits, entry-to-exit trade records. |
| 3 Risk/sizing | Built. |
| 4 Strategies | Six research families implemented. ETF built-ins: not started. |
| 5 Validation | Campaign framework built; evidence-pack generator not started. |
| 6–9 | Not started. |

Research history, including every failed study and the cumulative trial
count, is in [the research ledger](docs/RESEARCH_LEDGER.md). Detailed
contracts: [data layer](docs/DATA_LAYER.md), [backtester](docs/BACKTESTER.md),
[risk](docs/RISK_MANAGEMENT.md), [strategies](docs/STRATEGIES.md),
[validation](docs/VALIDATION.md), [data integration](docs/DATA_INTEGRATION.md),
[universes](docs/UNIVERSES.md), [reproducibility](docs/REPRODUCIBILITY.md).
Historical research findings: [research status](docs/RESEARCH_STATUS.md).
The SMA200 [forward signal journal](docs/FORWARD_SHADOW.md) has its first
capture window after the 2026-10-30 close.

## Development

```bash
python3 -m venv .venv
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests -v
```

Keep downloaded data and generated artifacts in ignored `local/` storage. Never put API credentials or third-party research datasets in Git.
