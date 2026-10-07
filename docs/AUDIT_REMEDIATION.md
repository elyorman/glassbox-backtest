# Audit Remediation

Implements the three accepted recommendations from [the independent audit](../CODEX_AUDIT_2026-10-04.md), supporting PR-01–PR-06, PR-08 and PR-13. The [implementation plan](superpowers/plans/2026-10-04-audit-remediation.md) records task scope and verification.

Version 0.5.0 adds regression-covered whole-share rebalance buys, explicit exact split counts, zero-equity reporting, consistent final-session expiry, low-volatility selection and equivalent-cost scenario labels. Undefined returns remain visible; truncated scalar split ratios are not silently converted into guessed exact ratios. Decimal serialization of older snapshots and frozen configurations is retained.

The data checker now includes the exact jump threshold and flags changes near common forward/reverse split ratios after accounting for known actions. These are suspicious observations, not inferred corporate actions. Default checks retain warnings; explicit `--strict-discontinuities` on data/backtest commands (or `RunConfig(strict_discontinuities=True)`) blocks unresolved observations. It is a recorded, stricter policy rather than a hidden change to older diagnostic semantics.

Independent-provider reports preserve the original candidate list, trial count and report bindings. Their nominee-only diagnostic is explicitly labeled as not repeating the full selection search or providing a new temporal holdout.

Validation retains full-loss trials and saved ledgers with explicit undefined-return
status. A later period beginning at zero equity reports null metrics instead of
crashing or fabricating returns. Incomplete/undefined search trials remain in the
registered history and block nomination.

Independent final review identified three further issues, all corrected with
regressions: known dividends could look like missing splits, the missing-bar
diagnostic could bypass strict discontinuity checks, and frozen replay could load
unverified cached bytecode. Known splits/dividends now adjust only the comparison
reference; the strict gate remains independent; replay uses a clean verified
source-only copy. Original bars and frozen archives stay unchanged.

[Source preservation](REPRODUCIBILITY.md) keeps older runtimes and results verifiable. [Provider and Parquet integration](DATA_INTEGRATION.md) and [dated universes](UNIVERSES.md) provide usable data foundations. The backtest CLI accepts a JSON snapshot or Parquet bundle and `--membership universe.json`; membership is bound into source provenance and applied at the signal date. Removed members can be sold at the next scheduled rebalance. Unknown coverage fails closed. Static buy-hold/cash references retain their separate universes.

Remaining production work includes qualified historical provider data, index coverage and membership evidence, complete corporate-action/payment/delisting inputs, measured execution assumptions, Windows validation, trade entry-to-exit analytics and the rest of the product roadmap. These foundations do not qualify a strategy or satisfy the three-to-four built-in strategy release gate.

## Verification — 2026-10-05

The complete unittest suite passes **505 tests**, including the optional Parquet
checks. The corrected archived replay verifies **all 99 frozen stock portfolios**.
The original 113-file baseline and four historical source manifests retain their
recorded hashes. The new 59-file version-0.5.0 archive verifies and matches the
live source. The CLI smoke workflow imports synthetic original responses into
Parquet, applies dated membership, executes the expected three fills, and verifies
USD 1,000 ending equity. Eleven changed documents have no missing local link
targets. Details/logs are in ignored
`local/audit-remediation-2026-10-04/FINAL_VERIFICATION.json` and the execution ledger.
These are engineering/reproducibility checks, not new investment-performance evidence.
