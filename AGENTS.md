# AGENTS.md

How coding agents work in this repository. What V1 is: [PRODUCT.md](PRODUCT.md). How the engine
works: [docs/ENGINE.md](docs/ENGINE.md). Studies: [docs/RESEARCH_LEDGER.md](docs/RESEARCH_LEDGER.md).

## Ownership and git

- Glassbox Backtest (`elyorman/glassbox-backtest`) is Elyorjon Mannonov's personal project, MIT-licensed
  and independent of any employer.
  No employer name, work account, work email, issue tracker or work tooling may appear in code, docs,
  commit metadata or configuration. No tickets or ticket-prefixed names are needed.
- Commit with the personal identity configured for this repository, concise descriptive messages and
  no co-author or session trailers.
- Create branches, commit, push or open pull requests only when the owner asks. Never force-push
  `main`.
- Never commit credentials (`.env`), anything under `local/`, downloaded vendor data or generated
  results.
- These rules override generic workflow preferences from other contexts.

## Core principles

1. **Correctness first.** A financial number that looks plausible but is wrong is unacceptable.
2. **No look-ahead.** At session `t`, signals, features, sizing and execution use only what was
   known at `t`. Signals and fills happen on different sessions.
3. **Reproducibility.** Every run records the data, configuration and code hashes needed to
   reproduce and audit it.
4. **Provider independence.** Plans, backtests and risk never call a data vendor directly; data
   arrives as provider-neutral snapshots.
5. **Local-first.** Data, analysis, backtests and the app run on the user's computer. No mandatory
   cloud service, account or LLM API; nothing the user owns is uploaded anywhere.
6. **No hype.** Never write copy or UI that implies guaranteed returns, certainty or prediction.
   Show losses, limits and failed studies as plainly as gains.

## Engineering rules

- Money, prices and quantities are `Decimal`; binary floats are refused at every financial boundary.
- Every change to financial logic comes with tests in the same commit, hand-checked where possible.
- Every bug fix that could affect results comes with a regression test that fails without the fix.
- Prefer small, surgical changes that match the surrounding code; touch only what the task needs.
- When behaviour, commands or public settings change, update `docs/ENGINE.md` (or `PRODUCT.md`,
  `README.md`) in the same commit. The docs must match the code.
- When a financial assumption is uncertain, make it explicit (a setting or a stated assumption) and
  ask the owner; never choose one silently.
- Use the repository's virtual environment: `.venv`. Run the suite with
  `PYTHONPATH=python .venv/bin/python -m unittest discover -s tests`.

## Research rules

- **Register before running.** A built-in plan's evidence comes only from a registered study: the
  registration file is committed and tagged before its run, and the run happens once.
- **Every study in the ledger.** Each study, including failures and abandoned ones, gets a row in the
  research ledger. Existing outcomes and counts are never edited.
- **No tuning after inspection.** A configuration changed after seeing results is a new registration
  that counts as new trials; both outcomes stay on record.
- **Count trials.** Follow the counting rules in `docs/ENGINE.md` (Trial counts); when in doubt,
  record the larger defensible number and say why.
- Survivor-selected stock panels are never evidence for a built-in. Built-ins are ETF-based in V1.
- Rehearsing a registration with `check` runs it on the panel: those configurations count as trials.

## Workflow

- Keep changes small and finish them: tested, documented, committed when asked.
- Routine work needs no design documents, written plans or multi-round reviews. Ask the owner when a
  decision is genuinely theirs (scope, product behaviour, money assumptions, publishing).
- Report honestly: say what was verified and how, what was not, and what failed.
- Defer a feature rather than ship it half-built.
