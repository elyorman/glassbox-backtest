"""Local campaign registration, execution, nomination and verification commands."""

import argparse
from datetime import date
from pathlib import Path
import sys

from quant_core.data.storage import load_snapshot
from quant_core.provenance import canonical_json
from quant_core.strategies import benchmark_recipes, initial_recipes
from quant_core.validation.campaign import (
    crosscheck, nominate, open_campaign, register_campaign, run_final, run_phase, verify_campaign,
)
from quant_core.validation.contracts import (
    CAPABILITIES, CampaignSpec, Capability, Qualification, load_document, parse_qualification, parse_spec,
)
from quant_core.validation.registry import publish, read_document
from quant_core.validation.temporal import Period


def _qualification(path):
    return load_document(path, "qualification", parse_qualification)


def _boundary(snapshot, start, end):
    days = tuple(d for d in snapshot.sessions if start <= d <= end)
    if not days:
        raise ValueError("Template snapshot lacks the proposed research periods; supply appropriate history")
    return days[0], days[-1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="Export proposed dates/recipes and UNRESOLVED qualification; no performance run")
    template.add_argument("snapshot", type=Path)
    template.add_argument("--universe", nargs="+", required=True)
    template.add_argument("--benchmark", required=True)
    template.add_argument("--reviewed-on", type=date.fromisoformat, required=True)
    template.add_argument("--output", type=Path, required=True)
    register = commands.add_parser("register")
    register.add_argument("specification", type=Path)
    register.add_argument("snapshot", type=Path)
    register.add_argument("--qualification", type=Path, required=True)
    register.add_argument("--output", type=Path, required=True)
    for name in ("development", "selection"):
        command = commands.add_parser(name)
        command.add_argument("campaign", type=Path)
        command.add_argument("snapshot", type=Path)
    command = commands.add_parser("crosscheck")
    command.add_argument("campaign", type=Path)
    command.add_argument("independent_snapshot", type=Path)
    command.add_argument("--qualification", type=Path, required=True)
    command = commands.add_parser("final")
    command.add_argument("campaign", type=Path)
    command.add_argument("original_snapshot", type=Path)
    command.add_argument("independent_snapshot", type=Path)
    for name in ("nominate", "verify"):
        command = commands.add_parser(name)
        command.add_argument("campaign", type=Path)
    command = commands.add_parser("record-holdout-exposure", help="Record accidental/external performance exposure; prevents fresh final-evidence claims")
    command.add_argument("campaign", type=Path)
    command.add_argument("--reason", required=True)
    command = commands.add_parser("record-experiment", help="Retain extra/manual search; prevents automatic nomination under this budget")
    command.add_argument("campaign", type=Path)
    command.add_argument("experiment", type=Path, help="JSON with hypothesis, configuration, dataset_hash, seed, status and reason")
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            data = load_snapshot(args.snapshot)
            folds = tuple(Period(str(year), *_boundary(data, date(year, 1, 1), date(year, 12, 31))) for year in (2019, 2020, 2021))
            spec = CampaignSpec("sector_etf_rules_v1_proposed", "Compare transparent rule families after costs without optimizing the simulator",
                                data.dataset_hash, initial_recipes(args.universe), benchmark_recipes(args.universe, args.benchmark),
                                folds, Period("selection", *_boundary(data, date(2022, 1, 1), date(2023, 12, 31))),
                                Period("locked_final", *_boundary(data, date(2024, 1, 1), date(2026, 9, 30))),
                                prior_holdout_use="unknown", prior_holdout_disclosure="Review prior strategy-performance use before declaring an unexposed final period")
            qualification = Qualification(data.dataset_hash, "exploratory_fixed_sample", "UNREVIEWED", args.reviewed_on,
                tuple(Capability(name, "unresolved", "Provide reviewed evidence before changing status") for name in CAPABILITIES),
                ("Fixed retrospectively chosen surviving sample; no historical constituent claim",
                 "Daily-bar open is an execution approximation; cash yield and reference rate zero"))
            args.output.mkdir(parents=True, exist_ok=False)
            publish(args.output / "specification.json", {"schema_version": 1, "campaign": spec})
            publish(args.output / "qualification.json", {"schema_version": 1, "qualification": qualification})
            result = {"status": "proposed_only", "directory": str(args.output), "campaign_hash": spec.campaign_hash}
        elif args.command == "register":
            result = {"campaign_hash": register_campaign(load_document(args.specification, "campaign", parse_spec),
                      load_snapshot(args.snapshot), _qualification(args.qualification), args.output)}
        elif args.command in ("development", "selection"):
            report = run_phase(args.campaign, load_snapshot(args.snapshot), args.command)
            result = {"phase": args.command, "status": report["status"], "trial_count": report["trial_count"]}
        elif args.command == "nominate":
            result = nominate(args.campaign)
        elif args.command == "crosscheck":
            report = crosscheck(args.campaign, load_snapshot(args.independent_snapshot), _qualification(args.qualification))
            result = {"phase": "crosscheck", "status": report["status"]}
        elif args.command == "final":
            report = run_final(args.campaign, load_snapshot(args.original_snapshot), load_snapshot(args.independent_snapshot))
            result = {"phase": "final", "status": report["status"]}
        elif args.command == "verify":
            result = verify_campaign(args.campaign)
        elif args.command == "record-holdout-exposure":
            from quant_core.data import identity
            identity(args.reason)
            registry, spec, _ = open_campaign(args.campaign, execution=False)
            with registry.exclusive():
                registry.append("holdout_exposed", {"period": spec.holdout, "reason": args.reason})
            result = {"status": "recorded_holdout_exposure", "fresh_final_evidence": "blocked"}
        else:
            registry, _, _ = open_campaign(args.campaign)
            experiment = read_document(args.experiment)
            if not isinstance(experiment, dict) or set(experiment) != {"hypothesis", "configuration", "dataset_hash", "seed", "status", "reason"}:
                raise ValueError("External experiment must supply all six declared audit fields")
            from quant_core.data import identity
            from quant_core.validation.contracts import digest
            for key in ("hypothesis", "status", "reason"):
                identity(experiment[key])
            digest(experiment["dataset_hash"])
            if type(experiment["seed"]) is not int or experiment["seed"] < 0 or not isinstance(experiment["configuration"], dict):
                raise ValueError("External experiment requires integer seed and configuration object")
            with registry.exclusive():
                if registry.has("nomination_decided") or registry.has("final_consumed"):
                    raise ValueError("Campaign is frozen/consumed; create a new research version linked to this history")
                registry.append("external_experiment", experiment)
            result = {"status": "recorded_additional_search", "automatic_nomination": "blocked_under_original_budget"}
        print(canonical_json(result))
        return 0 if result.get("status") not in ("incomplete", "failed") else 1
    except (ValueError, OSError, ArithmeticError) as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
