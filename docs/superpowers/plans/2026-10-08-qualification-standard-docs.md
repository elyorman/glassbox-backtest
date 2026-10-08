# Qualification Standard — Documentation Rewrite Implementation Plan

> **Executed 2026-10-08.** Review rounds revised Tasks 2–7; the committed documents are authoritative where they differ from the text below.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pass/fail built-in-strategy qualification contract with the disclosed-evidence standard from the approved spec, so every agent session and future study inherits one consistent rule.

**Architecture:** Documentation-only plan (Plan A of five). It adds one normative doc (`docs/STRATEGY_EVIDENCE.md`), one ledger (`docs/RESEARCH_LEDGER.md`), rewrites the governing sections of `PROJECT.md`, `AGENTS.md` and `README.md`, marks superseded research docs, and fixes the forward-journal command. A small link-check test guards the rewrite. No engine code changes; those are Plans B–E.

**Tech Stack:** Markdown, Python 3.12 `unittest` (no third-party test deps), git.

**Spec:** `docs/superpowers/specs/2026-10-08-strategy-qualification-standard-design.md`

**Repo rules that apply:** commit after each task with a concise descriptive message (no ticket IDs, no co-author trailers); never commit anything under `local/`; run tests with `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest ...` from the repo root.

---

## File map

| File | Action | Responsibility |
| --- | --- | --- |
| `tests/test_docs_links.py` | Create | Fails if any relative Markdown link in README/PROJECT/AGENTS/docs points at a missing file. |
| `docs/STRATEGY_EVIDENCE.md` | Create | The normative standard: definition, evidence pack, research process, trial-count convention. |
| `docs/RESEARCH_LEDGER.md` | Create | One line per study, past and future, with cumulative trial count. |
| `PROJECT.md` | Modify (4 places) | Reference Strategies section, Stage 5 retest paragraph, release gate 2, decision-log bullets. |
| `AGENTS.md` | Modify (5 places) | Built-in paragraph, provider decision, validation paragraph, data-cost bullet, status section. |
| `README.md` | Modify (lines 19–95) | Status summary replaces the changelog. |
| `docs/FORWARD_SHADOW.md` | Modify (line 33) | Correct capture command. |
| `docs/HANDOFF.md` | Modify ("Exact next task") | Point at the new standard and plans. |
| 10 research docs | Modify (line 1) | One-line superseded note. |

---

### Task 1: Markdown link-check test

**Files:**
- Create: `tests/test_docs_links.py`

- [ ] **Step 1: Write the test**

```python
"""Relative Markdown links in governing docs must resolve; broken links hide superseded rules."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)\s]*)?(?:\s+\"[^\"]*\")?\)")
SCHEME = re.compile(r"[a-z]+://", re.IGNORECASE)


def governing_documents():
    # Plans and specs under docs/superpowers quote link text inside code blocks; they are not governing docs.
    documents = [path for path in DOCS.rglob("*.md") if path.relative_to(DOCS).parts[0] != "superpowers"]
    return [ROOT / "README.md", ROOT / "PROJECT.md", ROOT / "AGENTS.md"] + sorted(documents)


def link_is_broken(document, target):
    """A link must resolve to a tracked-location file inside the repository, never under ignored local/."""
    resolved = (document.parent / target).resolve()
    inside_repo = ROOT == resolved or ROOT in resolved.parents
    under_local = ROOT / "local" in resolved.parents
    return not resolved.exists() or not inside_repo or under_local


class DocsLinkTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        broken = []
        for document in governing_documents():
            for match in LINK.finditer(document.read_text(encoding="utf-8")):
                target = match.group(1)
                if SCHEME.match(target) or target.startswith("mailto:"):
                    continue
                if link_is_broken(document, target):
                    broken.append(f"{document.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [], "Broken relative links:\n" + "\n".join(broken))

    def test_governing_documents_exist(self):
        for name in ("STRATEGY_EVIDENCE.md", "RESEARCH_LEDGER.md"):
            self.assertTrue((DOCS / name).exists(), f"docs/{name} is required by the standard")
```

(Review on 2026-10-08 added repo-bound target checks, title/scheme handling and the `Tests` class-name convention; committed as a follow-up to the first commit.)

