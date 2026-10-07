"""Register, collect and semantically verify a bounded broader candidate study."""
import argparse
from datetime import datetime,timezone
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

from quant_core.provenance import content_hash
from research.market_backtest import publish
from research.sec_capital_audit import sources as capital_sources,render as capital_render
from research.broad_universe import parse_index,candidate_panel,input_readiness

ROOT=Path(__file__).resolve().parents[2]
FORMS=('2017-06-30','2018-06-29','2019-06-28','2020-06-30','2021-06-30','2022-06-30','2023-06-30','2024-06-28','2025-06-30','2026-06-30')
LIMIT=32*1024*1024


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def now():return datetime.now(timezone.utc).isoformat()


def sources():
    return {**capital_sources(),**{'research/'+n:digest(Path(__file__).with_name(n))
        for n in ('broad_universe.py','broad_universe_audit.py')}}


def parent_binding(parent):
    names=('AUDIT_PLAN.json','RULES.json','CAPITAL.json','REPORT.html','REPORT_HASHES.json')
    audit=load(parent/'AUDIT_PLAN.json');result=load(parent/'CAPITAL.json');hashes=load(parent/'REPORT_HASHES.json')['files']
    if (audit.get('sources')!=capital_sources() or audit.get('formations')!=list(FORMS) or audit.get('minimum_eligible')!=10 or
        result.get('audit_plan_hash')!=content_hash(audit) or result.get('fixed_panel_infeasible') is not True or
        result.get('performance_evaluated') is not False or set(hashes)!={'CAPITAL.json','REPORT.html'} or
        any(digest(parent/n)!=h for n,h in hashes.items()) or capital_render(result)!=(parent/'REPORT.html').read_text()):
        raise ValueError('Previous verified capital report/sources/scope changed')
    if 'rules_hash' in audit and content_hash(load(parent/'RULES.json'))!=audit['rules_hash']:raise ValueError('Previous capital rules changed')
    return {n:digest(parent/n) for n in names}


def make_plan(parent,registered_at):
    if datetime.fromisoformat(registered_at).utcoffset() is None:raise ValueError('Study registration requires UTC offset')
    requests={}
    for year in range(2016,2027):
        for quarter in range(1,3 if year==2026 else 5):
            key=f'{year}Q{quarter}'
            requests[key]=dict(year=year,quarter=quarter,url=f'https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.gz')
    return dict(schema_version=1,purpose='broader_fundamental_candidate_discovery',registered_at=registered_at,
        parent=str(parent.resolve()),parent_files=parent_binding(parent),sources=sources(),formations=list(FORMS),
        requests=requests,sample_limit=100,sample_seed='quant-platform-broad-fundamentals-v1',minimum_eligible=10,
        annual_period_days=[330,380],fiscal_end_policy='prior calendar year',share_date_policy='exact December31',
        discovery_policy='10-K/10-K/A from Jan1 prior calendar year; filed strictly before formation',
        historical_membership_qualified=False,performance_enabled=False,
        previously_exposed_history='2016–2026 inspected; new universe is not untouched temporal OOS',
        limitations=['Quarterly indexes retrieved now may reflect post-acceptance corrections/deletions',
                    'Filing candidates are not necessarily historical listed common stocks',
                    'No current ticker, exchange, SIC or survival filter; no issuer replacement',
                    'Price/action/identity/project-use and accounting proof must be separately reviewed'])


def register(output,parent):
    plan=make_plan(parent,now());output.mkdir(parents=True,exist_ok=True);publish(output/'STUDY_PLAN.json',plan)
    return dict(index_requests=len(plan['requests']),sample_limit=100,performance_enabled=False)


def read_plan(output):
    plan=load(output/'STUDY_PLAN.json')
    if plan!=make_plan(Path(plan['parent']),plan['registered_at']):raise ValueError('Registered study sources/parent/selection scope changed')
    return plan


def download(path,url,contact):
    meta=path.with_suffix('.request.json')
    if path.exists() or meta.exists():
        r=load(meta)
        if r['url']!=url or r['status']!=200 or r['body_file']!=path.name or digest(path)!=r['sha256']:
            raise ValueError('Cached SEC index response failed/changed: '+path.name)
        return
    if not re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/full-index/20[0-9]{2}/QTR[1-4]/master\.gz',url):
        raise ValueError('Unregistered SEC index endpoint')
    if not contact or '@' not in contact or any(c in contact for c in '\r\n'):raise ValueError('Declared SEC research contact required')
    attempt_statuses=[]
    for attempt in range(3):
        time.sleep(.55)
        try:
            with urlopen(Request(url,headers={'User-Agent':'QuantPlatformResearch '+contact}),timeout=45) as response:
                body=response.read(LIMIT+1);status=response.status
        except HTTPError as exc:body=exc.read(LIMIT+1);status=exc.code
        attempt_statuses.append(status)
        if status not in (429,500,502,503,504) or attempt==2:break
        time.sleep(2**attempt)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body)
    publish(meta,dict(url=url,status=status,body_file=path.name,sha256=digest(path),retrieved_at=now(),
                      contact_omitted=True,oversize=len(body)>LIMIT,attempt_statuses=attempt_statuses))
    print(json.dumps({'index':path.name,'status':status,'bytes':len(body)}),flush=True)
    if status!=200 or len(body)>LIMIT:raise ValueError('SEC index request failed/oversize; original response retained')


