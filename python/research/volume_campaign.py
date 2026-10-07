"""Byte-registered volume hypothesis: 54 simulations and 54 exact reused references."""
import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal as D, localcontext
import json
from pathlib import Path, PurePosixPath
import shutil

from quant_core.analytics import CONTEXT, sharpe, summarize_run
from quant_core.backtest import RunConfig, run_backtest
from quant_core.backtest.sources import SessionContext
from quant_core.data import Dividend, Split, number
from quant_core.data.storage import load_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import content_hash, primitive
from quant_core.reporting import save_run, verify_run
from quant_core.strategies import StrategyConfig, benchmark_recipes, build_strategy
from quant_core.strategies.volume import VolumeConfig, build_volume_strategy
from quant_core.validation.statistics import paired_bootstrap
from research import stock_campaign as stock
from research.high_campaign import digest, overlap_diagnostics, reuse_reference, MOMENTUM, PARENT as HIGH
from research.market_backtest import publish, saved_model, period_rows
from research.robustness_audit import source_hashes, audit_ledger, verified_cash_inputs
from research.robustness_metrics import cash_intervals
from research.source_archive import archive_sources, verify_source_archive

PARENT = "stock_unusual_dollar_volume50_top5"
CONTROL = "stock_low_dollar_volume50_top5"
SPEC_HASH = "5c68046f89f4b703cfcf1ac50b675d19e4dfa1ceb8aa2bb9bb549a553fb05f47"
REVIEW_HASH = "4c07e1f5f5dab1f9402ed0f07f0ff19b5e0a1c18f5cc13497453e5996836c1af"
PAPER = "https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf"
REPO = Path(__file__).resolve().parents[2]


def verify_file_map(root, files):
    for name, value in files.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or relative.as_posix() != name:
            raise ValueError("Unsafe evidence path")
        path = root / name
        if path.is_symlink() or digest(path) != value:
            raise ValueError("Preserved evidence changed: " + str(path))


def volume_entries(stocks):
    result = []
    for name, role, window, direction in ((PARENT,"parent",50,"descending"),
            ("stock_unusual_dollar_volume55_top5","neighbor",55,"descending"),
            (CONTROL,"direction_control",50,"ascending")):
        cfg = VolumeConfig(name, stocks, window_sessions=window, direction=direction,
                           min_price="5", min_average_dollar_volume="10000000")
        result.append(dict(configuration=primitive(cfg),role=role,parent=PARENT,
                           objective="return_seeking",research_source=PAPER,adaptation_not_replication=True))
    result.extend(dict(configuration=primitive(cfg),role="reference",parent=None,objective="reference")
        for cfg in benchmark_recipes(stocks,"SPY") if cfg.name != "broad_market_buy_hold")
    return result


def adapt_plan(base):
    plan = deepcopy(base)
    plan.update(entries=volume_entries(tuple(base["stocks"])),source_hashes=source_hashes(),
                purpose="private_exploratory_frozen_volume_hypothesis",trial_budget=54,
                specification_sha256=SPEC_HASH)
    plan["uncertainty"]["scope"] = "New parent, neighbor and direction control only; all earlier searches excluded; no combined significance, DSR/PBO or fresh OOS claim"
    if sum(len(p["scenarios"]) for p in plan["periods"]) != 9:
        raise ValueError("Frozen budget requires nine period/scenario combinations")
    return primitive(plan)


def validate_frozen_protocol(plan, spec):
    allocation = spec["allocation"]
    candidates = [e for e in plan["entries"] if e["role"] != "reference"]
    if len(candidates) != len(spec["recipes"]):
        raise ValueError("Frozen hypothesis/control count changed")
    for entry, frozen in zip(candidates,spec["recipes"]):
        expected = VolumeConfig(frozen["name"],tuple(plan["stocks"]),window_sessions=frozen["window_sessions"],
            direction=frozen["direction"],top_k=allocation["top_k"],invested_fraction=allocation["invested_fraction"],
            min_price=allocation["min_raw_price"],volume_lookback=allocation["average_volume_window"],
            min_average_dollar_volume=allocation["min_average_dollar_volume"],
            max_volume_participation=allocation["entry_participation"],profile=allocation["profile"])
        if entry["configuration"] != primitive(expected) or entry["role"] != frozen["role"] or entry["parent"] != PARENT or entry["objective"] != "return_seeking":
            raise ValueError("Frozen volume configuration/allocation changed")
    settings = spec["uncertainty"]
    if any(plan["uncertainty"][key] != value for key,value in (("blocks",settings["expected_blocks"]),
            ("repetitions",settings["repetitions"]),("seed",settings["seed"]))):
        raise ValueError("Frozen uncertainty settings changed")
    combinations = sum(len(p["scenarios"]) for p in plan["periods"])
    refs = [e for e in plan["entries"] if e["role"] == "reference"]
    budget = spec["trial_budget"]
    if (plan["trial_budget"] != len(plan["entries"])*combinations or plan["trial_budget"] != budget["per_panel"] or
            len(candidates)*combinations*2 != budget["new_simulations"] or len(refs)*combinations*2 != budget["reused_reference_scenarios"]):
        raise ValueError("Frozen new/reused scenario budget changed")


