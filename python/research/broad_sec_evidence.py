"""CIK-based preliminary evidence; no historical security or strategy passes."""
from datetime import date
from pathlib import PurePosixPath
import re

from research.sec_fundamentals import audit_issuer


def archive_requests(cik,submission):
    if int(submission['cik'])!=int(cik):raise ValueError('Submission CIK mismatch')
    if not isinstance(submission.get('filings'),dict) or not isinstance(submission['filings'].get('files',[]),list):
        raise ValueError('Malformed submission filing structure')
    result={}
    for row in submission['filings'].get('files',[]):
        name=row['name']
        if not re.fullmatch('CIK'+cik+r'-submissions-[0-9]+\.json',name):raise ValueError('Unsafe/wrong-issuer history archive')
        first,last=date.fromisoformat(row['filingFrom']),date.fromisoformat(row['filingTo'])
        if first>last:raise ValueError('Reversed history archive dates')
        if last<date(2016,1,1) or first>date(2026,6,30):continue
        request=dict(url='https://data.sec.gov/submissions/'+name,filing_from=first.isoformat(),filing_to=last.isoformat())
        if name in result and result[name]!=request:raise ValueError('Conflicting history archive metadata')
        result[name]=request
    return dict(sorted(result.items()))


def joined_history(cik,payloads):
    result={}
    for payload in payloads:
        if 'cik' in payload and int(payload['cik'])!=int(cik):raise ValueError('History CIK mismatch')
        cols=payload['filings']['recent'] if 'filings' in payload else payload
        size=len(cols['accessionNumber'])
        required=('accessionNumber','filingDate','reportDate','form')
        if any(not isinstance(cols[k],list) or len(cols[k])!=size for k in required):raise ValueError('Ragged filing history')
        for key in ('acceptanceDateTime','primaryDocument'):
            if key in cols and (not isinstance(cols[key],list) or len(cols[key])!=size):raise ValueError('Ragged optional filing column')
        for i in range(size):
            accn=cols['accessionNumber'][i];filed=cols['filingDate'][i];report=cols['reportDate'][i]
            if not re.fullmatch(r'[0-9]{10}-[0-9]{2}-[0-9]{6}',accn):raise ValueError('Malformed history accession')
            date.fromisoformat(filed)
            if report:date.fromisoformat(report)
            primary=cols.get('primaryDocument',[None]*size)[i]
            if primary and (not re.fullmatch(r'[A-Za-z0-9_./-]+',primary) or
                PurePosixPath(primary).is_absolute() or '..' in PurePosixPath(primary).parts):
                raise ValueError('Unsafe primary document')
            row=dict(filed=filed,report_date=report or None,form=cols['form'][i],
                acceptance_datetime=cols.get('acceptanceDateTime',[None]*size)[i],primary_document=primary or None)
            if accn in result:
                old=result[accn]
                if any(old[k]!=row[k] for k in ('filed','report_date','form')):raise ValueError('Conflicting filing history')
                for k in ('acceptance_datetime','primary_document'):
                    if old[k] and row[k] and old[k]!=row[k]:raise ValueError('Conflicting optional filing metadata')
                    row[k]=old[k] or row[k]
            result[accn]=row
    return result


def annual_references(sample,index):
    cutoff=date.fromisoformat(sample['formation']);result=[]
    for original in sample['filings']:
        row=index.get(original['accession']);status='missing' if row is None else 'matched'
        if row is not None and (row['filed'],row['form'])!=(original['filed'],original['form']):status='mismatched'
        report=row['report_date'] if status=='matched' else None
        result.append(dict(**original,join_status=status,report_date=report,
            primary_document=row['primary_document'] if status=='matched' else None,
            header_required=report is None or date.fromisoformat(report).year==cutoff.year-1,
            available_before_formation=date.fromisoformat(original['filed'])<cutoff))
    return result


