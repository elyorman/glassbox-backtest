# Fundamental Accounting and Capital Evidence

Authorized 2026-10-04 after [original-filing reconciliation](FUNDAMENTAL_RECONCILIATION.md).
Supports PR-01, PR-05, PR-06, PR-08 and PR-13. Native execution in the existing
virtual environment; no branch, commit, purchase or performance optimization.

## Goal and architecture

Recover explicitly scoped original accounting and capital components, audit
preferred obligations and share/split basis, then recompute feasibility on the
unchanged 17-stock panel and ten-issuer floor. Preserve every previous audit and
its processing sources. A separate research-only parser and campaign extend the
old reader; existing SEC modules and trading-engine files stay unchanged.
Technology: Python standard library, Decimal, unittest, immutable local JSON
registries and HTML reports. Raw/public evidence remains in ignored `local/`.

## Global constraints

- Prior fiscal year is determined by its actual ending calendar year; annual
  durations are 330–380 days; filings must be strictly before June formation.
- December market equity requires exactly December 31 shares. No nearby date,
  interpolation, current float, EPS average or generic issued-share substitute.
- Dimensional facts require reviewed exact axis/member scope. No automatic sum
  of segments/classes; no unidentified dimension may disappear during parsing.
- Preferred valuation follows redemption, liquidation, then par. Missing facts
  never prove zero; investment assets and authorization are not issuer liabilities.
- Source/hash-bound reviews must precede component arithmetic. Unreviewed
  missing-instance amendment substitutions, new conflicts and missing inputs
  fail closed. Financial amendments with independently validated original
  instances remain eligible available vintages.
- New evidence cannot manufacture point-in-time universe membership, complete
  price/actions, licensed independent data or an untouched temporal holdout.

## Review focus

1. Product/member accounting with extra geography/class axes must be rejected.
2. An issued tag can already mean net shares; avoid subtracting treasury twice.
3. Nonfinancial-amendment review cannot allow a different accession/body/date.
4. Preferred amount/unit/issuer/date/class must match parent equity; nil is missing.
5. Missing split observations do not prove none occurred; supplied-feed checks
   remain separate from original share-basis evidence and provider qualification.

## Implementation tasks

### 1. Scoped original inputs and accounting arithmetic

Files: create `python/research/sec_scoped.py`, `tests/test_sec_scoped.py`.
Interfaces: `parse_scoped(bytes)` and `parse_scoped_inline(bytes)` return original
numeric rows with exact normalized axis/member tuples; `crosscheck_scoped`
compares selected scoped primary/extracted records. No global parser mutation.

- [x] Test exact member identity, extra/typed dimensions, context/unit/issuer
  conflicts, unknown namespaces, nil/scaling, nested inline facts and duplicates.
- [x] Implement parser and inline adapter using existing transformations and
  precision reconciliation; test realistic XBRL fixtures before real inputs.

### 2. Bounded accounting and capital rules

Files: create `python/research/sec_capital.py`, `tests/test_sec_capital.py`,
`docs/fundamental_capital_rules.json`.
Interfaces: `costco_profit`, `issued_less_treasury`, `preferred_deduction`,
`check_amendment`, and `share_basis` return evidence/explicit missing reasons.

- [x] Test Costco product revenue plus membership equals consolidated revenue,
  same annual scope/assets, and original direct-profit agreement when supplied.
- [x] Test class-matched issued/treasury arithmetic, invalid negative counts,
  exact dates, already-net issued semantics and conflicting direct observations.
- [x] Test affirmative zero versus missing preferred; precedence, original USD
  amounts versus per-share values, noncontrolling/class/investment exclusions.
- [x] Test accession/hash-bound amendment exemptions and unknown amendments.
- [x] Test original vintage/split-date checks using actual serialized Split.
- [x] Freeze concrete issuer rules/review evidence from original filings; do not
  add generic tag priorities or financial formulas merely to improve coverage.

### 3. Registered collection, audit and semantic verification

