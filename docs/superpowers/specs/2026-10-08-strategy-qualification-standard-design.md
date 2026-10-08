# Strategy qualification standard — design

Date: 2026-10-08. Decision owner: Elyorjon Mannonov.
Status: approved in discussion; awaiting written-spec review.

## Problem

The V1 release gate requires 3–4 validated built-in strategies. Under the
current Reference Strategies contract none can qualify, whatever their merit:

- Qualification requires survivorship-free point-in-time data, an independent
  provider retest and genuinely uninspected history. All 2016–2026 history is
  declared exposed, Alpaca history starts in 2016, and paid data is deferred.
- The pass/fail rules stack many noisy Sharpe comparisons. A Monte Carlo of the
  frozen market-adjusted rule passes a genuinely better strategy (Sharpe 0.95
  vs 0.79) only 12–34% of the time on one panel.
- Modeling conventions decide outcomes. Idle cash earns 0% while Sharpe uses a
  T-bill reference; with T-bill yield on cash, SMA200's broader-panel fold
  failures become passes.
- The equal-weight reference on survivor panels is inflated (17.0%/yr vs SPY
  13.85%), biasing tests against trend, momentum and low-volatility.

The blocker is the standard, not the data or the engine. This design replaces
the standard. It does not lower the honesty bar; it removes the coin-flip verdict
and replaces it with complete disclosure.

## Decisions

1. **Evidence bar: disclosed evidence, no pass/fail threshold.** Each built-in
   ships with its full net-of-cost evidence, uncertainty, worst periods and
   limitations. No return, Sharpe or benchmark-beating threshold decides
   inclusion. A strategy that lost to buy-and-hold over 2016–2026 may ship if
   the pack says so plainly. Hard exclusions: no economic rationale, no
   published sources, parameters chosen after seeing results, or behavior that
   cannot be explained to a user in a paragraph.
2. **Candidates: four ETF-based, literature-backed roles.**
   - Multi-asset time-series trend (Faber 2007; Moskowitz, Ooi, Pedersen 2012).
   - Dual momentum / global equities momentum (Antonacci 2014).
   - US sector rotation, 12-1 momentum (Jegadeesh & Titman 1993; Moskowitz &
     Grinblatt 1999).
   - Defensive inverse-volatility / risk-parity allocation (Asness, Frazzini,
     Pedersen 2012).
   Stock-based strategies remain research candidates for a later paid-data
   stage; they are not V1 built-ins.
3. **Data: free Alpaca daily data for building and research; an independent
   cross-check (target: Tiingo business plan) before publishing reference
   numbers.** Daily bars only in V1; hourly data is reserved for execution
   realism checks. The data contract gains a bar-frequency field so intraday
   can be added later without a rewrite.
4. **Process: one registration file and a git tag per study; one research
   ledger; run once.** No copied source trees, no duplicated run bundles, no
   multi-file seals.

## Section 1 — Definition of a qualified built-in

A built-in strategy qualifies when all of the following hold:

1. **Economic rationale and sources.** A stated hypothesis (why it should work
   and who the counterparty is) with at least two independent published
   sources.
2. **Fixed rules, declared before any backtest.** Universe, signals, rebalance
   schedule, costs, cash handling and sizing. Parameters are the literature's;
   any deviation is documented with its reason.
3. **Verified implementation.** Hand-calculated test cases, a no-look-ahead
   test, and the registered run reproduces byte-for-byte from saved inputs.
4. **Complete evidence pack** (Section 2) produced once from the registered
   configuration, with no tuning after inspection.
5. **Distinct role.** Each built-in occupies a different portfolio role.
   Parameter variants, sizing presets, benchmarks and cash controls do not
   count as separate strategies.
6. **Plain-language limitations page** covering data limitations (history
   length, provider, survivorship where relevant), regimes in which the
   strategy has lost money, and what it does not promise.

## Section 2 — Evidence pack

Generated from one registered run plus its declared variants. Contents:

