"""Local, auditable result bundles with integrity-checked JSON and CSV ledgers."""

import csv
from dataclasses import fields
from hashlib import sha256
import json
from pathlib import Path

from quant_core.backtest.contracts import (
    BacktestResult, CashMovement, CorporateActionRecord, DailyState, FillRecord, RunSummary, SignalDecision,
)
from quant_core.portfolio import PositionValue, Receivable
from quant_core.provenance import canonical_json, content_hash, primitive
from quant_core.risk import RiskDecision

LEGACY_FILES = {"run.json", "manifest.json", "orders.csv", "fills.csv", "cash.csv", "actions.csv",
         "equity.csv", "positions.csv", "receivables.csv"}
SCHEMA_FILES = {1: LEGACY_FILES, 2: LEGACY_FILES | {"risk.csv"},
               3: LEGACY_FILES | {"risk.csv", "signals.csv"}}
FILES = SCHEMA_FILES[3]


def _csv(path, names, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def save_run(result: BacktestResult, directory: Path) -> None:
    """Refuse existing destinations; a completion marker is written last."""
    directory.mkdir(parents=True, exist_ok=False)
    payload = primitive(result)
    (directory / "run.json").write_text(
        canonical_json({"schema_version": 3, "result_hash": result.result_hash, "result": payload}) + "\n",
        encoding="utf-8")
    (directory / "manifest.json").write_text(canonical_json(result.manifest) + "\n", encoding="utf-8")
    order_names = ["order_id", "signal_date", "eligible_date", "processed_date", "security_id", "side",
                   "requested_quantity", "adjusted_quantity", "priority", "signal_reason", "status",
                   "reason_code", "fill_id", "requested_stop_price", "adjusted_stop_price"]
    order_rows = []
    for order in payload["orders"]:
        request = order["request"]
        order_rows.append({"order_id": order["order_id"], "signal_date": order["signal_date"],
                           "eligible_date": order["eligible_date"], "processed_date": order["processed_date"],
                           "security_id": request["security_id"], "side": request["side"],
                           "requested_quantity": request["quantity"], "adjusted_quantity": order["adjusted_quantity"],
                           "priority": request["priority"], "signal_reason": request["reason"],
                           "status": order["status"], "reason_code": order["reason_code"], "fill_id": order["fill_id"],
                           "requested_stop_price": request["stop_price"], "adjusted_stop_price": order["adjusted_stop_price"]})
    _csv(directory / "orders.csv", order_names, order_rows)
    for filename, record_type, key in (("fills.csv", FillRecord, "fills"),
                                        ("cash.csv", CashMovement, "cash_movements"),
                                        ("actions.csv", CorporateActionRecord, "corporate_actions"),
                                        ("receivables.csv", Receivable, "outstanding_receivables")):
        _csv(directory / filename, [f.name for f in fields(record_type)], payload[key])
    equity_names = [f.name for f in fields(DailyState) if f.name != "positions"]
    _csv(directory / "equity.csv", equity_names,
         [{key: value for key, value in state.items() if key != "positions"} for state in payload["equity"]])
    _csv(directory / "positions.csv", ["session"] + [f.name for f in fields(PositionValue)],
         [dict(position, session=state["session"]) for state in payload["equity"] for position in state["positions"]])
    _csv(directory / "risk.csv", [f.name for f in fields(RiskDecision)],
         [dict(row, reason_codes="|".join(row["reason_codes"])) for row in payload["risk_decisions"]])
    _csv(directory / "signals.csv", [f.name for f in fields(SignalDecision)],
         [dict(row, reason_codes="|".join(row["reason_codes"]), features=canonical_json(row["features"]))
          for row in payload["signal_decisions"]])
    hashes = {name: sha256((directory / name).read_bytes()).hexdigest() for name in sorted(FILES)}
    (directory / "COMPLETE.json").write_text(
        canonical_json({"schema_version": 3, "result_hash": result.result_hash, "files": hashes}) + "\n",
        encoding="utf-8")


def verify_run(directory: Path) -> dict:
    """Verify all bundle files and return the persisted result as primitive data."""
    try:
        marker = json.loads((directory / "COMPLETE.json").read_text(encoding="utf-8"))
        if (set(marker) != {"schema_version", "result_hash", "files"}
                or type(marker["schema_version"]) is not int or marker["schema_version"] not in SCHEMA_FILES
                or set(marker["files"]) != SCHEMA_FILES[marker["schema_version"]]):
            raise ValueError("Unsupported or incomplete run bundle")
        for name in sorted(marker["files"]):
            if sha256((directory / name).read_bytes()).hexdigest() != marker["files"][name]:
                raise ValueError(f"Run file integrity mismatch: {name}")
        envelope = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        if (set(envelope) != {"schema_version", "result_hash", "result"}
                or type(envelope["schema_version"]) is not int or envelope["schema_version"] != marker["schema_version"]):
            raise ValueError("Unsupported run schema")
        if content_hash(envelope["result"]) != envelope["result_hash"] or envelope["result_hash"] != marker["result_hash"]:
            raise ValueError("Run result integrity mismatch")
        result = envelope["result"]
        expected_fields = {f.name for f in fields(BacktestResult)}
        if marker["schema_version"] < 3:
            expected_fields -= {"signal_decisions"}
        if marker["schema_version"] == 1:
            expected_fields -= {"risk_decisions"}
        if (not isinstance(result, dict) or set(result) != expected_fields
                or not isinstance(result["summary"], dict)
                or set(result["summary"]) != {f.name for f in fields(RunSummary)}
                or not isinstance(result["manifest"], dict)):
            raise ValueError("Malformed run result schema")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest != result["manifest"]:
            raise ValueError("Standalone manifest disagrees with the run result")
        return result
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed run bundle: {exc}") from exc