Files: create `python/research/sec_capital_audit.py`,
`tests/test_sec_capital_audit.py`; update current project documentation.
Interfaces: CLI `plan|collect|audit|verify`, separate versioned local output.

- [x] Register parent audit/sources, exact document requests, panel/calendar,
  reviewed mappings and snapshot. Reuse immutable raw evidence; collect any
  missing primary documents through indexed SEC endpoints before review.
- [x] Compute 190 rows only after input/source/review registration. Preserve
  prior evidence and report recovered components, complete capital candidates,
  blockers, supplied-feed split checks and unchanged readiness/qualification gates.
- [x] Test offline manifest completeness, missing requests, reviewed-body
  tampering, changed scope and resealed arithmetic/report tampering.
- [x] Run real audit and semantic verifier; independent code review, focused
  and full tests. Record infeasibility if fixed panel still misses the floor.

Performance campaign launch is a separate readiness decision: component
improvements alone do not authorize weakening research standards.

## Evidence contract and operation

The implementation consists of three new research modules; the earlier SEC
and trading modules remain unchanged. `sec_scoped` keeps exact axis/member
identities, opaque scopes, declared accuracy, issuer and units. Its inline
adapter restores divided-unit casing lost by HTML parsing and crosschecks
selected numeric values, precision and scope against original extracted XML.
Foreign namespaces, extra axes and unknown contexts cannot become approved
whole-issuer components.

`sec_capital` implements hand-tested component arithmetic. The versioned
[review rules](fundamental_capital_rules.json) bind two nonfinancial amendment
exemptions to exact original/amendment body hashes, issuer, period and explanatory
notes. Unrelated or financial amendments receive no missing-instance exemption.
The reviewed MCD FY2023 original balance-sheet note proves no issued preferred
stock; the rounded numeric zero alone does not. Positive preferred carrying
amounts or class-specific obligations contradict an affirmative absence.
Same-day capital vintages must agree on preferred evidence as well as equity.

For Costco FY2018–25, product revenue plus membership fees must agree with the
consolidated reported total under declared accuracy. Merchandise gross profit
is product revenue less merchandise costs, preserving its issuer-specific cost
classification. This is an SEC-as-reported adaptation, not normalized Compustat
replication or qualified accounting comparability. Current original periods are
used; transition/comparative dimensions do not backfill history.

CVX, KO and MCD counts use reviewed whole common issued less treasury counts.
PEP's issued count already means net of repurchases; subtracting treasury again
is incorrect. Only original annual December-31 periods qualify for these
recipes. KO/MCD million/100,000 rounding remains an interval, not an exact count.
First available share observations and later-vintage flags in the previous
report remain available. Current-period original/class checks are separate from
complete price/action-feed proof; this snapshot declares incomplete actions,
so every share-basis gate remains false.

PG's two ESOP series are inventoried as a class-scoped liquidation arithmetic
candidate even when eligible parent equity is unavailable. Both series sit in
legal convertible Class A; ESOP Series B is not legal preferred Class B. Its
candidate is not a reviewed deduction: redemption priority and complete class
coverage are unresolved. PEP fair-value/carrying amounts also remain unresolved.
Missing KO preferred evidence never becomes zero. The valuation hierarchy is
redemption, then liquidation, then par with outstanding shares and explicit
higher-priority absence/class review. [French variable definitions](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/variable_definitions.html)

The CLI reuses the previous audit's exact indexed responses and request records;
this stage needs zero new downloads. Registration precedes publishing derived
results. It pins all parent files/sources, the market snapshot and current
processing code plus frozen rules. Verification re-verifies the parent audit,
checks source/input registration, and independently recomputes every derived
row, coverage field and HTML report. Rehashing an incorrect derived number does
not make it semantically valid. Previous failed attempts and audited reports
are preserved unchanged; generated material remains in ignored local storage.

