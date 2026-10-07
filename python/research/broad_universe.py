"""Filing-dated candidate discovery, never historical stock membership proof."""
from datetime import date, datetime
import gzip
import hashlib
from heapq import merge
from io import BytesIO
from pathlib import PurePosixPath
import re

from quant_core.provenance import content_hash

CHECKS=('historical_common_listing','security_identity_and_classes','historical_nonfinancial_classification',
        'original_annual_accounting','preferred_and_december_market_equity','raw_prices_and_complete_actions',
        'delisting_outcomes','project_use_rights','coherent_gross_profit_and_assets','positive_common_book_and_market_equity')
INDEX_LIMIT=128*1024*1024


def parse_index(body,year,quarter):
    if type(year) is not int or type(quarter) is not int or not 1994<=year<=2100 or quarter not in (1,2,3,4):
        raise ValueError('Invalid SEC index quarter')
    if not body.startswith(b'\x1f\x8b') or len(body)>32*1024*1024:raise ValueError('Expected bounded original gzip index')
    try:
        with gzip.GzipFile(fileobj=BytesIO(body)) as stream:decoded=stream.read(INDEX_LIMIT+1)
    except (OSError,EOFError) as exc:raise ValueError('Invalid SEC index gzip') from exc
    if len(decoded)>INDEX_LIMIT:raise ValueError('SEC index exceeds decoded size limit')
    try:text=decoded.decode('utf-8-sig');encoding='utf-8'
    except UnicodeDecodeError:text=decoded.decode('latin-1');encoding='latin-1'
    lines=text.splitlines();header='CIK|Company Name|Form Type|Date Filed|Filename'
    if lines.count(header)!=1:raise ValueError('Original master-index header absent/ambiguous')
    start=lines.index(header)+1
    if start==len(lines) or not re.fullmatch('-{5,}',lines[start].strip()):raise ValueError('Original master-index separator absent')
    rows={};total=0;identities={}
    for line in lines[start+1:]:
        if not line.strip():continue
        parts=line.split('|')
        if len(parts)!=5:raise ValueError('Malformed original filing row')
        cik,name,form,filed,path=parts
        # SEC can supply an empty company name. Keep that absence verbatim;
        # never discard its CIK or fill it from today's issuer metadata.
        if not re.fullmatch(r'[0-9]{1,10}',cik) or int(cik)<=0 or not form.strip():
            raise ValueError('Malformed original filing identity')
        try:day=date.fromisoformat(filed)
        except ValueError as exc:raise ValueError('Malformed original filing date') from exc
        if len(filed)!=10 or day.year!=year or (day.month-1)//3+1!=quarter:raise ValueError('Original index row outside registered quarter')
        match=re.fullmatch(r'edgar/data/([0-9]{1,10})/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt',path)
        if match is None or int(match[1])!=int(cik):raise ValueError('Original filing path/issuer mismatch')
        raw_identity=hashlib.sha256('|'.join((cik.zfill(10),name,form,filed,path)).encode()).digest()
        identity_key=cik.zfill(10)+match[2]
        identities.setdefault(identity_key,set()).add(raw_identity)
        total+=1
        if form not in ('10-K','10-K/A'):continue
        row=dict(cik=cik.zfill(10),name=name,form=form,filed=filed,accession=match[2],path=path,
            filing_url='https://www.sec.gov/Archives/'+path,index=f'{year}Q{quarter}')
        if identity_key in rows and rows[identity_key]!=row:raise ValueError('Conflicting original issuer/accession metadata')
        rows[identity_key]=row
    if not total:raise ValueError('Empty original master index')
    if any(len(identities[key])>1 for key in rows):raise ValueError('Conflicting annual issuer/accession identity')
    # A compact, issuer/accession-sorted ledger enables a streaming cross-quarter
    # conflict check without retaining millions of full metadata dictionaries.
    ledger=bytearray()
    for key in sorted(identities):
        for identity_hash in sorted(identities[key]):ledger.extend(key.encode('ascii')+identity_hash)
    return dict(year=year,quarter=quarter,total_rows=total,encoding=encoding,raw_accessions=bytes(ledger),
                annual_filings=sorted(rows.values(),key=lambda r:(r['filed'],r['cik'],r['accession'])))


