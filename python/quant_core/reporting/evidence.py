"""The evidence pack of a registered study: every number, from the study's runs (docs/STRATEGY_EVIDENCE.md, Section 2).

`build_pack` returns plain values; the limitations page is generated from the data,
the registration and the results, never written after seeing them.
"""

from decimal import localcontext

from quant_core.analytics import CONTEXT, return_metrics
from quant_core.analytics.evidence import (
    bootstrap, correlation, deflated, holdings_overlap, periods, results, run_series,
)
from quant_core.strategies.plans import EqualWeightPlan, FixedWeightPlan, plan_to_dict
from quant_core.validation.study import planned_runs, references

SCHEMA_VERSION = 1
SENSITIVITY_ROLES = ("plan", "delay", "cash0", "shift", "neighbour")
SENSITIVITY_FIELDS = ("cagr", "sharpe", "max_drawdown", "annual_turnover")
NOT_PROMISED = (
    "Past results do not promise future results; the plan can lose money, for years at a time.",
    "Results are before taxes and before account fees other than the modelled trading costs.",
    "Orders are modelled as filled at the next session's open with an adverse cost; real fills differ.",
    "Orders are whole shares and all-or-nothing: a buy the cash cannot cover at the open waits a month, "
    "where a person would buy slightly fewer shares.",
    "Idle cash is assumed to earn the 3-month Treasury rate; a broker may pay less.",
)


def _bps(cost):
    return format(cost, "f")


def _percent(fraction):
    with localcontext(CONTEXT):
        return f"{(fraction * 100).normalize():f}%"


def _difference(a, b):
    if a is None or b is None:
        return None
    with localcontext(CONTEXT):
        return a - b


def holds(source, result):
    """What a comparison portfolio holds, in words, so a reader can tell what was beaten or not."""
    if source is None:
        return "Cash only, earning the 3-month Treasury rate"
    invested = source.invested_fraction
    with localcontext(CONTEXT):
        cash = _percent(1 - invested)
        if isinstance(source, FixedWeightPlan):
            parts = [f"{_percent(invested * weight)} {asset}"
                     for asset, weight in sorted(source.weights, key=lambda item: (-item[1], item[0]))]
            return f"Rebalanced at each month end to {', '.join(parts)} and {cash} cash"
    if isinstance(source, EqualWeightPlan):
        chosen = {}
        for decision in result.signal_decisions:
            chosen.setdefault(decision.session, set())
            if decision.selected:
                chosen[decision.session].add(decision.security_id)
        counts = [len(chosen[day]) for day in sorted(chosen)]
        picked = f"{counts[0]} at the first month end and {counts[-1]} at the last" if counts else "none"
        return (f"Equal weights over the plan's ETFs with enough history, {_percent(invested)} invested and "
                f"rebalanced at each month end; ETFs chosen: {picked}")
    return f"{', '.join(source.universe)} bought once with {_percent(invested)} of the capital and held; {cash} cash"


def limitations(registration, dataset, parent_periods):
    """The plain-language limitations page: data limits, losing years and falls, what is not promised."""
    firsts = {}
    for bar in dataset.snapshot.bars:
        if bar.security_id in registration.plan.universe:
            firsts[bar.security_id] = min(firsts.get(bar.security_id, bar.session), bar.session)
    return {"data": {"provider": dataset.snapshot.metadata.source, "dataset_id": registration.dataset_id,
                     "first_sessions": {asset: day.isoformat() for asset, day in sorted(firsts.items())},
                     "snapshot_limitations": list(dataset.snapshot.metadata.limitations),
                     "quality_warnings": dataset.manifest.get("quality_warnings", {})},
            "losing_years": {year: row["return"] for year, row in parent_periods["calendar_years"].items()
                             if row["return"] < 0},
            "largest_drawdowns": parent_periods["drawdowns"], "not_promised": list(NOT_PROMISED),
            "disclosures": list(registration.disclosures)}


