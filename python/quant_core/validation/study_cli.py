"""Check or run a registered study and write its evidence pack (docs/VALIDATION.md, "Registered studies")."""

import argparse
from pathlib import Path
import sys

from quant_core.analytics.evidence import run_series_from_bundle
from quant_core.data import number
from quant_core.data.dataset import load_dataset
from quant_core.provenance import canonical_json, content_hash
from quant_core.reporting import verify_run
from quant_core.reporting.evidence import build_pack, write_pack
from quant_core.validation.registration import PRIMARY_COST_BPS, load_registration
from quant_core.validation.study import check_output, planned_runs, save_study, simulate_study


def _earlier(registration):
    """The primary run of each earlier built-in and its result hash, read before anything runs."""
    series = {}
    for study, runs in registration.earlier_studies:
        try:
            payload = verify_run(Path(runs))
            series[study] = (run_series_from_bundle(Path(runs)), content_hash(payload))
        except (ValueError, OSError) as exc:
            raise ValueError(f"Earlier study {study}: {runs} is not a saved run ({exc})") from None
        config, source = payload["manifest"]["config"], payload["manifest"]["source"]
        if (source.get("purpose") != "built_in_plan" or source["plan"]["decision_offset"] != 0
                or number(config["execution"]["slippage_bps"]) != PRIMARY_COST_BPS
                or config["cash_rates"] is None or config["execution_delay_sessions"] != 1):
            raise ValueError(f"Earlier study {study}: {runs} is not a parent's primary run (a built-in plan at 10 bps "
                             "with T-bill cash and next-open fills)")
    return series


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Check the registration, dataset, code and earlier studies, and "
                                              "rehearse every run in memory; save and show nothing")
    run = commands.add_parser("run", help="Run the study once and write pack.json and PACK.md")
    for command in (check, run):
        command.add_argument("registration", type=Path)
        command.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            check_output(args.output)
        registration, dataset = load_registration(args.registration), load_dataset(args.dataset)
        earlier = _earlier(registration)
        result = {"study": registration.study, "registration_hash": registration.hash,
                  "planned_runs": len(planned_runs(registration))}
        runs = simulate_study(registration, dataset)  # Every run and the pack in memory before anything is saved.
        pack = build_pack(registration, dataset, runs, earlier)
        if args.command == "check":
            result["status"] = "ready"  # Show nothing of the results before the registration is tagged.
        else:
            save_study(runs, args.output)
            result.update(status="complete", pack=str(args.output / "PACK.md"),
                          pack_content_hash=write_pack(pack, args.output))
        print(canonical_json(result))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Study error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
