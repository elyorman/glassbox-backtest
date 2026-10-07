"""Mechanical input checks for the frozen stock retest; no portfolios execute."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from quant_core import __version__
from quant_core.backtest.engine import _engine_hash
from quant_core.cli import load_local_snapshot
from quant_core.data import snapshot_payload
from quant_core.data.quality import check_quality
from quant_core.provenance import content_hash, primitive
from quant_core.validation.contracts import CAPABILITIES, parse_qualification
from quant_core.validation.registry import publish
from research.source_archive import verify_source_archive


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate evidence field")
        result[key] = value
    return result


def _read(path):
    value = json.loads(Path(path).read_bytes(), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError("Evidence must be a JSON object")
    return value


def _hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _check_bound(files):
    if any(_hash(path) != digest for path, digest in files.items()):
        raise ValueError("Input integrity changed during review; prepare a new preflight")


def preflight(snapshot, frozen_plan, qualification=None):
    """Report all input conflicts; human-reviewed evidence remains indispensable."""
    checks = {}

    def check(name, passed, explanation, observed=None):
        checks[name] = dict(status="passed" if passed else "failed", explanation=explanation, observed=observed)

    provider = snapshot.metadata.source
    check("independent_dataset", snapshot.dataset_hash != frozen_plan["dataset_hash"],
          "Candidate hash must differ from the original dataset", snapshot.dataset_hash)
    check("independent_provider", provider != frozen_plan["source_provider"] and not provider.lower().startswith("alpaca"),
          "Different source required; a source name alone does not prove acquisition independence", provider)
    calendar = [d.isoformat() for d in snapshot.sessions]
    check("calendar", calendar == frozen_plan["calendar"], "Exact frozen sessions, including warmup, required",
          dict(candidate_count=len(calendar), required_count=len(frozen_plan["calendar"])))
    required = set(frozen_plan["stocks"]) | {frozen_plan["benchmark"]}
    actual = {s.security_id for s in snapshot.securities}
    check("security_panel", actual == required, "Same surviving panel and separate benchmark; no replacements",
          dict(missing=sorted(required-actual), extra=sorted(actual-required)))
    check("actions_complete", snapshot.metadata.actions_complete,
          "Reviewed complete actions required; this source assertion is not independent proof")
    quality = check_quality(snapshot, strict_discontinuities=True)
    check("data_quality", not quality.has_errors, "Strict missing-bar and unexplained-discontinuity checks",
          primitive(quality.issues))
    schema = snapshot_payload(snapshot)["schema_version"]
    check("frozen_snapshot_schema", schema == 1,
          "Original runtime accepts JSON schema 1; schema 2 needs explicit compatibility work, never silent approximation", schema)
    adjusted_volume = (provider.lower() == "eodhd" or any("split-adjusted volume" in s.lower()
                       for s in snapshot.metadata.limitations))
    checks["raw_volume_basis"] = dict(status="unresolved" if adjusted_volume else "passed",
        explanation=("Known split-adjusted volume conflicts with historical liquidity/capacity; reviewed reconstruction required"
                     if adjusted_volume else "No declared adjusted-volume conflict; reviewer must evidence actual volume basis"))
    bound = (qualification is not None and qualification.dataset_hash == snapshot.dataset_hash
             and qualification.scope == "independent_retest_fixed_sample"
             and qualification.independent_from == frozen_plan["dataset_hash"])
    check("qualification_binding", bound, "Review must bind the candidate and original dataset, with independent-retest scope")
    capabilities = (primitive(qualification.capabilities) if qualification is not None else
                    [dict(name=name, status="unresolved", evidence="No reviewed qualification supplied") for name in CAPABILITIES])
    ready = all(c["status"] == "passed" for c in checks.values()) and all(c["status"] == "passed" for c in capabilities)
    return dict(schema_version=1, tool_version=__version__, preflight_runtime_hash=_engine_hash(),
                input_gate_ready=ready, dataset_hash=snapshot.dataset_hash,
                original_dataset_hash=frozen_plan["dataset_hash"], checks=checks, capabilities=capabilities,
                qualification=primitive(qualification) if qualification is not None else None,
                source_limitations=list(snapshot.metadata.limitations), retest_executed=False,
                strategy_qualified=False, fresh_temporal_holdout=False,
                interpretation="Input preflight only. Human evidence review and the exact archived retest gate remain required; fixed survivor sample and already exposed dates persist")


def qualification_template(snapshot, frozen_plan):
    return dict(schema_version=1, qualification=dict(dataset_hash=snapshot.dataset_hash,
        scope="independent_retest_fixed_sample", reviewer=None, reviewed_on=None,
        capabilities=[dict(name=name, status="unresolved", evidence="Required: review source-specific evidence for "+name)
                      for name in CAPABILITIES],
        limitations=["Fixed retrospectively chosen surviving stock panel, not historical index membership",
                     "Previously exposed market history; no new temporal holdout",
                     "Daily open simulation; liquidity/raw-volume and execution assumptions require review"],
        independent_from=frozen_plan["dataset_hash"], independence_evidence=None))


def load_frozen_scope(campaign, archive):
    """Bind registration/freeze metadata; this does not replace full ledger verification."""
    names = ("EXPERIMENT_PLAN.json", "RESULTS.json", "FROZEN_CANDIDATES.json", "RETEST_REQUIREMENTS.json")
    # Capture identities before parsing; a concurrent rewrite must not bind old
    # decoded values to newly observed bytes.
    bound = {str((campaign/name).resolve()): _hash(campaign/name) for name in names}
    bound[str((archive/"SOURCE_ARCHIVE.json").resolve())] = _hash(archive/"SOURCE_ARCHIVE.json")
    plan, results, frozen, requirements = (_read(campaign/name) for name in names)
    plan_hash = content_hash(plan)
    manifest = verify_source_archive(archive)
    if manifest["files"] != plan["source_hashes"]:
        raise ValueError("Frozen source archive differs from registration")
    if any(document.get("plan_hash") != plan_hash for document in (results, frozen, requirements)):
        raise ValueError("Frozen campaign metadata binding changed")
    expected = [entry for entry in plan["entries"] if entry["role"] == "parent"
                and results["decisions"][entry["configuration"]["name"]]["freeze_for_retest"]]
    if not expected or frozen.get("entries") != expected or requirements.get("frozen_count") != len(expected):
        raise ValueError("Frozen candidates differ from registered decisions")
    if frozen.get("production_nomination") is not False:
        raise ValueError("Research freeze is not production nomination")
    bound.update({str((archive/name).resolve()): digest for name, digest in manifest["files"].items()})
    scope = dict(plan_hash=plan_hash, start=plan["start"], end=plan["end"], stocks=plan["stocks"],
                 benchmark=plan["benchmark"], calendar=plan["calendar"], frozen_entries=expected,
                 source_hashes=plan["source_hashes"], metadata_binding_only=True,
                 interpretation="Trusted original campaign metadata; full archived portfolio verification remains separate")
    if "readiness_path" in plan or "readiness_hash" in plan:
        readiness = Path(plan["readiness_path"])
        if _hash(readiness) != plan["readiness_hash"]:
            raise ValueError("Original readiness evidence changed")
        observation = _read(readiness)
        if observation.get("dataset_hash") != plan["dataset_hash"]:
            raise ValueError("Original readiness dataset binding differs")
        scope["original_source_readiness"] = dict(qualified=observation.get("qualified"),
            missing_payment_count=len(observation.get("missing_payable_dates", ())),
            interpretation="Original development-source observations, not candidate-provider facts")
        bound[str(readiness.resolve())] = plan["readiness_hash"]
    _check_bound(bound)
    return plan, scope, bound


def verify_package(directory):
    directory = Path(directory)
    marker = _read(directory/"COMPLETE.json")
    expected = {"PREFLIGHT.json", "SCOPE.json", "QUALIFICATION_TEMPLATE.json"}
    if (marker.get("schema_version") != 1 or set(marker.get("files", {})) != expected
            or {p.name for p in directory.iterdir()} != expected | {"COMPLETE.json"}):
        raise ValueError("Preflight package integrity: incomplete/changed file set")
    if any((directory/name).is_symlink() or _hash(directory/name) != digest for name, digest in marker["files"].items()):
        raise ValueError("Preflight package integrity mismatch")
    report = _read(directory/"PREFLIGHT.json")
    _check_bound(report["input_files"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("campaign", "source-archive", "snapshot", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--qualification", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise FileExistsError("Output already exists; preserve original preflight")
        plan, scope, bound = load_frozen_scope(args.campaign, args.source_archive)
        paths = (args.snapshot/"bars.parquet", args.snapshot/"manifest.json") if args.snapshot.is_dir() else (args.snapshot,)
        bound.update({str(path.resolve()): _hash(path) for path in paths})
        if args.qualification:
            bound[str(args.qualification.resolve())] = _hash(args.qualification)
        snapshot = load_local_snapshot(args.snapshot)
        review = None
        if args.qualification:
            envelope = _read(args.qualification)
            if (set(envelope) != {"schema_version", "qualification"}
                    or type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1):
                raise ValueError("Unsupported qualification envelope")
            review = parse_qualification(envelope["qualification"])
        report = dict(preflight(snapshot, plan, review), input_files=bound, frozen_plan_hash=content_hash(plan))
        documents = {"PREFLIGHT.json": report, "SCOPE.json": scope,
                     "QUALIFICATION_TEMPLATE.json": qualification_template(snapshot, plan)}
        _check_bound(bound)
        args.output.mkdir(parents=True)
        for name, value in documents.items():
            publish(args.output/name, value)
        publish(args.output/"COMPLETE.json", dict(schema_version=1,
                files={name: _hash(args.output/name) for name in documents}))
        verify_package(args.output)
        print(json.dumps({"input_gate_ready": report["input_gate_ready"], "dataset_hash": snapshot.dataset_hash,
                          "blocked_checks": [k for k,v in report["checks"].items() if v["status"] != "passed"],
                          "unreviewed_capabilities": [c["name"] for c in report["capabilities"] if c["status"] != "passed"],
                          "retest_executed": False}))
        return 0 if report["input_gate_ready"] else 1
    except (ValueError, OSError, ImportError, TypeError, KeyError):
        print("Data preflight error: malformed input, changed evidence, or immutable output conflict", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
