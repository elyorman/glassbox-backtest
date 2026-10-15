# Glassbox Backtest

Transparent, auditable Python backtests of four published ETF investing rules: multi-asset trend
following, dual momentum, US sector rotation and inverse volatility. Every trade traces to the rule and
numbers behind it, accounting is exact `Decimal`, and registered studies produce evidence packs with
bootstrap intervals and the deflated Sharpe ratio. Everything runs locally with your own Tiingo key.

**Status:** published as is (October 2026). The engine, the plans and the evidence tools work and are
tested; the app described in [PRODUCT.md](PRODUCT.md) (order sheet, screens) was not built.

| Part | Status |
| --- | --- |
| Data: Tiingo prices, Treasury cash rates, frozen datasets, quality checks | Built |
| Backtester: next-open fills, costs, dividends, interest, full audit bundles | Built |
| The four plans | Built; one exploratory run on real data, recorded in the [research ledger](docs/RESEARCH_LEDGER.md) |
| Risk and money management in the engine | Built; not yet wired to the plans |
| Registered studies and evidence packs | Built; no plan registered yet |
| Monthly order sheet, local web app | Not built |

## Quick start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[parquet]'
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests
```

No market data is included. Put a free [Tiingo](https://www.tiingo.com) key in `.env` (see
`.env.example`) as `TIINGO_API_KEY=...`, then freeze a dataset of every ETF the plans trade plus
Treasury rates (exit code 3: request budget spent, run it again later):

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.cli download-tiingo --output local/data/<name>
```

Backtest a plan (run with `PYTHONPATH=python`):

```python
from datetime import date
from decimal import Decimal
from pathlib import Path

from quant_core.analytics.evidence import results
from quant_core.backtest import RunConfig, run_backtest
from quant_core.data.dataset import load_dataset
from quant_core.execution import ExecutionProfile
from quant_core.strategies.plans import build_plan, builtin_plans

data = load_dataset(Path("local/data/<name>"))
trend = builtin_plans()[0]  # multi_asset_trend; dual momentum and inverse volatility also need data.rates
start, costs = date(2007, 4, 30), ExecutionProfile("10")
source = build_plan(data.snapshot, trend, start, costs)
run = run_backtest(data.snapshot, source, RunConfig(Decimal(100000), costs, trend.universe, start,
                                                    cash_rates=data.rates))
print(results(run))  # CAGR, volatility, Sharpe over T-bills, drawdown, turnover, trades...
```

Registered studies (`check` rehearses every run and saves nothing; `run` writes the runs, `pack.json`
and `PACK.md`):

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli check \
  docs/registrations/<study>.json --dataset local/data/<name>
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli run \
  docs/registrations/<study>.json --dataset local/data/<name> --output local/<study>
```

## Documentation

[docs/ENGINE.md](docs/ENGINE.md): technical reference · [docs/RESEARCH_LEDGER.md](docs/RESEARCH_LEDGER.md):
every study, including failures · [PRODUCT.md](PRODUCT.md): the intended app · [AGENTS.md](AGENTS.md):
rules for coding agents

## Disclaimer and license

Research software, not investment advice. Backtests describe the past under stated assumptions; they
do not predict returns, and every plan here has lost money in some years. Released under the
[MIT license](LICENSE), provided as is, without warranty.
