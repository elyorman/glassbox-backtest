"""Research-only reconciliation of SEC facts against original XBRL instances."""
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
import re
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from quant_core.provenance import primitive, content_hash
from research.market_backtest import publish
from quant_core.data.storage import load_snapshot
from quant_core.data import Split

XBRLI='http://www.xbrl.org/2003/instance'
ISO='http://www.xbrl.org/2003/iso4217'
XSI='http://www.w3.org/2001/XMLSchema-instance'
COMPONENTS={'GrossProfit','Assets','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerExcludingAssessedTax',
    'RevenueFromEnrollmentAndRegistrationFeesExcludingHospitalityEnterprises','CostOfGoodsSold','CostOfGoodsAndServicesSold',
    'CostOfRevenue','StockholdersEquity','CommonStockSharesOutstanding','EntityCommonStockSharesOutstanding',
    'PreferredStockSharesOutstanding','PreferredStockRedemptionValue','PreferredStockLiquidationValue',
    'PreferredStockCarryingValue','PreferredStockValue','NetSales','MembershipFeeRevenue','MembershipFees'}


def merge_duplicate(first,second):
    """Consistent rounded displays retain the observation with greatest accuracy."""
    def accuracy(row):
        d=row['decimals']
        return Decimal('Infinity') if d=='INF' else Decimal(d) if d is not None else None
    a,b=accuracy(first),accuracy(second)
    if a is None or b is None:
        if first['value']!=second['value']:raise ValueError('Duplicate accuracy unavailable')
        return first
    def interval(row,precision):
        if '_lower' in row:return row['_lower'],row['_upper']
        half=Decimal(0) if precision.is_infinite() else Decimal(10)**(-int(precision))/2
        return row['value']-half,row['value']+half
    lo1,hi1=interval(first,a);lo2,hi2=interval(second,b)
    lower,upper=max(lo1,lo2),min(hi1,hi2)
    exact=a.is_infinite() or b.is_infinite()
    if lower>upper or (lower==upper and not exact) or (a==b and first['value']!=second['value']):
        raise ValueError('Conflicting original XBRL facts')
    selected=dict(first if a>=b else second)
    selected['_lower']=lower;selected['_upper']=upper
    return selected


def parse_instance(body):
    """Preserve exact numeric units/contexts; dimensional facts never imply totals."""
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ValueError('Unsupported XBRL entity declarations')
    namespaces={}
    for event,item in ET.iterparse(BytesIO(body),events=('start-ns',)):
        prefix,uri=item
        if prefix in namespaces and namespaces[prefix]!=uri:
            raise ValueError('Unsupported rebound namespace prefix')
        namespaces[prefix]=uri
    root=ET.fromstring(body)
    if root.tag!='{'+XBRLI+'}xbrl':raise ValueError('Not an original XBRL instance')
    contexts={};units={}
    for context in root.findall('{'+XBRLI+'}context'):
        identifier=context.find('{'+XBRLI+'}entity/{'+XBRLI+'}identifier')
        if identifier is None or identifier.get('scheme') not in ('http://www.sec.gov/CIK','https://www.sec.gov/CIK'):
            raise ValueError('Unsupported XBRL issuer identifier')
        period=context.find('{'+XBRLI+'}period')
        instant=period.find('{'+XBRLI+'}instant');start=period.find('{'+XBRLI+'}startDate')
        end=instant if instant is not None else period.find('{'+XBRLI+'}endDate')
        if end is None:continue  # Forever contexts cannot supply dated financial inputs.
        scoped=any(len(n)>0 or (n.text or '').strip() for n in (
            list(context.findall('{'+XBRLI+'}entity/{'+XBRLI+'}segment'))+
            list(context.findall('{'+XBRLI+'}scenario'))))
        item=dict(cik=int(identifier.text),start=None if start is None else date.fromisoformat(start.text.strip()),
            end=date.fromisoformat(end.text.strip()),dimensional=bool(scoped))
        key=context.attrib['id']
        if key in contexts and contexts[key]!=item:raise ValueError('Conflicting XBRL context identifiers')
        contexts[key]=item
    for unit in root.findall('{'+XBRLI+'}unit'):
        measures=unit.findall('{'+XBRLI+'}measure')
        label=None
        if len(unit)==1 and len(measures)==1:
            lexical=measures[0].text.strip()
            prefix,local=lexical.split(':',1) if ':' in lexical else ('',lexical)
            uri=namespaces.get(prefix)
            if uri==ISO and local in ('USD','EUR'):label=local
            elif uri==XBRLI and local=='shares':label='shares'
        key=unit.attrib['id']
        if key in units and units[key]!=label:raise ValueError('Conflicting XBRL units')
        units[key]=label
    rows={}
    for element in root:
        context_id=element.get('contextRef');unit_id=element.get('unitRef')
        if context_id is None or unit_id is None or element.get('{'+XSI+'}nil') in ('true','1'):continue
        if context_id not in contexts or unit_id not in units:raise ValueError('Unresolved XBRL context/unit')
        if units[unit_id] is None:continue
        uri,tag=element.tag[1:].split('}',1)
        if tag not in COMPONENTS:continue
        taxonomy=('us-gaap' if re.fullmatch(r'https?://fasb\.org/us-gaap/[^/]+',uri) else
                  'dei' if re.fullmatch(r'https?://xbrl\.sec\.gov/dei/[^/]+',uri) else uri)
        value=Decimal((element.text or '').strip())
        if not value.is_finite():raise ValueError('Nonfinite original XBRL fact')
        context=contexts[context_id]
        item=dict(taxonomy=taxonomy,tag=tag,units=units[unit_id],value=value,
            context_id=context_id,decimals=element.get('decimals'),**context)
        key=(taxonomy,tag,item['cik'],item['start'],item['end'],item['dimensional'],item['units'])
        # Preserve dimensional facts individually; distinct segment members are not duplicates.
        if item['dimensional']:key+=(context_id,)
        rows[key]=merge_duplicate(rows[key],item) if key in rows else item
    return tuple({k:v for k,v in r.items() if not k.startswith('_')} for r in rows.values())


