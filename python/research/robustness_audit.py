"""Finite, offline robustness audit. Does not tune or nominate a strategy."""

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext, Context
import hashlib
import json
from pathlib import Path

from quant_core.analytics import paired_metrics, return_metrics, summarize_run
from quant_core.backtest import RunConfig, run_backtest
from quant_core.data import Dividend, Split
from quant_core.data.storage import load_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import content_hash, primitive, canonical_json
from quant_core.reporting import save_run, verify_run
from quant_core.risk import RiskPolicy
from quant_core.strategies import initial_recipes, benchmark_recipes, build_strategy
from research.compare_strategies import common_start
from research.market_backtest import END, SYMBOLS, WarmupDistributionStrategy, publish, period_rows, saved_model
from research import robustness_metrics as rm

PARENTS = ('momentum_252_skip21_top3', 'trend_sma_200')
REFERENCES = ('broad_market_buy_hold_reserve', 'same_universe_equal_weight', 'cash_control')
SCENARIOS = (('primary10', '10'), ('stress25', '25'))
ZERO, ONE = Decimal(0), Decimal(1)


def experiments(universe=SYMBOLS[:-1]):
    base = {r.name: r for r in initial_recipes(universe)}
    rows = []
    for name in PARENTS:
        parent = base[name]
        rows.append(dict(parent=name, role='parent', configuration=parent, risk=None))
        changes = ({'momentum_lookback': 231}, {'momentum_lookback': 273}, {'top_k': 2}, {'top_k': 4}) if parent.family == 'momentum' else ({'mean_window': 180}, {'mean_window': 220})
        for change in changes:
            key, value = next(iter(change.items()))
            rows.append(dict(parent=name, role='neighbor',
                configuration=replace(parent, name=name + '_' + key + str(value), **change), risk=None))
        rows.append(dict(parent=name, role='allocation_control',
                         configuration=replace(parent, name=name + '_allocation75', invested_fraction='.75'), risk=None))
        policy = RiskPolicy(max_position_fraction='.35', max_gross_fraction='.95',
                            cash_reserve_fraction='.05', max_portfolio_heat='.045', max_positions=9,
                            drawdown_reduce='.90', drawdown_halt='.99', reduced_budget_scale='1')
        rows.append(dict(parent=name, role='atr_control',
                         configuration=replace(parent, name=name + '_atr14x2', profile='atr_protected'), risk=policy))
    for ref in benchmark_recipes(universe, 'SPY'):
        if ref.name in REFERENCES:
            rows.append(dict(parent=None, role='reference', configuration=ref, risk=None))
    return tuple(rows)


def source_hashes():
    root = Path(__file__).resolve().parents[1]
    files = list((root / 'quant_core').rglob('*.py')) + list((root / 'research').glob('*.py'))
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def register_plan(output, plan):
    frozen = primitive(plan)  # Deep value copy; later result enrichment cannot mutate registration.
    plan_hash = content_hash(frozen)
    publish(output / 'EXPERIMENT_PLAN.json', frozen)
    return frozen, plan_hash


