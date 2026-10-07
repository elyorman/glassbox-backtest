"""Finite, retrospective Alpaca universe-transfer research; never qualification."""
import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from quant_core.data.quality import check_quality
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.provenance import content_hash, primitive
from research.alpaca_download import credentials
from research.market_backtest import publish
from research.stock_data import STOCKS, normalize_records

SEED='quant-platform-universe-transfer-v1-2026-10-05'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_roster(body, expected_date, excluded, seed, count):
    if type(count) is not int or count <= 0:
        raise ValueError('Positive integer sample count required')
    lines=body.decode('utf-8-sig').splitlines()
    dated=[r for r in csv.reader(lines) if r and r[0]=='Fund Holdings as of']
    if len(dated)!=1 or dated[0][1]!=expected_date:
        raise ValueError('Holdings response date differs from the registered date')
    starts=[i for i,l in enumerate(lines) if l.startswith('Ticker,Name,')]
    if len(starts)!=1: raise ValueError('Holdings CSV header absent or duplicated')
    records=[]; seen=set()
    for r in csv.DictReader(io.StringIO('\n'.join(lines[starts[0]:]))):
        if r.get('Asset Class')!='Equity': continue
        symbol=r['Ticker']
        if not symbol or symbol=='-' or symbol!=symbol.strip():
            raise ValueError('Unresolved holdings ticker')
        if symbol in seen: raise ValueError('Duplicate equity ticker')
        seen.add(symbol)
        if symbol in excluded: continue
        records.append(dict(Ticker=symbol,Name=r['Name'],Exchange=r.get('Exchange'),
                            selection_hash=hashlib.sha256((seed+':'+symbol).encode()).hexdigest()))
    return sorted(records,key=lambda r:(r['selection_hash'],r['Ticker']))[:count]


def assess_member(symbol, rows, events, spy, observed_at):
    report=dict(symbol=symbol,eligible=False,qualified=False,observations=len(rows))
    try:
        data,readiness=normalize_records({'bars':{symbol:rows}}, {'corporate_actions':events},
            spy.sessions,spy,(symbol,),(),observed_at,True)
        quality=check_quality(data,strict_discontinuities=True)
        errors=[i.code for i in quality.issues if i.severity=='error']
        if errors: raise ValueError(','.join(sorted(set(errors))))
        report.update(eligible=True,reason='complete bars and supported received actions; coverage remains unqualified',
            missing_payable_dates=readiness['missing_payable_dates'],quality=primitive(quality),
            non_position_transforming_actions=readiness['non_position_transforming_actions'])
        return data,report
    except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
        # Missing observations are not a reason to replace the sampled name.
        reason=str(exc)
        if 'Missing/invalid observations' in reason: reason='missing_bar: '+reason
        report.update(reason=reason,error_type=type(exc).__name__)
        return None,report


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_pages(root, name, endpoint, params, headers, budget=40, *, offline=False):
    """One attempt per page; resume only verified cached successes."""
    if endpoint not in ('https://data.alpaca.markets/v2/stocks/bars',
                         'https://data.alpaca.markets/v1/corporate-actions'):
        raise ValueError('Unapproved Alpaca endpoint')
    raw=root/'raw'; raw.mkdir(exist_ok=True)
    amendment=root/'COLLECTION_AMENDMENT.json'
    if amendment.exists():budget=min(budget,json.loads(amendment.read_text())['new_collection_budget'])
    seen=set(); token=None; page=0
    while True:
        query=dict(params)
        if token: query['page_token']=token
        meta=raw/f'{name}.{page:04d}.request.json'; body_path=raw/f'{name}.{page:04d}.json'
        cached=meta.exists()
        if cached:
            m=json.loads(meta.read_text())
            if m['endpoint']!=endpoint or m['parameters']!=query or digest(body_path)!=m['sha256']:
                raise ValueError('Cached request/body binding changed')
            status=m['status']; body=body_path.read_bytes()
        else:
            if offline: raise ValueError('Incomplete cached pagination; normalization cannot download or infer empty responses')
            if body_path.exists(): raise ValueError('Incomplete cached response; retain without overwrite')
            if len(list(raw.glob('*.request.json')))>=budget: raise ValueError('Registered HTTP request budget exhausted')
            time.sleep(.35)
            try:
                with build_opener(NoRedirect()).open(Request(endpoint+'?'+urlencode(query),headers=headers),timeout=45) as response:
                    body,status=response.read(),response.status
            except HTTPError as exc: body,status=exc.read(),exc.code
            except URLError as exc:
                failure=root/f'{name}.{page:04d}.transport-{len(list(root.glob("*.transport-*.json"))):04d}.json'
                publish(failure,dict(endpoint=endpoint,parameters=query,time=datetime.now(timezone.utc),
                                     error_type=type(exc).__name__,reason=str(exc),http_completed=False))
                raise
            with body_path.open('xb') as handle: handle.write(body)
            publish(meta,dict(endpoint=endpoint,parameters=query,status=status,
                retrieved_at=datetime.now(timezone.utc),sha256=digest(body_path),body_file=body_path.name))
        if status!=200: raise ValueError(f'{name} page {page}: HTTP {status}; no retry or replacement')
        payload=json.loads(body,parse_float=Decimal)
        print(json.dumps(dict(request=name,page=page,status=status,cached=cached)),flush=True)
        yield payload
        token=payload.get('next_page_token')
        if not token: return
        if token in seen: raise ValueError('Repeated pagination token')
        seen.add(token); page+=1


