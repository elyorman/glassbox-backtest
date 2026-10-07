# Research design review — 2026-10-06

Prepared for Elyorjon Mannonov. Supports PR-05, PR-06, PR-08 and
PR-13. Uses sealed outcomes and cached input coverage; adds **zero simulations**.

**Decision:** Preserve previous findings and freeze one bounded
[market-adjusted momentum experiment](MARKET_ADJUSTED_EXPERIMENT.md), with
matched ordinary and volatility-standardized momentum controls. Paid acquisition
remains deferred under the user's [Alpaca decision](ALPACA_RESEARCH.md).

## What failed, and what remains useful

The [five-family review](RESEARCH_DECISION_REVIEW.md) retains 234 unique stock
scenarios. The [volume study](VOLUME_RESEARCH.md) adds 54 new simulations and
54 reused references: 288 cumulative unique stock scenarios, **six parent
hypotheses on two panels**, not 288 independent ideas. Earlier ETF/robustness
searches remain part of the selection history. This design uses those findings.

| Parent | Original / broader CAGR at 10 bps | Original / broader CAGR at 25 bps | Registered limitation |
| --- | ---: | ---: | --- |
| Momentum | 21.97% / 24.15% | 20.95% / 22.87% | Sharpe below equal weight; fold and delay failures. |
| SMA200 | 11.06% / 10.33% | 10.66% / 9.97% | Continuous defensive objective passes both; broader folds pass 1/3. |
| Short reversal | 6.43% / 9.55% | −3.15% / −2.27% | Cost sensitivity and weak net risk-adjusted comparisons. |
| Low volatility | 8.71% / 9.87% | 8.39% / 9.16% | Original return-floor and broader drawdown failures. |
| Nearness to high | 14.01% / 9.47% | 12.25% / 6.73% | Sharpe and transfer failures. |
| Unusual volume | 14.13% / 14.04% | 11.31% / 10.54% | Sharpe, folds, delay and direction failures. |

Figures are calendar CAGR, with costs per traded side. Saved figures and decisions
remain in the original evidence and the new local `parents.csv`; comparisons use
unrounded values. Zero strategies are qualified. SMA200's original defensive
finding remains exploratory. Its broader stressed fold return-floor misses are
approximately 0.014 and 0.405 percentage points; do not describe them as collapse
or relax the threshold after inspection.

Volume's mean net daily parent-minus-control return is negative at both costs
on both panels. Original 25-bps parent CAGR is slightly higher than control CAGR;
arithmetic means and compound returns are different statistics. Do not promote
the low-volume control after seeing its returns.

## Design limitations, separate from data limitations

**Hypothesis fidelity:** Most ranked stock studies use five equal slots monthly:
approximately 23% of the original panel and 11% of the broader panel before
eligibility. Shared mechanics and thin cross-sections may obscure differences
between hypotheses. Month-end unusual-volume sampling is a substantial
adaptation of event-based research; top five does not ensure extreme activity.
The volume diagnostics already demonstrate this issue. Failures reject our
registered implementations, not entire published strategy families.

**Exposure/concentration:** Momentum's descriptive SPY betas are 1.144 and 1.271.
The largest contributors account for 29.40% and 27.35% of the sum of positive
asset P&Ls; broader top three account for 60.70%. This motivates testing exposure
adjustment. It does not prove beta caused failure or establish significant alpha.
We have not simulated removing those names and will not blacklist them.

**Execution:** Reversal's full-period notional-turnover ratios are 605.41 and
775.42; the paired cost cases reduce CAGR by 9.58 and 11.82 percentage points.
That includes changed quantities/fills/compounding, not just fees. Daily bars
cannot justify a convenient limit-fill model to rescue this behavior.

**Portfolio role:** Defensive strategies already have downside-protection and
return-retention objectives distinct from return-seeking Sharpe comparisons.
Useful defense need not win every return statistic, but failed predeclared gates
remain failed. Redesigning portfolio breadth or role would be a separately
registered study, not a reinterpretation of old outcomes.

