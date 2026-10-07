"""Hand-calculated original XBRL reconciliation and availability safeguards."""
from datetime import date
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.sec_reconcile import parse_instance, profitability, december_shares, reconcile_fact, instance_name, download_body, derive, audit, verify, primary_names, annual_equity, collect
from research.market_backtest import publish
from quant_core.data import Split
from quant_core.provenance import primitive


def document(facts, extra_context='', unit='iso:USD'):
    return ('''<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
        xmlns:g="http://fasb.org/us-gaap/2020-01-31" xmlns:dei="http://xbrl.sec.gov/dei/2020-01-31"
        xmlns:iso="http://www.xbrl.org/2003/iso4217" xmlns:c="http://example.com/2020">
        <xbrli:context id="annual"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:startDate>2020-01-01</xbrli:startDate><xbrli:endDate>2020-12-31</xbrli:endDate></xbrli:period></xbrli:context>
        <xbrli:context id="balance"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:instant>2020-12-31</xbrli:instant></xbrli:period></xbrli:context>'''+extra_context+
        '<xbrli:unit id="usd"><xbrli:measure>'+unit+'</xbrli:measure></xbrli:unit>'+
        '<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>'+facts+'</xbrli:xbrl>').encode()


def fact(tag,value,context='annual',unit='usd'):
    return '<'+tag+' contextRef="'+context+'" unitRef="'+unit+'" decimals="0">'+str(value)+'</'+tag+'>'


DIRECT={'status':'direct','rules':[]}
DERIVED={'status':'reviewed_derivation','rules':[{'from':'2016-01-01','through':'2025-12-31',
    'revenue':['us-gaap','Revenues'],'cost':['us-gaap','CostOfGoodsSold']}]}