def collect(root, env_file, original):
    root.mkdir(exist_ok=True)
    source=root/'holdings-probe-2.csv'
    roster=select_roster(source.read_bytes(),'Oct 02, 2026',STOCKS+('SPY',),SEED,60)
    symbols=tuple(sorted(r['Ticker'] for r in roster))
    request_symbols=tuple(s for s in symbols if re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}',s))
    plan=dict(schema_version=1,registered_at=datetime.now(timezone.utc),
        purpose='private_exploratory_universe_transfer',roster_path=source.name,roster_hash=digest(source),
        roster_date='2026-10-02',roster=roster,symbols=symbols,seed=SEED,
        request_symbols=request_symbols,unsupported_request_symbols=[s for s in symbols if s not in request_symbols],
        original_snapshot=str(original.resolve()),original_hash=digest(original),
        historical_roster_probe_status='legacy route returned HTML; current route ignored requested historical date',
        scope='hash-selected current IVV equity holdings; retrospective survivor-conditioned panel, not historical S&P 500',
        missing_policy='no replacement; exclude unsupported/incomplete members before any portfolio outcome and retain coverage',
        minimum_eligible=10,http_budget=40,no_hidden_retries=True,
        start='2016-01-04',end='2026-10-02',feed='sip',adjustment='raw',qualified=False,
        price_parameters=dict(symbols=','.join(request_symbols),start='2016-01-01',end='2026-10-02T20:00:00Z',
            timeframe='1Day',limit=10000,feed='sip',adjustment='raw',asof='2026-10-03',sort='asc'),
        action_parameters=dict(symbols=','.join(request_symbols),start='2015-01-01',end='2026-12-31',limit=1000,data_quality='all'))
    plan_path=root/'INPUT_PLAN.json'
    if plan_path.exists():
        previous=json.loads(plan_path.read_text())
        if {k:v for k,v in primitive(plan).items() if k!='registered_at'}!={k:v for k,v in previous.items() if k!='registered_at'}:
            raise ValueError('Existing data registration differs')
        plan=previous
    else: publish(plan_path,plan)
    headers=credentials(env_file)
    for name,endpoint,params in (
        ('transfer_bars','https://data.alpaca.markets/v2/stocks/bars',plan['price_parameters']),
        ('transfer_actions','https://data.alpaca.markets/v1/corporate-actions',plan['action_parameters'])):
        for _ in request_pages(root,name,endpoint,params,headers,plan['http_budget']): pass


def member_events(events,symbol):
    return {kind:[v for v in rows if symbol in [value for key,value in v.items() if 'symbol' in key]]
            for kind,rows in events.items()}


