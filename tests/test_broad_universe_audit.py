"""Offline original-index collection, immutable scope and semantic verification."""
from io import BytesIO
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from quant_core.provenance import content_hash
from research.sec_capital_audit import sources as capital_sources,render as capital_render
from research.broad_universe_audit import register,collect,audit,verify,download,read_inputs
from test_broad_universe import index_body,filing


class Response(BytesIO):
    status=200


class AuditTests(unittest.TestCase):
    def setup_study(self,root):
        parent=root/'parent';parent.mkdir();output=root/'study'
        p=dict(sources=capital_sources(),formations=['2017-06-30','2018-06-29','2019-06-28','2020-06-30','2021-06-30','2022-06-30','2023-06-30','2024-06-28','2025-06-30','2026-06-30'],minimum_eligible=10)
        result=dict(rows=[],coverage=[],fixed_panel_infeasible=True,required=[],audit_plan_hash=content_hash(p),performance_evaluated=False)
        (parent/'AUDIT_PLAN.json').write_text(json.dumps(p));(parent/'RULES.json').write_text('{}')
        (parent/'CAPITAL.json').write_text(json.dumps(result));(parent/'REPORT.html').write_text(capital_render(result))
        hashes={'files':{n:hashlib.sha256((parent/n).read_bytes()).hexdigest() for n in ('CAPITAL.json','REPORT.html')}}
        (parent/'REPORT_HASHES.json').write_text(json.dumps(hashes))
        register(output,parent)
        plan=json.loads((output/'STUDY_PLAN.json').read_text());raw=output/'raw'
        for key,r in plan['requests'].items():
            raw.mkdir(exist_ok=True);year,quarter=r['year'],r['quarter'];month=(quarter-1)*3+1
            body=index_body([filing(1,name='Historical issuer',filed=f'{year}-{month:02d}-02',accession=f'0000099999-{year%100:02d}-{quarter:06d}')])
            (raw/(key+'.gz')).write_bytes(body)
            (raw/(key+'.request.json')).write_text(json.dumps(dict(url=r['url'],status=200,body_file=key+'.gz',
                sha256=hashlib.sha256(body).hexdigest(),retrieved_at=datetime.now(timezone.utc).isoformat(),contact_omitted=True)))
        return output,parent

    def test_complete_real_arithmetic_roundtrip_and_no_implicit_performance(self):
        with tempfile.TemporaryDirectory() as d:
            output,_=self.setup_study(Path(d));result=audit(output)
            self.assertEqual(result['index_responses'],42);self.assertEqual(result['unique_review_ciks'],1)
            self.assertEqual(result['sample_issuer_formations'],10);self.assertFalse(result['ready_for_performance'])
            self.assertEqual(verify(output),result)
            with self.assertRaises(FileExistsError):audit(output)

    def test_partial_missing_changed_url_and_orphan_inputs_cannot_be_audited(self):
        for mutation in ('missing','changed','url','orphan'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as d:
                output,_=self.setup_study(Path(d));raw=output/'raw';body=next(raw.glob('*.gz'));meta=body.with_suffix('.request.json')
                if mutation=='missing':body.unlink()
                elif mutation=='changed':body.write_bytes(b'wrong')
                elif mutation=='url':
                    r=json.loads(meta.read_text());r['url']='https://example.com/index.gz';meta.write_text(json.dumps(r))
                else:(raw/'orphan.gz').write_bytes(b'unregistered')
                with self.assertRaises((ValueError,FileNotFoundError)):audit(output)
                self.assertFalse((output/'ROSTER.json').exists())

    def test_resealed_sample_tampering_and_incomplete_report_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            output,_=self.setup_study(Path(d));audit(output)
            result=json.loads((output/'ROSTER.json').read_text());result['panel']['formations'][0]['sample'][0]['cik']='9999999999'
            (output/'ROSTER.json').write_text(json.dumps(result));hashes=json.loads((output/'REPORT_HASHES.json').read_text())
            hashes['files']['ROSTER.json']=hashlib.sha256((output/'ROSTER.json').read_bytes()).hexdigest();(output/'REPORT_HASHES.json').write_text(json.dumps(hashes))
            with self.assertRaises(ValueError):verify(output)
            del hashes['files']['REPORT.html'];(output/'REPORT_HASHES.json').write_text(json.dumps(hashes))
            with self.assertRaises(ValueError):verify(output)

    def test_modified_selection_scope_and_previous_report_cannot_pass_registration(self):
        for mutation in ('scope','parent'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as d:
                output,parent=self.setup_study(Path(d))
                if mutation=='parent':(parent/'CAPITAL.json').write_text('{}')
                else:
                    plan=json.loads((output/'STUDY_PLAN.json').read_text());plan['sample_seed']='chosen-after-returns'
                    (output/'STUDY_PLAN.json').write_text(json.dumps(plan))
                with self.assertRaises(ValueError):read_inputs(output)

    def test_missing_naive_or_future_retrieval_time_cannot_be_audited(self):
        for timestamp in (None,'2026-10-04','2099-01-01T00:00:00+00:00'):
            with self.subTest(timestamp=timestamp),tempfile.TemporaryDirectory() as d:
                output,_=self.setup_study(Path(d));path=next((output/'raw').glob('*.request.json'));metadata=json.loads(path.read_text())
                if timestamp is None:del metadata['retrieved_at']
                else:metadata['retrieved_at']=timestamp
                path.write_text(json.dumps(metadata))
                with self.assertRaises(ValueError):audit(output)

    def test_http_failure_is_retained_and_not_silently_retried_as_a_new_success(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'index.gz';url='https://www.sec.gov/Archives/edgar/full-index/2016/QTR1/master.gz'
            error=HTTPError(url,403,'Forbidden',{},BytesIO(b'Denied'))
            with patch('research.broad_universe_audit.urlopen',side_effect=error),patch('research.broad_universe_audit.time.sleep'):
                with self.assertRaises(ValueError):download(path,url,'test@example.com')
            self.assertEqual(path.read_bytes(),b'Denied')
            metadata=json.loads(path.with_suffix('.request.json').read_text());self.assertEqual(metadata['status'],403)
            self.assertNotIn('test@example.com',path.with_suffix('.request.json').read_text())
            with self.assertRaises(ValueError):download(path,url,'test@example.com')

    def test_cached_collection_never_calls_network_and_keeps_exact_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            output,_=self.setup_study(Path(d));before={p.name:p.read_bytes() for p in (output/'raw').iterdir()}
            with patch('research.broad_universe_audit.urlopen',side_effect=AssertionError('Unexpected network')):
                result=collect(output,'test@example.com')
            self.assertEqual(result['collected'],42);self.assertEqual({p.name:p.read_bytes() for p in (output/'raw').iterdir()},before)


if __name__=='__main__':unittest.main()