def parse_header(body,cik,expected):
    if len(body)>1024*1024:raise ValueError('Original header oversized')
    try:text=body.decode('utf-8');encoding='utf-8'
    except UnicodeDecodeError:text=body.decode('latin-1');encoding='latin-1'
    if text.count('<SEC-HEADER>')!=1 or text.count('</SEC-HEADER>')!=1:raise ValueError('Original SEC header absent/ambiguous')
    text=text.split('<SEC-HEADER>',1)[1].split('</SEC-HEADER>',1)[0]
    tagged=bool(re.search(r'^<ACCESSION-NUMBER>',text,re.M))
    def tags(block,tag):return re.findall(r'^<'+tag+r'>([^\r\n]*)',block,re.M)
    def one(label):
        mapping={'ACCESSION NUMBER':'ACCESSION-NUMBER','CONFORMED SUBMISSION TYPE':'TYPE',
            'FILED AS OF DATE':'FILING-DATE','CONFORMED PERIOD OF REPORT':'PERIOD'}
        values=tags(text,mapping[label]) if tagged else re.findall(r'^\s*'+re.escape(label)+r':[^\S\r\n]*(.*?)\s*$',text,re.M)
        if len(values)!=1:raise ValueError('Original header field absent/ambiguous: '+label)
        return values[0]
    accn=one('ACCESSION NUMBER');form=one('CONFORMED SUBMISSION TYPE');filed=one('FILED AS OF DATE')
    if (accn,form,filed)!=(expected['accession'],expected['form'],expected['filed'].replace('-','')):
        raise ValueError('Original header accession/form/date mismatch')
    period=one('CONFORMED PERIOD OF REPORT')
    report=date(int(period[:4]),int(period[4:6]),int(period[6:])) if re.fullmatch('[0-9]{8}',period) else None
    if report is None:raise ValueError('Original header report date invalid')
    filers=[]
    blocks=re.findall(r'<FILER>\s*(.*?)</FILER>',text,re.S) if tagged else re.split(r'^\s*FILER:\s*$',text,flags=re.M)[1:]
    for block in blocks:
        if tagged:
            company=re.findall(r'<COMPANY-DATA>\s*(.*?)</COMPANY-DATA>',block,re.S)
            if len(company)!=1:raise ValueError('Original company-data block absent/ambiguous')
            block=company[0];ids=tags(block,'CIK')
        else:
            block=re.split(r'^\s*(?:SUBJECT COMPANY|FILED BY|ISSUER):\s*$',block,flags=re.M)[0]
            ids=re.findall(r'^\s*CENTRAL INDEX KEY:\s*([0-9]{1,10})\s*$',block,re.M)
        if len(ids)!=1 or int(ids[0])!=int(cik):continue
        names=tags(block,'CONFORMED-NAME') if tagged else re.findall(r'^\s*COMPANY CONFORMED NAME:[^\S\r\n]*(.*?)\s*$',block,re.M)
        sics=tags(block,'ASSIGNED-SIC') if tagged else re.findall(r'^\s*STANDARD INDUSTRIAL CLASSIFICATION:[^\S\r\n]*(.*?)\s*$',block,re.M)
        if len(names)!=1 or len(sics)>1:raise ValueError('Ambiguous original issuer metadata')
        sic=re.fullmatch(r'([0-9]{4})',sics[0].strip()) if tagged and sics else re.search(r'\[([0-9]{4})\]',sics[0]) if sics else None
        filers.append((names[0],sic[1] if sic else None))
    if len(filers)!=1:raise ValueError('Original header issuer absent/ambiguous')
    name,sic=filers[0]
    return dict(cik=cik,accession=accn,form=form,filed=expected['filed'],report_date=report.isoformat(),
        original_name=name,sic=sic,financial_sic_observed=None if sic is None else 6000<=int(sic)<=6999,
        encoding=encoding,historical_security_qualified=False,classification_reviewed=False)


def issuer_audit(sample,submission,facts,index):
    result=dict(cik=sample['cik'],formation=sample['formation'],historical_name=sample['name_at_latest_filing'],
        current_metadata=None,components=None,exact_december_shares=[],references=annual_references(sample,index),
        historical_common_listing='missing',qualified=False,performance_evaluated=False,error=None)
    try:
        if submission is None:raise ValueError('Submissions unavailable')
        if int(submission['cik'])!=int(sample['cik']):raise ValueError('Submission CIK mismatch')
        result['current_metadata']={k:submission.get(k) for k in ('name','sic','tickers','exchanges')}
        if facts is None:raise ValueError('CompanyFacts unavailable')
        if int(facts['cik'])!=int(sample['cik']):raise ValueError('CompanyFacts CIK mismatch')
        # The existing financial routine expects date objects in its index.
        financial_index={accn:dict(row,filed=date.fromisoformat(row['filed'])) for accn,row in index.items()}
        components=audit_issuer(facts,financial_index,date.fromisoformat(sample['formation']))
        result['components']=components
        result['exact_december_shares']=[r for r in components['december_outstanding_shares'] if r['end'].day==31]
    except (ValueError,KeyError,TypeError,ArithmeticError,AttributeError) as exc:result['error']=str(exc)
    return result
