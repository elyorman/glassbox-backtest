"""Standalone exports from a frozen robustness audit; never simulates/tunes."""

import base64
from collections import defaultdict
from datetime import date
from decimal import Decimal
import hashlib
from html import escape
import json
import os
from pathlib import Path

from quant_core.data.storage import load_snapshot
from quant_core.provenance import content_hash, primitive
from quant_core.reporting import verify_run
from quant_core.analytics import summarize_run
from quant_core.backtest import RunConfig
from quant_core.execution import ExecutionProfile
from quant_core.risk import RiskPolicy
from research.market_report import write_csv, percent
from research.robustness_audit import PARENTS, REFERENCES, verified_cash_inputs, source_hashes, decisions
from research.market_backtest import saved_model
from research import robustness_metrics as rm


def seal_evidence(output, names):
    manifest = {'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in sorted(names)}}
    with (output / 'EVIDENCE_HASHES.json').open('x') as stream:
        stream.write(json.dumps(manifest, sort_keys=True) + '\n')


def verify_evidence(output):
    manifest = json.loads((output / 'EVIDENCE_HASHES.json').read_text())
    for name, expected in manifest['files'].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Audit evidence changed: {name}")
    return manifest


def verify_panel(plan, trials):
    expected = {(scenario, e['configuration']['name']): e for scenario, _ in plan['scenarios'] for e in plan['entries']}
    keys = [(t['scenario'], t['recipe']) for t in trials]
    if len(keys) != len(set(keys)) or set(keys) != set(expected) or len(keys) != plan['trial_budget']:
        raise ValueError("Trial panel differs from registered configurations/scenarios")
    for row in trials:
        entry = expected[row['scenario'], row['recipe']]
        if row['parent'] != entry['parent'] or row['role'] != entry['role'] or row['status'] not in ('completed', 'failed'):
            raise ValueError("Trial role/status differs from registration")
    return expected


def verify_inputs(output):
    plan = json.loads((output / 'EXPERIMENT_PLAN.json').read_text())
    results = json.loads((output / 'RESULTS.json').read_text())
    diagnostics = json.loads((output / 'DIAGNOSTICS.json').read_text())
    raw = json.loads((output / 'TRIAL_RESULTS.json').read_text())
    expected = content_hash(plan)
    if any(r['plan_hash'] != expected for r in (results, diagnostics, raw)):
        raise ValueError("Audit report plan hash mismatch")
    evidence = verify_evidence(output)
    mandatory = {'EXPERIMENT_PLAN.json', 'TRIAL_RESULTS.json', 'RESULTS.json', 'DIAGNOSTICS.json',
                 'CASH_INTERVALS.json', 'INDEPENDENT_LEDGER_AUDIT.json'}
    mandatory.update(t['scenario'] + '_' + t['recipe'] + suffix for t in raw['trials'] for suffix in ('.started.json', '.completed.json'))
    if set(evidence['files']) != mandatory:
        raise ValueError("Evidence registry omits a required artifact/trial record")
    panel = verify_panel(plan, results['trials'])
    verify_panel(plan, raw['trials'])
    finished = {(t['scenario'], t['recipe']): t for t in results['trials']}
    for row in raw['trials']:
        final = finished[row['scenario'], row['recipe']]
        if any(content_hash(final.get(k)) != content_hash(value) for k, value in row.items()):
            raise ValueError("Final result changed an immutable trial field")
        key = row['scenario'] + '_' + row['recipe']
        if json.loads((output / (key + '.completed.json')).read_text()) != row:
            raise ValueError("Raw trial differs from retained completion record")
    if content_hash(decisions(results['trials'])) != content_hash(results['decisions']):
        raise ValueError("Research decisions disagree with frozen rules/evidence")
    snapshot = load_snapshot(Path(plan['snapshot']))
    if snapshot.dataset_hash != plan['dataset_hash'] or source_hashes() != plan['source_hashes']:
        raise ValueError("Audit source/dataset differs from frozen plan")
    metadata, rates = verified_cash_inputs(Path(plan['cash_path']))
    if metadata != plan['cash_source']:
        raise ValueError("Cash provenance differs from frozen plan")
    payloads = {}
    all_rows = results['original'] + results['trials']
    for row in all_rows:
        if row.get('status', 'completed') == 'completed':
            payload = verify_run(Path(row['bundle']))
            if content_hash(payload) != row['result_hash'] or payload['manifest']['dataset_hash'] != plan['dataset_hash']:
                raise ValueError("Audit bundle/result mismatch")
            if content_hash(summarize_run(saved_model(payload))) != content_hash(row['metrics']):
                raise ValueError("Reported metrics disagree with verified ledger")
            if 'scenario' in row:
                entry = panel[row['scenario'], row['recipe']]
                risk = RiskPolicy(**entry['risk']) if entry['risk'] is not None else None
                cost = dict(plan['scenarios'])[row['scenario']]
                config = RunConfig('100000', ExecutionProfile(cost, '0', '0'), tuple(entry['configuration']['universe']),
                                   date.fromisoformat(plan['start']), date.fromisoformat(plan['end']), risk=risk)
                if payload['manifest']['config'] != primitive(config) or payload['manifest']['source']['configuration'] != entry['configuration']:
                    raise ValueError("Bundle configuration differs from registration")
            payloads[row.get('scenario', 'original'), row['recipe']] = payload
    if len(results['trials']) != plan['trial_budget'] or len(raw['trials']) != plan['trial_budget']:
        raise ValueError("Incomplete audit trial registry")
    return plan, results, diagnostics, payloads, rates


def save_rows(output, name, rows):
    if rows:
        keys = list(dict.fromkeys(k for row in rows for k in row))
        write_csv(output / name, [{k: r.get(k) for k in keys} for r in rows])


def table(rows, columns):
    return '<div class="scroll"><table><thead><tr>' + ''.join('<th>' + escape(c) + '</th>' for c in columns) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join('<td>' + escape(str(r.get(c, 'N/A'))) + '</td>' for c in columns) + '</tr>' for r in rows) + '</tbody></table></div>'


