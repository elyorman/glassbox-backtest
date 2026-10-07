"""Verify and report frozen independent retests without selecting new recipes."""

from datetime import date
from decimal import Decimal
import hashlib
from html import escape
import json
from pathlib import Path


EVIDENCE = ('EXPERIMENT_PLAN.json', 'RESULTS.json', 'INDEPENDENT_LEDGER_AUDIT.json')


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify_retest(output):
    """Reconcile every saved trial and comparison to the original frozen campaign."""
    from quant_core.analytics import sharpe, summarize_run
    from quant_core.backtest import RunConfig
    from quant_core.data.storage import load_snapshot
    from quant_core.execution import ExecutionProfile
    from quant_core.provenance import content_hash, primitive
    from quant_core.reporting import verify_run
    from quant_core.strategies import StrategyConfig, build_strategy
    from quant_core.validation.contracts import load_document, parse_qualification
    from research.market_backtest import period_rows, saved_model
    from research.robustness_audit import audit_ledger, source_hashes, verified_cash_inputs
    from research.robustness_metrics import cash_intervals
    from research import stock_campaign as campaign

    output = Path(output)
    plan, results = (_read(output / name) for name in EVIDENCE[:2])
    if results['plan_hash'] != content_hash(plan) or source_hashes() != plan['source_hashes']:
        raise ValueError('Retest plan/source hash mismatch')
    original_path = Path(plan['original_campaign'])
    original, original_results, original_payloads = campaign.verify_campaign(original_path)
    frozen = _read(original_path / 'FROZEN_CANDIDATES.json')['entries']
    if not frozen:
        raise ValueError('Retest has no originally frozen candidate')
    snapshot_path = Path(plan['snapshot'])
    data = load_snapshot(snapshot_path)
    qualification_path = Path(plan['qualification_path'])
    if hashlib.sha256(qualification_path.read_bytes()).hexdigest() != plan['qualification_hash']:
        raise ValueError('Retest qualification bytes changed')
    qualification = load_document(qualification_path, 'qualification', parse_qualification)
    campaign.validate_retest_inputs(original, data, qualification)
    references = [entry for entry in original['entries'] if entry['role'] == 'reference']
    expected_plan = primitive(dict(original, dataset_hash=data.dataset_hash,
        snapshot=str(snapshot_path.resolve()), original_campaign=str(original_path.resolve()),
        original_dataset_hash=original['dataset_hash'], original_plan_hash=content_hash(original),
        qualification=qualification, qualification_path=str(qualification_path.resolve()),
        qualification_hash=hashlib.sha256(qualification_path.read_bytes()).hexdigest(),
        entries=frozen + references, periods=original['periods'][:1],
        trial_budget=3 * (len(frozen) + len(references))))
    if plan != expected_plan:
        raise ValueError('Retest procedure differs from the original frozen campaign')
    campaign.validate_trials(plan, results['trials'])
    registered = campaign.expected_panel(plan)
    required = set(EVIDENCE)
    required.update(key + suffix for key in registered for suffix in ('.started.json', '.completed.json'))
    hashes = _read(output / 'EVIDENCE_HASHES.json')['files']
    if set(hashes) != required:
        raise ValueError('Retest evidence registry incomplete')
    for name, digest in hashes.items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Retest evidence changed: ' + name)
    cashmeta, rates = verified_cash_inputs(Path(plan['cash_path']))
    if cashmeta != plan['cash_source']:
        raise ValueError('Retest cash provenance changed')
    payloads, models, audits = {}, {}, []
    for row in results['trials']:
        period, scenario, entry = registered[row['key']]
        expected_start = dict(key=row['key'], period=period['name'], scenario=scenario[0],
            recipe=entry['configuration']['name'], family=entry['configuration']['family'],
            parent=entry['parent'], role=entry['role'], start=period['start'], end=period['end'],
            status='started', plan_hash=content_hash(plan))
        if (_read(output / (row['key'] + '.started.json')) != expected_start
            or _read(output / (row['key'] + '.completed.json')) != row
            or any(row.get(key) != value for key, value in expected_start.items() if key != 'status')):
            raise ValueError('Retest trial identity changed')
        if row['status'] == 'failed':
            continue
        bundle = output / 'runs' / row['key']
        if Path(row['bundle']).resolve() != bundle.resolve():
            raise ValueError('Retest bundle is outside its registered output')
        payload = verify_run(bundle)
        execution = ExecutionProfile(scenario[1], '0', '0')
        recipe = StrategyConfig(**entry['configuration'])
        config = RunConfig('100000', execution, recipe.universe,
            date.fromisoformat(period['start']), date.fromisoformat(period['end']),
            actions_policy='require_complete', execution_delay_sessions=scenario[2])
        source = build_strategy(data, recipe, config.start, execution)
        if (content_hash(payload) != row['result_hash']
            or payload['manifest']['dataset_hash'] != data.dataset_hash
            or payload['manifest']['config'] != primitive(config)
            or payload['manifest']['source'] != primitive(source.spec)):
            raise ValueError('Retest bundle differs from frozen configuration/data')
        model = saved_model(payload)
        valid = (entry['role'] != 'reference' or recipe.family == 'cash'
                 or (any(fill.side == 'buy' for fill in model.fills)
                     and not model.summary.rejected_order_count))
        if row['status'] != ('completed' if valid else 'invalid_benchmark'):
            raise ValueError('Retest benchmark status disagrees with fills')
        rf = tuple(Decimal(item['return']) for item in cash_intervals(
            tuple(state.session for state in model.equity), rates))
        historical = sharpe(tuple(state.session_return - rate for state, rate in zip(model.equity, rf)))
        if (row['metrics'] != primitive(summarize_run(model))
            or row['annual'] != primitive(period_rows(model))
            or row['sharpe_historical_reference'] != (None if historical is None else str(historical))):
            raise ValueError('Retest derived metrics disagree with verified ledger')
        audits.append(dict(key=row['key'], **audit_ledger(data, payload)))
        payloads[row['key']], models[row['key']] = payload, model
    if _read(output / 'INDEPENDENT_LEDGER_AUDIT.json') != {'trials': audits}:
        raise ValueError('Retest independent ledger audit disagrees with bundles')
    prior = {(row['scenario'], row['recipe']): row for row in original_results['trials']
             if row['period'] == 'continuous'}
    comparisons = []
    for row in results['trials']:
        _, _, entry = registered[row['key']]
        before = prior[row['scenario'], row['recipe']]
        refs = [next(trial for trial in results['trials'] if trial['scenario'] == row['scenario']
                     and trial['recipe'] == name) for name in (campaign.REFERENCE, campaign.EQUAL)]
        objective = campaign.economic_pass(row, refs, entry['objective']) if entry['role'] == 'parent' else None
        after_model = models.get(row['key']) if row['status'] == 'completed' else None
        before_model = saved_model(original_payloads[before['key']]) if before['status'] == 'completed' else None
        comparisons.append(campaign.compare_retest(row, before, after_model, before_model,
                                                   objective, original['cross_provider_tolerances']))
    if (results != dict(plan_hash=content_hash(plan), trials=results['trials'], comparisons=comparisons,
                        strategy_selected=False, fresh_final_test=False)):
        raise ValueError('Retest comparisons or research claims disagree with evidence')
    return plan, results, payloads