def collect(output,contact):
    plan=read_plan(output)
    for key,r in plan['requests'].items():download(output/'raw'/(key+'.gz'),r['url'],contact)
    return dict(registered=len(plan['requests']),collected=len(plan['requests']))


def import_evidence(output,path):
    if path is None:return
    evidence=load(path);publish(output/'EVIDENCE.json',evidence)
    files={n for row in evidence['checks'] for n in row.get('evidence_files',[])}
    for name in sorted(files):
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name or not name or name.endswith('/'):
            raise ValueError('Unsafe readiness proof path')
        source=path.parent/rel
        if source.resolve().is_relative_to(path.parent.resolve()) is False:raise ValueError('Readiness proof outside evidence directory')
        target=output/'evidence'/rel;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(source.read_bytes())


def read_inputs(output,as_of=None):
    plan=read_plan(output);hashes={'STUDY_PLAN.json':digest(output/'STUDY_PLAN.json')};indexes=[];expected=set()
    latest=datetime.fromisoformat(as_of or now())
    if latest.utcoffset() is None:raise ValueError('Audit timing requires an explicit offset')
    for key,r in plan['requests'].items():
        body=output/'raw'/(key+'.gz');meta=output/'raw'/(key+'.request.json');m=load(meta)
        if (m['status']!=200 or m['url']!=r['url'] or m['body_file']!=body.name or
            m.get('oversize',False) or digest(body)!=m['sha256']):raise ValueError('SEC index request/body metadata changed')
        try:retrieved=datetime.fromisoformat(m['retrieved_at'])
        except (KeyError,ValueError,TypeError) as exc:raise ValueError('Original response retrieval time missing/invalid') from exc
        # Prior cached acquisitions may precede a new study registration; none
        # may postdate the frozen audit or predate completion of its quarter.
        next_year=r['year']+(r['quarter']==4);next_month=1 if r['quarter']==4 else r['quarter']*3+1
        earliest=datetime(next_year,next_month,1,tzinfo=timezone.utc)
        if retrieved.utcoffset() is None or retrieved>latest or retrieved<earliest:
            raise ValueError('Original response retrieval chronology inconsistent')
        for path in (body,meta):
            name=str(path.relative_to(output));expected.add(name);hashes[name]=digest(path)
        indexes.append(parse_index(body.read_bytes(),r['year'],r['quarter']))
    if expected!={str(p.relative_to(output)) for p in (output/'raw').rglob('*') if p.is_file()}:
        raise ValueError('Unexpected/orphan original index response')
    evidence=None
    if (output/'EVIDENCE.json').exists():
        evidence=load(output/'EVIDENCE.json');hashes['EVIDENCE.json']=digest(output/'EVIDENCE.json')
        expected={n for row in evidence['checks'] for n in row.get('evidence_files',[])}
        for name in sorted(expected):
            rel=Path(name)
            if rel.is_absolute() or '..' in rel.parts or '\\' in name or not name or name.endswith('/'):
                raise ValueError('Unsafe readiness proof path')
            p=output/'evidence'/rel
            if not p.resolve().is_relative_to((output/'evidence').resolve()):raise ValueError('Readiness proof escapes registered directory')
            hashes['evidence/'+name]=digest(p)
        actual={str(p.relative_to(output/'evidence')) for p in (output/'evidence').rglob('*') if p.is_file()}
        if actual!=expected:raise ValueError('Unregistered readiness proof files')
    elif (output/'evidence').exists() and any((output/'evidence').rglob('*')):raise ValueError('Orphan readiness evidence')
    return plan,indexes,hashes,evidence


def audit_registration(plan,hashes,registered_at):
    return dict(schema_version=1,study_plan_hash=content_hash(plan),registered_at=registered_at,input_files=hashes,
                sources=sources(),performance_enabled=False,qualified=False)