def matching(records,cik,concept,start,end,units='USD'):
    rows=[r for r in records if (r['taxonomy'],r['tag'])==tuple(concept) and r['cik']==int(cik)
          and not r['dimensional'] and r['start']==start and r['end']==end and r['units']==units]
    if not rows:return None
    if len({r['value'] for r in rows})>1:raise ValueError('Ambiguous original financial context')
    return rows[0]


def reconcile_fact(records,cik,expected):
    start=date.fromisoformat(expected['start']) if expected.get('start') else None
    row=matching(records,cik,('us-gaap',expected['tag']),start,date.fromisoformat(expected['end']),expected['units'])
    if row is None or row['value']!=Decimal(expected['value']):raise ValueError('Original fact differs from aggregate discovery')
    return row


def profitability(records,profile,cik,cutoff,filed):
    if filed>=cutoff or profile['status']=='blocked':return None
    candidates=[]
    for row in records:
        if (row['cik']!=int(cik) or row['dimensional'] or row['units']!='USD' or
                row['start'] is None or row['end'].year!=cutoff.year-1 or
                not 330<=(row['end']-row['start']).days<=380):continue
        start,end=row['start'],row['end']
        assets=matching(records,cik,('us-gaap','Assets'),None,end)
        if assets is None or assets['value']<=0:continue
        components=[];gp=None;method=profile['status']
        if profile['status']=='direct' and (row['taxonomy'],row['tag'])==('us-gaap','GrossProfit'):
            gp=row['value'];components=[row]
        elif profile['status']=='reviewed_derivation':
            for rule in profile['rules']:
                if not date.fromisoformat(rule['from'])<=end<=date.fromisoformat(rule['through']):continue
                if rule.get('gross_profit'):
                    direct=matching(records,cik,rule['gross_profit'],start,end)
                    if direct is not None:
                        gp=direct['value'];components=[direct];method='reviewed_direct'
                    continue
                revenue=matching(records,cik,rule['revenue'],start,end)
                cost=matching(records,cik,rule['cost'],start,end)
                subtract=matching(records,cik,rule['subtract_revenue'],start,end) if rule.get('subtract_revenue') else None
                if revenue is None or cost is None or (rule.get('subtract_revenue') and subtract is None):continue
                gp=revenue['value']-cost['value']-(subtract['value'] if subtract is not None else 0)
                components=[revenue,cost]+([subtract] if subtract is not None else [])
        if gp is not None:candidates.append(dict(start=start,end=end,gross_profit=gp,assets=assets['value'],
            score=gp/assets['value'],components=components+[assets],method=method))
    if not candidates:return None
    end=max(c['end'] for c in candidates);rows=[c for c in candidates if c['end']==end]
    if len({(r['gross_profit'],r['assets']) for r in rows})>1:raise ValueError('Conflicting original annual profitability')
    return rows[0]


