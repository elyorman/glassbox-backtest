"""Research-only SEC annual-fact feasibility; no backtest or qualification claims."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from quant_core.provenance import content_hash, primitive
from quant_core.data.storage import load_snapshot
from quant_core.strategies import rebalance_dates
from research.market_backtest import publish

CIKS={'AAPL':'0000320193','MSFT':'0000789019','AMZN':'0001018724','GOOGL':'0001652044',
 'NVDA':'0001045810','CSCO':'0000858877','XOM':'0000034088','CVX':'0000093410','JNJ':'0000200406',
 'PG':'0000080424','KO':'0000021344','PEP':'0000077476','WMT':'0000104169','COST':'0000909832',
 'HD':'0000354950','CAT':'0000018230','UNP':'0000100885','UPS':'0001090727','MCD':'0000063908'}
COMMON=tuple(a for a in CIKS if a not in ('GOOGL','UPS'))
REVENUE_TAGS=('RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues')
COST_TAGS=('CostOfGoodsAndServicesSold','CostOfRevenue','CostOfGoodsSold')
PREFERRED_TAGS=('PreferredStockRedemptionValue','PreferredStockLiquidationValue',
                'PreferredStockCarryingValue','PreferredStockValue')


def issuer_identity(symbol,cik,submission,facts,formations):
    if int(submission['cik'])!=int(cik) or int(facts['cik'])!=int(cik):
        raise ValueError('SEC issuer CIK mismatch: '+symbol)
    if symbol in submission.get('tickers',[]):
        return dict(status='current_ticker_matches_not_historical_proof',cik=cik)
    # The predecessor's empty current tickers do not erase its historical filings.
    # This exception does not permit joining the successor's future observations.
    if (symbol=='XOM' and cik=='0000034088' and not submission.get('tickers') and
            formations and all(date.fromisoformat(d)<date(2026,7,1) for d in formations)):
        return dict(status='documented_predecessor_for_formation_dates',cik=cik,
            successor_cik='0002115436',effective_date='2026-07-01',exchange_ratio='1:1',
            source='https://www.sec.gov/Archives/edgar/data/2115436/000119312526291990/d71068d8k12b.htm',
            scope='old-issuer annual facts only; market identity/action qualification unchanged')
    raise ValueError('Unreviewed SEC ticker/issuer lineage: '+symbol)


def filing_index(payloads):
    result={}
    for payload in payloads:
        columns=payload['filings']['recent'] if 'filings' in payload else payload
        required=('accessionNumber','filingDate','form','reportDate')
        size=len(columns['accessionNumber'])
        if any(len(columns[k])!=size for k in required):raise ValueError('Ragged filing index')
        accepted=columns.get('acceptanceDateTime',[None]*size)
        if len(accepted)!=size:raise ValueError('Ragged acceptance index')
        for i in range(size):
            row={'filed':date.fromisoformat(columns['filingDate'][i]),'form':columns['form'][i],
                 'report_date':columns['reportDate'][i], 'acceptance_datetime':accepted[i]}
            accn=columns['accessionNumber'][i]
            if accn in result and result[accn]!=row:raise ValueError('Conflicting filing accession')
            result[accn]=row
    return result


def fact_records(facts,index,tag,cutoff,units='USD',duration=None):
    """Only prior-year facts published strictly before the daily decision cutoff."""
    output={}
    rows=facts.get('facts',{}).get('us-gaap',{}).get(tag,{}).get('units',{}).get(units,[])
    for raw in rows:
        end=date.fromisoformat(raw['end']); filed=date.fromisoformat(raw['filed'])
        if end.year!=cutoff.year-1 or filed>=cutoff or raw['form'] not in ('10-K','10-K/A','10-Q','10-Q/A'):continue
        start=date.fromisoformat(raw['start']) if raw.get('start') else None
        if duration=='annual' and (raw['form'] not in ('10-K','10-K/A') or start is None or not 330<=(end-start).days<=380):continue
        if duration=='instant' and start is not None:continue
        accn=raw['accn']; filing=index.get(accn)
        if filing is None or filing['filed']!=filed or filing['form']!=raw['form']:
            raise ValueError('Fact accession/publication disagrees with filing history: '+accn)
        value=Decimal(str(raw['val']))
        if not value.is_finite():raise ValueError('Nonfinite financial fact')
        row=dict(tag=tag,units=units,value=value,start=start,end=end,filed=filed,
                 accession=accn,form=raw['form'],fiscal_label=raw.get('fy'),period_label=raw.get('fp'))
        key=(accn,start,end)
        if key in output and output[key]['value']!=value:raise ValueError('Conflicting values for same fact context')
        output[key]=row
    return tuple(output.values())


def latest(rows):
    if not rows:return None
    best=max((r['end'],r['filed']) for r in rows)
    selected=[r for r in rows if (r['end'],r['filed'])==best]
    values={tuple(r.get(k) for k in ('value','gross_profit','assets','score')) for r in selected}
    if len(values)>1:raise ValueError('Ambiguous same-day financial vintage')
    return min(selected,key=lambda r:r['accession'])


def audit_issuer(facts,index,cutoff):
    """Report coherent components and unresolved mappings, never zero-fill gaps."""
    records={tag:fact_records(facts,index,tag,cutoff,duration='annual')
             for tag in ('GrossProfit',)+REVENUE_TAGS+COST_TAGS}
    assets=fact_records(facts,index,'Assets',cutoff,duration='instant')
    asset_lookup={(r['accession'],r['end']):r for r in assets}
    profit=[];derivations=[]
    for gp in records['GrossProfit']:
        a=asset_lookup.get((gp['accession'],gp['end']))
        if a is not None and a['value']>0:
            profit.append(dict(start=gp['start'],end=gp['end'],filed=gp['filed'],accession=gp['accession'],
                gross_profit=gp['value'],assets=a['value'],score=gp['value']/a['value'],
                gross_profit_record=gp,assets_record=a))
    for revenue_tag in REVENUE_TAGS:
        for revenue in records[revenue_tag]:
            for cost_tag in COST_TAGS:
                for cost in records[cost_tag]:
                    if (revenue['accession'],revenue['start'],revenue['end'])!=(cost['accession'],cost['start'],cost['end']):continue
                    a=asset_lookup.get((revenue['accession'],revenue['end']))
                    if a is None or a['value']<=0:continue
                    derivations.append(dict(accession=revenue['accession'],start=revenue['start'],end=revenue['end'],
                        filed=revenue['filed'],revenue_tag=revenue_tag,cost_tag=cost_tag,
                        revenue=revenue['value'],cost=cost['value'],gross_profit=revenue['value']-cost['value'],
                        assets=a['value'],mapping_reviewed=False))
    annual_contexts={(r['accession'],r['end']) for rows in records.values() for r in rows}
    equity=[r for r in fact_records(facts,index,'StockholdersEquity',cutoff,duration='instant')
            if (r['accession'],r['end']) in annual_contexts]
    preferred={tag:list(fact_records(facts,index,tag,cutoff,duration='instant')) for tag in PREFERRED_TAGS}
    shares=[r for r in fact_records(facts,index,'CommonStockSharesOutstanding',cutoff,units='shares',duration='instant')
            if r['end'].month==12]
    share_values={}
    for r in shares:share_values.setdefault(r['end'],set()).add(r['value'])
    parent=latest(equity); selected=latest(profit)
    return dict(formation=cutoff,fiscal_end_calendar_year=cutoff.year-1,
        gross_profitability=selected,parent_equity=parent,
        positive_parent_equity=None if parent is None else parent['value']>0,
        possible_gross_profit_derivations=derivations,preferred_records=preferred,
        december_outstanding_shares=shares,
        revised_share_dates=[d for d,values in share_values.items() if len(values)>1],
        gross_profitability_status='direct_components_available_unqualified' if selected else
            'derivation_mapping_review_required' if derivations else 'missing_coherent_annual_components',
        value_status='preferred_stock_and_market_equity_review_required' if parent else 'missing_parent_annual_equity',
        qualified=False)


def download(output,name,url,contact):
    """Declared public-data client, <=2 requests/sec, immutable cached bodies."""
    body_path=output/(name+'.json'); metadata_path=output/(name+'.request.json')
    if body_path.exists() or metadata_path.exists():
        metadata=json.loads(metadata_path.read_text())
        if metadata['url']!=url or metadata['status']!=200 or hashlib.sha256(body_path.read_bytes()).hexdigest()!=metadata['sha256']:
            raise ValueError('Cached SEC request failed/changed: '+name)
        return json.loads(body_path.read_text(),parse_float=Decimal)
    if not contact or '@' not in contact or any(c in contact for c in '\r\n'):raise ValueError('Declared SEC contact required')
    for attempt in range(3):
        time.sleep(.55)
        try:
            with urlopen(Request(url,headers={'User-Agent':'QuantPlatformResearch '+contact,'Accept':'application/json'}),timeout=45) as response:
                body=response.read();status=response.status
        except HTTPError as exc:body=exc.read();status=exc.code
        if status not in (429,500,502,503,504) or attempt==2:break
        time.sleep(2**attempt)
    with body_path.open('xb') as stream:stream.write(body)
    publish(metadata_path,dict(url=url,status=status,sha256=hashlib.sha256(body).hexdigest(),
        retrieved_at=datetime.now(timezone.utc),body_file=body_path.name,contact_omitted=True))
    print(json.dumps({'request':name,'status':status,'bytes':len(body)}),flush=True)
    if status!=200:raise ValueError('SEC request failed; response retained: '+name)
    return json.loads(body,parse_float=Decimal)


def input_plan(snapshot_path):
    data=load_snapshot(snapshot_path)
    if set(CIKS)!=set(s.security_id for s in data.securities)-{'SPY','JPM','BAC','GS'}:
        raise ValueError('SEC audit differs from frozen stock panel')
    return dict(schema_version=1,purpose='private_fundamental_data_feasibility',ciks=CIKS,common_panel=COMMON,
        excluded={'JPM/BAC/GS':'financial accounting scope','GOOGL/UPS':'common performance panel excludes multiple share classes'},
        market_snapshot=str(snapshot_path.resolve()),market_dataset_hash=data.dataset_hash,
        formations=[d for d in rebalance_dates(data.sessions,'month_end') if d.month==6 and d.year>=2017],
        filed_policy='strictly before formation day; no intraday availability claim',
        annual_duration_days=[330,380],performance_evaluated=False,qualified=False)


def collect(output,snapshot_path,contact):
    plan=primitive(input_plan(snapshot_path))
    if not output.exists():output.mkdir(parents=True)
    plan_path=output/'INPUT_PLAN.json'
    if plan_path.exists():
        if json.loads(plan_path.read_text())!=plan:raise ValueError('Previously registered SEC scope changed')
    else:publish(plan_path,plan)
    raw=output/'raw';raw.mkdir(exist_ok=True)
    for symbol,cik in CIKS.items():
        submission=download(raw,symbol+'.submissions','https://data.sec.gov/submissions/CIK'+cik+'.json',contact)
        facts=download(raw,symbol+'.facts','https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json',contact)
        issuer_identity(symbol,cik,submission,facts,plan['formations'])
        for archive in submission['filings'].get('files',[]):
            if archive['filingTo']<'2015-01-01' or archive['filingFrom']>'2026-10-03':continue
            name=archive['name']
            if '/' in name or '..' in name or not name.startswith('CIK'+cik+'-submissions-'):raise ValueError('Unexpected submission archive name')
            download(raw,symbol+'.'+name.removesuffix('.json'),'https://data.sec.gov/submissions/'+name,contact)


def read_inputs(output,plan):
    raw=output/'raw';hashes={};bodies={}
    def read(name,url):
        path=raw/(name+'.json');meta=raw/(name+'.request.json')
        m=json.loads(meta.read_text())
        if (m['body_file']!=path.name or m['url']!=url or m['status']!=200 or
                hashlib.sha256(path.read_bytes()).hexdigest()!=m['sha256']):
            raise ValueError('SEC input failed/changed: '+name)
        hashes['raw/'+path.name]=m['sha256'];hashes['raw/'+meta.name]=hashlib.sha256(meta.read_bytes()).hexdigest()
        bodies[path.name]=json.loads(path.read_text(),parse_float=Decimal)
        return bodies[path.name]
    for symbol,cik in plan['ciks'].items():
        submission=read(symbol+'.submissions','https://data.sec.gov/submissions/CIK'+cik+'.json')
        facts=read(symbol+'.facts','https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json')
        issuer_identity(symbol,cik,submission,facts,plan['formations'])
        for archive in submission['filings'].get('files',[]):
            if archive['filingTo']<'2015-01-01' or archive['filingFrom']>'2026-10-03':continue
            name=archive['name']
            if '/' in name or '..' in name or not name.startswith('CIK'+cik+'-submissions-'):
                raise ValueError('Unexpected submission archive name')
            read(symbol+'.'+name.removesuffix('.json'),'https://data.sec.gov/submissions/'+name)
    if set(hashes)!={'raw/'+p.name for p in raw.iterdir() if p.is_file()}:
        raise ValueError('Unexpected/orphan SEC raw evidence files')
    return bodies,hashes


def derive_audit(plan,bodies,audit_plan):
    rows=[]
    for symbol,cik in plan['ciks'].items():
        facts=bodies[symbol+'.facts.json'];submission=bodies[symbol+'.submissions.json'];indexes=[submission]
        identity=issuer_identity(symbol,cik,submission,facts,plan['formations'])
        for archive in submission['filings'].get('files',[]):
            if archive['filingTo']<'2015-01-01' or archive['filingFrom']>'2026-10-03':continue
            indexes.append(bodies[symbol+'.'+archive['name']])
        index=filing_index(indexes)
        for formation in plan['formations']:
            try:row=audit_issuer(facts,index,date.fromisoformat(formation))
            except ValueError as exc:row=dict(formation=formation,error=str(exc),gross_profitability=None,
                gross_profitability_status='invalid_ambiguous_components',value_status='invalid_ambiguous_components',qualified=False)
            rows.append(dict(symbol=symbol,in_common_panel=symbol in plan['common_panel'],identity=identity,**row))
    return primitive(dict(plan_hash=content_hash(plan),audit_plan_hash=content_hash(audit_plan),rows=rows,
        counts=dict(Counter(r['gross_profitability_status'] for r in rows)),
        value_ready=False,production_qualified=False,performance_evaluated=False,
        required=['Issuer-level revenue/cost and preferred/minority-interest review',
                  'December market equity/share-class/split-vintage verification',
                  'Original-filing reconciliation for current aggregate API extraction',
                  'Existing market-price/action and independent-data qualification still pending']))


def render_report(result,plan):
    html_rows=''.join('<tr>'+''.join('<td>'+escape(str(r.get(k,'N/A')))+'</td>' for k in
        ('symbol','formation','in_common_panel','gross_profitability_status','value_status','positive_parent_equity','error'))+'</tr>' for r in result['rows'])
    return '<!doctype html><meta charset="utf-8"><title>SEC fundamental feasibility</title><style>body{font:15px system-ui;margin:30px}td,th{padding:7px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Value and gross-profitability data feasibility</h1><p>No strategy performance evaluated. Historical filing-date filtering is an engineering safeguard; aggregate API extraction and accounting conventions still require original-filing review. No strategy or provider is qualified.</p><p>'+str(len(plan['ciks']))+' nonfinancial issuers audited; proposed common strategy panel has '+str(len(plan['common_panel']))+'. Missing preferred values are not zero; unreviewed revenue/cost mappings do not become profitability signals.</p><pre>'+escape(json.dumps(result['counts'],indent=2))+'</pre><table><tr>'+''.join('<th>'+k+'</th>' for k in ('Symbol','Formation','Common panel','Profitability status','Value status','Positive parent equity','Error'))+'</tr>'+html_rows+'</table><p>Full selected-component evidence and issuer-lineage annotations: FEASIBILITY.json. Raw and report hashes remain local.</p>'


def audit_sources():
    root=Path(__file__).resolve().parents[1]
    paths=list((root/'quant_core').rglob('*.py'))+[root/'research'/n for n in ('market_backtest.py','sec_fundamentals.py')]
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def audit_registration(output,plan,hashes):
    return dict(schema_version=1,input_plan_hash=content_hash(plan),sources=audit_sources(),
        raw_files=hashes,performance_evaluated=False,qualified=False,
        scope='component-availability audit; not original-filing reconciliation or market-equity qualification')


def audit(output):
    plan=json.loads((output/'INPUT_PLAN.json').read_text())
    if plan!=primitive(input_plan(Path(plan['market_snapshot']))):raise ValueError('Registered SEC scope/snapshot changed')
    bodies,hashes=read_inputs(output,plan)
    registration=audit_registration(output,plan,hashes)
    registration_path=output/'AUDIT_PLAN.json'
    if registration_path.exists():
        if json.loads(registration_path.read_text())!=registration:raise ValueError('Registered SEC audit changed')
    else:publish(registration_path,registration)
    result=derive_audit(plan,bodies,registration)
    publish(output/'FEASIBILITY.json',result)
    input_hashes={n:hashlib.sha256((output/n).read_bytes()).hexdigest() for n in ('INPUT_PLAN.json','AUDIT_PLAN.json')}
    publish(output/'INPUT_HASHES.json',{'files':{**input_hashes,**hashes}})
    with (output/'REPORT.html').open('x') as stream:stream.write(render_report(result,plan))
    publish(output/'REPORT_HASHES.json',{'files':{n:hashlib.sha256((output/n).read_bytes()).hexdigest()
        for n in ('FEASIBILITY.json','INPUT_HASHES.json','REPORT.html')}})
    print(json.dumps({'observations':len(result['rows']),'counts':result['counts'],'qualified':False,'performance_evaluated':False}),flush=True)


def verify(output):
    for name in ('INPUT_HASHES.json','REPORT_HASHES.json'):
        for path,digest in json.loads((output/name).read_text())['files'].items():
            if Path(path).is_absolute() or '..' in Path(path).parts:raise ValueError('Invalid SEC evidence path')
            if hashlib.sha256((output/path).read_bytes()).hexdigest()!=digest:raise ValueError('SEC evidence changed: '+path)
    plan=json.loads((output/'INPUT_PLAN.json').read_text());result=json.loads((output/'FEASIBILITY.json').read_text())
    if plan!=primitive(input_plan(Path(plan['market_snapshot']))):raise ValueError('Registered SEC scope/snapshot changed')
    bodies,hashes=read_inputs(output,plan)
    registration=json.loads((output/'AUDIT_PLAN.json').read_text())
    if registration!=audit_registration(output,plan,hashes):raise ValueError('SEC sources/registration changed')
    expected={n:hashlib.sha256((output/n).read_bytes()).hexdigest() for n in ('INPUT_PLAN.json','AUDIT_PLAN.json')}
    if json.loads((output/'INPUT_HASHES.json').read_text())['files']!={**expected,**hashes}:
        raise ValueError('Incomplete SEC input manifest')
    if set(json.loads((output/'REPORT_HASHES.json').read_text())['files'])!={'FEASIBILITY.json','INPUT_HASHES.json','REPORT.html'}:
        raise ValueError('Incomplete SEC report manifest')
    if result!=derive_audit(plan,bodies,registration) or (output/'REPORT.html').read_text()!=render_report(result,plan):
        raise ValueError('SEC derived evidence/report disagrees with inputs')
    return {'verified_observations':len(result['rows']),'performance_evaluated':False,'qualified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('collect','audit','verify'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--snapshot',type=Path,default=Path('local/stock-data-2026-10-03-frozen/stock.snapshot.json'))
    parser.add_argument('--contact',default=os.environ.get('SEC_CONTACT_EMAIL'))
    args=parser.parse_args()
    if args.command=='collect':
        contact=args.contact or subprocess.check_output(['git','config','user.email'],text=True).strip()
        collect(args.output,args.snapshot,contact)
    elif args.command=='audit':audit(args.output)
    else:print(json.dumps(verify(args.output)))


if __name__=='__main__':main()