- [ ] **Step 2: Run the test and confirm the second case fails**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_docs_links -v`
Expected: `test_relative_links_resolve ... ok`, `test_governing_documents_exist ... FAIL` (AssertionError: docs/STRATEGY_EVIDENCE.md is required by the standard).

- [ ] **Step 3: Commit the test (red is expected until Task 3)**

```bash
git add tests/test_docs_links.py
git commit -m "Add Markdown link-check test for governing documents"
```

---

### Task 2: `docs/STRATEGY_EVIDENCE.md`

> **Revised after review (2026-10-08):** the committed `docs/STRATEGY_EVIDENCE.md` and
> `docs/RESEARCH_LEDGER.md` supersede the text below (commits 42bf585 and 6796b8b):
> T-bill Sharpe convention, stricter trial counting (ledger total 44), DSR inputs with a
> historical V[SR] floor, committed registrations in annotated tags, four named ETF roles,
> and ledger panel/period/tag columns.

**Files:**
- Create: `docs/STRATEGY_EVIDENCE.md`

- [ ] **Step 1: Write the file**

```markdown
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
```

- [ ] **Step 2: Run the link test**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_docs_links -v`
Expected: both FAIL, and the only broken link is `docs/STRATEGY_EVIDENCE.md -> RESEARCH_LEDGER.md` (created in Task 3; the two documents link to each other, so Tasks 2 and 3 run back to back).

- [ ] **Step 3: Commit**

```bash
git add docs/STRATEGY_EVIDENCE.md
git commit -m "Add built-in strategy evidence standard"
```

---

### Task 3: `docs/RESEARCH_LEDGER.md`

Counts below follow Section 4 of the standard and were derived from the run
directories under `local/` on 2026-10-08 (`ls local/<study>/runs`, recipe is
the part after `<period>_<cost>_`). References excluded; neighbours and
controls included; same configuration on a second panel counted again.

**Files:**
- Create: `docs/RESEARCH_LEDGER.md`

- [ ] **Step 1: Write the file**

```markdown
# Research ledger

One line per study, past and future. Append only; never edit an outcome.
Counting rule: [evidence standard, Section 4](STRATEGY_EVIDENCE.md#4-trial-count-convention).
Studies before 2026-10-08 predate the git-tag process; their source archives
and evidence remain under `local/` on the original machine.

| Date | Study | Source | Trials | Cumulative | Outcome | Evidence |
| --- | --- | --- | ---: | ---: | --- | --- |
| 2026-10-03 | ETF market backtest (momentum 252/21 top 3 on 9 sector SPDRs) | pre-tag | 1 | 1 | Exploratory; no nominee | `local/market-backtest-2026-10-03/` |
| 2026-10-03 | All ten predefined recipes on the same sector-ETF panel (momentum 252/21 top 3 already counted) | pre-tag | 9 | 10 | No reliable benchmark superiority | `local/strategy-comparison-2026-10-03/` |
| 2026-10-03 | Robustness audit, two ETF parents: 6 momentum and 4 trend variants (lookback, top-k, mean window, ATR stop, 75% allocation; allocation variants counted conservatively) | pre-tag | 10 | 20 | Both parents fail predeclared objectives | `local/robustness-audit-2026-10-03/` |
| 2026-10-03 | Stock campaign, 22-stock survivor panel (4 parents + 4 neighbours) | pre-tag | 8 | 28 | SMA200 passes defensive screen; others fail | `local/stock-campaign-2026-10-03-finalized/` |
| 2026-10-05 | Corrected-engine replay of the 99 stock trials | pre-tag | 0 | 28 | Byte-identical outcomes | `local/stock-engine-replay-2026-10-05/` |
| 2026-10-05 | Universe transfer, 47-stock survivor panel (same 8 configurations) | pre-tag | 8 | 36 | All four parents fail full rule | `local/universe-transfer-2026-10-05-v2/` |
| 2026-10-05 | 52-week-high proximity, both panels (parent + neighbour × 2) | pre-tag | 4 | 40 | Rejected on both panels | `local/high-anchor-2026-10-05/` |
| 2026-10-06 | Unusual dollar volume, both panels (2 ranked + 1 control × 2) | pre-tag | 6 | 46 | Rejected on both panels; direction check fails | `local/volume-2026-10-06-finalized/` |
| 2026-10-06 | Research design review; market-adjusted momentum specification | pre-tag | 0 | 46 | Frozen, **paused 2026-10-08**, not run | `local/research-design-review-2026-10-06/` |
| 2026-10-08 | Qualification standard replaced (disclosed evidence, ETF-based built-ins) | commit 3f8c70f | 0 | 46 | Decision | [spec](superpowers/specs/2026-10-08-strategy-qualification-standard-design.md) |

Forward journals:

| Registered | Journal | Status |
| --- | --- | --- |
| 2026-10-05 | SMA200 trend, original 22-stock recipe | Zero records; first window after the 2026-10-30 close. See [forward journal](FORWARD_SHADOW.md). |
```

