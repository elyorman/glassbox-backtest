"""Save/run a wholly synthetic validation campaign. Never a performance experiment."""

import argparse
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from quant_core.data import Bar, DataMetadata, Security, Snapshot
from quant_core.data.storage import save_snapshot
from quant_core.provenance import canonical_json
from quant_core.strategies import StrategyConfig, benchmark_recipes
from quant_core.validation.campaign import nominate, register_campaign, run_phase, verify_campaign
from quant_core.validation.contracts import CAPABILITIES, CampaignSpec, Capability, Criteria, Qualification
from quant_core.validation.registry import publish
from quant_core.validation.temporal import Period


def build_fixture():
    days, day = [], date(2023, 1, 2)
    while len(days) < 90:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    bars = []
    for asset in ("A", "B", "SPY"):
        previous = Decimal(100)
        for i, day in enumerate(days):
            close = (Decimal(100) + Decimal(i) / 2 + (i % 7 - 3) if asset == "A"
                     else Decimal(100) + Decimal(i % 5) / 10 if asset == "B"
                     else Decimal(100) + Decimal(i) / 4)
            bars.append(Bar(asset, day, previous, max(previous, close) + 1, min(previous, close) - 1, close, 100000))
            previous = close
    metadata = DataMetadata("synthetic_validation_fixture", datetime(2026, 10, 3, tzinfo=timezone.utc),
                            "fixed_engineering_sample", True, "synthetic_weekdays_not_exchange_calendar",
                            limitations=("Synthetic engineering fixture; no empirical performance evidence",))
    data = Snapshot(tuple(days), tuple(bars), metadata,
                    tuple(Security(a, a, "SYNTHETIC") for a in ("A", "B", "SPY")))
    recipes = (StrategyConfig("trend3", "trend", ("A", "B"), mean_window=3, volume_lookback=1,
                              max_volume_participation="1", purpose="engineering_fixture"),
               StrategyConfig("momentum3", "momentum", ("A", "B"), momentum_lookback=3, momentum_skip=1,
                              top_k=1, volume_lookback=1, max_volume_participation="1", purpose="engineering_fixture"))
    benchmarks = tuple(replace(c, volume_lookback=1, max_volume_participation=Decimal(1))
                       for c in benchmark_recipes(("A", "B"), "SPY"))
    specification = CampaignSpec("synthetic_validation_v1", "Verify chronology/reporting; no alpha hypothesis",
        data.dataset_hash, recipes, benchmarks,
        (Period("fold1", days[5], days[19]), Period("fold2", days[20], days[34])),
        Period("selection", days[35], days[59]), Period("holdout", days[60], days[89]),
        criteria=Criteria(minimum_sessions=10, removed_winner_sessions=2), bootstrap_blocks=(2, 5),
        bootstrap_repetitions=100, purpose="engineering_fixture", initial_cash="10000")
    qualification = Qualification(data.dataset_hash, "engineering_fixture", "synthetic_fixture_author", date(2026, 10, 3),
        tuple(Capability(name, "passed", "Constructed fixture only; not provider/rights qualification") for name in CAPABILITIES),
        ("Synthetic surviving sample; daily execution approximation; no real-data rights assertion",))
    return data, specification, qualification


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    data, spec, qualification = build_fixture()
    save_snapshot(data, args.output / "synthetic.snapshot.json")
    publish(args.output / "specification.json", {"schema_version": 1, "campaign": spec})
    publish(args.output / "qualification.json", {"schema_version": 1, "qualification": qualification})
    campaign = args.output / "campaign"
    register_campaign(spec, data, qualification, campaign)
    development, selection = run_phase(campaign, data, "development"), run_phase(campaign, data, "selection")
    decision = nominate(campaign)
    print(canonical_json({"development_status": development["status"], "selection_status": selection["status"],
                          "decision": decision["status"], "verification": verify_campaign(campaign)}))


if __name__ == "__main__":
    main()