def december_shares(records,cik,cutoff,filed):
    if filed>=cutoff:return None
    end=date(cutoff.year-1,12,31)
    concepts={('us-gaap','CommonStockSharesOutstanding'),('dei','EntityCommonStockSharesOutstanding')}
    rows=[r for r in records if (r['taxonomy'],r['tag']) in concepts and r['cik']==int(cik) and
          not r['dimensional'] and r['start'] is None and r['end']==end and r['units']=='shares' and r['value']>0]
    if not rows:return None
    selected=rows[0]
    try:
        for row in rows[1:]:selected=merge_duplicate(selected,row)
    except ValueError as exc:raise ValueError('Disagreeing exact-date outstanding share counts') from exc
    return dict(end=end,value=selected['value'],components=rows,share_basis_reviewed=False,
                selection_method='consistent_declared_accuracy')


def annual_equity(records,cik,cutoff,filed,report_date):
    if filed>=cutoff or not report_date:return None
    end=date.fromisoformat(report_date)
    if end.year!=cutoff.year-1:return None
    parent=matching(records,cik,('us-gaap','StockholdersEquity'),None,end)
    if parent is None:return None
    zero=matching(records,cik,('us-gaap','PreferredStockSharesOutstanding'),None,end,'shares')
    preferred=[r for tag in ('PreferredStockRedemptionValue','PreferredStockLiquidationValue',
        'PreferredStockCarryingValue','PreferredStockValue')
        for r in [matching(records,cik,('us-gaap',tag),None,end)] if r is not None]
    if zero is not None:preferred.append(zero)
    return dict(parent=parent,preferred_components=preferred,
        preferred_status='explicit_zero_outstanding_original_evidence' if zero is not None and zero['value']==0 else
            'issuer_preferred_values_require_valuation_review' if preferred else 'annual_issuer_obligation_review_required')


class UnavailableInstance(ValueError):
    pass


def instance_name(index):
    names=[]
    for item in index['directory']['item']:
        name=item['name']
        if not name.endswith('.xml'):continue
        if '/' in name or '..' in name:raise ValueError('Unsafe original filing name')
        if name=='FilingSummary.xml' or re.fullmatch(r'R\d+\.xml',name) or name.endswith(('_cal.xml','_def.xml','_lab.xml','_pre.xml')):continue
        names.append(name)
    if len(names)!=1:raise UnavailableInstance('Missing or ambiguous original XBRL instance')
    return names[0]