- [ ] **Step 2: Run the link test**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_docs_links -v`
Expected: both tests `ok`.

- [ ] **Step 3: Commit**

```bash
git add docs/RESEARCH_LEDGER.md
git commit -m "Add research ledger seeded with 2026-10 studies"
```

---

### Task 4: `PROJECT.md`

**Files:**
- Modify: `PROJECT.md` — Reference Strategies section (currently lines 953–993), Stage 5 paragraph starting "Freeze promising candidates" (line 1260), release gate 2 (line 1312), decision-log bullets at lines 1329 and 1346.

Use exact-string edits; line numbers shift after the first edit.

- [ ] **Step 1: Replace the Reference Strategies section**

Find the block that begins `## Reference Strategies` and ends with the paragraph ending `...relabel examined history as fresh validation.` (just before `## Production Models`). Replace it with:

```markdown
## Reference Strategies

V1 must ship **3–4 distinct, well-researched built-in strategies** (minimum
three; target four), ready to configure, scan, backtest, validate and inspect
through Desktop with explainable risk/sizing defaults. The qualification and
delivery contract is [the built-in strategy evidence standard](docs/STRATEGY_EVIDENCE.md),
adopted 2026-10-08. In summary, a built-in qualifies when it has:

- an economic rationale with at least two independent published sources;
- fixed rules declared in a committed registration before the run, each
  parameter sourced from the literature and related prior studies cited;
- a verified implementation (hand-calculated tests, no-look-ahead test,
  byte-for-byte reproduction);
- a complete evidence pack: net-of-cost results at three cost levels,
  bootstrap uncertainty and a deflated Sharpe ratio using the disclosed trial
  count, period and drawdown breakdowns, sensitivity tables, a registered
  primary reference plus SPY, 60/40 and equal-weight references, T-bill cash
  yield, a forward signal journal and a reproduction command;
- a distinct portfolio role from every other built-in;
- a plain-language limitations page.

There is no return, Sharpe or benchmark-beating threshold. Honest evidence that
a strategy underperformed in some regime is a deliverable, not a failure.

The V1 candidates are ETF-based and literature-backed: multi-asset
time-series trend, dual momentum, US sector rotation and defensive
inverse-volatility allocation. Stock-based strategies remain research
candidates for a later stage with survivorship-free data. Every study,
including failures, is recorded in [the research ledger](docs/RESEARCH_LEDGER.md).
Do not fill the quota with parameter variants, change a registered
configuration after seeing results, or relabel inspected history as untouched.
```

- [ ] **Step 2: Replace the Stage 5 retest paragraph**

Find the paragraph beginning `Freeze promising candidates and re-test with better independent data before commercial reference claims.` and replace the whole paragraph with:

```markdown
Before publishing reference numbers, the project owner decides whether to
cross-check a built-in on an independent provider and records the decision and
reason in its evidence pack. Another vendor over
the same dates is a data cross-check, not a new temporal holdout. All inspected
history is listed in [the research ledger](docs/RESEARCH_LEDGER.md); forward
journals and future sessions supply fresh evidence.
```

- [ ] **Step 3: Replace release gate 2**

Find: `2. at least three distinct built-in strategies (target four) meet the Reference Strategies qualification/delivery contract, with documented methodology and honest OOS/walk-forward evidence; supplied models meet the same relevant evidence standard;`

Replace with: `2. at least three distinct built-in strategies (target four) meet [the built-in strategy evidence standard](docs/STRATEGY_EVIDENCE.md), each with its complete evidence pack and limitations page; supplied models meet the same relevant evidence standard;`

- [ ] **Step 4: Update the two decision-log bullets**

Find: `- V1 requires 3–4 distinct, well-researched, validated built-in strategies (minimum three; target four); the research platform and custom builder do not replace this requirement.`

Replace with: `- V1 requires 3–4 distinct, well-researched built-in strategies (minimum three; target four) under the 2026-10-08 disclosed-evidence standard; the research platform and custom builder do not replace this requirement. V1 candidates are ETF-based.`

