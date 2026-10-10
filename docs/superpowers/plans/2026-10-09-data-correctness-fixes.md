# Data Correctness Fixes (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three verified data bugs from the 2026-10-08 review: split-adjusted EODHD volume reaching raw-share liquidity rules, weak missed-split detection, and a Parquet `fsync` that fails on Windows.

**Architecture:** (1) An explicit volume basis via the existing `DataMetadata.adjustment_policy` field (new allowed value, so existing dataset hashes are unchanged); strategies and risk-enabled runs refuse non-raw volume. (2) A provider-neutral cross-check of declared splits/dividends against a provider's back-adjusted closes, wired into the EODHD importer; the price-only heuristic becomes more sensitive and stays a warning by default. (3) `fsync` on a writable handle.

**Tech Stack:** Python 3.12 stdlib `Decimal`/`unittest`; optional `pyarrow` for Parquet tests.

**Design approval:** 2026-10-09 (block adjusted volume now; raw-volume reconstruction deferred to the EODHD customer-adapter work; Alpaca split-adjusted cross-check deferred to Plan E data collection).

**Test commands:** single-module runs need `tests/` on the path because some tests import sibling test modules: use `PYTHONPATH=python:tests` wherever a step names a module (e.g. `tests.test_audit_quality`). `discover -s tests` already does this.

**Repo rules:** commit after each task with the given message (no ticket IDs, no co-author trailers; a local hook rejects them). Never stage anything under `local/`. Run tests from the repo root with `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest ...`. Baseline: 606 tests pass.

**Prototype evidence:** applying these changes to a scratch copy, the only existing test that changes outcome is `test_universe_strategy.test_original_provider_response_to_parquet_to_dated_portfolio`, which ran a strategy on EODHD volume (the bug itself). Task 2 rewrites it.

---

## File map

| File | Change |
| --- | --- |
| `python/quant_core/data/__init__.py` | `RAW_PRICES_SPLIT_ADJUSTED_VOLUME`, `ADJUSTMENT_POLICIES`, `require_raw_volume()` |
| `python/quant_core/data/eodhd.py` | Label volume basis; cross-check `adjusted_close` |
| `python/quant_core/data/adjustments.py` | `AdjustmentDisagreement`, `provider_adjustment_disagreements()` |
| `python/quant_core/data/quality.py` | Add 3:4 and 4:3 ratios; tolerance 0.5% → 3% |
| `python/quant_core/data/parquet.py` | Writable handle for `fsync` |
| `python/quant_core/strategies/__init__.py` | `validate_run` requires raw volume (also covers `VolumeStrategy`, which reuses it) |
| `python/quant_core/backtest/engine.py` | Risk-enabled runs require raw volume |
| `tests/test_data.py`, `tests/test_eodhd.py`, `tests/test_audit_quality.py`, `tests/test_parquet.py`, `tests/test_universe_strategy.py` | New/updated cases |
| `tests/test_volume_basis.py`, `tests/test_adjustment_crosscheck.py` | New |
| `docs/DATA_LAYER.md`, `docs/DATA_INTEGRATION.md`, `docs/BACKTESTER.md`, `docs/UNIVERSES.md`, `pyproject.toml`, `python/quant_core/__init__.py` | Docs and version 0.5.2 |

---

### Task 1: Explicit volume basis in `DataMetadata`

**Files:** Modify `python/quant_core/data/__init__.py`; Test `tests/test_data.py`

- [ ] **Step 1: Write the failing test** — add to class `SchemaTests` in `tests/test_data.py`, directly after `test_exact_decimals_and_rejection_of_ambiguous_numbers`:

```python
    def test_split_adjusted_volume_policy_is_explicit_and_blocks_liquidity_rules(self):
        from quant_core.data import RAW_PRICES_SPLIT_ADJUSTED_VOLUME, require_raw_volume
        adjusted = replace(META, adjustment_policy=RAW_PRICES_SPLIT_ADJUSTED_VOLUME)
        self.assertEqual(adjusted.adjustment_policy, "raw_prices_split_adjusted_volume")
        require_raw_volume(META, "Liquidity filter")
        with self.assertRaisesRegex(ValueError, "Liquidity filter: raw share volume required"):
            require_raw_volume(adjusted, "Liquidity filter")
        self.assertEqual(snapshot().dataset_hash, snapshot(metadata=replace(META)).dataset_hash)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_data.SchemaTests.test_split_adjusted_volume_policy_is_explicit_and_blocks_liquidity_rules -v`
Expected: ERROR, `ImportError: cannot import name 'RAW_PRICES_SPLIT_ADJUSTED_VOLUME'`.

- [ ] **Step 3: Implement** — in `python/quant_core/data/__init__.py`:

Directly above `@dataclass(frozen=True)\nclass DataMetadata:` insert:

