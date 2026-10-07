"""Compare the ten existing recipes on cached data without tuning or nomination.

Preserves the original ten-year window and a mechanically chosen common-warmup
window. The latter is primary for comparisons, with all declared cost/delay
scenarios. Old matching ten-year bundles are verified and reused, never replaced.
"""

import argparse
import base64
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import hashlib
from html import escape
import json
import os
from pathlib import Path

from quant_core.analytics import summarize_run
from quant_core.backtest import RunConfig, run_backtest
from quant_core.data.storage import load_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import canonical_json, content_hash, primitive
from quant_core.reporting import save_run, verify_run
from quant_core.strategies import build_strategy, initial_recipes, benchmark_recipes, rebalance_dates
from quant_core.validation.statistics import search_diagnostic, paired_bootstrap
from research.market_backtest import START, END, SYMBOLS, WarmupDistributionStrategy, publish, saved_model, period_rows
from research.market_report import audit, percent, write_csv, LABELS


SCENARIOS = (("primary10", "10", 1), ("cost5", "5", 1), ("stress25", "25", 1), ("delay10", "10", 2))
REFERENCE = "broad_market_buy_hold_reserve"


def common_start(snapshot, candidates):
    """First month-end with full common history; only calendar/config access."""
    required = max(recipe.required_history for recipe in candidates)
    if len(snapshot.sessions) < required:
        raise ValueError("Not enough common feature history")
    ready = max(START, snapshot.sessions[required - 1])
    options = [d for d in rebalance_dates(snapshot.sessions, "month_end") if ready <= d < END]
    if not options:
        raise ValueError("No common warmed rebalance session")
    return options[0]


def valid_benchmark(recipe, result):
    if recipe.purpose != "benchmark" or recipe.family == "cash":
        return True
    return bool(any(f.side == "buy" for f in result.fills)) and not result.summary.rejected_order_count


def rank_candidates(trials):
    valid = [r for r in trials if r["window"] == "common_warmup" and r["scenario"] == "primary10"
             and r["purpose"] == "research_candidate" and r["status"] == "completed"]
    # Undefined Sharpe comes last; historical ranking is not a production choice.
    return sorted(valid, key=lambda r: (r["metrics"]["sharpe"] is None,
        -Decimal(r["metrics"]["sharpe"] or 0), -Decimal(r["metrics"]["cagr_calendar"]), r["recipe"]))


