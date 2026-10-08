# Alpaca universe transfer — 2026-10-05

> Superseded by the [2026-10-08 strategy qualification standard](STRATEGY_EVIDENCE.md); retained as research history. Outcomes recorded here are unchanged and are counted in [the research ledger](RESEARCH_LEDGER.md).

This study asks whether the four existing stock implementations behave similarly
outside the original hand-selected 22 stocks. It supports PR-01, PR-02, PR-05,
PR-06, PR-08 and PR-13. Its source/data/coverage registration precedes portfolio
outcomes, and it changes no strategy parameters or qualification requirements.

## Selection and coverage

Two bounded issuer probes attempted December 31, 2015 IVV holdings. The legacy
download route returned product HTML; the current CSV route ignored the query
date and returned October 2, 2026 holdings. Both responses are retained. These
attempts do not prove historical holdings are unavailable from every source.

The separately recorded fallback samples **60** equity tickers from the current
issuer holdings. Rank tickers by SHA-256 of
`quant-platform-universe-transfer-v1-2026-10-05:<ticker>` and take the first 60,
excluding SPY and the original requested 24 names, including PFE/MRK. Fund
weights, returns, liquidity and later data availability do not influence this
sampling rule. All 60 names remain in the coverage report; no missing name is
replaced. The sample is a current-holdings equity sample, not a historical
S&P 500 membership reconstruction.

The first Alpaca batch failed with HTTP 400 because `VYLR WI` is unsupported
request syntax. Its plan/body and sandbox transport failure remain preserved.
A separate collection version requests the other 59, retaining that holding
as an exclusion. Sixteen price pages and two action pages complete successfully.
The amended cap is 39 requests plus the original failed request; collection
uses no hidden retries or credential-bearing redirects. It requests all action
types and retains every raw page and its credential-free request metadata.

Before any portfolio outcome, **47 names** pass complete 2,703-session coverage,
valid raw bars, supported received corporate actions and strict discontinuity
checks. **13 names** remain excluded: CARR, CVNA, DDOG, FRT, LEN, LULU, MRNA,
MRVL, P, PGR, TT, VYLR WI and WDC. Missing history, unsupported share/identity
events, a split-sized gap, a duplicate action and provider syntax are reported
individually in `coverage.csv`. A heuristic gap is a reason to investigate,
not proof of a missing split; no price repair occurs.

The combined snapshot contains 129,744 bars for 47 stocks plus SPY and
**602 unknown dividend payment dates**, withheld as receivables through the
sample under the existing research policy. The benchmark uses the unchanged
cached Alpaca/issuer-reconciled SPY reference. Unknown dates and source revisions
are not independently resolved by passing mechanical checks.

Current holdings already select surviving securities. Requiring complete history
and supported events further conditions the simulated sample. Excluded names
remain visible but their economic outcomes are **outside** the portfolio; they
are not assigned zero returns or represented as handled delistings. Historical
aliases, security identity and terminal outcomes remain unqualified. The study
is retrospective exploratory transfer evidence, not independent validation,
survivorship-free research or an untouched temporal holdout.

## Fixed experiment

The existing campaign runs all **99** portfolios: four parents, four one-factor
neighbors and three references across the original continuous/chronological
windows, 10/25 basis point costs per side and delayed execution. These are
scenario checks of four hypotheses, not 99 independent ideas. Warmup,
signal-at-close/next-session execution, starting cash, sizing, participation,
objectives, fold rule, historical cash reference and bootstrap settings match
the original protocol exactly. Recipes are academic-family adaptations.

The full 63-source runtime and all input/coverage bytes are frozen before
performance. Every result has a verified portfolio bundle and independent
cash/share ledger audit. Original 22-stock results and their corrected-engine
replay remain preserved. New results must be assessed against **both** equity
references under the original objectives, not merely compared by CAGR.

