"""Bounded stock research and gated independent retest; never a production nominee."""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
import hashlib
import json
import shutil
from pathlib import Path

from quant_core.analytics import summarize_run, sharpe
from quant_core.backtest import RunConfig, run_backtest
from quant_core.data.quality import check_quality
from quant_core.data.storage import load_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import content_hash, primitive
from quant_core.reporting import save_run, verify_run
from quant_core.strategies import StrategyConfig, build_strategy, rebalance_dates, benchmark_recipes
from quant_core.validation.contracts import load_document, parse_qualification
from quant_core.validation.statistics import paired_bootstrap, search_diagnostic
from research.market_backtest import publish, saved_model, period_rows
from research.robustness_audit import source_hashes, audit_ledger, detail, verified_cash_inputs
from research.robustness_metrics import cash_intervals, total_return_leg

REFERENCE='broad_market_buy_hold_reserve'
EQUAL='same_universe_equal_weight'
SCENARIOS=(('primary10','10',1),('stress25','25',1),('delay10','10',2))
SOURCES={
 'momentum':'https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x',
 'trend':'https://fairmodel.econ.yale.edu/ec439/mosk.pdf',
 'reversal':'https://www.nber.org/papers/w2533',
 'low_vol':'https://www.hbs.edu/ris/Publication%20Files/Benchmarks%20as%20Limits%20to%20Arbitrage_4c97001f-33d4-426e-8c74-6fbc00b3482e.pdf'}


def entries(stocks):
    base=dict(universe=stocks,top_k=5,min_price='5',min_average_dollar_volume='10000000')
    parents=(StrategyConfig('stock_momentum252_skip21_top5','momentum',**base),
             StrategyConfig('stock_trend_sma200','trend',**base),
             StrategyConfig('stock_reversal5_sma200_top5','reversal',**base),
             StrategyConfig('stock_low_vol126_top5','low_vol',**base))
    result=[]
    for parent,change in zip(parents,({'momentum_lookback':231},{'mean_window':180},{'reversal_window':3},{'volatility_window':105})):
        role='defensive' if parent.family in ('trend','low_vol') else 'return_seeking'
        neighbor=replace(parent,name=parent.name+'_neighbor',**change)
        for cfg,label in ((parent,'parent'),(neighbor,'neighbor')):
            result.append(dict(configuration=primitive(cfg),role=label,parent=parent.name,objective=role,
                               research_source=SOURCES[parent.family],adaptation_not_replication=True))
    for cfg in benchmark_recipes(stocks,'SPY'):
        if cfg.name=='broad_market_buy_hold': continue
        result.append(dict(configuration=primitive(cfg),role='reference',parent=None,objective='reference'))
    return result


