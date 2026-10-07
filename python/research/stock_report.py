"""Export verified, frozen stock research without simulating or selecting recipes."""

import argparse
import base64
import csv
from datetime import date
from decimal import Decimal
import hashlib
from html import escape
import json
import os
from pathlib import Path

from quant_core.provenance import content_hash
from research.market_report import percent


CSV_NAMES = ('trials.csv', 'annual_returns.csv', 'fold_results.csv', 'decisions.csv',
             'attribution_assets.csv', 'attribution_daily.csv', 'attribution_annual.csv',
             'attribution_episodes.csv', 'rolling.csv', 'recoveries.csv', 'concentration.csv')
PLOT_NAMES = ('equity_drawdown', 'neighbor_costs')
EVIDENCE_NAMES = ('EXPERIMENT_PLAN.json', 'RESULTS.json', 'DATA_READINESS.json',
                  'INDEPENDENT_LEDGER_AUDIT.json', 'DIAGNOSTICS.json',
                  'FROZEN_CANDIDATES.json', 'RETEST_REQUIREMENTS.json', 'EVIDENCE_HASHES.json')


def write_rows(path, rows, fallback):
    """Keep empty exports explicit and structured fields machine readable."""
    columns = list(dict.fromkeys(key for row in rows for key in row)) or list(fallback)
    with path.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list))
                         else value for key, value in row.items()} for row in rows)


def table(rows, columns, identifier=None):
    attr = ' id="' + escape(identifier, quote=True) + '"' if identifier else ''
    return '<div class="scroll"><table' + attr + '><thead><tr>' + ''.join(
        '<th>' + escape(column) + '</th>' for column in columns) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join('<td>' + escape(str(row.get(column, 'N/A'))) + '</td>'
                        for column in columns) + '</tr>' for row in rows) + '</tbody></table></div>'


def number(value):
    return 'N/A' if value is None else f'{Decimal(value):.3f}'


def trial_export(trial):
    row = {key: trial.get(key) for key in ('key', 'period', 'scenario', 'recipe', 'parent',
                                         'role', 'family', 'start', 'end', 'status',
                                         'bundle', 'result_hash', 'error')}
    if trial['status'] == 'completed':
        metrics = trial['metrics']
        row.update({key: value for key, value in metrics.items() if key != 'sharpe'})
        row['sharpe_zero_reference'] = metrics.get('sharpe')
        row['sharpe_historical_reference'] = trial.get('sharpe_historical_reference')
        days = metrics.get('calendar_days_inclusive')
        turnover = metrics.get('notional_turnover')
        row['turnover_per_year'] = (Decimal(turnover) * Decimal('365.2425') / Decimal(days)
                                    if days is not None and Decimal(days) > 0 and turnover is not None else None)
    return row


def annual_export(trial):
    rows = []
    for year, metrics in sorted(trial.get('annual', {}).items()):
        first, last = date.fromisoformat(trial['start']), date.fromisoformat(trial['end'])
        y = int(year)
        partial = ((y == first.year and (first.month, first.day) != (1, 1)) or
                   (y == last.year and (last.month, last.day) != (12, 31)))
        rows.append({'key': trial['key'], 'period': trial['period'], 'scenario': trial['scenario'],
                     'recipe': trial['recipe'], 'role': trial['role'], 'year': year,
                     'partial_calendar_coverage': partial, **metrics})
    return rows


def save_plot(figure, output, name):
    # Passing an exclusively opened stream prevents savefig from overwriting artifacts.
    for extension in ('png', 'pdf'):
        with (output / (name + '.' + extension)).open('xb') as stream:
            figure.savefig(stream, format=extension, dpi=140)