def source_hashes():
    package = Path(__file__).resolve().parents[1]
    files = list((package / "quant_core").rglob("*.py")) + [
        package / "research" / name for name in ("compare_strategies.py", "market_backtest.py", "market_report.py")]
    return {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def run(snapshot, old_root, output):
    candidates = initial_recipes(SYMBOLS[:-1])
    references = benchmark_recipes(SYMBOLS[:-1], "SPY")
    recipes = candidates + references
    warmed = common_start(snapshot, candidates)
    windows = (("common_warmup", warmed, SCENARIOS), ("ten_year", START, SCENARIOS[:1]))
    output.mkdir(parents=True, exist_ok=False)
    plan = {"purpose": "private_exploratory_all_ten_recipe_comparison", "dataset_hash": snapshot.dataset_hash,
        "recipes": recipes, "initial_cash": "100000", "end": END, "windows": windows,
        "primary_window": "common_warmup", "primary_scenario": "primary10",
        "common_start_rule": "First monthly rebalance session after max required-history calendar readiness",
        "candidate_budget": 10, "trial_budget": 70, "parameters_tuned": False, "risk_policy": None,
        "prior_exposure": "Canonical momentum and benchmark results for 2016-2026 already inspected",
        "fresh_final_test": False, "production_nomination": False,
        "sort_rule": "Common-warmup primary Sharpe descending, then CAGR descending, then recipe ID",
        "benchmark_priority": REFERENCE, "bootstrap_blocks": (20, 60), "bootstrap_repetitions": 500,
        "bootstrap_seed": 1729, "paired_intervals": "Conditional on highest descriptive Sharpe, not selection-corrected",
        "search_test": "Joint centered maximum mean daily excess across all ten, not a Sharpe test or DSR",
        "source_hashes": source_hashes(), "data_limitations": snapshot.metadata.limitations,
        "original_experiment_plan_hash": content_hash(json.loads((old_root / "EXPERIMENT_PLAN.json").read_text()))}
    publish(output / "EXPERIMENT_PLAN.json", plan)
    recipe_folder = output / "recipes"
    recipe_folder.mkdir()
    for recipe in recipes:
        publish(recipe_folder / (recipe.name + ".json"), {"schema_version": 1, "configuration": recipe})
    trials, returns, audits = [], {}, []
    for window, start, scenarios in windows:
        for scenario, cost, delay in scenarios:
            execution = ExecutionProfile(cost, "0", "0")
            for recipe in recipes:
                key = window + "_" + scenario + "_" + recipe.name
                record = {"window": window, "scenario": scenario, "recipe": recipe.name, "family": recipe.family,
                          "purpose": recipe.purpose, "start": start, "end": END,
                          "plan_hash": content_hash(plan), "status": "started"}
                publish(output / (key + ".started.json"), record)
                try:
                    if source_hashes() != plan["source_hashes"]:
                        raise ValueError("Source changed after experiment registration")
                    config = RunConfig("100000", execution, recipe.universe, start, END,
                                       execution_delay_sessions=delay)
                    source = WarmupDistributionStrategy(build_strategy(snapshot, recipe, start, execution))
                    prior = old_root / "runs" / scenario / recipe.name
                    if window == "ten_year" and prior.exists():
                        payload = verify_run(prior)
                        manifest = payload["manifest"]
                        if (manifest["dataset_hash"] != snapshot.dataset_hash or
                            manifest["config"] != primitive(config) or manifest["source"] != primitive(source.spec)):
                            raise ValueError("Prior run differs from frozen dataset/configuration/source")
                        result = saved_model(payload)
                        record["bundle"] = str(prior.resolve())
                        record["reused_existing_bundle"] = True
                    else:
                        result = run_backtest(snapshot, source, config)
                        folder = output / "runs" / window / scenario / recipe.name
                        save_run(result, folder)
                        payload = verify_run(folder)
                        if content_hash(payload) != result.result_hash:
                            raise ValueError("Saved bundle hash mismatch")
                        record["bundle"] = str(folder.resolve())
                        record["reused_existing_bundle"] = False
                    independent = audit(snapshot, payload)
                    audits.append({"trial": key, **independent})
                    metrics = summarize_run(result)
                    record.update(status="completed" if valid_benchmark(recipe, result) else "invalid_benchmark",
                                  result_hash=content_hash(payload), summary=payload["summary"], metrics=metrics,
                                  annual=period_rows(result),
                                  first_fill=min((f.execution_date for f in result.fills), default=None))
                    returns[window, scenario, recipe.name] = tuple(s.session_return for s in result.equity)
                except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
                    record.update(status="failed", error=str(exc))
                publish(output / (key + ".completed.json"), record)
                trials.append(record)
                print(canonical_json({"trial": len(trials), "of": 70, "window": window, "scenario": scenario,
                    "recipe": recipe.name, "status": record["status"], "error": record.get("error")}), flush=True)
    publish(output / "INDEPENDENT_LEDGER_AUDIT.json", {"dataset_hash": snapshot.dataset_hash, "trials": audits})
    publish(output / "TRIAL_RESULTS.json", {"plan_hash": content_hash(plan), "trials": trials})
    ranked = rank_candidates(trials)
    inference = {"status": "incomplete", "note": "No promotion; these dates were already exposed"}
    reference_record = next(r for r in trials if r["window"] == "common_warmup" and
                            r["scenario"] == "primary10" and r["recipe"] == REFERENCE)
    if len(ranked) == 10 and reference_record["status"] == "completed":
        baseline = returns["common_warmup", "primary10", REFERENCE]
        panel = [returns["common_warmup", "primary10", r.name] for r in candidates]
        leader = ranked[0]["recipe"]
        inference = {"status": "descriptive_diagnostics_only", "benchmark": REFERENCE,
            "highest_historical_sharpe": leader, "selection_corrected_sharpe_interval": False,
            "search": [], "conditional_paired_intervals": [],
            "note": "Joint search diagnostic does not restore an untouched holdout or validate provider data"}
        for block in plan["bootstrap_blocks"]:
            print(canonical_json({"diagnostic": "bootstrap", "block_sessions": block}), flush=True)
            inference["search"].append(search_diagnostic(panel, baseline, block, 500, 1729))
            inference["conditional_paired_intervals"].append(paired_bootstrap(
                returns["common_warmup", "primary10", leader], baseline, block, 500, 1729))
    publish(output / "DIAGNOSTICS.json", inference)
    publish(output / "RESULTS.json", {"plan_hash": content_hash(plan), "trials": trials,
        "descriptive_ranking": [r["recipe"] for r in ranked], "diagnostics": inference,
        "fresh_final_test": False, "strategy_selected": False})
    print(canonical_json({"completed": len(trials), "statuses": dict(Counter(r["status"] for r in trials)),
                          "common_start": warmed, "ranking": [r["recipe"] for r in ranked]}), flush=True)


def label(recipe):
    return LABELS.get(recipe, recipe.replace("_", " "))


def report(snapshot, output):
    os.environ.setdefault("MPLCONFIGDIR", str(output / "matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    results = json.loads((output / "RESULTS.json").read_text())
    plan = json.loads((output / "EXPERIMENT_PLAN.json").read_text())
    if results["plan_hash"] != content_hash(plan) or snapshot.dataset_hash != plan["dataset_hash"]:
        raise ValueError("Comparison report input hash mismatch")
    trials = results["trials"]
    ranked = rank_candidates(trials)
    rows, years, verified = [], [], 0
    for trial in trials:
        row = {k: trial.get(k) for k in ("window", "scenario", "recipe", "family", "status", "first_fill")}
        if trial["status"] != "failed":
            payload = verify_run(Path(trial["bundle"]))
            if content_hash(payload) != trial["result_hash"]:
                raise ValueError("Comparison bundle changed")
            verified += 1
            metrics = trial["metrics"]
            duration = Decimal(metrics["calendar_days_inclusive"]) / Decimal("365.2425")
            row.update(final_equity_usd=trial["summary"]["final_equity"],
                cagr_calendar=metrics["cagr_calendar"], max_drawdown=metrics["max_drawdown"],
                sharpe=metrics["sharpe"], sortino=metrics["sortino"],
                turnover_per_calendar_year=Decimal(metrics["notional_turnover"]) / duration,
                average_gross_exposure=metrics["average_gross_exposure"],
                fill_count=metrics["fill_count"], rejected_orders=metrics["rejected_orders"],
                slippage_usd=metrics["slippage"], result_hash=trial["result_hash"])
            if trial["window"] == "common_warmup" and trial["scenario"] == "primary10":
                for year, values in trial["annual"].items():
                    years.append({"recipe": trial["recipe"], "year": year, "partial_year": year in ("2017", "2026"),
                                  "return": values["total_return"] if trial["status"] == "completed" else None,
                                  "max_drawdown_within_year": values["max_drawdown"] if trial["status"] == "completed" else None})
        rows.append(row)
    # Failures keep the same columns and remain visible in exports.
    headers = list(dict.fromkeys(k for row in rows for k in row))
    write_csv(output / "comparison.csv", [{k: row.get(k) for k in headers} for row in rows])
    if years:
        write_csv(output / "annual.csv", years)
    primary = {r["recipe"]: r for r in trials if r["window"] == "common_warmup" and r["scenario"] == "primary10"}
    candidates = [r for r in plan["recipes"] if r["purpose"] == "research_candidate"]
    for kind in ("equity", "drawdown"):
        fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout="constrained")
        for axis, family in zip(axes.flat, ("trend", "momentum", "nearness_high", "reversal")):
            names = [r["name"] for r in candidates if r["family"] == family] + [REFERENCE]
            for name in names:
                trial = primary[name]
                if trial["status"] != "completed":
                    continue
                payload = verify_run(Path(trial["bundle"]))
                states = payload["equity"]
                dates = [date.fromisoformat(s["session"]) for s in states]
                values = [float(s["equity"]) if kind == "equity" else -100 * float(s["drawdown"]) for s in states]
                axis.plot(dates, values, label=label(name), linewidth=1.3,
                          **({"color": "black", "linestyle": "--"} if name == REFERENCE else {}))
            axis.set_title(family.replace("_", " "))
            axis.set_xlabel("Trading session date (New York)")
            axis.set_ylabel("Portfolio equity (USD)" if kind == "equity" else "Drawdown from peak (%)")
            if kind == "equity":
                axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value/1000:,.0f}k"))
            axis.grid(alpha=0.2)
            axis.legend(fontsize=8)
        fig.suptitle("All predefined strategies | Common warmup start | $100,000 | 10 bps per side")
        for extension in ("png", "pdf"):
            fig.savefig(output / (kind + "." + extension), dpi=140)
        plt.close(fig)
    html_rows = []
    for row in rows:
        valid = row["status"] == "completed"
        html_rows.append('<tr data-window="' + row['window'] + '" data-scenario="' + row['scenario'] + '"><td>' +
            escape(label(row['recipe'])) + '</td><td>' + row['status'] + '</td><td>' +
            (f"${Decimal(row['final_equity_usd']):,.0f}" if valid else 'N/A') + '</td><td>' +
            (percent(row['cagr_calendar']) if valid else 'N/A') + '</td><td>' +
            (percent(row['max_drawdown']) if valid else 'N/A') + '</td><td>' +
            (f"{Decimal(row['sharpe']):.2f}" if valid and row.get('sharpe') is not None else 'N/A') + '</td><td>' +
            (f"{Decimal(row['turnover_per_calendar_year']):.2f}x" if valid else 'N/A') + '</td><td>' +
            (percent(row['average_gross_exposure']) if valid else 'N/A') + '</td></tr>')
    diagnostics = results['diagnostics']
    diagnostic_text = escape(json.dumps(diagnostics, indent=2))
    pictures = ''.join('<img alt="' + name + ' comparison by strategy family" src="data:image/png;base64,' +
                       base64.b64encode((output / (name + '.png')).read_bytes()).decode() + '">' for name in ('equity', 'drawdown'))
    ranking_text = ', '.join(escape(label(r['recipe'])) for r in ranked)
    annual_html = []
    for year in sorted({r['year'] for r in years}):
        values = {r['recipe']: r['return'] for r in years if r['year'] == year}
        annual_html.append('<tr><td>'+year+(' (partial)' if year in ('2017','2026') else '')+'</td>'+''.join(
            '<td>'+percent(values.get(r['name']))+'</td>' for r in plan['recipes'])+'</tr>')
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>All strategy comparison</title>
<style>body{font:15px system-ui;color:#18293b;max-width:1300px;margin:35px auto;padding:0 18px}p,li{line-height:1.65}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}td,th{padding:9px;border-bottom:1px solid #dbe2e8;text-align:left}th{background:#edf2f7}img{width:100%}.scroll{overflow-x:auto}.note{padding:16px;background:#edf2f7}select{padding:8px;margin:8px}pre{white-space:pre-wrap}</style>
<h1>Comparison of all ten predefined strategies</h1><p class="note">Private exploratory research on previously inspected dates. No tuning, production nomination, or fresh out-of-sample claim. Charts use the common-warmup window; the table also retains the original ten-year window.</p>
<p>All candidates use the same nine ETFs, 95% invested slots, $100,000 starting cash, zero cash yield, whole-share orders, raw next-open execution and issuer dividends/splits. Protective stop-risk variants and ML are outside this comparison. Common-warmup accounting starts ''' + str(plan['windows'][0][1]) + ''' and ends 2026-10-02. Monthly strategies first enter February 1, 2017; weekly reversal enters on its next weekly rebalance. The full ten-year accounting window starts October 3, 2016 and has different recipe warmups.</p>
<h2>All retained trials</h2><label>Window<select id="window"><option value="common_warmup">Common warmup (primary)</option><option value="ten_year">Original ten-year (10 bps only)</option></select></label><label>Costs / timing<select id="scenario"><option value="primary10">10 bps / next open</option><option value="cost5">5 bps / next open</option><option value="stress25">25 bps / next open</option><option value="delay10">10 bps / second open</option></select></label>
<table id="comparison"><thead><tr><th>Strategy / reference</th><th>Status</th><th>End equity (USD)</th><th>CAGR (%/year)</th><th>Max drawdown (%)</th><th>Sharpe (0% reference)</th><th>Turnover (times/year)</th><th>Avg gross exposure (%)</th></tr></thead><tbody>''' + ''.join(html_rows) + '''</tbody></table>
<h2>Family comparisons</h2>''' + pictures + '''<h2>Calendar-year returns, common-warmup primary</h2><div class="scroll"><table><thead><tr><th>Year</th>''' + ''.join('<th>'+escape(label(r['name']))+'</th>' for r in plan['recipes']) + '''</tr></thead><tbody>''' + ''.join(annual_html) + '''</tbody></table></div>
<h2>Historical ranking and uncertainty</h2><p>Descriptive primary Sharpe ranking: ''' + ranking_text + '''. This is a ranking of observed history, not a selected deployable strategy. Searching ten variants increases the chance of an impressive historical result.</p><p>Joint stationary-block resampling compares the maximum mean daily excess across all ten with the predeclared 5%-reserve SPY reference. This is a maximum-mean diagnostic, not a Sharpe test or DSR. Paired intervals for the highest historical Sharpe are conditional on that selection and do not correct its selection bias. Neither calculation restores an untouched holdout.</p><details><summary>Recorded bootstrap diagnostics</summary><pre>''' + diagnostic_text + '''</pre></details>
<h2>Assumptions and evidence</h2><ul><li>All failures and invalid references remain in the export. A rejected full-budget SPY entry is labelled invalid, not treated as market performance; no start date or share quantity is changed to repair it. SPY buys once and retains dividend cash, rather than continuously reinvesting it. Its cash fraction therefore drifts.</li>
<li>The source snapshot and recipe parameters are unchanged from the earlier experiment. The XLF September 2016 non-cash distribution remains a disclosed signal-only warmup valuation approximation. Calendar/open semantics, historical revisions, split completeness and independent-provider qualification remain unresolved.</li>
<li>Annual figures are slices of continuous portfolios, not yearly resets. 2017 and 2026 are partial in the common-start window. Risk controls are the existing scheduled allocation/liquidity rules; no protective stops were introduced.</li>
<li>Previously inspected 2016–2026 dates, including the proposed 2024–2026 holdout, remain exposed. There is no fresh final test or production nominee.</li></ul><p>Verified bundles: ''' + str(verified) + '''. Every trial has an independent cash/share/receivable/equity and fill-timing/price audit. Existing compatible ten-year bundles are verified and reused; new bundles preserve their own source/runtime hashes.</p>
<p>Dataset SHA-256: <code>''' + plan['dataset_hash'] + '''</code></p><p>Plan SHA-256: <code>''' + results['plan_hash'] + '''</code></p><p><a href="comparison.csv">All trials CSV</a> · <a href="annual.csv">Annual CSV</a> · <a href="equity.pdf">Equity PDF</a> · <a href="drawdown.pdf">Drawdown PDF</a> · <a href="DIAGNOSTICS.json">Diagnostics</a> · <a href="INDEPENDENT_LEDGER_AUDIT.json">Independent audit</a></p>
<script>let w=document.getElementById('window'),s=document.getElementById('scenario');function filter(){if(w.value==='ten_year'){s.value='primary10';s.disabled=true}else{s.disabled=false}document.querySelectorAll('#comparison tbody tr').forEach(r=>r.hidden=r.dataset.window!==w.value||r.dataset.scenario!==s.value)}w.addEventListener('change',filter);s.addEventListener('change',filter);filter();</script></html>'''
    with (output / "REPORT.html").open("x") as stream:
        stream.write(html)
    names = ("EXPERIMENT_PLAN.json", "TRIAL_RESULTS.json", "RESULTS.json", "DIAGNOSTICS.json", "INDEPENDENT_LEDGER_AUDIT.json",
             "comparison.csv", "annual.csv", "equity.png", "equity.pdf", "drawdown.png", "drawdown.pdf", "REPORT.html")
    publish(output / "REPORT_HASHES.json", {"files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in names}})
    print(canonical_json({"verified_bundles": verified, "report": str(output / "REPORT.html")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "report"))
    parser.add_argument("--snapshot", type=Path, default=Path("local/market-backtest-2026-10-03/market.snapshot.json"))
    parser.add_argument("--prior", type=Path, default=Path("local/market-backtest-2026-10-03"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = load_snapshot(args.snapshot)
    if args.command == "run":
        run(snapshot, args.prior, args.output)
    else:
        report(snapshot, args.output)


if __name__ == "__main__":
    main()
