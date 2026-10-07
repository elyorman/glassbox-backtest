"""Pre-registered daily rule-strategy campaigns and separately gated final evaluation."""

from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
from statistics import median

from quant_core.analytics import CONTEXT, mean, paired_metrics, return_metrics, summarize_run
from quant_core.backtest.contracts import RunConfig
from quant_core.backtest.engine import _engine_hash, run_backtest
from quant_core.data import Snapshot
from quant_core.data.quality import check_quality
from quant_core.execution import ExecutionProfile
from quant_core.provenance import content_hash, primitive
from quant_core.reporting import save_run, verify_run
from quant_core.strategies import build_strategy
from quant_core.validation.contracts import CampaignSpec, Qualification, parse_qualification, parse_spec
from quant_core.validation.registry import Registry, publish, read_document
from quant_core.validation.statistics import fold_score_bootstrap, paired_bootstrap, search_diagnostic
from quant_core.validation.temporal import Period, period_sessions


def bounded_snapshot(snapshot, end):
    """Exclude all later prices/actions; retain one later known calendar session only."""
    days = tuple(d for d in snapshot.sessions if d <= end)
    next_days = tuple(d for d in snapshot.sessions if d > end)
    return replace(snapshot, sessions=days + next_days[:1],
                   bars=tuple(b for b in snapshot.bars if b.session <= end),
                   actions=tuple(a for a in snapshot.actions if a.session <= end))


def _check_data(snapshot, spec, qualification, phase="registration", original=None):
    if not isinstance(snapshot, Snapshot) or not isinstance(qualification, Qualification):
        raise ValueError("Need snapshot and qualification evidence")
    if qualification.dataset_hash != snapshot.dataset_hash or not qualification.passed:
        raise ValueError("Dataset qualification is unbound or has unresolved/failed capabilities")
    if not snapshot.metadata.actions_complete:
        raise ValueError("Complete corporate actions required; a declaration alone is not qualification")
    if spec.purpose == "engineering_fixture":
        if qualification.scope != "engineering_fixture":
            raise ValueError("Engineering campaigns require engineering qualification")
    elif qualification.scope == "engineering_fixture":
        raise ValueError("Synthetic qualification cannot authorize empirical research")
    if original is not None:
        if (qualification.scope != "independent_retest_fixed_sample"
                or qualification.independent_from != original or snapshot.dataset_hash == original):
            raise ValueError("Independent-retest evidence must bind a different dataset to the original")
    elif snapshot.dataset_hash != spec.dataset_hash:
        raise ValueError("Campaign dataset hash mismatch")
    recipes = spec.candidates + spec.benchmarks
    assets = {a for c in recipes for a in c.universe}
    registry = {s.security_id: s for s in snapshot.securities}
    if not assets <= set(registry):
        raise ValueError("Campaign references unknown securities")
    periods = spec.development_folds + (spec.selection, spec.holdout)
    for period in periods:
        if period.start not in snapshot.sessions or period.end not in snapshot.sessions:
            raise ValueError("All registered boundaries must be explicit calendar sessions")
    # Development folds cover a continuous portfolio, rather than independently funded pieces.
    for left, right in zip(spec.development_folds, spec.development_folds[1:]):
        if any(left.end < d < right.start for d in snapshot.sessions):
            raise ValueError("Development folds must cover consecutive supplied sessions")
    for period in (Period("development", spec.development_folds[0].start, spec.development_folds[-1].end),
                   spec.selection, spec.holdout):
        days = period_sessions(snapshot.sessions, period)
        if len(days) < spec.criteria.minimum_sessions or max(spec.bootstrap_blocks) > len(days):
            raise ValueError("Evaluation period is too short for registered sample/block requirements")
        index = snapshot.sessions.index(period.start)
        if index + 1 < max(c.required_history for c in recipes):
            raise ValueError("Common start lacks registered feature warmup")
        if any(not registry[a].active_on(period.start) for a in assets):
            raise ValueError("Fixed-sample instruments must be active at each evaluation start")
    end = spec.holdout.end if phase == "final" else spec.selection.end
    issues = tuple(i for i in check_quality(bounded_snapshot(snapshot, end)).issues
                   if i.security_id in assets and (i.session is None or i.session <= end))
    if any(i.severity == "error" for i in issues):
        raise ValueError("Data coverage errors block the campaign; no forward filling")
    return issues


