"""Synthetic strategy scaling/conformance check; no empirical alpha-performance run."""

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import platform
from time import perf_counter

from quant_core.backtest import RunConfig, run_backtest
from quant_core.data import Bar, DataMetadata, Security, Snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import canonical_json
from quant_core.strategies import StrategyConfig, build_strategy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("local/strategy-benchmark.json"))
    args = parser.parse_args()
    days, day = [], date(2010, 1, 4)
    while len(days) < 1260:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    securities = tuple(Security(f"SYNTH-{i:04d}", f"T{i}", "SYNTHETIC") for i in range(200))
    price, volume = Decimal(100), Decimal(1000000)
    snapshot = Snapshot(tuple(days), tuple(Bar(s.security_id, d, price, price, price, price, volume)
                                          for d in days for s in securities),
                        DataMetadata("synthetic_strategy_scaling", datetime(2026, 10, 2, tzinfo=timezone.utc),
                                     "fixed_synthetic_universe", True, "synthetic_weekdays_not_exchange_calendar"), securities)
    strategy = StrategyConfig("synthetic_momentum252_top3_scaling", "momentum",
                              tuple(s.security_id for s in securities), purpose="engineering_fixture")
    execution = ExecutionProfile("10")
    source = build_strategy(snapshot, strategy, execution=execution)
    runs, durations = [], []
    for _ in range(2):
        started = perf_counter()
        runs.append(run_backtest(snapshot, source, RunConfig(execution=execution)))
        durations.append(perf_counter() - started)
    # Zero returns tie by ID. Each selected slot: floor((100000*.95/3)/100.1)=316.
    # Three opening buys incur .1/share slippage, then hold constant prices.
    if runs[0] != runs[1] or runs[0].summary.final_equity != Decimal("99905.200"):
        raise AssertionError("Strategy benchmark failed repeated/independent final-equity checks")
    if [(f.security_id, f.quantity) for f in runs[0].fills] != [(s.security_id, Decimal(316)) for s in securities[:3]]:
        raise AssertionError("Strategy benchmark failed independent ranking/quantity checks")
    peak_bytes = None
    try:
        import resource
        peak_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except ImportError:
        pass
    report = {"scope": "Synthetic 200 assets/1260 weekdays/252000 constant-price bars; monthly momentum252 skip21 top3",
              "python": platform.python_version(), "platform": platform.system(), "logical_cpus": os.cpu_count(),
              "first_run_seconds": durations[0], "repeat_run_seconds": durations[1],
              "peak_process_memory_bytes": peak_bytes, "memory_scope": "Whole process including both retained results",
              "timing_scope": "Validation, hashes, indexing, causal strategy decisions and portfolio simulation; excludes export",
              "repeated_results_equal": True, "engine_hash": runs[0].manifest.engine_hash,
              "dataset_hash": runs[0].manifest.dataset_hash, "source": runs[0].manifest.source,
              "summary": runs[0].summary, "signal_decision_count": len(runs[0].signal_decisions)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(report) + "\n")
    # Full predeclared calendar is stored in the file, not echoed to terminal.
    print(canonical_json({key: value for key, value in report.items() if key != "source"}))


if __name__ == "__main__":
    main()