def plots(output, plan, trials, payloads):
    os.environ.setdefault('MPLCONFIGDIR', str(output / 'matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    parents = [entry for entry in plan['entries'] if entry['role'] == 'parent']
    references = [entry['configuration']['name'] for entry in plan['entries'] if entry['role'] == 'reference']
    primary = {trial['recipe']: trial for trial in trials
               if trial['period'] == 'continuous' and trial['scenario'] == 'primary10'
               and trial['status'] == 'completed'}
    fig, axes = plt.subplots(len(parents), 2, figsize=(14, max(4, 3 * len(parents))),
                             squeeze=False, layout='constrained')
    for index, entry in enumerate(parents):
        name = entry['configuration']['name']
        for recipe in [name] + references:
            trial = primary.get(recipe)
            if trial is None:
                continue
            states = payloads[trial['key']]['equity']
            sessions = [date.fromisoformat(state['session']) for state in states]
            axes[index, 0].plot(sessions, [float(state['equity']) for state in states],
                                label=recipe, linewidth=1.2)
            axes[index, 1].plot(sessions, [-100 * float(state['drawdown']) for state in states],
                                label=recipe, linewidth=1.2)
        for column, ylabel in ((0, 'Portfolio equity (USD)'), (1, 'Drawdown from peak (%)')):
            axis = axes[index, column]
            axis.set_title(entry['configuration']['family'] + ' | ' + name)
            axis.set_xlabel('Trading session date (New York)')
            axis.set_ylabel(ylabel)
            axis.grid(alpha=.2)
            if axis.lines:
                axis.legend(fontsize=7)
        if name not in primary:
            axes[index, 0].text(.5, .5, 'Parent failed or incomplete; no performance plotted',
                                transform=axes[index, 0].transAxes, ha='center', fontsize=9)
    fig.suptitle(f"Frozen parents and references | {plan['start']}–{plan['end']} | 10 bps per side")
    save_plot(fig, output, 'equity_drawdown')
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), squeeze=False, layout='constrained')
    for axis, entry in zip(axes.flat, parents):
        parent = entry['configuration']['name']
        names = [item['configuration']['name'] for item in plan['entries']
                 if item['configuration']['name'] == parent or
                 (item['role'] == 'neighbor' and item['parent'] == parent)]
        rows = {(trial['recipe'], trial['scenario']): trial for trial in trials
                if trial['period'] == 'continuous' and trial['status'] == 'completed'}
        omitted = []
        for offset, scenario, label, color in ((-.22, 'primary10', '10 bps / next open', '#187aaf'),
                                               (0, 'stress25', '25 bps / next open', '#ce7423'),
                                               (.22, 'delay10', '10 bps / second open', '#547d54')):
            selected = [(i, rows.get((name, scenario))) for i, name in enumerate(names)]
            available = [(i, trial) for i, trial in selected
                         if trial is not None and trial['metrics'].get('cagr_calendar') is not None]
            axis.bar([i + offset for i, _ in available],
                     [100 * float(trial['metrics']['cagr_calendar']) for _, trial in available],
                     width=.21, label=label, color=color)
            omitted.extend(name + '/' + scenario for name in names if (name, scenario) not in rows)
        axis.set_xticks(range(len(names)), names, rotation=15, ha='right', fontsize=7)
        axis.set_xlabel('Frozen parent and registered one-factor neighbor')
        axis.set_ylabel('Calendar CAGR (%/year)')
        axis.set_title(entry['configuration']['family'])
        axis.axhline(0, color='grey', linewidth=.7)
        axis.grid(axis='y', alpha=.2)
        axis.legend(fontsize=7)
        if omitted:
            axis.text(.01, .01, f'{len(omitted)} missing/failed trial bars omitted',
                      transform=axis.transAxes, fontsize=7)
    for axis in list(axes.flat)[len(parents):]:
        axis.set_visible(False)
    fig.suptitle('All four hypotheses | No neighbor replaces its parent | Missing results are not zero')
    save_plot(fig, output, 'neighbor_costs')
    plt.close(fig)