Find: `- Use free/free-tier market data for initial development/training/backtesting where permitted, then re-test frozen promising candidates on a paid/higher-quality and preferably independent dataset before commercial reference claims.`

Replace with: `- Use free/free-tier market data for development and built-in strategy research where permitted; cross-check on an independent provider where feasible before publishing reference numbers, and disclose if not done. Paid survivorship-free data is a later requirement for stock-based strategies, not for V1 ETF built-ins.`

- [ ] **Step 5: Run the link test**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_docs_links -v`
Expected: both `ok`.

- [ ] **Step 6: Commit**

```bash
git add PROJECT.md
git commit -m "Adopt disclosed-evidence standard in PROJECT.md"
```

---

### Task 5: `AGENTS.md`

**Files:**
- Modify: `AGENTS.md` — five exact-string edits.

- [ ] **Step 1: Replace the built-in strategy paragraph**

Find the paragraph beginning `V1 also requires **3–4 distinct, well-researched, validated built-in strategies**` and ending `continue bounded research if fewer than three qualify.` Replace with:

```markdown
V1 also requires **3–4 distinct, well-researched built-in strategies**
(minimum three; target four) under
[the built-in strategy evidence standard](docs/STRATEGY_EVIDENCE.md), adopted
2026-10-08: disclosed evidence packs, no pass/fail return threshold, ETF-based
V1 candidates, one registration and git tag per study, and
[the research ledger](docs/RESEARCH_LEDGER.md) for every outcome. Engine
tools, parameter/sizing variants and benchmarks do not count as strategies.
Where any other document disagrees with the standard, the standard governs.
```

- [ ] **Step 2: Replace the provider-decision paragraph**

Find the paragraph beginning `Current user decision (2026-10-05): continue with existing Alpaca data/account` and ending `See \`docs/ALPACA_RESEARCH.md\`.` Replace with:

```markdown
Current user decision (2026-10-08): build and research V1 ETF built-ins on
the existing Alpaca daily data. Cross-check on an independent provider
(target: Tiingo business plan) before publishing reference numbers; disclose
if not done. Paid survivorship-free data is deferred to a later stock-strategy
stage. Confirming Alpaca's terms for commercial research use is an open
action item. See `docs/STRATEGY_EVIDENCE.md`, Section 5.
```

- [ ] **Step 3: Replace the first Validation Requirements paragraph**

Find the paragraph beginning `The initial rule-strategy campaign API/CLI is documented in \`docs/VALIDATION.md\`.` and ending `and a disclosure of previously exposed periods.` Replace with:

```markdown
The campaign API/CLI in `docs/VALIDATION.md` remains available as a research
tool; built-in qualification follows `docs/STRATEGY_EVIDENCE.md` instead of
its nomination gates. Keep failure history and evidence hashes intact. Do not
relabel synthetic engineering campaigns as empirical validation or a
maximum-mean bootstrap diagnostic as DSR. Changing a configuration after
inspecting results is a new registration with a new git tag that cites the
prior trial count.
```

- [ ] **Step 4: Replace the data-cost bullet**

Find: `- For promising candidates, freeze the methodology/configuration, obtain a better paid dataset/provider, and re-run the important experiments from scratch. Prefer an independent-provider cross-check before shipping/reference claims.`

Replace with: `- Before publishing reference numbers for a built-in, cross-check on an independent provider where feasible and disclose if not done. Paid survivorship-free data is required before stock-based strategies can become built-ins.`

- [ ] **Step 5: Add the ledger to the status section**

Find: `See [audit remediation](docs/AUDIT_REMEDIATION.md) for corrected engine/data behavior and [research status](docs/RESEARCH_STATUS.md) for dated evidence.`

Replace with: `See [audit remediation](docs/AUDIT_REMEDIATION.md) for corrected engine/data behavior, [the research ledger](docs/RESEARCH_LEDGER.md) for every study and its trial count, and [research status](docs/RESEARCH_STATUS.md) for dated historical evidence (superseded rules noted at its top).`

- [ ] **Step 6: Run the link test**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_docs_links -v`
Expected: both `ok`.

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md
git commit -m "Point agent instructions at the evidence standard"
```

---

### Task 6: `README.md`

