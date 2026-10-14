"""Check or run a registered study and write its evidence pack (docs/VALIDATION.md, "Registered studies")."""

import argparse
from pathlib import Path
import sys

from quant_core.analytics.evidence import run_series_from_bundle
from quant_core.data.dataset import load_dataset
from quant_core.provenance import canonical_json
from quant_core.reporting.evidence import build_pack, write_pack
from quant_core.validation.registration import load_registration
from quant_core.validation.study import check_study, planned_runs, run_study


def _earlier(registration):
    """The primary run of each earlier built-in, read before anything runs."""
    series = {}
    for study, runs in registration.earlier_studies:
        try:
            series[study] = run_series_from_bundle(Path(runs))
        except (ValueError, OSError) as exc:
            raise ValueError(f"Earlier study {study}: {runs} is not a saved run ({exc})") from None
    return series


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Check the registration, dataset, code and earlier studies; run nothing")
    run = commands.add_parser("run", help="Run the study once and write pack.json and PACK.md")
    for command in (check, run):
        command.add_argument("registration", type=Path)
        command.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        registration, dataset = load_registration(args.registration), load_dataset(args.dataset)
        check_study(registration, dataset)
        earlier = _earlier(registration)
        result = {"study": registration.study, "registration_hash": registration.hash,
                  "planned_runs": len(planned_runs(registration))}
        if args.command == "check":
            result["status"] = "ready"
        else:
            runs = run_study(registration, dataset, args.output)
            result.update(status="complete", pack=str(args.output / "PACK.md"),
                          pack_hash=write_pack(build_pack(registration, dataset, runs, earlier), args.output))
        print(canonical_json(result))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Study error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