def make_plan(data,snapshot_path,readiness_path,cash_path):
    stocks=tuple(s.security_id for s in data.securities if s.security_id!='SPY')
    panel=entries(stocks); required=max(StrategyConfig(**e['configuration']).required_history for e in panel)
    rebalances=rebalance_dates(data.sessions,'month_end')
    start=next(d for d in rebalances if d>=data.sessions[required-1])
    end=data.sessions[-1]
    periods=[dict(name='continuous',start=start,end=end,scenarios=SCENARIOS)]
    for name,lower,upper in (('fold_2017_2019',start,date(2019,12,31)),
                             ('fold_2020_2022',date(2020,1,1),date(2022,12,31)),
                             ('fold_2023_2026',date(2023,1,1),end)):
        first=next(d for d in rebalances if lower<=d<=upper)
        last=max(d for d in data.sessions if first<=d<=upper)
        periods.append(dict(name=name,start=first,end=last,scenarios=SCENARIOS[:2]))
    cashmeta,_=verified_cash_inputs(cash_path)
    return primitive(dict(schema_version=1,purpose='private_exploratory_fixed_stock_research',
        dataset_hash=data.dataset_hash,snapshot=str(snapshot_path.resolve()),source_provider=data.metadata.source,
        readiness_path=str(readiness_path.resolve()),readiness_hash=hashlib.sha256(readiness_path.read_bytes()).hexdigest(),
        stocks=stocks,benchmark='SPY',calendar=data.sessions,start=start,end=end,entries=panel,periods=periods,
        trial_budget=sum(len(p['scenarios'])*len(panel) for p in periods),source_hashes=source_hashes(),
        cash_path=str(cash_path.resolve()),cash_source=cashmeta,
        cash_convention='historical reference only, lagged Treasury ACT/365; actual cash yield zero',
        prior_exposure='2016-2026 market history exposed; survivor panel and canonical adaptation choices are research decisions',
        walk_forward='fixed-rule chronological portfolios with independent cash resets; no parameter fitting or fresh OOS claim',
        objectives={'return_seeking':'positive CAGR and historical-reference Sharpe above BOTH equity references at BOTH costs',
                    'defensive':'positive CAGR; drawdown <=75% and CAGR >=50% of BOTH positive-CAGR equity references at BOTH costs'},
        freeze_rule='Parent objective at both costs, positive neighbor at both, >=2/3 folds pass at BOTH costs, delay passes objective',
        cross_provider_tolerances={'total_return':'.05','daily_return':'.005'},
        uncertainty={'blocks':[20,60],'repetitions':500,'seed':1729,
            'scope':'primary continuous sample only; conditional survivor evidence, no fresh holdout or significance claim; prior ETF search excluded'},
        limitations=data.metadata.limitations,fresh_final_test=False,production_nomination=False))


def expected_panel(plan):
    return {(p['name']+'_'+s[0]+'_'+e['configuration']['name']):(p,s,e)
            for p in plan['periods'] for s in p['scenarios'] for e in plan['entries']}


def validate_trials(plan,trials):
    expected=expected_panel(plan); keys=[t['key'] for t in trials]
    if len(keys)!=len(set(keys)) or set(keys)!=set(expected) or len(keys)!=plan['trial_budget']:
        raise ValueError('Incomplete/duplicate registered trial panel')
    for row in trials:
        p,s,e=expected[row['key']]
        if (row['period']!=p['name'] or row['scenario']!=s[0] or row['recipe']!=e['configuration']['name']
            or row['role']!=e['role'] or row['parent']!=e['parent']
            or row['status'] not in ('completed','failed','invalid_benchmark')):
            raise ValueError('Trial identity/role/status disagrees with registration')


def economic_pass(row,refs,role):
    if row['status']!='completed' or any(r['status']!='completed' for r in refs): return None
    metric=row['metrics']
    if D(metric['cagr_calendar'])<=0: return False
    if role=='return_seeking':
        values=[r.get('sharpe_historical_reference') for r in [row]+refs]
        return all(v is not None for v in values) and all(D(values[0])>D(v) for v in values[1:])
    if role!='defensive': raise ValueError('Unknown economic objective')
    if any(D(r['metrics']['cagr_calendar'])<=0 for r in refs): return None
    return all(D(metric['max_drawdown'])<=D('.75')*D(r['metrics']['max_drawdown'])
               and D(metric['cagr_calendar'])>=D('.5')*D(r['metrics']['cagr_calendar']) for r in refs)


def research_decisions(plan,trials):
    validate_trials(plan,trials); table={(r['period'],r['scenario'],r['recipe']):r for r in trials}; decisions={}
    def passed(period,scenario,cfg,objective):
        return economic_pass(table[period,scenario,cfg],
            [table[period,scenario,name] for name in (REFERENCE,EQUAL)],objective)
    for entry in plan['entries']:
        if entry['role']!='parent': continue
        name=entry['configuration']['name']; objective=entry['objective']
        outcomes=[passed('continuous',s,name,objective) for s in ('primary10','stress25')]
        neighbor=next(e['configuration']['name'] for e in plan['entries'] if e['role']=='neighbor' and e['parent']==name)
        neighbor_positive=all(table['continuous',s,neighbor]['status']=='completed' and
            D(table['continuous',s,neighbor]['metrics']['cagr_calendar'])>0 for s in ('primary10','stress25'))
        folds=[all(passed(p['name'],s,name,objective) is True for s in ('primary10','stress25'))
               for p in plan['periods'] if p['name']!='continuous']
        delay=passed('continuous','delay10',name,objective)
        base=all(v is True for v in outcomes)
        promising=base and neighbor_positive and sum(folds)>=2 and delay is True
        decisions[name]=dict(family=entry['configuration']['family'],objective=objective,
            decision='incomplete' if any(v is None for v in outcomes) else
                     'promising_exploratory_retest_only' if promising else 'reject_on_this_sample',
            objective_passed=base,neighbor_positive=neighbor_positive,
            fold_pass_fraction=str(D(sum(folds))/len(folds)),delay_passed=delay,
            freeze_for_retest=promising,qualified=False)
    return decisions


