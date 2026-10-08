# Built-in strategy evidence standard

Adopted 2026-10-08. Design record:
[strategy qualification standard](superpowers/specs/2026-10-08-strategy-qualification-standard-design.md).
Supports PR-05, PR-06, PR-08 and PR-13. This document is normative; where an
older research document disagrees, this one governs.

V1 ships **3–4 distinct built-in strategies** (minimum three; target four).
A strategy qualifies by meeting the definition below and shipping its complete
evidence pack. There is **no return, Sharpe or benchmark-beating threshold**.
A strategy that lost to buy-and-hold over the research period may ship if its
pack says so plainly; showing that honestly is part of the product.

## 1. Definition of a qualified built-in

All six must hold:

1. **Economic rationale and sources.** A stated hypothesis (why it should
   work and who the counterparty is) with at least two independent published
   sources.
2. **Fixed rules, declared before any backtest.** Universe, signals, rebalance
   schedule, costs, cash handling and sizing. Parameters are the literature's;
   any deviation is documented with its reason.
3. **Verified implementation.** Hand-calculated test cases, a no-look-ahead
   test, and the registered run reproduces byte-for-byte from saved inputs.
4. **Complete evidence pack** (Section 2) produced once from the registered
   configuration, with no tuning after inspection.
5. **Distinct role.** Each built-in occupies a different portfolio role
   (for example trend-following, momentum/rotation, defensive allocation).
   Parameter variants, sizing presets, benchmarks and cash controls do not
   count as separate strategies.
6. **Plain-language limitations page** covering data limitations (history
   length, provider, survivorship where relevant), regimes in which the
   strategy has lost money, and what it does not promise.

Hard exclusions: no economic rationale, no published sources, parameters
chosen after seeing results, or behavior that cannot be explained to a user
in a paragraph.

## 2. Evidence pack

Generated from one registered run plus its declared variants. Never re-run
after inspection; a changed configuration is a new registration.

| Part | Content |
| --- | --- |
| Registration | Strategy configuration hash, engine hash, data manifest (provider, dataset hash, period, limitations), declared cost scenarios, declared parameter neighbours, cumulative trial count (Section 4). |
| Results | Net of costs at 10, 25 and 50 bps per side: CAGR, volatility, Sharpe, Sortino, maximum drawdown, Calmar, longest underwater period, exposure, turnover, trade count, whole-share and opening-gap rejections. Formulas: [validation contract](VALIDATION.md). |
| Uncertainty | Stationary-bootstrap 95% intervals for CAGR, Sharpe, maximum drawdown and benchmark-relative Sharpe. Deflated Sharpe ratio (Bailey and López de Prado, 2014) using the cumulative trial count. |
| Periods | Calendar years; predeclared windows 2016–2019, 2020–2022, 2023–2026; best and worst 12 months; five largest drawdowns with recovery time. |
| Sensitivity | Parameter neighbours, rebalance-day shift (±2 sessions), second-open delay, cost ladder. Reported only; never used to select. |
| References | Role-appropriate buy-and-hold (SPY for equity roles, 60/40 SPY/IEF for allocation roles), equal weight of the universe, T-bill cash. |
| Cash | Idle cash earns lagged 3-month T-bill yield. The 0% variant is also reported. |
| Forward record | Prospective signal journal started when the strategy ships; hash-chained; each record committed to git. |
| Limitations | The plain-language page from Section 1. |
| Reproduction | One command and the hashes needed to reproduce every number. |

## 3. Research process

- `REGISTRATION.json` per study: configuration hashes, dataset hash, engine
  hash, declared variants, costs and periods, cumulative trial count,
  registration time.
- Git tag `study/<name>-<YYYY-MM-DD>` on the exact source before the run.
  The tag is the source archive; do not copy source trees.
- One line per study in [the research ledger](RESEARCH_LEDGER.md),
  including failures and abandoned studies.
- Run bundles are stored once under `local/<study>/` and referenced by hash.
- A change after inspecting results is a new registration with a new tag
  that cites the prior trial count. Old outcomes are never edited.

## 4. Trial-count convention

The cumulative trial count feeds the deflated Sharpe ratio. Count **one per
(strategy configuration, data panel) pair whose outcome was inspected**:

- parameter neighbours, controls and reversed-direction variants each count;
- cost, delay, period and sizing scenarios of the same configuration do not;
- references (buy-and-hold, equal weight, cash) do not;
- the same configuration on a different panel counts again;
- reruns that reproduce an earlier result (engine replays) do not.

When a historical study's registration makes the count ambiguous, record the
larger defensible number and say so in the ledger.

## 5. Data and disclosure

- Free Alpaca daily data is acceptable for building and researching built-ins.
- Before publishing reference numbers, cross-check on an independent provider
  where feasible (target: Tiingo business plan). If not done, the pack says so.
- All inspected history is listed in the ledger. Forward journals and future
  sessions supply fresh evidence; previously inspected history is disclosed,
  never relabelled as untouched.
- Daily bars only in V1. Hourly data may support execution-realism checks.