def register_campaign(spec, snapshot, qualification, directory):
    if not isinstance(spec, CampaignSpec) or not isinstance(snapshot, Snapshot) or not isinstance(qualification, Qualification):
        raise ValueError("Need frozen CampaignSpec, Snapshot and Qualification")
    # Publish registration before data checks, so a failed qualification remains inspectable.
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    registry = Registry(directory)
    manifest = {"schema_version": 1, "campaign": spec, "qualification": qualification,
                "engine_hash": _engine_hash(), "calendar_hash": content_hash(snapshot.sessions),
                "trial_budget_per_phase": (len(spec.candidates) + len(spec.benchmarks)) * (len(spec.costs_bps) + 3),
                "assumptions": ("Fixed surviving sample; no historical index-membership claim",
                                "Cash yield and Sharpe reference rate zero; annualization 252 sessions",
                                "Development continuous portfolio; selection/final reset to cash",
                                "Gross is a separately simulated zero-cost diagnostic, not net plus costs",
                                "One extra session delay and half entry participation are diagnostic trials",
                                "Local integrity checks are not an OS sandbox or proof of provider/licensing claims")}
    publish(directory / "CAMPAIGN.json", {"hash": content_hash(manifest), "manifest": manifest})
    with registry.exclusive():
        registry.append("registered", {"manifest_hash": content_hash(manifest), "campaign_hash": spec.campaign_hash})
        try:
            issues = _check_data(snapshot, spec, qualification)
        except (ValueError, ArithmeticError) as exc:
            registry.append("qualification_failed", {"error": str(exc)})
            raise
        registry.append("qualification_passed", {"scope": qualification.scope, "issues": issues})
    return spec.campaign_hash


def open_campaign(directory, execution=True):
    registry = Registry(directory)
    envelope = read_document(registry.directory / "CAMPAIGN.json")
    if set(envelope) != {"hash", "manifest"} or content_hash(envelope["manifest"]) != envelope["hash"]:
        raise ValueError("Campaign manifest integrity mismatch")
    manifest = envelope["manifest"]
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported campaign schema")
    events = registry.events()
    if not events or events[0]["kind"] != "registered" or events[0]["payload"]["manifest_hash"] != envelope["hash"]:
        raise ValueError("Campaign manifest is not anchored in the registry")
    if execution and manifest["engine_hash"] != _engine_hash():
        raise ValueError("Runtime changed after registration; preserve this campaign and register a new research version")
    if not registry.has("qualification_passed"):
        raise ValueError("Campaign data qualification has not passed")
    return registry, parse_spec(manifest["campaign"]), parse_qualification(manifest["qualification"])