def report(output):
    plan, results, diagnostics, payloads, rates = verify_inputs(output)
    os.environ.setdefault('MPLCONFIGDIR', str(output / 'matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    trial_rows, annual = [], []
    combined = [dict(r, window='original', role='reused', scenario='primary10', status='completed') for r in results['original']] + [dict(r, window='matched') for r in results['trials']]
    for r in combined:
        row = {k: r.get(k) for k in ('window', 'scenario', 'recipe', 'parent', 'role', 'status', 'start', 'end', 'result_hash')}
        if r['status'] == 'completed':
            metrics, overlay = r['metrics'], r['cash_overlay']
            payload = payloads['original' if r['window'] == 'original' else r['scenario'], r['recipe']]
            sessions = [s['session'] for s in payload['equity']]
            cash = tuple(v['return'] for v in rm.cash_intervals(sessions, rates))
            hist_sharpe = rm.regression(tuple(Decimal(s['session_return']) for s in payload['equity']), (Decimal(0),) * len(sessions), cash)['sharpe_historical_reference']
            row.update(cagr_calendar=metrics['cagr_calendar'], max_drawdown=metrics['max_drawdown'],
                sharpe_zero_reference=metrics['sharpe'], sharpe_historical_reference=hist_sharpe,
                average_gross_exposure=metrics['average_gross_exposure'], rejected_orders=metrics['rejected_orders'],
                turnover_per_year=Decimal(metrics['notional_turnover']) * Decimal('365.2425') / Decimal(metrics['calendar_days_inclusive']),
                cash_overlay_cagr=overlay['cagr_calendar'], cash_overlay_interest_usd=overlay['interest_usd'],
                cash_overlay_sharpe_historical_reference=overlay['sharpe_historical_reference'],
                beta_spy=r.get('paired_spy', {}).get('beta'),
                alpha_arithmetic_252_spy=r.get('paired_spy', {}).get('alpha_arithmetic_252'))
            groups = defaultdict(list)
            for state in payload['equity']:
                groups[state['session'][:4]].append(Decimal(state['session_return']))
            for year, values in sorted(groups.items()):
                annual.append(dict(window=r['window'], scenario=r['scenario'], recipe=r['recipe'], year=year,
                                   partial_year=year in ('2017', '2026'), **rm.return_metrics(values)))
        else:
            row['error'] = r.get('error')
        trial_rows.append(row)
    save_rows(output, 'trials.csv', trial_rows)
    save_rows(output, 'annual_returns.csv', annual)
    csv_rows = defaultdict(list)
    concentration_rows, recovery_rows, bucket_rows = [], [], []
    for key, d in diagnostics['details'].items():
        for name in ('assets', 'daily', 'annual', 'episodes'):
            csv_rows['attribution_' + name + '.csv'].extend(dict(portfolio=key, **r) for r in d['attribution'][name])
        csv_rows['rolling.csv'].extend(dict(portfolio=key, **r) for r in d['rolling'])
        csv_rows['recoveries.csv'].extend(dict(portfolio=key, **r) for r in d['recovery'])
        csv_rows['concentration.csv'].append(dict(portfolio=key, **d['concentration']))
        buckets = defaultdict(list)
        for e in d['attribution']['episodes']:
            days = e['calendar_days']
            category = '0-30' if days <= 30 else '31-90' if days <= 90 else '91-365' if days <= 365 else '366+'
            buckets[category].append(e)
        for category, episodes in sorted(buckets.items()):
            csv_rows['holding_buckets.csv'].append(dict(portfolio=key, calendar_days=category,
                episode_count=len(episodes), open_count=sum(e['status'] == 'open' for e in episodes),
                pnl_usd=sum((Decimal(e['pnl_usd']) for e in episodes), Decimal(0))))
        dcon = d['concentration']
        flagged = [a['security_id'] for a in d['attribution']['assets'] if a['positive_pnl_share'] is not None and Decimal(a['positive_pnl_share']) > Decimal(plan['concentration_asset_threshold'])]
        concentration_rows.append({'Portfolio': key, 'Asset >60% positive P&L': ', '.join(flagged) or 'None',
            'Mean excess/day (%)': percent(dcon['mean_daily_excess']),
            'After zeroing five best excess days (%)': percent(dcon['mean_excess_after_zeroing']),
            'Five days / positive excess (%)': percent(dcon['removed_positive_excess_share'])})
        worst = max(d['recovery'], key=lambda r: Decimal(r['max_drawdown']), default=None)
        if worst:
            recovery_rows.append({'Portfolio': key, 'Peak': worst['peak_date'], 'Trough': worst['trough_date'],
                'Max drawdown (%)': percent(worst['max_drawdown']), 'Recovery': worst['recovery_date'] or 'Unrecovered',
                'Sessions to recovery': worst['sessions_to_recovery'] if worst['sessions_to_recovery'] is not None else 'Unrecovered',
                'Calendar days': worst['calendar_days']})
    for name, rows in csv_rows.items():
        save_rows(output, name, rows)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout='constrained')
    for parent, color in zip(PARENTS, ('#187aaf', '#ce7423')):
        d = diagnostics['details'].get('primary10_' + parent)
        if not d:
            continue
        points = d['rolling']
        sessions = [date.fromisoformat(r['session']) for r in points]
        axes[0, 0].plot(sessions, [100 * float(r['total_return']) for r in points], label=parent, color=color)
        axes[0, 1].plot(sessions, [100 * float(r['relative_growth']) for r in points], label=parent, color=color)
        axis = axes[1, 0] if parent == PARENTS[0] else axes[1, 1]
        assets = d['attribution']['assets']
        axis.bar([r['security_id'] for r in assets], [float(r['pnl_usd']) for r in assets], color=color)
        axis.set_title(parent + ' | Actual dollar P&L')
        axis.set_xlabel('ETF security identifier')
        axis.set_ylabel('Net asset contribution (USD)')
    for axis, ylabel in ((axes[0, 0], '252-session compounded return (%)'), (axes[0, 1], '252-session growth relative to SPY (%)')):
        axis.set_xlabel('Window end date (New York session)')
        axis.set_ylabel(ylabel)
        axis.axhline(0, color='grey', linewidth=.8)
        axis.legend(fontsize=8)
    for axis in axes.flat:
        axis.grid(axis='y', alpha=.2)
    fig.suptitle(f"Fixed parents | Matched start {plan['start']} | 10 bps costs | Cash yield 0%")
    for extension in ('png', 'pdf'):
        fig.savefig(output / ('diagnostics.' + extension), dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout='constrained')
    for column, parent in enumerate(PARENTS):
        for top, roles in ((0, ('parent', 'neighbor')), (1, ('parent', 'allocation_control', 'atr_control'))):
            axis = axes[top, column]
            names = [r['recipe'] for r in results['trials'] if r['parent'] == parent and r['role'] in roles and r['scenario'] == 'primary10']
            for offset, scenario, color in ((-.17, 'primary10', '#187aaf'), (.17, 'stress25', '#ce7423')):
                rows = {r['recipe']: r for r in results['trials'] if r['parent'] == parent and r['scenario'] == scenario and r['status'] == 'completed'}
                # Missing trial bars are omitted, never replaced by zero performance.
                xs = [i + offset for i, name in enumerate(names) if name in rows]
                values = [100 * float(rows[name]['metrics']['cagr_calendar']) for name in names if name in rows]
                axis.bar(xs, values, width=.34, color=color, label='10 bps' if scenario == 'primary10' else '25 bps')
            labels = [('parent' if name == parent else name.removeprefix(parent + '_')) for name in names]
            axis.set_xticks(range(len(names)), labels, rotation=20, ha='right', fontsize=8)
            axis.set_ylabel('Calendar CAGR (%/year)')
            axis.set_xlabel('Registered one-factor variant' if top == 0 else 'Allocation / bundled ATR control')
            axis.set_title(parent)
            axis.legend(fontsize=8)
            axis.grid(axis='y', alpha=.2)
    fig.suptitle('All declared parameter/control trials | Parent unchanged | No new winner selected')
    for extension in ('png', 'pdf'):
        fig.savefig(output / ('stability_controls.' + extension), dpi=140)
    plt.close(fig)

    html_rows = []
    for row in trial_rows:
        valid = row['status'] == 'completed'
        cells = [row['recipe'], row['role'], row['status'], percent(row.get('cagr_calendar')),
            percent(row.get('max_drawdown')), f"{Decimal(row['sharpe_zero_reference']):.2f}" if valid and row.get('sharpe_zero_reference') is not None else 'N/A',
            percent(row.get('average_gross_exposure')), percent(row.get('cash_overlay_cagr')),
            f"{Decimal(row['turnover_per_year']):.2f}x" if valid else 'N/A', str(row.get('rejected_orders', 'N/A'))]
        html_rows.append('<tr data-window="' + row['window'] + '" data-cost="' + row['scenario'] + '">' + ''.join('<td>' + escape(str(v)) + '</td>' for v in cells) + '</tr>')
    pictures = ''.join('<img alt="' + name + ' robustness diagnostics with labelled axes" src="data:image/png;base64,' + base64.b64encode((output / (name + '.png')).read_bytes()).decode() + '">' for name in ('diagnostics', 'stability_controls'))
    decision_labels = {'retain_for_research': 'Retain defensive hypothesis for research', 'reject_on_this_sample': 'Rejected for its stated objective on this sample', 'inconclusive': 'Inconclusive', 'incomplete': 'Incomplete audit'}
    decision_text = ''.join('<li><strong>' + escape(parent) + '</strong>: ' + escape(decision_labels[d['decision']]) + '. Separate parameter-stability check: ' + ('passes' if d.get('parameter_stable') else 'fails or incomplete') + ' (' + percent(d.get('positive_neighbor_fraction_both_costs')) + ' positive at both costs).</li>' for parent, d in results['decisions'].items())
    yearly_rows = []
    for year in sorted({r['year'] for r in annual if r['window'] == 'matched'}):
        values = {r['recipe']: r['total_return'] for r in annual if r['year'] == year and r['window'] == 'matched' and r['scenario'] == 'primary10'}
        yearly_rows.append({'Year': year + (' (partial)' if year in ('2017', '2026') else ''),
                           **{name: percent(values.get(name)) for name in PARENTS + REFERENCES}})
    links = ['trials.csv', 'annual_returns.csv'] + sorted(csv_rows) + ['DIAGNOSTICS.json', 'INDEPENDENT_LEDGER_AUDIT.json', 'EXPERIMENT_PLAN.json', 'diagnostics.pdf', 'stability_controls.pdf']
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Strategy robustness audit</title>
<style>body{font:15px system-ui;color:#192b3d;max-width:1350px;margin:35px auto;padding:0 20px}p,li{line-height:1.6}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}td,th{padding:9px;border-bottom:1px solid #dce3e9;text-align:left}th{background:#edf2f7}.scroll{overflow:auto}img{width:100%}.note{padding:16px;background:#edf2f7}select{padding:8px;margin:8px}pre{white-space:pre-wrap}</style>
<h1>Why it worked, where it failed, and how stable it is</h1><p class="note">Private exploratory robustness audit. The two parents were chosen after inspecting the earlier ten-strategy comparison. All 2016–2026 dates remain exposed. No production winner, fresh holdout, or market-beating claim is created.</p>
<h2>Recorded research decisions</h2><ul>''' + decision_text + '''</ul><p>Momentum must beat both reserve-SPY and equal-weight sectors on historical-reference Sharpe at both costs. The defensive trend objective requires drawdown at most 75% of SPY's and CAGR at least 50% of SPY's at both costs. Neighbor stability requires at least 75% of neighbors to retain positive CAGR at both costs. These are predeclared research preferences; passing them does not establish alpha or future performance.</p>
<h2>All retained portfolios</h2><p>Thirty new trials share ''' + plan['start'] + '''–2026-10-02, the first warmed month-end for the 273-session neighbor, determined without inspecting prices. Five original January 31, 2017 portfolios are verified and retained separately. All start with $100,000. Actual portfolios retain zero cash yield; the separate cash column is a fixed-order diagnostic.</p>
<label>Window<select id="window"><option value="matched">Matched parameter/control window</option><option value="original">Original common-warmup portfolios</option></select></label><label>Costs<select id="cost"><option value="primary10">10 bps per side</option><option value="stress25">25 bps per side</option></select></label>
<div class="scroll"><table id="trials"><thead><tr><th>Recipe</th><th>Role</th><th>Status</th><th>Actual CAGR (%/year)</th><th>Max drawdown (%)</th><th>Sharpe (0% reference)</th><th>Avg gross exposure (%)</th><th>Cash-overlay CAGR (%/year)</th><th>Turnover / year</th><th>Rejected orders</th></tr></thead><tbody>''' + ''.join(html_rows) + '''</tbody></table></div>
''' + pictures + '''<h2>Calendar-year returns, matched parents and references at 10 bps</h2>''' + table(yearly_rows, ['Year'] + list(PARENTS + REFERENCES)) + '''<p>Annual returns slice continuous portfolios; they do not reset positions or cash each January. Asset-level dollar contributions by year are also exported, including partial 2026.</p><h2>Concentration and benchmark-relative sensitivity</h2>''' + table(concentration_rows, ['Portfolio', 'Asset >60% positive P&L', 'Mean excess/day (%)', 'After zeroing five best excess days (%)', 'Five days / positive excess (%)']) + '''<p>Dollar asset P&L includes filled fees/slippage, dividends recognized on entitlement, and terminal holdings. Arithmetic return contributions are not geometrically linked attribution. Asset shares use total positive asset P&L, rather than a near-zero net-profit denominator. Best-five removal zeros positive daily excess observations; it does not remove trades or replay a different portfolio. It remains descriptive and selected on this history.</p>
<h2>Worst drawdown recovery episodes</h2>''' + table(recovery_rows, ['Portfolio', 'Peak', 'Trough', 'Max drawdown (%)', 'Recovery', 'Sessions to recovery', 'Calendar days']) + '''<p>All underwater episodes and holding-duration buckets are exported. Holdings are flat-to-flat episodes: partial sales and monthly rebalances do not create independent round trips. Open holdings retain their marked value, with no invented exit. Holding durations are calendar days; recovery durations report both sessions and calendar days.</p>
<h2>Cash, exposure and risk assumptions</h2><ul><li>Historical cash uses official U.S. Treasury 3-month par-yield observations, strictly lagged before each interval's starting session, simple ACT/365 accrual including weekends, with at most ten days of staleness. Only previous cash plus accumulated interest earns interest; receivables do not. The fixed-order overlay does not change share sizing or orders. Revised historical yields are not a point-in-time vintage, Treasury total-return index, or broker cash rate.</li>
<li>Rolling/full-period historical-reference Sharpe and benchmark beta/alpha are exported. Alpha is an annualized arithmetic regression intercept, not CAGR. Exposure matching uses prior cash-overlay equity for weights and a fully invested, ex-date-reinvested SPY signal index as the risky leg, rather than reserve-SPY returns which already contain cash. This is a diagnostic with zero trading costs; it cannot establish an executable trading edge. Gross exposure and cash differences remain visible.</li>
<li>The 75% allocation control changes only scheduled allocation. ATR 14 / 2x uses the existing bundled sizing, fixed-stop and admission profile, 0.5% planned entry risk, 35% position cap, 95% gross cap, 5% reserve and 4.5% heat. Drawdown reduce/halt thresholds are 90%/99%, with scale 1, so ordinary drawdowns do not invoke a tuned circuit breaker. Stops can gap beyond planned budgets. Risk rejections and open holdings remain recorded; a bundled result cannot isolate stop effectiveness.</li>
<li>Fixed surviving ETF sample, issuer actions and the disclosed XLF signal-only warmup approximation remain unchanged. Calendar/open semantics, historical revisions, independent-provider and commercial qualification remain unresolved. The prior cost/delay comparison remains available; no parameter or rule is promoted from this audit.</li></ul>
<details><summary>Exact decisions and evidence</summary><pre>''' + escape(json.dumps(results['decisions'], indent=2)) + '''</pre></details><p>Verified accounting bundles: ''' + str(len(payloads)) + '''. Independent reconstruction checks raw shares/cash/receivables/equity, next-open fills and protective stop OHLC/price semantics. All failures remain in the registry.</p><p>Dataset SHA-256: <code>''' + plan['dataset_hash'] + '''</code><br>Audit plan SHA-256: <code>''' + results['plan_hash'] + '''</code></p><p>''' + ' · '.join('<a href="' + name + '">' + escape(name) + '</a>' for name in links) + '''</p>
<script>let w=document.getElementById('window'),c=document.getElementById('cost');function filter(){if(w.value==='original'){c.value='primary10';c.disabled=true}else{c.disabled=false}document.querySelectorAll('#trials tbody tr').forEach(r=>r.hidden=r.dataset.window!==w.value||r.dataset.cost!==c.value)}w.addEventListener('change',filter);c.addEventListener('change',filter);filter();</script></html>'''
    with (output / 'REPORT.html').open('x') as stream:
        stream.write(html)
    names = ['EXPERIMENT_PLAN.json', 'EVIDENCE_HASHES.json', 'CASH_INTERVALS.json', 'TRIAL_RESULTS.json', 'RESULTS.json', 'DIAGNOSTICS.json',
             'INDEPENDENT_LEDGER_AUDIT.json', 'trials.csv', 'annual_returns.csv', 'REPORT.html',
             'diagnostics.png', 'diagnostics.pdf', 'stability_controls.png', 'stability_controls.pdf'] + sorted(csv_rows)
    publish_hashes = {'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in names}}
    with (output / 'REPORT_HASHES.json').open('x') as stream:
        stream.write(json.dumps(publish_hashes, sort_keys=True) + '\n')
    print(json.dumps({'verified_bundles': len(payloads), 'artifacts': len(names), 'report': str(output / 'REPORT.html')}), flush=True)