def download_body(path,url,contact):
    meta=path.with_suffix(path.suffix+'.request.json')
    if path.exists() or meta.exists():
        metadata=json.loads(meta.read_text());body=path.read_bytes()
        if (metadata['url']!=url or metadata['status']!=200 or metadata['body_file']!=path.name or
                hashlib.sha256(body).hexdigest()!=metadata['sha256']):
            raise ValueError('Changed/failed original filing cache: '+path.name)
        return body
    if not contact or '@' not in contact or any(c in contact for c in '\r\n'):
        raise ValueError('Declared SEC research contact required')
    if not re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/data/\d+/\d{18}/[^/?]+',url):
        raise ValueError('Unexpected original SEC endpoint')
    for attempt in range(3):
        time.sleep(.55)
        try:
            with urlopen(Request(url,headers={'User-Agent':'QuantPlatformResearch '+contact}),timeout=45) as response:
                body=response.read();status=response.status
        except HTTPError as exc:body=exc.read();status=exc.code
        if status not in (429,500,502,503,504) or attempt==2:break
        time.sleep(2**attempt)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body)
    publish(meta,dict(url=url,status=status,body_file=path.name,sha256=hashlib.sha256(body).hexdigest(),
        retrieved_at=datetime.now(timezone.utc),contact_omitted=True,
        collector_source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(json.dumps({'request':str(path),'status':status,'bytes':len(body)}),flush=True)
    if status!=200:raise ValueError('Original SEC request failed; evidence retained: '+path.name)
    return body


def derive(plan,previous,instances,mappings,splits,document_errors=None):
    """Original component evidence only; no trading or value readiness inference."""
    rows=[];document_errors=document_errors or {}
    for old in previous:
        symbol=old['symbol'];formation=old['formation'];cutoff=date.fromisoformat(formation)
        cik=plan['ciks'][symbol];profile=mappings['profiles'][symbol]
        profits=[];shares=[];equities=[];errors=[];parent=None;aggregate_match=None;preferred=[]
        preferred_status='annual_issuer_obligation_review_required'
        applicable=[(key,d) for key,d in plan['documents'].items() if d['symbol']==symbol and
                    any(use[0]==formation for use in d['uses'])]
        for key,d in applicable:
            records=instances[key];filed=date.fromisoformat(d['filed'])
            if filed>=cutoff:raise ValueError('Registered unavailable original filing')
            if key in document_errors:
                errors.append(dict(document=key,component='original_parse',form=d['form'],error=document_errors[key]))
            if d['form'] in ('10-K','10-K/A'):
                try:
                    profit=profitability(records,profile,cik,cutoff,filed)
                    if profit is not None:profits.append(dict(profit,document=key,accession=d['accession'],filed=filed))
                except ValueError as exc:errors.append(dict(document=key,component='profitability_context',error=str(exc)))
                try:
                    equity=annual_equity(records,cik,cutoff,filed,d.get('report_date'))
                    if equity is not None:equities.append(dict(equity,document=key,filed=filed))
                except ValueError as exc:errors.append(dict(document=key,component='equity_context',error=str(exc)))
            try:
                share=december_shares(records,cik,cutoff,filed)
                if share is not None:shares.append(dict(share,document=key,accession=d['accession'],filed=filed))
            except ValueError as exc:errors.append(dict(document=key,component='shares_context',error=str(exc)))
            previous_profit=old.get('gross_profitability')
            if previous_profit and d['accession']==previous_profit['accession']:
                try:
                    reconcile_fact(records,cik,previous_profit['gross_profit_record'])
                    reconcile_fact(records,cik,previous_profit['assets_record'])
                    aggregate_match=True
                except ValueError as exc:
                    aggregate_match=False;errors.append(dict(document=key,component='aggregate_profit',error=str(exc)))
            previous_parent=old.get('parent_equity')
            if previous_parent and d['accession']==previous_parent['accession']:
                try:parent=dict(reconcile_fact(records,cik,previous_parent),document=key,filed=filed)
                except ValueError as exc:errors.append(dict(document=key,component='parent_equity',error=str(exc)))
        if equities:
            best=max((e['parent']['end'],e['filed']) for e in equities)
            same=[e for e in equities if (e['parent']['end'],e['filed'])==best]
            if len({e['parent']['value'] for e in same})>1:
                errors.append(dict(component='parent_equity',error='Ambiguous annual original equity'))
            else:
                selected=min(same,key=lambda e:e['document'])
                parent=dict(selected['parent'],document=selected['document'],filed=selected['filed'])
                preferred=selected['preferred_components'];preferred_status=selected['preferred_status']
        if any(e['component'] in ('parent_equity','equity_context','original_parse') for e in errors):
            parent=None;preferred=[];preferred_status='annual_issuer_obligation_review_required'
        profit=None;share=None
        if profits:
            best=max((p['end'],p['filed']) for p in profits)
            same=[p for p in profits if (p['end'],p['filed'])==best]
            if len({(p['gross_profit'],p['assets']) for p in same})>1:
                errors.append(dict(component='profitability',error='Ambiguous same-day original vintages'))
            else:profit=min(same,key=lambda p:p['accession'])
        if aggregate_match is False or any(e['component']=='profitability_context' or
                (e['component']=='original_parse' and e['form'] in ('10-K','10-K/A')) for e in errors):
            profit=None
        if shares:
            first=min(s['filed'] for s in shares);same=[s for s in shares if s['filed']==first]
            if len({s['value'] for s in same})>1:
                errors.append(dict(component='december_shares',error='Ambiguous first-published share counts'))
            else:
                share=min(same,key=lambda s:s['accession'])
                share['intervening_splits']=[s for s in splits if s['security_id']==symbol and
                    share['end']<date.fromisoformat(s['session'])<=share['filed']]
                share['later_share_vintages']=[dict(document=s['document'],filed=s['filed'],value=s['value'])
                    for s in shares if s['filed']>first and s['value']!=share['value']]
        if any(e['component'] in ('original_parse','shares_context') for e in errors):share=None
        rows.append(dict(symbol=symbol,formation=formation,in_common_panel=symbol in plan['common_panel'],
            profitability=profit,profitability_status='original_components_reconciled_unqualified' if profit else
                'mapping_blocked' if profile['status']=='blocked' else 'missing_eligible_original_components',
            mapping_reason=profile.get('reason'),previous_profit_reconciled=aggregate_match,
            parent_equity=parent,december_shares=share,errors=errors,
            preferred_components=preferred,preferred_status=preferred_status,value_ready=False,qualified=False))
    coverage=[dict(formation=f,profitability_components=sum(r['in_common_panel'] and r['profitability'] is not None
        for r in rows if r['formation']==f),exact_december_share_components=sum(r['in_common_panel'] and r['december_shares'] is not None
        for r in rows if r['formation']==f),minimum_eligible=mappings['minimum_eligible']) for f in plan['formations']]
    return primitive(dict(plan_hash=content_hash(plan),rows=rows,coverage=coverage,
        profitability_coverage_passed=all(c['profitability_components']>=c['minimum_eligible'] for c in coverage),
        value_ready=False,performance_evaluated=False,production_qualified=False,
        required=['Accounting comparability and original-note review; complete eligible coverage',
                  'Preferred valuation and December share-class/split-basis reconciliation',
                  'Existing price/action/provider gaps and independent-data retest remain pending']))


def primary_names(payloads):
    result={}
    for payload in payloads:
        columns=payload['filings']['recent'] if 'filings' in payload else payload
        for accn,name,form in zip(columns['accessionNumber'],columns.get('primaryDocument',['']*len(columns['accessionNumber'])),columns['form']):
            if form not in ('10-K','10-K/A','10-Q','10-Q/A'):continue
            if name and ('/' in name or '..' in name or '\\' in name):raise ValueError('Unsafe primary original document')
            if name:result[accn]=name
    return result


def make_plan(previous_path,mapping_path):
    from research.sec_fundamentals import verify, read_inputs, filing_index
    verify(previous_path)
    input_plan=json.loads((previous_path/'INPUT_PLAN.json').read_text())
    previous=json.loads((previous_path/'FEASIBILITY.json').read_text())['rows']
    bodies,_=read_inputs(previous_path,input_plan)
    documents={};indexes={};primary_documents={}
    for symbol in input_plan['ciks']:
        payloads=[payload for name,payload in bodies.items() if name.startswith(symbol+'.') and '.facts.' not in name]
        indexes[symbol]=filing_index(payloads)
        primary_documents[symbol]=primary_names(payloads)
    def add(symbol,formation,accn,role):
        filing=indexes[symbol][accn]
        if filing['filed']>=date.fromisoformat(formation):raise ValueError('Unavailable original filing request')
        cik=input_plan['ciks'][symbol];key=cik+'-'+accn
        if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',accn):raise ValueError('Unsafe original accession')
        if key not in documents:documents[key]=dict(symbol=symbol,cik=cik,accession=accn,**primitive(filing),uses=[],
                                                  primary_document=primary_documents[symbol].get(accn))
        use=[formation,role]
        if use not in documents[key]['uses']:documents[key]['uses'].append(use)
    for row in previous:
        symbol,formation=row['symbol'],row['formation'];cutoff=date.fromisoformat(formation)
        annual=[(accn,f) for accn,f in indexes[symbol].items() if f['form'] in ('10-K','10-K/A') and
            f['filed']<cutoff and f['report_date'] and date.fromisoformat(f['report_date']).year==cutoff.year-1]
        if annual:
            accn,_=max(annual,key=lambda item:(item[1]['report_date'],item[1]['filed'],item[0]))
            add(symbol,formation,accn,'annual')
        if row.get('gross_profitability'):add(symbol,formation,row['gross_profitability']['accession'],'previous_profit')
        if row.get('parent_equity'):add(symbol,formation,row['parent_equity']['accession'],'previous_parent')
        for taxonomy,tag in (('us-gaap','CommonStockSharesOutstanding'),('dei','EntityCommonStockSharesOutstanding')):
            facts=bodies[symbol+'.facts.json'].get('facts',{}).get(taxonomy,{}).get(tag,{}).get('units',{}).get('shares',[])
            candidates=[r for r in facts if r['end']==str(date(cutoff.year-1,12,31)) and
                r['filed']<formation and r['form'] in ('10-K','10-K/A','10-Q','10-Q/A') and not r.get('start')]
            if candidates:
                first=min(r['filed'] for r in candidates)
                for r in candidates:
                    if r['filed']==first:add(symbol,formation,r['accn'],'shares_'+taxonomy)
    original_hashes=json.loads((previous_path/'INPUT_HASHES.json').read_text())['files']
    original_hashes.update(json.loads((previous_path/'REPORT_HASHES.json').read_text())['files'])
    original_hashes.update({n:hashlib.sha256((previous_path/n).read_bytes()).hexdigest()
                           for n in ('INPUT_HASHES.json','REPORT_HASHES.json')})
    return primitive(dict(schema_version=1,purpose='original_filing_component_reconciliation',
        previous_path=str(previous_path.resolve()),previous_hashes=original_hashes,
        mapping_path=str(mapping_path.resolve()),mapping_policy='freeze reviewed MAPPINGS.json before component audit; request scope independent of mapping decisions',
        market_snapshot=input_plan['market_snapshot'],market_dataset_hash=input_plan['market_dataset_hash'],
        ciks=input_plan['ciks'],common_panel=input_plan['common_panel'],formations=input_plan['formations'],
        documents={k:documents[k] for k in sorted(documents)},minimum_eligible=10,
        annual_policy='end calendar t-1; 330–380 days; 10-K/K-A; filed strictly before formation',
        share_policy='exact Dec31; first eligible original observation; basis/class unqualified until reviewed',
        discovery_policy='one original instance per SEC directory, excluding linkbases/report XML; no guessing ambiguous files',
        performance_evaluated=False,qualified=False))


def register(output,previous_path,mapping_path):
    plan=make_plan(previous_path,mapping_path);output.mkdir(parents=True,exist_ok=True)
    path=output/'INPUT_PLAN.json'
    if path.exists():
        if json.loads(path.read_text())!=plan:raise ValueError('Original reconciliation registration changed')
    else:publish(path,plan)
    return plan


def collect(output,previous_path,mapping_path,contact,maximum=None):
    plan=register(output,previous_path,mapping_path);raw=output/'raw';raw.mkdir(exist_ok=True)
    collected={}
    for i,(key,d) in enumerate(plan['documents'].items()):
        if maximum is not None and i>=maximum:break
        prefix='https://www.sec.gov/Archives/edgar/data/'+str(int(d['cik']))+'/'+d['accession'].replace('-','')+'/'
        directory=raw/key
        index=json.loads(download_body(directory/'index.json',prefix+'index.json',contact))
        unavailable=None
        try:name=instance_name(index)
        except UnavailableInstance as exc:name=None;unavailable=str(exc)
        if name is not None:download_body(directory/'instance.xml',prefix+name,contact)
        collected[key]=dict(instance_name=name,index_url=prefix+'index.json',instance_url=prefix+name if name else None)
        if unavailable:collected[key]['instance_unavailable']=unavailable
        if name is None or name.endswith('_htm.xml'):
            if not d.get('primary_document'):raise ValueError('No indexed primary inline filing')
            download_body(directory/'primary.html',prefix+d['primary_document'],contact)
            collected[key]['primary_url']=prefix+d['primary_document']
    if len(collected)==len(plan['documents']):
        path=output/'COLLECTION.json'
        if path.exists():
            if json.loads(path.read_text())!={'documents':collected}:raise ValueError('Original collection discovery changed')
        else:publish(path,{'documents':collected})
    print(json.dumps({'registered_documents':len(plan['documents']),'collected_documents':len(collected),
                      'performance_evaluated':False}),flush=True)


def read_evidence(output):
    plan=json.loads((output/'INPUT_PLAN.json').read_text())
    if plan!=make_plan(Path(plan['previous_path']),Path(plan['mapping_path'])):
        raise ValueError('Registered original scope/inputs changed')
    mappings=json.loads((output/'MAPPINGS.json').read_text())
    if set(mappings['profiles'])!=set(plan['ciks']) or mappings['minimum_eligible']!=10:
        raise ValueError('Mapping panel/minimum differs from registered research scope')
    if any(p['status'] not in ('direct','reviewed_derivation','blocked') for p in mappings['profiles'].values()):
        raise ValueError('Unknown accounting review status')
    data=load_snapshot(Path(plan['market_snapshot']))
    if data.dataset_hash!=plan['market_dataset_hash']:raise ValueError('Registered market snapshot changed')
    splits=primitive([a for a in data.actions if isinstance(a,Split)])
    collection=json.loads((output/'COLLECTION.json').read_text())['documents']
    if set(collection)!=set(plan['documents']):raise ValueError('Incomplete original document collection')
    hashes={n:hashlib.sha256((output/n).read_bytes()).hexdigest() for n in ('INPUT_PLAN.json','COLLECTION.json','MAPPINGS.json')}
    instances={};document_errors={}
    for key,d in plan['documents'].items():
        directory=output/'raw'/key;record=collection[key]
        prefix='https://www.sec.gov/Archives/edgar/data/'+str(int(d['cik']))+'/'+d['accession'].replace('-','')+'/'
        instance_url=prefix+record['instance_name'] if record['instance_name'] else None
        if record['index_url']!=prefix+'index.json' or record['instance_url']!=instance_url:
            raise ValueError('Changed original document endpoints')
        requests=[('index.json',record['index_url'])]
        if record['instance_name']:requests.append(('instance.xml',record['instance_url']))
        if record['instance_name'] is None or record['instance_name'].endswith('_htm.xml'):
            if not d.get('primary_document') or record.get('primary_url')!=prefix+d['primary_document']:
                raise ValueError('Missing/changed original inline primary endpoint')
            requests.append(('primary.html',record['primary_url']))
        for name,url in requests:
            path=directory/name;meta=directory/(name+'.request.json');m=json.loads(meta.read_text())
            if m['status']!=200 or m['url']!=url or m['body_file']!=name or hashlib.sha256(path.read_bytes()).hexdigest()!=m['sha256']:
                raise ValueError('Failed/changed original response')
            hashes[str(path.relative_to(output))]=m['sha256']
            hashes[str(meta.relative_to(output))]=hashlib.sha256(meta.read_bytes()).hexdigest()
        try:discovered=instance_name(json.loads((directory/'index.json').read_text()));unavailable=None
        except UnavailableInstance as exc:discovered=None;unavailable=str(exc)
        if discovered!=record['instance_name'] or unavailable!=record.get('instance_unavailable'):
            raise ValueError('Changed original instance discovery')
        try:
            if record['instance_name'] is None:raise UnavailableInstance(unavailable)
            extracted=parse_instance((directory/'instance.xml').read_bytes())
            if record['instance_name'].endswith('_htm.xml'):
                from research.sec_inline import parse_inline, crosscheck
                instances[key]=crosscheck(parse_inline((directory/'primary.html').read_bytes()),extracted)
            else:instances[key]=extracted
        except (ValueError,ArithmeticError,ET.ParseError) as exc:
            instances[key]=();document_errors[key]=str(exc)
    expected={p for p in hashes if p.startswith('raw/')}
    if expected!={str(p.relative_to(output)) for p in (output/'raw').rglob('*') if p.is_file()}:
        raise ValueError('Unexpected/orphan original evidence files')
    previous=json.loads((Path(plan['previous_path'])/'FEASIBILITY.json').read_text())['rows']
    return plan,previous,instances,mappings,splits,hashes,document_errors


def result_for(plan,previous,instances,mappings,splits,document_errors,registration):
    result=derive(plan,previous,instances,mappings,splits,document_errors)
    result['audit_plan_hash']=content_hash(registration)
    result['document_errors']=document_errors
    result['original_documents']=len(instances)
    return result


def sources():
    from research.sec_fundamentals import audit_sources
    return {**audit_sources(),**{'research/'+name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                               for name in ('sec_reconcile.py','sec_inline.py')}}


def render(result):
    from html import escape
    keys=('formation','profitability_components','exact_december_share_components','minimum_eligible')
    coverage=''.join('<tr>'+''.join('<td>'+escape(str(c[k]))+'</td>' for k in keys)+'</tr>' for c in result['coverage'])
    fields=('symbol','formation','profitability_status','mapping_reason','previous_profit_reconciled','preferred_status')
    rows=''.join('<tr>'+''.join('<td>'+escape(str(r.get(k)))+'</td>' for k in fields)+'</tr>' for r in result['rows'])
    return '<!doctype html><meta charset="utf-8"><title>Original filing reconciliation</title><style>body{font:15px system-ui;margin:30px}td,th{padding:7px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Original filing reconciliation</h1><p>No new strategy backtest. SEC-as-reported accounting adaptation, not Compustat replication. Original component proof does not qualify a provider or strategy. Preferred obligations and share-class/split basis remain under review; missing inputs are not zero.</p><p>Profitability coverage passed: '+str(result['profitability_coverage_passed'])+'. Value ready: False. Minimum issuer floor unchanged.</p><h2>Common-panel component coverage</h2><table><tr>'+''.join('<th>'+k+'</th>' for k in keys)+'</tr>'+coverage+'</table><h2>Issuer/formation status</h2><table><tr>'+''.join('<th>'+k+'</th>' for k in fields)+'</tr>'+rows+'</table><p>Full original contexts, arithmetic, parent/share evidence, vintage/split flags and errors: RECONCILIATION.json. Original XML/index/request bodies and hashes remain local.</p><pre>'+escape(json.dumps(result['document_errors'],indent=2))+'</pre>'


def audit(output):
    plan=json.loads((output/'INPUT_PLAN.json').read_text())
    mapping_path=output/'MAPPINGS.json'
    if not mapping_path.exists():
        with mapping_path.open('xb') as stream:stream.write(Path(plan['mapping_path']).read_bytes())
    plan,previous,instances,mappings,splits,hashes,errors=read_evidence(output)
    registration=dict(schema_version=1,input_plan_hash=content_hash(plan),input_files=hashes,sources=sources(),
        performance_evaluated=False,qualified=False)
    path=output/'AUDIT_PLAN.json'
    if path.exists():
        if json.loads(path.read_text())!=registration:raise ValueError('Original audit registration changed')
    else:publish(path,registration)
    result=result_for(plan,previous,instances,mappings,splits,errors,registration)
    publish(output/'RECONCILIATION.json',result)
    publish(output/'INPUT_HASHES.json',{'files':{**hashes,'AUDIT_PLAN.json':hashlib.sha256(path.read_bytes()).hexdigest()}})
    with (output/'REPORT.html').open('x') as stream:stream.write(render(result))
    publish(output/'REPORT_HASHES.json',{'files':{n:hashlib.sha256((output/n).read_bytes()).hexdigest()
        for n in ('RECONCILIATION.json','INPUT_HASHES.json','REPORT.html')}})
    print(json.dumps({'issuer_years':len(result['rows']),'original_documents':len(instances),
        'profitability_coverage_passed':result['profitability_coverage_passed'],'value_ready':False,'performance_evaluated':False}))


def verify(output):
    for name in ('INPUT_HASHES.json','REPORT_HASHES.json'):
        for path,digest in json.loads((output/name).read_text())['files'].items():
            if Path(path).is_absolute() or '..' in Path(path).parts:raise ValueError('Unsafe evidence path')
            if hashlib.sha256((output/path).read_bytes()).hexdigest()!=digest:raise ValueError('Changed original evidence: '+path)
    plan,previous,instances,mappings,splits,hashes,errors=read_evidence(output)
    registration=json.loads((output/'AUDIT_PLAN.json').read_text())
    if registration!=dict(schema_version=1,input_plan_hash=content_hash(plan),input_files=hashes,sources=sources(),
        performance_evaluated=False,qualified=False):raise ValueError('Original audit sources/registration changed')
    hashes['AUDIT_PLAN.json']=hashlib.sha256((output/'AUDIT_PLAN.json').read_bytes()).hexdigest()
    if json.loads((output/'INPUT_HASHES.json').read_text())['files']!=hashes:raise ValueError('Incomplete original input manifest')
    if set(json.loads((output/'REPORT_HASHES.json').read_text())['files'])!={'RECONCILIATION.json','INPUT_HASHES.json','REPORT.html'}:
        raise ValueError('Incomplete original report manifest')
    result=result_for(plan,previous,instances,mappings,splits,errors,registration)
    if result!=json.loads((output/'RECONCILIATION.json').read_text()) or render(result)!=(output/'REPORT.html').read_text():
        raise ValueError('Original derived results disagree with raw evidence')
    return dict(issuer_years=len(result['rows']),original_documents=len(instances),
        profitability_coverage_passed=result['profitability_coverage_passed'],value_ready=False,performance_evaluated=False)


def main():
    import argparse
    import os
    import subprocess
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('plan','collect','audit','verify'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--previous',type=Path,default=Path('local/sec-fundamentals-2026-10-03'))
    parser.add_argument('--mappings',type=Path,default=Path('docs/fundamental_mappings.json'))
    parser.add_argument('--contact',default=os.environ.get('SEC_CONTACT_EMAIL'))
    parser.add_argument('--maximum-documents',type=int,help='Collect first N registered documents; resume without this flag for the full fixed list')
    args=parser.parse_args()
    if args.command=='plan':
        plan=register(args.output,args.previous,args.mappings)
        print(json.dumps({'documents':len(plan['documents']),'issuer_years':len(plan['ciks'])*len(plan['formations']),
                          'performance_evaluated':False}))
    elif args.command=='collect':
        if args.maximum_documents is not None and args.maximum_documents<=0:parser.error('maximum must be positive')
        contact=args.contact or subprocess.check_output(['git','config','user.email'],text=True).strip()
        collect(args.output,args.previous,args.mappings,contact,args.maximum_documents)
    elif args.command=='audit':audit(args.output)
    else:print(json.dumps(verify(args.output)))


if __name__=='__main__':main()
