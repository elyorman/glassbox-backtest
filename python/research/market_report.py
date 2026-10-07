"""Verify saved exploratory ledgers independently; export charts and local HTML.

Matplotlib is an optional research dependency, never a core runtime dependency.
The report does not simulate, tune, nominate, or contact data providers.
"""

import argparse
import base64
from collections import defaultdict
from datetime import date
from decimal import Decimal, Context, ROUND_HALF_EVEN, localcontext
import csv
import hashlib
from html import escape
import json
import os
from pathlib import Path

from quant_core.analytics import return_metrics
from quant_core.data import Dividend, Split
from quant_core.data.storage import load_snapshot
from quant_core.provenance import canonical_json, content_hash
from quant_core.reporting import verify_run


LABELS = {"momentum_252_skip21_top3": "Momentum 252 / skip 21 / top 3",
          "broad_market_buy_hold": "SPY buy & hold",
          "broad_market_buy_hold_reserve": "SPY buy & hold, 5% reserve",
          "same_universe_equal_weight": "Equal-weight sectors, monthly",
          "cash_control": "Cash (0% yield)"}


def audit(snapshot, run):
    """Rebuild cash, shares and receivables using raw closes and saved fills.

    No portfolio, engine, or reported position/valuation functions are used.
    Checks every session; separately checks next-open timing and fill prices.
    """
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        config = run["manifest"]["config"]
        cash, holdings, pending = Decimal(config["initial_cash"]), defaultdict(Decimal), []
        bars = {(b.session, b.security_id): b for b in snapshot.bars}
        indices = {day: i for i, day in enumerate(snapshot.sessions)}
        events, fills = defaultdict(list), defaultdict(list)
        for event in snapshot.actions:
            events[event.session].append(event)
        for fill in run["fills"]:
            fills[date.fromisoformat(fill["execution_date"])].append(fill)
        count = 0
        for state in run["equity"]:
            day = date.fromisoformat(state["session"])
            # Splits precede same-date dividend entitlements.
            for event in events[day]:
                if isinstance(event, Split):
                    holdings[event.security_id] *= event.ratio
            for event in events[day]:
                if isinstance(event, Dividend):
                    amount = holdings[event.security_id] * event.amount
                    pending.append((event.pay_date, amount))
            cash += sum((amount for payment, amount in pending if payment <= day), Decimal(0))
            pending = [(payment, amount) for payment, amount in pending if payment > day]
            for fill in fills[day]:
                asset, qty, price = fill["security_id"], Decimal(fill["quantity"]), Decimal(fill["price"])
                sign = Decimal(1) if fill["side"] == "buy" else Decimal(-1)
                expected_price = bars[day, asset].open * (1 + sign * Decimal(config["execution"]["slippage_bps"]) / 10000)
                if price != expected_price or Decimal(fill["notional"]) != qty * price:
                    raise ArithmeticError("Fill-price/notional audit failed")
                signal = date.fromisoformat(fill["signal_date"])
                if indices[day] - indices[signal] != config["execution_delay_sessions"]:
                    raise ArithmeticError("Next-open timing audit failed")
                holdings[asset] += sign * qty
                cash -= sign * qty * price + Decimal(fill["fees"])
            receivable = sum((amount for _, amount in pending), Decimal(0))
            market = sum((qty * bars[day, asset].close for asset, qty in holdings.items() if qty), Decimal(0))
            equity = cash + receivable + market
            tolerance = max(Decimal("1e-18"), abs(equity) * Decimal("1e-24"))
            for observed, expected in ((state["cash"], cash), (state["receivables"], receivable),
                                       (state["market_value"], market), (state["equity"], equity)):
                if abs(Decimal(observed) - expected) > tolerance:
                    raise ArithmeticError(f"Independent ledger audit failed on {day}")
            count += 1
        return {"sessions_checked": count, "fills_checked": len(run["fills"]), "status": "passed"}


def percent(value):
    return "N/A" if value is None else f"{Decimal(value) * 100:,.2f}%"