def verify_cache(snapshot_path,data,readiness):
    if readiness['dataset_hash']!=data.dataset_hash: raise ValueError('Readiness snapshot mismatch')
    for name,digest in data.metadata.input_hashes:
        path=Path(readiness['spy_snapshot']) if name=='spy.snapshot.json' else snapshot_path.parent/name
        if not path.exists(): path=snapshot_path.parent/'raw'/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise ValueError('Pinned data input changed: '+name)


def simulate_trial(data,plan,p,s,entry,output,actions_policy='allow_incomplete_diagnostic'):
    recipe=StrategyConfig(**entry['configuration']); scenario,cost,delay=s
    key=p['name']+'_'+scenario+'_'+recipe.name
    record=dict(key=key,period=p['name'],scenario=scenario,recipe=recipe.name,family=recipe.family,
        parent=entry['parent'],role=entry['role'],start=p['start'],end=p['end'],status='started',plan_hash=content_hash(plan))
    publish(output/(key+'.started.json'),record)
    try:
        if source_hashes()!=plan['source_hashes']: raise ValueError('Source changed after registration')
        execution=ExecutionProfile(cost,'0','0'); start=date.fromisoformat(p['start']); end=date.fromisoformat(p['end'])
        cfg=RunConfig('100000',execution,recipe.universe,start,end,actions_policy=actions_policy,execution_delay_sessions=delay)
        result=run_backtest(data,build_strategy(data,recipe,start,execution),cfg)
        bundle=output/'runs'/key; save_run(result,bundle); payload=verify_run(bundle)
        independent=audit_ledger(data,payload)
        valid=entry['role']!='reference' or recipe.family=='cash' or (any(f.side=='buy' for f in result.fills) and not result.summary.rejected_order_count)
        _,rates=verified_cash_inputs(Path(plan['cash_path']))
        rf=tuple(D(v['return']) for v in cash_intervals(tuple(s.session for s in result.equity),rates))
        historical=sharpe(tuple(s.session_return-c for s,c in zip(result.equity,rf)))
        record.update(status='completed' if valid else 'invalid_benchmark',bundle=str(bundle.resolve()),
            result_hash=content_hash(payload),metrics=primitive(summarize_run(result)),
            sharpe_historical_reference=None if historical is None else str(historical),annual=primitive(period_rows(result)))
        return record,dict(key=key,**independent)
    except (ValueError,ArithmeticError,OSError,KeyError,TypeError) as exc:
        record.update(status='failed',error_type=type(exc).__name__,error=str(exc))
        return record,None


def campaign_uncertainty(plan,trials,rates):
    uncertainty={}; settings=plan['uncertainty']
    primary={r['recipe']:r for r in trials if r['period']=='continuous' and r['scenario']=='primary10'}
    models={name:saved_model(verify_run(Path(r['bundle']))) for name,r in primary.items() if r['status']=='completed'}
    if REFERENCE in models and EQUAL in models:
        rf=tuple(D(v['return']) for v in cash_intervals(tuple(s.session for s in models[REFERENCE].equity),rates))
        excess={name:tuple(s.session_return-c for s,c in zip(model.equity,rf)) for name,model in models.items()}
        for entry in plan['entries']:
            name=entry['configuration']['name']
            if entry['role']=='parent' and name in models:
                uncertainty[name]={ref:[paired_bootstrap(excess[name],excess[ref],block,settings['repetitions'],settings['seed'])
                    for block in settings['blocks']] for ref in (REFERENCE,EQUAL)}
        names=[e['configuration']['name'] for e in plan['entries'] if e['role']!='reference']
        uncertainty['bounded_search']={ref:[search_diagnostic([excess[n] for n in names],excess[ref],block,
            settings['repetitions'],settings['seed']) for block in settings['blocks']]
            for ref in (REFERENCE,EQUAL)} if all(n in models for n in names) else {'status':'incomplete_candidate_panel'}
    else: uncertainty={'status':'invalid_reference'}
    return primitive(uncertainty)


