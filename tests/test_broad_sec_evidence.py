"""Historical evidence cannot become a universe or strategy pass."""
from datetime import date
import unittest

from research.broad_sec_evidence import archive_requests,joined_history,annual_references,parse_header,issuer_audit


def columns(accn='0000099999-21-000001',filed='2021-03-01',report='2020-12-31',form='10-K'):
    return dict(accessionNumber=[accn],filingDate=[filed],reportDate=[report],form=[form],
        acceptanceDateTime=[filed+'T18:00:00Z'],primaryDocument=['annual.htm'])


def sample():
    return dict(cik='0000000001',formation='2021-06-30',name_at_latest_filing='Original name',
        filings=[dict(cik='0000000001',accession='0000099999-21-000001',filed='2021-03-01',form='10-K')])


def submission():
    return dict(cik=1,tickers=[],name='Current changed name',sic='6021',
        filings=dict(recent=columns(),files=[]))


def header(cik=1,sic='Manufacturing [3571]'):
    return (f'<SEC-HEADER>\nACCESSION NUMBER: 0000099999-21-000001\nCONFORMED SUBMISSION TYPE: 10-K\n'
        f'CONFORMED PERIOD OF REPORT: 20201231\nFILED AS OF DATE: 20210301\nFILER:\nCOMPANY DATA:\n'
        f'COMPANY CONFORMED NAME: Original name\nCENTRAL INDEX KEY: {cik:010d}\n'
        f'STANDARD INDUSTRIAL CLASSIFICATION: {sic}\n</SEC-HEADER>').encode()


class HistoryTests(unittest.TestCase):
    def test_null_submission_filing_structure_is_an_explicit_schema_error(self):
        with self.assertRaises(ValueError):archive_requests('0000000001',dict(submission(),filings=None))

    def test_only_issuer_safe_intersecting_archives_are_requested(self):
        sub=submission();sub['filings']['files']=[
            dict(name='CIK0000000001-submissions-001.json',filingFrom='2010-01-01',filingTo='2020-01-01'),
            dict(name='CIK0000000001-submissions-002.json',filingFrom='2000-01-01',filingTo='2010-01-01')]
        self.assertEqual(list(archive_requests('0000000001',sub)),['CIK0000000001-submissions-001.json'])
        for name in ('../secret.json','CIK0000000002-submissions-001.json','https://other/a.json'):
            sub['filings']['files'][0]['name']=name
            with self.assertRaises(ValueError):archive_requests('0000000001',sub)

    def test_recent_and_archive_join_retains_primary_document_and_conflicts_fail(self):
        result=joined_history('0000000001',[submission(),columns(accn='0000099999-20-000001',filed='2020-03-01',report='2019-12-31')])
        self.assertEqual(len(result),2);self.assertEqual(result['0000099999-21-000001']['primary_document'],'annual.htm')
        with self.assertRaises(ValueError):joined_history('0000000001',[submission(),columns(filed='2021-03-02')])
        bad=columns();bad['primaryDocument']=[]
        with self.assertRaises(ValueError):joined_history('0000000001',[bad])

    def test_nonannual_xsl_primary_paths_do_not_invalidate_annual_history(self):
        nonannual=columns(accn='0000099999-21-000002',form='4')
        nonannual['primaryDocument']=['xslF345X05/primary_doc.xml']
        index=joined_history('0000000001',[submission(),nonannual])
        self.assertEqual(index['0000099999-21-000001']['form'],'10-K')
        self.assertEqual(index['0000099999-21-000002']['primary_document'],'xslF345X05/primary_doc.xml')
        nonannual['primaryDocument']=['../private.xml']
        with self.assertRaises(ValueError):joined_history('0000000001',[nonannual])

    def test_reference_join_preserves_missing_mismatched_and_wrong_year_evidence(self):
        s=sample();index=joined_history(s['cik'],[submission()])
        row=annual_references(s,index)[0];self.assertEqual(row['join_status'],'matched')
        self.assertTrue(row['header_required']);self.assertEqual(row['report_date'],'2020-12-31')
        self.assertTrue(annual_references(s,{})[0]['header_required'])
        self.assertEqual(annual_references(s,{})[0]['join_status'],'missing')
        wrong=joined_history(s['cik'],[columns(report='2021-01-03')])
        self.assertFalse(annual_references(s,wrong)[0]['header_required'])
        mismatch=joined_history(s['cik'],[columns(filed='2021-03-02')])
        self.assertEqual(annual_references(s,mismatch)[0]['join_status'],'mismatched')
        self.assertTrue(annual_references(s,mismatch)[0]['header_required'])