def direction_comparison(parent, control):
    left, right = parent["equity"], control["equity"]
    dates = [s["session"] for s in left]
    if not dates or dates != sorted(set(dates)) or dates != [s["session"] for s in right]:
        return dict(status="incomplete",reason="unaligned_sessions",mean_daily_parent_minus_control=None,positive=None)
    try:
        differences = tuple(number(a["session_return"]) - number(b["session_return"]) for a,b in zip(left,right))
    except (ValueError, TypeError, KeyError):
        return dict(status="incomplete",reason="undefined_return",mean_daily_parent_minus_control=None,positive=None)
    mean = sum(differences,D(0)) / len(differences)
    return primitive(dict(status="complete",equity_sessions=len(dates),mean_daily_parent_minus_control=mean,
                          positive=mean > 0,uses_net_returns=True))


def direction_panel(plan, trials, payloads):
    table = {r["key"]:r for r in trials}
    result = {}
    for p in plan["periods"]:
        for s in p["scenarios"]:
            key = p["name"] + "_" + s[0]
            keys = (key+"_"+PARENT,key+"_"+CONTROL)
            if any(table[k]["status"] != "completed" or k not in payloads for k in keys):
                result[key] = dict(status="incomplete",reason="invalid_or_missing_portfolio",mean_daily_parent_minus_control=None,positive=None)
            else:
                result[key] = direction_comparison(*(payloads[k] for k in keys))
    return result


def volume_decisions(plan, trials, directions):
    # Keep the original objective and full screens, while explicitly distinguishing
    # missing required evidence (including folds/neighbor/control) from rejection.
    decisions = stock.research_decisions(plan,trials)
    decision = decisions[PARENT]
    required = [r for r in trials if r["recipe"] in (PARENT,stock.REFERENCE,stock.EQUAL) or
                (r["period"] == "continuous" and r["scenario"] in ("primary10","stress25")
                 and r["role"] in ("neighbor","direction_control"))]
    missing = [r["key"] for r in required if r["status"] != "completed" or
               (r["recipe"] in (PARENT,stock.REFERENCE,stock.EQUAL) and r.get("sharpe_historical_reference") is None)]
    direction_pass = []
    for scenario in ("primary10","stress25"):
        key = "continuous_" + scenario
        row = directions.get(key,{})
        if row.get("status") != "complete" or row.get("mean_daily_parent_minus_control") is None:
            missing.append(key+"_direction")
            direction_pass.append(None)
        else:
            direction_pass.append(number(row["mean_daily_parent_minus_control"]) > 0)
    freeze = decision["freeze_for_retest"] and all(v is True for v in direction_pass) and not missing
    decision.update(base_full_rule_passed=decision["freeze_for_retest"],direction_passed=all(v is True for v in direction_pass),
                    direction_by_cost=dict(zip(("primary10","stress25"),direction_pass)),
                    missing_required_evidence=missing,freeze_for_retest=freeze,
                    decision="incomplete" if missing else "promising_exploratory_retest_only" if freeze else "reject_on_this_sample")
    return decisions


def freeze_for_both_samples(decisions):
    return set(decisions) == {"original22","transfer47"} and all(
        d.get(PARENT,{}).get("freeze_for_retest") is True for d in decisions.values())