| Part | Content |
| --- | --- |
| Registration | Strategy config hash, engine hash, data manifest (provider, dataset hash, period, limitations), declared cost scenarios, declared parameter neighbours, cumulative trial count for the research line. |
| Results | Net of costs at 10 / 25 / 50 bps per side: CAGR, volatility, Sharpe, Sortino, max drawdown, Calmar, longest underwater, exposure, turnover, trade count, whole-share/opening-gap rejections. Formulas as documented in `docs/VALIDATION.md`. |
| Uncertainty | Stationary-bootstrap 95% intervals (existing implementation) for CAGR, Sharpe, max drawdown and benchmark-relative Sharpe. Deflated Sharpe ratio (Bailey & López de Prado 2014) using the disclosed cumulative trial count. |
| Periods | Calendar years; predeclared windows 2016–2019, 2020–2022, 2023–2026; best and worst 12 months; five largest drawdowns with recovery time. |
| Sensitivity | Parameter neighbours (e.g. SMA 8/10/12 months), rebalance-day shift (±2 sessions), second-open delay, cost ladder. Reported only; never used to select. |
| References | Role-appropriate buy-and-hold (SPY for equity roles, 60/40 SPY/IEF for allocation roles), equal weight of the universe, T-bill cash. |
| Cash | Idle cash earns lagged 3-month T-bill yield (existing `cash_rates.csv` input). The 0% variant is also reported. |
| Forward record | Prospective signal journal started when the strategy ships; hash-chained; each record committed to git. |
| Limitations | The plain-language page from Section 1. |
| Reproduction | One command and the hashes needed to reproduce every number. |

## Section 3 — Research process

- `REGISTRATION.json` per study: config hashes, dataset hash, engine hash,
  declared variants/costs/periods, cumulative trial count, registration time.
- Git tag `study/<name>-<YYYY-MM-DD>` on the exact source before the run.
- `docs/RESEARCH_LEDGER.md`: one line per study (date, name, tag, trial count,
  outcome, bundle location). Failures stay.
- Run bundles stored once under `local/<study>/`, referenced by hash. No copied
  source archives; the git tag is the archive.
- A change after inspecting results is a new registration with a new tag that
  cites the prior trial count. Old outcomes are never edited.

## Section 4 — Existing rules and studies

| Existing rule / artifact | Disposition |
| --- | --- |
| Six stock studies (288 scenarios) | Retained in the ledger as history; trial count carried into DSR disclosure; none are candidates. |
| Market-adjusted momentum experiment | Paused, not run; spec retained. |
| SMA200 forward journal | Continues; documented capture command corrected to the frozen archive. |
| "Independent retest before production/reference claims" | Becomes "independent cross-check where feasible, disclosed if not done" (release gate 11). |
| "Previously inspected history cannot serve as fresh evidence" | Becomes a disclosure. Forward journals and future years supply fresh evidence. |
| Survivor stock panels | Not used for built-ins. |
| Alpaca research use | Action item: confirm commercial-research terms with Alpaca by email. |

Research docs that describe superseded rules get one line at the top:
"Superseded by the 2026-10-08 strategy qualification standard; retained as
research history."

## Section 5 — Engine prerequisites

Small, tested changes, in order. Each is its own commit.

1. `RunConfig.cash_yield`: optional lagged daily-rate series. Accrual is a
   cash movement credited at each session; default none keeps old results
   byte-identical.
2. Read-only reference symbols in `SessionContext`: `RunConfig.references`
   lists symbols a strategy may read but not trade.
3. Strategy families `ts_trend`, `dual_momentum`, `inverse_vol`; sector
   rotation reuses `momentum` with monthly scheduling.
4. `validation/statistics`: deflated Sharpe ratio. `reporting`: evidence-pack
   generator (JSON plus Markdown).
5. ETF data collection via the existing Alpaca collector: SPY, EFA, EEM, IEF,
   TLT, GLD, VNQ, BIL and the 11 sector SPDRs, from 2016-01-04.
6. Verified bug fixes: block or reconstruct EODHD split-adjusted volume before
   it reaches liquidity features; correct the forward-journal command;
   cross-check unrecorded splits against provider adjusted close.
7. `DataMetadata.bar_frequency` (default `"daily"`, the only accepted value in
   V1) so intraday support later does not change the snapshot contract.

## Documentation changes

- `PROJECT.md` Reference Strategies: replace with Sections 1–2 summary and a
  link to `docs/STRATEGY_EVIDENCE.md`.
- `AGENTS.md`: replace the built-in-strategy paragraph and the "do not relabel
  / exposed history" guidance with the new standard and process.
- New `docs/STRATEGY_EVIDENCE.md`: Sections 1–3 in full.
- New `docs/RESEARCH_LEDGER.md`: seeded with the existing studies.
- `README.md`: replace the changelog with a status summary and links.
- Superseded-note line on affected research docs.

## Out of scope

Hourly/intraday strategies; stock-based built-ins; paid data purchase;
declarative strategy schema for the no-code builder (separate product work);
documentation consolidation (after the first ETF study).

## Testing

Documentation changes: link check (existing test pattern). Engine changes:
unit tests per prerequisite, the existing no-look-ahead and reconciliation
suites, and byte-identical replay of one existing run with defaults unchanged.