Evidence: `local/universe-transfer-2026-10-05-v2/`, with original failed
collection retained at `local/universe-transfer-2026-10-05/`. Final report,
comparison CSV, complete 99-trial results and completion hash manifest belong
to this separately registered version.

## Results and interpretation

All 99 simulations complete and pass the independent campaign verifier and
cash/share ledger audit: **132,902 session valuations and 107,171 fills**.
The full suite passes **562 tests**, including 26 new selection/coverage and
forward-journal tests. The prior 61-source runtime, original 1,412 campaign
files, corrected replay and original dataset remain unchanged. New code is
limited to two research modules; production core remains 0.5.1.

At the primary 10 bps per side:

| Parent | CAGR | Maximum drawdown | Historical-reference Sharpe | Full registered rule |
| --- | ---: | ---: | ---: | --- |
| Momentum 252/skip21/top5 | 24.15% | 35.22% | 0.814 | Reject on this sample |
| SMA200 | 10.33% | 14.96% | 0.790 | Reject on this sample |
| Reversal 5/SMA200/top5 | 9.55% | 34.53% | 0.405 | Reject on this sample |
| Low-volatility 126/top5 | 9.87% | 37.06% | 0.494 | Reject on this sample |
| Same-universe equal weight reference | 17.01% | 33.35% | 0.830 | Reference |
| SPY with reserve reference | 13.85% | 31.28% | 0.719 | Reference |

Momentum's high CAGR does not pass its return-seeking objective: Sharpe remains
below the equal-weight reference at both costs. Reversal changes from 9.55%
to **−2.27% CAGR** at 25 bps per side. Low-volatility drawdown exceeds the
defensive bound. None of these failures disproves an entire strategy family.

SMA200 passes the continuous defensive objective at both costs and the delayed
execution check, and its neighbor remains positive. But **only one of three
chronological folds** meets the objective at both costs; the existing requirement
is at least two. Its average equity exposure is **61.35%**, so lower exposure
and cash contribute to defensive behavior. The study does not establish
stock-selection alpha. The original panel's promising decision remains an
unchanged historical result; it does not become a general robust-strategy claim.

The fold failures are return-retention failures at the stressed cost, rather
than failure of drawdown protection. Preserve their magnitudes:

| SMA200 fold | 25 bps CAGR | Binding half-benchmark CAGR floor | Outcome at both costs |
| --- | ---: | ---: | --- |
| 2017–2019 | 12.479% | 10.928% (equal weight) | Pass |
| 2020–2022 | 7.286% | 7.300% (equal weight) | Fail |
| 2023–2026 | 9.220% | 9.625% (SPY with reserve) | Fail |

The middle fold misses by only about **0.014 percentage points**, while the
last misses by about **0.405 percentage points**. That makes SMA200 worth
further observation as a defensive implementation; it does not change the
registered decision. These thresholds express our research objective, not a
universal scientific definition of a strategy edge.

There are **zero newly frozen candidates** and **zero production-qualified
strategies**. More complete data could change observations, but missing independent
data is not the only reason these implementations are unready: the available
data already exposes objective, cost and sample-stability weaknesses. Do not
relax the thresholds, select a favorable subperiod or silently discard this study.

The next bounded price-only research candidate is nearness to a 52-week high,
motivated by [George and Hwang's original study](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00695.x).
It uses an anchoring-related signal rather than past return alone, but can
overlap substantially with momentum. Our long-only implementation would be an
adaptation, not a replication or automatically a distinct qualified offering.
Its exact recipe, trial budget, both sample panels, benchmark/objective and
correlation assessment must be registered before any new performance run.

The [prospective SMA200 journal](FORWARD_SHADOW.md) separately freezes the
original 22-stock recipe for operational evidence despite its transfer failure.
Additional distinct price-only hypotheses remain conditional follow-up;
preregister any experiment before outcomes and retain
the cumulative search history. Do not sweep existing parameters until a metric
passes. Zero strategies qualify for production until the remaining release
evidence is earned.