def volume_diagnostics(payload):
    by_day = defaultdict(list)
    for row in payload["signal_decisions"]:
        by_day[row["session"]].append(row)
    rows, selected_scores = [], []
    for day, panel in sorted(by_day.items()):
        if len({r["security_id"] for r in panel}) != len(panel):
            raise ValueError("Duplicate volume diagnostic decision")
        scores = [number(r["score"]) for r in panel if r["eligible"] and r["score"] is not None]
        selected_scores.extend(number(r["score"]) for r in panel if r["selected"] and r["score"] is not None)
        mean = sum(scores,D(0))/len(scores) if scores else None
        deviation = (sum(((v-mean)**2 for v in scores),D(0))/len(scores)).sqrt() if scores else None
        rows.append(dict(session=day,eligible_scored=len(scores),distinct_scores=len(set(scores)),
                         cross_stock_tie=len(set(scores)) < len(scores),score_range=max(scores)-min(scores) if scores else None,
                         population_score_stddev=deviation))
    return primitive(dict(selected_scores=len(selected_scores),selected_below_090=sum(v<D(".90") for v in selected_scores),
        selected_below_090_fraction=D(sum(v<D(".90") for v in selected_scores))/len(selected_scores) if selected_scores else None,
        cross_stock_tie_sessions=sum(r["cross_stock_tie"] for r in rows),
        cross_stock_tie_session_fraction=D(sum(r["cross_stock_tie"] for r in rows))/len(rows) if rows else None,
        mean_population_score_stddev=sum((r["population_score_stddev"] for r in rows if r["population_score_stddev"] is not None),D(0)) /
            sum(r["population_score_stddev"] is not None for r in rows) if any(r["population_score_stddev"] is not None for r in rows) else None,
        selection_gate=False,rows=rows))


def build_source(data, entry, start, execution):
    if entry["role"] == "reference":
        return build_strategy(data,StrategyConfig(**entry["configuration"]),start,execution)
    return build_volume_strategy(data,VolumeConfig(**entry["configuration"]),start,execution)


def verify_volume_signals(data, source, payload):
    """Replay only causal rule decisions against saved closing states, not returns."""
    histories = defaultdict(list)
    for bar in data.bars:
        histories[bar.security_id].append(bar)
    histories = {a:tuple(sorted(b,key=lambda v:v.session)) for a,b in histories.items()}
    dates = {a:tuple(b.session for b in bars) for a,bars in histories.items()}
    splits = tuple(a for a in data.actions if isinstance(a, Split))
    dividends = tuple(a for a in data.actions if isinstance(a, Dividend))
    model = saved_model(payload)
    replay, requests = [], []
    with localcontext(CONTEXT):
        for state in model.equity:
            context = SessionContext(state.session,source.configuration.universe,state.cash,state.equity,state.positions,
                                     histories,dates,splits,dividends)
            batch = source.orders(context)
            replay.extend(batch.decisions)
            ordered = sorted(batch.requests,key=lambda r: (0 if r.side == "sell" else 1,
                             r.priority,r.security_id,content_hash(r)))
            requests.extend(dict(signal_date=state.session,request=r) for r in ordered)
    if primitive(replay) != payload["signal_decisions"]:
        raise ValueError("Volume signal decisions/raw feature provenance differ from causal replay")
    actual = [dict(signal_date=r["signal_date"],request=r["request"]) for r in payload["orders"]]
    if primitive(requests) != actual:
        raise ValueError("Volume order requests differ from causal rule replay")
    return dict(status="passed",decisions=len(replay),order_requests=len(requests))


def volume_uncertainty(plan, trials, rates, payloads):
    primary = {r["recipe"]:payloads[r["key"]] for r in trials if r["period"] == "continuous" and
               r["scenario"] == "primary10" and r["status"] == "completed" and r["key"] in payloads}
    if primary:
        dates = [s["session"] for s in next(iter(primary.values()))["equity"]]
        if any([s["session"] for s in p["equity"]] != dates for p in primary.values()):
            raise ValueError("Uncertainty portfolios require identical dates")
    result = stock.campaign_uncertainty(plan,trials,rates)
    if PARENT in primary and CONTROL in primary:
        # The shared historical Treasury reference affects the Sharpe difference;
        # mean parent-minus-control returns remain exactly the net daily contrast.
        model = saved_model(primary[PARENT])
        rf = tuple(D(v["return"]) for v in cash_intervals(tuple(s.session for s in model.equity),rates))
        series = {n:tuple(number(s["session_return"])-r for s,r in zip(primary[n]["equity"],rf)) for n in (PARENT,CONTROL)}
        result.setdefault(PARENT,{})[CONTROL] = primitive([paired_bootstrap(series[PARENT],series[CONTROL],block,
            plan["uncertainty"]["repetitions"],plan["uncertainty"]["seed"]) for block in plan["uncertainty"]["blocks"]])
    else:
        result.setdefault(PARENT,{})[CONTROL] = dict(status="incomplete_control_panel")
    result["scope"] = plan["uncertainty"]["scope"]
    return result


def load_specification(repo):
    review = repo/"local/research-decision-2026-10-05"
    if digest(review/"COMPLETE.json") != REVIEW_HASH or digest(review/"NEXT_EXPERIMENT_SPEC.json") != SPEC_HASH:
        raise ValueError("Frozen specification/review bytes changed")
    seal = json.loads((review/"COMPLETE.json").read_text())
    verify_file_map(review,seal["files"])
    spec = json.loads((review/"NEXT_EXPERIMENT_SPEC.json").read_text())
    if digest(repo/spec["specification_document"]) != spec["specification_document_sha256"] or digest(repo/"docs/RESEARCH_DECISION_REVIEW.md") != spec["decision_document_sha256"]:
        raise ValueError("Frozen method document changed")
    current = source_hashes()
    if any(current.get(k) != v for k,v in spec["baseline_runtime_hashes"].items()):
        raise ValueError("Existing 64-file runtime changed")
    return review,seal,spec


