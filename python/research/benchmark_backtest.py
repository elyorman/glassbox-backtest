"""Reproducible synthetic scaling check; never imported by the runtime."""

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import platform
from time import perf_counter

from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.data import Bar, DataMetadata, Security, Snapshot
from quant_core.execution import OrderRequest
from quant_core.provenance import canonical_json
from quant_core.risk import RiskPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=int, default=200)
    parser.add_argument("--sessions", type=int, default=1260)
    parser.add_argument("--output", type=Path, default=Path("local/backtest-benchmark.json"))
    parser.add_argument("--risk", action="store_true", help="Include admission, stops, and daily portfolio monitoring")
    args = parser.parse_args()
    if min(args.assets, args.sessions) < 2:
        parser.error("Use at least two assets and two sessions")
    if args.risk and args.sessions < 21:
        parser.error("Risk benchmark requires at least 21 sessions for liquidity warmup and execution")
    prepared = perf_counter()
    days = []
    day = date(2010, 1, 4)
    while len(days) < args.sessions:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    securities = tuple(Security(f"SYNTH-{i:04d}", f"T{i}", "SYNTHETIC") for i in range(args.assets))
    price, volume = Decimal(100), Decimal(1000000)
    snapshot = Snapshot(tuple(days), tuple(Bar(s.security_id, d, price, price, price, price, volume)
                                          for d in days for s in securities),
                        DataMetadata("synthetic_scaling_fixture", datetime(2026, 10, 2, tzinfo=timezone.utc),
                                     "fixed_synthetic_universe", True, "synthetic_weekdays_not_exchange_calendar"),
                        securities)
    source = OrderSchedule(tuple(ScheduledOrder(days[19] if args.risk else days[0],
                                               OrderRequest(s.security_id, "buy", "1", stop_price="80" if args.risk else None))
                                 for s in securities[:10]))
    preparation_seconds = perf_counter() - prepared
    durations = []
    results = []
    for _ in range(2):
        started = perf_counter()
        results.append(run_backtest(snapshot, source, RunConfig(risk=RiskPolicy() if args.risk else None)))
        durations.append(perf_counter() - started)
    if results[0] != results[1]:
        raise AssertionError("Repeated runs disagree")
    expected_equity = Decimal(100000) - Decimal("0.1") * min(10, args.assets)
    if results[0].summary.final_equity != expected_equity:
        raise AssertionError("Synthetic final equity does not match the hand calculation")
    peak_bytes = None
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = peak if platform.system() == "Darwin" else peak * 1024
    except ImportError:
        pass
    report = {
        "scope": "Synthetic weekdays, constant raw prices, up to 10 held assets, no corporate actions",
        "python": platform.python_version(), "platform": platform.system(), "architecture": platform.machine(),
        "logical_cpus": os.cpu_count(), "assets": args.assets, "sessions": args.sessions,
        "bars": len(snapshot.bars), "held_assets": min(10, args.assets),
        "risk_enabled": args.risk,
        "preparation_seconds": preparation_seconds,
        "first_run_seconds": durations[0], "repeat_run_seconds": durations[1],
        "peak_process_memory_bytes": peak_bytes,
        "memory_scope": "Whole process, including dataset construction and both retained results",
        "timing_scope": "Validation, data/code hashes, indexing, simulation, and result construction; excludes CSV export",
        "dataset_hash": results[0].manifest.dataset_hash, "engine_hash": results[0].manifest.engine_hash,
        "summary": results[0].summary, "repeated_results_equal": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(report) + "\n")
    print(canonical_json(report))


if __name__ == "__main__":
    main()