def audit_ledger(snapshot, run):
    """Independent raw-price ledger, including protective stop timing and prices."""
    with localcontext(Context(prec=28)):
        config = run['manifest']['config']
        cash, held, pending = Decimal(config['initial_cash']), defaultdict(Decimal), []
        bars = {(b.session, b.security_id): b for b in snapshot.bars}
        indices = {d: i for i, d in enumerate(snapshot.sessions)}
        panel = tuple(d for d in snapshot.sessions if (not config['start'] or d >= date.fromisoformat(config['start']))
                      and (not config['end'] or d <= date.fromisoformat(config['end'])))
        if tuple(date.fromisoformat(s['session']) for s in run['equity']) != panel:
            raise ArithmeticError("Incomplete or duplicated equity session panel")
        if any(date.fromisoformat(f['execution_date']) not in panel for f in run['fills']):
            raise ArithmeticError("Fill outside portfolio session panel")
        if len({f['fill_id'] for f in run['fills']}) != len(run['fills']):
            raise ArithmeticError("Duplicate fill identity")
        orders = {o['order_id']: o for o in run['orders']}
        if len(orders) != len(run['orders']) or {o['fill_id'] for o in orders.values() if o['status'] == 'filled'} != {f['fill_id'] for f in run['fills']}:
            raise ArithmeticError("Filled-order registry differs from fills")
        stops = {}
        events, fills = defaultdict(list), defaultdict(list)
        for event in snapshot.actions:
            events[event.session].append(event)
        for fill in run['fills']:
            fills[date.fromisoformat(fill['execution_date'])].append(fill)
        kinds = Counter()
        for state in run['equity']:
            day = date.fromisoformat(state['session'])
            for event in events[day]:
                if isinstance(event, Split):
                    held[event.security_id] *= event.ratio
                    if event.security_id in stops:
                        trigger, signal = stops[event.security_id]
                        stops[event.security_id] = (trigger / event.ratio, signal)
                elif not isinstance(event, Dividend):
                    raise ValueError("Audit supports the pinned split/cash-dividend ETF snapshot only")
            for event in events[day]:
                if isinstance(event, Dividend):
                    pending.append((event.pay_date, held[event.security_id] * event.amount))
            cash += sum((amount for payment, amount in pending if payment <= day), ZERO)
            pending = [(payment, amount) for payment, amount in pending if payment > day]
            required_gaps = {a for a, (stop, _) in stops.items() if bars[day, a].volume > 0 and bars[day, a].open <= stop}
            intraday_phase = False
            for fill in fills[day]:
                asset, quantity = fill['security_id'], Decimal(fill['quantity'])
                bar = bars[day, asset]
                signal = date.fromisoformat(fill['signal_date'])
                kind = fill.get('execution_kind', 'market_open')
                sign = ONE if fill['side'] == 'buy' else -ONE
                order = orders.get(fill['order_id'])
                if (order is None or order['status'] != 'filled' or order['fill_id'] != fill['fill_id']
                        or order['request']['security_id'] != asset or order['request']['side'] != fill['side']
                        or Decimal(order['adjusted_quantity']) != quantity):
                    raise ArithmeticError("Fill does not match its accepted order")
                if kind == 'market_open':
                    if required_gaps or intraday_phase:
                        raise ArithmeticError("Missing gap stop or market fill after intraday phase")
                    raw = bar.open
                    if indices[day] - indices[signal] != config['execution_delay_sessions']:
                        raise ArithmeticError("Scheduled fill timing mismatch")
                elif kind in ('stop_gap', 'stop_intraday'):
                    trigger = Decimal(fill['trigger_price'])
                    if (fill['side'] != 'sell' or signal >= day or asset not in stops
                            or stops[asset] != (trigger, signal) or quantity != held[asset]):
                        raise ArithmeticError("Invalid stop side/timing")
                    if kind == 'stop_gap' and asset in required_gaps and not intraday_phase:
                        raw = bar.open
                        required_gaps.remove(asset)
                    elif kind == 'stop_intraday' and bar.low <= trigger < bar.open:
                        if required_gaps:
                            raise ArithmeticError("Missing earlier opening stop")
                        intraday_phase = True
                        raw = trigger
                    else:
                        raise ArithmeticError("Stop trigger disagrees with raw OHLC")
                else:
                    raise ArithmeticError("Unknown execution kind")
                price = raw * (ONE + sign * Decimal(config['execution']['slippage_bps']) / 10000)
                notional = price * quantity
                fee = notional * Decimal(config['execution']['fee_bps']) / 10000 + Decimal(config['execution']['fee_per_order'])
                if (price != Decimal(fill['price']) or notional != Decimal(fill['notional']) or fee != Decimal(fill['fees'])
                        or Decimal(fill.get('raw_execution_price') or str(raw)) != raw):
                    raise ArithmeticError("Fill price/notional/fee mismatch")
                held[asset] += sign * quantity
                if held[asset] < 0 or held[asset] != Decimal(fill['position_quantity_after']):
                    raise ArithmeticError("Fill inventory mismatch")
                cash -= sign * notional + fee
                if fill['side'] == 'buy' and order['adjusted_stop_price'] is not None:
                    stop = Decimal(order['adjusted_stop_price'])
                    if not ZERO < stop < bar.open:
                        raise ArithmeticError("Entry has invalid attached stop")
                    stops[asset] = (stop, signal)
                elif held[asset] == ZERO:
                    stops.pop(asset, None)
                kinds[kind] += 1
            if required_gaps or any(bars[day, a].volume > 0 and bars[day, a].low <= trigger
                                    for a, (trigger, _) in stops.items()):
                raise ArithmeticError("Triggered protective stop was not executed")
            receivable = sum((v for _, v in pending), ZERO)
            market = sum((qty * bars[day, asset].close for asset, qty in held.items() if qty), ZERO)
            equity = cash + receivable + market
            tolerance = max(Decimal('1e-18'), abs(equity) * Decimal('1e-24'))
            for field, expected in (('cash', cash), ('receivables', receivable), ('market_value', market), ('equity', equity)):
                if abs(Decimal(state[field]) - expected) > tolerance:
                    raise ArithmeticError(f"Independent {field} mismatch on {day}")
            reported = {p['security_id']: Decimal(p['quantity']) for p in state['positions']}
            if reported != {a: q for a, q in held.items() if q}:
                raise ArithmeticError("Reported holdings mismatch")
        if sum(kinds.values()) != len(run['fills']):
            raise ArithmeticError("Unprocessed fill")
        return dict(status='passed', sessions_checked=len(run['equity']), fills_checked=sum(kinds.values()), execution_kinds=dict(kinds))


