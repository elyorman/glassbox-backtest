"""One preregistered high-anchor hypothesis across two exposed stock samples."""
import argparse
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import hashlib
import json
from pathlib import Path
import shutil

from quant_core.backtest import RunConfig
from quant_core.data import number
from quant_core.data.storage import load_snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import content_hash, primitive
from quant_core.reporting import verify_run
from quant_core.strategies import StrategyConfig, benchmark_recipes, build_strategy
from research.market_backtest import publish
from research.robustness_audit import source_hashes, audit_ledger, verified_cash_inputs
from research.source_archive import archive_sources, verify_source_archive
from research import stock_campaign as stock

PARENT='stock_nearness_high252_top5'
MOMENTUM='stock_momentum252_skip21_top5'
PAPER='https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf'
THRESHOLDS={'mean_jaccard':'0.60','mean_rank_spearman':'0.80','daily_return_correlation':'0.80'}


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def high_entries(stocks):
    parent=StrategyConfig(PARENT,'nearness_high',stocks,top_k=5,min_price='5',min_average_dollar_volume='10000000')
    entries=[dict(configuration=primitive(cfg),role=role,parent=PARENT,objective='return_seeking',
        research_source=PAPER,adaptation_not_replication=True) for cfg,role in (
            (parent,'parent'),(replace(parent,name=PARENT+'_neighbor',high_window=231),'neighbor'))]
    entries.extend(dict(configuration=primitive(cfg),role='reference',parent=None,objective='reference')
        for cfg in benchmark_recipes(stocks,'SPY') if cfg.name!='broad_market_buy_hold')
    return entries


def adapt_plan(base):
    plan=deepcopy(base);plan['entries']=high_entries(tuple(base['stocks']))
    plan['trial_budget']=len(plan['entries'])*sum(len(p['scenarios']) for p in plan['periods'])
    plan['source_hashes']=source_hashes();plan['purpose']='private_exploratory_high_anchor_one_hypothesis'
    return primitive(plan)


def correlation(left,right):
    if len(left)!=len(right):raise ValueError('Correlation requires identical sample lengths')
    if len(left)<2 or any(v is None for v in tuple(left)+tuple(right)):return None
    left,right=tuple(map(number,left)),tuple(map(number,right))
    with localcontext() as ctx:
        ctx.prec=28
        a,b=sum(left,D(0))/len(left),sum(right,D(0))/len(right)
        x,y=tuple(v-a for v in left),tuple(v-b for v in right)
        denominator=(sum((v*v for v in x),D(0))*sum((v*v for v in y),D(0))).sqrt()
        return sum((u*v for u,v in zip(x,y)),D(0))/denominator if denominator else None


def rank_correlation(left,right):
    def ranks(values):
        values=tuple(map(number,values));ordered=sorted(values);result={};i=0
        while i<len(ordered):
            j=i+1
            while j<len(ordered) and ordered[j]==ordered[i]:j+=1
            result[ordered[i]]=D(i+1+j)/2;i=j
        return tuple(result[v] for v in values)
    return correlation(ranks(left),ranks(right))


