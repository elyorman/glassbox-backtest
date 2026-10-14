"""The evidence pack of a registered study: every number, from the study's runs (docs/STRATEGY_EVIDENCE.md, Section 2).

`build_pack` returns plain values; the limitations page is generated from the data,
the registration and the results, never written after seeing them.
"""

from decimal import Decimal, localcontext
import json
from pathlib import Path

from quant_core.analytics import CONTEXT, return_metrics
from quant_core.analytics.evidence import (
    bootstrap, correlation, deflated, holdings_overlap, periods, results, run_series,
)
from quant_core.provenance import content_hash, primitive
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


def _label(planned, primary):
    if planned.role == "plan":
        return f"Parent at {_bps(planned.cost_bps)} bps"
    if planned.role == "delay":
        return f"Fills at the second open ({primary} bps)"
    if planned.role == "cash0":
        return f"Idle cash at 0%, ratios against 0% ({primary} bps)"
    if planned.role == "shift":
        return f"Decisions {planned.source.decision_offset:+d} sessions from month end ({primary} bps)"
    return f"Neighbour {planned.source.name} ({primary} bps)"


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
        "sensitivity": {key: {"role": run.role, "label": _label(run, primary),
                              **{name: rows[key][name] for name in SENSITIVITY_FIELDS}}
                        for key, run in planned.items() if run.role in SENSITIVITY_ROLES},
        "cash": {"series": rates.series, "source": rates.source, "first": rates.observations[0][0].isoformat(),
                 "last": rates.observations[-1][0].isoformat(), "zero_cash": rows[f"plan-{primary}bps-cash0"]},
        "overlap": {study: {"correlation": correlation(parent, other),
                            "holdings_overlap": holdings_overlap(parent, other)}
                    for study, other in sorted((earlier or {}).items())},
        "limitations": limitations(registration, dataset, parent_periods),
        "reproduction": {"command": (f"python -m quant_core.validation.study_cli run docs/registrations/"
                                     f"{registration.study}.json --dataset DATASET_DIRECTORY"
                                     f" --output local/{registration.study}"),
                         "tag": registration.tag, "registration_hash": registration.hash,
                         "dataset_id": registration.dataset_id, "code_hash": registration.code_hash,
                         "runs": {key: runs[key].result_hash for key in planned}},
    }


def _fixed(value, places):
    if value is None:
        return "n/a"
    with localcontext(CONTEXT):
        text = format(Decimal(value).quantize(Decimal(1).scaleb(-places)), "f")
    return text.lstrip("-") if Decimal(text) == 0 else text  # Never "-0.00".


def _pct(value):
    if value is None:
        return "n/a"
    with localcontext(CONTEXT):
        return f"{_fixed(Decimal(value) * 100, 2)}%"


def _interval(pair, show):
    return "n/a" if None in pair else f"{show(pair[0])} to {show(pair[1])}"


def _table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    return lines + ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]


def _period_rows(rows):
    return [(name, "no sessions", "", "", "", "", "") if row is None else
            (name, row["first_session"], row["last_session"], row["sessions"], _pct(row["return"]),
             _pct(row["max_drawdown"]), _fixed(row["sharpe"], 2)) for name, row in rows]


def _bullets(items, empty):
    return [f"- {item}" for item in items] or [f"- {empty}"]