class HeaderTests(unittest.TestCase):
    def test_literal_tagged_sec_endpoint_header_and_joint_filers(self):
        body=b'''<SEC-HEADER>0000002178-17-000019.hdr.sgml : 20170331
<ACCEPTANCE-DATETIME>20170331122740
<ACCESSION-NUMBER>0000002178-17-000019
<TYPE>10-K
<PUBLIC-DOCUMENT-COUNT>65
<PERIOD>20161231
<FILING-DATE>20170331
<DATE-OF-FILING-DATE-CHANGE>20170331
<FILER>
<COMPANY-DATA>
<CONFORMED-NAME>ADAMS RESOURCES & ENERGY, INC.
<CIK>0000002178
<ASSIGNED-SIC>5172
<FISCAL-YEAR-END>0926
</COMPANY-DATA>
</FILER>
</SEC-HEADER>'''
        expected=dict(accession='0000002178-17-000019',filed='2017-03-31',form='10-K')
        r=parse_header(body,'0000002178',expected)
        self.assertEqual(r['sic'],'5172');self.assertEqual(r['report_date'],'2016-12-31')
        extra=b'<FILER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Co-filer\n<CIK>0000000002\n<ASSIGNED-SIC>6021\n</COMPANY-DATA>\n</FILER>\n'
        joint=body.replace(b'</SEC-HEADER>',extra+b'</SEC-HEADER>')
        self.assertEqual(parse_header(joint,'0000000002',expected)['sic'],'6021')
        with self.assertRaises(ValueError):parse_header(joint,'0000000003',expected)
        with self.assertRaises(ValueError):parse_header(body.replace(b'<TYPE>10-K',b'<TYPE>10-Q'),'0000002178',expected)

    def test_non_utf8_original_name_is_preserved_with_explicit_encoding(self):
        body=header().replace(b'Original name','Société'.encode('latin-1'))
        r=parse_header(body,'0000000001',sample()['filings'][0])
        self.assertEqual(r['original_name'],'Société');self.assertEqual(r['encoding'],'latin-1')

    def test_original_issuer_header_is_observation_not_historical_listing_pass(self):
        r=parse_header(header(),'0000000001',sample()['filings'][0])
        self.assertEqual(r['sic'],'3571');self.assertEqual(r['original_name'],'Original name')
        self.assertFalse(r['historical_security_qualified'])
        missing=parse_header(header(sic=''),'0000000001',sample()['filings'][0])
        self.assertIsNone(missing['sic'])

    def test_joint_filing_selects_exact_cik_and_missing_wrong_identity_fails(self):
        joint=header().replace(b'</SEC-HEADER>',b'FILER:\nCOMPANY DATA:\nCOMPANY CONFORMED NAME: Other\nCENTRAL INDEX KEY: 0000000002\nSTANDARD INDUSTRIAL CLASSIFICATION: Bank [6021]\n</SEC-HEADER>')
        self.assertEqual(parse_header(joint,'0000000002',sample()['filings'][0])['sic'],'6021')
        for body in (b'<html>blocked</html>',header(cik=3),header().replace(b'20210301',b'20210302'),header().replace(b'10-K',b'10-Q')):
            with self.assertRaises(ValueError):parse_header(body,'0000000001',sample()['filings'][0])


class ComponentTests(unittest.TestCase):
    def facts(self):
        base=dict(accn='0000099999-21-000001',filed='2021-03-01',form='10-K',end='2020-12-31')
        return dict(cik=1,facts={'us-gaap':{
            'GrossProfit':{'units':{'USD':[dict(base,start='2020-01-01',val=40)]}},
            'Assets':{'units':{'USD':[dict(base,val=100)]}},
            'CommonStockSharesOutstanding':{'units':{'shares':[dict(base,val=10),dict(base,end='2020-12-30',val=20)]}}}})

    def test_coherent_components_and_exact_december_shares_remain_unqualified(self):
        s=sample();r=issuer_audit(s,submission(),self.facts(),joined_history(s['cik'],[submission()]))
        self.assertEqual(str(r['components']['gross_profitability']['score']),'0.4')
        self.assertEqual(len(r['exact_december_shares']),1)
        self.assertFalse(r['qualified']);self.assertEqual(r['historical_common_listing'],'missing')
        self.assertEqual(r['current_metadata']['sic'],'6021')

    def test_failed_absent_wrong_cik_and_later_vintage_do_not_erase_sample(self):
        s=sample()
        for sub,facts in ((None,None),(submission(),None),(dict(submission(),cik=2),self.facts())):
            r=issuer_audit(s,sub,facts,{})
            self.assertEqual(r['cik'],s['cik']);self.assertFalse(r['qualified']);self.assertIsNone(r['components'])
        facts=self.facts();facts['facts']['us-gaap']['GrossProfit']['units']['USD'][0]['filed']='2021-06-30'
        r=issuer_audit(s,submission(),facts,joined_history(s['cik'],[submission()]))
        self.assertIsNone(r['components']['gross_profitability'])

    def test_malformed_financial_value_is_an_issuer_error_not_a_global_failure(self):
        s=sample();facts=self.facts();facts['facts']['us-gaap']['Assets']['units']['USD'][0]['val']='invalid'
        r=issuer_audit(s,submission(),facts,joined_history(s['cik'],[submission()]))
        self.assertIsNotNone(r['error']);self.assertIsNone(r['components']);self.assertFalse(r['qualified'])


if __name__=='__main__':unittest.main()
