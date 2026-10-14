"""Check or run a registered study and write its evidence pack (docs/VALIDATION.md, "Registered studies")."""

import argparse
import json
from pathlib import Path
import sys

from quant_core.analytics.evidence import run_series_from_bundle
from quant_core.data.dataset import load_dataset
from quant_core.provenance import canonical_json, content_hash
from quant_core.reporting import verify_run
from quant_core.reporting.evidence import build_pack, pack_files, write_pack
from quant_core.validation.registration import load_registration
from quant_core.validation.study import check_output, planned_runs, save_study, simulate_study


def _earlier(registration):
    """Each earlier built-in's parent at its primary cost, with its result hash: the run its own pack.json names,
    read from that study's output directory before anything runs."""
    series = {}
    for study, output in registration.earlier_studies:
        try:
            pack = json.loads((Path(output) / "pack.json").read_text(encoding="utf-8"))
            if pack["registration"]["study"] != study:
                raise ValueError(f"its pack.json is for {pack['registration']['study']}")
            key = f"plan-{pack['registration']['primary_cost_bps']}bps"
            run_hash = content_hash(verify_run(Path(output) / "runs" / key))
            if run_hash != pack["reproduction"]["runs"][key]:
                raise ValueError(f"its {key} run is not the one its pack.json names")
            series[study] = (run_series_from_bundle(Path(output) / "runs" / key), run_hash)
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Earlier study {study}: {output} is not a completed study ({exc})") from None
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
        files = pack_files(build_pack(registration, dataset, runs, earlier))
        if args.command == "check":
            result["status"] = "ready"  # Show nothing of the results before the registration is tagged.
        else:
            save_study(runs, args.output)
            result.update(status="complete", pack=str(args.output / "PACK.md"),
                          pack_sha256=write_pack(files, args.output))
        print(canonical_json(result))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Study error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
