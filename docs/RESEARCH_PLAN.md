# Strategy Research and Backtest Validation Plan

Prepared for Elyorjon Mannonov on 2026-10-02.

This plan defines the first research campaign for the quantitative platform. We will compare multiple strategies and models through the same verified portfolio simulator, preserve unsuccessful experiments, and reserve historical periods for validation. The purpose is to determine whether any candidate has useful evidence after costs and realistic execution. An inconclusive result or rejection of every candidate is a valid outcome.

The agreed sequence is **free data → develop → freeze strategy and training recipe → better independent data → re-test → only then ship or publish reference results**. `PROJECT.md` remains the product source of truth and `AGENTS.md` defines engineering requirements. This document proposes research choices; it does not declare any strategy profitable or change the commercial V1 scope.

## Current evidence and unresolved data requirements

### Next stock campaign implementation — authorized 2026-10-03

Implements PR-01–PR-06, PR-08–PR-10 and PR-13, toward the mandatory 3–4
qualified built-in strategies. This is an exploratory stock panel, not a
historical index or a production nomination. Implementation is inline; no Git
actions or external messages are authorized. The existing Python environment
and financial engine are reused.

- [x] Data readiness: `python/research/stock_data.py`, tested in
  `tests/test_stock_research.py`, caches raw stock bars/actions with hashes,
  uses the existing independently supplied provider calendar and SPY snapshot,
  rejects unsupported actions/coverage gaps, and writes exact capability gaps.
  No secrets enter exports. Missing dividend pay dates are retained as unresolved;
  an explicitly named conservative research convention holds that entitlement
  as a receivable through the sample, rather than inventing available cash.
- [x] Strategies: add causal realized-volatility ranking to the shared feature/
  strategy modules and test its hand-calculated values, split/dividend continuity,
  ranking, ties, missing history and future-prefix invariance. Explicit diagnostic
  action policy may enable unqualified research signals; strict mode still blocks.
- [x] Campaign: `python/research/stock_campaign.py` freezes eight recipes,
  sources, data limitations and the 99-trial budget before performance; retains
  failures, independently audits ledgers and records objective/neighbor results.
  Freeze passing exploratory candidates with a separate independent-retest
  requirements manifest; never nominate from this exposed surviving panel.
- [x] Reporting: `python/research/stock_report.py` verifies evidence/bundles,
  exports results/folds/regimes/attribution and labelled figures, and explains
  all five steps including blocked qualification/retest requirements.
- [x] Retest workflow: consume a separately supplied qualified independent snapshot and
  reviewed capability evidence; rerun frozen configurations, costs and baselines
  without retuning. Reject absent/unqualified/same-source data. No paid purchase
  or independently sourced market history is fabricated by this implementation.
- [ ] Actual independent market-data retest: requires a separately reviewed
  qualified dataset; the frozen candidate remains exploratory until that work
  and genuinely new evidence are completed.

The panel is frozen before downloading prices: **AAPL, MSFT, AMZN, GOOGL,
NVDA, CSCO, JPM, BAC, GS, XOM, CVX, JNJ, MRK, PFE, PG, KO, PEP, WMT,
COST, HD, CAT, UNP, UPS, MCD**; SPY is a separate reference. These are deliberately
chosen familiar surviving securities across several industries, not historical
index members or a representative sample. No replacement based on returns.
Download window is 2016-01-04–2026-10-02; no pre-2016 history is assumed.

Pre-performance data audit retained the failed 24-stock normalization and
excluded PFE for its unsupported 2020 VTRS share distribution, with no
replacement. The actual frozen eligible panel therefore has **23 stocks**;
trend uses 23 fixed slots. All raw responses and the explicit scope decision
are preserved. Acquirer-only mergers do not transfer cash/shares to existing
acquirer holders; same-symbol name/CUSIP changes remain unqualified identity
metadata. Neither is credited as portfolio income.