def result_for(plan,indexes,evidence,registration):
    panel=candidate_panel(plan,indexes)
    readiness=input_readiness(plan,panel,evidence,review_cutoff=registration['registered_at'])
    ciks=sorted({r['cik'] for f in panel['formations'] for r in f['sample']})
    followup={cik:dict(companyfacts='https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json',
        submissions='https://data.sec.gov/submissions/CIK'+cik+'.json',collected=False,qualified=False) for cik in ciks}
    return dict(audit_plan_hash=content_hash(registration),study_plan_hash=content_hash(plan),panel=panel,readiness=readiness,
        index_responses=len(indexes),all_index_filing_rows=sum(i['total_rows'] for i in indexes),
        indexed_annual_filings=sum(len(i['annual_filings']) for i in indexes),followup_requests=followup,
        performance_evaluated=False,production_qualified=False)


def render(result):
    columns=('formation','candidate_count','sample_count','complete_review_candidates','minimum_eligible')
    table=''.join('<tr>'+''.join('<td>'+escape(str(r[k]))+'</td>' for k in columns)+'</tr>' for r in result['readiness']['coverage'])
    sample=''.join('<tr><td>'+f['formation']+'</td><td>'+r['cik']+'</td><td>'+escape(r['name_at_latest_filing'])+
        '</td><td>'+r['first_filed']+'</td><td>'+r['last_filed']+'</td></tr>' for f in result['panel']['formations'] for r in f['sample'])
    return '<!doctype html><meta charset="utf-8"><title>Broader fundamental candidates</title><style>body{font:15px system-ui;margin:32px}td,th{padding:7px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Broader fundamental candidate study</h1><p>Filing-dated discovery only. These CIKs are not a qualified historical stock universe. SEC indexes retrieved now can reflect later corrections. Current tickers and returns are not selection inputs.</p><p>At most 100 deterministic review candidates per formation; missing candidates are never replaced. Ten-issuer eligibility floor unchanged. No backtest, provider qualification, purchase or ML training.</p><table><tr>'+''.join('<th>'+c+'</th>' for c in columns)+'</tr>'+table+'</table><h2>Fixed historical review sample</h2><table><tr><th>Formation</th><th>CIK</th><th>Name at last available filing</th><th>First filing</th><th>Last filing</th></tr>'+sample+'</table><p>ROSTER.json preserves the entire unselected roster, original accession/URL evidence, sample hashes, missing checks and uncollected follow-up requests. STUDY_PLAN.json and AUDIT_INPUTS.json bind scope, input bodies and processing sources.</p><pre>'+escape(json.dumps(result['readiness']['required'],indent=2))+'</pre>'


def summary(result):
    return dict(index_responses=result['index_responses'],indexed_annual_filings=result['indexed_annual_filings'],
        unique_review_ciks=len(result['followup_requests']),sample_issuer_formations=sum(f['sample_count'] for f in result['panel']['formations']),
        ready_for_performance=False,performance_evaluated=False)


def audit(output,evidence_path=None):
    if (output/'AUDIT_INPUTS.json').exists() or (output/'ROSTER.json').exists():raise FileExistsError('Audit registration/results already exist')
    import_evidence(output,evidence_path)
    plan,indexes,hashes,evidence=read_inputs(output)
    registration=audit_registration(plan,hashes,now());publish(output/'AUDIT_INPUTS.json',registration)
    result=result_for(plan,indexes,evidence,registration);publish(output/'ROSTER.json',result)
    with (output/'REPORT.html').open('x') as stream:stream.write(render(result))
    publish(output/'REPORT_HASHES.json',{'files':{n:digest(output/n) for n in ('AUDIT_INPUTS.json','ROSTER.json','REPORT.html')}})
    return summary(result)


def verify(output):
    hashes=load(output/'REPORT_HASHES.json')['files']
    if set(hashes)!={'AUDIT_INPUTS.json','ROSTER.json','REPORT.html'} or any(digest(output/n)!=h for n,h in hashes.items()):
        raise ValueError('Broader study report manifest changed/incomplete')
    registered=load(output/'AUDIT_INPUTS.json')
    plan,indexes,input_files,evidence=read_inputs(output,as_of=registered['registered_at'])
    if registered!=audit_registration(plan,input_files,registered['registered_at']):raise ValueError('Broader study input/source registration changed')
    result=result_for(plan,indexes,evidence,registered)
    if load(output/'ROSTER.json')!=result or (output/'REPORT.html').read_text()!=render(result):
        raise ValueError('Derived roster/readiness/report disagrees with original indexes')
    return summary(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('plan','collect','audit','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--parent',type=Path);parser.add_argument('--evidence',type=Path)
    parser.add_argument('--contact',default=os.environ.get('SEC_CONTACT_EMAIL'));args=parser.parse_args()
    if args.command=='plan':
        if args.parent is None:parser.error('--parent required for plan')
        result=register(args.output,args.parent)
    elif args.command=='collect':
        contact=args.contact or subprocess.check_output(['git','config','user.email'],text=True).strip()
        result=collect(args.output,contact)
    elif args.command=='audit':result=audit(args.output,args.evidence)
    else:result=verify(args.output)
    print(json.dumps(result))


if __name__=='__main__':main()