def campaign_diagnostics(data,trials,rates):
    details={}
    reference=next(r for r in trials if r['period']=='continuous' and r['scenario']=='primary10' and r['recipe']==REFERENCE)
    if reference['status']=='completed':
        reference_payload=verify_run(Path(reference['bundle']))
        b=saved_model(reference_payload)
        rf=tuple(D(v['return']) for v in cash_intervals(tuple(s.session for s in b.equity),rates))
        leg=total_return_leg(data,tuple(s.session for s in b.equity))
        for row in trials:
            if row['period']=='continuous' and row['scenario']=='primary10' and row['role']=='parent' and row['status']=='completed':
                details[row['recipe']]=detail(verify_run(Path(row['bundle'])),reference_payload,rf,leg)
    return details


def reuse_registration(plan,reuse):
    """Only repair stock-campaign postprocessing; financial sources/rules stay frozen."""
    previous=json.loads((reuse/'EXPERIMENT_PLAN.json').read_text())
    if {k:v for k,v in plan.items() if k!='source_hashes'}!={k:v for k,v in previous.items() if k!='source_hashes'}:
        raise ValueError('Recovery cannot change registered data/recipes/criteria/settings')
    changed={k for k in set(plan['source_hashes'])|set(previous['source_hashes'])
             if plan['source_hashes'].get(k)!=previous['source_hashes'].get(k)}
    if changed!={'research/stock_campaign.py'}:
        raise ValueError('Recovery permits only campaign postprocessing source change')
    failure=json.loads((reuse/'FINALIZATION_FAILURE.json').read_text())
    archive=Path(failure['registered_source_archive'])
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=previous['source_hashes']['research/stock_campaign.py']:
        raise ValueError('Original registered source archive changed')
    original=json.loads((reuse/'RESULTS.json').read_text())
    if original['plan_hash']!=content_hash(previous): raise ValueError('Original result registration changed')
    validate_trials(previous,original['trials'])
    for row in original['trials']:
        started={k:row[k] for k in ('key','period','scenario','recipe','family','parent','role','start','end')}
        started.update(status='started',plan_hash=content_hash(previous))
        if (json.loads((reuse/(row['key']+'.completed.json')).read_text())!=row
            or json.loads((reuse/(row['key']+'.started.json')).read_text())!=started):
            raise ValueError('Original trial records disagree with original results')
    names=sorted(p.name for p in reuse.glob('*.json'))+[archive.name]
    registration=dict(path=str(reuse.resolve()),plan_hash=content_hash(previous),
        reason='Verified ledger reuse after primitive diagnostic argument repair; no financial resimulation or retuning',
        original_registration_before_outcomes=True,
        files={n:hashlib.sha256((reuse/n).read_bytes()).hexdigest() for n in names})
    return registration,{r['key']:r for r in original['trials']}


def retest_requirements(plan,frozen):
    return dict(plan_hash=content_hash(plan),
        status='awaiting_qualified_independent_data' if frozen else 'blocked_no_promising_candidates',
        frozen_count=len(frozen),qualified_strategies=0,
        required=['Separate provider raw prices/actions/calendar for exactly the frozen panel/window',
                  'Reviewed passed usage/calendar/actions/paydates/identity/sample/delisting capabilities',
                  'Same source/configuration/risk/cost protocol; no retuning; genuine new temporal evidence still required'],
        actual_independent_retest_executed=False,no_purchase_made=True)