```python
RAW_PRICES_SPLIT_ADJUSTED_VOLUME = "raw_prices_split_adjusted_volume"
ADJUSTMENT_POLICIES = ("raw", RAW_PRICES_SPLIT_ADJUSTED_VOLUME)  # Prices are always raw.


```

In `DataMetadata`, change the field line `    adjustment_policy: str = "raw"` to:

```python
    adjustment_policy: str = "raw"  # Volume basis: "raw" or RAW_PRICES_SPLIT_ADJUSTED_VOLUME.
```

and replace

```python
        if self.adjustment_policy != "raw":
            raise ValueError("Execution snapshots must contain raw prices")
```

with

```python
        if self.adjustment_policy not in ADJUSTMENT_POLICIES:
            raise ValueError("Execution snapshots must contain raw prices")
```

Directly after the end of the `DataMetadata` class (before `@dataclass(frozen=True)\nclass Security:`) insert:

```python
def require_raw_volume(metadata: DataMetadata, purpose: str) -> None:
    """Liquidity rules count shares in each bar's own units; adjusted volume would double-count splits."""
    if metadata.adjustment_policy != "raw":
        raise ValueError(f"{purpose}: raw share volume required, but this snapshot's volume is "
                         f"split-adjusted (adjustment_policy={metadata.adjustment_policy}); reconstruct raw "
                         "volume from reviewed complete splits or use a raw-volume source")


```

- [ ] **Step 4: Run the test and the data suite**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_data -v 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/quant_core/data/__init__.py tests/test_data.py
git commit -m "Add explicit split-adjusted volume basis to data metadata"
```

---

### Task 2: Label EODHD volume and refuse it in liquidity rules

**Files:** Modify `python/quant_core/data/eodhd.py`, `python/quant_core/strategies/__init__.py`, `python/quant_core/backtest/engine.py`, `tests/test_eodhd.py`, `tests/test_universe_strategy.py`; Create `tests/test_volume_basis.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_volume_basis.py`:

```python
"""Split-adjusted provider volume must never reach raw-share liquidity rules."""

from dataclasses import replace
import json
import unittest

import test_universe_strategy as dated
from quant_core.backtest import OrderSchedule, RunConfig, run_backtest
from quant_core.data import RAW_PRICES_SPLIT_ADJUSTED_VOLUME
from quant_core.data.eodhd import EodhdJsonSource
from quant_core.execution import ExecutionProfile
from quant_core.risk import RiskPolicy
from quant_core.strategies import build_strategy


def adjusted(snapshot):
    return replace(snapshot, metadata=replace(snapshot.metadata, adjustment_policy=RAW_PRICES_SPLIT_ADJUSTED_VOLUME))