def decisions(trials):
    """Predeclared research-hypothesis decisions; never selects a production winner."""
    output = {}
    for parent in PARENTS:
        rows = [r for r in trials if r['parent'] == parent and r['role'] in ('parent', 'neighbor')]
        neighbor_count = 4 if parent == PARENTS[0] else 2
        complete = len(rows) == (neighbor_count + 1) * 2 and all(r['status'] == 'completed' for r in rows)
        complete = complete and all(sum(r['role'] == 'parent' and r['scenario'] == s for r in rows) == 1 and
            len({r['recipe'] for r in rows if r['role'] == 'neighbor' and r['scenario'] == s}) == neighbor_count for s, _ in SCENARIOS)
        complete = complete and ({r['recipe'] for r in rows if r['role'] == 'neighbor' and r['scenario'] == 'primary10'} ==
                                 {r['recipe'] for r in rows if r['role'] == 'neighbor' and r['scenario'] == 'stress25'})
        if not complete:
            output[parent] = dict(decision='incomplete', reason='Missing/failed registered parent or neighbor', strategy_selected=False)
            continue
        neighbors = [r for r in rows if r['role'] == 'neighbor']
        positive = sum(Decimal(r['metrics']['cagr_calendar']) > 0 for r in neighbors)
        fraction = Decimal(positive) / len(neighbors)
        # Each neighbor must retain positivity at both costs, not just one row.
        names = {r['recipe'] for r in neighbors}
        stable = sum(all(Decimal(r['metrics']['cagr_calendar']) > 0 for r in neighbors if r['recipe'] == name) for name in names)
        stability = Decimal(stable) / neighbor_count
        parents = [r for r in rows if r['role'] == 'parent']
        try:
            if parent == PARENTS[0]:
                passed = all(r['paired_spy']['sharpe_difference'] is not None and r['paired_equal']['sharpe_difference'] is not None and
                    Decimal(r['paired_spy']['sharpe_difference']) > 0 and Decimal(r['paired_equal']['sharpe_difference']) > 0 for r in parents)
                objective = 'historical_reference_sharpe_above_both_references_at_both_costs'
                status = 'inconclusive' if passed else 'reject_on_this_sample'
            else:
                passed = all(Decimal(r['metrics']['max_drawdown']) <= Decimal('.75') * Decimal(r['spy_metrics']['max_drawdown']) and
                    Decimal(r['metrics']['cagr_calendar']) >= Decimal('.50') * Decimal(r['spy_metrics']['cagr_calendar']) for r in parents)
                objective = 'drawdown_at_most_75pct_spy_and_cagr_at_least_50pct_spy_at_both_costs'
                status = 'retain_for_research' if passed else 'reject_on_this_sample'
        except KeyError:
            output[parent] = dict(decision='incomplete', reason='Required reference diagnostics unavailable', strategy_selected=False)
            continue
        output[parent] = dict(decision=status, objective=objective, objective_passed=passed,
            positive_neighbor_fraction_both_costs=stability, positive_neighbor_trial_fraction=fraction,
            parameter_stable=stability >= Decimal('.75'), stability_threshold='.75', strategy_selected=False,
            note='Selected after prior comparison; already exposed history. No fresh validation or alpha proof.')
    return output