def candidate_panel(plan,indexes):
    if plan['minimum_eligible']!=10 or type(plan['sample_limit']) is not int or not 1<=plan['sample_limit']<=100:
        raise ValueError('Registered floor/sample workload changed')
    def raw_records(index):
        ledger=index['raw_accessions']
        for start in range(0,len(ledger),62):yield ledger[start:start+62]
    previous=None
    annual_keys={(r['cik']+r['accession']).encode('ascii') for index in indexes for r in index['annual_filings']}
    for record in merge(*(raw_records(index) for index in indexes)):
        if previous is not None and previous[:30]==record[:30] and previous!=record and record[:30] in annual_keys:
            raise ValueError('Conflicting cross-index raw issuer/accession identity')
        previous=record
    filings={}
    for index in indexes:
        for row in index['annual_filings']:
            key=(row['cik'],row['accession'])
            if key in filings and filings[key]!=row:raise ValueError('Conflicting cross-index accession')
            filings[key]=row
    formations=[]
    for formation in plan['formations']:
        cutoff=date.fromisoformat(formation);start=date(cutoff.year-1,1,1);groups={}
        for row in filings.values():
            if start<=date.fromisoformat(row['filed'])<cutoff:groups.setdefault(row['cik'],[]).append(row)
        roster=[]
        for cik,records in sorted(groups.items()):
            records=sorted(records,key=lambda r:(r['filed'],r['accession']))
            rank=hashlib.sha256((plan['sample_seed']+':'+cik).encode()).hexdigest()
            roster.append(dict(cik=cik,name_at_latest_filing=records[-1]['name'],first_filed=records[0]['filed'],
                last_filed=records[-1]['filed'],filings=records,sample_hash=rank))
        sample=sorted(roster,key=lambda r:(r['sample_hash'],r['cik']))[:plan['sample_limit']]
        formations.append(dict(formation=formation,discovery_start=start.isoformat(),candidate_count=len(roster),
                               sample_count=len(sample),roster=roster,sample=sample))
    return dict(formations=formations,historical_membership_qualified=False,
        source_policy='Currently retrieved quarterly indexes filtered by historical filing dates; post-acceptance corrections unresolved',
        selection_policy='Stable hash sample of filing candidates; no returns, current tickers, availability replacement or stock eligibility inference')


def input_readiness(plan,panel,evidence,review_cutoff=None):
    keys={(f['formation'],r['cik']) for f in panel['formations'] for r in f['sample']};checks={}
    registered=datetime.fromisoformat(review_cutoff or plan['registered_at']).date()
    if evidence is not None:
        if (evidence.get('schema_version')!=1 or evidence.get('study_plan_hash')!=content_hash(plan) or
            evidence.get('candidate_panel_hash')!=content_hash(panel)):
            raise ValueError('Readiness evidence unbound to study/candidate panel')
        for row in evidence['checks']:
            key=(row['formation'],row['cik'],row['check'])
            if key[:2] not in keys or key[2] not in CHECKS or key in checks:raise ValueError('Unknown/duplicate candidate readiness check')
            if row['status'] not in ('passed','failed','missing'):raise ValueError('Unknown readiness status')
            if row['status']=='passed':
                files=row.get('evidence_files',[])
                if not row.get('reviewer') or date.fromisoformat(row['reviewed_at'])>registered or not files:
                    raise ValueError('Passed readiness lacks timely review/evidence')
                if len(set(files))!=len(files) or any(not isinstance(n,str) or not n or PurePosixPath(n).is_absolute() or
                    '..' in PurePosixPath(n).parts or '\\' in n or n.endswith('/') for n in files):
                    raise ValueError('Unsafe/duplicate readiness evidence path')
            checks[key]=row
    rows=[]
    for formation,cik in sorted(keys):
        statuses={check:checks.get((formation,cik,check),{}).get('status','missing') for check in CHECKS}
        rows.append(dict(formation=formation,cik=cik,checks=statuses,complete_review=all(v=='passed' for v in statuses.values()),
            blockers=[k for k,v in statuses.items() if v!='passed']))
    coverage=[dict(formation=f['formation'],candidate_count=f['candidate_count'],sample_count=f['sample_count'],
        complete_review_candidates=sum(r['complete_review'] for r in rows if r['formation']==f['formation']),
        minimum_eligible=plan['minimum_eligible']) for f in panel['formations']]
    return dict(rows=rows,coverage=coverage,review_floor_passed=all(c['complete_review_candidates']>=10 for c in coverage),
        ready_for_performance=False,performance_enabled=False,production_qualified=False,
        required=['Independent review of index corrections and historical security membership',
                  'Actually reviewed input evidence for every required candidate check',
                  'Separate accounting/market data audit and registered performance campaign',
                  'Search-history disclosure and genuinely untouched future validation'])
