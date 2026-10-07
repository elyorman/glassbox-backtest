"""Offline, fixed-recipe exploratory run; never nominates a production strategy.

Uses immutable Alpaca raw bars/calendar/splits and issuer cash distributions.
The 2016 XLF non-cash distribution is a disclosed signal-only warmup convention;
the portfolio must start after its payable date. No provider calls occur here.
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from quant_core.analytics import paired_metrics, return_metrics, summarize_run
from quant_core.backtest import RunConfig, run_backtest
from quant_core.data import Bar, DataMetadata, Dividend, Security, Snapshot, Split
from quant_core.data.quality import check_quality
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import canonical_json, content_hash
from quant_core.reporting import save_run, verify_run
from quant_core.strategies import build_strategy, load_config, save_recipe_registry


SYMBOLS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "SPY")
START, END = date(2016, 10, 3), date(2026, 10, 2)
SPIN_EX, SPIN_PAY = date(2016, 9, 19), date(2016, 9, 22)
SPIN_VALUE = Decimal("4.5292")  # Issuer Form 8937; signal-only historical valuation.
SPIN_DOCUMENT = "https://www.ssga.com/library-content/products/fund-docs/etfs/us/tax-documents/US-Form-8937-XLF-Signed-New.pdf"


def publish(path, value):
    with path.open("x") as handle:
        handle.write(canonical_json(value) + "\n")


def issuer_rows(path):
    """Read this issuer's explicit shared-string XLSX, preserving decimal text.

    Unsupported cell representations fail instead of silently losing fields.
    """
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        strings = ["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        rows = ET.fromstring(archive.read("xl/worksheets/sheet1.xml")).findall(".//m:row", namespace)
        for row in rows:
            values = {}
            for cell in row:
                column = "".join(c for c in cell.attrib["r"] if c.isalpha())
                kind = cell.attrib.get("t")
                if kind not in (None, "s", "n") or cell.find("m:f", namespace) is not None:
                    raise ValueError("Unsupported issuer cell representation")
                node = cell.find("m:v", namespace)
                value = node.text if node is not None else ""
                values[column] = (strings[int(value)] if kind == "s" and value else value).strip()
            yield values


def parse_issuer_date(value):
    if "/" in value:
        return datetime.strptime(value, "%m/%d/%Y").date()
    # Excel's 1900 serial convention, including its fictitious leap day.
    return date(1899, 12, 30) + timedelta(days=int(value))


def cash_distributions(rows, first, last):
    results, identities, excluded = {}, {}, []
    for row in rows:
        asset = row.get("B")
        if asset not in SYMBOLS:
            continue
        identities[asset] = row["C"]
        ex_date = parse_issuer_date(row["D"])
        if not first <= ex_date <= last:
            continue
        if asset == "XLF" and ex_date == SPIN_EX:
            # 0.139146 is a share distribution ratio, not dollars of cash.
            excluded.append(row)
            continue
        amount = sum((Decimal(row.get(k) or "0") for k in ("G", "H", "I")), Decimal(0))
        if amount <= 0:
            raise ValueError("Non-positive or unsupported issuer distribution")
        payment = parse_issuer_date(row["F"])
        action = Dividend(asset, ex_date, amount, payment)
        key = asset, ex_date
        if key in results:
            raise ValueError("Duplicate issuer security/ex-date; review aggregation before running")
        results[key] = action
    if set(identities) != set(SYMBOLS):
        raise ValueError("Issuer identity coverage incomplete")
    if first <= SPIN_EX <= last and len(excluded) != 1:
        raise ValueError("Expected exactly one separately treated XLF non-cash distribution")
    return results, identities, excluded


def normalize(root):
    raw = root / "raw"
    bars = []
    for file in sorted(raw.glob("bars_raw_20261002T200000Z.[0-9][0-9][0-9][0-9].json")):
        payload = json.loads(file.read_text(), parse_float=Decimal)
        for asset, values in payload["bars"].items():
            for value in values:
                day = datetime.fromisoformat(value["t"].replace("Z", "+00:00")).date()
                bars.append(Bar(asset, day, value["o"], value["h"], value["l"], value["c"], value["v"]))
    if set(b.security_id for b in bars) != set(SYMBOLS):
        raise ValueError("Downloaded symbol coverage incomplete")
    first, last = min(b.session for b in bars), max(b.session for b in bars)
    if last != END:
        raise ValueError("Requested completed-session end is unavailable")
    calendar_records = json.loads((raw / "calendar.0000.json").read_text())
    full_calendar = tuple(date.fromisoformat(v["date"]) for v in calendar_records)
    # END is within October, so monthly scheduling needs no later calendar marker.
    calendar = tuple(d for d in full_calendar if first <= d <= last)
    distributions, identities, excluded = cash_distributions(issuer_rows(raw / "issuer-distributions.xlsx"), first, last)
    actions = json.loads((raw / "actions.0000.json").read_text(), parse_float=Decimal)["corporate_actions"]
    unknown = set(actions) - {"cash_dividends", "forward_splits", "reverse_splits"}
    if unknown:
        raise ValueError(f"Unsupported corporate-action types require review: {sorted(unknown)}")
    splits = []
    for kind in ("forward_splits", "reverse_splits"):
        for value in actions.get(kind, []):
            day = date.fromisoformat(value["ex_date"])
            if first <= day <= last:
                splits.append(Split(value["symbol"], day, Decimal(value["new_rate"]) / Decimal(value["old_rate"])))
    mismatches, provider_missing = [], []
    issuer_keys = set(distributions)
    provider_keys = set()
    for value in actions.get("cash_dividends", []):
        key = value["symbol"], date.fromisoformat(value["ex_date"])
        if not first <= key[1] <= last or key == ("XLF", SPIN_EX):
            continue
        provider_keys.add(key)
        issuer = distributions.get(key)
        if issuer is None:
            mismatches.append({"security": key[0], "ex_date": key[1], "issue": "provider_event_absent_from_issuer"})
        elif abs(issuer.amount - Decimal(value["rate"])) > Decimal("0.000001"):
            mismatches.append({"security": key[0], "ex_date": key[1], "issue": "distribution_amount_differs",
                               "issuer": issuer.amount, "provider": value["rate"]})
        if issuer and value.get("payable_date") and date.fromisoformat(value["payable_date"]) != issuer.pay_date:
            mismatches.append({"security": key[0], "ex_date": key[1], "issue": "payment_date_differs",
                               "issuer": issuer.pay_date, "provider": value["payable_date"]})
    for asset, day in sorted(issuer_keys - provider_keys):
        provider_missing.append({"security": asset, "ex_date": day})
    limitations = (
        "Private exploratory research only; commercial-use rights unresolved, not independently qualified",
        "Fixed surviving nine-sector ETF sample; no historical stock-index membership claim; sectors changed",
        "Alpaca SIP daily open is an aggregation approximation, not a verified auction execution price",
        "Calendar supplied by Alpaca; not independently reconciled against the exchange",
        "Issuer cash distributions replace missing/inconsistent Alpaca records; retrospective revisions possible",
        "Split coverage checked against raw discontinuities, not independently proven exhaustive",
        "2016 XLF XLRE share distribution is excluded from cash actions; issuer 4.5292 tax valuation is a disclosed signal-only warmup approximation",
        "No pre-2016 bars available; momentum has insufficient history until January 2017 and first enters February 2017",
        "Full-period exploratory inspection exposes 2024-2026 dates previously proposed as an untouched holdout",
        "Daily execution, zero cash yield, 10 bps per-side primary cost, whole shares; no stop-risk layer",
    )
    input_hashes = tuple((p.name, hashlib.sha256(p.read_bytes()).hexdigest())
                         for p in sorted(raw.iterdir()) if p.is_file())
    metadata = DataMetadata("alpaca_sip_with_ssga_issuer_cash_distributions", datetime.now(timezone.utc),
                            "fixed_retrospective_surviving_sector_etf_sample", True,
                            "alpaca_market_calendar", limitations=limitations, input_hashes=input_hashes)
    snapshot = Snapshot(calendar, tuple(bars), metadata,
                        tuple(Security(a, a, "NYSE_ARCA") for a in SYMBOLS),
                        tuple(distributions.values()) + tuple(splits))
    quality = check_quality(snapshot)
    if quality.has_errors:
        raise ValueError("Missing/invalid market observations; see quality report before running")
    counts = Counter((v.security_id, v.session.year) for v in distributions.values())
    for asset in SYMBOLS:
        for year in range(2016, 2026):
            if counts[asset, year] < 4:
                raise ValueError(f"Issuer quarterly distribution coverage missing: {asset} {year}")
        if counts[asset, 2026] < 3:
            raise ValueError(f"Issuer 2026 distributions missing: {asset}")
    save_snapshot(snapshot, root / "market.snapshot.json")
    publish(root / "DATA_REVIEW.json", {
        "dataset_hash": snapshot.dataset_hash, "bar_count": len(bars), "sessions": len(calendar),
        "start": first, "end": last, "dividend_count": len(distributions), "split_count": len(splits),
        "issuer_cusips": identities, "excluded_non_cash_distribution": excluded,
        "alpaca_missing_events": provider_missing, "alpaca_issuer_mismatches": mismatches,
        "missing_alpaca_payment_dates": sum(not v.get("payable_date") for v in actions.get("cash_dividends", [])),
        "quality": quality, "qualification": "unqualified_exploratory_only"})
    print(canonical_json({"normalized": snapshot.dataset_hash, "dividends": len(distributions),
                          "splits": len(splits), "vendor_mismatches": len(mismatches)}), flush=True)
    return snapshot


class WarmupDistributionStrategy:
    """Expose a non-cash warmup value to signals without crediting portfolio cash.

    The approximation is bound in provenance and rejected for runs that could
    own the asset through the historical non-cash distribution.
    """

    def __init__(self, base):
        self.base = base
        self.distribution = Dividend("XLF", SPIN_EX, SPIN_VALUE, SPIN_PAY)
        self.spec = replace(base.spec,
                            version="1_with_disclosed_warmup_non_cash_distribution",
                            artifact_hash=content_hash((base.spec, self.distribution, SPIN_DOCUMENT,
                                                       "signal_only_issuer_tax_value_approximation")),
                            signal_price_policy=base.spec.signal_price_policy + ";warmup_xlf_non_cash_tax_value_proxy")

    def validate_run(self, snapshot, config):
        if config.start <= SPIN_PAY:
            raise ValueError("Signal-only distribution cannot model portfolio ownership of a spinoff")
        self.base.validate_run(snapshot, config)

    def orders(self, context):
        if context.as_of < SPIN_PAY:
            raise ValueError("Issuer historical valuation proxy must not be used before payment")
        return self.base.orders(replace(context, _dividends=context._dividends + (self.distribution,)))


def period_rows(result):
    groups = defaultdict(list)
    for state in result.equity:
        groups[state.session.year].append(state.session_return)
    return {str(year): return_metrics(values) for year, values in sorted(groups.items())}


def saved_model(value):
    """Read verified primitive ledgers for analytics without simulating again."""
    if isinstance(value, dict):
        return SimpleNamespace(**{key: saved_model(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(saved_model(item) for item in value)
    if isinstance(value, str):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?", value):
            return Decimal(value)
    return value


def run(root, resume=False):
    snapshot = load_snapshot(root / "market.snapshot.json")
    recipes = root / "recipes"
    if not resume:
        save_recipe_registry(SYMBOLS[:-1], "SPY", recipes)
    names = ("momentum_252_skip21_top3", "broad_market_buy_hold", "broad_market_buy_hold_reserve",
             "same_universe_equal_weight", "cash_control")
    scenarios = (("cost5", "5", 1), ("primary10", "10", 1), ("stress25", "25", 1), ("delay10", "10", 2))
    plan = {"purpose": "private_exploratory_research_not_validation_campaign", "start": START, "end": END,
            "initial_cash": "100000", "dataset_hash": snapshot.dataset_hash,
            "canonical_recipe": names[0], "recipes": [load_config(recipes / (name + ".json")) for name in names],
            "scenarios": scenarios, "no_tuning": True,
            "source_convention": "signal-only warmup XLF non-cash issuer valuation proxy; never portfolio cash",
            "holdout_exposure": {"previously_reserved": ["2024-01-01", "2026-09-30"],
                                 "reason": "User explicitly requested full ten-year exploratory backtest",
                                 "fresh_final_test": False},
            "limitations": snapshot.metadata.limitations,
            "research_source_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if resume:
        original = json.loads((root / "EXPERIMENT_PLAN.json").read_text())
        current = json.loads(canonical_json(plan))
        if any(original[k] != current[k] for k in original if k != "research_source_hash"):
            raise ValueError("Recovery cannot change the frozen experiment")
        publish(root / "RECOVERY.json", {
            "original_plan_hash": content_hash(original),
            "reason": "First simulation saved and verified; metrics crashed on zero SPY dividend audit outside candidate universe",
            "change": "Ignore zero outside-universe income; reject nonzero outside-universe income",
            "performance_tuning": False, "existing_simulations_reused": True,
            "research_source_hash": current["research_source_hash"],
            "analytics_source_hash": hashlib.sha256(Path("python/quant_core/analytics/__init__.py").read_bytes()).hexdigest()})
        plan = original
    else:
        publish(root / "EXPERIMENT_PLAN.json", plan)  # BEFORE any performance run.
    reports, results = [], {}
    for scenario, cost, delay in scenarios:
        execution = ExecutionProfile(cost, "0", "0")
        for name in names:
            configuration = load_config(recipes / (name + ".json"))
            base = build_strategy(snapshot, configuration, START, execution)
            source = WarmupDistributionStrategy(base)
            binding = RunConfig("100000", execution, configuration.universe, START, END,
                                execution_delay_sessions=delay)
            target = root / "runs" / scenario / name
            record = {"scenario": scenario, "recipe": name, "cost_bps": cost, "delay_sessions": delay,
                      "plan_hash": content_hash(plan), "status": "started"}
            record_path = root / f"TRIAL_{scenario}_{name}"
            started = record_path.with_suffix(".started.json")
            if not started.exists():
                publish(started, record)
            elif not resume or not target.exists():
                raise ValueError("An interrupted simulation without a saved bundle cannot be silently rerun")
            try:
                if target.exists():
                    result = saved_model(verify_run(target))
                    expected = json.loads(canonical_json(binding))
                    persisted = json.loads((target / "manifest.json").read_text())
                    if persisted["config"] != expected or persisted["dataset_hash"] != snapshot.dataset_hash:
                        raise ValueError("Saved run does not match the frozen experiment")
                    record["recovered_saved_simulation"] = True
                else:
                    result = run_backtest(snapshot, source, binding)
                    save_run(result, target)
                payload = verify_run(target)
                if not isinstance(result, SimpleNamespace) and content_hash(payload) != result.result_hash:
                    raise ValueError("Saved result verification failed")
                valid = not (configuration.family == "buy_hold" and
                             (not any(v.side == "buy" for v in result.fills) or result.summary.rejected_order_count))
                metrics = summarize_run(result)
                record.update(status="completed" if valid else "invalid_benchmark",
                              result_hash=content_hash(payload), summary=payload["summary"], metrics=metrics,
                              annual=period_rows(result),
                              first_fill=min((f.execution_date for f in result.fills), default=None),
                              last_fill=max((f.execution_date for f in result.fills), default=None))
                results[scenario, name] = result
            except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
                record.update(status="failed", error=str(exc))
            publish(record_path.with_suffix(".completed.json"), record)
            reports.append(record)
            print(canonical_json({k: record.get(k) for k in ("scenario", "recipe", "status", "summary", "error")}), flush=True)
    comparisons = []
    for scenario, _, _ in scenarios:
        candidate = results.get((scenario, names[0]))
        if candidate:
            for name in names[1:]:
                benchmark = results.get((scenario, name))
                record = next(v for v in reports if v["scenario"] == scenario and v["recipe"] == name)
                if benchmark and record["status"] == "completed":
                    comparisons.append({"scenario": scenario, "benchmark": name,
                                        "metrics": paired_metrics([s.session_return for s in candidate.equity],
                                                                  [s.session_return for s in benchmark.equity])})
    publish(root / "RESULTS.json", {"purpose": "unqualified_exploratory_research", "plan_hash": content_hash(plan),
                                    "trials": reports, "comparisons": comparisons,
                                    "fresh_final_test": False, "strategy_selected": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("command", choices=("normalize", "run"))
    parser.add_argument("--resume", action="store_true", help="Recover a saved simulation after reporting failed")
    args = parser.parse_args()
    if args.command == "normalize":
        normalize(args.root)
    else:
        run(args.root, args.resume)


if __name__ == "__main__":
    main()