def run_campaign(snapshot_path,output,cash_path,reuse=None):
    data=load_snapshot(snapshot_path); readiness_path=snapshot_path.parent/'DATA_READINESS.json'
    readiness=json.loads(readiness_path.read_text()); verify_cache(snapshot_path,data,readiness)
    plan=make_plan(data,snapshot_path,readiness_path,cash_path)
    prior={}
    if reuse is not None:
        registration,prior=reuse_registration(plan,reuse)
        plan['prior_registration']=registration
    output.mkdir(parents=True,exist_ok=False); publish(output/'EXPERIMENT_PLAN.json',plan)
    publish(output/'DATA_READINESS.json',readiness)
    trials=[]; audits=[]
    for p in plan['periods']:
        for s in p['scenarios']:
            for entry in plan['entries']:
                key=p['name']+'_'+s[0]+'_'+entry['configuration']['name']
                if prior:
                    before=prior[key]
                    started={k:before[k] for k in ('key','period','scenario','recipe','family','parent','role','start','end')}
                    publish(output/(key+'.started.json'),dict(started,status='started',plan_hash=content_hash(plan)))
                    record=dict(before,plan_hash=content_hash(plan),reused_from=before['bundle'] if before['status']!='failed' else str(reuse/(key+'.completed.json')))
                    audit=None
                    if before['status']!='failed':
                        payload=verify_run(Path(before['bundle']))
                        if content_hash(payload)!=before['result_hash']: raise ValueError('Original bundle changed before reuse')
                        bundle=output/'runs'/key; shutil.copytree(Path(before['bundle']),bundle)
                        record['bundle']=str(bundle.resolve())
                        audit=dict(key=key,**audit_ledger(data,payload))
                else:
                    record,audit=simulate_trial(data,plan,p,s,entry,output)
                publish(output/(record['key']+'.completed.json'),record); trials.append(record)
                if audit: audits.append(audit)
                print(json.dumps({'trial':len(trials),'of':plan['trial_budget'],'key':record['key'],
                                  'status':record['status'],'error':record.get('error')}),flush=True)
    validate_trials(plan,trials)
    decisions=research_decisions(plan,trials)
    _,rates=verified_cash_inputs(cash_path)
    uncertainty=campaign_uncertainty(plan,trials,rates)
    results=dict(plan_hash=content_hash(plan),trials=trials,decisions=decisions,uncertainty=primitive(uncertainty),
                 strategy_selected=False,fresh_final_test=False)
    publish(output/'RESULTS.json',results); publish(output/'INDEPENDENT_LEDGER_AUDIT.json',{'trials':audits})
    details=campaign_diagnostics(data,trials,rates)
    publish(output/'DIAGNOSTICS.json',{'plan_hash':content_hash(plan),'details':details})
    frozen=[e for e in plan['entries'] if e['role']=='parent' and decisions[e['configuration']['name']]['freeze_for_retest']]
    publish(output/'FROZEN_CANDIDATES.json',{'plan_hash':content_hash(plan),'entries':frozen,'production_nomination':False})
    publish(output/'RETEST_REQUIREMENTS.json',retest_requirements(plan,frozen))
    names=[p.name for p in output.glob('*.json')]
    publish(output/'EVIDENCE_HASHES.json',{'files':{n:hashlib.sha256((output/n).read_bytes()).hexdigest() for n in sorted(names)}})
    print(json.dumps({'statuses':dict(Counter(r['status'] for r in trials)),'frozen_candidates':len(frozen),'decisions':decisions}),flush=True)