def register(output):
    repo = REPO
    review,review_seal,spec = load_specification(repo)
    high_root = repo/"local/high-anchor-2026-10-05"
    high_seal = json.loads((high_root/"COMPLETE.json").read_text())
    verify_file_map(high_root,high_seal["files"])
    panels = []
    for frozen, prior_name, label in zip(spec["panels"],("stock-engine-replay-2026-10-05","universe-transfer-2026-10-05-v2"),("original22","transfer47")):
        root = repo/"local"/prior_name
        seal = json.loads((root/"COMPLETE.json").read_text())
        if digest(root/"COMPLETE.json") != frozen["prior_complete_sha256"]:
            raise ValueError("Prior campaign seal changed")
        verify_file_map(root,seal["files"])
        archived = verify_source_archive(root/"source-archive")["files"]
        if any(source_hashes().get(k) != v for k,v in archived.items()):
            raise ValueError("Reference financial runtime changed")
        old = json.loads((root/"campaign/EXPERIMENT_PLAN.json").read_text())
        data = load_snapshot(Path(frozen["snapshot"]))
        readiness = json.loads(Path(frozen["readiness_path"]).read_text())
        stock.verify_cache(Path(frozen["snapshot"]),data,readiness)
        base = stock.make_plan(data,Path(frozen["snapshot"]),Path(frozen["readiness_path"]),Path(frozen["cash_path"]))
        ignored = {"source_hashes","prior_registration"}
        if {k:v for k,v in base.items() if k not in ignored} != {k:v for k,v in old.items() if k not in ignored}:
            raise ValueError("Baseline protocol changed")
        for field, path in (("snapshot",Path(frozen["snapshot"])),("readiness",Path(frozen["readiness_path"])),("cash",Path(frozen["cash_path"]))):
            if digest(path) != frozen[field+"_sha256"]:
                raise ValueError("Specification input changed: " + field)
        if (data.dataset_hash != frozen["dataset_hash"] or base["stocks"] != frozen["stocks"] or
                content_hash(base["calendar"]) != frozen["calendar_sha256"] or base["periods"] != frozen["periods"] or
                base["freeze_rule"] != frozen["freeze_rule"] or base["objectives"]["return_seeking"] != frozen["objective"]):
            raise ValueError("Specification data/calendar/protocol mismatch")
        plan = adapt_plan(base)
        validate_frozen_protocol(plan,spec)
        if [e["configuration"] for e in plan["entries"] if e["role"] == "reference"] != frozen["reference_configurations"]:
            raise ValueError("Frozen reference configurations changed")
        if [(e["configuration"]["name"],e["role"],e["configuration"]["window_sessions"],e["configuration"]["direction"]) for e in plan["entries"][:3]] != [(r["name"],r["role"],r["window_sessions"],r["direction"]) for r in spec["recipes"]]:
            raise ValueError("Frozen volume recipes changed")
        # Verify every reference origin BEFORE the first new portfolio outcome.
        prior = json.loads((root/"campaign/RESULTS.json").read_text())
        old_rows = {r["key"]:r for r in prior["trials"]}
        reference_hashes = {}
        for key,(p,s,e) in stock.expected_panel(plan).items():
            if e["role"] != "reference":
                continue
            row = old_rows[key]
            payload = verify_run(Path(row["bundle"]))
            execution = ExecutionProfile(s[1],"0","0")
            cfg = RunConfig("100000",execution,tuple(e["configuration"]["universe"]),date.fromisoformat(p["start"]),date.fromisoformat(p["end"]),actions_policy="allow_incomplete_diagnostic",execution_delay_sessions=s[2])
            source = build_source(data,e,cfg.start,execution)
            if (row["status"] != "completed" or content_hash(payload) != row["result_hash"] or
                    payload["manifest"]["dataset_hash"] != plan["dataset_hash"] or payload["manifest"]["config"] != primitive(cfg) or
                    payload["manifest"]["source"] != primitive(source.spec)):
                raise ValueError("Reference origin/configuration mismatch before outcomes")
            reference_hashes[key] = row["result_hash"]
        panels.append(dict(label=label,prior_root=str(root),prior_campaign=str(root/"campaign"),
            prior_complete_hash=digest(root/"COMPLETE.json"),prior_files=seal["files"],plan=plan,reference_result_hashes=reference_hashes))
    if sum(p["plan"]["trial_budget"] for p in panels) != spec["trial_budget"]["scenario_entries"]:
        raise ValueError("Combined budget differs from specification")
    output.mkdir(parents=True,exist_ok=False)
    archive = archive_sources(repo,output/"source-archive")
    # Preserve documents whose old seal includes mutable README/status navigation.
    for name, value in review_seal["document_hashes"].items():
        source = repo/name
        if digest(source) != value:
            raise ValueError("Original review document changed before preservation")
        target = output/"original-documents"/name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    registration = dict(schema_version=1,registered_at=datetime.now(timezone.utc),repository_root=str(repo),panels=panels,
        source_hashes=archive["files"],specification_sha256=SPEC_HASH,review_root=str(review),review_complete_sha256=REVIEW_HASH,
        review_files=review_seal["files"],original_document_hashes=review_seal["document_hashes"],
        high_root=str(high_root),high_complete_sha256=digest(high_root/"COMPLETE.json"),high_files=high_seal["files"],
        new_simulations=54,reused_reference_scenarios=54,scenario_entries=108,new_hypotheses=1,
        prior_search=spec["prior_search"],direction_gate=spec["direction_gate"],stopping_rule=spec["stopping_rule"],
        qualified=False,fresh_final_test=False,independent_validation=False,production_nomination=False)
    publish(output/"REGISTRATION.json",registration)
    publish(output/"REGISTRATION_HASH.json",dict(sha256=digest(output/"REGISTRATION.json")))
    print(json.dumps(dict(registered=True,new_simulations=54,reused_reference_scenarios=54,source_files=len(archive["files"]))),flush=True)