def write_csv(path, rows):
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    os.environ.setdefault("MPLCONFIGDIR", str(root / "matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    results = json.loads((root / "RESULTS.json").read_text())
    plan = json.loads((root / "EXPERIMENT_PLAN.json").read_text())
    snapshot = load_snapshot(root / "market.snapshot.json")
    if content_hash(plan) != results["plan_hash"] or snapshot.dataset_hash != plan["dataset_hash"]:
        raise ValueError("Report provenance does not match the frozen inputs")
    audits, primary, summaries, annual, monthly = [], {}, [], [], []
    for trial in results["trials"]:
        folder = root / "runs" / trial["scenario"] / trial["recipe"]
        run = verify_run(folder)
        if content_hash(run) != trial["result_hash"]:
            raise ValueError("Trial result hash mismatch")
        audits.append({"scenario": trial["scenario"], "recipe": trial["recipe"], **audit(snapshot, run)})
        metrics = trial["metrics"]
        summaries.append({"scenario": trial["scenario"], "recipe": trial["recipe"], "status": trial["status"],
                          "final_equity_usd": trial["summary"]["final_equity"],
                          "total_return": metrics["total_return"], "cagr_calendar": metrics["cagr_calendar"],
                          "max_drawdown": metrics["max_drawdown"], "sharpe_zero_reference": metrics["sharpe"],
                          "first_fill": trial["first_fill"], "fill_count": metrics["fill_count"],
                          "slippage_usd": metrics["slippage"], "result_hash": trial["result_hash"]})
        if trial["scenario"] == "primary10":
            primary[trial["recipe"]] = run
            for year, values in trial["annual"].items():
                annual.append({"recipe": trial["recipe"], "year": year,
                               "total_return": values["total_return"], "max_drawdown_within_year": values["max_drawdown"],
                               "partial_year": year in ("2016", "2026")})
            groups = defaultdict(list)
            for state in run["equity"]:
                groups[state["session"][:7]].append(Decimal(state["session_return"]))
            for month, values in sorted(groups.items()):
                monthly.append({"recipe": trial["recipe"], "month": month,
                                "total_return": return_metrics(values)["total_return"]})
    write_csv(root / "comparison.csv", summaries)
    write_csv(root / "annual.csv", annual)
    write_csv(root / "monthly.csv", monthly)
    with (root / "INDEPENDENT_LEDGER_AUDIT.json").open("x") as stream:
        stream.write(canonical_json({"dataset_hash": snapshot.dataset_hash, "trials": audits}) + "\n")

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, layout="constrained",
                             gridspec_kw={"height_ratios": [2, 1]})
    for name, run in primary.items():
        if name == "cash_control":
            continue
        dates = [date.fromisoformat(s["session"]) for s in run["equity"]]
        axes[0].plot(dates, [float(s["equity"]) for s in run["equity"]], label=LABELS[name], linewidth=1.4)
        axes[1].plot(dates, [-float(s["drawdown"]) * 100 for s in run["equity"]], linewidth=1.1)
    axes[0].set_ylabel("Portfolio equity (USD)")
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1000:,.0f}k"))
    axes[0].set_title("Ten-year exploratory backtest | $100,000 start | 10 bps per traded side")
    axes[0].legend(loc="upper left", fontsize=9)
    axes[1].set_ylabel("Drawdown from peak (%)")
    axes[1].set_xlabel("Trading session date (New York)")
    for ax in axes:
        ax.grid(alpha=0.2)
    axes[0].axvspan(date(2016, 10, 3), date(2017, 2, 1), color="grey", alpha=0.12)
    fig.savefig(root / "equity_drawdown.png", dpi=160)
    fig.savefig(root / "equity_drawdown.pdf")
    plt.close(fig)
    image = base64.b64encode((root / "equity_drawdown.png").read_bytes()).decode()
    body_rows = []
    for row in summaries:
        body_rows.append('<tr data-scenario="' + row["scenario"] + '"><td>' + row["scenario"] + '</td><td>' +
                         escape(LABELS[row["recipe"]]) + '</td><td>' + row["status"] + '</td><td>$' +
                         f'{Decimal(row["final_equity_usd"]):,.0f}' + '</td><td>' + percent(row["cagr_calendar"]) +
                         '</td><td>' + percent(row["max_drawdown"]) + '</td><td>' +
                         (f'{Decimal(row["sharpe_zero_reference"]):.2f}' if row["sharpe_zero_reference"] else 'N/A') + '</td></tr>')
    year_rows = []
    for year in sorted({r["year"] for r in annual}):
        values = {r["recipe"]: r["total_return"] for r in annual if r["year"] == year}
        year_rows.append('<tr><td>' + year + (' (partial)' if year in ('2016', '2026') else '') + '</td>' +
                         ''.join('<td>' + percent(values[name]) + '</td>' for name in LABELS if name != 'cash_control') + '</tr>')
    findings = ("The fixed momentum recipe beat the monthly equal-weight sector reference, but trailed both SPY references "
                "over the full period at the predeclared 10 bps primary cost. It has not established a robust market-beating edge. "
                "No recipe, date, or cost assumption was tuned after observing these results.")
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ten-year strategy research</title><style>body{font:16px system-ui;max-width:1150px;margin:40px auto;padding:0 20px;color:#172338}h1{font-size:30px}p,li{line-height:1.6}table{border-collapse:collapse;width:100%;font-size:14px;margin:20px 0}td,th{padding:10px;border-bottom:1px solid #dde3ea;text-align:left}th{background:#eff3f7}img{width:100%}.note{background:#f4f6f8;padding:16px}select{padding:8px}</style>
<h1>Ten-year private strategy research</h1><p>October 3, 2016–October 2, 2026 · USD 100,000 · Fixed nine-sector ETF universe · No fitted ML model</p>
<p class="note">''' + findings + '''</p><img alt="Equity in USD and drawdown in percent across trading session dates" src="data:image/png;base64,''' + image + '''">
<h2>Results and execution sensitivity</h2><label>Scenario <select id="scenario"><option value="primary10">Primary: 10 bps / next open</option><option value="cost5">5 bps / next open</option><option value="stress25">25 bps / next open</option><option value="delay10">10 bps / second open</option><option value="all">All declared trials</option></select></label>
<table id="results"><thead><tr><th>Scenario</th><th>Rule / reference</th><th>Status</th><th>End equity (USD)</th><th>CAGR (%/year)</th><th>Max drawdown (%)</th><th>Sharpe (0% reference)</th></tr></thead><tbody>''' + ''.join(body_rows) + '''</tbody></table>
<h2>Actual portfolio calendar-year returns</h2><table><thead><tr><th>Year</th>''' + ''.join('<th>' + escape(v) + '</th>' for k,v in LABELS.items() if k != 'cash_control') + '''</tr></thead><tbody>''' + ''.join(year_rows) + '''</tbody></table>
<h2>Interpretation and audit</h2><ul><li>Momentum ranks the trailing 252-session total-return signal, excluding the latest 21 sessions, holds the top three with 95% invested, and rebalances at month-end for next-open execution. It first enters on February 1, 2017; earlier months stay in cash because pre-2016 history is unavailable.</li>
<li>SPY references buy once at the start and retain dividend cash; they are not a continuously dividend-reinvested index. The reserve reference starts with approximately 5% cash; its cash fraction changes afterward. Sector equal weight rebalances monthly and first enters November 1, 2016. These initialization differences are visible, not erased.</li>
<li>All 20 bundles pass file-integrity verification and independent session-by-session cash/share/receivable/equity audits against raw closes, plus fill-price and execution-delay checks. The 5 bps full-budget SPY order was rejected for insufficient cash after an opening gap. Its all-cash outcome is retained as an invalid benchmark and must not be interpreted as SPY performance.</li>
<li>Issuer records replaced missing/inconsistent vendor dividends and payment dates. The XLF September 2016 non-cash XLRE distribution uses the issuer's historical $4.5292 tax valuation as a disclosed signal-only warmup approximation, not a cash payment. No simulated holding crosses that distribution.</li>
<li>The first saved simulation was recovered after fixing analytics handling of zero-dollar audit actions outside its trading universe. RECOVERY.json records the reporting failure and change; its simulation was not rerun.</li>
<li>This is an exploratory full-period diagnostic, not a gated validation campaign or production nomination. Inspection exposes the previously reserved 2024–2026 dates; future selection cannot claim those dates as untouched. Independent-provider retesting remains required.</li></ul>
<details><summary>Dataset limitations and provenance</summary><ul>''' + ''.join('<li>'+escape(s)+'</li>' for s in plan['limitations']) + '''</ul><p>Dataset SHA-256: <code>''' + plan['dataset_hash'] + '''</code></p><p>Plan SHA-256: <code>''' + results['plan_hash'] + '''</code></p></details>
<p><a href="comparison.csv">All trials CSV</a> · <a href="annual.csv">Annual returns CSV</a> · <a href="monthly.csv">Monthly returns CSV</a> · <a href="equity_drawdown.pdf">Chart PDF</a> · <a href="INDEPENDENT_LEDGER_AUDIT.json">Independent audit</a></p>
<script>const select=document.getElementById('scenario');function filter(){document.querySelectorAll('#results tbody tr').forEach(r=>r.hidden=select.value!=='all'&&r.dataset.scenario!==select.value)}select.addEventListener('change',filter);filter();</script></html>'''
    with (root / "REPORT.html").open("x") as stream:
        stream.write(html)
    names = ("comparison.csv", "annual.csv", "monthly.csv", "equity_drawdown.png", "equity_drawdown.pdf",
             "REPORT.html", "INDEPENDENT_LEDGER_AUDIT.json", "RESULTS.json", "EXPERIMENT_PLAN.json", "RECOVERY.json", "DATA_REVIEW.json")
    with (root / "REPORT_HASHES.json").open("x") as stream:
        stream.write(canonical_json({"files": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}}) + "\n")
    print(canonical_json({"verified_bundles": len(audits), "audited_sessions": sum(a['sessions_checked'] for a in audits),
                          "audited_fills": sum(a['fills_checked'] for a in audits), "report": str(root / "REPORT.html")}))


if __name__ == "__main__":
    main()