**Files:**
- Modify: `README.md` lines 19–95 (from `V1 must include **3–4 distinct...` through `...registered; no model training was run.`), keeping lines 1–18 and the final command block.

- [ ] **Step 1: Replace lines 19–95 with**

```markdown
V1 must include **3–4 distinct, well-researched built-in strategies** (minimum
three; target four), ready for no-code use. They qualify under
[the built-in strategy evidence standard](docs/STRATEGY_EVIDENCE.md): disclosed
evidence packs with uncertainty and limitations, no return, Sharpe or
benchmark-beating threshold. V1 built-ins are ETF-based (candidates:
multi-asset trend, dual momentum, sector rotation, inverse-volatility
allocation). **No built-in is qualified yet.**

The agreed build order is:

1. Market-data layer
2. Backtester
3. Risk/money management
4. Strategies
5. Validate strategies
6. ML models
7. Scanner/analytics
8. Desktop UI
9. Packaging/licensing/website

## Status

| Stage | State |
| --- | --- |
| 1 Data | Built: CSV/JSON/Parquet snapshots, EODHD import, dated index membership, action audit. Open: provider qualification, columnar storage for index-scale history. |
| 2 Backtester | Built: next-open execution, shared cash, costs, splits/dividends/delistings, stops, audit bundles. Open: target/trailing exits, entry-to-exit trade records. |
| 3 Risk/sizing | Built. |
| 4 Strategies | Six research families implemented. ETF built-ins: not started. |
| 5 Validation | Campaign framework built; evidence-pack generator not started. |
| 6–9 | Not started. |

Research history, including every failed study and the cumulative trial
count, is in [the research ledger](docs/RESEARCH_LEDGER.md). Detailed
contracts: [data layer](docs/DATA_LAYER.md), [backtester](docs/BACKTESTER.md),
[risk](docs/RISK_MANAGEMENT.md), [strategies](docs/STRATEGIES.md),
[validation](docs/VALIDATION.md), [data integration](docs/DATA_INTEGRATION.md),
[universes](docs/UNIVERSES.md), [reproducibility](docs/REPRODUCIBILITY.md).
Historical research findings: [research status](docs/RESEARCH_STATUS.md).
The SMA200 [forward signal journal](docs/FORWARD_SHADOW.md) has its first
capture window after the 2026-10-30 close.

## Development
```

- [ ] **Step 2: Confirm the file now reads: title, intro (lines 1–18), the new block, then the existing bash block and the closing paragraph**

Run: `grep -n "^## " README.md`
Expected: `## Status` and `## Development` headings present; no duplicated "agreed build order" text.

- [ ] **Step 3: Run the link test**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_docs_links -v`
Expected: both `ok`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Replace README changelog with status summary"
```

---

### Task 7: Forward-journal command, handoff, superseded notes

**Files:**
- Modify: `docs/FORWARD_SHADOW.md:33`
- Modify: `docs/HANDOFF.md` ("Exact next task" section)
- Modify (line 1): `docs/RESEARCH_STATUS.md`, `docs/RESEARCH_DECISION_REVIEW.md`, `docs/RESEARCH_DESIGN_REVIEW.md`, `docs/MARKET_ADJUSTED_EXPERIMENT.md`, `docs/NEXT_EXPERIMENT.md`, `docs/VOLUME_RESEARCH.md`, `docs/HIGH_ANCHOR_RESEARCH.md`, `docs/UNIVERSE_TRANSFER.md`, `docs/INDEPENDENT_DATA_RETEST.md`, `docs/ALPACA_RESEARCH.md`

- [ ] **Step 1: Fix the capture command**

In `docs/FORWARD_SHADOW.md`, find:

```
PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.forward_shadow capture \
```

Replace with:

```
PYTHONPATH=local/sma200-forward-2026-10-05/source-archive PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.forward_shadow capture \
```

Immediately after the closing triple backtick of that command block, insert:

```markdown
The capture refuses to run from the live source tree once any registered file
has changed; the journal's frozen archive is the required runtime. Run it from
the repository root (the `.env` path is relative), between 16:15 ET on the
signal day and 09:29 ET on the next session. Avoid 16:00–16:15 ET: the free
Alpaca plan may refuse the most recent bars, and a failed response is cached
and blocks that output directory. Use a fresh `--output` directory after any
HTTP error.
```

- [ ] **Step 2: Verify the archived runtime still matches the registration**