def overlap_diagnostics(high,momentum):
    def signals(run):
        table=defaultdict(dict)
        for row in run['signal_decisions']:
            day,asset=row['session'],row['security_id']
            if asset in table[day]:raise ValueError('Duplicate signal decision')
            table[day][asset]=row
        return table
    a,b=signals(high),signals(momentum)
    if not a or set(a)!=set(b):raise ValueError('Signal sessions must match without dropped dates')
    rows=[];empty=0;undefined_ranks=0
    for day in sorted(a):
        if set(a[day])!=set(b[day]):raise ValueError('Signal security panels differ')
        left={asset for asset,r in a[day].items() if r['selected']}
        right={asset for asset,r in b[day].items() if r['selected']}
        union=left|right;intersection=left&right
        common=sorted(asset for asset in a[day] if a[day][asset]['eligible'] and b[day][asset]['eligible']
                      and a[day][asset]['score'] is not None and b[day][asset]['score'] is not None)
        rho=rank_correlation(tuple(a[day][v]['score'] for v in common),tuple(b[day][v]['score'] for v in common))
        if not union:empty+=1
        if rho is None:undefined_ranks+=1
        rows.append(dict(session=day,high_selected=sorted(left),momentum_selected=sorted(right),
            jaccard=D(len(intersection))/len(union) if union else None,
            exact_set=left==right if union else None,common_scored_names=len(common),rank_spearman=rho))
    equity_high,equity_momentum=high['equity'],momentum['equity']
    dates=[s['session'] for s in equity_high]
    if (not dates or dates!=sorted(set(dates)) or dates!=[s['session'] for s in equity_momentum]):
        raise ValueError('Equity sessions must match without dropped dates')
    returns_high=tuple(s['session_return'] for s in equity_high)
    returns_momentum=tuple(s['session_return'] for s in equity_momentum)
    missing_returns=sum(x is None or y is None for x,y in zip(returns_high,returns_momentum))
    def average(values):
        defined=[v for v in values if v is not None]
        return sum(defined,D(0))/len(defined) if defined else None
    jaccard=average([r['jaccard'] for r in rows]);rho=average([r['rank_spearman'] for r in rows])
    exact=average([D(int(r['exact_set'])) if r['exact_set'] is not None else None for r in rows])
    daily=correlation(returns_high,returns_momentum)
    metrics=dict(mean_jaccard=jaccard,mean_rank_spearman=rho,daily_return_correlation=daily)
    warnings=[name for name,value in metrics.items() if value is not None and value>=D(THRESHOLDS[name])]
    return primitive(dict(metrics,exact_set_fraction=exact,signal_sessions=len(rows),equity_sessions=len(dates),
        empty_union_sessions=empty,undefined_rank_sessions=undefined_ranks,missing_return_intervals=missing_returns,
        thresholds=THRESHOLDS,overlap_warning=bool(warnings),warning_metrics=warnings,
        independent_strategy_established=False,rows=rows))


def register(output):
    repo=Path(__file__).resolve().parents[2]
    inputs=(('original22',repo/'local/stock-engine-replay-2026-10-05'),
            ('transfer47',repo/'local/universe-transfer-2026-10-05-v2'))
    panels=[]
    for label,root in inputs:
        seal=json.loads((root/'COMPLETE.json').read_text())
        for name,value in seal['files'].items():
            if digest(root/name)!=value:raise ValueError('Prior evidence changed: '+name)
        old=json.loads((root/'campaign/EXPERIMENT_PLAN.json').read_text())
        # Source changes are allowed only outside the existing runtime.
        archived=verify_source_archive(root/'source-archive')['files'];current=source_hashes()
        if any(current.get(k)!=v for k,v in archived.items()):raise ValueError('Existing financial/research sources changed')
        data=load_snapshot(Path(old['snapshot']));readiness=json.loads(Path(old['readiness_path']).read_text())
        stock.verify_cache(Path(old['snapshot']),data,readiness)
        base=stock.make_plan(data,Path(old['snapshot']),Path(old['readiness_path']),Path(old['cash_path']))
        ignored={'source_hashes','prior_registration'}
        if {k:v for k,v in base.items() if k not in ignored}!={k:v for k,v in old.items() if k not in ignored}:
            raise ValueError('Baseline protocol changed')
        panels.append(dict(label=label,prior_root=str(root),prior_campaign=str(root/'campaign'),
            prior_complete_hash=digest(root/'COMPLETE.json'),prior_files=seal['files'],plan=adapt_plan(base)))
    output.mkdir(parents=True,exist_ok=False)
    archive=archive_sources(repo,output/'source-archive')
    registration=dict(schema_version=1,registered_at=datetime.now(timezone.utc),panels=panels,
        source_hashes=archive['files'],new_hypotheses=1,new_simulations=36,reused_reference_scenarios=54,
        scenario_entries=90,overlap_thresholds=THRESHOLDS,prior_hypotheses='Four original stock parents plus retained earlier ETF research; one new hypothesis does not reset cumulative selection bias',
        paper=PAPER,paper_review='CRSP 1963-2001; winner/loser 30% rankings, long-short and six-month overlapping holdings; our adjusted-close long-only monthly top5 recipe is an adaptation',
        uncertainty_scope='Existing block-bootstrap diagnostics conditional on this new parent/neighbor, excluding prior hypotheses; no combined-search significance claim',
        fresh_final_test=False,qualified=False,production_nomination=False,
        both_sample_rule='Both samples must pass unchanged full return-seeking freeze rule; this cannot qualify production',
        scripts={p.name:digest(p) for p in output.glob('*.py')})
    publish(output/'REGISTRATION.json',registration)
    publish(output/'REGISTRATION_HASH.json',dict(sha256=digest(output/'REGISTRATION.json')))
    print(json.dumps(dict(registered=True,new_simulations=36,reused_reference_scenarios=54,source_files=len(archive['files']))),flush=True)