def verify_campaign(output):
    plan=json.loads((output/'EXPERIMENT_PLAN.json').read_text()); results=json.loads((output/'RESULTS.json').read_text())
    if results['plan_hash']!=content_hash(plan) or source_hashes()!=plan['source_hashes']: raise ValueError('Plan/source hash mismatch')
    prior={}
    if 'prior_registration' in plan:
        registration=plan['prior_registration']; previous=Path(registration['path'])
        for name,digest in registration['files'].items():
            if hashlib.sha256((previous/name).read_bytes()).hexdigest()!=digest: raise ValueError('Original registered evidence changed')
        recovered,prior=reuse_registration({k:v for k,v in plan.items() if k!='prior_registration'},previous)
        if registration!=recovered: raise ValueError('Recovery registration changed')
    manifest=json.loads((output/'EVIDENCE_HASHES.json').read_text())
    required={'EXPERIMENT_PLAN.json','DATA_READINESS.json','RESULTS.json','INDEPENDENT_LEDGER_AUDIT.json',
              'DIAGNOSTICS.json','FROZEN_CANDIDATES.json','RETEST_REQUIREMENTS.json'}
    required.update(t['key']+suffix for t in results['trials'] for suffix in ('.started.json','.completed.json'))
    if set(manifest['files'])!=required: raise ValueError('Evidence registry incomplete')
    for name,digest in manifest['files'].items():
        if hashlib.sha256((output/name).read_bytes()).hexdigest()!=digest: raise ValueError('Changed campaign evidence '+name)
    data=load_snapshot(Path(plan['snapshot'])); readiness=json.loads((output/'DATA_READINESS.json').read_text())
    if data.dataset_hash!=plan['dataset_hash']: raise ValueError('Dataset changed')
    if hashlib.sha256(Path(plan['readiness_path']).read_bytes()).hexdigest()!=plan['readiness_hash']: raise ValueError('Readiness changed')
    verify_cache(Path(plan['snapshot']),data,readiness)
    cashmeta,rates=verified_cash_inputs(Path(plan['cash_path']))
    if cashmeta!=plan['cash_source']: raise ValueError('Cash provenance changed')
    validate_trials(plan,results['trials']); payloads={}; registered=expected_panel(plan)
    verified_audits=[]
    for row in results['trials']:
        if prior:
            before=prior[row['key']]
            expected=dict(before,plan_hash=content_hash(plan),reused_from=before['bundle'] if before['status']!='failed' else str(previous/(row['key']+'.completed.json')))
            if before['status']!='failed': expected['bundle']=str((output/'runs'/row['key']).resolve())
            if row!=expected: raise ValueError('Recovery changed original financial results')
        p,s,e=registered[row['key']]
        started=dict(key=row['key'],period=p['name'],scenario=s[0],recipe=e['configuration']['name'],
            family=e['configuration']['family'],parent=e['parent'],role=e['role'],start=p['start'],end=p['end'],
            status='started',plan_hash=content_hash(plan))
        if (json.loads((output/(row['key']+'.started.json')).read_text())!=started
            or any(row.get(k)!=v for k,v in started.items() if k!='status')):
            raise ValueError('Registered trial identity changed')
        if json.loads((output/(row['key']+'.completed.json')).read_text())!=row: raise ValueError('Trial record changed')
        if row['status']=='failed': continue
        if Path(row['bundle']).resolve()!=(output/'runs'/row['key']).resolve(): raise ValueError('Unregistered bundle path')
        payload=verify_run(Path(row['bundle']))
        execution=ExecutionProfile(s[1],'0','0')
        cfg=RunConfig('100000',execution,tuple(e['configuration']['universe']),date.fromisoformat(p['start']),
            date.fromisoformat(p['end']),actions_policy='allow_incomplete_diagnostic',execution_delay_sessions=s[2])
        source=build_strategy(data,StrategyConfig(**e['configuration']),cfg.start,execution)
        if (content_hash(payload)!=row['result_hash'] or payload['manifest']['dataset_hash']!=plan['dataset_hash']
             or payload['manifest']['config']!=primitive(cfg) or payload['manifest']['source']!=primitive(source.spec)
             or content_hash(summarize_run(saved_model(payload)))!=content_hash(row['metrics'])):
            raise ValueError('Bundle configuration/result/metrics disagrees with frozen trial')
        model=saved_model(payload)
        valid=e['role']!='reference' or e['configuration']['family']=='cash' or (any(f.side=='buy' for f in model.fills) and not model.summary.rejected_order_count)
        if row['status']!=('completed' if valid else 'invalid_benchmark'):
            raise ValueError('Benchmark status disagrees with audited fills')
        verified_audits.append(dict(key=row['key'],**audit_ledger(data,payload)))
        rf=tuple(D(v['return']) for v in cash_intervals(tuple(s.session for s in model.equity),rates))
        historical=sharpe(tuple(s.session_return-c for s,c in zip(model.equity,rf)))
        if (row['sharpe_historical_reference']!=(None if historical is None else str(historical))
            or row['annual']!=primitive(period_rows(model))):
            raise ValueError('Historical-reference Sharpe/annual metrics changed')
        payloads[row['key']]=payload
    if content_hash(research_decisions(plan,results['trials']))!=content_hash(results['decisions']): raise ValueError('Decision mismatch')
    if results['uncertainty']!=campaign_uncertainty(plan,results['trials'],rates): raise ValueError('Uncertainty changed')
    diagnostics={'plan_hash':content_hash(plan),'details':primitive(campaign_diagnostics(data,results['trials'],rates))}
    if json.loads((output/'DIAGNOSTICS.json').read_text())!=diagnostics: raise ValueError('Diagnostics changed')
    frozen=json.loads((output/'FROZEN_CANDIDATES.json').read_text())
    expected=[e for e in plan['entries'] if e['role']=='parent' and results['decisions'][e['configuration']['name']]['freeze_for_retest']]
    if frozen!={'plan_hash':content_hash(plan),'entries':expected,'production_nomination':False}:
        raise ValueError('Frozen candidates disagree with registered decisions')
    if json.loads((output/'RETEST_REQUIREMENTS.json').read_text())!=retest_requirements(plan,expected):
        raise ValueError('Independent retest requirements disagree with frozen entries')
    audits=json.loads((output/'INDEPENDENT_LEDGER_AUDIT.json').read_text())['trials']
    if (len(audits)!=len(payloads) or {a['key'] for a in audits}!=set(payloads)
        or any(a.get('status')!='passed' for a in audits)
        or audits!=verified_audits):
        raise ValueError('Independent ledger audit panel incomplete/failed')
    return plan,results,payloads


