# Quantitative Research Platform

Local-first research software for US ETFs and equities: built-in investment
plans with an honest track record, a realistic backtester, risk and sizing,
and a monthly order sheet that says what to buy and why. Everything runs on
the user's computer with the user's own data key.

The goal: **strong enough that a quant can audit it, simple enough that a smart
non-trader can use it in ten minutes.**

- [PROJECT.md](PROJECT.md): product requirements, commercial model, decisions.
- [Roadmap](docs/ROADMAP.md): the V1 tester release, build order and status.
- [Evidence standard](docs/STRATEGY_EVIDENCE.md): how a built-in plan qualifies.
- [Research ledger](docs/RESEARCH_LEDGER.md): every study, including failures.

## What exists

| Area | State |
| --- | --- |
| Market data | Tiingo download and import (the tester release's provider), frozen research datasets with Treasury 3-month cash rates, CSV/JSON/Parquet snapshots, EODHD import, provider adjustment cross-checks, data-quality checks, dated index membership. |
| Backtester | Next-open fills, shared cash, costs, idle-cash interest, splits/dividends/delistings, stops, read-only reference series, entry-to-exit trade records, full audit bundles. |
| Risk and sizing | Position, cash, exposure, liquidity and drawdown limits; fixed, fractional and ATR sizing; every refusal recorded. |
| Strategies | The four rule-based V1 plans (multi-asset trend, dual momentum, US sector rotation, inverse volatility) with hand-checked tests, not yet run on real data; six research rule families. The ML plan: not built yet. |
| Validation | Campaign framework, stationary bootstrap, deflated Sharpe ratio, cost and period breakdowns. Evidence-pack report: not built yet. |
| ML, order sheet, Rewind, UI, packaging | Not started; see the roadmap. |

Contracts: [data layer](docs/DATA_LAYER.md), [data integration](docs/DATA_INTEGRATION.md),
[universes](docs/UNIVERSES.md), [backtester](docs/BACKTESTER.md),
[risk](docs/RISK_MANAGEMENT.md), [strategies](docs/STRATEGIES.md),
[validation](docs/VALIDATION.md), [reproducibility](docs/REPRODUCIBILITY.md).
The SMA200 [forward signal journal](docs/FORWARD_SHADOW.md) has its first
capture window after the 2026-10-30 close.

Research from October 2026 (stock campaigns, SEC fundamentals studies, their
scripts and reports) was removed from the working tree; the git tag
`archive/research-2026-10` keeps it, and the ledger records every outcome.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[parquet]'
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests
```

Credentials go in `.env` (gitignored; see `.env.example`). Downloaded data and
generated artifacts go in the ignored `local/` directory. Never commit
credentials or third-party datasets.