def guard_registration(output):
    if digest(output/'REGISTRATION.json')!=json.loads((output/'REGISTRATION_HASH.json').read_text())['sha256']:
        raise ValueError('Registration bytes changed')
    reg=json.loads((output/'REGISTRATION.json').read_text())
    if source_hashes()!=reg['source_hashes'] or verify_source_archive(output/'source-archive')['files']!=reg['source_hashes']:
        raise ValueError('Registered runtime changed')
    for panel in reg['panels']:
        root=Path(panel['prior_root'])
        if digest(root/'COMPLETE.json')!=panel['prior_complete_hash']:raise ValueError('Prior completion seal changed')
        for name,value in panel['prior_files'].items():
            if digest(root/name)!=value:raise ValueError('Prior evidence changed')
    return reg


def reuse_reference(data,plan,p,s,entry,old,output):
    if entry['role']!='reference' or old['status']!='completed':raise ValueError('Only completed registered references may be reused')
    payload=verify_run(Path(old['bundle']));recipe=StrategyConfig(**entry['configuration'])
    execution=ExecutionProfile(s[1],'0','0')
    from datetime import date
    cfg=RunConfig('100000',execution,recipe.universe,date.fromisoformat(p['start']),date.fromisoformat(p['end']),
                  actions_policy='allow_incomplete_diagnostic',execution_delay_sessions=s[2])
    source=build_strategy(data,recipe,cfg.start,execution)
    if (content_hash(payload)!=old['result_hash'] or payload['manifest']['dataset_hash']!=plan['dataset_hash']
        or payload['manifest']['config']!=primitive(cfg) or payload['manifest']['source']!=primitive(source.spec)):
        raise ValueError('Reference data/configuration/source differs from registration')
    key=p['name']+'_'+s[0]+'_'+recipe.name
    if old['key']!=key:raise ValueError('Reference scenario identity differs')
    started=dict(key=key,period=p['name'],scenario=s[0],recipe=recipe.name,family=recipe.family,
        parent=None,role='reference',start=p['start'],end=p['end'],status='started',plan_hash=content_hash(plan))
    publish(output/(key+'.started.json'),started)
    bundle=output/'runs'/key;shutil.copytree(Path(old['bundle']),bundle)
    record=dict(old,plan_hash=content_hash(plan),bundle=str(bundle.resolve()),reused_from=old['bundle'])
    return record,dict(key=key,**audit_ledger(data,payload))


