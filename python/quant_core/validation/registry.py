"""Exclusive local publication and a verifiable append-only campaign event chain."""

from contextlib import contextmanager
import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from quant_core.provenance import canonical_json, content_hash, primitive


def publish(path, value):
    publish_text(path, canonical_json(value) + "\n")


def publish_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                prefix=".validation-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_document(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Registry:
    def __init__(self, directory):
        self.directory = Path(directory)
        self._locked_events = None

    @contextmanager
    def exclusive(self):
        path = self.directory / "ACTIVE.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(str(os.getpid()) + "\n")
            self._locked_events = list(self.events())
            yield
        finally:
            self._locked_events = None
            path.unlink(missing_ok=True)

    def events(self):
        if self._locked_events is not None:
            return tuple(self._locked_events)
        events, previous = [], None
        root = self.directory / "events"
        paths = sorted(root.glob("*.json"))
        for index, path in enumerate(paths, 1):
            event = read_document(path)
            if path.name != f"{index:06d}.json" or set(event) != {"hash", "event"}:
                raise ValueError("Registry sequence/schema mismatch")
            row = event["event"]
            if (set(row) != {"sequence", "previous_hash", "recorded_at", "kind", "payload"}
                    or type(row["sequence"]) is not int or row["sequence"] != index
                    or row["previous_hash"] != previous or content_hash(row) != event["hash"]):
                raise ValueError("Registry integrity mismatch")
            previous = event["hash"]
            events.append(row)
        return tuple(events)

    def append(self, kind, payload):
        if self._locked_events is None:
            raise ValueError("Registry writes require its exclusive lock")
        events = self.events()
        previous = content_hash(events[-1]) if events else None
        row = {"sequence": len(events) + 1, "previous_hash": previous,
               "recorded_at": datetime.now(timezone.utc).isoformat(), "kind": kind, "payload": payload}
        publish(self.directory / "events" / f"{len(events) + 1:06d}.json",
                {"hash": content_hash(row), "event": row})
        self._locked_events.append(primitive(row))

    def has(self, kind):
        return any(e["kind"] == kind for e in self.events())

    def outcome(self, phase):
        if phase not in ("development", "selection", "crosscheck", "final"):
            raise ValueError("Unknown campaign phase")
        envelope = read_document(self.directory / f"{phase}.json")
        if set(envelope) != {"hash", "report"} or content_hash(envelope["report"]) != envelope["hash"]:
            raise ValueError("Phase report integrity mismatch")
        events = self.events()
        matches = [e for e in events if e["kind"] == "phase_complete" and e["payload"]["phase"] == phase]
        if len(matches) != 1 or matches[0]["payload"]["report_hash"] != envelope["hash"]:
            raise ValueError("Phase report is not anchored in the registry")
        report = envelope["report"]
        if (report.get("comparison_csv") != f"{phase}.csv" or
                sha256((self.directory / f"{phase}.csv").read_bytes()).hexdigest() != report.get("comparison_csv_hash")):
            raise ValueError("Comparison CSV integrity mismatch")
        return envelope["report"]

    def save_outcome(self, phase, report):
        columns = ("period", "input_dataset_hash", "recipe", "family", "scenario", "status", "total_return",
                   "cagr_calendar", "volatility", "sharpe", "sortino", "calmar", "max_drawdown", "longest_underwater_sessions",
                   "notional_turnover", "average_gross_exposure", "average_cash_fraction", "fees", "slippage",
                   "fill_count", "rejected_orders", "expired_orders", "error", "reasons")
        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        rows = report.get("trials", []) + [row for provider in report.get("providers", []) for row in provider["trials"]]
        for row in rows:
            values = dict(row.get("metrics", {}), **{key: value for key, value in row.items() if key != "metrics"})
            values["reasons"] = "|".join(row.get("reasons", ()))
            writer.writerow({key: values.get(key) for key in columns})
        data = output.getvalue()
        publish_text(self.directory / f"{phase}.csv", data)
        report["comparison_csv"] = f"{phase}.csv"
        report["comparison_csv_hash"] = sha256(data.encode("utf-8")).hexdigest()
        publish(self.directory / f"{phase}.json", {"hash": content_hash(report), "report": report})
        self.append("phase_complete", {"phase": phase, "report_hash": content_hash(report)})
