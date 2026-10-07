"""Historical filing availability and hand-derived coherent accounting examples."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.sec_fundamentals import filing_index, fact_records, audit_issuer, issuer_identity, audit, verify, download
from research.market_backtest import publish


def filing(accn='first',filed='2021-03-01',form='10-K',report='2020-12-31'):
    return {'accessionNumber':[accn],'filingDate':[filed],'form':[form],
            'reportDate':[report],'acceptanceDateTime':[filed+'T18:00:00Z']}


def fact(value,accn='first',filed='2021-03-01',start=None,end='2020-12-31',form='10-K'):
    row={'val':value,'accn':accn,'filed':filed,'form':form,'end':end,'fy':2021,'fp':'FY'}
    if start is not None:row['start']=start
    return row


def company(tags):
    return {'cik':1,'facts':{'us-gaap':{tag:{'units':{'USD':rows}} for tag,rows in tags.items()}}}


class FilingHistoryTests(unittest.TestCase):
    def test_documented_xom_predecessor_is_valid_only_before_the_transition(self):
        submission={'cik':'0000034088','tickers':[]};facts={'cik':34088}
        identity=issuer_identity('XOM','0000034088',submission,facts,['2026-06-30'])
        self.assertEqual(identity['status'],'documented_predecessor_for_formation_dates')
        self.assertEqual(identity['effective_date'],'2026-07-01')
        with self.assertRaises(ValueError):
            issuer_identity('XOM','0000034088',submission,facts,['2026-07-01'])
        with self.assertRaises(ValueError):
            issuer_identity('AAPL','0000320193',{'cik':320193,'tickers':[]},{'cik':320193},['2026-06-30'])
        with self.assertRaises(ValueError):
            issuer_identity('XOM','0000034088',submission,{'cik':2115436},['2026-06-30'])

    def test_recent_and_historical_indexes_join_and_conflicts_are_rejected(self):
        a=filing();b=filing('amended','2021-07-01','10-K/A')
        index=filing_index([{'filings':{'recent':a}},b,a])
        self.assertEqual(set(index),{'first','amended'})
        with self.assertRaises(ValueError):filing_index([a,filing(filed='2021-03-02')])
        bad=deepcopy(a);bad['form']=[]
        with self.assertRaises(ValueError):filing_index([bad])

    def test_later_restatement_and_same_day_filing_cannot_rewrite_prior_information(self):
        facts=company({'GrossProfit':[fact(40,start='2020-01-01'),
            fact(60,'amended','2021-07-01',start='2020-01-01',form='10-K/A')]})
        index=filing_index([filing(),filing('amended','2021-07-01','10-K/A')])
        before=fact_records(facts,index,'GrossProfit',date(2021,6,30),duration='annual')
        self.assertEqual([r['value'] for r in before],[D(40)])
        same=fact_records(facts,index,'GrossProfit',date(2021,7,1),duration='annual')
        self.assertEqual([r['value'] for r in same],[D(40)])
        later=fact_records(facts,index,'GrossProfit',date(2021,7,2),duration='annual')
        self.assertEqual({r['value'] for r in later},{D(40),D(60)})

    def test_period_dates_override_fiscal_year_label_and_exclude_short_period(self):
        facts=company({'GrossProfit':[fact(40,start='2020-01-01'),fact(9,start='2020-10-01')]})
        rows=fact_records(facts,filing_index([filing()]),'GrossProfit',date(2021,6,30),duration='annual')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['end'],date(2020,12,31))

    def test_unjoined_or_mismatched_publication_metadata_is_not_usable(self):
        facts=company({'Assets':[fact(100)]})
        for index in ({},filing_index([filing(filed='2021-03-02')]),filing_index([filing(form='10-K/A')])):
            with self.assertRaises(ValueError):fact_records(facts,index,'Assets',date(2021,6,30))

    def test_conflicting_same_context_is_not_resolved_by_input_order(self):
        facts=company({'Assets':[fact(100),fact(101)]})
        with self.assertRaises(ValueError):fact_records(facts,filing_index([filing()]),'Assets',date(2021,6,30))
        facts['facts']['us-gaap']['Assets']['units']['USD']=[fact(100),fact(100)]
        self.assertEqual(len(fact_records(facts,filing_index([filing()]),'Assets',date(2021,6,30))),1)

    def test_wrong_units_missing_tags_and_nonfinite_values_do_not_become_zero(self):
        facts=company({'Assets':[fact(100)]});facts['facts']['us-gaap']['Assets']['units']={'EUR':[fact(100)]}
        self.assertEqual(fact_records(facts,filing_index([filing()]),'Assets',date(2021,6,30)),())
        self.assertEqual(fact_records(facts,filing_index([filing()]),'Missing',date(2021,6,30)),())
        with self.assertRaises(ValueError):fact_records(company({'Assets':[fact('NaN')]}),filing_index([filing()]),'Assets',date(2021,6,30))


class CoherentAccountingTests(unittest.TestCase):
    def fixture(self):
        return company({'GrossProfit':[fact(40,start='2020-01-01')],'Assets':[fact(100)],
                        'StockholdersEquity':[fact(30)]}),filing_index([filing()])

    def test_direct_profitability_is_hand_calculated_and_preferred_is_not_assumed_zero(self):
        facts,index=self.fixture();r=audit_issuer(facts,index,date(2021,6,30))
        self.assertEqual(r['gross_profitability']['score'],D('.4'))
        self.assertEqual(r['parent_equity']['value'],D(30))
        self.assertEqual(r['value_status'],'preferred_stock_and_market_equity_review_required')
        self.assertFalse(r['qualified'])

    def test_components_from_different_accessions_cannot_form_a_score(self):
        facts,index=self.fixture()
        facts['facts']['us-gaap']['Assets']['units']['USD']=[fact(100,'other','2021-04-01')]
        index.update(filing_index([filing('other','2021-04-01')]))
        r=audit_issuer(facts,index,date(2021,6,30))
        self.assertIsNone(r['gross_profitability'])

    def test_latest_available_restatement_changes_future_score_only(self):
        facts,index=self.fixture()
        facts['facts']['us-gaap']['GrossProfit']['units']['USD'].append(fact(60,'amended','2021-07-01',start='2020-01-01',form='10-K/A'))
        facts['facts']['us-gaap']['Assets']['units']['USD'].append(fact(100,'amended','2021-07-01',form='10-K/A'))
        index.update(filing_index([filing('amended','2021-07-01','10-K/A')]))
        self.assertEqual(audit_issuer(facts,index,date(2021,6,30))['gross_profitability']['score'],D('.4'))
        self.assertEqual(audit_issuer(facts,index,date(2021,7,2))['gross_profitability']['score'],D('.6'))

    def test_missing_gross_profit_keeps_possible_derivation_unqualified(self):
        facts=company({'Revenues':[fact(100,start='2020-01-01')],
                       'CostOfGoodsAndServicesSold':[fact(60,start='2020-01-01')],'Assets':[fact(100)]})
        r=audit_issuer(facts,filing_index([filing()]),date(2021,6,30))
        self.assertIsNone(r['gross_profitability'])
        self.assertEqual(r['possible_gross_profit_derivations'][0]['gross_profit'],D(40))
        self.assertFalse(r['possible_gross_profit_derivations'][0]['mapping_reviewed'])

    def test_nonpositive_assets_and_inclusive_equity_are_not_silent_substitutes(self):
        facts=company({'GrossProfit':[fact(40,start='2020-01-01')],'Assets':[fact(0)],
                       'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest':[fact(30)]})
        r=audit_issuer(facts,filing_index([filing()]),date(2021,6,30))
        self.assertIsNone(r['gross_profitability'])
        self.assertIsNone(r['parent_equity'])

    def test_weighted_average_shares_are_not_market_equity_shares(self):
        facts,index=self.fixture();facts['facts']['us-gaap']['WeightedAverageNumberOfSharesOutstandingBasic']={'units':{'shares':[fact(20)]}}
        r=audit_issuer(facts,index,date(2021,6,30))
        self.assertEqual(r['december_outstanding_shares'],[])


class EvidenceAuditTests(unittest.TestCase):
    def fixture(self,output):
        raw=output/'raw';raw.mkdir()
        plan={'schema_version':1,'ciks':{'AAPL':'0000320193'},'common_panel':['AAPL'],
              'formations':['2021-06-30'],'market_snapshot':'unused_fixture',
              'performance_evaluated':False,'qualified':False}
        publish(output/'INPUT_PLAN.json',plan)
        facts,index=CoherentAccountingTests().fixture();facts['cik']=320193
        submission={'cik':320193,'tickers':['AAPL'],'filings':{'recent':filing(),'files':[]}}
        for name,payload,url in (
            ('AAPL.facts',facts,'https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json'),
            ('AAPL.submissions',submission,'https://data.sec.gov/submissions/CIK0000320193.json')):
            publish(raw/(name+'.json'),payload)
            publish(raw/(name+'.request.json'),{'url':url,'status':200,'body_file':name+'.json',
                'sha256':hashlib.sha256((raw/(name+'.json')).read_bytes()).hexdigest()})
        return plan

    def test_full_report_is_recomputed_and_resealed_wrong_score_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);plan=self.fixture(output)
            with patch('research.sec_fundamentals.input_plan',return_value=plan):
                audit(output)
                self.assertEqual(verify(output)['verified_observations'],1)
                result=json.loads((output/'FEASIBILITY.json').read_text())
                self.assertEqual(result['rows'][0]['gross_profitability']['score'],'0.4')
                self.assertFalse(result['value_ready'])
                result['rows'][0]['gross_profitability']['score']='0.9'
                (output/'FEASIBILITY.json').write_text(json.dumps(result))
                manifest=json.loads((output/'REPORT_HASHES.json').read_text())
                manifest['files']['FEASIBILITY.json']=hashlib.sha256((output/'FEASIBILITY.json').read_bytes()).hexdigest()
                (output/'REPORT_HASHES.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):verify(output)

    def test_missing_raw_manifest_entry_does_not_silently_reduce_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);plan=self.fixture(output)
            with patch('research.sec_fundamentals.input_plan',return_value=plan):
                audit(output)
                manifest=json.loads((output/'INPUT_HASHES.json').read_text())
                del manifest['files']['raw/AAPL.facts.json']
                (output/'INPUT_HASHES.json').write_text(json.dumps(manifest))
                reports=json.loads((output/'REPORT_HASHES.json').read_text())
                reports['files']['INPUT_HASHES.json']=hashlib.sha256((output/'INPUT_HASHES.json').read_bytes()).hexdigest()
                (output/'REPORT_HASHES.json').write_text(json.dumps(reports))
                with self.assertRaises(ValueError):verify(output)

    def test_cached_request_reuses_bytes_and_rejects_tampering_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);self.fixture(output);raw=output/'raw'
            url='https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json'
            with patch('research.sec_fundamentals.urlopen',side_effect=AssertionError('network should not run')):
                self.assertEqual(download(raw,'AAPL.facts',url,None)['cik'],320193)
                with self.assertRaises(ValueError):download(raw,'AAPL.facts',url+'?changed',None)
                (raw/'AAPL.facts.json').write_text('{}')
                with self.assertRaises(ValueError):download(raw,'AAPL.facts',url,None)


if __name__=='__main__':unittest.main()