def detail(run, reference, cash_returns, market_leg):
    if [s['session'] for s in run['equity']] != [s['session'] for s in reference['equity']]:
        raise ValueError("Diagnostic portfolio dates differ")
    sessions = [s['session'] for s in run['equity']]
    left = tuple(Decimal(s['session_return']) for s in run['equity'])
    right = tuple(Decimal(s['session_return']) for s in reference['equity'])
    overlay = rm.cash_overlay(run, cash_returns)
    mixed = rm.exposure_match(run, market_leg, cash_returns, equities=overlay['equities'])
    return dict(attribution=rm.attribution(run), rolling=rm.rolling(sessions, left, right, cash_returns),
        recovery=rm.recoveries(sessions, tuple(Decimal(s['equity']) for s in run['equity']), Decimal(run['manifest']['config']['initial_cash'])),
        concentration=rm.concentration(left, right, sessions), regression=rm.regression(left, right, cash_returns),
        cash_overlay={k: v for k, v in overlay.items() if k not in ('returns', 'equities')},
        exposure_matched=paired_metrics(overlay['returns'], mixed),
        exposure_matched_note='Lagged cash-overlay candidate exposure mixes fully invested ex-date-reinvested SPY signal returns and cash proxy; no trade costs; non-executable diagnostic')


