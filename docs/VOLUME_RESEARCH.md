# Unusual dollar-volume research

The causal volume feature and monthly ranking strategy implement the
[October 5 frozen specification](NEXT_EXPERIMENT.md). This is an exploratory
research adaptation, not a qualified built-in strategy or an academic replication.
Supports PR-05, PR-06, PR-08 and PR-13; Desktop delivery remains separate work.

The feature compares completed signal-day `raw_close × raw_share_volume` with
the preceding 49 exact sessions (54 for the single sensitivity neighbor).
Equal observations receive midpoint mass. It retains every input close, share
volume and calendar ordinal in saved signal decisions. Missing sessions and
nonpositive volume are ineligible; later observations/actions cannot alter the
decision. Scores are ranks of observed activity, not probabilities of profit.

The explicit `VolumeConfig` and `VolumeStrategy` live in
`python/quant_core/strategies/volume.py`. They reuse common execution, allocation,
portfolio accounting and preflight contracts. The older closed family registry
and all its defaults remain unchanged. The research adapter is
`python/research/volume_campaign.py`; production code never imports research.

The registered study uses both unchanged cached Alpaca panels, fixed monthly
top-five selections, five 19% target slots, $100,000 independent cash resets,
$5 raw-price and $10 million 20-session average-dollar-volume eligibility,
and a split-aware 1% share-volume entry cap. Execution uses the next raw open,
10/25 basis points per side and the predeclared two-session delay stress.
Idle cash earns zero. Historical Treasury returns are the Sharpe reference.

The 55-session neighbor and ascending low-volume control cannot replace the
parent. Freezing requires both samples to pass the unchanged return-seeking
full rule plus a strictly positive mean aligned net parent-minus-control daily
return at both continuous cost levels. Missing required evidence is incomplete.
Score ties, dispersion and selections below 0.90 are diagnostics, never new gates.

The finite budget is 54 new simulations and 54 exact reused reference scenarios.
SPY reserve, same-universe equal weight and cash are verified against the earlier
data, source, configuration, execution and bundle hashes before new outcomes.
All earlier five-family studies and already exposed dates remain in the ledger.
Paired stationary bootstraps use 500 repetitions, seed 1729 and blocks 20/60;
the new three-recipe search diagnostic excludes earlier searches.

Independent data/use/actions/identity/delisting qualification remains outstanding.
Both panels are conditioned on surviving/current stocks with supported histories.
Unknown dividend payment dates remain withheld receivables (336 original,
602 broader). Chronological fixed-rule folds are not fitted walk-forward or
fresh OOS. Paid acquisition remains deferred under the user's Alpaca decision.

## Execution evidence

The verified results reject the parent on both samples under the frozen rule.
All 108 bundles pass full ledger, causal signal/order, source/configuration,
reference-origin, decision, diagnostic and uncertainty checks. The continuous sample runs from
January 31, 2017 to October 2, 2026. Costs below are basis points per side.

| Panel | Parent CAGR, 10 bps | Parent CAGR, 25 bps | Equal-weight CAGR, 10 bps | Parent Sharpe, 10 bps | Equal-weight Sharpe, 10 bps | Folds passing both costs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original 22 | 14.13% | 11.31% | 18.25% | 0.744 | 0.972 | 1/3 |
| Broader 47 | 14.04% | 10.54% | 17.01% | 0.624 | 0.830 | 0/3 |

Sharpe is below equal weight at both costs on both panels; delayed execution
also fails the objective. Neighbor positivity does not rescue those failures.
The direction gate fails at both costs in both panels: mean net daily
parent-minus-control returns are negative. On the original panel at 25 bps,
parent CAGR is slightly higher than control CAGR; that does not change the
predeclared **arithmetic daily-mean** direction screen. The low-volume control
remains a counterexample, not a replacement candidate. No candidate is frozen
across samples and zero strategies are qualified.

Selected scores below 0.90 are 218/585 (37.26%) original and 95/585 (16.24%)
broader. Each of 117 monthly sessions has at least one cross-stock score tie;
that does not mean every selected stock or selection cutoff is tied. The fixed
security-ID tie breaker remains unchanged. These are diagnostics, not reasons
to add a threshold or rerun.

The original 54 new portfolios were saved, but an order-request replay verifier
compared strategy security order with the engine's sell/buy/priority order and
marked finalization failed. A separate recovery version corrects only that
verification and its provenance guards. All 54 failed records and original
bundles remain in a 1,610-file seal. Recovery reuses saved outcomes with zero
additional financial simulations; feature, strategy, accounting, inputs and
criteria are unchanged. Independent fixtures reproduce priority ordering and
sell-before-entry behavior. The full suite passes 604 tests.

Local evidence: `local/volume-2026-10-06/` retains the original attempt;
`local/volume-2026-10-06-finalized/` contains the recovered registration/results.
The [local report](../local/volume-2026-10-06-finalized/REPORT.html) provides panel
filters, all 108 scenario entries, direction comparisons, score diagnostics,
uncertainty intervals and overlap with momentum/high-anchor. CSV/JSON exports
and a completion seal retain exact figures and provenance. The report's links
and panel markup are checked; browser rendering is not claimed as tested.

Reverify without writing another completion artifact, using the frozen runtime:

```bash
PYTHONPATH=local/volume-2026-10-06-finalized/source-archive \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c \
'from pathlib import Path; from research.volume_campaign import verify_campaigns; r=verify_campaigns(Path("local/volume-2026-10-06-finalized")); print({k:p["verified_bundles"] for k,p in r["panels"].items()})'
```

The original SMA200 forward journal remains unchanged and requires its archived
63-file runtime; it records prospective signals/targets, not portfolio returns.