def verify_recovery(registration):
    recovery = registration.get("recovery")
    if recovery is None:
        return
    root = Path(recovery["root"])
    if digest(root/"COMPLETE.json") != recovery["complete_sha256"] or digest(root/"REGISTRATION.json") != recovery["original_registration_sha256"]:
        raise ValueError("Original failure seal/registration changed")
    if recovery["files"] != json.loads((root/"COMPLETE.json").read_text())["files"]:
        raise ValueError("Original failure evidence registry incomplete")
    verify_file_map(root,recovery["files"])
    original = json.loads((root/"REGISTRATION.json").read_text())
    if original["source_hashes"] != recovery["original_source_hashes"]:
        raise ValueError("Original registered runtime changed")
    current,previous = registration["source_hashes"],original["source_hashes"]
    changed = {k for k in set(current)|set(previous) if current.get(k) != previous.get(k)}
    if changed != {"research/volume_campaign.py"}:
        raise ValueError("Recovery forbids changes to financial sources")


def guard_registration(output):
    if digest(output/"REGISTRATION.json") != json.loads((output/"REGISTRATION_HASH.json").read_text())["sha256"]:
        raise ValueError("Registration bytes changed")
    reg = json.loads((output/"REGISTRATION.json").read_text())
    verify_recovery(reg)
    if source_hashes() != reg["source_hashes"] or verify_source_archive(output/"source-archive")["files"] != reg["source_hashes"]:
        raise ValueError("Registered runtime changed")
    for label in ("review","high"):
        root = Path(reg[label+"_root"])
        if digest(root/"COMPLETE.json") != reg[label+"_complete_sha256"]:
            raise ValueError("Prior completion changed")
        verify_file_map(root,reg[label+"_files"])
    verify_file_map(output/"original-documents",reg["original_document_hashes"])
    _,_,spec = load_specification(Path(reg["repository_root"]))
    for panel in reg["panels"]:
        root = Path(panel["prior_root"])
        if digest(root/"COMPLETE.json") != panel["prior_complete_hash"]:
            raise ValueError("Prior campaign completion changed")
        verify_file_map(root,panel["prior_files"])
        plan = panel["plan"]
        validate_frozen_protocol(plan,spec)
        if plan["source_hashes"] != reg["source_hashes"]:
            raise ValueError("Panel runtime differs from registration")
    return reg