Run: `PYTHONPATH=local/sma200-forward-2026-10-05/source-archive PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m research.forward_shadow verify --journal local/sma200-forward-2026-10-05`
Expected: JSON with `"signal_records": 0` and `"chain_head": "058a33c9a004f2fbf4241b58c40a1c7523fcf920ee5acd6b489ff61186e636fc"`.

- [ ] **Step 3: Replace the HANDOFF "Exact next task" section body**

Replace the paragraph beginning `Implement the [frozen market-adjusted momentum specification]` (four lines, ending `implemented-runtime registration.`) with the block below. Keep the next paragraph (the byte-frozen method SHA-256) unchanged. Delete the paragraph after it, beginning `One 36-month market-adjusted parent` and ending `automatically another distinct strategy toward the release quota.`, including its trailing blank line.

```markdown
The 2026-10-08 [built-in strategy evidence standard](STRATEGY_EVIDENCE.md)
replaced the pass/fail contract. Next work follows the standard's plans in
`docs/superpowers/plans/`: documentation rewrite (done), verified bug fixes,
engine prerequisites (cash yield, read-only references, bar frequency), the
four ETF strategy families, then ETF data collection and the first evidence
pack.

The [market-adjusted momentum specification](MARKET_ADJUSTED_EXPERIMENT.md) is
paused, not run. Its frozen method hash and registration envelope remain on
record:
```

- [ ] **Step 4: Add the superseded note to the ten research docs**

Insert after the first line (the `# ` title) of each listed file, with one blank line before and after it:

```markdown
> Superseded by the [2026-10-08 strategy qualification standard](STRATEGY_EVIDENCE.md); retained as research history. Outcomes recorded here are unchanged and are counted in [the research ledger](RESEARCH_LEDGER.md).
```

- [ ] **Step 5: Run the link test and the full suite**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `Ran 606 tests` (604 existing + 2 new), `OK`.

- [ ] **Step 6: Commit**

```bash
git add docs/FORWARD_SHADOW.md docs/HANDOFF.md docs/RESEARCH_STATUS.md docs/RESEARCH_DECISION_REVIEW.md docs/RESEARCH_DESIGN_REVIEW.md docs/MARKET_ADJUSTED_EXPERIMENT.md docs/NEXT_EXPERIMENT.md docs/VOLUME_RESEARCH.md docs/HIGH_ANCHOR_RESEARCH.md docs/UNIVERSE_TRANSFER.md docs/INDEPENDENT_DATA_RETEST.md docs/ALPACA_RESEARCH.md
git commit -m "Mark superseded research docs and fix forward-journal command"
```

---

### Task 8: Final check

- [ ] **Step 1: Confirm no stale rule text remains in governing files**

Run: `grep -n "retest on qualified better independent data\|validated built-in strategies\|frozen methodology and a retest" PROJECT.md AGENTS.md README.md`
Expected: no output.

- [ ] **Step 2: Confirm nothing under `local/` is staged and the tree is clean**

Run: `git status --short && git log --oneline -8`
Expected: empty status apart from this plan file. As executed, review rounds added follow-up commits beyond the eight planned ones; see `git log 3f8c70f..`.

---

## Self-review

- **Spec coverage:** Decisions 1–4 → Tasks 2, 4, 5. Section 1 → Task 2 §1. Section 2 → Task 2 §2. Section 3 → Task 2 §3, Task 3. Section 4 → Tasks 3 (paused experiment, ledger), 5 (provider decision, Alpaca action item), 7 (journal command, superseded notes). Documentation changes list → Tasks 4–7. Sections 5 (engine) and Testing-engine items are Plans B–E by design.
- **Placeholders:** none; every edit shows its full text.
- **Consistency:** the file name `STRATEGY_EVIDENCE.md`, ledger name, trial count 44, and tag format `study/<name>-<YYYY-MM-DD>` are identical across tasks.

## Follow-on plans (separate documents)

- **Plan B** — verified bug fixes: EODHD split-adjusted volume gate, provider adjusted-close split cross-check, Parquet fsync on Windows.
- **Plan C** — engine prerequisites: `RunConfig.cash_yield`, read-only references in `SessionContext`, `DataMetadata.bar_frequency`.
- **Plan D** — strategy families `ts_trend`, `dual_momentum`, `inverse_vol` with hand-calculated tests; deflated Sharpe ratio.
- **Plan E** — ETF data collection, evidence-pack generator, first registered study.
