"""Frozen CIK evidence collection, including failed/missing original inputs."""
import argparse
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from quant_core.provenance import content_hash,primitive
from research.market_backtest import publish
from research import broad_universe_audit as parent_audit
from research.broad_universe import CHECKS
from research.broad_sec_evidence import archive_requests,joined_history,annual_references,parse_header,issuer_audit

LIMIT=32*1024*1024


def load(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()


def sources():
    return {**parent_audit.sources(),**{'research/'+n:digest(Path(__file__).with_name(n))
        for n in ('broad_sec_evidence.py','broad_sec_audit.py')}}


def make_plan(parent,registered_at):
    if datetime.fromisoformat(registered_at).utcoffset() is None:raise ValueError('Registration requires explicit time offset')
    parent_audit.read_plan(parent)
    manifests=load(parent/'REPORT_HASHES.json')['files']
    if set(manifests)!={'AUDIT_INPUTS.json','ROSTER.json','REPORT.html'} or any(digest(parent/n)!=h for n,h in manifests.items()):
        raise ValueError('Parent discovery report changed/incomplete')
    roster=load(parent/'ROSTER.json')
    if roster['performance_evaluated'] is not False:raise ValueError('Parent performance scope changed')
    samples=[dict(formation=f['formation'],**row) for f in roster['panel']['formations'] for row in f['sample']]
    ciks=sorted({r['cik'] for r in samples});requests={}
    for cik in ciks:
        requests[cik+'.facts.json']=dict(cik=cik,kind='facts',url='https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json')
        requests[cik+'.submissions.json']=dict(cik=cik,kind='submissions',url='https://data.sec.gov/submissions/CIK'+cik+'.json')
    return dict(schema_version=1,purpose='broader_sec_input_evidence',registered_at=registered_at,
        parent=str(parent.resolve()),parent_files={n:digest(parent/n) for n in ('STUDY_PLAN.json','AUDIT_INPUTS.json','ROSTER.json','REPORT.html','REPORT_HASHES.json')},
        sources=sources(),ciks=ciks,samples=samples,requests=requests,minimum_eligible=10,
        annual_period_days=[330,380],fiscal_end_policy='prior calendar year',share_date_policy='exact December31',
        replacement_allowed=False,performance_evaluated=False,qualified=False,
        limitations=['Current API metadata is not historical security proof','Aggregate facts require original accounting review',
                    'Header SIC observations are not reviewed listing/classification evidence','Previously exposed history is not untouched OOS'])


def register(output,parent):
    parent_audit.verify(parent)
    plan=make_plan(parent,now());output.mkdir(parents=True,exist_ok=True);publish(output/'INPUT_PLAN.json',plan)
    return dict(unique_ciks=len(plan['ciks']),sample_rows=len(plan['samples']),root_requests=len(plan['requests']))


def read_plan(output):
    plan=load(output/'INPUT_PLAN.json')
    if plan!=make_plan(Path(plan['parent']),plan['registered_at']):raise ValueError('Registered evidence sample/sources/parent changed')
    return plan


def download(raw,key,url,contact):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',key) or '..' in key:raise ValueError('Unsafe request filename')
    if not (re.fullmatch(r'https://data\.sec\.gov/(?:submissions/CIK[0-9]{10}(?:-submissions-[0-9]+)?\.json|api/xbrl/companyfacts/CIK[0-9]{10}\.json)',url) or
        re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/data/[0-9]{1,10}/[0-9]{18}/[0-9]{10}-[0-9]{2}-[0-9]{6}\.hdr\.sgml',url)):
        raise ValueError('Unexpected SEC evidence endpoint')
    path=raw/key;meta=raw/(key+'.request.json')
    if path.exists() or meta.exists():
        m=load(meta)
        if m['url']!=url or m['body_file']!=key or digest(path)!=m['sha256']:raise ValueError('Cached original response changed')
        return m  # Terminal failures remain failures, never silently retried.
    if not contact or '@' not in contact or any(c in contact for c in '\r\n'):raise ValueError('Declared SEC contact required')
    statuses=[]
    for attempt in range(3):
        time.sleep(.55)
        try:
            with urlopen(Request(url,headers={'User-Agent':'QuantPlatformResearch '+contact}),timeout=45) as response:
                body=response.read(LIMIT+1);status=response.status
        except HTTPError as exc:body=exc.read(LIMIT+1);status=exc.code
        statuses.append(status)
        if status not in (429,500,502,503,504) or attempt==2:break
        time.sleep(2**attempt)
    raw.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body)
    m=dict(url=url,status=status,body_file=key,sha256=digest(path),retrieved_at=now(),
        oversize=len(body)>LIMIT,attempt_statuses=statuses,contact_omitted=True)
    publish(meta,m);print(json.dumps(dict(request=key,status=status,bytes=len(body))),flush=True)
    return m


def read_response(output,key,url,hashes,as_of):
    path=output/'raw'/key;meta=output/'raw'/(key+'.request.json');m=load(meta)
    if m['url']!=url or m['body_file']!=key or digest(path)!=m['sha256']:raise ValueError('Original request metadata/bytes changed')
    retrieved=datetime.fromisoformat(m['retrieved_at'])
    if retrieved.utcoffset() is None or retrieved>datetime.fromisoformat(as_of):raise ValueError('Original response retrieval chronology invalid')
    if type(m['status']) is not int or not 200<=m['status']<=599 or m['attempt_statuses'][-1]!=m['status']:
        raise ValueError('Original terminal status invalid')
    for p in (path,meta):hashes[str(p.relative_to(output))]=digest(p)
    error=None if m['status']==200 and not m['oversize'] else 'HTTP '+str(m['status'])+(' oversized' if m['oversize'] else '')
    return path.read_bytes(),error,m


def json_response(body,error):
    if error:return None,error
    try:
        payload=json.loads(body,parse_float=Decimal)
        if not isinstance(payload,dict):raise ValueError('Expected SEC object')
        return payload,None
    except (ValueError,UnicodeDecodeError) as exc:return None,'Invalid SEC JSON: '+str(exc)


def roots_for(output,plan,hashes,as_of):
    roots={cik:{} for cik in plan['ciks']};errors={};statuses={}
    for key,r in plan['requests'].items():
        body,error,m=read_response(output,key,r['url'],hashes,as_of);payload,error=json_response(body,error)
        roots[r['cik']][r['kind']]=payload
        if error:errors[key]=error
        statuses[key]=m['status']
    return roots,errors,statuses


def history_manifest(plan,roots,hashes):
    requests={};errors={}
    for cik,payloads in roots.items():
        try:
            if payloads['submissions'] is None:raise ValueError('Submissions unavailable')
            for name,row in archive_requests(cik,payloads['submissions']).items():
                requests[cik+'.'+name]=dict(cik=cik,**row)
        except (ValueError,KeyError,TypeError) as exc:errors[cik]=str(exc)
    return dict(input_plan_hash=content_hash(plan),root_files=dict(hashes),requests=requests,issuer_errors=errors)


def histories_for(output,plan,roots,manifest,hashes,errors,statuses,as_of):
    payloads={c:[r['submissions']] for c,r in roots.items()};invalid=dict(manifest['issuer_errors'])
    for key,r in manifest['requests'].items():
        body,error,m=read_response(output,key,r['url'],hashes,as_of);payload,error=json_response(body,error)
        statuses[key]=m['status']
        if error:errors[key]=error;invalid[r['cik']]='Historical archive unavailable: '+key
        else:payloads[r['cik']].append(payload)
    indexes={}
    for cik,payload in payloads.items():
        try:
            if cik in invalid:raise ValueError(invalid[cik])
            indexes[cik]=joined_history(cik,payload)
        except (ValueError,KeyError,TypeError,AttributeError) as exc:indexes[cik]={};invalid[cik]=str(exc)
    return indexes,invalid


def document_manifest(plan,indexes,history_errors,hashes):
    requests={}
    for sample in plan['samples']:
        for row in annual_references(sample,indexes[sample['cik']]):
            if not row['header_required']:continue
            cik=sample['cik'];accn=row['accession'];key=cik+'.'+accn+'.hdr.sgml'
            request=dict(cik=cik,accession=accn,filed=row['filed'],form=row['form'],
                url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace("-","")}/{accn}.hdr.sgml')
            if key in requests and requests[key]!=request:raise ValueError('Conflicting registered original filing')
            requests[key]=request
    return dict(input_plan_hash=content_hash(plan),history_files=dict(hashes),history_errors=history_errors,
        requests=dict(sorted(requests.items())))


def freeze(path,value):
    if path.exists():
        if load(path)!=value:raise ValueError('Frozen evidence phase changed: '+path.name)
    else:publish(path,value)


def collect(output,contact):
    plan=read_plan(output);raw=output/'raw'
    for key,r in plan['requests'].items():download(raw,key,r['url'],contact)
    hashes={};roots,errors,statuses=roots_for(output,plan,hashes,now())
    history=history_manifest(plan,roots,hashes);freeze(output/'HISTORY_PLAN.json',history)
    for key,r in history['requests'].items():download(raw,key,r['url'],contact)
    indexes,invalid=histories_for(output,plan,roots,history,hashes,errors,statuses,now())
    documents=document_manifest(plan,indexes,invalid,hashes);freeze(output/'DOCUMENT_PLAN.json',documents)
    for key,r in documents['requests'].items():download(raw,key,r['url'],contact)
    return dict(root_requests=len(plan['requests']),history_requests=len(history['requests']),header_requests=len(documents['requests']))


def read_inputs(output,as_of):
    plan=read_plan(output);hashes={};roots,errors,statuses=roots_for(output,plan,hashes,as_of)
    history=history_manifest(plan,roots,hashes)
    if load(output/'HISTORY_PLAN.json')!=history:raise ValueError('History collection scope/input bytes changed')
    indexes,invalid=histories_for(output,plan,roots,history,hashes,errors,statuses,as_of)
    documents=document_manifest(plan,indexes,invalid,hashes)
    if load(output/'DOCUMENT_PLAN.json')!=documents:raise ValueError('Original-document collection scope/input bytes changed')
    headers={}
    for key,r in documents['requests'].items():
        body,error,m=read_response(output,key,r['url'],hashes,as_of);statuses[key]=m['status']
        try:
            if error:raise ValueError(error)
            headers[key]=parse_header(body,r['cik'],r)
        except (ValueError,TypeError) as exc:errors[key]=str(exc)
    actual={'raw/'+p.name for p in (output/'raw').iterdir() if p.is_file()}
    if actual!=set(hashes):raise ValueError('Orphan/unregistered original evidence files')
    for n in ('INPUT_PLAN.json','HISTORY_PLAN.json','DOCUMENT_PLAN.json'):hashes[n]=digest(output/n)
    return plan,roots,indexes,invalid,headers,errors,statuses,hashes


def derive(plan,roots,indexes,invalid,headers,errors,statuses,registration):
    rows=[]
    for sample in plan['samples']:
        cik=sample['cik'];row=issuer_audit(sample,roots[cik]['submissions'],roots[cik]['facts'],indexes[cik])
        row['history_error']=invalid.get(cik);row['original_headers']=[]
        for reference in row['references']:
            key=cik+'.'+reference['accession']+'.hdr.sgml';h=headers.get(key)
            conflict=h is not None and reference['report_date'] is not None and h['report_date']!=reference['report_date']
            row['original_headers'].append(dict(accession=reference['accession'],evidence=h,
                status='period_conflict' if conflict else 'observed_unreviewed' if h else
                'unavailable' if reference['header_required'] else 'outside_prior_calendar_year',error=errors.get(key)))
        row['qualification_checks']={check:'missing' for check in CHECKS};rows.append(row)
    coverage=[]
    for formation in sorted({r['formation'] for r in rows}):
        group=[r for r in rows if r['formation']==formation]
        coverage.append(dict(formation=formation,sample_count=len(group),
            direct_gp_observations=sum(bool(r['components'] and r['components']['gross_profitability']) for r in group),
            exact_december_share_observations=sum(bool(r['exact_december_shares']) for r in group),
            header_observations=sum(any(h['status']=='observed_unreviewed' for h in r['original_headers']) for r in group),
            qualified_issuers=0,minimum_eligible=10))
    return primitive(dict(audit_plan_hash=content_hash(registration),input_plan_hash=content_hash(plan),rows=rows,
        coverage=coverage,headers=headers,request_errors=errors,request_status_counts=dict(Counter(str(s) for s in statuses.values())),
        failed_http_requests=sum(s!=200 for s in statuses.values()),unique_ciks=len(plan['ciks']),
        historical_universe_qualified=False,performance_evaluated=False,qualified=False,
        required=['Review original annual financial statements/XBRL and every amendment',
                  'Historical listing, security/classes and nonfinancial classification proof',
                  'Preferred/common book and exact-date market equity/split basis review',
                  'Raw prices, actions, delistings, project-use rights and independent-provider validation',
                  'Separately registered performance study; preserve search history']))


def render(result):
    keys=('formation','sample_count','direct_gp_observations','exact_december_share_observations','header_observations','qualified_issuers','minimum_eligible')
    table=''.join('<tr>'+''.join('<td>'+escape(str(r[k]))+'</td>' for k in keys)+'</tr>' for r in result['coverage'])
    rows=''.join('<tr>'+''.join('<td>'+escape(str(r.get(k)))+'</td>' for k in ('formation','cik','historical_name','history_error','error'))+'</tr>' for r in result['rows'])
    return '<!doctype html><meta charset="utf-8"><title>Broader SEC input evidence</title><style>body{font:15px system-ui;margin:32px}td,th{padding:7px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Broader SEC evidence audit</h1><p>Frozen CIK sample; failed or missing issuers are never replaced. Current tickers/SIC/exchanges are not historical proof. Aggregate component and original-header observations require financial and security review. No strategy performance or historical stock-universe qualification.</p><table><tr>'+''.join('<th>'+k+'</th>' for k in keys)+'</tr>'+table+'</table><h2>Sample evidence gaps</h2><table><tr><th>Formation</th><th>CIK</th><th>Historical name</th><th>History issue</th><th>Component issue</th></tr>'+rows+'</table><h2>Request/schema/header failures</h2><pre>'+escape(json.dumps(result['request_errors'],indent=2))+'</pre><h2>Required next evidence</h2><pre>'+escape(json.dumps(result['required'],indent=2))+'</pre>'


def summary(result):
    return dict(sample_rows=len(result['rows']),unique_ciks=result['unique_ciks'],original_header_observations=len(result['headers']),
        failed_http_requests=result['failed_http_requests'],qualified_rows=0,performance_evaluated=False)


def audit(output):
    if (output/'AUDIT_PLAN.json').exists():raise FileExistsError('Evidence audit already registered')
    as_of=now();inputs=read_inputs(output,as_of);plan=inputs[0]
    registration=dict(input_plan_hash=content_hash(plan),registered_at=as_of,input_files=inputs[-1],sources=sources(),qualified=False)
    publish(output/'AUDIT_PLAN.json',registration);result=derive(*inputs[:-1],registration)
    publish(output/'EVIDENCE.json',result)
    with (output/'REPORT.html').open('x') as stream:stream.write(render(result))
    publish(output/'REPORT_HASHES.json',dict(files={n:digest(output/n) for n in ('AUDIT_PLAN.json','EVIDENCE.json','REPORT.html')}))
    return summary(result)


def verify(output):
    h=load(output/'REPORT_HASHES.json')['files']
    if set(h)!={'AUDIT_PLAN.json','EVIDENCE.json','REPORT.html'} or any(digest(output/n)!=v for n,v in h.items()):raise ValueError('Evidence report manifest changed/incomplete')
    registered=load(output/'AUDIT_PLAN.json');inputs=read_inputs(output,registered['registered_at'])
    expected=dict(input_plan_hash=content_hash(inputs[0]),registered_at=registered['registered_at'],input_files=inputs[-1],sources=sources(),qualified=False)
    if registered!=expected:raise ValueError('Evidence audit input/source registration changed')
    result=derive(*inputs[:-1],registered)
    if load(output/'EVIDENCE.json')!=result or (output/'REPORT.html').read_text()!=render(result):raise ValueError('Evidence report disagrees with original input bodies')
    return summary(result)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('plan','collect','audit','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--parent',type=Path)
    p.add_argument('--contact',default=os.environ.get('SEC_CONTACT_EMAIL'));args=p.parse_args()
    if args.command=='plan':
        if args.parent is None:p.error('--parent required')
        result=register(args.output,args.parent)
    elif args.command=='collect':result=collect(args.output,args.contact or subprocess.check_output(['git','config','user.email'],text=True).strip())
    elif args.command=='audit':result=audit(args.output)
    else:result=verify(args.output)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