def simulate_trial(data, plan, p, s, entry, output):
    recipe = VolumeConfig(**entry["configuration"])
    key = p["name"]+"_"+s[0]+"_"+recipe.name
    record = dict(key=key,period=p["name"],scenario=s[0],recipe=recipe.name,family=recipe.family,
        parent=entry["parent"],role=entry["role"],start=p["start"],end=p["end"],status="started",plan_hash=content_hash(plan))
    publish(output/(key+".started.json"),record)
    try:
        if source_hashes() != plan["source_hashes"]:
            raise ValueError("Source changed after registration")
        execution = ExecutionProfile(s[1],"0","0")
        cfg = RunConfig("100000",execution,recipe.universe,date.fromisoformat(p["start"]),date.fromisoformat(p["end"]),
                        actions_policy="allow_incomplete_diagnostic",execution_delay_sessions=s[2])
        source = build_volume_strategy(data,recipe,cfg.start,execution)
        result = run_backtest(data,source,cfg)
        bundle = output/"runs"/key;save_run(result,bundle);payload = verify_run(bundle)
        audit = audit_ledger(data,payload)
        verify_volume_signals(data,source,payload)
        _,rates = verified_cash_inputs(Path(plan["cash_path"]))
        rf = tuple(D(v["return"]) for v in cash_intervals(tuple(s.session for s in result.equity),rates))
        historical = sharpe(tuple(s.session_return-c for s,c in zip(result.equity,rf)))
        record.update(status="completed",bundle=str(bundle.resolve()),result_hash=content_hash(payload),
            metrics=primitive(summarize_run(result)),sharpe_historical_reference=None if historical is None else str(historical),
            annual=primitive(period_rows(result)))
        return record,dict(key=key,**audit),payload
    except (ValueError,ArithmeticError,OSError,KeyError,TypeError) as exc:
        record.update(status="failed",error_type=type(exc).__name__,error=str(exc))
        return record,None,None


def run_campaigns(output):
    registration = guard_registration(output)
    completed = []
    for panel in registration["panels"]:
        plan = panel["plan"];directory = output/panel["label"];directory.mkdir(exist_ok=False)
        data = load_snapshot(Path(plan["snapshot"]))
        readiness = json.loads(Path(plan["readiness_path"]).read_text())
        stock.verify_cache(Path(plan["snapshot"]),data,readiness)
        publish(directory/"EXPERIMENT_PLAN.json",plan);publish(directory/"DATA_READINESS.json",readiness)
        prior = json.loads((Path(panel["prior_campaign"])/"RESULTS.json").read_text())
        old = {r["key"]:r for r in prior["trials"]};trials, audits, payloads = [], [], {}
        for key,(p,s,entry) in stock.expected_panel(plan).items():
            if entry["role"] == "reference":
                record,audit = reuse_reference(data,plan,p,s,entry,old[key],directory)
                payload = verify_run(Path(record["bundle"]))
            else:
                record,audit,payload = simulate_trial(data,plan,p,s,entry,directory)
            publish(directory/(key+".completed.json"),record);trials.append(record)
            if audit:
                audits.append(audit)
            if payload:
                payloads[key] = payload
            print(json.dumps(dict(panel=panel["label"],trial=len(trials),of=54,key=key,status=record["status"],
                                  reused=entry["role"] == "reference",error=record.get("error"))),flush=True)
        stock.validate_trials(plan,trials)
        _,rates = verified_cash_inputs(Path(plan["cash_path"]))
        directions = direction_panel(plan,trials,payloads)
        decisions = volume_decisions(plan,trials,directions)
        publish(directory/"RESULTS.json",dict(plan_hash=content_hash(plan),trials=trials,decisions=decisions,
            direction_comparisons=directions,uncertainty=volume_uncertainty(plan,trials,rates,payloads),
            freeze_scope="Per-panel eligibility only; frozen artifacts require both samples",strategy_selected=False,fresh_final_test=False))
        publish(directory/"INDEPENDENT_LEDGER_AUDIT.json",dict(trials=audits))
        publish(directory/"DIAGNOSTICS.json",dict(plan_hash=content_hash(plan),details=stock.campaign_diagnostics(data,trials,rates),
            volume={r["key"]:volume_diagnostics(payloads[r["key"]]) for r in trials if r["role"] != "reference" and r["key"] in payloads}))
        completed.append((panel["label"],plan,directory,decisions))
    both_pass = freeze_for_both_samples({label:decisions for label,_,_,decisions in completed})
    for _,plan,directory,_ in completed:
        frozen = [e for e in plan["entries"] if e["role"] == "parent" and both_pass]
        publish(directory/"FROZEN_CANDIDATES.json",dict(plan_hash=content_hash(plan),entries=frozen,both_samples_pass=both_pass,production_nomination=False))
        publish(directory/"RETEST_REQUIREMENTS.json",stock.retest_requirements(plan,frozen))
        publish(directory/"EVIDENCE_HASHES.json",dict(files={p.name:digest(p) for p in directory.glob("*.json")}))


