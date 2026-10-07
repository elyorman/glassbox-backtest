"""Historical roster selection and readiness without outcome-driven replacement."""
from datetime import date
import gzip
import hashlib
import unittest

from quant_core.provenance import content_hash
from research.broad_universe import parse_index, candidate_panel, input_readiness, CHECKS


def index_body(lines):
    return gzip.compress(('Description: Master Index\nCIK|Company Name|Form Type|Date Filed|Filename\n'+('-'*60)+'\n'+'\n'.join(lines)+'\n').encode())


def filing(cik=1,name='Former issuer',form='10-K',filed='2017-02-01',accession=None):
    accession=accession or '0000099999-17-'+str(cik).zfill(6)
    return f'{cik}|{name}|{form}|{filed}|edgar/data/{cik}/{accession}.txt'


def plan(limit=100):
    return dict(schema_version=1,formations=['2017-06-30','2018-06-29'],sample_limit=limit,
        sample_seed='quant-platform-broad-fundamentals-v1',minimum_eligible=10,registered_at='2026-10-04T00:00:00+00:00')


class IndexTests(unittest.TestCase):
    def test_annual_forms_agent_accession_and_historical_names_are_retained(self):
        result=parse_index(index_body([filing(),filing(2,'Private-like debtor'),filing(3,form='10-Q'),filing(4,form='10-K/A')]),2017,1)
        self.assertEqual(result['total_rows'],4);self.assertEqual(len(result['annual_filings']),3)
        self.assertEqual(result['annual_filings'][0]['cik'],'0000000001')
        self.assertEqual(result['annual_filings'][0]['accession'],'0000099999-17-000001')
        self.assertEqual(result['annual_filings'][1]['name'],'Private-like debtor')

    def test_malformed_row_path_quarter_and_empty_response_cannot_be_ignored(self):
        bodies=[b'<html>Access denied</html>',gzip.compress(b'garbage'),index_body(['1|broken']),
            index_body([filing().replace('edgar/data/1/','edgar/data/2/')]),
            index_body([filing().replace('.txt','/../../secrets')]),index_body([filing(filed='2017-04-01')])]
        for body in bodies:
            with self.subTest(body=body[:10]),self.assertRaises(ValueError):parse_index(body,2017,1)

    def test_duplicate_accession_agrees_or_fails_instead_of_choosing_name(self):
        result=parse_index(index_body([filing(),filing()]),2017,1)
        self.assertEqual(len(result['annual_filings']),1)
        with self.assertRaises(ValueError):parse_index(index_body([filing(),filing(name='Different issuer')]),2017,1)
        with self.assertRaises(ValueError):parse_index(index_body([filing(),filing(form='10-Q')]),2017,1)

    def test_real_joint_annual_filing_preserves_distinct_issuer_ciks(self):
        body=index_body(['1002910|AMEREN CORP|10-K|2016-02-26|edgar/data/1002910/0001002910-16-000205.txt',
                         '100826|UNION ELECTRIC CO|10-K|2016-02-26|edgar/data/100826/0001002910-16-000205.txt'])
        parsed=parse_index(body,2016,1)
        self.assertEqual(len(parsed['annual_filings']),2)
        panel=candidate_panel(plan(),[parsed])
        self.assertEqual([r['cik'] for r in panel['formations'][0]['roster']],['0000100826','0001002910'])

    def test_real_combined_nonannual_schedules_do_not_invalidate_annual_roster(self):
        combined=['1552890|JAVELIN MORTGAGE INVESTMENT CORP.|SC 13E3/A|2016-03-10|edgar/data/1552890/0001398432-16-000500.txt',
                  '1552890|JAVELIN MORTGAGE INVESTMENT CORP.|SC TO-T/A|2016-03-10|edgar/data/1552890/0001398432-16-000500.txt']
        parsed=parse_index(index_body(combined+[filing(1,filed='2016-02-01')]),2016,1)
        panel=candidate_panel(plan(),[parsed]);self.assertEqual(panel['formations'][0]['candidate_count'],1)

    def test_missing_original_name_is_retained_without_current_name_replacement(self):
        blank='1593547||485BPOS|2016-02-26|edgar/data/1593547/0001135428-16-001124.txt'
        parsed=parse_index(index_body([blank,filing(1,name='',filed='2016-02-01')]),2016,1)
        self.assertEqual(parsed['total_rows'],2)
        panel=candidate_panel(plan(),[parsed])
        row=panel['formations'][0]['sample'][0]
        self.assertEqual(row['cik'],'0000000001');self.assertEqual(row['name_at_latest_filing'],'')
        self.assertFalse(input_readiness(plan(),panel,None)['ready_for_performance'])

    def test_date_only_availability_excludes_same_day_and_future_and_expired_discovery(self):
        a=parse_index(index_body([filing(1),filing(2)]),2017,1)
        b=parse_index(index_body([filing(3,filed='2017-06-29'),filing(4,filed='2017-06-30')]),2017,2)
        c=parse_index(index_body([filing(5,filed='2017-07-01')]),2017,3)
        result=candidate_panel(plan(),[a,b,c]);first,second=result['formations']
        self.assertEqual([r['cik'] for r in first['roster']],['0000000001','0000000002','0000000003'])
        self.assertEqual([r['cik'] for r in second['roster']],['0000000001','0000000002','0000000003','0000000004','0000000005'])
        self.assertEqual(first['candidate_count'],3);self.assertFalse(result['historical_membership_qualified'])

    def test_sampling_is_stable_to_file_order_and_future_only_additions(self):
        earlier=parse_index(index_body([filing(cik) for cik in range(1,21)]),2017,1)
        reverse=parse_index(index_body([filing(cik) for cik in reversed(range(1,21))]),2017,1)
        future=parse_index(index_body([filing(21,filed='2018-02-01')]),2018,1)
        p=plan(limit=4)
        first=candidate_panel(p,[earlier])['formations'][0]
        self.assertEqual(first,candidate_panel(p,[reverse,future])['formations'][0])
        expected=[4,13,9,19]  # Independently frozen hashes for the hand-sized fixture.
        self.assertEqual([r['cik'] for r in first['sample']],[str(c).zfill(10) for c in expected])

    def test_cross_index_conflict_and_changed_floor_fail(self):
        a=parse_index(index_body([filing()]),2017,1)
        other={**a,'annual_filings':[dict(a['annual_filings'][0],name='Other name')]}
        with self.assertRaises(ValueError):candidate_panel(plan(),[a,other])
        with self.assertRaises(ValueError):candidate_panel({**plan(),'minimum_eligible':9},[a])
        nonannual=parse_index(index_body([filing(form='10-Q',filed='2017-04-01')]),2017,2)
        with self.assertRaises(ValueError):candidate_panel(plan(),[a,nonannual])


