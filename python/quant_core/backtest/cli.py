"""Developer runner for the same backtest API the desktop will call."""

import argparse
from datetime import date
from pathlib import Path
import sys

from quant_core.backtest import RunConfig, run_backtest
from quant_core.backtest.sources import load_schedule
from quant_core.cli import load_local_snapshot
from quant_core.universes import DatedUniverse
from quant_core.execution import ExecutionProfile
from quant_core.provenance import canonical_json, content_hash
from quant_core.reporting import save_run, verify_run
from quant_core.risk import load_policy
from quant_core.strategies import build_strategy, load_config


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run or verify a daily portfolio backtest")
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("snapshot", type=Path)
    source_options = runner.add_mutually_exclusive_group(required=True)
    source_options.add_argument("--orders", type=Path)
    source_options.add_argument("--strategy", type=Path, help="Frozen rule-based strategy configuration")
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--capital", default="100000")
    runner.add_argument("--risk-policy", type=Path, help="Enable deterministic sizing/risk controls")
    runner.add_argument("--slippage-bps", default="10")
    runner.add_argument("--fee-bps", default="0")
    runner.add_argument("--fee-per-order", default="0")
    runner.add_argument("--execution-delay-sessions", type=int, choices=(1, 2), default=1,
                        help="One by default; two is a registered delay diagnostic requiring risk disabled")
    runner.add_argument("--universe", nargs="+", default=[])
    runner.add_argument("--membership", type=Path, help="Dated historical membership for a rule strategy")
    runner.add_argument("--start", type=date.fromisoformat)
    runner.add_argument("--end", type=date.fromisoformat)
    runner.add_argument("--allow-missing-unheld", action="store_true", help="Unqualified diagnostic mode")
    runner.add_argument("--allow-incomplete-actions", action="store_true", help="Unqualified diagnostic mode")
    runner.add_argument("--strict-discontinuities", action="store_true", help="Block unresolved suspicious price changes")
    verifier = commands.add_parser("verify")
    verifier.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            payload = verify_run(args.directory)
            print(canonical_json({"result_hash": content_hash(payload), "summary": payload["summary"]}))
            return 0
        snapshot = load_local_snapshot(args.snapshot)
        execution = ExecutionProfile(args.slippage_bps, args.fee_bps, args.fee_per_order)
        strategy_config = load_config(args.strategy) if args.strategy else None
        if args.membership and strategy_config is None:
            raise ValueError("Dated membership requires a rule strategy")
        membership = DatedUniverse.load(args.membership) if args.membership else None
        source = (build_strategy(snapshot, strategy_config, args.start, execution, membership=membership) if strategy_config
                  else load_schedule(args.orders))
        config = RunConfig(args.capital, execution,
                           tuple(args.universe) or (strategy_config.universe if strategy_config else ()), args.start, args.end,
                           "allow_missing_unheld_diagnostic" if args.allow_missing_unheld else "strict",
                           "allow_incomplete_diagnostic" if args.allow_incomplete_actions else "require_complete",
                           load_policy(args.risk_policy) if args.risk_policy else None,
                           args.execution_delay_sessions, strict_discontinuities=args.strict_discontinuities)
        result = run_backtest(snapshot, source, config)
        save_run(result, args.output)
        print(canonical_json({"result_hash": result.result_hash, "summary": result.summary,
                              "source_purpose": result.manifest.source.purpose,
                              "quality_issue_count": len(result.manifest.quality_issues)}))
        return 0
    except (ValueError, ArithmeticError, OSError, ImportError) as exc:
        print(f"Backtest error: {exc}", file=sys.stderr)
        return 2
if __name__ == "__main__":
    raise SystemExit(main())