```bash
PYTHONPATH=python .venv/bin/python -m research.sec_capital_audit plan \
  --parent local/sec-reconciliation-2026-10-04-v3 \
  --output local/sec-capital-2026-10-04
# Optional offline response validation; collect downloads nothing.
PYTHONPATH=python .venv/bin/python -m research.sec_capital_audit collect \
  --output local/sec-capital-2026-10-04
PYTHONPATH=python .venv/bin/python -m research.sec_capital_audit audit \
  --output local/sec-capital-2026-10-04
PYTHONPATH=python .venv/bin/python -m research.sec_capital_audit verify \
  --output local/sec-capital-2026-10-04
```

Outputs are exclusive-create. `plan` and `audit` cannot overwrite an existing
registration/result. Frozen inputs changing makes verification fail; a changed
study needs a new output directory and registration.

## Fixed-panel result and next boundary

The unchanged 190 issuer/formation audit recovers 99 profitability records,
103 December share records and 160 parent-equity records, compared with 91,
71 and 158 in the preceding stage. These totals include GOOGL/UPS evidence
outside the 17-stock common panel and are not simultaneous eligible portfolios.
The audit also records 73 affirmative preferred-zero deductions, 63 positive
common-book candidates and ten PG class-liquidation candidates. These are
component evidence; missing/negative book equity does not enter a value ranking.
Every value-readiness and production-qualification flag remains false.

| June formation | Common profitability components | Common Dec31 shares | Minimum |
|---|---:|---:|---:|
| 2017 | 10 | 11 | 10 |
| 2018 | 10 | 9 | 10 |
| 2019 | 10 | 9 | 10 |
| 2020 | 10 | 9 | 10 |
| 2021 | 9 | 9 | 10 |
| 2022 | 10 | 9 | 10 |
| 2023 | 10 | 11 | 10 |
| 2024 | 10 | 9 | 10 |
| 2025 | 10 | 9 | 10 |
| 2026 | 10 | 9 | 10 |

The registered fixed-panel study is **infeasible under its component-coverage
requirements**. The 2021 profitability shortfall and eight December-share
shortfalls remain; no performance campaign launches. More tag arithmetic is
not permission to weaken the floor or calendar. A broader, point-in-time
universe/accounting methodology would require a separately registered study
before performance, with licensed independent prices/actions and untouched
validation evidence. This stage does not authorize that change, purchase data
or train models. Zero strategies are commercially qualified; the minimum-three,
target-four release requirement remains outstanding.

## Acceptance evidence

The Linux/Python 3.12 suite passes 388 tests, including 84 SEC tests and 31 new
scoped/capital/audit tests. Financial cases include hand-derived revenue/member
reconciliation, treasury and already-net counts, precision ranges, class/par
arithmetic, missing/rounded zero, carrying/class contradictions, original
note/amendment tampering, actual Split schema, same-day capital conflicts,
missing/changed request bodies and resealed derived-result tampering.
Independent review found and reproduced the preferred carrying/class and
same-day-vintage gaps; both now have passing regressions and no important
findings remain. All 150 scoped primary/XML pairs agree. Real semantic
verification, source preservation and ignored-output checks accompany the
completed local report at `local/sec-capital-2026-10-04/REPORT.html`.

The exact 36 registered processing sources and both reviewed rule files are
also preserved at `local/sec-capital-2026-10-04/source-archive/`. Execute the
archived verifier while this registered dataset remains locally available:

```bash
PYTHONPATH=local/sec-capital-2026-10-04/source-archive/python \
  .venv/bin/python -m research.sec_capital_audit verify \
  --output local/sec-capital-2026-10-04
```

June 2021's remaining JNJ profitability gap follows the unchanged calendar
rule: its FY2020 actually ended 2021-01-03, outside prior calendar year 2020.
The share-count gaps follow exact December-31 availability and reviewed issuer
capital meanings. Neither justifies selecting a nearby date for convenience.

The subsequent [broader candidate study](BROAD_UNIVERSE_RESEARCH.md) is separately
registered and preserves this fixed-panel result. It collects historical SEC
indexes and fixes a review sample without relaxing accounting dates, issuer
counts or input-evidence gates. Filing discovery does not qualify a stock
universe or change the unlaunched performance status of this capital audit.