def report(output):
    from research.stock_campaign import verify_campaign

    output = Path(output)
    plan, results, payloads = verify_campaign(output)
    evidence = {name: json.loads((output / name).read_text()) for name in EVIDENCE_NAMES}
    diagnostics = evidence['DIAGNOSTICS.json']
    if diagnostics['plan_hash'] != content_hash(plan):
        raise ValueError('Diagnostic plan hash differs from verified campaign')
    parents = [entry for entry in plan['entries'] if entry['role'] == 'parent']
    configured_universe = parents[0]['configuration']['universe'] if parents else []
    scope = evidence['DATA_READINESS.json'].get('panel_scope_decision', {})
    universe = scope.get('eligible', configured_universe)
    if set(universe) != set(configured_universe):
        raise ValueError('Reported data scope differs from the registered strategy universe')
    exported = list(CSV_NAMES) + [name + '.' + extension for name in PLOT_NAMES
                                for extension in ('png', 'pdf')] + ['REPORT.html']
    for name in exported + ['REPORT_HASHES.json']:
        if (output / name).exists():
            raise FileExistsError(f'Report artifact already exists: {output / name}')
    trials = [trial_export(trial) for trial in results['trials']]
    annual = [row for trial in results['trials'] if trial['status'] == 'completed'
              for row in annual_export(trial)]
    folds = [row for row in trials if row['period'] != 'continuous']
    decisions = [{'parent': name, **value} for name, value in results['decisions'].items()]
    write_rows(output / 'trials.csv', trials, ('key', 'period', 'recipe', 'status'))
    write_rows(output / 'annual_returns.csv', annual, ('key', 'period', 'recipe', 'year', 'total_return'))
    write_rows(output / 'fold_results.csv', folds, ('key', 'period', 'recipe', 'status'))
    write_rows(output / 'decisions.csv', decisions, ('parent', 'objective', 'decision', 'qualified'))
    detail_rows = {name: [] for name in CSV_NAMES[4:]}
    for parent, detail in diagnostics['details'].items():
        for category in ('assets', 'daily', 'annual', 'episodes'):
            detail_rows['attribution_' + category + '.csv'].extend(
                {'parent': parent, **row} for row in detail['attribution'][category])
        detail_rows['rolling.csv'].extend({'parent': parent, **row} for row in detail['rolling'])
        detail_rows['recoveries.csv'].extend({'parent': parent, **row} for row in detail['recovery'])
        detail_rows['concentration.csv'].append({'parent': parent, **detail['concentration']})
    for name, rows in detail_rows.items():
        write_rows(output / name, rows, ('parent', 'status'))
    plots(output, plan, results['trials'], payloads)

    html_trials = []
    for row in trials:
        html_trials.append({'Period': row['period'], 'Scenario': row['scenario'], 'Recipe': row['recipe'],
                            'Role': row['role'], 'Status': row['status'],
                            'CAGR (%/year)': percent(row.get('cagr_calendar')),
                            'Max drawdown (%)': percent(row.get('max_drawdown')),
                            'Sharpe (historical reference)': number(row.get('sharpe_historical_reference')),
                            'Gross exposure (%)': percent(row.get('average_gross_exposure')),
                            'Turnover (notional/year)': number(row.get('turnover_per_year')),
                            'Error': row.get('error') or ''})
    html_folds = [{'Period': row['period'], 'Scenario': row['scenario'], 'Recipe': row['recipe'],
                   'Status': row['status'], 'CAGR (%/year)': percent(row.get('cagr_calendar')),
                   'Max drawdown (%)': percent(row.get('max_drawdown'))} for row in folds]
    html_annual = [{'Period': row['period'], 'Scenario': row['scenario'], 'Recipe': row['recipe'],
                    'Year': row['year'], 'Partial calendar coverage': row['partial_calendar_coverage'],
                    'Return (%)': percent(row.get('total_return')),
                    'Within-year drawdown (%)': percent(row.get('max_drawdown'))} for row in annual]
    html_decisions = [{'Parent': row['parent'], 'Objective': row['objective'], 'Decision': row['decision'],
                       'Objective passed': row.get('objective_passed'),
                       'Neighbor positive': row.get('neighbor_positive'),
                       'Fold pass fraction': row.get('fold_pass_fraction'),
                       'Delay passed': row.get('delay_passed'),
                       'Freeze for retest': row.get('freeze_for_retest'), 'Qualified': row['qualified']}
                      for row in decisions]
    excluded = scope.get('excluded', [])
    exclusions = ('The documented exclusions are ' + ', '.join(excluded) + ': ' +
                  str(scope.get('reason', 'see the retained data scope decision')) +
                  '. They were identified before strategy outcomes; no replacements were selected by returns.'
                  if excluded else 'Any requested/eligible panel differences remain recorded in data readiness.')
    images = ''.join('<img alt="' + escape(name.replace('_', ' ')) +
                     ' with labeled axes and units" src="data:image/png;base64,' +
                     base64.b64encode((output / (name + '.png')).read_bytes()).decode() + '">'
                     for name in PLOT_NAMES)
    details = ''.join('<details><summary>' + escape(name) + '</summary><pre>' +
                      escape(json.dumps(value, sort_keys=True, indent=2)) + '</pre></details>'
                      for name, value in [('Frozen experiment specification', plan),
                                          ('Complete data readiness', evidence['DATA_READINESS.json']),
                                          ('Independent ledger audit', evidence['INDEPENDENT_LEDGER_AUDIT.json']),
                                          ('Frozen exploratory candidates', evidence['FROZEN_CANDIDATES.json']),
                                          ('Requirements for an independent retest', evidence['RETEST_REQUIREMENTS.json']),
                                          ('Parent diagnostics', diagnostics)])
    if results.get('uncertainty') is not None:
        details += '<details><summary>Conditional bootstrap uncertainty</summary><p>Paired date-block results are conditional on this observed survivor sample. They cannot restore exposed dates, eliminate selection bias, or supply independent final evidence. A 95% interval is not a probability of future profit.</p><pre>' + escape(json.dumps(results['uncertainty'], indent=2, sort_keys=True)) + '</pre></details>'
    links = ' · '.join('<a href="' + escape(name, quote=True) + '">' + escape(name) + '</a>'
                       for name in exported + list(EVIDENCE_NAMES))
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bounded stock strategy research</title>
<style>body{font:15px system-ui;color:#192b3d;max-width:1400px;margin:35px auto;padding:0 20px}p,li{line-height:1.6}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px;margin:18px 0}td,th{padding:8px;border-bottom:1px solid #dce3e9;text-align:left}th{background:#edf2f7}img{width:100%}.note{padding:16px;background:#edf2f7}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{overflow-wrap:anywhere}input{padding:8px;margin:8px}</style></head><body>
<h1>Bounded stock strategy research</h1><p>''' + escape(str(plan['start'])) + '–' + escape(str(plan['end'])) + ' · ' + str(len(universe)) + ''' surviving stocks · Four frozen hypotheses</p>
<p class="note">Exploratory evidence only. All historical dates are already exposed. No fresh final test or production strategy nomination exists. The frozen rules may fail; neighbors do not replace their parents and a promising result authorizes only independent retesting.</p>
<h2>Predeclared objective decisions</h2>''' + table(html_decisions, tuple(html_decisions[0]) if html_decisions else ('Parent', 'Decision')) + '''
<p>Momentum and reversal seek positive net CAGR and historical-reference Sharpe above both reserve-SPY and the same-panel equal-weight reference at primary and stressed costs. Trend participation and low volatility seek positive CAGR, drawdown at most 75% of each equity reference, and at least 50% of each reference's CAGR. The exact registered fold, neighbor and delay checks are retained in the experiment specification and decisions. These screens are research preferences, not evidence of guaranteed profitability.</p>
<h2>Data scope and cash availability</h2><p>The retrospectively fixed surviving panel is ''' + escape(', '.join(universe)) + '''. It is a custom sample, not a historical index membership backtest. ''' + escape(exclusions) + ''' Missing dividend payment dates remain visible: entitlements contribute receivables to equity, while unknown cash availability is deferred through the entire sample. This explicit convention is not an observed payment date and can affect sizing, exposure, and cross-strategy comparisons.</p>
<p>SPY buys once with an initial reserve and retains dividend cash; it is not continuously dividend reinvested. The stock equal-weight reference rebalances the same opportunity set. Cash controls earn zero yield in the executed ledger. Historical-reference Sharpe and any cash-yield overlay are separately labeled diagnostics, not changes to executed orders. Corporate-action, opening-price, historical identity, survivorship and usage-right qualifications remain unresolved.</p>
<h2>All registered trial statuses and results</h2><p>''' + str(plan['trial_budget']) + ''' trials were registered across continuous history and chronological windows. Failed or invalid benchmark trials remain visible; their performance is not reported as zero.</p><label>Filter trial rows <input id="search" type="search" placeholder="Recipe, period, scenario, status"></label>''' + table(html_trials, tuple(html_trials[0]) if html_trials else ('Recipe', 'Status'), 'trials') + images + '''
<h2>Chronological fixed-rule windows</h2><p>Each development/selection window resets starting cash and holdings and supplies only earlier indicator warmup. These are fixed-rule walk-forward diagnostics with no model fitting. Their returns differ from annual slices of a continuously held portfolio. The already exposed dates cannot support a fresh OOS or final holdout claim.</p>''' + table(html_folds, tuple(html_folds[0]) if html_folds else ('Period', 'Status')) + '''
<details><summary>Annual slices of every completed portfolio</summary><p>Boundary years may have partial calendar coverage; within-year drawdown resets the peak and is distinct from full-period drawdown.</p>''' + table(html_annual, tuple(html_annual[0]) if html_annual else ('Year', 'Return (%)')) + '''</details>
<h2>Independent retest and qualification</h2><p>Step 5 remains blocked until appropriately licensed, independently sourced data with reviewed fixed-sample disclosure, identity, delisting treatment and corporate-action coverage is available. Historical-index claims additionally require point-in-time universe coverage. Frozen exploratory candidates are not qualified built-in strategies. Independent-provider agreement on exposed dates does not create fresh evidence; a final claim also requires genuinely untouched historical or prospective evidence. Preserve the full accumulated search, including rejected ETF experiments and these stock failures.</p>
<p>Attribution reconciles raw asset P&amp;L to the portfolio ledger. Recovery tables retain unrecovered drawdowns. Rolling windows overlap and are not independent observations. Zeroing the five strongest excess-return days is a descriptive concentration adjustment, not removal of trades or a replay. Any exposure-matched or cash-overlay results inside diagnostics are non-executable comparisons with their recorded limitations.</p>''' + details + '''
<p>Verified bundles: ''' + str(len(payloads)) + ' · Dataset SHA-256: <code>' + escape(plan['dataset_hash']) + '</code> · Plan SHA-256: <code>' + escape(results['plan_hash']) + '</code></p><p>' + links + '''</p>
<script>document.getElementById('search').addEventListener('input',function(){let term=this.value.toLowerCase();document.querySelectorAll('#trials tbody tr').forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(term))});</script></body></html>'''
    with (output / 'REPORT.html').open('x', encoding='utf-8') as stream:
        stream.write(html)
    names = sorted(exported + list(EVIDENCE_NAMES))
    manifest = {'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in names}}
    with (output / 'REPORT_HASHES.json').open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(manifest, sort_keys=True) + '\n')
    summary = {'verified_bundles': len(payloads), 'registered_trials': len(trials),
               'artifacts': len(names), 'report': str(output / 'REPORT.html')}
    print(json.dumps(summary, sort_keys=True), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    report(parser.parse_args().output)


if __name__ == '__main__':
    main()