def render_pack(pack):
    """PACK.md: the pack for reading. Every number comes from `pack`, which pack.json holds in full."""
    registration, trials = pack["registration"], pack["registration"]["trials"]
    primary, reference = registration["primary_cost_bps"], registration["primary_reference"]
    period_header = ("Period", "First session", "Last session", "Sessions", "Return", "Max drawdown", "Sharpe")
    lines = [f"# Evidence pack: {registration['study']}", "", f"{registration['role']}.", "",
             f"- Registered: {registration['registered_at']}, tag `{registration['tag']}`",
             f"- Registration hash: `{registration['hash']}`",
             f"- Dataset ID: `{registration['dataset_id']}`", f"- Code hash: `{registration['code_hash']}`",
             f"- Trials: {trials['cumulative']} cumulative, {trials['this_study']} in this study, "
             f"{trials['per_role']} for this role",
             f"- Costs: slippage in basis points of each fill; primary {primary} bps; primary reference "
             f"{reference}", "",
             "Sharpe and Sortino ratios use daily returns over T-bills; volatility and drawdowns use daily "
             "returns. Formulas: docs/VALIDATION.md, \"Evidence metrics\".", "", "## Results", ""]
    lines += _table(("Cost (bps)", "First session", "Last session", "CAGR", "Volatility", "Sharpe", "Sortino",
                     "Max drawdown", "Calmar", "Turnover a year", "Trades"),
                    [(cost, row["first_session"], row["last_session"], _pct(row["cagr"]), _pct(row["volatility"]),
                      _fixed(row["sharpe"], 2), _fixed(row["sortino"], 2), _pct(row["max_drawdown"]),
                      _fixed(row["calmar"], 2), _pct(row["annual_turnover"]), row["trades"])
                     for cost, row in pack["results"].items()])
    lines += ["", "Turnover is the value traded in a year as a share of equity."]
    lines += [""] + _table(("Cost (bps)", "Average invested", "Longest underwater (sessions)",
                            "Whole-share shortfalls", "Opening-gap rejections", "Interest income (USD)"),
                           [(cost, _pct(row["average_gross_exposure"]), row["longest_underwater_sessions"],
                             row["whole_share_shortfalls"], row["opening_gap_rejections"],
                             _fixed(row["interest_income"], 2)) for cost, row in pack["results"].items()])
    lines += ["", "## Comparison portfolios", "",
              "Each runs on the same sessions with the same costs and idle-cash interest as the plan."]
    lines += [""] + _table(("Portfolio", "What it holds"),
                           [(name, values["holds"]) for name, values in pack["references"].items()])
    lines += [""] + _table(("Portfolio", "Run", "CAGR", "Sharpe", "Max drawdown", "Turnover a year"),
                           [(name, run, _pct(row["cagr"]), _fixed(row["sharpe"], 2), _pct(row["max_drawdown"]),
                             _pct(row["annual_turnover"]))
                            for name, values in pack["references"].items()
                            for run, row in values.items() if run != "holds"])
    lines += ["", "Runs ending in cash0 earn 0% on idle cash and measure ratios against 0%.", "",
              f"The plan minus each portfolio at {primary} bps:", ""]
    lines += _table(("Portfolio", "Sharpe difference", "CAGR difference", "Correlation of daily excess returns"),
                    [(name, _fixed(row["sharpe_difference"], 2), _pct(row["cagr_difference"]),
                      _fixed(row["correlation"], 2)) for name, row in pack["comparison"].items()])
    uncertainty = pack["uncertainty"]
    observed = uncertainty["observed"]
    lines += ["", "## Uncertainty", "",
              f"Observed at {primary} bps: annualized return over 252 sessions "
              f"{_pct(observed['annualized_return_252'])}, Sharpe {_fixed(observed['sharpe'], 2)}, "
              f"maximum drawdown {_pct(observed['max_drawdown'])}.", "",
              f"Stationary bootstrap, {uncertainty['repetitions']} repetitions, seed {uncertainty['seed']}; 95% "
              f"intervals at the nearest-rank 2.5th and 97.5th percentiles. The Sharpe difference resamples the "
              f"same sessions of the plan and {uncertainty['reference']}.", ""]
    lines += _table(("Mean block (sessions)", "Annualized return", "Sharpe", "Max drawdown",
                     f"Sharpe minus {uncertainty['reference']}", "Replicates with a Sharpe"),
                    [(block, _interval(row["annualized_return_252"], _pct), _interval(row["sharpe"],
                      lambda value: _fixed(value, 2)), _interval(row["max_drawdown"], _pct),
                      "n/a" if row["sharpe_minus_reference"] is None
                      else _interval(row["sharpe_minus_reference"], lambda value: _fixed(value, 2)),
                      row["defined_sharpe_replicates"]) for block, row in uncertainty["blocks"].items()])
    deflation = pack["deflated_sharpe"]
    lines += ["", "## Deflated Sharpe ratio", "",
              f"Over {deflation['trials']} cumulative trials ({deflation['per_role_trials']} for this role). V is "
              "the variance of per-session Sharpe ratios across trials: this study's own (the parent and its "
              "neighbours) or the historical floor. The primary figure uses the larger.", ""]
    lines += _table(("V", "Variance", "Expected maximum Sharpe (per session)", "z", "Deflated Sharpe ratio"),
                    [(name, _fixed(row["sharpe_variance"], 6), _fixed(row["expected_maximum_sharpe"], 4),
                      _fixed(row["z"], 2), _fixed(row["deflated_sharpe_ratio"], 4))
                     for name, row in (("Primary (larger)", deflation["primary"]),
                                       ("Alternative (smaller)", deflation["alternative"]))])
    moments = deflation["primary"]
    lines += ["", f"This study's own V {_fixed(deflation['own_variance'], 6)}; historical floor "
              f"{_fixed(deflation['floor_variance'], 6)}. Per-session Sharpe {_fixed(moments['sharpe'], 4)} over "
              f"{moments['observations']} sessions, skewness {_fixed(moments['skewness'], 2)}, kurtosis "
              f"{_fixed(moments['kurtosis'], 2)} (raw; normal is 3).", "", "## Periods", "", "### Calendar years", ""]
    found = pack["periods"]
    lines += _table(period_header, _period_rows(found["calendar_years"].items()))
    lines += ["", "### Predeclared windows, since publication and segments", ""]
    lines += _table(period_header, _period_rows(list(found["windows"].items())
                                                + [("Since publication", found["since_publication"])]
                                                + list(found["segments"].items())))
    lines += ["", "### Best and worst twelve months", ""]
    if found["twelve_months"] is None:
        lines.append("The run is shorter than twelve months.")
    else:
        lines += _table(("", "Start", "End", "Return"),
                        [(name.capitalize(), row["start"], row["end"], _pct(row["return"]))
                         for name, row in found["twelve_months"].items()])
    lines += ["", "### Largest drawdowns", ""]
    lines += _table(("Depth", "Peak", "Trough", "Recovery", "Sessions to trough", "Sessions to recovery"),
                    [(_pct(row["depth"]), row["peak_session"] or "start", row["trough_session"],
                      row["recovery_session"] or "not recovered", row["sessions_to_trough"],
                      "n/a" if row["sessions_to_recovery"] is None else row["sessions_to_recovery"])
                     for row in found["drawdowns"]] or [("None", "", "", "", "", "")])
    lines += ["", "## Sensitivity", ""]
    lines += _table(("Run", "CAGR", "Sharpe", "Max drawdown", "Turnover a year"),
                    [(row["label"], _pct(row["cagr"]), _fixed(row["sharpe"], 2), _pct(row["max_drawdown"]),
                      _pct(row["annual_turnover"])) for row in pack["sensitivity"].values()])
    cash = pack["cash"]
    lines += ["", "## Cash", "",
              f"Idle cash earns simple ACT/365 interest at the last {cash['series']} rate ({cash['source']}) "
              f"observed before each holding period; observations run {cash['first']} to {cash['last']}. With "
              f"idle cash at 0% and ratios against 0%: CAGR "
              f"{_pct(cash['zero_cash']['cagr'])}, Sharpe {_fixed(cash['zero_cash']['sharpe'], 2)}.", "",
              "## Overlap with earlier built-ins", ""]
    lines += _table(("Study", "Correlation of daily excess returns", "Holdings overlap"),
                    [(study, _fixed(row["correlation"], 2), _pct(row["holdings_overlap"]))
                     for study, row in pack["overlap"].items()]) if pack["overlap"] else ["No earlier built-in."]
    limits = pack["limitations"]
    data = limits["data"]
    lines += ["", "## Limitations", "", "### Data", "",
              f"Provider {data['provider']}, dataset `{data['dataset_id']}`. First session of each ETF:", ""]
    lines += _table(("ETF", "First session"), list(data["first_sessions"].items()))
    lines += ["", "Snapshot limitations:"] + _bullets(data["snapshot_limitations"], "None recorded.")
    lines += ["", "Quality warnings:"] + _bullets([f"{code}: {count}" for code, count in
                                                   sorted(data["quality_warnings"].items())], "None.")
    lines += ["", "### Losing calendar years", ""] + _bullets(
        [f"{year}: {_pct(value)}" for year, value in limits["losing_years"].items()], "None.")
    lines += ["", "### Largest drawdowns", ""] + _bullets(
        [f"{_pct(row['depth'])} from {row['peak_session'] or 'the start'} to {row['trough_session']}, "
         + (f"recovered {row['recovery_session']}" if row["recovery_session"] else "not recovered")
         for row in limits["largest_drawdowns"]], "None.")
    lines += ["", "### What the plan does not promise", ""] + _bullets(limits["not_promised"], "")
    lines += ["", "### Disclosures", ""] + _bullets(limits["disclosures"], "None.")
    reproduction = pack["reproduction"]
    lines += ["", "## Reproduction", "", f"Check out `{reproduction['tag']}`, then:", "", "```",
              reproduction["command"], "```", "",
              f"Registration hash `{reproduction['registration_hash']}`, dataset ID `{reproduction['dataset_id']}`,"
              f" code hash `{reproduction['code_hash']}`. Result hash of each run:", ""]
    lines += _table(("Run", "Result hash"), [(key, f"`{value}`") for key, value in reproduction["runs"].items()])
    return "\n".join(lines) + "\n"


def write_pack(pack, directory):
    """Write pack.json and PACK.md into a study's output directory, never replacing either; returns the
    pack's content hash."""
    directory = Path(directory)
    for name, text in (("pack.json", json.dumps(primitive(pack), indent=2, sort_keys=True, allow_nan=False) + "\n"),
                       ("PACK.md", render_pack(pack))):
        with open(directory / name, "x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    return content_hash(pack)
