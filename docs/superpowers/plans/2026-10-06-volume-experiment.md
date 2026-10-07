# Frozen volume experiment implementation

Authority: `docs/NEXT_EXPERIMENT.md` and the byte-frozen specification in
`local/research-decision-2026-10-05/NEXT_EXPERIMENT_SPEC.json`.
Supports PR-05, PR-06, PR-08 and PR-13. Execution is inline, using the existing
virtual environment; no Git operations, market-data collection or tuning.

1. Test and implement causal raw-dollar-volume percentile and an explicit volume
   strategy in new modules. Retain the previous 64 runtime files unchanged.
   Check hand calculations, calendar gaps, invalid volume, ties, raw split
   units, future prefixes, allocation and next-open portfolio accounting.
2. Test and implement a research campaign adapter with exact specification,
   source, data, reference-origin and finite-budget guards. Reuse existing
   accounting, ledger audits, economic criteria and overlap calculations.
   Add the predeclared direction gate, volume diagnostics and control uncertainty.
3. Run the full test suite and review the implementation before registration.
   Archive the runtime and bind all sources and inputs before any outcomes.
4. Execute 54 new simulations and verify/copy 54 unchanged references. Retain
   every failure, verify all bundles and recompute financial/decision evidence.
5. Export the report, comparison CSVs and completion seal. Update navigation
   and status while preserving frozen method documents and original navigation
   bytes. Verify all old seals and the unchanged forward signal journal.

Shared interfaces: the feature returns exact observations and a score/reason;
the strategy consumes only completed context and emits common SignalDecision
and OrderBatch contracts; the campaign builds this strategy for the three new
recipes and the existing builder for references. The existing closed family
registry remains unchanged. Feature provenance retains each required raw close,
raw share volume and calendar ordinal in decisions, bound to the snapshot.

Review focus: causal calendar boundaries, split units, signal/execution timing,
partial fills and cash, undefined direction/Sharpe evidence, strict benchmark
reuse, no post-registration source changes or parameter rescue, complete budget
and honest qualification labels.

Progress and command evidence are retained in ignored local logs and the new
campaign's registration/completion manifests. A feature-test import failure is
the expected initial red result for these absent modules.

## Execution ledger

- Feature/strategy and campaign gates implemented in three new modules; the
  existing 64 runtime files remain unchanged.
- Pre-outcome review corrected cross-panel freeze publication and exact
  allocation/uncertainty/budget binding. Initial full suite: 601 tests passed.
- Original registration archived 67 files before 54 financial simulations.
  All 54 new portfolios and 54 unchanged references were saved. Order-request
  finalization then failed on all new portfolios because the replay verifier
  compared security order with the engine's sell/buy/priority order.
- The original history was verified with its archived runtime and sealed:
  1,610 files, all 108 saved bundles and all 54 failed finalization records.
- Independent priority-buy and sell-before-entry fixtures reproduced the bug.
  Repair changes only `research/volume_campaign.py`; the feature, strategy and
  accounting sources remain byte-identical. Recovery guards bind the full
  original failure seal, permit only this postprocessing source change and check
  recovered financial hashes/failure origins. Final full suite: 604 tests passed
  in 31.585 seconds. Read-only review found no remaining important repair issue.
- Recovery reused all 108 saved bundles with zero additional financial
  simulations. Full archived-runtime verification passed all 108, including
  independent ledgers, causal decisions/requests, exact financial-outcome and
  failure origins, predeclared decisions, diagnostics and uncertainty.
  Both panels reject the parent and direction hypothesis; fold passes are
  1/3 and 0/3. No candidate is frozen and none is qualified.
- Report/export generation and evidence sealing follow verification; their
  semantic checks and preserved-source/input coverage are recorded in the
  finalized completion manifest. No financial rerun, tuning, model training,
  purchase, broker action or Git operation was performed.