**Search reuse:** All inspected 2016–2026 history remains exposed. New recipes,
folds or a second provider do not restore a fresh temporal holdout. Preregistering
a new rule reduces further discretion without erasing previous selection.

**Data:** Current/surviving-stock and supported-action/complete-history selection
remain. Historical membership, delistings, identities, revisions and project-use
qualification are unresolved. Unknown dividend pay dates remain withheld
receivables: 336 original, 602 broader. We cannot quantify the bias or claim
these issues explain the economic failures. A purchase must address specific gaps.

## Primary-source shortlist

This is a feasibility/design judgment; no new returns were compared.

| Approach | Economic question and source | Decision |
| --- | --- | --- |
| Market-adjusted momentum | Does persistence in stock-specific performance improve ranking after removing a common-market component? [Blitz, Huij and Martens](https://repub.eur.nl/pub/22252/ResidualMomentum-2011.pdf), Sections 2–3. | Cached stock/SPY and Treasury history permit a disclosed one-factor adaptation. Specify next. |
| Continuous-information momentum | Does a gradual return path behave differently from dramatic jumps, conditional on cumulative return? [Da, Gurun and Warachka](https://academicweb.nd.edu/~zda/Frog.pdf), introductory methodology and double sorts. | Basic proxy is computable; small conditional groups and attribution require a separate design. Defer testing. |
| Diversified time-series trend | Can different asset classes contribute defensive behavior? [Moskowitz, Ooi and Pedersen](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum). | Our nine cached ETFs are US equity sectors, not a diversified futures/forward sample. No matched multi-asset cache is established. Defer acquisition/testing. |

The residual paper uses 36-month three-factor excess-return regressions,
standardized formation residuals, broad historical stock deciles and long-short
spreads. Our adaptation substitutes SPY and retains long-only top-five mechanics.
It omits size/value factors, paper universe exclusions and overlapping cohorts.
Published profitability is not our evidence; a residual-ranked long-only
portfolio is not market neutral. Standardized total-return momentum tests whether
scaling alone explains any change. The ordinary control uses matching month
boundaries/history/eligibility; the old daily 252/21 recipe cannot substitute.

## Next study and stopping rule

Freeze one 36-month parent, one 30-month neighbor, two matched momentum controls
and three references. Common warmup starts **2019-01-31**, ending **2026-10-02**.
Declare 2019–2020, 2021–2023 and 2024–2026 chronological windows beforehand;
the original early fold cannot be reused as if the new feature existed then.
Every comparison uses matching dates and independent cash resets.

Future budget: **126 new portfolios**, seven recipes × nine cost/delay/period
combinations × two unchanged panels. References need fresh portfolios because
starts/resets change. Only the parent can freeze, after both panels pass the
full rule. Failure stops the study; no neighbor/control promotion or parameter
search follows. This is research within the momentum family, potentially replacing
a candidate; it does not automatically add a distinct release strategy.

## Evidence and limits of this review

`local/research-design-review-2026-10-06/` retains input bindings, twelve
parent/panel findings, `parents.csv`, monthly/cash coverage, prior document
copies and a byte-frozen method. The review checked **8,891 prior manifest
file entries** across seven roots; counts include overlapping bindings. It did
not repeat every campaign ledger/causal verifier or resimulate the engine.
Both cached panels have 129 completed months, 128 monthly returns and 93
possible common signal months from January 2019. Coverage is mechanical
feasibility, not input or strategy qualification.

An initial script assumed the original stock seal was named `COMPLETE.json`;
that study uses `EVIDENCE_HASHES.json` and its full file map is also bound by
the replay seal. The failure and script are retained; correcting review
bookkeeping changes no portfolio outcome. All 67 existing runtime sources,
original frozen methods/snapshots and the forward journal remain unchanged.

[Implementation and runtime registration](superpowers/plans/2026-10-06-market-adjusted-experiment.md)
remain future work before outcomes. Qualified independent-data/use evidence,
fresh temporal evidence and Desktop delivery remain required for production.
The SMA200 forward journal records signals/targets, not prospective returns.
No spending, market-data collection, forecasting-model training or broker orders
occurred in this review.
