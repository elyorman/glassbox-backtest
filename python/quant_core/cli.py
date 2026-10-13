"""Developer data-import entry point; the desktop workflow will wrap this API."""

import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import sys

from quant_core.data import DataMetadata
from quant_core.data.csv_source import CsvSource, load_calendar, load_securities, load_actions
from quant_core.data.quality import check_quality
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.provenance import canonical_json, primitive


def load_local_snapshot(path):
    if path.is_dir():
        from quant_core.data.parquet import load_parquet_snapshot
        return load_parquet_snapshot(path)
    return load_snapshot(path)


def _now():
    return datetime.now(timezone.utc)


def plan_tickers():
    """Every ticker the built-in plans trade; SPY and IEF also serve the 60/40 reference."""
    from quant_core.strategies.plans import builtin_plans
    return tuple(sorted({asset for plan in builtin_plans() for asset in plan.universe}))


def _tiingo_key(env_file):
    """TIINGO_API_KEY from the environment, else from the env file; never printed."""
    key = os.environ.get("TIINGO_API_KEY")
    if not key and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name.removeprefix("export ").strip() == "TIINGO_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        raise ValueError(f"Set TIINGO_API_KEY in the environment or in {env_file}")
    return key


def _download(args):
    from quant_core.data.dataset import DownloadIncomplete, download_dataset, save_dataset
    from quant_core.data.remote import RequestBudget
    from quant_core.data.tiingo import TiingoClient, last_final_day
    from quant_core.data.treasury import TreasuryClient
    if args.output.exists():
        raise ValueError(f"Dataset directory {args.output} already exists; datasets are never overwritten")
    tiingo = TiingoClient(_tiingo_key(args.env_file), args.tiingo_cache, budget=RequestBudget(args.max_requests))
    end = args.end or last_final_day(_now())
    try:
        dataset = download_dataset(args.tickers or plan_tickers(), end, tiingo, TreasuryClient(args.treasury_cache))
    except DownloadIncomplete as exc:
        print(f"Download incomplete: {exc}", file=sys.stderr)
        return 3
    save_dataset(args.output, dataset)
    manifest = dataset.manifest
    print(canonical_json({key: manifest[key] for key in
                          ("dataset_id", "end", "snapshot", "securities", "rates", "quality_warnings")}))
    return 0


