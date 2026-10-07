"""Input preflight cannot turn declarations or engineering data into validation."""

from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import date
from hashlib import sha256
from io import StringIO
from importlib.util import find_spec
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_data as fixtures
from quant_core.data import Split
from quant_core.data.storage import save_snapshot
from quant_core.provenance import content_hash, canonical_json
from quant_core.validation.contracts import CAPABILITIES, Capability, Qualification


def inputs():
    data=fixtures.snapshot()
    plan={'dataset_hash':'a'*64,'source_provider':'original_fixture',
          'calendar':[d.isoformat() for d in data.sessions], 'stocks':['A'], 'benchmark':'A',
          'start':data.sessions[0].isoformat(),'end':data.sessions[-1].isoformat()}
    qualification=Qualification(data.dataset_hash,'independent_retest_fixed_sample','Fixture reviewer',date(2024,1,5),
        tuple(Capability(name,'passed','Constructed hand-reviewed engineering fixture') for name in CAPABILITIES),
        ('Synthetic test; no empirical rights or market qualification',),'a'*64,'Independent fixture acquisition')
    return data,plan,qualification


class PreflightTests(unittest.TestCase):
    def run_reviewed_cli(self,root,review_body=None):
        from research.data_preflight import main
        data,plan,q=inputs()
        campaign,archive=self.campaign(root,plan)
        source=root/'data.json';save_snapshot(data,source)
        review=root/'qualification.json'
        review.write_text(review_body or canonical_json({'schema_version':1,'qualification':q}))
        args=['--campaign',str(campaign),'--source-archive',str(archive),'--snapshot',str(source),
              '--qualification',str(review),'--output',str(root/'report')]
        return main,args,source,review

    def test_snapshot_change_after_parsing_cannot_get_ready_status(self):
        from research.data_preflight import load_local_snapshot
        with TemporaryDirectory() as folder:
            root=Path(folder);main,args,source,_=self.run_reviewed_cli(root)
            def changed(path):
                snapshot=load_local_snapshot(path)
                source.write_text('{}')
                return snapshot
            with patch('research.data_preflight.load_local_snapshot',side_effect=changed),redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(args),2)
            self.assertFalse((root/'report').exists())

    def test_qualification_change_after_parsing_cannot_get_ready_status(self):
        from quant_core.validation.contracts import parse_qualification
        with TemporaryDirectory() as folder:
            root=Path(folder);main,args,_,review=self.run_reviewed_cli(root)
            def changed(values):
                result=parse_qualification(values)
                review.write_text('{}')
                return result
            with patch('research.data_preflight.parse_qualification',side_effect=changed),redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(args),2)
            self.assertFalse((root/'report').exists())

    def test_conflicting_duplicate_qualification_status_is_rejected(self):
        _,_,q=inputs()
        body=canonical_json({'schema_version':1,'qualification':q}).replace('"status":"passed"','"status":"failed","status":"passed"',1)
        with TemporaryDirectory() as folder:
            root=Path(folder);main,args,_,_=self.run_reviewed_cli(root,body)
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(args),2)
            self.assertFalse((root/'report').exists())

    def test_malformed_review_text_is_not_echoed(self):
        _,_,q=inputs()
        body=canonical_json({'schema_version':1,'qualification':q}).replace('"2024-01-05"','"api_token=SECRET_SENTINEL"')
        with TemporaryDirectory() as folder:
            root=Path(folder);main,args,_,_=self.run_reviewed_cli(root,body)
            error=StringIO()
            with redirect_stdout(StringIO()),redirect_stderr(error):
                self.assertEqual(main(args),2)
            self.assertNotIn('SECRET_SENTINEL',error.getvalue())

    def test_campaign_metadata_change_during_parse_is_rejected(self):
        from research.data_preflight import _read,load_frozen_scope
        _,plan,_=inputs()
        with TemporaryDirectory() as folder:
            root=Path(folder);campaign,archive=self.campaign(root,plan)
            def changed(path):
                result=_read(path)
                if Path(path).name=='RESULTS.json':
                    Path(path).write_text('{}')
                return result
            with patch('research.data_preflight._read',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed|integrity'):
                    load_frozen_scope(campaign,archive)

    def test_readiness_change_during_parse_is_rejected(self):
        from research.data_preflight import _read,load_frozen_scope
        _,plan,_=inputs()
        with TemporaryDirectory() as folder:
            root=Path(folder);readiness=root/'readiness.json'
            readiness.write_text(json.dumps({'dataset_hash':plan['dataset_hash'],'missing_payable_dates':[]}))
            plan=dict(plan,readiness_path=str(readiness),readiness_hash=sha256(readiness.read_bytes()).hexdigest())
            campaign,archive=self.campaign(root,plan)
            def changed(path):
                result=_read(path)
                if Path(path)==readiness:
                    readiness.write_text('{}')
                return result
            with patch('research.data_preflight._read',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed|integrity'):
                    load_frozen_scope(campaign,archive)

    def test_complete_distinct_reviewed_input_passes_checks_without_executing(self):
        from research.data_preflight import preflight
        data,plan,q=inputs()
        report=preflight(data,plan,q)
        self.assertTrue(report['input_gate_ready'],report)
        self.assertFalse(report['retest_executed'])
        self.assertFalse(report['strategy_qualified'])
        self.assertFalse(report['fresh_temporal_holdout'])

    def test_all_blockers_are_retained_together(self):
        from research.data_preflight import preflight
        data,plan,_=inputs()
        plan.update(dataset_hash=data.dataset_hash,source_provider=data.metadata.source,stocks=['MISSING'])
        data=replace(data,metadata=replace(data.metadata,actions_complete=False))
        report=preflight(data,plan)
        failed={key for key,value in report['checks'].items() if value['status']!='passed'}
        self.assertTrue({'independent_provider','security_panel','actions_complete','qualification_binding'} <= failed)
        self.assertFalse(report['input_gate_ready'])
        self.assertEqual(len(report['capabilities']),8)
        self.assertTrue(all(c['status']=='unresolved' for c in report['capabilities']))

    def test_same_dataset_calendar_schema_and_qualification_mismatch_block(self):
        from research.data_preflight import preflight
        data,plan,q=inputs()
        cases=[(data,dict(plan,dataset_hash=data.dataset_hash),q,'independent_dataset'),
               (data,dict(plan,calendar=plan['calendar'][:-1]),q,'calendar'),
               (data,plan,replace(q,dataset_hash='b'*64),'qualification_binding'),
               (data,plan,replace(q,independent_from='b'*64),'qualification_binding'),
               (replace(data,actions=(Split('A',fixtures.DAYS[1],new_shares=1,old_shares=3),)),
                plan,q,'frozen_snapshot_schema')]
        for candidate,scope,review,key in cases:
            with self.subTest(key=key):
                report=preflight(candidate,scope,review)
                self.assertFalse(report['input_gate_ready'])
                self.assertEqual(report['checks'][key]['status'],'failed')

    def test_unreviewed_capability_blocks_even_when_mechanical_checks_pass(self):
        from research.data_preflight import preflight
        data,plan,q=inputs()
        q=replace(q,capabilities=tuple(replace(c,status='unresolved') if c.name=='security_identity' else c for c in q.capabilities))
        report=preflight(data,plan,q)
        self.assertFalse(report['input_gate_ready'])
        self.assertEqual(next(c for c in report['capabilities'] if c['name']=='security_identity')['status'],'unresolved')

    def test_strict_unexplained_gap_and_adjusted_volume_block(self):
        from research.data_preflight import preflight
        data,plan,q=inputs()
        jump=replace(data,bars=tuple(fixtures.bar(day,'200' if i==0 else '100') for i,day in enumerate(fixtures.DAYS)))
        report=preflight(jump,plan,replace(q,dataset_hash=jump.dataset_hash))
        self.assertEqual(report['checks']['data_quality']['status'],'failed')
        adjusted=replace(data,metadata=replace(data.metadata,source='eodhd',
                              limitations=('Provider uses split-adjusted volume; historical liquidity unqualified',)))
        report=preflight(adjusted,plan,replace(q,dataset_hash=adjusted.dataset_hash))
        self.assertEqual(report['checks']['raw_volume_basis']['status'],'unresolved')
        self.assertFalse(report['input_gate_ready'])

    def test_template_is_unreviewed_and_bound_to_both_datasets(self):
        from research.data_preflight import qualification_template
        data,plan,_=inputs()
        template=qualification_template(data,plan)['qualification']
        self.assertEqual(template['dataset_hash'],data.dataset_hash)
        self.assertEqual(template['independent_from'],plan['dataset_hash'])
        self.assertIsNone(template['reviewer'])
        self.assertIsNone(template['reviewed_on'])
        self.assertTrue(all(c['status']=='unresolved' for c in template['capabilities']))

    def campaign(self,root,plan):
        campaign=root/'campaign';campaign.mkdir()
        archive=root/'archive';(archive/'research').mkdir(parents=True)
        (archive/'research/stock_campaign.py').write_text('# Immutable engineering fixture\n')
        hashes={'research/stock_campaign.py':sha256((archive/'research/stock_campaign.py').read_bytes()).hexdigest()}
        (archive/'SOURCE_ARCHIVE.json').write_text(json.dumps({'files':hashes}))
        entry={'role':'parent','configuration':{'name':'fixed_trend'}}
        plan=dict(plan,source_hashes=hashes,entries=[entry])
        (campaign/'EXPERIMENT_PLAN.json').write_text(canonical_json(plan))
        (campaign/'RESULTS.json').write_text(canonical_json({'plan_hash':content_hash(plan),
             'decisions':{'fixed_trend':{'freeze_for_retest':True}}}))
        (campaign/'FROZEN_CANDIDATES.json').write_text(canonical_json({'plan_hash':content_hash(plan),
             'entries':[entry],'production_nomination':False}))
        (campaign/'RETEST_REQUIREMENTS.json').write_text(canonical_json({'plan_hash':content_hash(plan),'frozen_count':1}))
        return campaign,archive

    def test_cli_publishes_metadata_only_immutable_preflight_and_detects_tampering(self):
        from research.data_preflight import main,verify_package
        data,plan,_=inputs()
        with TemporaryDirectory() as folder:
            root=Path(folder);campaign,archive=self.campaign(root,plan)
            source=root/'data.json';save_snapshot(data,source)
            output=root/'review'
            args=['--campaign',str(campaign),'--source-archive',str(archive),'--snapshot',str(source),'--output',str(output)]
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(args),1)  # Missing review is a real blocker.
                self.assertEqual(main(args),2)  # Existing evidence cannot be overwritten.
            report=verify_package(output)
            self.assertFalse(report['input_gate_ready'])
            self.assertNotIn('bars',json.loads((output/'SCOPE.json').read_text()))
            (output/'PREFLIGHT.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'integrity'):
                verify_package(output)

    def test_changed_frozen_binding_is_rejected_before_output(self):
        from research.data_preflight import main
        data,plan,_=inputs()
        with TemporaryDirectory() as folder:
            root=Path(folder);campaign,archive=self.campaign(root,plan)
            source=root/'data.json';save_snapshot(data,source)
            (campaign/'FROZEN_CANDIDATES.json').write_text('{}')
            output=root/'review'
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(['--campaign',str(campaign),'--source-archive',str(archive),
                                      '--snapshot',str(source),'--output',str(output)]),2)
            self.assertFalse(output.exists())

    def test_original_readiness_evidence_is_bound_and_cannot_be_substituted(self):
        from research.data_preflight import load_frozen_scope
        _,plan,_=inputs()
        with TemporaryDirectory() as folder:
            root=Path(folder)
            readiness=root/'original-readiness.json'
            readiness.write_text(json.dumps({'dataset_hash':plan['dataset_hash'], 'qualified':False,
                                             'missing_payable_dates':[{'security_id':'A','ex_date':'2024-01-03'}]}))
            plan=dict(plan,readiness_path=str(readiness),readiness_hash=sha256(readiness.read_bytes()).hexdigest())
            campaign,archive=self.campaign(root,plan)
            _,scope,bound=load_frozen_scope(campaign,archive)
            self.assertEqual(scope['original_source_readiness']['missing_payment_count'],1)
            self.assertIn(str(readiness.resolve()),bound)
            readiness.write_text('{}')
            with self.assertRaisesRegex(ValueError,'readiness'):
                load_frozen_scope(campaign,archive)

    @unittest.skipUnless(find_spec('pyarrow'),'Optional PyArrow')
    def test_cli_accepts_parquet_and_binds_both_files(self):
        from quant_core.data.parquet import save_parquet_snapshot
        from research.data_preflight import main,verify_package
        data,plan,q=inputs()
        with TemporaryDirectory() as folder:
            root=Path(folder);campaign,archive=self.campaign(root,plan)
            source=root/'data';save_parquet_snapshot(data,source)
            review=root/'qualified.json';review.write_text(canonical_json({'schema_version':1,'qualification':q}))
            output=root/'review'
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(['--campaign',str(campaign),'--source-archive',str(archive),
                    '--snapshot',str(source),'--qualification',str(review),'--output',str(output)]),0)
            report=verify_package(output)
            self.assertTrue(report['input_gate_ready'])
            bound=report['input_files']
            self.assertIn(str((source/'bars.parquet').resolve()),bound)
            self.assertIn(str((source/'manifest.json').resolve()),bound)


if __name__=='__main__':
    unittest.main()