def verified_cash_inputs(path):
    metadata = json.loads((path.parent / 'SOURCE.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata['sha256']:
        raise ValueError("Normalized cash input hash mismatch")
    for item in metadata['raw_files']:
        if hashlib.sha256((path.parent / item['file']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError("Raw cash input hash mismatch")
    return metadata, rm.load_rates(path)


def run(snapshot_path, comparison, cash_path, output):
    snapshot = load_snapshot(snapshot_path)
    metadata, rates = verified_cash_inputs(cash_path)
    entries = experiments()
    start = common_start(snapshot, tuple(e['configuration'] for e in entries))
    sessions = tuple(d for d in snapshot.sessions if start <= d <= END)
    intervals = rm.cash_intervals(sessions, rates)
    rf = tuple(r['return'] for r in intervals)
    market_leg = rm.total_return_leg(snapshot, sessions)
    old_results = json.loads((comparison / 'RESULTS.json').read_text())
    old_plan = json.loads((comparison / 'EXPERIMENT_PLAN.json').read_text())
    if content_hash(old_plan) != old_results['plan_hash'] or snapshot.dataset_hash != old_plan['dataset_hash']:
        raise ValueError("Original comparison provenance mismatch")
    original, original_payloads = [], {}
    for old in old_results['trials']:
        if old['window'] == 'common_warmup' and old['scenario'] == 'primary10' and old['recipe'] in PARENTS + REFERENCES:
            payload = verify_run(Path(old['bundle']))
            if old['status'] != 'completed' or content_hash(payload) != old['result_hash']:
                raise ValueError("Original baseline changed/invalid")
            original.append({k: old[k] for k in ('recipe', 'bundle', 'result_hash', 'metrics', 'start', 'end')})
            original_payloads[old['recipe']] = payload
    if len(original) != 5:
        raise ValueError("Expected five original primary portfolios")
    old_sessions = [s['session'] for s in original_payloads[REFERENCES[0]]['equity']]
    old_rf = tuple(r['return'] for r in rm.cash_intervals(old_sessions, rates))
    old_market_leg = rm.total_return_leg(snapshot, old_sessions)
    plan = dict(schema_version=1, purpose='private_robustness_audit_no_tuning_or_nomination',
        dataset_hash=snapshot.dataset_hash, snapshot=str(snapshot_path.resolve()), start=start, end=END,
        original_comparison_plan_hash=old_results['plan_hash'], original_portfolios=original,
        entries=entries, scenarios=SCENARIOS, trial_budget=30, prior_exposure='2016-2026 inspected; parents chosen after ten-recipe comparison',
        source_hashes=source_hashes(), cash_path=str(cash_path.resolve()), cash_source=metadata,
        cash_convention='Strict observation date < interval start; ACT/365 simple yield proxy; max staleness 10 days; fixed orders',
        exposure_match='Prior-session cash-overlay gross exposure times fully invested ex-date-reinvested SPY signal return, remainder cash; zero trade costs; diagnostic only',
        rolling_sessions=252, concentration_days=5, concentration_asset_threshold='.60', neighbor_positive_threshold='.75',
        momentum_objective='Positive historical-reference Sharpe difference vs both references at both costs',
        trend_objective='Drawdown <= 75% SPY; CAGR >= 50% SPY at both costs',
        fresh_final_test=False, strategy_selected=False, production_nomination=False,
        limitations=snapshot.metadata.limitations, controls_note='ATR profile bundles sizing, fixed stops and admission controls; no isolated stop-effect claim')
    output.mkdir(parents=True, exist_ok=False)
    plan, plan_hash = register_plan(output, plan)
    publish(output / 'CASH_INTERVALS.json', {'source': metadata, 'intervals': intervals})
    audits = [dict(window='original', recipe=name, **audit_ledger(snapshot, payload)) for name, payload in original_payloads.items()]
    trials, payloads = [], {}
    for scenario, cost in SCENARIOS:
        execution = ExecutionProfile(cost, '0', '0')
        for entry in entries:
            recipe = entry['configuration']
            key = scenario + '_' + recipe.name
            row = dict(recipe=recipe.name, parent=entry['parent'], role=entry['role'], scenario=scenario,
                       status='started', plan_hash=plan_hash, start=start, end=END)
            publish(output / (key + '.started.json'), row)
            try:
                if source_hashes() != plan['source_hashes']:
                    raise ValueError("Source changed after audit registration")
                config = RunConfig('100000', execution, recipe.universe, start, END, risk=entry['risk'])
                source = WarmupDistributionStrategy(build_strategy(snapshot, recipe, start, execution))
                result = run_backtest(snapshot, source, config)
                folder = output / 'runs' / scenario / recipe.name
                save_run(result, folder)
                payload = verify_run(folder)
                if content_hash(payload) != result.result_hash:
                    raise ValueError("Saved result mismatch")
                checks = audit_ledger(snapshot, payload)
                audits.append(dict(window='matched', recipe=recipe.name, scenario=scenario, **checks))
                row.update(status='completed', bundle=str(folder.resolve()), result_hash=result.result_hash,
                           metrics=summarize_run(result), annual=period_rows(result))
                payloads[scenario, recipe.name] = payload
            except Exception as exc:
                row.update(status='failed', error_type=type(exc).__name__, error=str(exc))
            publish(output / (key + '.completed.json'), row)
            trials.append(row)
            print(canonical_json(dict(trial=len(trials), of=30, recipe=recipe.name, scenario=scenario,
                                      status=row['status'], error=row.get('error'))), flush=True)
    publish(output / 'INDEPENDENT_LEDGER_AUDIT.json', {'dataset_hash': snapshot.dataset_hash, 'trials': audits})
    publish(output / 'TRIAL_RESULTS.json', {'plan_hash': plan_hash, 'trials': trials})
    details = {}
    for scenario, _ in SCENARIOS:
        refs = {name: payloads.get((scenario, name)) for name in REFERENCES}
        ref_rows = {r['recipe']: r for r in trials if r['scenario'] == scenario and r['role'] == 'reference' and r['status'] == 'completed'}
        for row in trials:
            if row['scenario'] != scenario or row['status'] != 'completed':
                continue
            payload = payloads[scenario, row['recipe']]
            returns = tuple(Decimal(s['session_return']) for s in payload['equity'])
            overlay = rm.cash_overlay(payload, rf)
            row['cash_overlay'] = {k: v for k, v in overlay.items() if k not in ('returns', 'equities')}
            for name, key in ((REFERENCES[0], 'paired_spy'), (REFERENCES[1], 'paired_equal')):
                if refs[name] is not None:
                    other = tuple(Decimal(s['session_return']) for s in refs[name]['equity'])
                    row[key] = rm.regression(returns, other, rf)
            if REFERENCES[0] in ref_rows:
                row['spy_metrics'] = ref_rows[REFERENCES[0]]['metrics']
            if row['role'] == 'parent' and refs[REFERENCES[0]] is not None:
                details[scenario + '_' + row['recipe']] = detail(payload, refs[REFERENCES[0]], rf, market_leg)
    for row in original:
        payload = original_payloads[row['recipe']]
        overlay = rm.cash_overlay(payload, old_rf)
        row['cash_overlay'] = {k: v for k, v in overlay.items() if k not in ('returns', 'equities')}
        if row['recipe'] in PARENTS:
            details['original_' + row['recipe']] = detail(payload, original_payloads[REFERENCES[0]], old_rf, old_market_leg)
    publish(output / 'DIAGNOSTICS.json', {'plan_hash': plan_hash, 'details': details})
    decisions_ = decisions(trials)
    publish(output / 'RESULTS.json', dict(plan_hash=plan_hash, trials=trials, original=original,
        decisions=decisions_, fresh_final_test=False, strategy_selected=False))
    from research.robustness_report import seal_evidence
    names = ['EXPERIMENT_PLAN.json', 'CASH_INTERVALS.json', 'TRIAL_RESULTS.json', 'RESULTS.json',
             'DIAGNOSTICS.json', 'INDEPENDENT_LEDGER_AUDIT.json']
    names.extend(r['scenario'] + '_' + r['recipe'] + suffix for r in trials for suffix in ('.started.json', '.completed.json'))
    seal_evidence(output, names)
    print(canonical_json(dict(statuses=dict(Counter(r['status'] for r in trials)), matched_start=start, decisions=decisions_)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'report'))
    parser.add_argument('--snapshot', type=Path, default=Path('local/market-backtest-2026-10-03/market.snapshot.json'))
    parser.add_argument('--comparison', type=Path, default=Path('local/strategy-comparison-2026-10-03'))
    parser.add_argument('--cash-rates', type=Path, default=Path('local/robustness-inputs-2026-10-03/cash_rates.csv'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'run':
        run(args.snapshot, args.comparison, args.cash_rates, args.output)
    else:
        from research.robustness_report import report
        report(args.output)


if __name__ == '__main__':
    main()