def _cost_scenario(cost):
    """Numeric identity for scenario keys without changing legacy content hashes."""
    text = format(cost, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"cost_{text}"


def _scenarios(spec):
    return (("gross_diagnostic", Decimal(0), 1, False),) + tuple(
        (_cost_scenario(cost), cost, 1, False) for cost in spec.costs_bps) + (
        ("delay_one_extra_session", spec.primary_cost_bps, 2, False),
        ("half_entry_participation", spec.primary_cost_bps, 1, True))


def _window_metrics(values):
    """Report windows from an already validated full portfolio return series."""
    if values and all(v is None for v in values):
        # The period begins with zero capital: its return is 0/0, not another -100%.
        metrics = dict.fromkeys(return_metrics((0,)))
        metrics.update(session_count=len(values), reason="zero_equity_at_period_start")
        return metrics
    return return_metrics(values)


def _trial(registry, spec, data, recipe, period, scenario):
    name, cost, delay, half = scenario
    cfg = replace(recipe, max_volume_participation=recipe.max_volume_participation / 2) if half else recipe
    execution = ExecutionProfile(cost)
    settings = RunConfig(spec.initial_cash, execution, cfg.universe, period.start, period.end,
                         execution_delay_sessions=delay)
    binding = {"recipe": cfg, "period": period, "scenario": name, "run_config": settings,
               "input_dataset_hash": data.dataset_hash}
    trial_id = content_hash(binding)
    location = "runs/" + trial_id
    registry.append("trial_started", {"trial_id": trial_id, "binding": binding, "path": location,
                                      "seed": spec.seed, "hypothesis": spec.hypothesis})
    try:
        view = bounded_snapshot(data, period.end)
        result = run_backtest(view, build_strategy(view, cfg, start=period.start, execution=execution), settings)
        if result.manifest.engine_hash != read_document(registry.directory / "CAMPAIGN.json")["manifest"]["engine_hash"]:
            raise ValueError("Runtime changed during the campaign; preserve failures and register a new version")
        save_run(result, registry.directory / location)
        metrics = summarize_run(result)
        status, reasons = "completed", []
        if recipe.family == "buy_hold" and not any(f.side == "buy" for f in result.fills):
            status, reasons = "invalid_benchmark", ["buy_hold_entry_did_not_fill"]
        if recipe in spec.benchmarks and result.summary.rejected_order_count:
            status, reasons = "invalid_benchmark", reasons + ["benchmark_order_rejected"]
        returns = tuple(s.session_return for s in result.equity)
        dates = tuple(s.session for s in result.equity)
        if any(r is None for r in returns):
            reasons.append("undefined_returns_after_complete_loss")
            if status == "completed":
                status = "undefined_returns"
        annual = {str(year): _window_metrics(tuple(r for d, r in zip(dates, returns) if d.year == year))
                  for year in sorted({d.year for d in dates})}
        folds = {fold.name: _window_metrics(tuple(r for d, r in zip(dates, returns) if fold.start <= d <= fold.end))
                 for fold in spec.development_folds} if period.name == "development" else {}
        row = {"trial_id": trial_id, "recipe": recipe.name, "family": recipe.family, "scenario": name,
               "period": period.name, "input_dataset_hash": data.dataset_hash,
               "status": status, "reasons": reasons, "run_path": location, "result_hash": result.result_hash,
               "metrics": metrics, "dates": dates, "returns": returns, "yearly": annual, "folds": folds}
        registry.append("trial_finished", {"trial_id": trial_id, "status": status, "result_hash": result.result_hash,
                                           "metrics": metrics, "reasons": reasons})
        return primitive(row)
    except Exception as exc:
        registry.append("trial_failed", {"trial_id": trial_id, "error": str(exc), "exception": type(exc).__name__})
        return {"trial_id": trial_id, "recipe": recipe.name, "family": recipe.family, "scenario": name,
                "period": period.name, "input_dataset_hash": data.dataset_hash,
                "status": "failed", "error": str(exc), "run_path": location}


def _comparison(spec, rows, period):
    table = {(row["recipe"], row["scenario"]): row for row in rows}
    comparisons, diagnostics, limitations = {}, {}, {}
    for cost in (spec.primary_cost_bps, spec.stressed_cost_bps):
        scenario = _cost_scenario(cost)
        benchmark = table[("same_universe_equal_weight", scenario)]
        complete = all(table[(c.name, scenario)]["status"] == "completed" for c in spec.candidates)
        if not complete or benchmark["status"] != "completed":
            limitations[scenario] = "Full registered search includes incomplete, invalid or undefined-return trials; no reduced-search statistic"
        if benchmark["status"] != "completed":
            continue
        b = tuple(Decimal(v) for v in benchmark["returns"])
        if complete:
            diagnostics[scenario] = tuple(search_diagnostic(
                tuple(table[(c.name, scenario)]["returns"] for c in spec.candidates), b,
                block, spec.bootstrap_repetitions, spec.seed) for block in spec.bootstrap_blocks)
        for cfg in spec.candidates:
            row = table[(cfg.name, scenario)]
            if row["status"] != "completed":
                continue
            if row["dates"] != benchmark["dates"]:
                raise ValueError("Comparison dates do not align")
            values = tuple(Decimal(v) for v in row["returns"])
            paired = paired_metrics(values, b)
            excess = tuple(x - y for x, y in zip(values, b))
            winners = sorted((i for i, v in enumerate(excess) if v > 0), key=lambda i: (-excess[i], i))[:spec.criteria.removed_winner_sessions]
            residual = tuple(Decimal(0) if i in winners else v for i, v in enumerate(excess))
            paired["mean_excess_without_largest_winner_sessions"] = mean(residual)
            paired["removed_winner_dates"] = tuple(row["dates"][i] for i in winners)
            paired["bootstrap"] = tuple(paired_bootstrap(values, b, block, spec.bootstrap_repetitions, spec.seed)
                                        for block in spec.bootstrap_blocks)
            fold_scores = []
            if period.name == "development":
                for fold in spec.development_folds:
                    indices = [i for i, day in enumerate(row["dates"]) if fold.start.isoformat() <= day <= fold.end.isoformat()]
                    fold_scores.append(paired_metrics(tuple(values[i] for i in indices), tuple(b[i] for i in indices))["sharpe_difference"])
                paired["fold_sharpe_differences"] = tuple(fold_scores)
                paired["median_fold_sharpe_difference"] = median(fold_scores) if all(v is not None for v in fold_scores) else None
            market = table[("broad_market_buy_hold", scenario)]
            paired["broad_market_comparison"] = paired_metrics(values, market["returns"]) if market["status"] == "completed" else None
            comparisons.setdefault(cfg.name, {})[scenario] = paired
    return {"candidate_comparisons": comparisons, "search_diagnostics": diagnostics,
            "search_diagnostic_limitations": limitations}


def run_phase(directory, snapshot, phase):
    if phase not in ("development", "selection"):
        raise ValueError("Only development/selection accepted; final requires the frozen-nominee gate")
    registry, spec, qualification = open_campaign(directory)
    _check_data(snapshot, spec, qualification)
    period = Period("development", spec.development_folds[0].start, spec.development_folds[-1].end) if phase == "development" else spec.selection
    with registry.exclusive(), localcontext(CONTEXT):
        if registry.has(f"{phase}_started"):
            raise ValueError("Phase already attempted; its outputs are consumed, including failures")
        if phase == "selection":
            development = registry.outcome("development")
            if development["status"] != "completed":
                raise ValueError("Complete development trials before exposing selection")
        registry.append(f"{phase}_started", {"period": period, "trial_budget": (len(spec.candidates) + 4) * len(_scenarios(spec))})
        rows = [_trial(registry, spec, snapshot, cfg, period, scenario)
                for scenario in _scenarios(spec) for cfg in spec.candidates + spec.benchmarks]
        failed = any(row["status"] != "completed" for row in rows)
        analysis_error = None
        try:
            comparison = _comparison(spec, rows, period)
        except Exception as exc:
            failed, analysis_error = True, str(exc)
            comparison = {"candidate_comparisons": {}, "search_diagnostics": {}}
            registry.append("phase_analysis_failed", {"phase": phase, "exception": type(exc).__name__, "error": str(exc)})
        report = {"schema_version": 1, "phase": phase, "campaign_hash": spec.campaign_hash,
                  "status": "incomplete" if failed else "completed", "period": period,
                  "trial_count": len(rows), "trials": rows, **comparison,
                  "analysis_error": analysis_error,
                  "interpretation": "Engineering evidence only" if spec.purpose == "engineering_fixture" else
                  "Exploratory/selection evidence; no final-performance or commercial qualification claim"}
        registry.save_outcome(phase, report)
        return primitive(report)


def _nomination(spec, development, selection):
    decisions = []
    all_trials = development["trials"] + selection["trials"]
    if development["status"] != "completed" or selection["status"] != "completed":
        return {"status": "inconclusive", "nominee": None, "decisions": [], "reasons": ["incomplete_or_invalid_trials"]}
    for cfg in spec.candidates:
        reasons, weak = [], []
        for scenario in (_cost_scenario(spec.primary_cost_bps), _cost_scenario(spec.stressed_cost_bps)):
            for report in (development, selection):
                paired = report["candidate_comparisons"][cfg.name][scenario]
                score = paired["sharpe_difference"]
                if score is None:
                    weak.append("undefined_sharpe")
                elif Decimal(score) <= 0:
                    reasons.append("nonpositive_sharpe_advantage")
                if Decimal(paired["mean_excess_without_largest_winner_sessions"]) <= 0:
                    reasons.append("advantage_depends_on_largest_winner_sessions")
                for bootstrap in paired["bootstrap"]:
                    low = bootstrap["sharpe_difference_95"][0]
                    if (low is None or Decimal(low) <= 0
                            or Decimal(bootstrap["defined_sharpe_replicates"]) / spec.bootstrap_repetitions < spec.criteria.minimum_defined_bootstrap_fraction):
                        weak.append("paired_uncertainty_unresolved")
                diagnostics = report["search_diagnostics"].get(scenario, ())
                if not diagnostics or any(Decimal(d["p_value"]) > spec.criteria.max_search_p_value for d in diagnostics):
                    weak.append("registered_search_diagnostic_unresolved")
                row = next(t for t in report["trials"] if t["recipe"] == cfg.name and t["scenario"] == scenario)
                if Decimal(row["metrics"]["max_drawdown"]) > spec.criteria.max_drawdown:
                    reasons.append("drawdown_budget_exceeded")
        primary = _cost_scenario(spec.primary_cost_bps)
        score = development["candidate_comparisons"][cfg.name][primary]["median_fold_sharpe_difference"]
        if score is None or Decimal(score) <= 0:
            reasons.append("development_fold_median_not_positive")
        family = [c for c in spec.candidates if c.family == cfg.family]
        positive = sum((development["candidate_comparisons"][c.name][primary]["sharpe_difference"] is not None
                        and Decimal(development["candidate_comparisons"][c.name][primary]["sharpe_difference"]) > 0) for c in family)
        if Decimal(positive) / len(family) < spec.criteria.family_positive_fraction:
            reasons.append("registered_parameter_family_unstable")
        for scenario in ("delay_one_extra_session", "half_entry_participation"):
            for report in (development, selection):
                row = next(t for t in report["trials"] if t["recipe"] == cfg.name and t["scenario"] == scenario)
                bench = next(t for t in report["trials"] if t["recipe"] == "same_universe_equal_weight" and t["scenario"] == scenario)
                metrics = paired_metrics(row["returns"], bench["returns"])
                if metrics["sharpe_difference"] is None or metrics["sharpe_difference"] <= 0:
                    reasons.append("delay_or_capacity_sensitivity_failed")
        if any(Decimal(t["metrics"]["max_drawdown"]) > spec.criteria.max_drawdown
               for t in all_trials if t["recipe"] == cfg.name and t["scenario"] != "gross_diagnostic"):
            reasons.append("drawdown_budget_exceeded")
        turnover = next(t for t in development["trials"] if t["recipe"] == cfg.name and t["scenario"] == primary)["metrics"]["notional_turnover"]
        status = "rejected" if reasons else "inconclusive" if weak else "eligible"
        decisions.append({"recipe": cfg.name, "status": status, "reasons": sorted(set(reasons + weak)),
                          "development_score": score, "development_turnover": turnover})
    eligible = [d for d in decisions if d["status"] == "eligible"]
    eligible.sort(key=lambda d: (-Decimal(d["development_score"]), Decimal(d["development_turnover"]), d["recipe"]))
    tie_comparisons, shortlist = [], eligible[:1]
    if len(eligible) > 1:
        primary = _cost_scenario(spec.primary_cost_bps)
        top = next(t for t in development["trials"] if t["recipe"] == eligible[0]["recipe"] and t["scenario"] == primary)
        benchmark = next(t for t in development["trials"] if t["recipe"] == "same_universe_equal_weight" and t["scenario"] == primary)
        for candidate in eligible[1:]:
            row = next(t for t in development["trials"] if t["recipe"] == candidate["recipe"] and t["scenario"] == primary)
            # Real reports always retain dates. Missing/short fixtures cannot resolve a tie.
            indices = tuple(tuple(i for i, day in enumerate(top.get("dates", ()))
                                  if fold.start.isoformat() <= day <= fold.end.isoformat()) for fold in spec.development_folds)
            uncertainty = []
            if all(indices) and min(map(len, indices)) >= max(spec.bootstrap_blocks):
                uncertainty = [fold_score_bootstrap(top["returns"], row["returns"], benchmark["returns"], indices,
                                                   block, spec.bootstrap_repetitions, spec.seed) for block in spec.bootstrap_blocks]
            resolved = bool(uncertainty) and all(
                b["median_fold_score_difference_95"][0] is not None
                and b["median_fold_score_difference_95"][0] > 0
                and Decimal(b["defined_replicates"]) / spec.bootstrap_repetitions >= spec.criteria.minimum_defined_bootstrap_fraction
                for b in uncertainty)
            tie_comparisons.append({"top": eligible[0]["recipe"], "challenger": candidate["recipe"],
                                    "top_advantage_resolved": resolved, "bootstrap": uncertainty})
            if not resolved:
                shortlist.append(candidate)
    families = {c.name: c.family for c in spec.candidates}
    complexity = {"trend": 0, "momentum": 1, "nearness_high": 1, "low_vol": 1, "reversal": 2}
    shortlist.sort(key=lambda d: (Decimal(d["development_turnover"]), complexity[families[d["recipe"]]], d["recipe"]))
    nominee = shortlist[0]["recipe"] if shortlist else None
    status = "nominated_for_independent_retest" if nominee else ("rejected" if all(d["status"] == "rejected" for d in decisions) else "inconclusive")
    if spec.purpose == "engineering_fixture":
        status, nominee = "engineering_only", None
    if spec.prior_holdout_use != "unexposed":
        status, nominee = "inconclusive", None
    return {"status": status, "nominee": nominee, "decisions": decisions,
            "reasons": ["prior_holdout_use_requires_new_unexposed_period"] if spec.prior_holdout_use != "unexposed" else [],
            "pairwise_development_tie_checks": tie_comparisons,
            "registered_trial_count": len(all_trials)}


def nominate(directory):
    registry, spec, _ = open_campaign(directory)
    with registry.exclusive(), localcontext(CONTEXT):
        if registry.has("nomination_decided"):
            raise ValueError("Nomination already decided; do not reselect on the same exposed periods")
        development, selection = registry.outcome("development"), registry.outcome("selection")
        outcome = _nomination(spec, development, selection)
        if registry.has("external_experiment"):
            outcome["status"], outcome["nominee"] = "inconclusive", None
            outcome["reasons"].append("additional_search_requires_a_new_registered_research_version")
        if registry.has("holdout_exposed"):
            outcome["status"], outcome["nominee"] = "inconclusive", None
            outcome["reasons"].append("holdout_exposure_recorded_requires_new_unexposed_period")
        frozen = {"schema_version": 1, "campaign_hash": spec.campaign_hash, "engine_hash": _engine_hash(),
                  "development_report_hash": content_hash(development), "selection_report_hash": content_hash(selection),
                  "nomination": outcome, "holdout": spec.holdout,
                  "recipe": next((c for c in spec.candidates if c.name == outcome["nominee"]), None)}
        publish(registry.directory / "FREEZE.json", {"hash": content_hash(frozen), "frozen": frozen})
        registry.append("nomination_decided", {"freeze_hash": content_hash(frozen), "decision": outcome})
        return primitive(outcome)


def _freeze(registry, spec):
    if registry.has("holdout_exposed"):
        raise ValueError("Holdout exposure recorded; final period cannot supply fresh evidence")
    envelope = read_document(registry.directory / "FREEZE.json")
    if set(envelope) != {"hash", "frozen"} or content_hash(envelope["frozen"]) != envelope["hash"]:
        raise ValueError("Freeze integrity mismatch")
    frozen = envelope["frozen"]
    matches = [e for e in registry.events() if e["kind"] == "nomination_decided"]
    if (len(matches) != 1 or matches[0]["payload"]["freeze_hash"] != envelope["hash"]
            or frozen["campaign_hash"] != spec.campaign_hash or frozen["engine_hash"] != _engine_hash()):
        raise ValueError("Freeze binding mismatch")
    if frozen["nomination"]["status"] != "nominated_for_independent_retest" or frozen["recipe"] is None:
        raise ValueError("No eligible frozen nominee; final period remains locked")
    # Check phase hashes as well, preserving the selection history behind the freeze.
    if (content_hash(registry.outcome("development")) != frozen["development_report_hash"]
            or content_hash(registry.outcome("selection")) != frozen["selection_report_hash"]):
        raise ValueError("Frozen evidence changed")
    return frozen


def crosscheck(directory, independent, qualification):
    registry, spec, _ = open_campaign(directory)
    _check_data(independent, spec, qualification, original=spec.dataset_hash)
    with registry.exclusive(), localcontext(CONTEXT):
        frozen = _freeze(registry, spec)
        if registry.has("crosscheck_started"):
            raise ValueError("Independent crosscheck already attempted")
        nominee = next(c for c in spec.candidates if c.name == frozen["nomination"]["nominee"])
        registry.append("crosscheck_started", {"dataset_hash": independent.dataset_hash, "qualification": qualification,
                                               "freeze_hash": content_hash(frozen)})
        differences, rows, reports = [], [], []
        for phase in ("development", "selection"):
            period = Period("development", spec.development_folds[0].start, spec.development_folds[-1].end) if phase == "development" else spec.selection
            original = registry.outcome(phase)
            phase_rows = []
            for scenario in _scenarios(spec):
                for cfg in (nominee,) + spec.benchmarks:
                    row = _trial(registry, spec, independent, cfg, period, scenario)
                    rows.append(row)
                    phase_rows.append(row)
                    old = next(t for t in original["trials"] if t["recipe"] == cfg.name and t["scenario"] == scenario[0])
                    if row["status"] != "completed" or row["dates"] != old["dates"]:
                        differences.append({"phase": phase, "recipe": cfg.name, "scenario": scenario[0], "passed": False,
                                            "reason": "failed_trial_or_calendar_mismatch"})
                        continue
                    delta = abs(Decimal(row["metrics"]["total_return"]) - Decimal(old["metrics"]["total_return"]))
                    daily = max(abs(Decimal(a) - Decimal(b)) for a, b in zip(row["returns"], old["returns"]))
                    differences.append({"phase": phase, "recipe": cfg.name, "scenario": scenario[0],
                                        "total_return_difference": delta, "maximum_daily_difference": daily,
                                        "passed": delta <= spec.criteria.max_cross_provider_return_difference
                                        and daily <= spec.criteria.max_cross_provider_daily_difference})
            reports.append({"status": "completed" if all(t["status"] == "completed" for t in phase_rows) else "incomplete",
                            "trials": phase_rows, **_comparison(replace(spec, candidates=(nominee,)), phase_rows, period)})
        retained = _nomination(replace(spec, candidates=(nominee,)), reports[0], reports[1])
        report = {"schema_version": 1, "phase": "crosscheck", "freeze_hash": content_hash(frozen),
                  "independent_dataset_hash": independent.dataset_hash, "qualification": qualification,
                  "status": "passed" if all(d["passed"] for d in differences) and retained["nominee"] == nominee.name else "failed",
                  "search_context": {
                      "original_candidates": [c.name for c in spec.candidates],
                      "original_registered_trial_count": frozen["nomination"]["registered_trial_count"],
                      "original_development_report_hash": frozen["development_report_hash"],
                      "original_selection_report_hash": frozen["selection_report_hash"],
                      "original_selection_bound": True,
                      "retested_candidates": [nominee.name], "full_search_repeated": False,
                      "interpretation": "Nominee-only provider diagnostic over exposed history; "
                                        "not a repeat of the original multiple-candidate search."},
                  "independent_evidence_retention": retained, "phase_comparisons": reports,
                  "differences": differences, "trials": rows,
                  "interpretation": "Provider robustness check over exposed dates, not a new historical holdout"}
        registry.save_outcome("crosscheck", report)
        return primitive(report)


def run_final(directory, original, independent):
    registry, spec, original_qualification = open_campaign(directory)
    with registry.exclusive(), localcontext(CONTEXT):
        frozen = _freeze(registry, spec)
        checked = registry.outcome("crosscheck")
        if checked["status"] != "passed" or checked["freeze_hash"] != content_hash(frozen):
            raise ValueError("Independent-data crosscheck did not pass; final period remains locked")
        qualification = parse_qualification(checked["qualification"])
        if independent.dataset_hash != checked["independent_dataset_hash"]:
            raise ValueError("Final dataset differs from the reviewed independent snapshot")
        _check_data(original, spec, original_qualification, "final")
        _check_data(independent, spec, qualification, "final", spec.dataset_hash)
        if registry.has("final_consumed"):
            raise ValueError("Final period already consumed; no second tournament")
        nominee = next(c for c in spec.candidates if c.name == frozen["nomination"]["nominee"])
        # Mark consumed BEFORE any execution, including crashes and failed trials.
        registry.append("final_consumed", {"freeze_hash": content_hash(frozen), "period": spec.holdout,
                                           "datasets": (original.dataset_hash, independent.dataset_hash)})
        providers = []
        for data in (original, independent):
            rows = [_trial(registry, spec, data, cfg, spec.holdout, scenario)
                    for scenario in _scenarios(spec) for cfg in (nominee,) + spec.benchmarks]
            providers.append({"dataset_hash": data.dataset_hash, "trials": rows,
                              **_comparison(replace(spec, candidates=(nominee,)), rows, spec.holdout),
                              "status": "completed" if all(t["status"] == "completed" for t in rows) else "incomplete"})
        report = {"schema_version": 1, "phase": "final", "freeze_hash": content_hash(frozen), "providers": providers,
                  "status": "completed" if all(p["status"] == "completed" for p in providers) else "incomplete",
                  "interpretation": "Final period consumed. No automatic shipping decision; provider runs are not independent market histories."}
        registry.save_outcome("final", report)
        return primitive(report)


def verify_campaign(directory):
    registry, spec, _ = open_campaign(directory, execution=False)
    verified = 0
    events = registry.events()
    for event in events:
        if event["kind"] == "trial_finished":
            payload = event["payload"]
            starts = [e["payload"] for e in events if e["kind"] == "trial_started"
                      and e["payload"]["trial_id"] == payload["trial_id"]]
            if len(starts) != 1:
                raise ValueError("Trial lifecycle mismatch")
            result = verify_run(registry.directory / starts[0]["path"])
            if content_hash(result) != payload["result_hash"]:
                raise ValueError("Trial result differs from registry")
            verified += 1
        elif event["kind"] == "phase_complete":
            registry.outcome(event["payload"]["phase"])
    for event in events:
        if event["kind"] == "nomination_decided":
            envelope = read_document(registry.directory / "FREEZE.json")
            if (content_hash(envelope["frozen"]) != envelope["hash"]
                    or envelope["hash"] != event["payload"]["freeze_hash"]):
                raise ValueError("Freeze integrity mismatch")
    return {"campaign_hash": spec.campaign_hash, "event_count": len(events),
            "verified_run_count": verified, "final_consumed": registry.has("final_consumed"),
            "external_holdout_exposure": registry.has("holdout_exposed")}