def report_retest(output):
    """Write a minimal exclusive report after independently verifying saved evidence."""
    output = Path(output)
    plan, results, payloads = verify_retest(output)
    report_path, hashes_path = output / 'RETEST_REPORT.html', output / 'RETEST_REPORT_HASHES.json'
    if report_path.exists() or hashes_path.exists():
        raise FileExistsError('Retest report artifacts already exist')
    columns = ('recipe', 'scenario', 'status', 'objective_passed', 'total_return_difference',
               'maximum_daily_return_difference', 'cross_provider_tolerances_passed')
    rows = ''.join('<tr>' + ''.join('<td>' + escape(str(row.get(key, 'N/A'))) + '</td>'
                                   for key in columns) + '</tr>' for row in results['comparisons'])
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Independent stock retest</title>'
            '<style>body{font:15px system-ui;margin:30px}table{border-collapse:collapse}'
            'td,th{padding:8px;border:1px solid #ddd}pre{white-space:pre-wrap}</style>'
            '<h1>Frozen independent stock retest</h1><p>Fixed surviving sample. '
            'Provider agreement on exposed dates supplies robustness evidence; it does not establish '
            'a fresh temporal holdout or a production strategy nomination. Failed and invalid trials '
            'remain visible. Return differences are fractions; daily differences are maximum absolute '
            'session-return differences.</p><p>Verified bundles: ' + str(len(payloads)) + '</p>'
            '<table><thead><tr>' + ''.join('<th>' + escape(key) + '</th>' for key in columns)
            + '</tr></thead><tbody>' + rows + '</tbody></table><details><summary>Frozen retest specification</summary>'
            '<pre>' + escape(json.dumps(plan, indent=2, sort_keys=True)) + '</pre></details></html>')
    with report_path.open('x', encoding='utf-8') as stream:
        stream.write(html)
    names = EVIDENCE + ('EVIDENCE_HASHES.json', report_path.name)
    manifest = {'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in names}}
    with hashes_path.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, sort_keys=True)
        stream.write('\n')
    return {'verified_bundles': len(payloads), 'registered_trials': len(results['trials']),
            'report': str(report_path)}
