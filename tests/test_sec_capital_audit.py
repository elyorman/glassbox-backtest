"""Offline orchestration and immutable output verification with real arithmetic."""
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research.sec_capital_audit import derive, render, seal, verify_report, registration, checked_inputs
from research.sec_capital import issued_less_treasury
from research.sec_scoped import parse_scoped
from test_sec_scoped import document,fact,context,dimension


class CapitalAuditTests(unittest.TestCase):
    def fixture(self):
        formation='2021-06-30';key='annual'
        plan={'formations':[formation],'common_panel':['KO'],'minimum_eligible':10,'ciks':{'KO':'1'},
              'documents':{key:{'symbol':'KO','cik':'1','form':'10-K','filed':'2021-02-01','report_date':'2020-12-31','accession':'annual','uses':[[formation,'annual']]}}}
        baseline={'rows':[{'symbol':'KO','formation':formation,'in_common_panel':True,'profitability':None,
                    'parent_equity':None,'december_shares':None,'errors':[]}]}
        rows=parse_scoped(document(fact('CommonStockSharesIssued',100000000,'balance','shares','-6')+
            fact('TreasuryStockShares',20000000,'balance','shares','-6')+fact('StockholdersEquity',100,'balance')+
            fact('PreferredStockSharesIssued',0,'balance','shares','INF')))
        rules={'share_recipes':{'KO':{'from':'2016-12-31','through':'2025-12-31','treasury_tags':['TreasuryStockShares'],'already_net':False,'class_reviewed':True}},
               'preferred_notes':{},'preferred_candidates':{}}
        return plan,baseline,{key:rows},rules

    def test_recovery_preserves_rounding_but_never_qualifies_missing_actions_or_floor(self):
        result=derive(*self.fixture(),{},[],False,{})
        row=result['rows'][0]
        self.assertEqual(row['december_shares']['value'],'80000000')
        self.assertEqual(row['december_shares']['lower'],'79000000')
        self.assertEqual(row['common_book_equity_candidate'],'100')
        self.assertFalse(row['share_basis']['passed']);self.assertFalse(row['value_ready'])
        self.assertFalse(result['component_floor_passed']);self.assertTrue(result['fixed_panel_infeasible'])

    def test_unreviewed_parse_failure_and_sameday_filing_fail_closed(self):
        inputs=list(self.fixture());key='annual'
        result=derive(*inputs,{},[],False,{key:'unreviewed amendment'})
        self.assertIsNone(result['rows'][0]['december_shares'])
        inputs[0]['documents'][key]['filed']='2021-06-30'
        with self.assertRaises(ValueError):derive(*inputs,{},[],False,{})

    def test_direct_and_derived_conflict_blocks_instead_of_selecting_a_favorable_count(self):
        inputs=list(self.fixture());old=inputs[1]['rows'][0]
        old['december_shares']={'document':'annual','end':'2020-12-31','value':'60000000',
            'filed':'2021-02-01','components':[{'value':'60000000','decimals':'INF'}]}
        result=derive(*inputs,{},[],False,{})
        self.assertIsNone(result['rows'][0]['december_shares'])
        self.assertTrue(any('disagree' in e['error'] for e in result['rows'][0]['errors']))

    def test_same_day_capital_vintages_cannot_choose_zero_preferred(self):
        inputs=list(self.fixture());plan,baseline,instances,rules=inputs
        plan['documents']['other']=dict(plan['documents']['annual'],accession='other')
        instances['other']=tuple({**r,'value':Decimal(10)} if r['tag']=='PreferredStockSharesIssued' else r for r in instances['annual'])
        result=derive(*inputs,{},[],False,{})
        self.assertIsNone(result['rows'][0]['common_book_equity_candidate'])
        self.assertTrue(result['rows'][0]['errors'])

    def test_preferred_class_candidate_is_reported_even_when_parent_equity_is_missing(self):
        plan,baseline,instances,rules=self.fixture()
        plan['documents']['annual']['symbol']='PG';plan['ciks']={'PG':'1'};plan['common_panel']=['PG']
        baseline['rows'][0]['symbol']='PG';rules['share_recipes']={};rules['preferred_candidates']={'PG':{}}
        contexts='';facts=''
        for key,member,plan_member in (('a','SeriesAPreferredStockMember','PensionPlansDefinedBenefitMember'),
                                      ('b','SeriesBPreferredStockMember','OtherPostretirementBenefitPlansDefinedBenefitMember')):
            contexts+=context(key,dimension(member,'g:StatementClassOfStockAxis'),True)
            scope=dimension(member,'g:StatementClassOfStockAxis').replace('</i:segment>',
                '<d:explicitMember dimension="g:RetirementPlanTypeAxis">g:'+plan_member+'</d:explicitMember></i:segment>')
            contexts+=context(key+'amount',scope,True)
            facts+=fact('EmployeeStockOwnershipPlanESOPSharesInESOP',10,key,'shares','INF')+fact('PreferredStockLiquidationPreference',2,key+'amount','perShare','INF')
        instances['annual']=parse_scoped(document(facts,contexts))
        row=derive(plan,baseline,instances,rules,{},[],False,{})['rows'][0]
        self.assertEqual(row['preferred_candidate']['value'],'40')
        self.assertFalse(row['preferred_candidate']['valuation_reviewed'])
        self.assertIsNone(row['common_book_equity_candidate'])

    def test_changed_or_missing_parent_response_is_rejected_before_arithmetic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);parent=root/'parent';parent.mkdir();out=root/'output';out.mkdir()
            market=root/'snapshot.json';market.write_text('{}')
            plan={'common_panel':['KO'],'formations':['2021-06-30'],'minimum_eligible':10,
                'market_snapshot':str(market),'market_dataset_hash':'frozen'}
            (parent/'INPUT_PLAN.json').write_text(json.dumps(plan))
            (parent/'response.request.json').write_text('{"status":200}')
            (parent/'AUDIT_PLAN.json').write_text(json.dumps({'input_files':{'INPUT_PLAN.json':'unused','response.request.json':'unused'}}))
            for name in ('INPUT_HASHES.json','REPORT_HASHES.json','RECONCILIATION.json','REPORT.html'):(parent/name).write_text('{}')
            rules={'common_panel':['KO'],'formations':['2021-06-30'],'minimum_eligible':10}
            (out/'RULES.json').write_text(json.dumps(rules))
            (out/'AUDIT_PLAN.json').write_text(json.dumps(registration(parent,rules)))
            (parent/'response.request.json').write_text('{"status":403}')
            with self.assertRaises(ValueError):checked_inputs(out)
            (parent/'response.request.json').unlink()
            with self.assertRaises(FileNotFoundError):checked_inputs(out)

    def test_resealed_incorrect_arithmetic_is_not_semantically_valid(self):
        result=derive(*self.fixture(),{},[],False,{})
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);seal(output,result)
            self.assertTrue(verify_report(output,result))
            wrong=json.loads((output/'CAPITAL.json').read_text());wrong['rows'][0]['december_shares']['value']='99999999'
            (output/'CAPITAL.json').write_text(json.dumps(wrong))
            hashes=json.loads((output/'REPORT_HASHES.json').read_text())
            hashes['files']['CAPITAL.json']=hashlib.sha256((output/'CAPITAL.json').read_bytes()).hexdigest()
            (output/'REPORT_HASHES.json').write_text(json.dumps(hashes))
            with self.assertRaises(ValueError):verify_report(output,result)

    def test_manifest_cannot_omit_report_or_repeat_audit(self):
        result=derive(*self.fixture(),{},[],False,{})
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);seal(output,result)
            with self.assertRaises(FileExistsError):seal(output,result)
            manifest=json.loads((output/'REPORT_HASHES.json').read_text());del manifest['files']['REPORT.html']
            (output/'REPORT_HASHES.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):verify_report(output,result)


if __name__=='__main__':unittest.main()
