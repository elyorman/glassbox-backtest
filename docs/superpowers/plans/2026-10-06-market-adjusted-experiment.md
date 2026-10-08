# Market-adjusted experiment implementation checklist

> Paused, not run (2026-10-08). See [the evidence standard](../../STRATEGY_EVIDENCE.md) and [the research ledger](../../RESEARCH_LEDGER.md).

Future work under [the frozen specification](../../MARKET_ADJUSTED_EXPERIMENT.md).
The completed review adds no strategy implementation or portfolios. Supports
PR-05, PR-06, PR-08 and PR-13. Reuse the virtual environment and shared engine;
no Git actions, paid acquisition, downloads or forecasting-model training.

1. Implement and test causal monthly-return/residual features and explicit
   strategy configurations in new modules, retaining existing defaults/contracts.
   Check month anchors, 36/30-month fits, eleven-month formation, lagged monthly
   Treasury compounding, hand-calculated OLS/dispersion, degeneracy, missing
   sessions, action continuity, future-prefix invariance, common eligibility,
   ranking and next-open accounting. Preserve fit observations in decisions.
2. Add a research-only adapter for four ranked recipes and three references on
   both panels. Test method/input/source provenance, dates/resets, exact 126-slot
   budget, failures, four comparisons, incomplete status, fold/neighbor/delay
   gates, both-panel freeze and prohibition on promoting controls.
3. Run relevant tests and the full suite; review the implementation. Inspect
   context history capacity and decision size for three years of daily input.
   Archive/register the complete runtime before outcomes, retaining amendments.
4. Execute 126 new portfolios, independently reconstruct ledgers and causal
   scores/requests, retain failures and verify unrounded decisions. Changed
   starts/resets prohibit old benchmark reuse.
5. Export local reports with units, fit/eligibility/overlap/exposure/contribution
   diagnostics and uncertainty. Seal evidence, verify old sources/methods/data
   and the forward journal, update status, and stop without tuning.

Only the parent can freeze for later exploratory retesting. Independent
qualification, fresh temporal evidence, Desktop delivery and the three-to-four
distinct-strategy release requirement remain separate work.

