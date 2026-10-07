"""Developer CLI for local import and historical membership queries."""

import argparse
from datetime import date, datetime
from pathlib import Path
import sys

from quant_core.provenance import canonical_json
from quant_core.universes import DatedUniverse
from quant_core.universes.csv_source import import_membership_csv


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import or query dated historical universe membership")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import-csv", help="Save an immutable source-bound membership artifact")
    importer.add_argument("--input", type=Path, required=True)
    importer.add_argument("--output", type=Path, required=True)
    importer.add_argument("--universe-id", required=True)
    for name in ("coverage-start", "coverage-end", "coverage-available-on"):
        importer.add_argument(f"--{name}", type=date.fromisoformat, required=True)
    importer.add_argument("--source", required=True)
    importer.add_argument("--retrieved-at", type=datetime.fromisoformat, required=True)
    importer.add_argument("--limitation", action="append", default=[])
    members = commands.add_parser("members", help="Query effective membership without future leakage")
    members.add_argument("--input", type=Path, required=True)
    members.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "import-csv":
            record = import_membership_csv(args.input, universe_id=args.universe_id,
                coverage_start=args.coverage_start, coverage_end=args.coverage_end,
                coverage_available_on=args.coverage_available_on, source=args.source,
                retrieved_at=args.retrieved_at, limitations=tuple(args.limitation))
            record.save(args.output)
            print(canonical_json({"output": str(args.output), "universe_hash": record.content_hash()}))
        else:
            record = DatedUniverse.load(args.input)
            print(canonical_json({"universe_id": record.universe_id, "date": args.date,
                "members": record.members_on(args.date), "universe_hash": record.content_hash(),
                "source": record.source, "retrieved_at": record.retrieved_at,
                "limitations": record.limitations}))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Dated universe error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