def verify_panel(directory, panel, both_pass):
    plan = json.loads((directory/"EXPERIMENT_PLAN.json").read_text())
    results = json.loads((directory/"RESULTS.json").read_text())
    if plan != panel["plan"] or results["plan_hash"] != content_hash(plan):
        raise ValueError("Campaign differs from registration")
    manifest = json.loads((directory/"EVIDENCE_HASHES.json").read_text())
    required = {"EXPERIMENT_PLAN.json","DATA_READINESS.json","RESULTS.json","INDEPENDENT_LEDGER_AUDIT.json",
                "DIAGNOSTICS.json","FROZEN_CANDIDATES.json","RETEST_REQUIREMENTS.json"}
    required.update(t["key"]+suffix for t in results["trials"] for suffix in (".started.json",".completed.json"))
    if set(manifest["files"]) != required:
        raise ValueError("Evidence registry incomplete")
    verify_file_map(directory,manifest["files"])
    data = load_snapshot(Path(plan["snapshot"]));readiness = json.loads((directory/"DATA_READINESS.json").read_text())
    if data.dataset_hash != plan["dataset_hash"] or digest(Path(plan["readiness_path"])) != plan["readiness_hash"]:
        raise ValueError("Registered dataset/readiness changed")
    if readiness != json.loads(Path(plan["readiness_path"]).read_text()):
        raise ValueError("Copied readiness changed")
    stock.verify_cache(Path(plan["snapshot"]),data,readiness)
    cashmeta,rates = verified_cash_inputs(Path(plan["cash_path"]))
    if cashmeta != plan["cash_source"]:
        raise ValueError("Cash provenance changed")
    stock.validate_trials(plan,results["trials"])
    prior = json.loads((Path(panel["prior_campaign"])/"RESULTS.json").read_text())
    old = {r["key"]:r for r in prior["trials"]};payloads, verified_audits, signal_audits = {}, [], {}
    registered = stock.expected_panel(plan)
    for row in results["trials"]:
        p,s,e = registered[row["key"]]
        started = dict(key=row["key"],period=p["name"],scenario=s[0],recipe=e["configuration"]["name"],
            family=e["configuration"]["family"],parent=e["parent"],role=e["role"],start=p["start"],end=p["end"],
            status="started",plan_hash=content_hash(plan))
        if json.loads((directory/(row["key"]+".started.json")).read_text()) != started or any(row.get(k) != v for k,v in started.items() if k != "status"):
            raise ValueError("Registered trial identity changed")
        if json.loads((directory/(row["key"]+".completed.json")).read_text()) != row:
            raise ValueError("Trial record changed")
        if e["role"] == "reference":
            before = old[row["key"]]
            expected = dict(before,plan_hash=content_hash(plan),bundle=str((directory/"runs"/row["key"]).resolve()),reused_from=before["bundle"])
            if row != expected or row["result_hash"] != panel["reference_result_hashes"][row["key"]]:
                raise ValueError("Reference origin/metrics changed")
        if row["status"] == "failed":
            continue
        if Path(row["bundle"]).resolve() != (directory/"runs"/row["key"]).resolve():
            raise ValueError("Unregistered bundle path")
        payload = verify_run(Path(row["bundle"]))
        execution = ExecutionProfile(s[1],"0","0")
        cfg = RunConfig("100000",execution,tuple(e["configuration"]["universe"]),date.fromisoformat(p["start"]),date.fromisoformat(p["end"]),
                        actions_policy="allow_incomplete_diagnostic",execution_delay_sessions=s[2])
        source = build_source(data,e,cfg.start,execution);model = saved_model(payload)
        if (content_hash(payload) != row["result_hash"] or payload["manifest"]["dataset_hash"] != plan["dataset_hash"] or
            payload["manifest"]["config"] != primitive(cfg) or payload["manifest"]["source"] != primitive(source.spec) or
            content_hash(summarize_run(model)) != content_hash(row["metrics"])):
            raise ValueError("Bundle configuration/result/metrics differs from registration")
        valid = e["role"] != "reference" or e["configuration"]["family"] == "cash" or (any(f.side == "buy" for f in model.fills) and not model.summary.rejected_order_count)
        if row["status"] != ("completed" if valid else "invalid_benchmark"):
            raise ValueError("Benchmark status disagrees with audited fills")
        verified_audits.append(dict(key=row["key"],**audit_ledger(data,payload)))
        if e["role"] != "reference":
            signal_audits[row["key"]] = verify_volume_signals(data,source,payload)
        rf = tuple(D(v["return"]) for v in cash_intervals(tuple(s.session for s in model.equity),rates))
        historical = sharpe(tuple(s.session_return-c for s,c in zip(model.equity,rf)))
        if row["sharpe_historical_reference"] != (None if historical is None else str(historical)) or row["annual"] != primitive(period_rows(model)):
            raise ValueError("Sharpe/annual metrics changed")
        payloads[row["key"]] = payload
    directions = direction_panel(plan,results["trials"],payloads)
    if results["direction_comparisons"] != directions or results["decisions"] != volume_decisions(plan,results["trials"],directions):
        raise ValueError("Decision/direction evidence changed")
    if results["uncertainty"] != volume_uncertainty(plan,results["trials"],rates,payloads):
        raise ValueError("Uncertainty changed")
    diagnostics = primitive(dict(plan_hash=content_hash(plan),details=stock.campaign_diagnostics(data,results["trials"],rates),
        volume={r["key"]:volume_diagnostics(payloads[r["key"]]) for r in results["trials"] if r["role"] != "reference" and r["key"] in payloads}))
    if json.loads((directory/"DIAGNOSTICS.json").read_text()) != diagnostics:
        raise ValueError("Diagnostics changed")
    expected = [e for e in plan["entries"] if e["role"] == "parent" and both_pass]
    if json.loads((directory/"FROZEN_CANDIDATES.json").read_text()) != dict(plan_hash=content_hash(plan),entries=expected,both_samples_pass=both_pass,production_nomination=False):
        raise ValueError("Frozen candidates changed")
    if json.loads((directory/"RETEST_REQUIREMENTS.json").read_text()) != stock.retest_requirements(plan,expected):
        raise ValueError("Retest requirements changed")
    if json.loads((directory/"INDEPENDENT_LEDGER_AUDIT.json").read_text())["trials"] != verified_audits or any(a["status"] != "passed" for a in verified_audits):
        raise ValueError("Independent ledger audit mismatch")
    return results,payloads,signal_audits


