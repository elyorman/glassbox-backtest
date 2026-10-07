# Dated Historical Universes

`quant_core.universes` supplies local, provider-neutral historical membership
for PR-01 and PR-02. It separates the base universe from tradability, strategy
conditions, ranking and portfolio risk. Membership uses stable `security_id`
values from the market-data security registry, not ticker text. A symbol change
does not change membership identity.

## Coverage and availability contract

`DatedUniverse` declares complete membership between `coverage_start` and
`coverage_end`, both inclusive. Missing history outside that range raises
`UniverseCoverageError`; it never selects current constituents or a static
fallback. Within declared complete coverage, no intervals active on a date means
a known empty universe. The importer cannot prove that the source omitted no
members; the coverage declaration is a substantive source assertion. For gaps,
use separate artifacts with narrower complete ranges.

Each `MembershipInterval` has:

| Field | Meaning |
| --- | --- |
| `security_id` | Stable security identity |
| `entered_on` | Inclusive effective entry date |
| `entry_available_on` | First date the entry fact was available to the strategy |
| `left_on` | Exclusive effective removal date, or null for an open interval |
| `exit_available_on` | Availability date for the removal fact; required when `left_on` exists |

Same-security intervals may be adjacent or separated by gaps for re-entry;
overlap and duplicate/open overlapping intervals are rejected. Dates must be
`datetime.date`; retrieval timestamps must be timezone-aware.

`coverage_available_on` records when the initial coverage baseline was available.
`members_on(day)` fails with `UniverseAvailabilityError` if that baseline or an
already-effective entry/removal was unavailable on `day`. This blocks a late
historical correction from leaking into an earlier strategy decision. It does
not silently omit an unknown member, keep a member after an unknown removal, or
substitute a different universe. Events that become effective in the future do
not affect current membership. A removal announcement need not be known when
the member originally entered: membership before the removal remains usable.

Availability is distinct from effective dates and local `retrieved_at`. A source
retrieved today may carry independently evidenced historical announcement dates;
retrieval today alone does not establish those dates. If historical availability
is unknown, use the first evidenced availability date and retain the limitation.
Daily availability means the fact was available by the strategy's signal cutoff
on that date. A date-only announcement without a known cutoff must not be assumed
usable earlier that day.

CSV imports and later corrections are **not automatically point-in-time
qualified or survivorship-complete**. Preserve source name, retrieval timestamp,
coverage assertions and limitations. The importer hashes the original CSV bytes;
this proves input identity, not source accuracy or economic qualification. No
vendor entitlement, index history or qualified real-data campaign is supplied
by this module.

## Local CSV workflow

Supply every member's interval, including removed members and repeated entries.
An empty removal requires both removal fields to be empty. The exact CSV columns
are:

```csv
security_id,entered_on,entry_available_on,left_on,exit_available_on
A,2024-01-02,2024-01-01,2024-01-05,2024-01-04
B,2024-01-04,2024-01-03,,
A,2024-01-08,2024-01-07,,
```

From the repository root, save this as `local/membership.csv`, then import:

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.universes.cli import-csv \
  --input local/membership.csv --output local/synthetic-membership.json \
  --universe-id synthetic-index \
  --coverage-start 2024-01-02 --coverage-end 2024-01-10 \
  --coverage-available-on 2024-01-01 \
  --source hand-calculated-synthetic \
  --retrieved-at 2024-02-01T00:00:00+00:00 \
  --limitation 'Synthetic engineering fixture; no empirical qualification'

PYTHONPATH=python .venv/bin/python -m quant_core.universes.cli members \
  --input local/synthetic-membership.json --date 2024-01-05
```

The query prints `members: ["B"]` with provenance and the universe hash. The
hand-calculated history is:

| Date | Members | Change |
| --- | --- | --- |
| January 2 | A | A enters |
| January 4 | A, B | B enters |
| January 5 | B | A has left |
| January 8 | A, B | A re-enters |

Malformed files, uncovered dates and unavailable facts return CLI status 2.
JSON artifacts include a versioned canonical payload and SHA-256 content hash;
load checks integrity and normalized form. Publication is atomic and refuses an
existing destination. Corrections require a new artifact path. Raw CSV input is
never modified.

## Python consumer contract

```python
from datetime import date
from pathlib import Path
from quant_core.universes import DatedUniverse

membership = DatedUniverse.load(Path("local/synthetic-membership.json"))
eligible_members = membership.members_on(date(2024, 1, 5))  # ("B",)
all_registry_ids = membership.security_ids                 # ("A", "B")
universe_hash = membership.content_hash()
```

Consumers validate `security_ids` against their stable security registry, use
`members_on(signal_date)` before tradability/ranking, and retain membership
payload/hash in reproducibility metadata. A removed security can remain in the
registry and holdings so the portfolio can sell it. Membership removal does not
mean delisting, cash settlement or disappearance of market prices. A static
custom universe remains a separate, explicitly static choice.

The standalone importer/query CLI and module do not fetch provider data or run
economic research. Their regression suite is:

```bash
PYTHONPATH=python .venv/bin/python -m unittest discover -s tests -p test_universes.py -v
```

## Strategy and portfolio integration

`build_strategy(snapshot, configuration, membership=membership)` checks that
all membership IDs exist in the configured universe and market-data registry.
It checks membership at scheduled signal dates before history/liquidity/ranking.
Unknown coverage or unavailable effective changes block the run. The complete
membership artifact is bound into the version-2 strategy specification; changing
future membership changes provenance while leaving earlier decisions unchanged.

Removed holdings are sold at the next scheduled rebalance and next executable
open. Removal itself does not trigger an immediate trade or fabricate a delisting
outcome. Equal-weight/trend allocation uses the current member count; an empty
membership can liquidate previous holdings. Static custom universes remain
available. Buy-and-hold/cash references keep their separately declared universes
and reject a dated membership argument.

With matching snapshot, registry and strategy inputs:

```bash
PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli run \
  local/reviewed-snapshot-parquet --strategy local/strategy.json \
  --membership local/reviewed-membership.json \
  --capital 100000 --slippage-bps 10 --strict-discontinuities \
  --output local/dated-backtest-v1
PYTHONPATH=python .venv/bin/python -m quant_core.backtest.cli verify \
  local/dated-backtest-v1
```

These commands require reviewed complete actions by default. The synthetic
provider-to-Parquet-to-membership integration test is an explicitly incomplete-
action diagnostic; it does not weaken the normal execution gate.