class OriginalFactsTests(unittest.TestCase):
    def fixture(self):
        return parse_instance(document(fact('g:GrossProfit',40)+fact('g:Assets',100,'balance')))

    def test_original_units_and_periods_support_hand_calculated_score(self):
        rows=self.fixture()
        result=profitability(rows,DIRECT,1,date(2021,6,30),date(2021,3,1))
        self.assertEqual(result['score'],D('.4'))
        self.assertEqual(result['gross_profit'],D(40))
        self.assertEqual(result['end'],date(2020,12,31))

    def test_default_namespace_share_unit_and_whitespace_dates_are_valid(self):
        body=document(fact('g:CommonStockSharesOutstanding',20,'balance','shares'))
        body=body.replace(b'xmlns:xbrli=',b'xmlns="http://www.xbrl.org/2003/instance" xmlns:xbrli=')
        body=body.replace(b'>xbrli:shares<',b'>shares<').replace(b'>2020-12-31<',b'>\n2020-12-31\n<')
        rows=parse_instance(body)
        self.assertEqual(december_shares(rows,1,date(2021,6,30),date(2021,2,1))['value'],D(20))

    def test_same_day_future_and_wrong_fiscal_calendar_are_unavailable(self):
        rows=self.fixture()
        self.assertIsNone(profitability(rows,DIRECT,1,date(2021,6,30),date(2021,6,30)))
        self.assertIsNone(profitability(rows,DIRECT,1,date(2021,6,30),date(2021,7,1)))
        rows=parse_instance(document(fact('g:GrossProfit',40)+fact('g:Assets',100,'balance')).replace(b'2020-12-31',b'2021-01-03'))
        self.assertIsNone(profitability(rows,DIRECT,1,date(2021,6,30),date(2021,3,1)))

    def test_foreign_issuer_or_currency_cannot_supply_assets(self):
        rows=self.fixture()
        self.assertIsNone(profitability(rows,DIRECT,2,date(2021,6,30),date(2021,3,1)))
        euro=document(fact('g:GrossProfit',40)+fact('g:Assets',100,'balance'),unit='iso:EUR')
        self.assertIsNone(profitability(parse_instance(euro),DIRECT,1,date(2021,6,30),date(2021,3,1)))

    def test_segment_and_quarterly_profit_do_not_become_annual_entity_profit(self):
        scoped='''<xbrli:context id="segment"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier>
        <xbrli:segment><c:Business>Segment A</c:Business></xbrli:segment></xbrli:entity>
        <xbrli:period><xbrli:startDate>2020-01-01</xbrli:startDate><xbrli:endDate>2020-12-31</xbrli:endDate></xbrli:period></xbrli:context>'''
        rows=parse_instance(document(fact('g:GrossProfit',40,'segment')+fact('g:Assets',100,'balance'),scoped))
        self.assertIsNone(profitability(rows,DIRECT,1,date(2021,6,30),date(2021,3,1)))
        quarter=document(fact('g:GrossProfit',40)+fact('g:Assets',100,'balance')).replace(b'2020-01-01',b'2020-10-01')
        self.assertIsNone(profitability(parse_instance(quarter),DIRECT,1,date(2021,6,30),date(2021,3,1)))

    def test_duplicate_conflicts_and_nonfinite_values_fail_instead_of_zero_filling(self):
        with self.assertRaises(ValueError):parse_instance(document(fact('g:Assets',100,'balance')+fact('g:Assets',101,'balance')))
        with self.assertRaises(ValueError):parse_instance(document(fact('g:Assets','NaN','balance')))
        rows=parse_instance(document(fact('g:GrossProfit',40)+fact('g:Assets',0,'balance')))
        self.assertIsNone(profitability(rows,DIRECT,1,date(2021,6,30),date(2021,3,1)))

    def test_consistent_rounded_duplicates_use_most_precise_original_observation(self):
        finer=fact('g:Assets',1234000,'balance').replace('decimals="0"','decimals="-3"')
        coarse=fact('g:Assets',1230000,'balance').replace('decimals="0"','decimals="-4"')
        rows=parse_instance(document(coarse+finer))
        self.assertEqual(rows[0]['value'],D(1234000))
        self.assertEqual(rows[0]['decimals'],'-3')

    def test_unrelated_custom_note_duplicates_do_not_supply_or_block_components(self):
        rows=parse_instance(document(fact('c:UnrelatedExpense',100)+fact('c:UnrelatedExpense',101)+fact('g:Assets',100,'balance')))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['tag'],'Assets')

    def test_amendment_without_xbrl_is_preserved_as_missing_and_collection_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);raw=output/'raw'/'doc';raw.mkdir(parents=True)
            d={'symbol':'AAPL','cik':'0000000001','accession':'0000000001-21-000001','primary_document':'amendment.htm'}
            plan={'documents':{'doc':d}}
            prefix='https://www.sec.gov/Archives/edgar/data/1/000000000121000001/'
            for name,body,url in [('index.json',b'{"directory":{"item":[{"name":"amendment.htm"}]}}',prefix+'index.json'),
                                  ('primary.html',b'<html>Amendment; no structured instance</html>',prefix+'amendment.htm')]:
                (raw/name).write_bytes(body)
                publish(raw/(name+'.request.json'),{'url':url,'status':200,'body_file':name,'sha256':hashlib.sha256(body).hexdigest()})
            with patch('research.sec_reconcile.register',return_value=plan),patch('research.sec_reconcile.urlopen',side_effect=AssertionError('offline')):
                collect(output,None,None,None)
            result=json.loads((output/'COLLECTION.json').read_text())['documents']['doc']
            self.assertIsNone(result['instance_name'])
            self.assertTrue(result['instance_unavailable'])
            self.assertEqual((raw/'primary.html').read_bytes(),b'<html>Amendment; no structured instance</html>')

    def test_original_reconciliation_requires_exact_tag_entity_value_and_context(self):
        rows=self.fixture()
        expected={'tag':'Assets','start':None,'end':'2020-12-31','units':'USD','value':'100'}
        self.assertEqual(reconcile_fact(rows,1,expected)['value'],D(100))
        for field,value in [('value','101'),('end','2020-12-30'),('tag','StockholdersEquity'),('units','shares')]:
            with self.assertRaises(ValueError):reconcile_fact(rows,1,{**expected,field:value})

    def test_reviewed_mapping_selects_correct_cost_and_never_generic_tag_priority(self):
        rows=parse_instance(document(fact('g:Revenues',100)+fact('g:CostOfGoodsSold',60)+
            fact('g:CostOfGoodsAndServicesSold',1)+fact('g:Assets',100,'balance')))
        self.assertEqual(profitability(rows,DERIVED,1,date(2021,6,30),date(2021,3,1))['score'],D('.4'))
        self.assertIsNone(profitability(rows,{'status':'blocked','reason':'incompatible scope'},1,date(2021,6,30),date(2021,3,1)))

    def test_membership_income_is_removed_only_by_explicit_reviewed_formula(self):
        profile={'status':'reviewed_derivation','rules':[{'from':'2016-01-01','through':'2025-12-31',
            'revenue':['us-gaap','Revenues'],'cost':['us-gaap','CostOfGoodsSold'],
            'subtract_revenue':['us-gaap','RevenueFromEnrollmentAndRegistrationFeesExcludingHospitalityEnterprises']}]}
        rows=parse_instance(document(fact('g:Revenues',105)+fact('g:RevenueFromEnrollmentAndRegistrationFeesExcludingHospitalityEnterprises',5)+
            fact('g:CostOfGoodsSold',60)+fact('g:Assets',100,'balance')))
        self.assertEqual(profitability(rows,profile,1,date(2021,6,30),date(2021,3,1))['score'],D('.4'))
        missing=parse_instance(document(fact('g:Revenues',105)+fact('g:CostOfGoodsSold',60)+fact('g:Assets',100,'balance')))
        self.assertIsNone(profitability(missing,profile,1,date(2021,6,30),date(2021,3,1)))

    def test_date_bounded_reviewed_direct_rule_does_not_invent_later_derivations(self):
        profile={'status':'reviewed_derivation','rules':[
            {'from':'2016-01-01','through':'2017-12-31','revenue':['us-gaap','SalesRevenueNet'],'cost':['us-gaap','CostOfGoodsSold']},
            {'from':'2018-01-01','through':'2025-12-31','gross_profit':['us-gaap','GrossProfit']}]}
        result=profitability(self.fixture(),profile,1,date(2021,6,30),date(2021,3,1))
        self.assertEqual(result['score'],D('.4'))
        self.assertEqual(result['method'],'reviewed_direct')
        misleading=parse_instance(document(fact('g:Revenues',105)+fact('g:CostOfGoodsSold',60)+fact('g:Assets',100,'balance')))
        self.assertIsNone(profitability(misleading,profile,1,date(2021,6,30),date(2021,3,1)))
        early=document(fact('g:SalesRevenueNet',100)+fact('g:CostOfGoodsSold',60)+fact('g:Assets',100,'balance'))
        early=early.replace(b'2020-01-01',b'2017-01-01').replace(b'2020-12-31',b'2017-12-31')
        self.assertEqual(profitability(parse_instance(early),profile,1,date(2018,6,29),date(2018,2,1))['score'],D('.4'))

    def test_dei_exact_dated_outstanding_shares_are_evidence_but_not_automatic_value_readiness(self):
        rows=parse_instance(document(fact('dei:EntityCommonStockSharesOutstanding',20,'balance','shares')+
            fact('g:CommonStockSharesIssued',100,'balance','shares')+
            fact('g:PreferredStockSharesAuthorized',50,'balance','shares')))
        result=december_shares(rows,1,date(2021,6,30),date(2021,2,1))
        self.assertEqual(result['value'],D(20))
        self.assertFalse(result['share_basis_reviewed'])

    def test_december_month_and_january_cover_dates_do_not_prove_december_31(self):
        body=document(fact('g:CommonStockSharesOutstanding',20,'balance','shares'))
        for wrong in (b'2020-12-27',b'2021-01-15'):
            self.assertIsNone(december_shares(parse_instance(body.replace(b'2020-12-31',wrong)),1,date(2021,6,30),date(2021,2,1)))

    def test_disagreeing_share_counts_are_not_chosen_by_tag_preference(self):
        rows=parse_instance(document(fact('g:CommonStockSharesOutstanding',20,'balance','shares')+
            fact('dei:EntityCommonStockSharesOutstanding',21,'balance','shares')))
        with self.assertRaises(ValueError):december_shares(rows,1,date(2021,6,30),date(2021,2,1))

    def test_rounded_gaap_and_exact_dei_shares_reconcile_without_tag_preference(self):
        rounded=fact('g:CommonStockSharesOutstanding',586500000,'balance','shares').replace('decimals="0"','decimals="-5"')
        exact=fact('dei:EntityCommonStockSharesOutstanding',586486024,'balance','shares').replace('decimals="0"','decimals="INF"')
        for facts in (rounded+exact,exact+rounded):
            result=december_shares(parse_instance(document(facts)),1,date(2021,6,30),date(2021,2,1))
            self.assertEqual(result['value'],D(586486024))
            self.assertEqual(len(result['components']),2)
            self.assertEqual(result['selection_method'],'consistent_declared_accuracy')
            self.assertFalse(result['share_basis_reviewed'])

    def test_directory_discovery_rejects_multiple_instances_and_unsafe_paths(self):
        index={'directory':{'item':[{'name':'FilingSummary.xml'},{'name':'issuer_cal.xml'},{'name':'issuer-20201231_htm.xml'}]}}
        self.assertEqual(instance_name(index),'issuer-20201231_htm.xml')
        for names in (['first.xml','second.xml'],['../original.xml']):
            with self.assertRaises(ValueError):instance_name({'directory':{'item':[{'name':n} for n in names]}})

    def test_unrelated_ownership_form_display_paths_do_not_block_annual_collection(self):
        payload={'accessionNumber':['annual','ownership'],'primaryDocument':['original.htm','xslF345X03/form4.xml'],
                 'form':['10-K','4']}
        self.assertEqual(primary_names([payload]),{'annual':'original.htm'})
        payload['primaryDocument'][0]='../original.htm'
        with self.assertRaises(ValueError):primary_names([payload])

    def test_annual_parent_equity_does_not_require_an_unrelated_revenue_tag(self):
        rows=parse_instance(document(fact('g:StockholdersEquity',30,'balance')+fact('g:Assets',100,'balance')))
        result=annual_equity(rows,1,date(2021,6,30),date(2021,3,1),'2020-12-31')
        self.assertEqual(result['parent']['value'],D(30))
        self.assertEqual(result['preferred_status'],'annual_issuer_obligation_review_required')
        self.assertIsNone(annual_equity(rows,1,date(2021,6,30),date(2021,3,1),'2021-01-03'))

    def test_authorized_preferred_never_proves_zero_outstanding_and_values_share_fiscal_date(self):
        rows=parse_instance(document(fact('g:StockholdersEquity',30,'balance')+
            fact('g:PreferredStockSharesAuthorized',50,'balance','shares')))
        self.assertEqual(annual_equity(rows,1,date(2021,6,30),date(2021,3,1),'2020-12-31')['preferred_status'],
                         'annual_issuer_obligation_review_required')
        rows=parse_instance(document(fact('g:StockholdersEquity',30,'balance')+
            fact('g:PreferredStockSharesOutstanding',0,'balance','shares')))
        result=annual_equity(rows,1,date(2021,6,30),date(2021,3,1),'2020-12-31')
        self.assertEqual(result['preferred_status'],'explicit_zero_outstanding_original_evidence')
        self.assertEqual(result['preferred_components'][0]['value'],D(0))

    def test_original_cache_preserves_bytes_and_rejects_changes_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'original.xml';body=document(fact('g:Assets',100,'balance'));path.write_bytes(body)
            url='https://www.sec.gov/Archives/edgar/data/1/000000000121000001/original.xml'
            (path.with_suffix('.xml.request.json')).write_text(json.dumps({'url':url,'status':200,
                'sha256':hashlib.sha256(body).hexdigest(),'body_file':path.name}))
            with patch('research.sec_reconcile.urlopen',side_effect=AssertionError('cached reads must be offline')):
                self.assertEqual(download_body(path,url,None),body)
                with self.assertRaises(ValueError):download_body(path,url+'?changed',None)
                path.write_bytes(body+b' ')
                with self.assertRaises(ValueError):download_body(path,url,None)

    def test_reconciled_components_do_not_relax_coverage_or_qualify_value(self):
        records=self.fixture()+parse_instance(document(fact('dei:EntityCommonStockSharesOutstanding',20,'balance','shares')))
        plan={'common_panel':['AAPL'],'formations':['2021-06-30'],'ciks':{'AAPL':'0000000001'},
              'documents':{'doc':{'symbol':'AAPL','cik':'0000000001','accession':'original','filed':'2021-03-01','form':'10-K',
                                   'uses':[['2021-06-30','annual']]}}}
        old=[{'symbol':'AAPL','formation':'2021-06-30','gross_profitability':None,'parent_equity':None}]
        mappings={'minimum_eligible':10,'profiles':{'AAPL':DIRECT}}
        result=derive(plan,old,{'doc':records},mappings,[])
        self.assertEqual(result['coverage'][0]['profitability_components'],1)
        self.assertFalse(result['profitability_coverage_passed'])
        self.assertFalse(result['value_ready'])
        self.assertEqual(result['rows'][0]['profitability']['score'],'0.4')
        self.assertFalse(result['rows'][0]['december_shares']['share_basis_reviewed'])

    def test_unresolved_aggregate_original_disagreement_blocks_coverage(self):
        records=parse_instance(document(fact('g:GrossProfit',50)+fact('g:Assets',100,'balance')))
        d={'symbol':'AAPL','cik':'0000000001','accession':'original','filed':'2021-03-01','form':'10-K',
           'uses':[['2021-06-30','annual']]}
        plan={'common_panel':['AAPL'],'formations':['2021-06-30'],'ciks':{'AAPL':'0000000001'},'documents':{'doc':d}}
        old=[{'symbol':'AAPL','formation':'2021-06-30','parent_equity':None,'gross_profitability':{
            'accession':'original','gross_profit_record':{'tag':'GrossProfit','start':'2020-01-01','end':'2020-12-31','units':'USD','value':'40'},
            'assets_record':{'tag':'Assets','start':None,'end':'2020-12-31','units':'USD','value':'100'}}}]
        result=derive(plan,old,{'doc':records},{'minimum_eligible':10,'profiles':{'AAPL':DIRECT}},[])
        self.assertFalse(result['rows'][0]['previous_profit_reconciled'])
        self.assertIsNone(result['rows'][0]['profitability'])
        self.assertEqual(result['coverage'][0]['profitability_components'],0)

    def test_failed_later_original_document_cannot_fall_back_to_older_score(self):
        d={'symbol':'AAPL','cik':'0000000001','accession':'original','filed':'2021-03-01','form':'10-K',
           'uses':[['2021-06-30','annual']]}
        plan={'common_panel':['AAPL'],'formations':['2021-06-30'],'ciks':{'AAPL':'0000000001'},
              'documents':{'first':d,'later':{**d,'accession':'amended','filed':'2021-04-01'}}}
        old=[{'symbol':'AAPL','formation':'2021-06-30','parent_equity':None,'gross_profitability':None}]
        result=derive(plan,old,{'first':self.fixture(),'later':()},{'minimum_eligible':10,'profiles':{'AAPL':DIRECT}},[],
                      document_errors={'later':'Conflicting original contexts'})
        self.assertIsNone(result['rows'][0]['profitability'])
        self.assertEqual(result['coverage'][0]['profitability_components'],0)

    def test_annual_context_conflict_cannot_fall_back_to_older_score(self):
        d={'symbol':'AAPL','cik':'0000000001','accession':'original','filed':'2021-03-01','form':'10-K',
           'uses':[['2021-06-30','annual']]}
        plan={'common_panel':['AAPL'],'formations':['2021-06-30'],'ciks':{'AAPL':'0000000001'},
              'documents':{'first':d,'later':{**d,'accession':'amended','filed':'2021-04-01','form':'10-K/A'}}}
        extra='''<xbrli:context id="other"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:startDate>2019-12-20</xbrli:startDate><xbrli:endDate>2020-12-31</xbrli:endDate></xbrli:period></xbrli:context>'''
        amended=parse_instance(document(fact('g:GrossProfit',60)+fact('g:GrossProfit',61,'other')+fact('g:Assets',100,'balance'),extra))
        old=[{'symbol':'AAPL','formation':'2021-06-30','parent_equity':None,'gross_profitability':None}]
        result=derive(plan,old,{'first':self.fixture(),'later':amended},{'minimum_eligible':10,'profiles':{'AAPL':DIRECT}},[])
        self.assertIsNone(result['rows'][0]['profitability'])
        self.assertEqual(result['coverage'][0]['profitability_components'],0)
        self.assertEqual(result['rows'][0]['errors'][0]['component'],'profitability_context')

    def test_share_context_conflict_cannot_select_another_documents_count(self):
        d={'symbol':'AAPL','cik':'0000000001','accession':'original','filed':'2021-03-01','form':'10-Q',
           'uses':[['2021-06-30','shares']]}
        plan={'common_panel':['AAPL'],'formations':['2021-06-30'],'ciks':{'AAPL':'0000000001'},
              'documents':{'first':d,'later':{**d,'accession':'later','filed':'2021-04-01'}}}
        good=parse_instance(document(fact('g:CommonStockSharesOutstanding',20,'balance','shares')))
        conflict=parse_instance(document(fact('g:CommonStockSharesOutstanding',20,'balance','shares')+
            fact('dei:EntityCommonStockSharesOutstanding',21,'balance','shares')))
        old=[{'symbol':'AAPL','formation':'2021-06-30','parent_equity':None,'gross_profitability':None}]
        result=derive(plan,old,{'first':good,'later':conflict},{'minimum_eligible':10,'profiles':{'AAPL':DIRECT}},[])
        self.assertIsNone(result['rows'][0]['december_shares'])
        self.assertEqual(result['coverage'][0]['exact_december_share_components'],0)

    def test_intervening_split_is_flagged_instead_of_assuming_price_share_basis_matches(self):
        rows=parse_instance(document(fact('g:CommonStockSharesOutstanding',20,'balance','shares')))
        plan={'common_panel':['AAPL'],'formations':['2021-06-30'],'ciks':{'AAPL':'0000000001'},
              'documents':{'doc':{'symbol':'AAPL','cik':'0000000001','accession':'original','filed':'2021-03-01','form':'10-Q',
                                   'uses':[['2021-06-30','shares']]}}}
        old=[{'symbol':'AAPL','formation':'2021-06-30','gross_profitability':None,'parent_equity':None}]
        splits=primitive([Split('AAPL',date(2021,2,1),D(2))])
        result=derive(plan,old,{'doc':rows},{'minimum_eligible':10,'profiles':{'AAPL':DIRECT}},splits)
        shares=result['rows'][0]['december_shares']
        self.assertEqual(shares['intervening_splits'][0]['ratio'],'2')
        self.assertFalse(shares['share_basis_reviewed'])

    def test_report_recomputes_original_arithmetic_and_rejects_resealed_wrong_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);previous=output/'previous';previous.mkdir();mappings=output/'mappings.json'
            publish(mappings,{'minimum_eligible':10,'profiles':{'AAPL':DIRECT}})
            publish(previous/'FEASIBILITY.json',{'rows':[{'symbol':'AAPL','formation':'2021-06-30',
                'gross_profitability':None,'parent_equity':None}]})
            d={'symbol':'AAPL','cik':'0000000001','accession':'0000000001-21-000001',
               'filed':'2021-03-01','form':'10-K','uses':[['2021-06-30','annual']]}
            plan={'previous_path':str(previous),'mapping_path':str(mappings),'common_panel':['AAPL'],
                  'formations':['2021-06-30'],'ciks':{'AAPL':'0000000001'},'documents':{'doc':d},
                  'market_snapshot':'fixture','market_dataset_hash':'fixture'}
            publish(output/'INPUT_PLAN.json',plan)
            prefix='https://www.sec.gov/Archives/edgar/data/1/000000000121000001/'
            collection={'documents':{'doc':{'instance_name':'original.xml','index_url':prefix+'index.json','instance_url':prefix+'original.xml'}}}
            publish(output/'COLLECTION.json',collection);raw=output/'raw'/'doc';raw.mkdir(parents=True)
            for name,body,url in (
                ('index.json',json.dumps({'directory':{'item':[{'name':'original.xml'}]}}).encode(),prefix+'index.json'),
                ('instance.xml',document(fact('g:GrossProfit',40)+fact('g:Assets',100,'balance')),prefix+'original.xml')):
                (raw/name).write_bytes(body)
                publish(raw/(name+'.request.json'),{'status':200,'url':url,'body_file':name,'sha256':hashlib.sha256(body).hexdigest()})
            with patch('research.sec_reconcile.make_plan',return_value=plan),patch('research.sec_reconcile.load_snapshot',return_value=SimpleNamespace(dataset_hash='fixture',actions=())):
                audit(output)
                self.assertEqual(verify(output)['issuer_years'],1)
                result=json.loads((output/'RECONCILIATION.json').read_text())
                self.assertEqual(result['rows'][0]['profitability']['score'],'0.4')
                result['rows'][0]['profitability']['score']='0.9'
                (output/'RECONCILIATION.json').write_text(json.dumps(result))
                registry=json.loads((output/'REPORT_HASHES.json').read_text())
                registry['files']['RECONCILIATION.json']=hashlib.sha256((output/'RECONCILIATION.json').read_bytes()).hexdigest()
                (output/'REPORT_HASHES.json').write_text(json.dumps(registry))
                with self.assertRaises(ValueError):verify(output)


if __name__=='__main__':unittest.main()