class VolumeBasisTests(unittest.TestCase):
    def test_rule_strategy_refuses_split_adjusted_volume(self):
        data, members, recipe = dated.fixture()
        data, execution = adjusted(data), ExecutionProfile("0")
        source = build_strategy(data, recipe, execution=execution, membership=members)
        with self.assertRaisesRegex(ValueError, "Strategy liquidity rules: raw share volume required"):
            run_backtest(data, source, RunConfig("1000", execution, recipe.universe))

    def test_risk_enabled_run_refuses_split_adjusted_volume(self):
        data, _, _ = dated.fixture()
        with self.assertRaisesRegex(ValueError, "Risk liquidity limits: raw share volume required"):
            run_backtest(adjusted(data), OrderSchedule(()), RunConfig("1000", ExecutionProfile("0"), risk=RiskPolicy()))

    def test_explicit_orders_without_liquidity_rules_still_run(self):
        data, _, _ = dated.fixture()
        result = run_backtest(adjusted(data), OrderSchedule(()), RunConfig("1000", ExecutionProfile("0")))
        self.assertEqual(result.summary.final_equity, 1000)

    def test_eodhd_import_labels_volume_basis_and_strategy_refuses_it(self):
        data, members, recipe = dated.fixture()
        responses = {asset + ".US": json.dumps([{"date": b.session.isoformat(), "open": str(b.open),
                                                  "high": str(b.high), "low": str(b.low), "close": str(b.close),
                                                  "volume": int(b.volume)} for b in data.bars
                                                 if b.security_id == asset]).encode()
                     for asset in recipe.universe}
        imported = EodhdJsonSource(responses, {a + ".US": a for a in recipe.universe}, data.sessions,
                                   data.securities, replace(data.metadata, source="eodhd", actions_complete=False)).load()
        self.assertEqual(imported.metadata.adjustment_policy, RAW_PRICES_SPLIT_ADJUSTED_VOLUME)
        execution = ExecutionProfile("0")
        with self.assertRaisesRegex(ValueError, "raw share volume required"):
            run_backtest(imported, build_strategy(imported, recipe, execution=execution, membership=members),
                         RunConfig("1000", execution, recipe.universe, actions_policy="allow_incomplete_diagnostic"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and confirm the refusals fail**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_volume_basis -v 2>&1 | tail -4`
Expected: `FAILED (failures=3)` — the two refusal tests and the EODHD labelling test fail (`test_explicit_orders_without_liquidity_rules_still_run` passes).

- [ ] **Step 3: Implement**

`python/quant_core/data/eodhd.py`: change the import line `from quant_core.data import Bar, DataMetadata, Security, Snapshot` to `from quant_core.data import Bar, DataMetadata, RAW_PRICES_SPLIT_ADJUSTED_VOLUME, Security, Snapshot`, and change

```python
        metadata = replace(self.metadata, limitations=tuple(dict.fromkeys(limitations)),
```

to

```python
        metadata = replace(self.metadata, adjustment_policy=RAW_PRICES_SPLIT_ADJUSTED_VOLUME,
                           limitations=tuple(dict.fromkeys(limitations)),
```

`python/quant_core/strategies/__init__.py`: change the import line to

```python
from quant_core.data import Security, Snapshot, identity, number, require_raw_volume, session
```

and make the first statement of `RuleStrategy.validate_run` (after its docstring):

```python
        require_raw_volume(snapshot.metadata, "Strategy liquidity rules")
```

`python/quant_core/backtest/engine.py`: change the import line to

```python
from quant_core.data import CashDelisting, Dividend, Snapshot, Split, require_raw_volume
```

and insert directly after `self.config = replace(config, start=start, end=end, universe=universe)`:

```python
        if config.risk is not None:
            require_raw_volume(snapshot.metadata, "Risk liquidity limits")
```

`tests/test_eodhd.py`: in `test_raw_ohlc_and_json_decimals_survive_without_adjusted_execution`, after the `split-adjusted volume` assertion add:

```python
        self.assertEqual(data.metadata.adjustment_policy, "raw_prices_split_adjusted_volume")
```

`tests/test_universe_strategy.py`: replace the whole method `test_original_provider_response_to_parquet_to_dated_portfolio` with:

```python
    @unittest.skipUnless(find_spec("pyarrow"), "Optional PyArrow is not installed")
    def test_provider_response_roundtrips_and_raw_volume_portfolio_runs_from_parquet(self):
        from quant_core.data import RAW_PRICES_SPLIT_ADJUSTED_VOLUME
        from quant_core.data.eodhd import EodhdJsonSource
        from quant_core.data.parquet import save_parquet_snapshot, load_parquet_snapshot
        data, members, recipe = fixture()
        responses = {asset+".US": json.dumps([{"date":b.session.isoformat(), "open":str(b.open),
                                                "high":str(b.high), "low":str(b.low), "close":str(b.close),
                                                "volume":int(b.volume)} for b in data.bars if b.security_id == asset]).encode()
                     for asset in recipe.universe}
        imported = EodhdJsonSource(responses, {a+".US":a for a in recipe.universe}, data.sessions,
                                  data.securities, replace(data.metadata, source="eodhd", actions_complete=False)).load()
        with TemporaryDirectory() as folder:
            save_parquet_snapshot(imported, Path(folder)/"provider")
            save_parquet_snapshot(data, Path(folder)/"raw")
            provider = load_parquet_snapshot(Path(folder)/"provider")
            raw = load_parquet_snapshot(Path(folder)/"raw")
        self.assertEqual(provider.dataset_hash, imported.dataset_hash)
        self.assertEqual(provider.metadata.adjustment_policy, RAW_PRICES_SPLIT_ADJUSTED_VOLUME)
        execution = ExecutionProfile("0")
        with self.assertRaisesRegex(ValueError, "raw share volume required"):
            run_backtest(provider, build_strategy(provider, recipe, execution=execution, membership=members),
                         RunConfig("1000", execution, recipe.universe, actions_policy="allow_incomplete_diagnostic"))
        result = run_backtest(raw, build_strategy(raw, recipe, execution=execution, membership=members),
                              RunConfig("1000", execution, recipe.universe))
        self.assertEqual([f.security_id for f in result.fills], ["A", "A", "B"])
        self.assertEqual(result.summary.final_equity, 1000)
```

- [ ] **Step 4: Run the affected tests, then the full suite**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_volume_basis tests.test_eodhd tests.test_universe_strategy -v 2>&1 | tail -3`
Expected: `OK`.
Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `Ran 611 tests`, `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/quant_core/data/eodhd.py python/quant_core/strategies/__init__.py python/quant_core/backtest/engine.py tests/test_volume_basis.py tests/test_eodhd.py tests/test_universe_strategy.py
git commit -m "Refuse split-adjusted EODHD volume in liquidity rules"
```

---

### Task 3: Provider-neutral adjustment cross-check

> **Revised after review:** commit 4da9380 supersedes the code below (tolerance 0.001, series-level rounding unit, `previous_session`/`reason` fields, 14 tests).

**Files:** Modify `python/quant_core/data/adjustments.py`; Create `tests/test_adjustment_crosscheck.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_adjustment_crosscheck.py`:

```python
"""Provider back-adjusted closes cross-check declared splits and dividends."""

from datetime import date
from decimal import Decimal
import unittest

from quant_core.data import Dividend, Split
from quant_core.data.adjustments import provider_adjustment_disagreements

D1, D2 = date(2024, 1, 2), date(2024, 1, 3)


def observations(*rows):
    return tuple((day, Decimal(raw), Decimal(adjusted)) for day, raw, adjusted in rows)


class ProviderAdjustmentTests(unittest.TestCase):
    def test_declared_split_explains_provider_adjustment(self):
        rows = observations((D1, "100", "50"), (D2, "50.5", "50.5"))
        split = Split("A", D2, new_shares=2, old_shares=1)
        self.assertEqual(provider_adjustment_disagreements(rows, (split,)), ())

    def test_unrecorded_split_with_ordinary_gap_is_reported(self):
        rows = observations((D1, "100", "50"), (D2, "50.5", "50.5"))
        (found,) = provider_adjustment_disagreements(rows, ())
        self.assertEqual((found.session, found.implied_factor, found.expected_factor),
                         (D2, Decimal("0.5"), Decimal("1")))

    def test_genuine_large_move_is_not_an_adjustment(self):
        rows = observations((D1, "150", "150"), (D2, "100", "100"))
        self.assertEqual(provider_adjustment_disagreements(rows, ()), ())

    def test_cash_dividend_factor_uses_previous_close(self):
        rows = observations((D1, "100", "98"), (D2, "99", "99"))
        self.assertEqual(provider_adjustment_disagreements(rows, (Dividend("A", D2, "2", D2),)), ())
        (found,) = provider_adjustment_disagreements(rows, ())
        self.assertEqual(found.implied_factor, Decimal("0.98"))

    def test_same_day_split_then_post_split_dividend(self):
        rows = observations((D1, "200", "99"), (D2, "99", "99"))
        actions = (Split("A", D2, new_shares=2, old_shares=1), Dividend("A", D2, "1", D2))
        self.assertEqual(provider_adjustment_disagreements(rows, actions), ())

    def test_provider_rounding_of_small_adjusted_values_is_allowed(self):
        rows = observations((D1, "100", "0.0050"), (D2, "100", "0.0051"))
        self.assertEqual(provider_adjustment_disagreements(rows, ()), ())

    def test_invalid_observations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "ascending"):
            provider_adjustment_disagreements(observations((D2, "1", "1"), (D1, "1", "1")), ())
        with self.assertRaisesRegex(ValueError, "positive"):
            provider_adjustment_disagreements(observations((D1, "1", "0")), ())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and confirm failure**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_adjustment_crosscheck -v 2>&1 | tail -3`
Expected: ERROR, `ImportError: cannot import name 'provider_adjustment_disagreements'`.

- [ ] **Step 3: Implement** — in `python/quant_core/data/adjustments.py` replace the import block

```python
from dataclasses import replace
from decimal import Decimal
```

with

```python
from dataclasses import dataclass, replace
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from quant_core.data import Dividend, Split, number
```

and append at the end of the file:

```python


@dataclass(frozen=True)
class AdjustmentDisagreement:
    session: date
    implied_factor: Decimal  # Provider: A(previous) / A(current).
    expected_factor: Decimal  # Declared splits and cash dividends in (previous, current].


def provider_adjustment_disagreements(observations, actions, tolerance="0.01"):
    """Compare a provider's back-adjusted closes with declared splits and cash dividends.

    `observations` are ascending (session, raw_close, provider_adjusted_close) for one
    security. A back-adjusted series is raw * A(t), so A(previous) / A(current) equals
    the product of the price factors of actions in (previous, current]. Declared actions
    give that product as the action-adjusted previous close divided by the previous
    close (split: old/new shares; cash dividend: (reference - amount) / reference).
    The provider's last-digit rounding is allowed on top of `tolerance`.
    """
    tolerance = number(tolerance)
    if tolerance < 0:
        raise ValueError("Adjustment tolerance cannot be negative")
    rows = tuple(observations)
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("Adjustment observations require ascending unique sessions")
    if any(raw <= 0 or adjusted <= 0 for _, raw, adjusted in rows):
        raise ValueError("Adjustment observations require positive raw and adjusted closes")
    price_actions = sorted((a for a in actions if isinstance(a, (Split, Dividend))),
                           key=lambda a: (a.session, isinstance(a, Dividend)))
    found = []
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        for (day0, raw0, adjusted0), (day1, raw1, adjusted1) in zip(rows, rows[1:]):
            reference = raw0
            for action in price_actions:
                if day0 < action.session <= day1:
                    reference = (action.adjust_price(reference) if isinstance(action, Split)
                                 else reference - action.amount)
            expected = reference / raw0
            implied = (adjusted0 / raw0) / (adjusted1 / raw1)
            allowance = _half_unit(adjusted0) / adjusted0 + _half_unit(adjusted1) / adjusted1
            if expected <= 0 or abs(implied / expected - 1) > tolerance + allowance:
                found.append(AdjustmentDisagreement(day1, implied, expected))
    return tuple(found)


def _half_unit(value):
    """Half of the last printed digit; integers are treated as exact."""
    exponent = value.as_tuple().exponent
    return Decimal(0) if exponent >= 0 else Decimal(1).scaleb(exponent) / 2
```

- [ ] **Step 4: Run the new tests and the full suite** (checks there is no import cycle)

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_adjustment_crosscheck -v 2>&1 | tail -3` → `OK` (7 tests).
Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests 2>&1 | tail -3` → `Ran 628 tests`, `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/quant_core/data/adjustments.py tests/test_adjustment_crosscheck.py
git commit -m "Add provider adjustment cross-check for declared splits and dividends"
```

---

### Task 4: Cross-check EODHD `adjusted_close` at import

**Files:** Modify `python/quant_core/data/eodhd.py`; Test `tests/test_eodhd.py`

- [ ] **Step 1: Write the failing tests** — in `tests/test_eodhd.py`, add after the `RAW = (...)` constant:

```python
SPLIT_RAW = (b'[{"date":"2024-01-02","open":100,"high":100,"low":100,"close":100,"adjusted_close":50,"volume":1000},'
             b'{"date":"2024-01-03","open":50.5,"high":50.5,"low":50.5,"close":50.5,"adjusted_close":50.5,"volume":2000}]')
REVIEW = "a" * 64
```

and add these methods to `EodhdTests`:

```python
    def test_adjusted_close_confirms_declared_split(self):
        data = source(responses={"SYNTH.US": SPLIT_RAW}, actions_review_hash=REVIEW,
                      actions=(Split("ID-1", date(2024, 1, 3), new_shares=2, old_shares=1),),
                      metadata=replace(source().metadata, actions_complete=True)).load()
        self.assertFalse(any("adjusted_close" in s for s in data.metadata.limitations))

    def test_declared_complete_actions_missing_a_split_are_refused(self):
        with self.assertRaisesRegex(ValueError, r"disagree with EODHD adjusted_close: SYNTH\.US .*2024-01-03"):
            source(responses={"SYNTH.US": SPLIT_RAW}, actions_review_hash=REVIEW,
                   metadata=replace(source().metadata, actions_complete=True)).load()

    def test_incomplete_actions_record_unexplained_provider_adjustments(self):
        data = source(responses={"SYNTH.US": SPLIT_RAW}).load()
        self.assertTrue(any("not explained by supplied actions" in s for s in data.metadata.limitations))

    def test_missing_adjusted_close_skips_crosscheck_visibly(self):
        raw = SPLIT_RAW.replace(b',"adjusted_close":50,"volume":1000', b',"volume":1000')
        data = source(responses={"SYNTH.US": raw}).load()
        self.assertTrue(any("fewer than two usable sessions for SYNTH.US" in s
                            for s in data.metadata.limitations))

    def test_rows_without_adjusted_close_are_excluded_visibly(self):
        third = b',{"date":"2024-01-04","open":50,"high":50,"low":50,"close":50,"adjusted_close":50,"volume":2000}]'
        raw = (SPLIT_RAW[:-1] + third).replace(b'"adjusted_close":50.5,', b'')
        data = source(responses={"SYNTH.US": raw},
                      sessions=(date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))).load()
        self.assertTrue(any("excluded from the provider adjustment cross-check" in s for s in data.metadata.limitations))
        self.assertTrue(any("not explained by supplied actions" in s for s in data.metadata.limitations))
```

- [ ] **Step 2: Run and confirm failures**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_eodhd -v 2>&1 | tail -3`
Expected: `FAILED` — the refusal, incomplete-actions, missing-field and excluded-rows tests fail (the confirming test already passes).

- [ ] **Step 3: Implement** — in `python/quant_core/data/eodhd.py`:

Change the import line (after the Task 2 review fix it reads `from quant_core.data import Bar, DataMetadata, RAW_PRICES_SPLIT_ADJUSTED_VOLUME, SPLIT_ADJUSTED_VOLUME_LIMITATION, Security, Snapshot`) to

```python
from quant_core.data import (Bar, DataMetadata, Dividend, RAW_PRICES_SPLIT_ADJUSTED_VOLUME,
                             SPLIT_ADJUSTED_VOLUME_LIMITATION, Security, Snapshot, Split)
```

and add directly below it:

```python
from quant_core.data.adjustments import provider_adjustment_disagreements
```

In `EodhdJsonSource.load`, replace the response loop

```python
        for ticker, raw in sorted(self.responses.items()):
            if not isinstance(raw, bytes):
                raise ValueError("EODHD response must contain original bytes")
            for index, row in enumerate(_rows(raw), 1):
                try:
                    bars.append(_normalized_bar(row, self.ticker_security_ids[ticker], retrieved_day))
                except (ValueError, TypeError, KeyError, ArithmeticError):
                    raise ValueError(f"Invalid EODHD daily bar at row {index}; check fields and retrieval date") from None
            hashes.append(("eodhd:response:" + ticker, sha256(raw).hexdigest()))
```

with

```python
        provider_closes = []
        for ticker, raw in sorted(self.responses.items()):
            if not isinstance(raw, bytes):
                raise ValueError("EODHD response must contain original bytes")
            observed = []
            for index, row in enumerate(_rows(raw), 1):
                try:
                    bar = _normalized_bar(row, self.ticker_security_ids[ticker], retrieved_day)
                except (ValueError, TypeError, KeyError, ArithmeticError):
                    raise ValueError(f"Invalid EODHD daily bar at row {index}; check fields and retrieval date") from None
                bars.append(bar)
                observed.append((bar.session, bar.close, row.get("adjusted_close")))
            provider_closes.append((ticker, self.ticker_security_ids[ticker], observed))
            hashes.append(("eodhd:response:" + ticker, sha256(raw).hexdigest()))
```

Then, directly after the existing `if not self.metadata.actions_complete:` limitation block and before `metadata = replace(...)`, insert:

```python
        for ticker, security_id, observed in provider_closes:
            limitations.extend(self._adjustment_crosscheck(ticker, security_id, observed, actions))
```

and add this method to `EodhdJsonSource` after `load`:

```python
    def _adjustment_crosscheck(self, ticker, security_id, observed, actions):
        """Supplied splits/dividends must explain EODHD's back-adjusted closes; returns limitations."""
        usable = sorted((day, close, Decimal(adjusted)) for day, close, adjusted in observed
                        if not isinstance(adjusted, bool) and isinstance(adjusted, (int, Decimal)) and adjusted > 0)
        if len(usable) < 2:
            return [f"EODHD adjusted_close has fewer than two usable sessions for {ticker}; "
                    "provider adjustment cross-check not performed."]
        if len({day for day, _, _ in usable}) != len(usable):
            return []  # Snapshot construction reports the duplicate session.
        notes = []
        if len(usable) < len(observed):
            notes.append(f"EODHD adjusted_close is missing or not positive on {len(observed) - len(usable)} "
                         f"session(s) for {ticker}; they are excluded from the provider adjustment cross-check.")
        declared = [a for a in actions if isinstance(a, (Split, Dividend)) and a.security_id == security_id]
        found = provider_adjustment_disagreements(usable, declared)  # Malformed actions are left to Snapshot validation.
        if found:
            mismatched = sum(f.reason == "factor_mismatch" for f in found)
            first = found[0]
            summary = (f"{ticker} has {mismatched} provider adjustment(s) not explained by supplied actions and "
                       f"{len(found) - mismatched} session(s) too imprecise to verify (first "
                       f"{first.session.isoformat()}: {first.reason}, provider factor {first.implied_factor:.6f}, "
                       f"declared {first.expected_factor:.6f})")
            if self.metadata.actions_complete:
                raise ValueError(f"Declared corporate actions disagree with EODHD adjusted_close: {summary}; "
                                 "review splits and dividends before declaring actions complete")
            notes.append(f"EODHD adjusted_close: {summary}; corporate actions are incomplete.")
        return notes
```

- [ ] **Step 4: Run EODHD tests and the full suite**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_eodhd tests.test_data_commands tests.test_universe_strategy tests.test_volume_basis -v 2>&1 | tail -3` → `OK`.
Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests 2>&1 | tail -3` → `Ran 633 tests`, `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/quant_core/data/eodhd.py tests/test_eodhd.py
git commit -m "Cross-check EODHD adjusted close against supplied actions at import"
```

---

### Task 5: More sensitive split heuristic

**Files:** Modify `python/quant_core/data/quality.py`; Test `tests/test_audit_quality.py`

- [ ] **Step 1: Write the failing tests** — add to `AuditQualityTests` after `test_common_split_sized_changes_are_flagged_without_repair`:

```python
    def test_split_sized_changes_with_ordinary_gaps_are_flagged(self):
        for before, after in (("100", "50.5"), ("150", "101"), ("150", "99"), ("125", "101"), ("100", "75")):
            with self.subTest(before=before, after=after):
                data = fixtures.snapshot(tuple(fixtures.bar(day, before if i == 0 else after)
                                               for i, day in enumerate(fixtures.DAYS)))
                self.assertIn("suspected_missing_split", [i.code for i in check_quality(data).issues])

    def test_ordinary_moves_away_from_split_ratios_are_not_flagged(self):
        for before, after in (("100", "90"), ("100", "110"), ("100", "60")):
            with self.subTest(before=before, after=after):
                data = fixtures.snapshot(tuple(fixtures.bar(day, before if i == 0 else after)
                                               for i, day in enumerate(fixtures.DAYS)))
                self.assertNotIn("suspected_missing_split", [i.code for i in check_quality(data).issues])
```

- [ ] **Step 2: Confirm the first test fails**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_audit_quality -v 2>&1 | tail -3`
Expected: `FAILED (failures=5)` (all five subtests of the gap test; the second test passes).

- [ ] **Step 3: Implement** — in `python/quant_core/data/quality.py` replace

```python
                    common_factors = (Decimal(1) / 2, Decimal(2) / 3, Decimal(4) / 5,
                                      Decimal(5) / 4, Decimal(3) / 2, Decimal(2))
                    suspicious = any(abs(relative / factor - 1) <= Decimal("0.005")
                                     for factor in common_factors)
```

with

```python
                    # Sensitivity over specificity: a missed split corrupts every later mark,
                    # while a flagged genuine move only needs review. 3% covers ordinary gaps.
                    common_factors = (Decimal(1) / 2, Decimal(2) / 3, Decimal(3) / 4, Decimal(4) / 5,
                                      Decimal(5) / 4, Decimal(4) / 3, Decimal(3) / 2, Decimal(2))
                    suspicious = any(abs(relative / factor - 1) <= Decimal("0.03")
                                     for factor in common_factors)
```

- [ ] **Step 4: Run quality tests and the full suite**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_audit_quality tests.test_data -v 2>&1 | tail -3` → `OK`.
Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests 2>&1 | tail -3` → `Ran 635 tests`, `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/quant_core/data/quality.py tests/test_audit_quality.py
git commit -m "Widen missed-split heuristic to ordinary opening gaps"
```

---

### Task 6: Parquet `fsync` on a writable handle

**Files:** Modify `python/quant_core/data/parquet.py:69`; Test `tests/test_parquet.py`

- [ ] **Step 1: Write the failing test** — add `import os` to the imports of `tests/test_parquet.py` (alphabetical, after `import json`), and add to class `ParquetTests`:

```python
    @unittest.skipIf(os.name == "nt", "access-mode probe uses POSIX fcntl")
    def test_durability_sync_uses_writable_descriptors(self):
        import fcntl
        from quant_core.data import parquet
        real_fsync = os.fsync

        def checked(descriptor):
            if fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY:
                raise AssertionError("fsync on a read-only descriptor fails on Windows")
            return real_fsync(descriptor)

        with TemporaryDirectory() as folder, patch.object(parquet.os, "fsync", side_effect=checked):
            save_parquet_snapshot(snapshot(), Path(folder) / "bundle")
```

- [ ] **Step 2: Confirm failure**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_parquet.ParquetTests.test_durability_sync_uses_writable_descriptors -v 2>&1 | tail -3`
Expected: FAIL/ERROR mentioning `fsync on a read-only descriptor` (it may surface wrapped as the module's publication error).

- [ ] **Step 3: Implement** — in `python/quant_core/data/parquet.py` change

```python
        with bar_path.open("rb") as stream:
            os.fsync(stream.fileno())
```

to

```python
        with bar_path.open("r+b") as stream:  # Windows requires write access to flush to disk.
            os.fsync(stream.fileno())
```

- [ ] **Step 4: Run Parquet tests and the full suite**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_parquet -v 2>&1 | tail -3` → `OK`.
Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests 2>&1 | tail -3` → `Ran 636 tests`, `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/quant_core/data/parquet.py tests/test_parquet.py
git commit -m "Sync Parquet bars through a writable handle"
```

---

### Task 7: Documentation and version 0.5.2

**Files:** `docs/DATA_LAYER.md`, `docs/DATA_INTEGRATION.md`, `docs/BACKTESTER.md`, `docs/UNIVERSES.md`, `pyproject.toml`, `python/quant_core/__init__.py`

- [ ] **Step 1: `docs/DATA_LAYER.md`** — replace the paragraph beginning `The jump threshold is inclusive. The checker also flags observations near common` through `The default warning policy remains explicit and compatible with older diagnostics.` with:

```markdown
The jump threshold is inclusive. The checker also flags opening prices within 3%
of common split ratios (1:2, 2:3, 3:4, 4:5 and their inverses) after adjusting
for known actions, so missed splits with ordinary opening gaps are caught. These
are review prompts, not inferred splits, and genuine large moves near those
ratios are flagged too. `check_quality(..., strict_discontinuities=True)` or the
data CLI's `--strict-discontinuities` makes every flag an error; use it for
short, reviewed histories. For long histories prefer a provider adjustment
cross-check (see [data integration](DATA_INTEGRATION.md)) and review warnings.

`DataMetadata.adjustment_policy` states the volume basis; prices are always raw.
`raw` means raw share volume. `raw_prices_split_adjusted_volume` (set by the
EODHD importer) means volume already reflects later splits: strategies and
risk-enabled backtests refuse such snapshots, because their liquidity filters and
participation caps would double-count splits and see splits after the signal
date. Explicit order schedules without risk limits still run.
```

- [ ] **Step 2: `docs/DATA_INTEGRATION.md`** — replace the sentence `Adjusted close remains in original response bytes and is not an execution price or an automatically built signal series.` (it spans two lines) with:

```markdown
Adjusted close remains in original response bytes and is never an execution
price or signal series. The importer uses it only to cross-check supplied
splits and cash dividends: between consecutive sessions the provider's implied
adjustment must match the declared actions within 0.1% plus half a unit of the
finest decimal it prints; sessions whose rounding is too coarse to verify are
reported as such, and sessions without a usable adjusted close are excluded
visibly. For adjusted values below about 0.1 a 4-decimal series is rounded more
coarsely than 0.1%, so a small missing dividend there can pass; splits remain
checked. With actions declared complete, a disagreement stops the import and
names the ticker and date; with incomplete actions it is recorded as a
limitation. Missing `adjusted_close` skips the check visibly. Imported snapshots
carry `adjustment_policy = raw_prices_split_adjusted_volume`; strategies and
risk-enabled runs refuse them until raw volume is reconstructed from reviewed
complete splits (not yet implemented). EODHD snapshots imported before 0.5.2
are labelled `raw` but carry the importer's split-adjusted-volume limitation;
they are refused the same way. Re-import them from the raw response cache. CSV
imports cannot yet declare a split-adjusted volume basis; that option is
planned before customer CSV import ships. The guard runs in strategy and campaign
preflight and risk-enabled runs; a future scanner or any direct caller of
`RuleStrategy.evaluate()` must call `require_raw_volume` itself, and custom
order sources cannot yet see the volume basis through `SessionContext`.
```

- [ ] **Step 3: `docs/BACKTESTER.md`** — after the sentence that ends `requested strict discontinuity check.` add:

```markdown
Rule strategies and risk-enabled runs also require raw share volume
(`adjustment_policy = raw`); snapshots with split-adjusted volume are refused
with an explanatory error rather than silently mixing share bases.
```

- [ ] **Step 4: `docs/UNIVERSES.md`** — directly after the closing triple backtick of the `quant_core.backtest.cli run ... verify` example block, add:

```markdown
`--strict-discontinuities` suits short, reviewed snapshots: it turns every
suspicious price flag, including genuine large moves, into an error. See the
[data-layer quality notes](DATA_LAYER.md#quality-and-persistence).
```

- [ ] **Step 4b: Comment fix** — in `python/quant_core/data/adjustments.py` replace the comment on the
`PRECISION_LIMIT` line with `# Coarser rounding cannot verify even small stock dividends; reported, not trusted.`
and add `python/quant_core/data/adjustments.py` to this task's `git add`.

- [ ] **Step 5: Version** — set `version = "0.5.2"` in `pyproject.toml` and `__version__ = "0.5.2"` in `python/quant_core/__init__.py`.

- [ ] **Step 6: Final checks**

Run: `PYTHONPATH=python PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests 2>&1 | tail -3` → `Ran 636 tests`, `OK`.
Run: `grep -n "0.5.1" pyproject.toml python/quant_core/__init__.py` → no output.

- [ ] **Step 7: Commit**

```bash
git add docs/DATA_LAYER.md docs/DATA_INTEGRATION.md docs/BACKTESTER.md docs/UNIVERSES.md pyproject.toml python/quant_core/__init__.py python/quant_core/data/adjustments.py
git commit -m "Document volume basis and adjustment cross-check; version 0.5.2"
```

---

## Self-review

- **Spec coverage:** spec Section 5 item 6 — EODHD volume (Tasks 1–2, block chosen; reconstruction deferred and documented), split cross-check against provider adjusted close (Tasks 3–4), heuristic (Task 5); review finding on Parquet `fsync` (Task 6); docs (Task 7). The forward-journal command fix was completed in Plan A.
- **Placeholders:** none; every code step shows full code.
- **Consistency:** `RAW_PRICES_SPLIT_ADJUSTED_VOLUME`, `require_raw_volume(metadata, purpose)` with message `"{purpose}: raw share volume required"`, `provider_adjustment_disagreements(observations, actions, tolerance)` returning `AdjustmentDisagreement(session, implied_factor, expected_factor)` are used identically in Tasks 1–4. Test counts: 606 → 607 (T1) → 611 (T2) → 614 (T2 review fixes) → 621 (T3) → 628 (T3 review fixes) → 633 (T4) → 635 (T5) → 636 (T6).
- **Hash stability:** no new `DataMetadata` field; existing `raw` snapshots keep their dataset hashes (asserted in Task 1).