def _pairs(values):
    result = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key or not item or key in result:
            raise ValueError("Expected unique TICKER=value mappings")
        result[key] = item
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import or inspect a local raw-price dataset")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import-csv")
    for name in ("bars", "calendar", "securities", "output"):
        importer.add_argument(f"--{name}", type=Path, required=True)
    importer.add_argument("--actions", type=Path)
    importer.add_argument("--source", required=True)
    importer.add_argument("--retrieved-at", required=True, help="ISO timestamp with timezone")
    importer.add_argument("--universe-policy", required=True)
    importer.add_argument("--calendar-name", required=True)
    importer.add_argument("--actions-complete", action="store_true", help="Explicit assertion, not automatic qualification")
    importer.add_argument("--limitation", action="append", default=[])
    importer.add_argument("--parquet", action="store_true", help="Write a Parquet bundle instead of JSON")
    importer.add_argument("--strict-discontinuities", action="store_true")
    eodhd = commands.add_parser("import-eodhd", help="Import saved original EODHD daily JSON responses")
    eodhd.add_argument("--response", action="append", required=True, help="TICKER=original.json; repeat per ticker")
    eodhd.add_argument("--security-map", action="append", required=True, help="TICKER=stable_security_id")
    for name in ("calendar", "securities", "output"):
        eodhd.add_argument(f"--{name}", type=Path, required=True)
    eodhd.add_argument("--actions", type=Path)
    eodhd.add_argument("--action-review", type=Path, help="Supplied review evidence for corporate actions")
    eodhd.add_argument("--actions-complete", action="store_true")
    eodhd.add_argument("--retrieved-at", required=True)
    eodhd.add_argument("--universe-policy", required=True)
    eodhd.add_argument("--calendar-name", required=True)
    eodhd.add_argument("--limitation", action="append", default=[])
    eodhd.add_argument("--raw-cache", type=Path)
    eodhd.add_argument("--parquet", action="store_true")
    eodhd.add_argument("--strict-discontinuities", action="store_true")
    exporter = commands.add_parser("export-parquet")
    exporter.add_argument("snapshot", type=Path)
    exporter.add_argument("--output", type=Path, required=True)
    parquet_importer = commands.add_parser("import-parquet", help="Verify a bundle and export a JSON snapshot")
    parquet_importer.add_argument("snapshot", type=Path)
    parquet_importer.add_argument("--output", type=Path, required=True)
    inspector = commands.add_parser("inspect")
    inspector.add_argument("snapshot", type=Path)
    inspector.add_argument("--strict-discontinuities", action="store_true")
    downloader = commands.add_parser("download-tiingo",
                                     help="Download, check and freeze the built-in plans' ETFs and T-bill rates")
    downloader.add_argument("--output", type=Path, required=True)
    downloader.add_argument("--tickers", nargs="+", help="Default: every ticker the built-in plans trade")
    downloader.add_argument("--end", type=date.fromisoformat, help="Default: the latest final day")
    downloader.add_argument("--tiingo-cache", type=Path, default=Path("local/cache/tiingo"))
    downloader.add_argument("--treasury-cache", type=Path, default=Path("local/cache/treasury"))
    downloader.add_argument("--max-requests", type=int, default=45, help="Tiingo requests sent per run")
    downloader.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)
    try:
        if args.command == "download-tiingo":
            return _download(args)
        if args.command == "import-csv":
            metadata = DataMetadata(args.source, datetime.fromisoformat(args.retrieved_at),
                                    args.universe_policy, args.actions_complete, args.calendar_name,
                                    limitations=tuple(args.limitation))
            snapshot = CsvSource(args.bars, args.calendar, args.securities, metadata, args.actions).load()
        elif args.command == "import-eodhd":
            from quant_core.data.eodhd import EodhdJsonSource
            sessions, calendar_hash = load_calendar(args.calendar)
            securities, security_hash = load_securities(args.securities)
            actions, action_hash = load_actions(args.actions) if args.actions else ((), None)
            hashes = [("calendar_csv", calendar_hash), ("securities_csv", security_hash)]
            if action_hash is not None:
                hashes.append(("actions_csv", action_hash))
            metadata = DataMetadata("eodhd", datetime.fromisoformat(args.retrieved_at), args.universe_policy,
                                    args.actions_complete, args.calendar_name, limitations=tuple(args.limitation),
                                    input_hashes=tuple(hashes))
            responses = {ticker: Path(path).read_bytes() for ticker, path in _pairs(args.response).items()}
            review = sha256(args.action_review.read_bytes()).hexdigest() if args.action_review else None
            snapshot = EodhdJsonSource(responses, _pairs(args.security_map), sessions, securities, metadata,
                                       actions, review, args.raw_cache).load()
        else:
            snapshot = load_local_snapshot(args.snapshot)
        report = check_quality(snapshot, strict_discontinuities=getattr(args, "strict_discontinuities", False))
        output = primitive(report)
        output["has_errors"] = report.has_errors
        print(canonical_json(output))
        if report.has_errors:
            return 1  # Failed imports are reported, never persisted as a qualified snapshot.
        if args.command != "inspect":
            if args.command == "export-parquet" or getattr(args, "parquet", False):
                from quant_core.data.parquet import save_parquet_snapshot
                save_parquet_snapshot(snapshot, args.output)
            else:
                save_snapshot(snapshot, args.output)
        return 0
    except (ValueError, OSError, ImportError) as exc:
        print(f"Data error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