Independent issuer review then found MRK's missing 2021 OGN share distribution
([issuer Form 8937](https://www.merck.com/wp-content/uploads/sites/152/2021/06/Form-8937.pdf)).
MRK is also excluded before performance, yielding **22 eligible stocks** with
22 trend slots. The provisional 23-stock snapshot remains unqualified and is
superseded, not overwritten. Action downloads extend to process-date 2026-12-31
and are normalized by economic ex-date through 2026-10-02, avoiding boundary
omissions. This does not certify action completeness. Raw retrieval timestamps,
not normalization wall-clock time, identify the reproducible dataset version.

The four mechanisms and canonical/one-neighbor specifications are momentum
252/231 sessions with skip 21; broad unranked own-trend SMA 200/180;
trend-conditioned weekly reversal 5/3 with SMA 200; and realized daily-return
volatility ranking 126/105. Ranked strategies select five equal capital slots;
trend uses 22 fixed slots. Allocation is 95%, with price >=USD 5, prior
20-session average dollar volume >=USD 10 million, and 1% prior-volume entry
participation. Low-vol uses population standard deviation of arithmetic total-
return signal returns, ascending rank; zero volatility remains defined. Monthly
rebalance except reversal weekly, all next-session execution. Existing scheduled-
slot quantities and rejection semantics remain unchanged; no stop grid is added.

Primary evidence: [stock momentum](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x),
[own-trend](https://fairmodel.econ.yale.edu/ec439/mosk.pdf),
[short-term reversal](https://www.nber.org/papers/w2533), and
[low-risk anomaly](https://www.hbs.edu/ris/Publication%20Files/Benchmarks%20as%20Limits%20to%20Arbitrage_4c97001f-33d4-426e-8c74-6fbc00b3482e.pdf).
Our long-only daily-window portfolios are adaptations, not replications of
long-short stock, futures or monthly low-risk studies. The reversal trend gate
is our explicit adaptation. [Trading-cost evidence](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies)
motivates cost stress without transferring institutional estimates to our fills.

Eight recipes plus reserve-SPY, same-panel equal weight and cash give 11
configurations. All share the first warmed monthly session, chosen without
returns. Run the continuous window at 10/25 bps and second-open 10 bps:
**33 trials**. Run the same fixed rules with cash reset in three chronological
folds (common start–2019, 2020–2022, 2023–sample end) at 10/25 bps:
**66 trials**, for **99 total**. Warmup is causal and accessible before each
fold, no rules are fitted across folds, and all folds/dates are already exposed.
These are fixed-rule walk-forward diagnostics, not a fresh OOS selection gate.

Return-seeking momentum/reversal require positive CAGR and historical-reference
Sharpe above BOTH SPY and equal-weight at both costs. Defensive trend/low-vol
require positive CAGR, drawdown <=75% of BOTH references and CAGR >=50% of BOTH
at both costs. These research screens preserve the previous declared tradeoff
and do not establish statistical significance. Neighbor stability (positive
CAGR at both costs), at least two of three folds passing the objective at BOTH
costs, and second-open objective passage are required together to freeze a
parent for exploratory independent retest. All flags remain separately disclosed;
neighbors cannot replace parents. No automatic strategy/model production
nomination is allowed. Independent cross-provider tolerances are frozen at
5 percentage points total return and 0.5 percentage points maximum daily return
difference; passing them alone does not qualify a strategy. Source hashes and old experiment history remain recorded.

Before outcomes, register 500 stationary-block resamples at expected blocks
20/60 and seed 1729 on the primary continuous window. Paired historical-reference
Sharpe/excess intervals and a centered maximum-mean diagnostic include all
eight stock recipes versus both equity references. This is conditional
survivor-sample uncertainty; it excludes the accumulated earlier ETF search and
cannot support a fresh evidence or statistical-significance claim. It does not
change the freeze rule.

Review focus/tests: incomplete action/payment coverage must remain visible;
future splits must not alter prior volatility; rank ties must be deterministic;
fold cash resets and warmup must be explicit; independent retest must reject
changed configurations, reused providers, mismatched panels and unqualified data.

The companion [backtester research and design proposal](BACKTESTER_DESIGN.md) compares existing tools and defines the proposed engine contract, correctness fixtures, reuse evaluation, and usability checks. Its initial proceeds-reuse policy is an economic portfolio assumption; brokerage cash-account fidelity requires separate historical settlement and buying-power rules.

Our initial Alpaca account test successfully queried historical SIP daily bars for AAPL, SPY, and QQQ. Each sample returned 2,702 bars from 2016-01-04 through 2026-10-01, with matching timestamps, no duplicates, no invalid OHLC relationships, and no zero-volume bars. AAPL's August 2020 split adjustment behaved as expected. These observations establish sample access and basic consistency only.

We have not established full exchange-calendar completeness, official opening-auction versus aggregated daily-open semantics, dividend event coverage and payment dates, historical universe membership, delisted-security completeness, historical data revisions, or permitted development and model-distribution uses. These requirements need a capability report before a dataset is qualified. A successful API response is not a license determination.

Use completed sessions only. Pin a dataset snapshot, retrieval time, query parameters, feed, adjustment policy, and hashes. Preserve raw observations separately from normalized data. Put downloaded data, fitted models, and generated reports in ignored local storage; keep small synthetic fixtures and specifications in Git. Do not train from repeated live API downloads.

Independent-provider verification checks whether results depend on a vendor's observations or conventions. It does not create a new market history and cannot repair repeated tuning against the same dates. Paid data must satisfy its intended usage rights; purchasing later is not assumed to cover earlier uses.

Initial 2026-10-03 pre-backtest check: only synthetic snapshots were cached at that time. The ten nine-sector-ETF recipes and four SPY/equal-weight/cash references were exported to ignored `local/market-backtest-preparation-2026-10-03/`, with momentum-252/skip-21/top-3 as the proposed first individual run. That preparation has no dataset hash or market-performance result and is not campaign registration. The later private exploratory run is recorded below; full qualification remains pending.

The user confirmed on 2026-10-03 that the account is the standard/free account. Alpaca's [current plan documentation](https://docs.alpaca.markets/us/docs/about-market-data-api) lists historical US stock/ETF data since 2016, 200 historical requests per minute, and exclusion of the latest 15 minutes for Basic. These access limits are compatible with our completed-session daily research; real-time Basic coverage is IEX only. Its [data marketing page](https://alpaca.markets/data) describes the free plan as intended for developers and researchers, but that description does not explicitly grant commercial-project research rights.

Alpaca's [Terms and Conditions](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf), linked from its current [disclosure library](https://alpaca.markets/disclosures) and website footer when checked on 2026-10-03, specify personal/non-commercial use except as otherwise provided. They also address 30 days' advance written notice before making a User Application available to others, and prior written consent for the listed copying/distribution uses for a commercial enterprise. Additional agreements may govern an account. These public documents do not establish permission for our internal commercial-product research; this is an unresolved qualification, not a finding that every commercial arrangement is prohibited. A paid retail subscription alone does not establish the required rights. No private account agreement was inspected and no authenticated data request was made during this check.

The concrete clarification to obtain from Alpaca is: "Does a standard/free Basic account permit locally caching historical US ETF bars and corporate actions for internal backtesting and ML training while developing a commercial desktop product, if no raw data is redistributed? May we distribute resulting strategy code or model weights, and publish derived performance statistics? Please identify the applicable terms and any consent, agreement, notice, or exchange non-display requirements." This is a prepared inquiry only; it has not been sent.

Its [corporate-actions endpoint](https://docs.alpaca.markets/us/reference/corporateactions-1) supplies action types and pagination, but filters/sorts by `process_date` and warns of processing/availability delays. A successful response, the default `data_quality=complete`, or a count of dividend records is not proof of historical action completeness or point-in-time availability.

## First real-market exploratory run

On 2026-10-03 the user explicitly requested private research over ten years.
We ran the previously proposed `momentum_252_skip21_top3` recipe and four
references over **2016-10-03–2026-10-02**, with USD 100,000 and no parameter
search. The fixed universe remains XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY;
SPY is the independent broad-market instrument. No ML model was trained.

The snapshot has 27,030 raw SIP bars across ten instruments and 2,703 supplied
sessions, from 2016-01-04 through 2026-10-02. A request for 2015 warmup returned
no pre-2016 bars. Therefore the momentum rule stays in cash until its first
fully warmed month-end signal on 2017-01-31 and first entry on 2017-02-01.
SPY references enter on 2016-10-04 and equal-weight sectors on 2016-11-01;
these initialization differences are explicitly visible in reports. The decade
is a full portfolio-accounting period, not ten years of active momentum holdings.

Data review found 145 vendor dividends without payment dates, ten cash events
missing compared with the issuer, and two payment-date discrepancies. Cached
[issuer distribution records](https://www.ssga.com/us/en/institutional/resources/documents/etf-dividend-distributions)
provide 432 cash distributions including capital gains; five provider splits
are mapped separately. The issuer/vendor September 2016 XLF entry of 0.139146
represents XLRE shares rather than cash. It is excluded from portfolio cash
events. For warmup signals only, a research wrapper uses the issuer's historical
USD 4.5292 total-distribution valuation from its
[Form 8937](https://www.ssga.com/library-content/products/fund-docs/etfs/us/tax-documents/US-Form-8937-XLF-Signed-New.pdf).
This is a disclosed non-cash valuation approximation, not general spinoff
support; the wrapper refuses a portfolio start on/before the distribution's
payment date. No simulated holding receives synthetic spinoff cash.

Primary 10 bps-per-traded-side results, inclusive of dividends/receivables:

| Portfolio | End equity (USD) | Calendar CAGR | Max drawdown | Sharpe, zero reference |
| --- | ---: | ---: | ---: | ---: |
| Momentum top 3 | 356,546.89 | 13.56% | 28.81% | 0.82 |
| SPY buy-and-hold | 383,974.37 | 14.40% | 32.13% | 0.90 |
| SPY buy-and-hold, initial 5% reserve | 369,837.12 | 13.97% | 31.14% | 0.90 |
| Monthly equal-weight sectors | 319,669.01 | 12.32% | 34.93% | 0.82 |

SPY buys once and retains dividend cash; this is not a continuously
dividend-reinvested index. The ten-year momentum result exceeds the sector
reference but trails both SPY references. Initialization and lower exposure
affect that comparison. Positive historical returns do not establish alpha or
a robust production strategy. At 5/25 bps the momentum end equities are
USD 364,838.69 / 333,108.46; a predeclared second-open delay at 10 bps yields
USD 365,260.62. All scenarios remain visible. The 5 bps full-budget SPY entry
was rejected after an opening gap; its all-cash result is retained as an invalid
benchmark, with no date change or resizing to repair the outcome.

Ignored `local/market-backtest-2026-10-03/` contains the immutable raw responses,
`market.snapshot.json`, `DATA_REVIEW.json`, pre-run `EXPERIMENT_PLAN.json`,
start/completion records for 20 trials, verified accounting bundles,
`RESULTS.json`, `REPORT.html`, annual/monthly/comparison CSVs, PNG/PDF charts,
and report hashes. Independent reconstruction checks **50,280** session
cash/share/receivable/equity valuations and **5,656** fill prices/timings.

The first simulation was saved before analytics crashed on a zero-dollar SPY
dividend audit outside the candidate's trading universe. A regression-tested
analytics fix ignores zero outside-universe income and rejects nonzero income.
`RECOVERY.json` records that change; the saved simulation was recovered without
rerunning it or changing strategy parameters. Runtime hashes retain the change.

This direct exploratory run is **outside the gated validation campaign**:
calendar/open/split completeness, point-in-time provider revisions, commercial
usage rights and independent-provider qualification remain unresolved. No
qualification was fabricated, nomination made, or fresh-final-evidence claim
created. Inspecting the full period **exposes the proposed 2024–2026 holdout**;
future selection must disclose that exposure and obtain new untouched evidence.

To reproduce in a new ignored directory, reuse the repository virtual
environment and obtain the same source bytes or record any provider revisions:

```bash
.venv/bin/python python/research/alpaca_download.py --mode probe \
  --output local/market-backtest-reproduction/raw
.venv/bin/python python/research/alpaca_download.py --mode bars \
  --end 2026-10-02T20:00:00Z --output local/market-backtest-reproduction/raw
.venv/bin/python python/research/alpaca_download.py --mode issuer \
  --output local/market-backtest-reproduction/raw
PYTHONPATH=python .venv/bin/python python/research/market_backtest.py normalize \
  --root local/market-backtest-reproduction
PYTHONPATH=python .venv/bin/python python/research/market_backtest.py run \
  --root local/market-backtest-reproduction
# Optional research dependency for chart/report export:
.venv/bin/python -m pip install matplotlib
PYTHONPATH=python .venv/bin/python python/research/market_report.py \
  --root local/market-backtest-reproduction
```

Downloads/snapshots/trials refuse replacement. Keep credentials in ignored
`.env` or environment variables. Reporting uses cached data without API calls.

## All predefined strategy comparison

On 2026-10-03, at the user's request, we compared all ten existing rule recipes
on the same cached snapshot, without training ML, tuning parameters, or
introducing a new risk policy. The plan, source hashes, full configurations,
ranking rule and trial budget were saved before this comparison's performance
was inspected. Earlier momentum/reference results over these dates were already
known; this registration does not turn the comparison into untouched evidence.

The primary comparison starts on **2017-01-31**, the first monthly rebalance
after all ten recipes have enough history (maximum 253 sessions), determined
from calendar/configuration alone. It ends on **2026-10-02**. This removes the
original window's unequal feature warmup. Monthly rules first fill on February
1; weekly reversal keeps its natural schedule and first fills on February 6.
References begin at their own declared rebalance dates. We also retain the
original **2016-10-03–2026-10-02** accounting window at primary costs, rather
than replacing the earlier decade evidence.

The finite budget is **70 trials**: ten candidates plus four references under
four scenarios in the common-warmup window (56), plus all fourteen at primary
costs in the original decade. Scenarios are 5, 10 and 25 bps per traded side,
and a second-open delay at 10 bps. Five matching prior decade bundles were
verified and reused, leaving 65 new simulations. All rules retain USD 100,000
initial cash, whole-share sizing, next-open execution, the same allocation/
liquidity constraints, zero cash yield and zero Sharpe reference rate. No
protective stops were added. The fixed surviving-ETF sample, signal-only XLF
warmup approximation and unresolved provider qualifications remain as above.

Primary common-warmup results, after 10 bps per traded side:

| Recipe / reference | Calendar CAGR | Max drawdown | Sharpe, zero reference | Notional turnover / year |
| --- | ---: | ---: | ---: | ---: |
| Momentum 252 / skip 21 / top 3 | 14.05% | 28.81% | 0.84 | 4.62x |
| Trend SMA 200 | 6.97% | 14.57% | 0.79 | 2.15x |
| Momentum 252 / skip 21 / top 5 | 11.49% | 31.84% | 0.75 | 3.04x |
| Nearness to 252-day high / top 5 | 10.78% | 29.60% | 0.75 | 5.36x |
| Nearness to 252-day high / top 3 | 9.55% | 28.42% | 0.65 | 10.05x |
| Trend SMA 100 | 5.27% | 14.79% | 0.63 | 3.18x |
| Momentum 126 / skip 21 / top 5 | 8.98% | 34.11% | 0.61 | 4.91x |
| Momentum 126 / skip 21 / top 3 | 9.08% | 32.40% | 0.58 | 7.16x |
| Reversal 5 / SMA 200 / top 3 | 3.10% | 34.00% | 0.28 | 54.62x |
| Reversal 3 / SMA 200 / top 3 | 2.49% | 38.15% | 0.24 | 55.19x |
| SPY buy-and-hold, initial 5% reserve | 13.85% | 31.28% | 0.88 | 0.10x |
| Monthly equal-weight sectors | 11.93% | 34.93% | 0.78 | 0.41x |
| Cash, zero yield | 0.00% | 0.00% | Undefined | 0.00x |

Candidates are shown in the predeclared descriptive Sharpe order, using
unrounded values. Turnover counts both bought and sold notional relative to
contemporaneous equity and is annualized by calendar duration. SMA trend rules
hold substantial cash (SMA 200 averages about 71% gross exposure); they are not
risk-matched to SPY. SPY buys once and retains dividend cash, with an initial
reserve that subsequently drifts, rather than continuously reinvesting dividends.

Momentum 252/top 3 has the highest candidate return and Sharpe, narrowly exceeds
the reserve-SPY CAGR at common start, and has a smaller drawdown, but still has
lower Sharpe than SPY. Its CAGR ranges from 14.32% at 5 bps to 13.25% at 25 bps;
second-open execution gives 14.33%. Its original decade CAGR remains 13.56%,
below reserve-SPY's 13.97%. SMA 200 is a lower-drawdown/lower-return challenger,
not a demonstrated alpha improvement. Both reversal rules have high turnover
and deteriorate to negative CAGR at 25 bps: -5.64% (3-day), -5.01% (5-day).
No recipe demonstrates reliable superiority across these exploratory checks.

The joint centered stationary bootstrap tests maximum mean daily excess across
all ten candidates against the **predeclared reserve-SPY reference**. With 500
replicates and seed 1729, p-values are 0.836 / 0.856 for expected block lengths
20 / 60 sessions. These do not establish positive excess performance; this is
a maximum-mean diagnostic, not a Sharpe test, DSR or proof of equivalence.
Conditional paired 95% Sharpe-difference intervals for the descriptive leader
also include zero: approximately [-0.342, 0.235] / [-0.306, 0.257]. They do not
correct selection of that leader and cannot restore the exposed holdout.

There are **67 completed portfolios and three invalid benchmarks**, with no
failed simulations. Full-budget SPY entries at common start were rejected
after opening gaps at 5/10/25 bps. Their all-cash ledgers remain retained but
are labelled invalid rather than counted as market performance. No date,
allocation or order was changed to repair those outcomes. The reserve-SPY
reference was valid in every scenario and was specified before these results.

Ignored `local/strategy-comparison-2026-10-03/` contains `EXPERIMENT_PLAN.json`,
recipe exports, all started/completed trial records, accounting bundles,
`TRIAL_RESULTS.json`, `RESULTS.json`, `DIAGNOSTICS.json`, `REPORT.html`, all-trial
and annual CSVs, labelled PNG/PDF family charts and `REPORT_HASHES.json`.
All 70 ledgers passed independent reconstruction, covering **171,388** session
valuations and **52,238** fills. Reporting verifies every bundle, and all 12
listed report-artifact hashes were checked. All **248 tests** pass on
Linux/Python 3.12.7, including three comparison-specific checks. Dataset SHA-256
is `1df82e92960d986cdf724b10764baf71c358adb27a112f5b3164e2af7981b932`;
the frozen comparison plan hash is
`b49bbc58eecb4c5f7ad2136f256558c778beb4daab23c8e19072ea93af216dd5`.

To reproduce using that cached dataset and prior verified bundles in a **new**
ignored directory, without API requests:

```bash
PYTHONPATH=python .venv/bin/python python/research/compare_strategies.py run \
  --output local/strategy-comparison-reproduction
PYTHONPATH=python .venv/bin/python python/research/compare_strategies.py report \
  --output local/strategy-comparison-reproduction
```

Matplotlib is needed only for report export. No production strategy is selected;
the next qualification work must use appropriately licensed independent data
and new untouched evidence, while preserving this complete search history.

## Robustness audit implementation specification — 2026-10-03

The user authorized implementing the audit after the all-ten comparison.
The two fixed parents are `momentum_252_skip21_top3` and `trend_sma_200`.
Momentum's hypothesis is benchmark-relative performance after costs; trend's
is a lower-drawdown tradeoff, assessed separately from alpha. These dates are
already exposed. There is no automatic nomination or production selection.

Implementation tasks, executed inline with test-first financial fixtures:

- [x] `python/research/robustness_metrics.py` and `tests/test_robustness.py`:
  reconcile daily asset P&L and flat-to-flat holding episodes through splits,
  dividends and partial sales; calculate rolling 252-session results,
  benchmark beta/alpha, underwater episodes and top-five excess-day sensitivity.
- [x] `python/research/robustness_audit.py`: freeze input/source hashes and the
  finite budget before running; retain started/completed/failed records and
  independently reconstruct every new ledger, including gap/intraday stops.
- [x] `python/research/robustness_report.py`: export a standalone report,
  CSV/JSON evidence and labelled PNG/PDF figures; verify old/new bundles and
  artifact hashes. Update existing project/validation documents with outcomes.

There are six one-factor parameter neighbors: momentum lookback 231/273 with
top-3 fixed, momentum top-2/top-4 with lookback 252 and skip 21 fixed, and trend
SMA 180/220. No factorial search or winner replacement is performed. The two
parents and all neighbors share the first month-end after the longest required
history (274 sessions), chosen from calendar/configuration without prices.
Both parents also have two separately labelled controls: 75% scheduled
allocation, and the existing ATR-protected profile (ATR 14, multiple 2,
0.5% planned entry risk, 35% position cap, 95% gross cap, 5% reserve, 4.5%
portfolio heat, nine positions). For the ATR experiment, drawdown reduction/
halt thresholds are 90%/99%, with reduction scale 1; there is no tuned
drawdown restart. This profile bundles sizing, fixed stops and admission
rules, so it cannot identify the isolated effect of a stop.

The 15 configurations (two parents, six neighbors, four controls, reserve-SPY,
equal-weight sectors and cash) run at 10/25 bps: **30 new trials**. Five existing
primary common-warmup portfolios are verified and reused for original-period
diagnostics. Existing cost/delay evidence stays linked; it is not rerun merely
to improve a result. All new trials use USD 100,000 and the pinned snapshot.

Historical cash uses a separately hashed official 3-month Treasury yield
series. For each inter-session interval, use the most recent observation
strictly before the interval's starting session, reject missing or more than
10-day-old observations, and accrue simple ACT/365 interest over calendar days.
The fixed-order overlay earns interest on previous cash plus accumulated
overlay interest, never receivables. It does not change orders or sizing.
The yield proxy and revised historical observations are not an investable
total-return index or point-in-time vintage. Exposure matching uses the prior
session's cash-overlay gross exposure to mix fully invested, ex-date-reinvested
SPY signal-index returns and this cash proxy (not reserve-SPY returns);
it is a diagnostic with no additional rebalancing costs, not an executable
strategy. Sharpe with historical reference uses arithmetic excess returns;
beta/alpha use paired excess-return regression, with annualized alpha labelled
as arithmetic rather than CAGR.

Predeclared diagnostic rules: parameter stability requires at least 75% of
neighbors to retain positive CAGR at both costs; it does not establish alpha.
Momentum's benchmark-relative hypothesis is rejected on this sample if it
does not beat both references' historical-reference Sharpe at both costs;
otherwise it remains inconclusive pending independent/fresh evidence. Trend's
defensive hypothesis requires drawdown no greater than 75% of SPY's and CAGR
at least 50% of SPY's at both costs, otherwise reject that stated tradeoff.
Asset concentration flags any asset above 60% of positive asset P&L; best-five
excess-day removal is a descriptive return-series adjustment, never a replay
with trades removed. All decisions disclose prior selection and exposed dates.
Tests cover reconciliation failures, open episodes, zero-variance ratios,
calendar gaps, future/stale rates, future-price exclusion, stop semantics,
incomplete trial panels and tampered provenance. Thresholds are research
preferences recorded before these new diagnostics, not statistical guarantees.

## Robustness audit results — 2026-10-03

All **30 registered new trials completed**, with five original-window bundles
reused unchanged. The common window is **2017-02-28–2026-10-02**, covering
2,413 sessions, chosen mechanically to accommodate the longest declared
lookback. The earlier common-window results starting 2017-01-31 remain intact.
Both parents pass the limited positive-CAGR neighbor stability rule, but
**neither passes its own predeclared objective**. No neighbor replaces a parent,
no production strategy is selected, and these exposed dates are not new OOS
evidence. The thresholds themselves are declared research preferences.

Actual portfolios below earn zero cash interest; costs are per traded side,
fees are zero, and terminal holdings are marked without forced liquidation.
The SPY reference initially reserves 5% and retains distribution cash.

| Configuration | CAGR, 10 bps | Max drawdown, 10 bps | CAGR, 25 bps | Max drawdown, 25 bps |
| --- | ---: | ---: | ---: | ---: |
| Momentum 252 / skip 21 / top 3 | 13.93% | 28.81% | 13.12% | 28.79% |
| Trend SMA 200 | 6.70% | 14.59% | 6.34% | 15.37% |
| Reserve SPY | 13.50% | 31.33% | 13.47% | 31.31% |
| Equal-weight sectors | 11.62% | 34.93% | 11.53% | 34.88% |
| Momentum, 75% allocation | 11.03% | 23.18% | 10.41% | 23.15% |
| Trend, 75% allocation | 5.31% | 11.61% | 5.04% | 12.25% |
| Momentum, bundled ATR profile | 2.29% | 4.87% | 1.85% | 5.07% |
| Trend, bundled ATR profile | 1.89% | 10.40% | 1.86% | 11.44% |

Momentum's historical-reference Sharpe is **0.683/0.642** at 10/25 bps,
versus SPY's **0.697/0.696** and equal-weight's **0.603/0.599**. It misses the
requirement to beat both references at both costs. Its four neighbors remain
profitable, but their 10-bps CAGRs range from 11.48% to 13.54%; positive CAGR
does not demonstrate parameter-independent benchmark superiority. SPY beta is
about 0.96; fitted annual arithmetic alpha is +1.09% at 10 bps and +0.39% at
25 bps, descriptive coefficients with no new significance claim.

Trend reduces SPY drawdown by more than half, but retains only **49.65%/47.07%**
of SPY CAGR at the two costs, below the frozen 50% floor. The 10-bps miss is
small and is not evidence that trend can never serve a defensive purpose; the
stressed-cost miss and long recovery matter. Its worst drawdown begins at the
2022-01-04 peak and recovers on 2024-08-19 at 10 bps: **658 sessions / 958
calendar days**. At 25 bps recovery is 2024-08-30, 667 sessions / 969 days.
Momentum's worst drawdown recovers in 116 sessions / 167 days at 10 bps.

Attribution reconciles daily dollar P&L through cash distributions, splits,
partial sales and open holdings. XLK contributes **37.34%** of momentum's
positive asset P&L and **30.55%** of trend's at 10 bps; neither breaches the
predeclared 60% asset flag. However, zeroing momentum's five best positive
daily excess returns changes mean excess versus reserve SPY from **+0.00233%**
to **−0.00308% per session**. This is a return-series diagnostic, not a trade
removal or replay. Rolling 252-session growth trails SPY in 1,308/2,162
momentum windows and 1,857/2,162 trend windows; overlapping windows are not
independent trials. CSVs also retain annual asset contributions, holding-time
buckets and unrecovered/open episodes.

The 75% controls reduce return and drawdown together without establishing an
improved signal. The bundled ATR profiles average only **19.86%/29.27%** gross
exposure for momentum/trend at 10 bps and reject 101/91 orders; their low
drawdowns cannot be attributed to the stop alone. Historical-reference Sharpe
is negative for both ATR portfolios at both costs before the cash overlay.

### Historical cash diagnostic and provenance

The separate cash input contains **2,689** daily 3-month constant-maturity
yield observations from 2016-01-04 through 2026-10-02, taken from the official
[Treasury daily par-yield tables](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value=2026).
The raw annual CSVs, their URLs/hashes, normalized observations and retrieval
metadata are retained in ignored `local/robustness-inputs-2026-10-03/`.
Normalized CSV SHA-256 is
`c79d1da91a347e074eb98f9b0e2004eefd609eb510c8a64d0baf8aa00743d581`.
This is a yield proxy under the lagged ACT/365 convention above, not the return
on an investable fund or a historical-vintage guarantee.

With unchanged orders, the cash overlay raises 10-bps CAGR from 13.93% to
**14.04%** for momentum, 6.70% to **7.40%** for trend, and 13.50% to **13.67%**
for reserve SPY. Cash-only overlay CAGR is **2.63%**. These diagnostics are
reported separately and do not retroactively change the actual-portfolio
decision rule. Relative to the lagged-exposure SPY/cash mix, overlay Sharpe
differences are −0.025 for momentum and −0.102 for trend at 10 bps; neither
diagnostic establishes a reliable improvement over market exposure and cash.

### Verification, artifacts and reproduction

At that audit, all **276 tests** passed on Linux/Python 3.12.7, including 28 audit-specific
tests. Independent raw-bar reconstruction passes for **35 portfolios**,
**84,550 session valuations** and **15,974 fills**, including **30 gap stops**
and **155 intraday stops**. A separate code review found no remaining critical
or important findings within the pinned ETF audit's scope after fixes.
Source hashes, exact trial panels, accepted stop instructions, accounting
bundles, recomputed core metrics and decision rules are verified before export.
All **66 evidence-file hashes** and **22 report-artifact hashes** were checked;
the earlier two reports' artifacts remain unchanged. Hashes detect partial or
accidental changes, not a researcher rewriting all evidence coherently.

Frozen audit plan hash:
`cab7eed016c93f7d9efd4bb57286496b8d835e923a1f214f686db07ff3a05ca2`.
Market snapshot hash is unchanged from the preceding comparison.
Ignored `local/robustness-audit-2026-10-03/` contains the standalone `REPORT.html`,
all 30 started/completed records, 30 new bundles, five reused bundle references,
JSON diagnostics, 35-row trial CSV, 350 annual-return rows, attribution/holding/
rolling/recovery/concentration CSVs and labelled PNG/PDF figures. Report export
does not resimulate or tune a strategy. Existing output directories are never
silently overwritten.

Using the cached market snapshot, cash inputs and preceding comparison, run
into a **new** ignored directory without API calls:

```bash
PYTHONPATH=python .venv/bin/python python/research/robustness_audit.py run \
  --output local/robustness-audit-reproduction
PYTHONPATH=python .venv/bin/python python/research/robustness_audit.py report \
  --output local/robustness-audit-reproduction
```

Matplotlib is needed only for report export. Provider/corporate-action/calendar/
rights qualification, the retrospectively fixed surviving ETF universe,
daily-bar execution limitations, and the prior XLF signal-only distribution
proxy remain unchanged. Independent data and genuinely new untouched evidence
are still required before production nomination or commercial performance
claims; this audit does not reset the earlier search history.

## Research findings and their relevance

| Approach | What the primary research establishes | Implication for our campaign |
| --- | --- | --- |
| Cross-sectional momentum | Jegadeesh and Titman document intermediate-horizon winner versus loser stock strategies in their historical sample. | Start with a transparent ranking baseline. Our long-only portfolio and daily execution will be an adaptation, so published returns are not expected outcomes. [Paper](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x) |
| Time-series momentum | Moskowitz, Ooi, and Pedersen study persistence in an instrument's own past returns across liquid futures. | Test a separate long/cash trend hypothesis on equities or ETFs. Futures diversification and leverage results do not transfer automatically. [Paper](https://fairmodel.econ.yale.edu/ec439/mosk.pdf) |
| Nearness to the 52-week high | George and Hwang study this price-based signal as an explanation of stock momentum. | Include a distinct price-ranking hypothesis that requires no fundamentals. An ETF implementation remains our own experiment. [Paper](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00695.x) |
| Short-term reversal | Frazzini, Israel, and Moskowitz find materially different implementation costs across anomalies, with short-term reversal particularly constrained at institutional size. | Test reversal as a cost-sensitive challenger, with explicit turnover and break-even costs. Their institutional estimates are not our retail fill estimates. [Study](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies) |
| Momentum crash risk | Daniel and Moskowitz identify severe momentum losses associated with market declines and rebounds. | Report failures during rebounds and stressful periods; do not assume average performance captures the risk. Their long-short crash mechanism is not identical to our long-only strategy. [Paper](https://www.nber.org/papers/w20439) |
| ML return prediction | Gu, Kelly, and Xiu compare regularized linear models, trees, and neural networks on a much larger historical stock panel with richer predictors than we currently possess. | Run a model comparison, but do not transfer their monthly-return results to our short-horizon OHLCV dataset. [Author manuscript](https://dachxiu.chicagobooth.edu/download/ML_BKP.pdf) |
| Tabular ML | Grinsztajn and colleagues find strong tree-model performance in their 2022 tabular benchmark. Hollmann and colleagues show advances from a tabular foundation model in 2025. | Trees are a practical starting choice, not a universal winner. Generic tabular results do not establish financial forecasting skill. [2022 study](https://arxiv.org/abs/2207.08815), [2025 study](https://www.nature.com/articles/s41586-024-08328-6) |
| Multiple testing | White, Harvey and colleagues, and Bailey and colleagues describe how searching many specifications can inflate apparent evidence. | Bound the search, retain every attempted configuration, and evaluate selection as well as individual candidates. [Reality Check](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00152), [Factor testing](https://www.nber.org/papers/w20592), [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) |

These sources justify hypotheses and validation procedures. They do not identify the best strategy for our product. The proposed choices below are engineering and research judgments that we must evaluate on our own data.

## Campaign scope and universes

Proposed initial conditions: daily bars, long-only positions, no borrowing or leverage, USD accounting, and $100,000 initial capital. All values belong in versioned configuration. This is a tractable first research campaign; it does not settle every future product feature.

Start the simulator and deterministic strategy comparison with a fixed sector ETF universe: XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, and XLY. Use SPY as a broad-market benchmark and an equal-weight portfolio of the same nine ETFs as the opportunity-set benchmark. Confirm fund histories, corporate actions, and session coverage before accepting the set. Freeze the list before measuring strategy performance; retain and disclose that it is a retrospectively chosen, surviving ETF sample with changing underlying sector classifications. ETF research does not establish historical stock-selection skill.

For stock-ranking research, first establish dated eligibility, identity mappings, and delisting coverage. If no adequate free point-in-time universe is available, a fixed stock sample can support exploratory feature/model work, with its survivorship limitations stated in every report. Do not call a backtest on today's constituents a historical S&P 500 backtest. Qualification of stock results requires a better universe dataset later.

Fundamental value/quality factors, pairs trading, news, and reinforcement learning are outside this first campaign: they introduce additional data-timing, borrowing, execution, or action-space assumptions. Their exclusion is a scope decision rather than a finding that they cannot work.

## First strategy comparison

The following are proposed specifications to register before running performance experiments. Use one canonical configuration per family first, then its small declared comparison set. A parameter combination, added filter, sizing change, or manually selected date range is a new research choice and must be logged.

| Family | Canonical rule | Declared comparison set |
| --- | --- | --- |
| Trend participation | At month-end, hold each ETF's fixed portfolio slot when its signal price is above its trailing 200-session mean; otherwise leave that slot in cash. | Mean window 100 or 200 sessions: 2 recipes. |
| Relative momentum | At month-end, rank trailing returns from 252 sessions ago through 21 sessions ago. Hold the top 3 ETFs in equal slots. | Lookback 126 or 252 sessions, skip the latest 21 sessions, hold top 3 or 5: 4 recipes. |
| Nearness to high | At month-end, rank current signal price divided by its highest signal price over the trailing 252 sessions; hold top 3 in equal slots. | Hold top 3 or 5: 2 recipes. |
| Short-term reversal | At the last session of each week, select the 3 lowest trailing 5-session returns among ETFs above their 200-session mean. Hold until the next weekly rebalance. | Return window 3 or 5 sessions: 2 recipes. |

This gives **10 initial deterministic recipes**, plus separately registered benchmarks. These windows are proposed conventional starting values, not optimized settings or exact replications of the cited studies. Define inclusive/exclusive rolling endpoints and tie-breaking in tests. Reversal keeps empty slots in cash when fewer than 3 ETFs qualify. The first three ranked/trend families do not silently acquire a market filter or absolute-momentum gate later.

Fixed slots collectively target at most 95% invested capital; unused slots remain cash. Allocate 95%/9 to each trend slot and 95%/K to each ranked slot. Whole-share rounding and order cash checks apply. Avoid a stop/target grid in the initial comparison: scheduled exits isolate the signal hypothesis. Any subsequent stop, volatility sizing, or regime filter is an explicit ablation with a new trial entry.

Run SPY buy-and-hold, same-universe equal-weight monthly rebalancing, and cash controls over matching evaluation dates. Benchmarks include their own trades, dividends, costs, and declared cash treatment. Show full-investment SPY alongside a comparable reserve assumption rather than selecting whichever benchmark is easier to beat.

## ML comparison after simulator verification

Treat ML as a candidate-scoring layer. Keep the universe, allocation, execution, and risk policy fixed when comparing model scores with a deterministic ranking baseline. Otherwise improved performance cannot be attributed to the model.

Begin with compact, auditable price-derived features: lagged returns, skip-month momentum, distance to moving averages and highs, trailing volatility/ATR, relative volume, dollar volume, and market-relative returns. Add feature groups one at a time. Cross-sectional transforms use only the eligible universe at the signal timestamp. Statistical preprocessing and feature selection are fitted only within training folds. [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html)

Primary supervised target: realized forward excess total return versus SPY over 5, 10, or 20 sessions, with entry at the next session's simulated open and scheduled exit at the open H sessions after entry. Labels incorporate the declared corporate-action convention and use the same horizon for the benchmark. They are outcomes, never features. Remove samples whose label-end timestamp has not passed at model-fit time.

First model wave:

1. Ridge and Elastic Net as regularized linear baselines.
2. A constrained Random Forest as a different nonlinear baseline.
3. LightGBM, XGBoost, and CatBoost as alternative boosted-tree implementations.

Pre-register two capacity/regularization configurations per model and three horizons: **36 nominal recipes**. This budget is a proposed limit on exploration, not a claim of statistically independent trials or an optimal tuning budget. Publish exact configurations before training. Record every refit, seed, failed fit, and early-stopping decision; compare algorithms under a declared compute budget and disclose that limited tuning can affect rankings.

For each horizon, use a fixed H-session rebalance calendar, top-K rule, allocation, and benchmark. A holding horizon is not an instruction to open overlapping full-capital portfolios every day. If overlapping cohorts are later tested, divide capital explicitly and register the change.

Second wave, only if justified by development evidence:

- Compare LightGBM regression scores with a learning-to-rank objective grouped by signal date. For LambdaRank, use declared integer relevance labels and gains rather than supplying raw signed returns as relevance. [LightGBM objectives](https://lightgbm.readthedocs.io/en/stable/Parameters.html)
- Add a small MLP to test neural interactions; then a bounded GRU/TCN sequence experiment only if temporal inputs have a clear hypothesis. LSTM/Transformer variants require a documented reason and an additional trial budget.
- Consider a locally runnable tabular foundation model as an optional challenger after verifying version, licensing, resource needs, and chronological evaluation. Published generic benchmarks are not evidence of trading profitability.
- Test an ensemble only from components selected within development data; learn weights from past predictions, never from final-period outcomes.

A nine-ETF pilot is useful for verifying model plumbing, but provides a small cross-section. Many symbol-date rows are correlated and do not create an equally large number of independent observations. Broad stock-model conclusions must wait for an appropriate stock dataset.

Report date-level rank information coefficient, top-versus-bottom outcome spread, feature ablations, training time, and inference time alongside portfolio results. Neither accuracy nor rank correlation alone establishes net economic value. Ranking scores are not probabilities; probability calibration is evaluated only for explicitly probabilistic targets.

## Simulator contract

Freeze a versioned simulator contract before comparing candidates. Strategies produce signals and intended allocations; they cannot change the broker's fills, costs, or accounting. Backtrader's next-bar execution and LEAN's corporate-action handling provide useful reference behaviors, not automatic verification of our implementation. [Backtrader orders](https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/), [LEAN corporate actions](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions)

- **Timing:** signals use a completed session t; market orders become executable at the following session's open. Never fill a close-derived signal at that same close. Record the exchange calendar, timezone, and data availability convention.
- **Sizing:** calculate intended share counts from session-t equity and raw closing prices, preserving the cash reserve. At execution, update for overnight corporate actions, execute sells first, then buys in recorded rank order with deterministic symbol tie-breaking. Reject unaffordable buys rather than allowing negative cash. Log order-ordering sensitivity because it can affect results.
- **Open prices:** Alpaca's daily open is an aggregated bar field. Until reconciled with regular-session/auction conventions, next-open execution is an explicit approximation. Do not describe it as a verified auction fill.
- **Actions:** execute and mark holdings using raw prices; adjust shares and cost basis on splits. Record dividend entitlements on ex-date and cash on payable date when available. If payable dates are unavailable, record receivables and specify a conservative availability convention; missing essential action data blocks total-return qualification. Do not use dividend-adjusted prices and also credit dividend cash.
- **Signals:** construct return/indicator series from known events with a documented point-in-time adjustment convention. Future corporate actions must not change historical absolute-price eligibility or decisions. Provider-adjusted series alone do not establish this property.
- **Costs:** proposed ETF sensitivity ladder is 5, 10, and 25 basis points per traded side for combined spread/slippage/fees. Choose 10 bps as the primary exploratory scenario and show all three. These are assumptions, not measured execution estimates. Replace them with independently justified instrument/order-size assumptions before qualification. Zero-cost output is diagnostic only.
- **Liquidity:** eligibility and sizing use lagged volume; proposed participation cap is 1% of trailing 20-session average volume. This is a capacity proxy, not proof that an order would fill at the open. Actual fills and capacity remain approximations until more detailed execution data are available.
- **Missing observations:** no forward-filled tradable OHLC. Cancel an order when its execution bar is absent, mark stale holdings explicitly, and log the missing session. Define valuation and final liquidation for halts and delistings; do not drop failed symbols or sell them at a convenient last good price.
- **Intrabar orders:** the implemented protective stops fill adverse opening gaps at the available opening price with costs, not automatically at the stop price. Intraday stop proceeds cannot fund earlier opening entries. If both a stop and target are touched in one daily bar when targets are implemented, report the ambiguous trade and adverse-first result; a favorable ordering requires finer data. Trailing stops based on a new daily high must become active next session when implemented.

The initial [risk/sizing layer](RISK_MANAGEMENT.md) is available for separately registered stop/sizing/control ablations. Freeze its full policy, group assumptions, warmup requirements and drawdown restart convention with each recipe. The scheduled-exit signal baseline above can use explicit orders with risk disabled; risk-enabled entries currently require protective stops. Do not claim a stop-risk percentage or drawdown circuit-breaker threshold guarantees the corresponding realized-loss bound.
- **Cash and metrics:** initial exploratory cash yield and Sharpe reference rate are both 0%, stated prominently. Before qualifying cash-heavy strategies, repeat the comparison with an independently sourced historical cash/risk-free convention. Report dividends, transaction costs, turnover, exposure, and cash balances separately.

End-of-period holdings are marked to market rather than secretly liquidated without costs. Realized and unrealized P&L reconcile to total equity. Comparisons start on a common date after required warmup; this period choice cannot be adjusted after seeing results.

## Correctness and leakage checks

Before interpreting strategy returns, verify the simulator against hand-calculated synthetic fixtures and independent calculations. Required checks include:

1. Buy, hold, sell, cash reconciliation, fees, adverse slippage, whole-share rounding, insufficient cash, and simultaneous multi-asset orders.
2. Splits, dividends/receivables, missing bars, halted/delisted assets, rejected orders, and terminal valuation.
3. Signal close versus next open, including a large overnight gap; no accidental same-close execution.
4. Prefix invariance: altering or appending future observations cannot change earlier features, predictions, orders, or fills. Include preprocessing, universe membership, identity mappings, and adjustments in the checks.
5. Label-boundary tests: labels that finish after the fit cutoff cannot enter training; whole signal dates remain in one split.
6. Flat-price and synthetic random-return controls, plus independently calculated benchmark returns. Negative controls have known expectations or simulated sampling distributions, rather than a requirement that every random realization lose money.
7. Monotonic accounting effects: for an identical fill schedule, increasing costs cannot increase ending equity. A strategy rerun may change later orders through cash constraints, so that is a separate sensitivity check.

Use a small independent ledger or a suitably configured external engine to reconcile selected fixtures, with matching assumptions. Agreement between two libraries with the same hidden assumption is not conclusive. A semantic bug triggers a version change and reruns of every affected candidate and benchmark, including failures; record whether holdout outputs were exposed during debugging.

## Chronological evaluation and the locked period

Proposed date partitions, based on the available post-2016 data:

| Period | Role | Permitted use |
| --- | --- | --- |
| 2016–2021 | Development | Features, hypotheses, limited tuning, nested chronological folds, correctness checks. 2016 contributes warmup; usable samples depend on lookback. |
| 2022–2023 | Selection validation | Evaluate the declared campaign and nomination rule once. This is selection data and must not be described as untouched final evidence. |
| 2024-01-01–2026-09-30 | Locked final evaluation | Evaluate the frozen nominee and declared benchmarks after better-data verification. Keep performance outputs inaccessible during development. |
| Subsequent completed sessions | Prospective observation | Generate signals before outcomes exist and record simulated next-session decisions with the frozen recipe. |

These are proposed boundaries to register before any alpha-performance runs. If the final period has already informed strategy decisions elsewhere, disclose that contamination and reserve genuinely later data instead. The earlier access check inspected bars and a split, not strategy performance; it did not validate an alpha hypothesis.

Within development, use expanding annual outer windows, initially training through 2018 and evaluating 2019, then repeating for 2020 and 2021. Inner tuning/early stopping uses only earlier chronological partitions. Annual refitting is the initial operational schedule; changing it creates a new recipe. Nested development scores estimate the declared procedure, but human revisions after inspecting them make them exploratory evidence.

Split by **unique session dates**, not flattened symbol rows. Standard `TimeSeriesSplit` supplies time-ordered splits and a sample gap, but a panel needs our own date grouping and label-interval checks. Purge training examples whose entry-to-label-end interval reaches the validation/test boundary. A 20-session label can require more than 20 sessions of gap once next-session entry is included; derive the purge from timestamps, not a guessed fixed row count. Earlier data may supply indicator warmup without fitting on future outcomes. [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)

If a diagnostic resampling procedure trains on blocks after a held-out block, add the appropriate embargo and identify the exercise as a selection diagnostic. The primary simulated deployment always trains on the past and predicts the future.

The final run evaluates a **frozen procedure**, including its predefined retraining schedule; fitted weights may evolve using only labels available at each historical fit. Freeze features, label construction, configuration search, winner-selection policy, risk, execution, costs, and reporting. Paying for data is not permission to search new settings on the locked period.

## Search control and statistical evidence

Maintain an append-only experiment registry with hypothesis, source/inference, configuration, dataset and code hashes, seed, fit/prediction dates, costs, metrics, failure status, and decision reason. Retain return series for every candidate. Record manual experiments, changes in universes, risk filters, and unsuccessful tests, not just optimizer runs.

The 10 deterministic and 36 first-wave ML recipes are finite starting budgets. Diagnostics, parameter neighbors, repeated seeds, and later extensions are separately identified but remain visible to the research history. Increasing a budget requires a recorded reason before the additional experiment; do not erase the accumulated search by restarting a campaign.

Report uncertainty using date-block resampling of paired candidate and benchmark returns, preserving contemporaneous cross-asset relationships and testing declared block-length sensitivity. Trade count and symbol count are not independent sample sizes. Bootstrap intervals are conditional on the observed history and do not manufacture missing crises or future regimes.

Use the Deflated Sharpe Ratio as a multiple-testing/non-normality diagnostic, publishing inputs and sensitivity to correlated-trial estimates. Do not describe it as the probability of future profit, and do not apply an IID shortcut to serially dependent daily returns without qualification. A benchmark-relative Reality Check is an additional way to assess the declared search. [DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf), [White](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00152)

Probability of Backtest Overfitting via CSCV can examine a complete, aligned matrix of candidate development returns. It is a secondary selection diagnostic, and is distinct from chronological forecasting validation; merely recombining returns from already trained models is not a substitute for leakage-safe ML refitting. Its short-sample and design limitations must be disclosed. [PBO paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)

## Reports and candidate nomination

Every report shows all attempted recipes, gross and net performance, the same declared benchmarks, yearly and fold-level results, worst drawdown/duration, volatility, Sharpe convention, Sortino, exposure, turnover, trade distribution, cash, rejected orders, costs, and provenance. Include rank metrics for ML. Show both aggregate and failure-period results; regime labels must be predefined or explicitly descriptive.

Required sensitivity results include higher costs, a one-session execution delay, nearby registered parameter values, removal of the largest winners as a descriptive concentration check, asset-level contributions, and alternate size/capacity assumptions. Do not select a new winner from these diagnostic outputs without registering that decision as additional development.

Proposed primary comparison statistic: the difference between candidate and same-universe benchmark annualized net Sharpe ratios, using the declared 0% reference rate. Nomination ranks eligible candidates by the median of that difference across the annual development folds. Report the paired uncertainty of the difference, net CAGR, SPY performance, beta, drawdown, and exposure alongside it. Define standard deviation, annualization, zero-variance handling, and tie-breaking before execution; an unresolved statistical difference favors the simpler, lower-turnover procedure. For the first campaign, propose a 25% maximum-drawdown budget; this is a research risk preference to settle before running the campaign, not a fact supported by a paper. A defensive candidate's lower exposure alone does not establish forecasting skill.

Proposed eligibility gates for paid-data nomination: correctness/data checks pass; aggregate development and selection-validation Sharpe differences are positive under both the primary 10-bps and stressed 25-bps cost scenarios; observed drawdown stays within the declared budget; and sensitivity/concentration reports do not reveal a single narrow source of apparent advantage. Specify quantitative concentration and parameter-stability criteria in the experiment registration before measuring returns. A nomination authorizes further research expenditure, not a finding of proven profitability. Use paired uncertainty and selection diagnostics; if evidence is weak, label it inconclusive rather than relaxing thresholds. A 95% confidence interval is a reporting convention, not an automatic guarantee or an excuse to ignore multiple testing. Prefer the simpler procedure when differences are not resolved by the evidence.

Freeze at most one nominee per separately declared objective; do not turn the final period into another tournament. The default first campaign has one objective and one nominee. A passing validation year alone is insufficient. A failing year alone is not automatically disqualifying; its magnitude, mechanism, and relation to the predefined risk objective must be reported.

## Better data and release qualification

After nomination, freeze a manifest of code, data schema, universe policy, strategy, features, label definition, training schedule, model configuration, simulator contract, cost scenarios, and evaluation rules.

Obtain an independently sourced, appropriately licensed dataset. Check whether supposedly different providers share an underlying feed. Reconcile calendar, corporate actions, identity, adjustment convention, dividends, delistings, and membership before comparing results. For stock models, qualified point-in-time coverage is essential; the better-data stage may reject the initial exploratory universe assumptions.

Rebuild features and retrain from scratch under the frozen recipe using only the permitted historical training windows. First compare the development/selection dates across providers; investigate material differences without consulting the locked period. Longer paid history may support a separately specified historical stress test, but must not become an unlogged new optimization space.

Then evaluate the nominee on the locked period with both datasets and the registered reports. Provider agreement is a robustness check, not two independent statistical samples. If methodology changes in response to these outcomes, mark the period consumed, create a new research version, and seek new prospective evidence before making fresh final-validation claims.

Prospective shadow research records signals before outcomes, without broker execution. It tests data arrival and operational behavior; a short shadow period cannot establish long-run profitability. Ship a strategy/model or publish reference performance only when usage rights, correctness, reproducibility, limitations, and the accumulated evidence support the specific claim. Selling the research platform itself must not imply a guaranteed profitable strategy.

## Implementation sequence and deliverables

The product build order is the nine-stage roadmap in `PROJECT.md`: market-data layer, backtester, risk/money management, strategies, strategy validation, ML models, scanner/analytics, desktop UI, then packaging/licensing/website. The table below describes research deliverables within that roadmap; its numbering is not the product-stage numbering. Rule-based candidates undergo strategy validation before ML work, and ML candidates repeat that process before selection.

| Stage | Work | Completion evidence |
| --- | --- | --- |
| 1 | Register universe, periods, objective, recipe budgets, and simulator contract. | Versioned experiment specification; unresolved assumptions identified before returns are measured. |
| 2 | Qualify Alpaca data and build raw/normalized local snapshots, actions, calendar, and manifests. | Capability/quality report; reproducible snapshots; qualified scope or explicit exploratory restrictions. |
| 3 | Build the minimal daily portfolio simulator and ledger. | Hand-calculated fixtures, leakage checks, independent reconciliation, benchmark agreement. |
| 4 | Run the 10 deterministic recipes with registered costs and development folds. | Complete comparison report, failures included; shared assumptions verified. |
| 5 | Add feature/label pipeline and the 36 bounded ML recipes where data supports the task. | Chronological predictions and portfolio results, feature ablations, search registry. |
| 6 | Apply the registered selection-validation policy and robustness diagnostics. | Nomination or rejection/inconclusive decision, with reasons and frozen manifest if nominated. |
| 7 | Obtain better independent data, rebuild/retrain, and evaluate the frozen nominee. | Provider reconciliation, final-period report, contamination record, prospective observation log. |
| 8 | Decide what belongs in commercial V1. | Evidence package and honest limitations supporting each included strategy/model. |

Use the repository's provider-neutral Python boundaries, Parquet/DuckDB storage direction, virtual environment, and financial tests. Qlib is a useful reference for feature/model research workflows, but its datasets, universes, labels, and execution assumptions must be audited before adopting examples. Do not import research scripts into the production runtime. [Qlib project](https://github.com/microsoft/qlib)

The local data foundation, backtester, risk layer and four [rule-based strategy families](STRATEGIES.md) are implemented with synthetic accounting, feature and causality tests. The ten proposed recipe configurations and four benchmark configurations can be exported without running returns. Full-budget and 5%-reserve broad-market buy-and-hold are both included. Scheduled slots budget estimated entry fees/slippage at the signal close before rounding shares; the exact allocation convention is recorded in strategy source provenance. ATR-protected allocation is an explicit separate ablation.

The [Stage 5 validation workflow](VALIDATION.md) now implements frozen rule-strategy campaigns, reviewed snapshot-bound capability records, complete trial/failure tracking, common-date development/selection portfolios, cost/delay/participation scenarios, year/fold metrics and reconciled asset P&L, paired stationary bootstrap and a centered maximum-mean search diagnostic. Quantitative concentration/parameter/uncertainty gates and a lower-turnover choice for unresolved development-score differences are recorded before evaluation. Freeze, independent-provider crosscheck and consumed-once final evaluation are separately gated. A synthetic two-recipe campaign exercises 72 trial bundles without a real-data nominee or final-period consumption.

Actual-provider qualification and the registered ten-recipe empirical campaign remain pending. A normalized, explicitly unqualified fixed-ETF snapshot and private momentum diagnostic now exist as recorded above; no qualified Alpaca dataset has been established. Full execution profiles, historical cash rates, historical stock membership, independent-engine/Windows checks, prospective shadow recording and ML refitting still require work. DSR/PBO remain distinct diagnostics to implement/qualify; the existing maximum-mean bootstrap is not presented as either. Engineering strategy fixtures are not performance evidence, and no production strategy has been selected or empirically validated. The previously proposed 2024–2026 final dates have now been exposed and cannot remain an untouched holdout for future selection.

## Stock campaign results — 2026-10-03

The four hypotheses, their one-factor neighbors and three references completed
all **99 registered trials**: 33 continuous scenarios and 66 chronological
portfolios. Only 99 unique simulations were performed. All independently
reconstructed ledgers passed, covering **132,902 session valuations and 76,727
fills**. Tests now total **304 passing** on Linux/Python 3.12.7.

The sample is 22 deliberately chosen surviving stocks plus SPY, with the data
and exclusion decisions frozen before performance. Data starts 2016-01-04;
common indicator warmup moves actual portfolio evaluation to
**2017-01-31–2026-10-02**. There is no fresh temporal holdout. The unknown
336 dividend payment dates and all unresolved qualification capabilities remain
visible; unavailable cash can affect sizing and comparisons.

| Parent/reference | CAGR, 10 bps per side | Maximum drawdown | Historical-reference Sharpe | Predeclared parent decision |
| --- | ---: | ---: | ---: | --- |
| Momentum 252/skip21/top5 | 21.97% | 27.59% | 0.890 | Reject on this sample |
| Trend SMA200 | 11.06% | 13.19% | 0.890 | Freeze for exploratory independent retest |
| Reversal 5/SMA200/top5 | 6.43% | 31.46% | 0.296 | Reject on this sample |
| Low volatility 126/top5 | 8.71% | 17.42% | 0.513 | Reject on this sample |
| Reserve SPY buy-and-hold | 13.85% | 31.28% | 0.719 | Reference only |
| Same-panel equal weight | 18.25% | 28.48% | 0.972 | Reference only |

Momentum's higher CAGR does not establish the required Sharpe advantage over
the same-panel reference. Reversal is particularly cost-sensitive: increasing
slippage to 25 bps changes CAGR to -3.15% and drawdown to 50.83%. Low volatility
reduces drawdown but fails the declared half-reference CAGR threshold. A more
favorable neighbor cannot replace a failed canonical parent.

Trend meets the declared defensive tradeoff at 10/25 bps, its 180-session
neighbor remains positive, all three chronological windows meet the objective
at both costs, and second-open execution passes. Its stressed CAGR/drawdown
are 10.66%/13.46%; delayed execution gives 11.49%/12.58%. This supports further
investigation, not qualification, superiority in every objective, or reliable
future profit. The frozen configuration is `stock_trend_sma200`; **one
exploratory candidate and zero qualified built-in strategies** remain.

500 paired stationary-block resamples at expected block lengths 20/60 and
seed 1729 accompany the primary continuous results. The eight-recipe centered
maximum-mean diagnostic gives conditional p-values about 0.034/0.036 versus
SPY and 0.236/0.206 versus same-panel equal weight. These statistics concern a
bounded exposed survivor sample, exclude earlier ETF searching, do not test
the full defensive objective and are not a fresh or general significance claim.

The first finalization attempt failed after the simulations and uncertainty
were saved: the diagnostic handoff supplied model/return objects to a function
requiring primitive candidate AND reference ledgers. The unchanged original
registration, 99 trial records/bundles, results/audits, original registered
source and `FINALIZATION_FAILURE.json` are retained at
`local/stock-campaign-2026-10-03/`. A regression test reproduces the repaired
boundary.

The finalized revision reuses those exact 99 portfolios in
`local/stock-campaign-2026-10-03-finalized/`, with **204 pinned original file
hashes**, an explicit `prior_registration` record and `reused_from` identities.
Recovery rejects changed data, recipes, objectives, statistical settings or
financial-engine sources. Only the campaign postprocessing source changes; no
financial resimulation, parameter search or old registration rewriting occurs.
Verification recalculates ledgers, metrics, bootstrap diagnostics, attribution
and frozen/retest decisions before report exports. Revised plan SHA-256:
`032af4c91c0c85482d6cdadca4e64c47a38d07bc81f2d068f98e18db37440a21`.
Snapshot SHA-256:
`d8f9b4013f4073a47ebf5c80bda9e162bc53405d9a9b44a8e044191b7782cae2`.

`REPORT.html`, labelled PNG/PDF plots and 11 CSV exports are under the finalized
folder; 205 immutable evidence files and the report artifacts have hash
registries. To reproduce finalization, preserve the original campaign and use
a new output directory:

```bash
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py run \
  --reuse-campaign local/stock-campaign-2026-10-03 \
  --output local/stock-campaign-2026-10-03-finalized
PYTHONPATH=python .venv/bin/python python/research/stock_campaign.py report \
  --output local/stock-campaign-2026-10-03-finalized
```

The independent retest workflow is implemented and tested on synthetic split/
dividend ledgers, including altered reviews, configurations, audits, comparisons
and report hashes. **Actual independent market-data retesting remains pending**:
a separately sourced snapshot and reviewed qualification evidence are not yet
available. The frozen trend strategy must be rerun unchanged with its references
and fixed costs/delays, and needs genuinely new evidence before final claims.
No market data was purchased. V1 still requires at least three distinct
qualified strategies, targeting four; this campaign does not satisfy that gate.

## Fundamental feasibility and frozen retest preparation — 2026-10-03

The authorized next task researches two distinct hypotheses—value and gross
profitability—before new performance experiments. See the
[fixed scope, rules, sources, proposed 81-trial budget and actual audit findings](FUNDAMENTAL_RESEARCH.md).
The research-only SEC module caches 57 responses and derives 190 issuer/year
rows: 80 direct profitability pairs remain unqualified, 67 require accounting
mapping review and 43 have no coherent pair. The proposed common 17-stock panel
has only 7–9 direct pairs per formation, below the ten-eligible-issuer gate.
Value's preferred-stock and December market-equity inputs remain unresolved.
No performance campaign was launched and no hypothesis was promoted on returns.

The [independent-data input brief](INDEPENDENT_DATA_RETEST.md) replaces the
unresolved provider choice with a conditional EODHD pilot and Massive alternative,
plus documented license/history/volume/payment/calendar/identity gaps. Norgate's
current public business-use limitation pauses that earlier option. No purchase,
account agreement or provider qualification is fabricated.

Before adding the SEC module, the exact 43 stock-campaign source files were
copied to `local/frozen-stock-source-2026-10-03/` and checked against the original
registration. This preserves the original campaign procedure without rewriting
its plan; the live research tree now intentionally has a different source set.
For verification and eventual independent retest, use the archived commands in
the input brief. Existing market dates remain exposed; independent-provider
agreement cannot manufacture a new temporal holdout.

## Original-filing reconciliation — 2026-10-04

The [next implemented research stage](FUNDAMENTAL_RECONCILIATION.md) collects
218 original accessions, parses 216 instances and independently crosschecks
150 inline primary filings. Reviewed P&G and bounded Costco mappings yield
91 original profitability observations. Common-panel component coverage is
8–10 per June formation; only 2018 and 2020 reach ten. Exact December-share
components cover only 6–7 common issuers. Parent equity, preferred obligations,
class/split basis and accounting comparability remain explicitly unqualified.
Neither fundamental hypothesis is ready for the proposed performance campaign.

The initial real split-schema failure, original registration and exact sources
are preserved. A verified v2 report is retained separately; final v3 reconciles
compatible rounded GAAP and exact DEI share counts using declared precision,
without changing request scope or reusing strategy-performance outcomes. Tests
cover real serialized split records, arithmetic, conflicting contexts,
transformations, issuer/period/units, exact dates and re-sealed tampering. The
full suite now has 357 passing tests; independent code review found no remaining
critical/important issue in the documented bounded research scope.

Current standalone report: `local/sec-reconciliation-2026-10-04-v3/REPORT.html`.
No new backtest, ML training, purchase, Git action or qualification was made.

## Accounting and capital evidence — 2026-10-04

The [bounded extension](FUNDAMENTAL_CAPITAL.md) preserves the original SEC/stock processing
sources and reports. It adds exact dimensional accounting, body-bound
nonfinancial-amendment exemptions, reviewed issued/treasury shares, preferred
zero/hierarchy evidence and explicit original/split-basis gates. The new
190-row audit has 99 profitability records and 103 December share records;
common-panel coverage remains 9–10 and 9–11, below the unchanged ten-issuer
requirements in one/eight formations respectively. The fixed-panel study is
infeasible under the registered scope. No strategy performance, market-data
purchase or ML training launches. Component arithmetic cannot qualify a
provider or strategy; a broader study requires separate preregistration.
The then-current suite passed 388 tests, including 84 SEC tests. Capital evidence:
`local/sec-capital-2026-10-04/REPORT.html` and `CAPITAL.json`.

## Broader filing-candidate study — 2026-10-04

The separately registered [broader study](BROAD_UNIVERSE_RESEARCH.md) preserves the infeasible
fixed panel and uses 42 original SEC quarterly indexes, 2016Q1–2026Q2.
Filing-date selection yields 7,154–8,162 candidates per June formation;
a frozen hash rule samples 100 each, totaling 1,000 issuer/formation rows
and 198 distinct CIKs. Current tickers, returns and data availability do
not influence selection, and missing candidates are never replaced.
Historical listing/identity/classification, accounting, price/action/delisting
and project-use checks remain missing. Current quarterly-index corrections
also remain unresolved: filing candidates are not qualified historical stocks.
No strategy performance or ML training launches. Its then-current suite passed
407 tests, including 19 broader-study tests. Local evidence is
`local/broad-universe-2026-10-04-v2/REPORT.html` and `ROSTER.json`; original
failed registration, source archive and all 84 response files are preserved.

## Broader SEC input evidence — 2026-10-04

The [evidence audit](BROAD_SEC_EVIDENCE.md) keeps the exact 198 CIKs and 1,000 sample
rows. All 1,400 registered requests were attempted: 396 API roots, nine
historical archives and 995 original annual headers. Preserve the 32
CompanyFacts 404s and nine issuer/year publication-metadata disagreements;
missing candidates are never replaced. There are 246 preliminary GP/assets
rows and 430 exact December-share observations, with no qualified issuers.
Original header names/SIC are unreviewed evidence, not historical listing
or share-class proof. All 10,000 qualification checks remain missing.
Original financial/amendment and historical security review precede market-
data qualification and any separately registered performance campaign.
The full suite passes 425 tests, including 18 new evidence-stage tests.
Current local evidence: `local/broad-sec-evidence-2026-10-04-v2/REPORT.html`
and `EVIDENCE.json`. Both 40-source archives and original format/transport
finding records remain preserved; no purchase, performance or ML launch.
