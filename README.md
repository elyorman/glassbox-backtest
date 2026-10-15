# Quant Platform

A local app that turns four published ETF investing rules into an exact monthly order sheet, with a
backtest traceable to every input and built-in risk and money management. It runs on your own
computer with your own Tiingo key.

| Part | Status |
| --- | --- |
| Data: Tiingo prices, Treasury cash rates, frozen datasets, quality checks | Built |
| Backtester: next-open fills, costs, dividends, interest, full audit bundles | Built |
| Four rule plans (trend, dual momentum, sector rotation, inverse volatility) | Built, tested on synthetic data |
| Risk and money management in the engine | Built; not yet wired to the plans |
| Evidence packs for registered studies | Built; no plan registered yet |
| Monthly order sheet, local web app in a native window | Not started |

## Quick start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[parquet]'
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests
```

## Data

Put your key in `.env` (gitignored; see `.env.example`) as `TIINGO_API_KEY=...`, then freeze a
dataset of every ETF the plans trade plus Treasury rates (exit code 3: budget spent, run it again later):

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.cli download-tiingo --output local/data/<name>
```

## Registered studies

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli check \
  docs/registrations/<study>.json --dataset local/data/<name>
PYTHONPATH=python .venv/bin/python -m quant_core.validation.study_cli run \
  docs/registrations/<study>.json --dataset local/data/<name> --output local/<study>
```

`check` rehearses every run and saves nothing; `run` writes the runs, `pack.json` and `PACK.md`.

[PRODUCT.md](PRODUCT.md): what V1 is · [AGENTS.md](AGENTS.md): how to work here ·
[docs/ENGINE.md](docs/ENGINE.md): technical reference · [docs/RESEARCH_LEDGER.md](docs/RESEARCH_LEDGER.md):
every study, including failures