def run_campaigns(output):
    registration=guard_registration(output)
    for panel in registration['panels']:
        plan=panel['plan'];directory=output/panel['label'];directory.mkdir(exist_ok=False)
        data=load_snapshot(Path(plan['snapshot']));readiness=json.loads(Path(plan['readiness_path']).read_text())
        stock.verify_cache(Path(plan['snapshot']),data,readiness)
        publish(directory/'EXPERIMENT_PLAN.json',plan);publish(directory/'DATA_READINESS.json',readiness)
        prior=json.loads((Path(panel['prior_campaign'])/'RESULTS.json').read_text())
        prior_rows={r['key']:r for r in prior['trials']};trials=[];audits=[]
        for p in plan['periods']:
            for s in p['scenarios']:
                for entry in plan['entries']:
                    key=p['name']+'_'+s[0]+'_'+entry['configuration']['name']
                    if entry['role']=='reference':record,audit=reuse_reference(data,plan,p,s,entry,prior_rows[key],directory)
                    else:record,audit=stock.simulate_trial(data,plan,p,s,entry,directory)
                    publish(directory/(key+'.completed.json'),record);trials.append(record)
                    if audit:audits.append(audit)
                    print(json.dumps(dict(panel=panel['label'],trial=len(trials),of=45,status=record['status'],key=key,
                        reused=entry['role']=='reference',error=record.get('error'))),flush=True)
        stock.validate_trials(plan,trials);_,rates=verified_cash_inputs(Path(plan['cash_path']))
        decisions=stock.research_decisions(plan,trials)
        publish(directory/'RESULTS.json',dict(plan_hash=content_hash(plan),trials=trials,decisions=decisions,
            uncertainty=primitive(stock.campaign_uncertainty(plan,trials,rates)),strategy_selected=False,fresh_final_test=False))
        publish(directory/'INDEPENDENT_LEDGER_AUDIT.json',dict(trials=audits))
        publish(directory/'DIAGNOSTICS.json',dict(plan_hash=content_hash(plan),details=stock.campaign_diagnostics(data,trials,rates)))
        frozen=[e for e in plan['entries'] if e['role']=='parent' and decisions[e['configuration']['name']]['freeze_for_retest']]
        publish(directory/'FROZEN_CANDIDATES.json',dict(plan_hash=content_hash(plan),entries=frozen,production_nomination=False))
        publish(directory/'RETEST_REQUIREMENTS.json',stock.retest_requirements(plan,frozen))
        publish(directory/'EVIDENCE_HASHES.json',dict(files={p.name:digest(p) for p in directory.glob('*.json')}))


def verify_campaigns(output):
    registration=guard_registration(output);outcomes={};overlaps={}
    for panel in registration['panels']:
        plan,results,payloads=stock.verify_campaign(output/panel['label'])
        if plan!=panel['plan']:raise ValueError('Campaign differs from prior registration')
        old=json.loads((Path(panel['prior_campaign'])/'RESULTS.json').read_text())
        refs={r['key']:r for r in old['trials'] if r['role']=='reference'}
        for row in results['trials']:
            if row['role']=='reference':
                before=refs[row['key']]
                expected=dict(before,plan_hash=content_hash(plan),bundle=str((output/panel['label']/'runs'/row['key']).resolve()),reused_from=before['bundle'])
                if row!=expected:raise ValueError('Reference origin/metrics changed')
        high=payloads['continuous_primary10_'+PARENT]
        momentum=next(r for r in old['trials'] if r['key']=='continuous_primary10_'+MOMENTUM)
        prior_payload=verify_run(Path(momentum['bundle']))
        if content_hash(prior_payload)!=momentum['result_hash']:raise ValueError('Momentum comparison input changed')
        overlaps[panel['label']]=overlap_diagnostics(high,prior_payload)
        outcomes[panel['label']]=dict(decisions=results['decisions'],trial_count=len(results['trials']),
            verified_bundles=len(payloads),new_simulations=sum(r['role']!='reference' for r in results['trials']),
            references_reused=sum(r['role']=='reference' for r in results['trials']))
    return primitive(dict(panels=outcomes,overlap=overlaps,
        both_samples_pass=all(p['decisions'][PARENT]['freeze_for_retest'] for p in outcomes.values()),
        qualified=False,independent_validation=False,fresh_final_test=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('register','run','verify'));parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='register':register(args.output)
    elif args.command=='run':run_campaigns(args.output)
    else:
        result=verify_campaigns(args.output);publish(args.output/'VERIFICATION.json',result)
        print(json.dumps(dict(panels=result['panels'],both_samples_pass=result['both_samples_pass'])),flush=True)


if __name__=='__main__':main()
