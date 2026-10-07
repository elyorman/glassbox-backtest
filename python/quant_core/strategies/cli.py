"""Export the proposed bounded recipe registry; never selects winners."""

import argparse
from pathlib import Path
import sys

from quant_core.strategies import save_recipe_registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", nargs="+", required=True, help="Explicit stable security IDs")
    parser.add_argument("--benchmark", required=True, help="Broad-market benchmark security ID")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        save_recipe_registry(args.universe, args.benchmark, args.output)
        print(f"Saved 10 proposed candidates and 4 benchmark configurations to {args.output}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Strategy registry error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