class ReadinessTests(unittest.TestCase):
    def inputs(self):
        p=plan(limit=10);panel=candidate_panel(p,[parse_index(index_body([filing(c) for c in range(1,13)]),2017,1)])
        entries=[]
        for formation in panel['formations']:
            for row in formation['sample']:
                for check in CHECKS:
                    entries.append(dict(formation=formation['formation'],cik=row['cik'],check=check,status='passed',
                        reviewer='Accounting reviewer',reviewed_at='2026-10-03',evidence_files=['review.json']))
        evidence=dict(schema_version=1,study_plan_hash=content_hash(p),candidate_panel_hash=content_hash(panel),checks=entries)
        return p,panel,evidence

    def test_missing_proof_remains_missing_without_sample_replacement(self):
        p,panel,_=self.inputs();r=input_readiness(p,panel,None)
        self.assertEqual([x['sample_count'] for x in r['coverage']],[10,10])
        self.assertEqual([x['complete_review_candidates'] for x in r['coverage']],[0,0])
        self.assertFalse(r['performance_enabled']);self.assertFalse(r['ready_for_performance'])
        self.assertEqual(len(r['rows']),20)

    def test_complete_review_is_distinct_from_performance_enablement(self):
        p,panel,evidence=self.inputs();r=input_readiness(p,panel,evidence)
        self.assertTrue(r['review_floor_passed']);self.assertFalse(r['ready_for_performance'])
        self.assertFalse(r['performance_enabled'])

    def test_missing_unknown_duplicate_future_and_unbound_proof_fail_closed(self):
        p,panel,e=self.inputs()
        variants=[dict(e,study_plan_hash='0'*64),dict(e,candidate_panel_hash='0'*64),
                  dict(e,checks=e['checks']+[e['checks'][0]]),dict(e,checks=[dict(e['checks'][0],cik='9999999999')]),
                  dict(e,checks=[dict(e['checks'][0],reviewed_at='2027-01-01')]),
                  dict(e,checks=[dict(e['checks'][0],evidence_files=[])]),
                  dict(e,checks=[dict(e['checks'][0],evidence_files=['../../outside'])])]
        for v in variants:
            with self.subTest(v=v.keys()),self.assertRaises(ValueError):input_readiness(p,panel,v)
        partial=input_readiness(p,panel,dict(e,checks=e['checks'][1:]))
        self.assertFalse(partial['review_floor_passed'])
        self.assertEqual(partial['coverage'][0]['complete_review_candidates'],9)


if __name__=='__main__':unittest.main()
