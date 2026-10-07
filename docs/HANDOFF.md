# Repository handoff — 2026-10-07

This checkpoint preserves the work for Elyorjon Mannonov when
continuing from another account. The repository is
`https://github.com/elyorman/quant-platform`; the existing machine's origin uses
the `github-elyorman` SSH alias. Account access and SSH configuration are local
setup, not part of the quant runtime. No new research implementation is part of
this wrap-up.

## Read first

1. [AGENTS.md](../AGENTS.md) — engineering and financial invariants.
2. [PROJECT.md](../PROJECT.md) — product requirements, roadmap and release gates.
3. [Research status](RESEARCH_STATUS.md) — completed studies and limitations.
4. [Design review](RESEARCH_DESIGN_REVIEW.md) and
   [market-adjusted experiment](MARKET_ADJUSTED_EXPERIMENT.md) — the next task.

The product is a local-first quantitative stock research and risk platform,
with explainable/no-code workflows and perpetual purchased-version use. V1
requires at least three distinct qualified built-in strategies, targeting four.
The engineering foundation is implemented; the full commercial product is not
finished. There are **zero production-qualified strategies** and no trained
production forecasting models.

## Completed foundation and research

The market-data/import layer, daily portfolio backtester, risk/position sizing,
rule strategies, validation/provenance and local reporting are implemented.
See [data integration](DATA_INTEGRATION.md), [backtester](BACKTESTER.md),
[risk](RISK_MANAGEMENT.md), [strategies](STRATEGIES.md),
[validation](VALIDATION.md) and [audit remediation](AUDIT_REMEDIATION.md).

Six stock hypotheses were examined on original 22-stock and broader 47-stock
panels. The ledger retains 288 unique stock scenarios, with copied references
identified; these are not independent ideas. Earlier sector-ETF and robustness
searches remain disclosed. Momentum, reversal, low volatility, high proximity
and unusual-volume parents fail their registered screens. SMA200 passes its
original-panel defensive screen but fails the broader fold requirement. Do not
change those findings or promote a winning control after inspecting outcomes.

The volume campaign's initial request-order verifier failure and its separate
saved-outcome recovery are preserved. All 108 saved bundles were verified;
recovery performed zero additional financial simulations. Details are in
[volume research](VOLUME_RESEARCH.md).

The last completed task was a research-design review, not a new backtest.
It checked 8,891 prior manifest file entries, twelve parent/panel findings,
cached monthly/lagged-cash coverage and unchanged runtime/journal evidence.
Its final evidence seal contains 31 files. Review-script manifest-name and
Unicode-minus comparison errors were retained and corrected without financial
execution; the latter was a reporting-check issue, not incorrect returns.

## Exact next task

Implement the [frozen market-adjusted momentum specification](MARKET_ADJUSTED_EXPERIMENT.md)
and follow its [implementation checklist](superpowers/plans/2026-10-06-market-adjusted-experiment.md).
Do not start performance runs before correctness tests, review and an archived
implemented-runtime registration.

The byte-frozen method SHA-256 is
`5ebd7c6582feacffca17e6de5aae8ae5458edaf670ae94cfba3edcb0904ac378`.
Its ignored registration envelope is
`local/research-design-review-2026-10-06/NEXT_EXPERIMENT_SPEC.json`.
The method freeze does not register an unimplemented runtime.

One 36-month market-adjusted parent, one 30-month neighbor, ordinary momentum
and standardized-total-return controls, plus SPY/equal-weight/cash references
are specified. Both existing panels, common January 31, 2019 start, fixed folds,
10/25 bps per side and second-open delay give **126 new portfolios**. Old
benchmark curves cannot be reused after changed starts/resets. Only the parent
can freeze after both panels pass. This is a momentum-family adaptation, not
automatically another distinct strategy toward the release quota.

The existing SMA200 journal is separate and unchanged: it has zero signal
records at this handoff. Its first capture window is after the October 30, 2026
close and before the November 2 open. It records prospective signals/targets,
not portfolio returns or broker orders. Use its frozen source archive for
verification/capture; see [forward journal](FORWARD_SHADOW.md).

## Data policy and local files

Continue existing Alpaca/cached data for disclosed exploratory research.
Paid acquisition is deferred until promising customer interest. Current/surviving
panels, missing dividend payment dates, corporate-action/identity/calendar/
delisting completeness, revisions and project-use qualification remain unresolved.
All inspected 2016–2026 history is exposed. Better data cannot create an edge or
restore a fresh temporal holdout. Qualified independent-data/use evidence and
genuinely uninspected evidence remain required before production claims.

Git contains source, tests, product requirements, research methods/status and
handoff instructions. It deliberately excludes `.env`, credentials, `.venv`,
machine-specific `.claude` permission settings and **all `local/` artifacts**.
Existing synthetic test fixtures are included; vendor research data is not.

On the original machine, keep the existing full checkout in place.
Changing the chat/account does not relocate these files. A fresh clone on another
computer does **not** contain datasets, frozen source archives, saved outcomes,
local registration envelopes or reports. Keep this working directory. If moving
machines, separately preserve the private `local/` directory in user-controlled
storage, verify its seals and respect provider rights; GitHub is not its backup.
Recreating files from downloads is new evidence, not recovery of frozen bytes.

Important ignored roots on the existing machine:

- `local/stock-data-2026-10-03-frozen/` — original stock snapshot/readiness.
- `local/stock-campaign-2026-10-03-finalized/` — original stock campaign.
- `local/stock-engine-replay-2026-10-05/` — corrected-engine replay.
- `local/universe-transfer-2026-10-05-v2/` — broader snapshot and transfer study.
- `local/high-anchor-2026-10-05/` — high-proximity experiment.
- `local/volume-2026-10-06/` — original outcomes and failed finalizations.
- `local/volume-2026-10-06-finalized/` — recovered/verified volume evidence.
- `local/research-design-review-2026-10-06/` — review and next-method freeze.
- `local/robustness-inputs-2026-10-03/` — bound historical Treasury reference.
- `local/sma200-forward-2026-10-05/` — frozen prospective signal journal.

Earlier ETF, SEC/fundamental and qualification artifacts are also in `local/`;
keep the complete directory rather than just this shortlist. Fundamental-study
coverage remains infeasible/incomplete; no fundamental strategy performance
or bulk continuation is silently authorized by this handoff.

## Environment and verification

Requires Python 3.12 or newer. Reuse the existing `.venv` on this machine. For a
fresh checkout, create a virtual environment and install the package if needed:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests
```

Parquet support is optional (`pip install -e '.[parquet]'` inside the virtual
environment). Tests requiring unavailable optional support may be skipped;
do not treat such skips as full Parquet verification. Windows uses
`.venv\Scripts\python.exe` and the shell's environment-variable syntax.

Wrap-up verification on 2026-10-07: **604 tests passed in 31.997 seconds** on
the existing Linux environment. This is engineering evidence, not strategy or
Windows release qualification. No production runtime changed in this wrap-up.
Follow the frozen-source commands in each dossier when verifying old campaigns;
current-source substitution can invalidate archived evidence.