def verify_campaigns(output):
    registration = guard_registration(output);panels,overlaps = {}, {}
    both_pass = freeze_for_both_samples({p["label"]:json.loads((output/p["label"]/"RESULTS.json").read_text())["decisions"] for p in registration["panels"]})
    for panel in registration["panels"]:
        results,payloads,signals = verify_panel(output/panel["label"],panel,both_pass)
        if "recovery" in registration:
            original_root = Path(registration["recovery"]["root"])/panel["label"]
            original_results = json.loads((original_root/"RESULTS.json").read_text())
            original_rows = {r["key"]:r for r in original_results["trials"]}
            for row in results["trials"]:
                if row["role"] == "reference":
                    continue
                before = original_rows[row["key"]]
                origin = original_root/"runs"/row["key"]
                if (before["status"] != "failed" or before["error"] != "Volume order requests differ from causal rule replay" or
                        row.get("prior_failure") != before or row.get("recovered_from") != str(origin) or
                        content_hash(verify_run(origin)) != row["result_hash"]):
                    raise ValueError("Recovery changed saved financial outcomes/failure origins")
        old = json.loads((Path(panel["prior_campaign"])/"RESULTS.json").read_text())
        high = json.loads((Path(registration["high_root"])/panel["label"]/"RESULTS.json").read_text())
        comparisons = {}
        parent_key = "continuous_primary10_" + PARENT
        if parent_key in payloads:
            for name,previous in ((MOMENTUM,old),(HIGH,high)):
                row = next(r for r in previous["trials"] if r["key"] == "continuous_primary10_"+name)
                before = verify_run(Path(row["bundle"]))
                if content_hash(before) != row["result_hash"]:
                    raise ValueError("Overlap comparison input changed")
                comparisons[name] = overlap_diagnostics(payloads[parent_key],before)
        else:
            comparisons["status"] = "incomplete_parent"
        overlaps[panel["label"]] = comparisons
        panels[panel["label"]] = dict(decisions=results["decisions"],trial_count=len(results["trials"]),verified_bundles=len(payloads),
            failed_trials=[r["key"] for r in results["trials"] if r["status"] != "completed"],
            new_simulations=sum(r["role"] != "reference" for r in results["trials"]),references_reused=sum(r["role"] == "reference" for r in results["trials"]),
            causal_signal_audits=signals)
    return primitive(dict(panels=panels,overlap=overlaps,both_samples_pass=freeze_for_both_samples({k:p["decisions"] for k,p in panels.items()}),
                          qualified=False,independent_validation=False,fresh_final_test=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("register","run","verify"));parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if args.command == "register":
        register(args.output)
    elif args.command == "run":
        run_campaigns(args.output)
    else:
        result = verify_campaigns(args.output);publish(args.output/"VERIFICATION.json",result)
        print(json.dumps(dict(panels={k:{n:v for n,v in p.items() if n != "causal_signal_audits"} for k,p in result["panels"].items()},both_samples_pass=result["both_samples_pass"])),flush=True)


if __name__ == "__main__":
    main()