def normalize(root):
    plan=json.loads((root/'INPUT_PLAN.json').read_text()); original=Path(plan['original_snapshot'])
    if digest(original)!=plan['original_hash'] or digest(root/plan['roster_path'])!=plan['roster_hash']:
        raise ValueError('Registered original/roster changed')
    spy=load_snapshot(original); bars={}; events={}; hashes=[]; retrievals=[]
    # Validate the entire page chain and exact registered queries before combining.
    for name,endpoint,params in (
        ('transfer_bars','https://data.alpaca.markets/v2/stocks/bars',plan['price_parameters']),
        ('transfer_actions','https://data.alpaca.markets/v1/corporate-actions',plan['action_parameters'])):
        for _ in request_pages(root,name,endpoint,params,{},plan['http_budget'],offline=True): pass
    for meta in sorted((root/'raw').glob('*.request.json')):
        m=json.loads(meta.read_text()); body=root/'raw'/m['body_file']
        if m['status']!=200 or digest(body)!=m['sha256']: raise ValueError('Failed or changed response')
        hashes.extend(((meta.name,digest(meta)),(body.name,digest(body))))
        retrievals.append(datetime.fromisoformat(m['retrieved_at']))
        payload=json.loads(body.read_bytes(),parse_float=Decimal)
        target,key=(bars,'bars') if body.name.startswith('transfer_bars') else (events,'corporate_actions')
        for asset,values in payload[key].items(): target.setdefault(asset,[]).extend(values)
    if not retrievals: raise ValueError('No collection evidence')
    if set(bars)-set(plan['symbols']): raise ValueError('Unexpected stock bars')
    eligible=[]; coverage=[]
    for symbol in plan['symbols']:
        data,report=assess_member(symbol,bars.get(symbol,[]),member_events(events,symbol),spy,max(retrievals))
        if symbol in plan.get('unsupported_request_symbols',[]):
            report.update(eligible=False,reason='Unsupported provider request syntax; original sampled holding retained without replacement')
        coverage.append(report)
        if data is not None: eligible.append(symbol)
    decision=dict(input_plan_hash=content_hash(plan),requested=plan['symbols'],eligible=eligible,coverage=coverage,
        excluded=[r['symbol'] for r in coverage if not r['eligible']],no_replacements=True,qualified=False,
        survivorship_warning='Current holdings plus complete-history exclusions condition the result on survivorship; missing securities are outside simulated returns, not assigned zero.')
    publish(root/'COVERAGE.json',decision)
    with (root/'coverage.csv').open('x') as handle:
        writer=csv.DictWriter(handle,fieldnames=('symbol','eligible','observations','reason'));writer.writeheader()
        writer.writerows({k:r[k] for k in writer.fieldnames} for r in coverage)
    if len(eligible)<plan['minimum_eligible']:
        publish(root/'INFEASIBLE.json',dict(reason='Fewer than ten complete supported sampled names',eligible=len(eligible),qualified=False))
        return
    filtered={}
    for kind,values in events.items():
        filtered[kind]=[v for v in values if any(s in [value for k,value in v.items() if 'symbol' in k] for s in eligible)]
    if (root/'COLLECTION_AMENDMENT.json').exists():
        hashes.append(('COLLECTION_AMENDMENT.json',digest(root/'COLLECTION_AMENDMENT.json')))
    hashes.extend((('INPUT_PLAN.json',digest(root/'INPUT_PLAN.json')),('COVERAGE.json',digest(root/'COVERAGE.json')),
                   (plan['roster_path'],digest(root/plan['roster_path'])),('spy.snapshot.json',digest(original))))
    data,readiness=normalize_records({'bars':{s:bars[s] for s in eligible}},{'corporate_actions':filtered},
        spy.sessions,spy,eligible,tuple(hashes),max(retrievals),True)
    metadata=replace(data.metadata,universe_policy='hash_selected_current_ivv_complete_history_subset',
        limitations=(decision['survivorship_warning'],)+data.metadata.limitations)
    data=replace(data,metadata=metadata); readiness.update(dataset_hash=data.dataset_hash,spy_snapshot=str(original.resolve()),
        panel_scope_decision=decision,quality=primitive(check_quality(data,strict_discontinuities=True)))
    if readiness['quality']['issues'] and any(i['severity']=='error' for i in readiness['quality']['issues']):
        raise ValueError('Combined panel strict quality failed')
    save_snapshot(data,root/'stock.snapshot.json');publish(root/'DATA_READINESS.json',readiness)
    print(json.dumps(dict(status='normalized',requested=len(plan['symbols']),eligible=len(eligible),bars=len(data.bars),
                         missing_payable_dates=len(readiness['missing_payable_dates']),qualified=False)),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('collect','normalize'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,default=Path('.env'))
    parser.add_argument('--original',type=Path,default=Path('local/stock-data-2026-10-03-frozen/stock.snapshot.json'))
    args=parser.parse_args()
    if args.command=='collect': collect(args.output,args.env_file,args.original)
    else: normalize(args.output)


if __name__=='__main__': main()