def validate_retest_inputs(plan,data,qualification):
    if (not qualification.passed or qualification.scope!='independent_retest_fixed_sample'
        or qualification.dataset_hash!=data.dataset_hash or qualification.independent_from!=plan['dataset_hash']):
        raise ValueError('Independent qualification incomplete/mismatched')
    if (data.dataset_hash==plan['dataset_hash'] or data.metadata.source==plan['source_provider']
        or data.metadata.source.lower().startswith('alpaca') or not data.metadata.actions_complete):
        raise ValueError('Independent source/actions not qualified')
    if (tuple(d.isoformat() for d in data.sessions)!=tuple(plan['calendar'])
        or set(s.security_id for s in data.securities)!=set(plan['stocks'])|{plan['benchmark']}
        or check_quality(data).has_errors): raise ValueError('Retest panel/calendar/coverage differs')


def compare_retest(row,before,after_model,before_model,objective,tolerances):
    result=dict(recipe=row['recipe'],scenario=row['scenario'],status=row['status'],
        objective_passed=objective,production_nomination=False,fresh_temporal_holdout=False)
    if row['status']!='completed' or before['status']!='completed':
        return dict(result,cross_provider_tolerances_passed=None)
    if tuple(s.session for s in after_model.equity)!=tuple(s.session for s in before_model.equity):
        raise ValueError('Independent equity calendars differ')
    difference=D(row['metrics']['total_return'])-D(before['metrics']['total_return'])
    daily=max(abs(a.session_return-b.session_return) for a,b in zip(after_model.equity,before_model.equity))
    return dict(result,total_return_difference=str(difference),maximum_daily_return_difference=str(daily),
        cross_provider_tolerances_passed=abs(difference)<=D(tolerances['total_return']) and daily<=D(tolerances['daily_return']))


