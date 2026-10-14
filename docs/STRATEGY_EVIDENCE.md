# Built-in strategy evidence standard

Adopted 2026-10-08. Design record:
[strategy qualification standard](superpowers/specs/2026-10-08-strategy-qualification-standard-design.md).
Supports PR-05, PR-06, PR-08 and PR-13. This document is normative for
built-in strategies. Where `PROJECT.md`, `AGENTS.md`, [the validation
contract](VALIDATION.md) or any research document disagrees, this one governs.

V1 ships **at least three distinct rule-based built-ins (target four) plus the
ML-ranked rotation**.
A strategy qualifies by meeting the definition below and shipping its complete
evidence pack. There is **no return, Sharpe or benchmark-beating threshold**.
A strategy that lost to buy-and-hold over the research period may ship if its
pack says so plainly; showing that honestly is part of the product.

## 1. Definition of a qualified built-in

All six must hold:

1. **Economic rationale and sources.** A stated hypothesis (why it should
   work and who the counterparty is) with at least two independent published
   sources.
2. **Fixed rules, declared in the registration before the registered run.**
   Universe, signals, rebalance schedule, exits, risk overlays, costs, cash
   handling and sizing. Each parameter names the specific published source it
   comes from. A deviation from the source is documented with its reason; a
   reason based on performance observed on already inspected data is not
   allowed. Every related ledger row (same signal family on overlapping
   instruments or dates) is cited with its outcome.
3. **Verified implementation.** Hand-calculated test cases, a no-look-ahead
   test, and the registered run reproduces byte-for-byte from saved inputs.
4. **Complete evidence pack** (Section 2) produced once from the registered
   configuration, with no tuning after inspection.
5. **Distinct role.** Each built-in occupies one of the roles below, and no
   two built-ins share a role. Parameter variants, sizing presets, benchmarks
   and cash controls do not count as separate strategies. Each pack reports
   daily-return correlation and holdings overlap with every previously
   registered built-in; the latest pack therefore covers all of them.
6. **Plain-language limitations page** covering data limitations (history
   length, provider, survivorship where relevant), regimes in which the
   strategy has lost money, and what it does not promise.

Hard exclusions: no economic rationale, no published sources, parameters
chosen after seeing results, or behavior that cannot be explained to a user
in a paragraph.

### V1 roles and candidates

V1 built-ins are ETF-based. Survivor-selected stock panels are never used as
evidence for a built-in; stock-based strategies require survivorship-free,
point-in-time data and remain research candidates until then.

| Role | V1 candidate | Starting sources |
| --- | --- | --- |
| Cross-asset trend following | Multi-asset time-series trend | Faber 2007; Moskowitz, Ooi and Pedersen 2012 |
| Tactical equity/bond allocation | Dual momentum: relative and absolute momentum with a bond fallback | Antonacci 2014; Asness, Moskowitz and Pedersen 2013 |
| Equity sector rotation, always invested | US sector rotation by 12-1 momentum | Jegadeesh and Titman 1993; Moskowitz and Grinblatt 1999 |
| Diversified defensive allocation | Inverse-volatility / risk-parity allocation | Maillard, Roncalli and Teïletche 2010; Asness, Frazzini and Pedersen 2012 |
| Model-ranked multi-asset rotation | ML-ranked rotation over a frozen ~60-ETF universe (Ridge baseline, then gradient-boosted ranking) | Gu, Kelly and Xiu 2020; Burges 2010 |

Candidates overlap with configurations already inspected, including
momentum and trend recipes on ETF-9 and low-volatility stock recipes (see
[the research ledger](RESEARCH_LEDGER.md)); every registration cites its
related rows under rule 2.

The ML-ranked rotation's evidence pack also compares it with the plain 12-1
momentum rule on the same universe and reports its overlap and return
correlation with sector rotation. If the model adds nothing over the rule, the
first page says so. Its scores are shown as ranks with a measured hit rate,
never as probabilities.

## 2. Evidence pack

Generated from one registered run plus its declared variants. A changed
configuration is a new registration. A correction (for example after an engine
bug fix) is also a new registration: both outcomes stay on record and the fix
carries a regression test.

| Part | Content |
| --- | --- |
| Registration | Section 3 fields, including the cumulative trial count. |
| Results | Net of costs at 10, 25 and 50 bps per side: CAGR, volatility, Sharpe, Sortino, maximum drawdown, Calmar, longest underwater period, exposure, turnover, trade count, whole-share and opening-gap rejections. Formulas as in [the validation contract](VALIDATION.md), except the reference rate (Cash row). |
| Uncertainty | Stationary-bootstrap 95% intervals for CAGR, Sharpe, maximum drawdown and benchmark-relative Sharpe, with registered block lengths, repetitions and seed. Deflated Sharpe ratio (Section 4). |
| Periods | Effective start after signal warmup; calendar years; predeclared windows 2016–2019, 2020–2022, 2023–2026; since the first public version of the plan's primary rule source (date verified and recorded in the registration); best and worst 12 months; five largest drawdowns with recovery time. |
| Sensitivity | Parameter neighbours, rebalance-day shift (±2 sessions), second-open delay, cost ladder. Reported only; never used to select. |
| References | The registered primary reference, plus SPY buy-and-hold, 60/40 SPY/IEF and equal weight of the universe for every built-in, and T-bill cash. |
| Cash | Idle cash earns the lagged 3-month T-bill yield, and Sharpe and Sortino use excess returns over that same series. A secondary variant reports 0% cash against a 0% reference rate. |
| Forward record | Prospective signal journal started when the strategy ships; hash-chained; each record committed to git. |
| Limitations | The plain-language page from Section 1. |
| Reproduction | One command and the hashes needed to reproduce every number. |