def build_pack(registration, dataset, runs, earlier=None):
    """Every number of the pack from a study's runs, by key; `earlier` maps an earlier built-in's study name
    to the RunSeries of its parent at its primary cost."""
    primary = _bps(registration.primary_cost_bps)
    planned = {run.key: run for run in planned_runs(registration)}
    if set(runs) != set(planned):
        raise ValueError("The runs are not the registration's planned runs")
    series = {key: run_series(result) for key, result in runs.items()}
    rows = {key: results(result) for key, result in runs.items()}
    parent, main = series[f"plan-{primary}bps"], rows[f"plan-{primary}bps"]
    neighbours = [series[f"neighbour-{n.name}-{primary}bps"] for n in registration.neighbours]
    if any(n.sessions != parent.sessions for n in neighbours):
        raise ValueError("The parent and its neighbours must cover the same sessions")
    costs = [_bps(cost) for cost in registration.costs_bps]
    comparison = {name: {"sharpe_difference": _difference(main["sharpe"], rows[f"{name}-{primary}bps"]["sharpe"]),
                         "cagr_difference": _difference(main["cagr"], rows[f"{name}-{primary}bps"]["cagr"]),
                         "correlation": correlation(parent, series[f"{name}-{primary}bps"])}
                  for name in references(registration)}
    observed = {"annualized_return_252": return_metrics(parent.returns)["annualized_return_252"],
                "sharpe": main["sharpe"], "max_drawdown": main["max_drawdown"]}
    parent_periods = periods(parent, registration.publication, registration.segments)
    rates = dataset.rates
    return {
        "schema_version": SCHEMA_VERSION,
        "registration": {"study": registration.study, "role": registration.role, "tag": registration.tag,
                         "hash": registration.hash, "registered_at": registration.registered_at.isoformat(),
                         "dataset_id": registration.dataset_id, "code_hash": registration.code_hash,
                         "plan": plan_to_dict(registration.plan),
                         "primary_cost_bps": primary, "primary_reference": registration.primary_reference,
                         "trials": {"cumulative": registration.trials, "this_study": registration.trials_this_study,
                                    "per_role": registration.trials_per_role}},
        "results": {cost: rows[f"plan-{cost}bps"] for cost in costs},
        "references": {name: {"holds": holds(source, runs[f"{name}-{primary}bps"]),
                              **{suffix: rows[f"{name}-{suffix}"] for suffix in
                                 [f"{cost}bps" for cost in costs] + [f"{primary}bps-cash0"]}}
                       for name, source in references(registration).items()},
        "comparison": comparison,
        "uncertainty": {"observed": observed, "reference": registration.primary_reference,
                        **bootstrap(parent, series[f"{registration.primary_reference}-{primary}bps"],
                                    registration.block_lengths, registration.repetitions, registration.seed)},
        "deflated_sharpe": {**deflated(parent, neighbours, registration.trials, registration.historical_floor),
                            "per_role_trials": registration.trials_per_role},
        "periods": parent_periods,
        "sensitivity": {key: {"role": run.role, **{name: rows[key][name] for name in SENSITIVITY_FIELDS}}
                        for key, run in planned.items() if run.role in SENSITIVITY_ROLES},
        "cash": {"series": rates.series, "source": rates.source, "first": rates.observations[0][0].isoformat(),
                 "last": rates.observations[-1][0].isoformat(), "zero_cash": rows[f"plan-{primary}bps-cash0"]},
        "overlap": {study: {"correlation": correlation(parent, other),
                            "holdings_overlap": holdings_overlap(parent, other)}
                    for study, other in sorted((earlier or {}).items())},
        "limitations": limitations(registration, dataset, parent_periods),
        "reproduction": {"command": (f"python -m quant_core.validation.study run docs/registrations/"
                                     f"{registration.study}.json --dataset DATASET_DIRECTORY"
                                     f" --output local/studies/{registration.study}"),
                         "tag": registration.tag, "registration_hash": registration.hash,
                         "dataset_id": registration.dataset_id, "code_hash": registration.code_hash,
                         "runs": {key: runs[key].result_hash for key in planned}},
    }
