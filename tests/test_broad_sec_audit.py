"""Frozen collection phases retain failures and reject misleading resealed results."""
from datetime import datetime,timezone
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from research.broad_sec_audit import register,collect,audit,verify,download,read_plan
from research.broad_universe_audit import audit as audit_parent
import test_broad_universe_audit as parent_fixture


def response(output,key,url,body,status=200):
    raw=output/'raw';raw.mkdir(exist_ok=True)
    (raw/key).write_bytes(body)
    (raw/(key+'.request.json')).write_text(json.dumps(dict(url=url,status=status,body_file=key,
        sha256=hashlib.sha256(body).hexdigest(),retrieved_at=datetime.now(timezone.utc).isoformat(),
        oversize=False,attempt_statuses=[status],contact_omitted=True)))


class Response(BytesIO):
    status=200


class EvidenceAuditTests(unittest.TestCase):
    def fixture(self,root):
        parent,_=parent_fixture.AuditTests().setup_study(root);audit_parent(parent)
        output=root/'evidence';register(output,parent);plan=json.loads((output/'INPUT_PLAN.json').read_text())
        filings={r['accession']:r for s in plan['samples'] for r in s['filings']}
        c=dict(accessionNumber=list(filings),filingDate=[r['filed'] for r in filings.values()],
            reportDate=[str(int(r['filed'][:4])-1)+'-12-31' for r in filings.values()],
            form=[r['form'] for r in filings.values()],primaryDocument=['annual.htm']*len(filings))
        sub=dict(cik=1,name='Currently changed',tickers=[],sic='6021',filings=dict(recent=c,files=[]))
        for key,r in plan['requests'].items():
            body=sub if r['kind']=='submissions' else dict(cik=1,facts={})
            response(output,key,r['url'],json.dumps(body).encode())
        return output

    def collect_fixture(self,output):
        def get(request,timeout):
            url=request.full_url;accn=url.rsplit('/',1)[1].removesuffix('.hdr.sgml')
            year=2000+int(accn[11:13]);quarter=int(accn[-6:]);month=(quarter-1)*3+1
            return Response((f'<SEC-HEADER>\nACCESSION NUMBER: {accn}\nCONFORMED SUBMISSION TYPE: 10-K\n'
                f'FILED AS OF DATE: {year}{month:02d}02\nCONFORMED PERIOD OF REPORT: {year-1}1231\n'
                'FILER:\nCOMPANY DATA:\nCOMPANY CONFORMED NAME: Original\nCENTRAL INDEX KEY: 0000000001\n'
                'STANDARD INDUSTRIAL CLASSIFICATION: Manufacturing [3571]\n</SEC-HEADER>').encode())
        with patch('research.broad_sec_audit.urlopen',side_effect=get),patch('research.broad_sec_audit.time.sleep'):
            collect(output,'test@example.com')

    def test_real_phase_roundtrip_keeps_all_sample_rows_and_no_qualification(self):
        with tempfile.TemporaryDirectory() as d:
            output=self.fixture(Path(d));self.collect_fixture(output);result=audit(output)
            self.assertEqual(result['sample_rows'],10);self.assertEqual(result['unique_ciks'],1)
            self.assertEqual(result['qualified_rows'],0);self.assertFalse(result['performance_evaluated'])
            self.assertEqual(verify(output),result)
            with self.assertRaises(FileExistsError):audit(output)

    def test_terminal_404_is_retained_and_collection_continues_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            output=self.fixture(Path(d));plan=read_plan(output);key=next(k for k,r in plan['requests'].items() if r['kind']=='facts')
            (output/'raw'/key).unlink();(output/'raw'/(key+'.request.json')).unlink()
            error=HTTPError(plan['requests'][key]['url'],404,'Missing',{},BytesIO(b'not found'))
            with patch('research.broad_sec_audit.urlopen',side_effect=error),patch('research.broad_sec_audit.time.sleep'):
                metadata=download(output/'raw',key,plan['requests'][key]['url'],'test@example.com')
            self.assertEqual(metadata['status'],404);self.assertEqual((output/'raw'/key).read_bytes(),b'not found')
            self.collect_fixture(output);result=audit(output)
            self.assertEqual(result['sample_rows'],10);self.assertEqual(result['failed_http_requests'],1)
            self.assertEqual(verify(output),result)

    def test_malformed_submission_is_reported_without_dropping_sample_or_abort(self):
        with tempfile.TemporaryDirectory() as d:
            output=self.fixture(Path(d));plan=read_plan(output)
            key='0000000001.submissions.json'
            response(output,key,plan['requests'][key]['url'],b'{"cik":1,"filings":null}')
            self.collect_fixture(output);result=audit(output)
            self.assertEqual(result['sample_rows'],10);self.assertEqual(result['qualified_rows'],0)
            rows=json.loads((output/'EVIDENCE.json').read_text())['rows']
            self.assertTrue(all(r['history_error'] for r in rows));self.assertEqual(verify(output),result)

    def test_wrong_result_cannot_be_resealed_into_success(self):
        with tempfile.TemporaryDirectory() as d:
            output=self.fixture(Path(d));self.collect_fixture(output);audit(output)
            p=output/'EVIDENCE.json';r=json.loads(p.read_text());r['rows'][0]['qualified']=True;p.write_text(json.dumps(r))
            m=output/'REPORT_HASHES.json';h=json.loads(m.read_text());h['files']['EVIDENCE.json']=hashlib.sha256(p.read_bytes()).hexdigest();m.write_text(json.dumps(h))
            with self.assertRaises(ValueError):verify(output)

    def test_missing_orphan_changed_phase_and_future_response_fail_closed(self):
        for change in ('missing','orphan','phase','future'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                output=self.fixture(Path(d));self.collect_fixture(output)
                if change=='missing':next((output/'raw').glob('*.hdr.sgml')).unlink()
                elif change=='orphan':(output/'raw'/'unregistered.json').write_text('{}')
                elif change=='phase':
                    p=output/'DOCUMENT_PLAN.json';v=json.loads(p.read_text());v['requests']={};p.write_text(json.dumps(v))
                else:
                    p=next((output/'raw').glob('*.request.json'));v=json.loads(p.read_text());v['retrieved_at']='2099-01-01T00:00:00+00:00';p.write_text(json.dumps(v))
                with self.assertRaises((ValueError,FileNotFoundError)):audit(output)

    def test_changed_cik_sample_and_current_sources_cannot_change_registration(self):
        with tempfile.TemporaryDirectory() as d:
            output=self.fixture(Path(d));p=output/'INPUT_PLAN.json';v=json.loads(p.read_text());v['samples'][0]['cik']='0000000002';p.write_text(json.dumps(v))
            with self.assertRaises(ValueError):read_plan(output)


if __name__=='__main__':unittest.main()