def retest(campaign,snapshot_path,qualification_path,output):
    plan,results,payloads=verify_campaign(campaign)
    frozen=json.loads((campaign/'FROZEN_CANDIDATES.json').read_text())['entries']
    if not frozen: raise ValueError('No promising candidate frozen; independent retest cannot select a different recipe')
    data=load_snapshot(snapshot_path); q=load_document(qualification_path,'qualification',parse_qualification)
    validate_retest_inputs(plan,data,q)
    references=[e for e in plan['entries'] if e['role']=='reference']
    independent_plan=primitive(dict(plan,dataset_hash=data.dataset_hash,snapshot=str(snapshot_path.resolve()),
        original_dataset_hash=plan['dataset_hash'],original_plan_hash=content_hash(plan),qualification=q,
        original_campaign=str(campaign.resolve()),
        qualification_path=str(qualification_path.resolve()),qualification_hash=hashlib.sha256(qualification_path.read_bytes()).hexdigest(),
        entries=frozen+references,periods=plan['periods'][:1],
        trial_budget=3*(len(frozen)+len(references))))
    output.mkdir(parents=True,exist_ok=False); publish(output/'EXPERIMENT_PLAN.json',independent_plan)
    rows=[]; audits=[]
    for s in SCENARIOS:
        for e in independent_plan['entries']:
            r,a=simulate_trial(data,independent_plan,independent_plan['periods'][0],s,e,output,'require_complete')
            publish(output/(r['key']+'.completed.json'),r); rows.append(r)
            if a: audits.append(a)
    validate_trials(independent_plan,rows)
    comparisons=[]
    original={(r['scenario'],r['recipe']):r for r in results['trials'] if r['period']=='continuous'}
    for r in rows:
        before=original[r['scenario'],r['recipe']]
        entry=next(e for e in independent_plan['entries'] if e['configuration']['name']==r['recipe'])
        refs=[next(t for t in rows if t['scenario']==r['scenario'] and t['recipe']==name) for name in (REFERENCE,EQUAL)]
        objective=economic_pass(r,refs,entry['objective']) if entry['role']=='parent' else None
        after_model=saved_model(verify_run(Path(r['bundle']))) if r['status']=='completed' else None
        before_model=saved_model(payloads[before['key']]) if before['status']=='completed' else None
        comparisons.append(compare_retest(r,before,after_model,before_model,objective,plan['cross_provider_tolerances']))
    publish(output/'RESULTS.json',dict(plan_hash=content_hash(independent_plan),trials=rows,comparisons=comparisons,
                                    strategy_selected=False,fresh_final_test=False))
    publish(output/'INDEPENDENT_LEDGER_AUDIT.json',{'trials':audits})
    names=sorted(p.name for p in output.glob('*.json'))
    publish(output/'EVIDENCE_HASHES.json',{'files':{n:hashlib.sha256((output/n).read_bytes()).hexdigest() for n in names}})


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('command',choices=('run','report','verify','retest'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--snapshot',type=Path,default=Path('local/stock-data-2026-10-03-frozen/stock.snapshot.json'))
    p.add_argument('--cash-path',type=Path,default=Path('local/robustness-inputs-2026-10-03/cash_rates.csv'))
    p.add_argument('--campaign',type=Path); p.add_argument('--qualification',type=Path)
    p.add_argument('--reuse-campaign',type=Path,help='Preserve identical registered financial results after campaign finalization repair')
    a=p.parse_args()
    if a.command=='run': run_campaign(a.snapshot,a.output,a.cash_path,a.reuse_campaign)
    elif a.command=='report':
        if 'original_plan_hash' in json.loads((a.output/'EXPERIMENT_PLAN.json').read_text()):
            from research.stock_retest import report_retest
            print(json.dumps(report_retest(a.output)))
        else:
            from research.stock_report import report
            print(json.dumps(report(a.output)))
    elif a.command=='verify':
        if 'original_plan_hash' in json.loads((a.output/'EXPERIMENT_PLAN.json').read_text()):
            from research.stock_retest import verify_retest
            print(json.dumps({'verified_bundles':len(verify_retest(a.output)[2])}))
        else: print(json.dumps({'verified_bundles':len(verify_campaign(a.output)[2])}))
    else:
        if a.campaign is None or a.qualification is None: p.error('--campaign and --qualification required')
        retest(a.campaign,a.snapshot,a.qualification,a.output)


if __name__=='__main__': main()
