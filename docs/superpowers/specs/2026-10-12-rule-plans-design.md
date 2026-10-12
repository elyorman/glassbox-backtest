# Four rule plans and the deflated Sharpe ratio (Plan D) — design

Date: 2026-10-12. Roadmap step D (`docs/ROADMAP.md`). The owner chose option A
(each paper's own monthly rule) and left the remaining choices to the design.
Next step: the implementation plan, a dry run on a scratch copy, then task-by-task
execution with subagents and reviews (as Plans B and C).

Plan D builds and hand-tests the four plans and the deflated Sharpe ratio. It
runs nothing on real market data: the rules below are fixed before anyone sees
a result, and the registered runs happen once, in step E.

## Sources (verified 2026-10-12)

Each rule and each number names its source. Quotes and pages were checked
against the primary text unless marked.

| Source | What it gives the plans | Where |
| --- | --- | --- |
| Faber, *A Quantitative Approach to Tactical Asset Allocation* (2007; update Feb 2013) | Trend rule: "Buy when monthly price > 10-month SMA", else cash (p.21); total-return series, T-bill cash (p.22); S&P 500, MSCI EAFE, US 10-year government bonds, GSCI, NAREIT at 20% each, rebalanced monthly (pp.15, 29, 55); signal and trade at the month-end close (p.22) | [2013 update](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf) |
| Moskowitz, Ooi and Pedersen, *Time Series Momentum* (JFE 2012) | Academic support for trend: the sign of the past 12-month excess return predicts the next month, across asset classes | [paper](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf) |
| Antonacci, *Dual Momentum Investing* (2014), via the author's FAQ and GEM page | Absolute momentum first: S&P 500 12-month return vs T-bills; if positive, the stronger of S&P 500 and ACWI ex-US; otherwise US aggregate bonds, with no test of their own; 12 months, month-end, no skipped month, total returns (book p.98 as the author describes it) | [FAQ](https://web.archive.org/web/20220113153557/https://www.optimalmomentum.com/faq/), [GEM](https://web.archive.org/web/20220120222819/https://www.optimalmomentum.com/global-equities-momentum/) |
| Antonacci, *Risk Premia Harvesting Through Dual Momentum* (2012/2013) | Uses MSCI EAFE for the non-US leg before 1988; "results do not change significantly if we use only the MSCI EAFE Index" (footnote 2) | [paper](https://www.emiratescapitalassetmanagement.com/uploads/2/5/5/4/25541321/risk_premia_harvesting_through_dual_momentum.pdf) |
| Asness, Moskowitz and Pedersen, *Value and Momentum Everywhere* (JF 2013) | 12-1 momentum: past 12-month return skipping the most recent month, the same measure for every asset class (pp.936–937); academic support for dual momentum's relative leg | [paper](https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf) |
| Jegadeesh and Titman, *Returns to Buying Winners and Selling Losers* (JF 1993) | Momentum with formation periods up to 12 months, equal weights | [paper](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf) |
| Moskowitz and Grinblatt, *Do Industries Explain Momentum?* (JF 1999) | Industry momentum: "investing equally in the top three industries" (p.1262) | [paper](https://web.archive.org/web/2015/http://www-stat.wharton.upenn.edu/~steele/Courses/956/Resource/Momentum/MoskowitzGrinblatt99.pdf) |
| Faber, *Relative Strength Strategies for Investing* (2010) | Sector rotation: top 3 at 33% each, re-ranked monthly at the month-end close (pp.6–7) | [paper](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id1585517.pdf) |
| Asness, Frazzini and Pedersen, *Leverage Aversion and Risk Parity* (FAJ 2012) | Weight ∝ 1/σ, σ = "three-year rolling volatility of monthly excess returns", rebalanced every calendar month, unlevered weights rescaled to sum to 1; broad sample: stocks, government bonds, credit, S&P GSCI (Appendix A, Table 1) | [paper](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Leverage-Aversion-and-Risk-Parity.pdf) |
| Maillard, Roncalli and Teïletche, *Equally Weighted Risk Contribution Portfolios* (JPM 2010) | With equal correlations, equal risk contribution weights are x_i = σ_i⁻¹ / Σ σ_j⁻¹ (working paper Sec. 3.2) | [working paper](http://www.thierry-roncalli.com/download/erc.pdf) |
| Bailey and López de Prado, *The Deflated Sharpe Ratio* (JPM 2014) | Eq. 1 (expected maximum Sharpe), Eq. 2 (DSR), numerical example (pp.9–10) | [paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) |

Supporting sources for the limitations pages; they change no rule (existence
and abstracts checked):

- Hurst, Ooi and Pedersen, *A Century of Evidence on Trend-Following
  Investing* (JPM 2017): trend following tested back to 1880.
  [paper](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing)
- Daniel and Moskowitz, *Momentum Crashes* (JFE 2016): momentum suffers rare,
  sharp losses in market rebounds after panics.
  [working paper](https://www.nber.org/papers/w20439)
- Anderson, Bianchi and Goldberg, *Will My Risk Parity Strategy Outperform?*
  (FAJ 2012): results depend heavily on start and end dates and on trading
  costs. [abstract](https://rpc.cfainstitute.org/research/financial-analysts-journal/2012/will-my-risk-parity-strategy-outperform)
- McLean and Pontiff, *Does Academic Research Destroy Stock Return
  Predictability?* (JF 2016): returns of 97 published stock predictors are
  58% lower after publication. [paper](https://ivey.uwo.ca/media/3775549/pontiff.pdf)

ETF history (Tiingo metadata, 2026-10-12): SPY 1993-01-29; XLB, XLE, XLF, XLI,
XLK, XLP, XLU, XLV, XLY 1998-12-22; VTI 2001-05-31; EFA 2001-08-17; IEF, TLT,
SHY, LQD 2002-07-26; AGG 2003-09-26; VNQ 2004-09-29; GLD 2004-11-18; DBC
2006-02-03; GSG 2006-07-21; VEU 2007-03-08; BND 2007-04-10; ACWX 2008-03-31;
XLRE 2015-10-08; XLC 2018-06-19.

## 1. Shared conventions

- **Monthly decisions.** A plan decides on each month-end session: the last
  session of a calendar month in the bound calendar (`rebalance_dates`, so a
  truncated final month is never a decision). A declared offset of −2 … +2
  sessions moves every decision for the evidence pack's rebalance-day shift;
  the registered plans use 0.
- **Month-end values.** Signals use each ETF's total-return signal index
  (`signal_prices`: known splits, dividends reinvested at the ex-date close),
  sampled on decision sessions. "10 months" means the current decision and the
  nine before it; a 12-month return compares the current decision with the one
  twelve decisions earlier. All rules use ratios, so the index's local base
  cancels.
- **T-bills.** Dual momentum and inverse volatility need T-bill returns. The
  plan binds its own `CashRateSeries` and compounds it exactly as the engine
  credits idle cash (rate strictly before the previous session, ACT/365 per
  calendar day). The plan's decisions therefore do not change when the run's
  idle cash earns 0% (the evidence pack's secondary variant). Trend and sector
  rotation bind no series.
- **Execution.** Orders fill at the next session's open (engine convention;
  the papers trade at the signal close). The plans invest 95%: each weight is
  multiplied by 0.95 and the rest stays in cash as a cushion, so a higher open
  does not get buys rejected. The papers are fully invested; the cushion is
  pure exposure scaling, not a counted trial.
- **Orders.** Target shares, whole-share buys, sells, the cap on buys at 1% of
  20-session average volume, and reason codes are those of the existing `scheduled_slots`
  profile, extracted into one shared helper. Sells execute before buys.
- **Data checks.** An ETF is skipped, with the reason recorded, when it is
  outside its lifetime, lacks the decision bar, lacks history back to its
  earliest needed decision, has a missing session in that window, or fails the
  liquidity check (20-session average volume above zero). A skipped ETF's
  weight stays in cash; weights of other ETFs are not enlarged, except where a
  rule below says so.
- **Corporate actions** must be declared complete, raw volume is required, and
  `risk` must be None, as for the existing rule strategies.

## 2. The four plans

### Multi-asset trend
- **ETFs:** SPY (S&P 500), EFA (MSCI EAFE), IEF (7–10-year Treasuries), VNQ
  (US REITs), GSG (S&P GSCI): Faber's five asset classes.
- **Rule (Faber):** each ETF is held at 20% while its month-end value is
  strictly above the average of its last 10 month-end values; otherwise its
  20% stays in cash. Held ETFs are reset to 20% each month.
- **First full decision:** 2007-04-30 (GSG's tenth month-end).
- **Departures:** VNQ tracks a different REIT index from NAREIT and IEF covers
  7–10 years rather than the 10-year bond; both are the closest ETFs with the
  history. Equality with the average counts as below (the paper defines only
  above and below).

### Dual momentum
- **ETFs:** SPY (S&P 500), EFA (non-US stocks), AGG (US aggregate bonds).
- **Rule (Antonacci, absolute momentum first):** if SPY's 12-month return is
  strictly greater than the T-bill return over the same 12 months, hold
  whichever of SPY and EFA has the higher 12-month return (SPY on a tie);
  otherwise hold AGG. One ETF at 100% of the invested share. If any of the
  three is skipped, the plan holds cash and records why.
- **First full decision:** 2003-10-31 (AGG's first month-end with 20 sessions
  of history).
- **Departure:** ACWI ex-US is replaced by EFA (developed markets only).
  ACWX starts 2008-03-31, so its first 12-month signal would be March 2009 and
  2008 would be missing. The author's own paper used EAFE for its early years
  and reports no significant change with EAFE only. The reason is history
  length, not results.

### US sector rotation
- **ETFs:** XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY; XLRE and XLC take
  part once they have the needed history (from 2016-10-31 and 2019-06-28), so
  the set matches the sector funds that existed at each date.
- **Rule:** rank by the return from 12 month-ends ago to 1 month-end ago
  (12-1, Asness, Moskowitz and Pedersen); hold the top 3 at a third each
  (Moskowitz and Grinblatt; Faber 2010); re-rank monthly (Faber 2010). Always
  invested: negative returns stay eligible. Ties go to the lower ticker. With
  fewer than three ranked ETFs, the empty slots stay in cash.
- **First full decision:** 1999-12-31.
- **Departure:** Moskowitz and Grinblatt hold for six months; we follow
  Faber 2010's monthly re-ranking.
- **Disclosure:** close to the 2026-10-03 ETF-9 trial (momentum 252/21 top 3,
  2016–2026); the registration cites it.

### Inverse-volatility allocation
- **ETFs:** SPY (stocks), IEF (government bonds), LQD (investment-grade
  corporate credit), GSG (commodities): Asness, Frazzini and Pedersen's four
  broad-sample asset classes.
- **Rule:** each month, an ETF's monthly excess return is its month-end-to-
  month-end return minus the T-bill return over the same month; σ is the
  standard deviation of its last 36 monthly excess returns; weights are
  1/σ scaled to sum to 1 across the ETFs with 36 months of history (the
  unlevered version). The 1/(n−1) or 1/n choice cancels in the scaling. An ETF
  with σ = 0 is skipped with a reason.
- **First full decision:** 2005-07-29 with SPY, IEF and LQD; GSG joins on
  2009-07-31. Here a missing ETF's weight is shared by the others, because
  the paper rescales across "the available asset classes".
- **Departures:** the S&P 500 stands in for the whole US market; IEF for all
  Treasuries; LQD for all credit (the paper also includes mortgage-backed and
  high-yield bonds). The levered version is not used: it scales to a
  volatility known only afterwards.

## 3. Code shape

- **`quant_core/strategies/plans.py` (new).** One frozen config per rule
  (`TrendPlan`, `DualMomentumPlan`, `SectorRotationPlan`,
  `InverseVolatilityPlan`) on a shared keyword-only base with `name`,
  `invested_fraction` (default 0.95), `decision_offset` (0), `volume_lookback`
  (20), `max_volume_participation` (0.01) and `purpose`. Each rule has a pure
  function from month-end values (and T-bill growths) of the eligible ETFs to
  weights, scores, ranks, reason codes and features, testable without the
  engine. `builtin_plans()` returns the four configurations above.
- **`MonthlyPlan` source.** Binds the config, calendar, security registry,
  first signal session, execution profile and, for the two T-bill rules, the
  cash-rate series. It computes decision sessions, runs data checks, calls the
  rule, converts weights to orders through the shared helper, and records one
  `SignalDecision` per ETF per decision with the numbers behind it. The source
  spec (`PlanSpec`) records the rule, config, price policy, calendar, decision
  sessions, execution profile and the full rate series; its hash covers all of
  them. `evaluate(context)` projects a decision without trading, on decision
  sessions only.
- **`validate_run`.** The existing checks (calendar and start binding,
  registry, universe within the run universe, execution profile, complete
  actions, raw volume, `risk=None`), plus: the plan's rate series must give a
  non-stale rate for every session from the earliest lookback start of the
  first decision in the run to the last decision in the run. The engine's own
  preflight covers only the run's sessions.
- **Shared pieces.** The `scheduled_slots` order logic moves out of
  `RuleStrategy.evaluate` into a helper used by both sources; existing results
  must stay byte-identical. The compounding loop in
  `SessionContext.cash_growth` moves to `CashRateSeries` so the engine context
  and the plans share one implementation.
- **No reference series.** None of the four plans needs one, so references
  are not wired into plan configs.

## 4. Deflated Sharpe ratio — `quant_core/validation/statistics.py`

- `return_moments(returns)`: per-period Sharpe (mean over sample standard
  deviation), number of returns T, skewness m₃/m₂^1.5 and raw kurtosis m₄/m₂²
  (population central moments; normal returns give 0 and 3).
- `expected_maximum_sharpe(trials, sharpe_variance)`: Eq. 1 with zero mean,
  SR₀ = √V · ((1−γ) Φ⁻¹(1 − 1/N) + γ Φ⁻¹(1 − 1/(N·e))), γ the
  Euler–Mascheroni constant.
- `deflated_sharpe_ratio(sharpe, observations, skewness, kurtosis, trials,
  sharpe_variance)`: Eq. 2,
  Φ((SR − SR₀)·√(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²)).
  Sharpe and its variance are per period, never annualized.
- `deflated_sharpe(returns, trials, sharpe_variance)` combines the two and
  returns every input and intermediate value for the evidence pack.
- Refused: N < 2, V < 0, T < 2, returns with zero variance, or a
  non-positive term under the square root. Moments are exact Decimals; Φ and Φ⁻¹ use the standard
  library's `NormalDist` in binary floating point, so results agree across
  platforms to far better than the four decimals a pack shows.

## 5. Documentation

- `docs/STRATEGIES.md`: a "Built-in plans" section with the rules, ETFs,
  sources, departures, first decisions and API.
- `docs/STRATEGY_EVIDENCE.md`: the Periods row adds "since the first public
  version of the plan's primary rule source"; the date is verified and
  recorded in the registration.
- `docs/VALIDATION.md`: the DSR formulas, conventions and API.
- `docs/ROADMAP.md` row D, `README.md`, version 0.7.0.

## 6. Testing

- **Rules, by hand:** for each rule, small month-end series with expected
  weights worked out by hand: trend above, below and equal; dual momentum's
  three outcomes, the strict T-bill test and the SPY tie; sector ranks where
  the skipped month would change the order, negative winners, fewer than three
  ranked; inverse volatility with series chosen for exact σ values, excess
  over T-bills, a missing ETF's weight shared, σ = 0.
- **Sampling:** decision sessions across holidays and month boundaries;
  offsets ±2; dividends and splits inside the lookback.
- **Through the engine:** one synthetic run per plan, with fills and final
  equity worked out by hand.
- **No look-ahead:** changing prices, dividends or rates after a decision
  leaves that decision and its orders unchanged.
- **Preflight:** a run refused when rates do not cover the first lookback;
  identical decisions with the run's idle-cash rate set or None.
- **Data checks:** an ETF joining exactly when its history suffices; a
  missing session skips the ETF with a reason.
- **Unchanged behaviour:** existing strategy fixtures and the full suite give
  byte-identical results after the helper extraction.
- **DSR:** the paper's example (N = 100, V = 1/2 annualized, T = 1250,
  γ₃ = −3, γ₄ = 10, SR = 2.5 annualized → SR₀ ≈ 0.1132 per period,
  DSR ≈ 0.9004), its N = 46 variant (≈ 0.9505) and its normal-returns N = 88
  variant (≈ 0.9505); moments of a short hand-worked series; each refusal.

## Not in this step

- Step E: the ETF download command; registration files; runs on real data;
  evidence packs including the since-publication period; excess-return Sharpe
  and Sortino; the historical V[SR] floor; freezing the rate series by hash;
  how the research campaign runner passes cash rates.
- Step G: a decision on the latest month-end when the data ends exactly on it
  (`rebalance_dates` needs the next session to recognise a month-end);
  evaluation between month-ends.
- Weekly decisions (optional in the roadmap) are not built.