## 3. Research process

- **Registration file.** `docs/registrations/<study>.json`, committed before
  the run. Fields: configuration hashes for every declared configuration, panel
  (instrument set and provider dataset hash), period, engine hash, declared
  variants, cost scenarios, primary reference, parameter sources and any
  deviation reasons (rule 2), related ledger rows (rule 2), any planned
  independent-provider cross-check, bootstrap block lengths, repetitions and
  seed, deflated-Sharpe inputs (Section 4), cumulative trial count and
  registration time. The file format, the runs and the commands are in
  [the validation contract](VALIDATION.md), "Registered studies".
- **Tag.** An annotated git tag `study/<name>-<YYYY-MM-DD>` on the commit that
  contains the registration file and the exact source. Tags are never moved or
  deleted. The tag is the source archive; do not copy source trees. When the
  owner authorises it, study tags are pushed at registration so the remote
  provides an external timestamp.
- **Ledger.** One line per study in [the research ledger](RESEARCH_LEDGER.md),
  including failures and abandoned studies, with panel, inspected period, tag
  and registration hash.
- **Evidence.** Run bundles are stored once under `local/<study>/`.
- **Changes.** A change after inspecting results is a new registration with a
  new tag that cites the prior trial count. Old outcomes are never edited.

## 4. Trial count and deflated Sharpe ratio

The trial count feeds the deflated Sharpe ratio (Bailey and López de Prado,
2014). Count **one per (configuration, panel) pair declared in a registration
or run**, whether or not its outcome was looked at. A panel is an instrument
set together with a provider dataset.

- Configurations that differ in signal, universe, rebalance schedule
  (including rebalance-day shifts), exits, stops, risk overlays or sizing
  method each count. Parameter neighbours, controls and reversed-direction
  variants count.
- Scenarios that do not count: cost levels, execution delay, evaluation period,
  cash-yield convention, and pure exposure scaling (a different invested
  fraction with otherwise identical rules), even when registered as a control.
- References (buy-and-hold, 60/40, equal weight, cash) do not count.
- The same configuration on a different panel counts again, except an
  independent-provider cross-check declared in the original registration and
  never used for selection.
- Evaluating an unchanged registered configuration on later data (a forward
  journal or an extension of the same instruments and provider) does not count.
  The pack keeps the registered panel's results; extension results are added
  alongside them, never in place of them.
- Reruns that reproduce an earlier result (engine replays) do not count.
- Whenever classification is ambiguous, record the larger defensible number
  and say why in the ledger.

Deflated Sharpe inputs, stated in every pack and computed per parent:

- **N:** the ledger's cumulative trial count including the current study's
  declared configurations. A per-role count is reported alongside.
- **V[SR]:** the primary DSR uses the larger of these two variances of daily
  Sharpe ratios, each a sample variance (dividing by n − 1); the pack also
  reports DSR under the smaller one:
  - the study's own: across the configurations declared in the current
    registration (at least three: the parent and its declared neighbours;
    rebalance-shift copies excluded), at 10 bps, under this document's cash and
    reference-rate convention;
  - the historical floor: one Sharpe per counted ledger trial, taken from the
    study row that counted it: its zero-reference `sharpe` metric for the
    10 bps continuous period, divided by √252 to give a daily value. It is
    computed once from the sealed evidence, with the script and the list of
    trials committed, and recorded in the ledger header before the first
    registration under this standard. It is not recomputed afterwards.
- **T, skewness, kurtosis:** the number of daily returns in the primary
  period and the skewness and raw kurtosis (3 for normal returns) of the
  strategy's daily excess returns, from population central moments as
  `return_moments` computes them.

## 5. Data and disclosure

- Tiingo daily data is used for building, researching and registering the
  tester-release built-ins (owner decision 2026-10-11; see
  [the roadmap](ROADMAP.md)): raw prices with dividends and splits, checked
  against Tiingo's adjusted closes at import. Alpaca daily data stays internal
  development data; confirming Alpaca's terms for commercial research use is
  an open action item.
- Before publishing reference numbers, the project owner decides whether an
  independent-provider cross-check is feasible, and with which provider
  (Tiingo's own adjusted closes are not independent); the pack records the
  decision and its reason, and any cross-check result. Tiingo must also confirm
  that published derived results are not data redistribution (an open item in
  the roadmap).
- All inspected history is listed in the ledger by panel and period. Forward
  journals and future sessions supply fresh evidence; previously inspected
  history is disclosed, never relabelled as untouched.
- Daily bars only in V1. Hourly data may support execution-realism checks.
