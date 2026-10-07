"""Hand-derived scoped accounting, capital, amendment and basis safeguards."""
from datetime import date
from decimal import Decimal as D
import hashlib
import unittest

from quant_core.data import Split
from quant_core.provenance import primitive
from research.sec_scoped import parse_scoped
from research.sec_capital import costco_profit, issued_less_treasury, preferred_deduction, check_amendment, share_basis, check_note
from test_sec_scoped import document, context, dimension, fact


CUTOFF=date(2021,6,30);END=date(2020,12,31);FILED=date(2021,2,1)


class AccountingTests(unittest.TestCase):
    def costco(self,extra=''):
        contexts=context()+context('product',dimension())+context('member',dimension('MembershipMember'))+context('balance',instant=True)
        return parse_scoped(document(fact('RevenueFromContractWithCustomerExcludingAssessedTax',105)+
            fact('RevenueFromContractWithCustomerExcludingAssessedTax',100,'product')+
            fact('RevenueFromContractWithCustomerExcludingAssessedTax',5,'member')+
            fact('CostOfGoodsAndServicesSold',60)+fact('Assets',100,'balance')+extra,contexts))

    def test_member_reconciliation_excludes_membership_from_merchandise_profit(self):
        r=costco_profit(self.costco(),1,END,FILED,CUTOFF)
        self.assertEqual(r['gross_profit'],D(40));self.assertEqual(r['score'],D('.4'))
        self.assertEqual(r['membership'],D(5));self.assertEqual(len(r['components']),5)

    def test_inconsistent_total_or_direct_gross_profit_blocks_recipe(self):
        # 100 +/- .5 plus 5 +/- .5 cannot reconcile to 108 +/- .5.
        for rows in ([{**r,'value':D(108)} if not r['dimensions'] and r['tag'].startswith('Revenue') else r for r in self.costco()],
                     self.costco(fact('GrossProfit',45))):
            with self.assertRaises(ValueError):costco_profit(rows,1,END,FILED,CUTOFF)

    def test_missing_member_foreign_issuer_quarter_and_extra_axes_do_not_supply_recipe(self):
        rows=self.costco()
        self.assertIsNone(costco_profit(rows,2,END,FILED,CUTOFF))
        self.assertIsNone(costco_profit(rows,1,END,CUTOFF,CUTOFF))
        self.assertIsNone(costco_profit([r for r in rows if r['dimensions']!=((('srt','ProductOrServiceAxis'),('us-gaap','MembershipMember')),)],1,END,FILED,CUTOFF))
        altered=[{**r,'dimensions':r['dimensions']+((('us-gaap','GeographicalAreaAxis'),('us-gaap','EuropeMember')),)} if r['dimensions'] else r for r in rows]
        self.assertIsNone(costco_profit(altered,1,END,FILED,CUTOFF))
        quarter=[{**r,'start':date(2020,10,1)} if r['start'] else r for r in rows]
        self.assertIsNone(costco_profit(quarter,1,END,FILED,CUTOFF))

    def test_raw_issued_less_treasury_preserves_rounding_interval(self):
        rows=parse_scoped(document(fact('CommonStockSharesIssued',100000000,'balance','shares','-6')+
            fact('TreasuryStockCommonShares',20000000,'balance','shares','-6')))
        result=issued_less_treasury(rows,1,END,['TreasuryStockCommonShares'])
        self.assertEqual(result['value'],D(80000000))
        self.assertEqual(result['lower'],D(79000000));self.assertEqual(result['upper'],D(81000000))
        self.assertFalse(result['numerically_exact'])

    def test_already_net_issued_is_not_reduced_twice(self):
        rows=parse_scoped(document(fact('CommonStockSharesIssued',1377,'balance','shares')+fact('TreasuryStockShares',490,'balance','shares')))
        result=issued_less_treasury(rows,1,END,['TreasuryStockShares'],already_net=True)
        self.assertEqual(result['value'],D(1377));self.assertEqual(len(result['components']),1)

    def test_share_class_date_units_negative_and_unknown_treasury_do_not_fall_back(self):
        rows=parse_scoped(document(fact('CommonStockSharesIssued',20,'balance','shares')+fact('TreasuryStockShares',25,'balance','shares')))
        with self.assertRaises(ValueError):issued_less_treasury(rows,1,END,['TreasuryStockShares'])
        self.assertIsNone(issued_less_treasury(rows,1,date(2020,12,27),['TreasuryStockShares']))
        self.assertIsNone(issued_less_treasury(rows,1,END,['TreasuryStockCommonShares']))
        altered=[{**r,'dimensions':((('us-gaap','StatementClassOfStockAxis'),('us-gaap','PreferredStockMember')),)} for r in rows]
        self.assertIsNone(issued_less_treasury(altered,1,END,['TreasuryStockShares']))
        self.assertIsNone(issued_less_treasury([{**r,'units':'USD'} for r in rows],1,END,['TreasuryStockShares']))

    def test_affirmative_zero_issued_preferred_is_distinct_from_missing_or_authorized(self):
        zero=parse_scoped(document(fact('PreferredStockSharesIssued',0,'balance','shares')+fact('PreferredStockValue',0,'balance')))
        self.assertEqual(preferred_deduction(zero,1,END)['value'],D(0))
        self.assertIsNone(preferred_deduction([],1,END))
        rounded=parse_scoped(document(fact('PreferredStockSharesIssued',0,'balance','shares','-6')))
        self.assertIsNone(preferred_deduction(rounded,1,END))
        self.assertIsNone(preferred_deduction(parse_scoped(document(fact('PreferredStockSharesAuthorized',0,'balance','shares'))),1,END))

    def test_preferred_zero_conflict_and_fair_value_do_not_become_deductions(self):
        rows=parse_scoped(document(fact('PreferredStockSharesIssued',0,'balance','shares')+fact('PreferredStockRedemptionValue',5,'balance')))
        with self.assertRaises(ValueError):preferred_deduction(rows,1,END)
        fair=parse_scoped(document(fact('PreferredStockValueOutstanding',64,'balance')+fact('PreferredStockValue',41,'balance')))
        self.assertIsNone(preferred_deduction(fair,1,END))
        with self.assertRaises(ValueError):preferred_deduction(fair,1,END,{'basis':'redemption','concept':['us-gaap','PreferredStockValueOutstanding'],'higher_priority_absent':[]})

    def test_whole_issuer_zero_cannot_hide_positive_preferred_class(self):
        contexts=context('balance',instant=True)+context('class',dimension('SeriesAPreferredStockMember','g:StatementClassOfStockAxis'),True)
        rows=parse_scoped(document(fact('PreferredStockSharesIssued',0,'balance','shares','INF')+
            fact('PreferredStockSharesOutstanding',10,'class','shares','INF'),contexts))
        with self.assertRaises(ValueError):preferred_deduction(rows,1,END)

    def test_zero_preferred_cannot_hide_positive_carrying_value(self):
        rows=parse_scoped(document(fact('PreferredStockSharesIssued',0,'balance','shares','INF')+
            fact('PreferredStockCarryingValue',10,'balance','usd','INF')))
        with self.assertRaises(ValueError):preferred_deduction(rows,1,END)

    def test_nonzero_hierarchy_requires_explicit_review_and_currency_scope(self):
        rows=parse_scoped(document(fact('PreferredStockRedemptionValue',5,'balance')+fact('PreferredStockLiquidationValue',6,'balance')))
        self.assertIsNone(preferred_deduction(rows,1,END))
        review={'basis':'redemption','concept':['us-gaap','PreferredStockRedemptionValue'],'higher_priority_absent':[]}
        self.assertEqual(preferred_deduction(rows,1,END,review)['value'],D(5))
        with self.assertRaises(ValueError):preferred_deduction(rows,1,END,{'basis':'liquidation','concept':['us-gaap','PreferredStockLiquidationValue'],'higher_priority_absent':[]})
        self.assertIsNone(preferred_deduction([{**r,'units':'shares'} for r in rows],1,END,review))

    def test_amendment_exemption_is_exact_pair_body_hash_metadata_and_note(self):
        primary=b'<html><p>Only purchase obligations changed. No other financial information changed.</p></html>'
        original=b'original instance'
        docs={'a':{'accession':'amend','cik':'1','report_date':'2020-12-31','form':'10-K/A','filed':'2021-03-01'},
              'o':{'accession':'orig','cik':'1','report_date':'2020-12-31','form':'10-K','filed':'2021-02-01'}}
        review={'amendment':'a','original':'o','amendment_sha256':hashlib.sha256(primary).hexdigest(),
            'original_sha256':hashlib.sha256(original).hexdigest(),'anchors':['Only purchase obligations changed','No other financial information changed']}
        self.assertTrue(check_amendment('a',docs,primary,original,review)['financial_components_unchanged'])
        for wrong in ({**review,'original':'unknown'},{**review,'amendment_sha256':'0'*64},
                      {**review,'anchors':['results restated']}):
            with self.assertRaises(ValueError):check_amendment('a',docs,primary,original,wrong)
        docs['o']['report_date']='2019-12-31'
        with self.assertRaises(ValueError):check_amendment('a',docs,primary,original,review)

    def test_reviewed_par_uses_outstanding_shares_and_higher_priority_absence(self):
        rows=parse_scoped(document(fact('PreferredStockParOrStatedValuePerShare',2,'balance','perShare')+
            fact('PreferredStockSharesOutstanding',10,'balance','shares')))
        review={'basis':'par','concept':['us-gaap','PreferredStockParOrStatedValuePerShare'],
            'higher_priority_absent':['redemption','liquidation'],'all_issuer_classes_reviewed':True}
        self.assertEqual(preferred_deduction(rows,1,END,review)['value'],D(20))
        with self.assertRaises(ValueError):preferred_deduction(rows,1,END,{**review,'higher_priority_absent':['redemption']})

    def test_liquidation_class_candidate_retains_uncertainty_and_is_not_an_approved_deduction(self):
        a=context('a',dimension('SeriesAPreferredStockMember','g:StatementClassOfStockAxis'),True)
        b=context('b',dimension('SeriesBPreferredStockMember','g:StatementClassOfStockAxis'),True)
        rows=parse_scoped(document(fact('EmployeeStockOwnershipPlanESOPSharesInESOP',20648000,'a','shares','-3')+
            fact('EmployeeStockOwnershipPlanESOPSharesInESOP',49107000,'b','shares','-3')+
            fact('PreferredStockLiquidationPreference','6.82','a','perShare','INF')+
            fact('PreferredStockLiquidationPreference','12.96','b','perShare','INF'),a+b))
        classes=[]
        for member in ('SeriesAPreferredStockMember','SeriesBPreferredStockMember'):
            scope=((('us-gaap','StatementClassOfStockAxis'),('us-gaap',member)),)
            classes.append({'shares_concept':['us-gaap','EmployeeStockOwnershipPlanESOPSharesInESOP'],'shares_scope':scope,
                'amount_concept':['us-gaap','PreferredStockLiquidationPreference'],'amount_scope':scope})
        result=preferred_deduction(rows,1,END,{'basis':'liquidation','classes':classes,'as_candidate_only':True})
        self.assertEqual(result['value'],D(777246080));self.assertEqual(result['lower'],D(777236190))
        self.assertFalse(result['valuation_reviewed'])
        altered=[{**r,'units':'USD'} if r['tag']=='PreferredStockLiquidationPreference' else r for r in rows]
        self.assertIsNone(preferred_deduction(altered,1,END,{'basis':'liquidation','classes':classes,'as_candidate_only':True}))

    def test_original_share_vintage_and_actual_split_schema_do_not_prove_complete_history(self):
        share={'end':END};doc={'report_date':'2020-12-31','filed':'2021-02-01'}
        split=primitive([Split('AAPL',date(2021,1,15),D(4))])
        result=share_basis(share,doc,'AAPL',split,class_reviewed=True,actions_complete=False)
        self.assertFalse(result['passed']);self.assertEqual(len(result['intervening_splits']),1)
        result=share_basis(share,doc,'AAPL',[],class_reviewed=True,actions_complete=False)
        self.assertTrue(result['current_period_original']);self.assertFalse(result['passed'])
        self.assertTrue(share_basis(share,doc,'AAPL',[],class_reviewed=True,actions_complete=True)['passed'])
        self.assertFalse(share_basis(share,{**doc,'report_date':'2021-03-31'},'AAPL',[],class_reviewed=True,actions_complete=True)['passed'])

    def test_reviewed_current_issuer_note_can_prove_zero_but_changed_body_date_cannot(self):
        body=b'<p>Preferred stock; issued none.</p>'
        doc={'cik':'1','report_date':'2020-12-31'}
        review={'cik':'1','report_date':'2020-12-31','sha256':hashlib.sha256(body).hexdigest(),
            'basis':'affirmative_note_zero','anchors':['Preferred stock; issued none.']}
        checked=check_note(body,doc,review)
        rows=parse_scoped(document(fact('PreferredStockSharesIssued',0,'balance','shares','-6')))
        self.assertEqual(preferred_deduction(rows,1,END,checked)['value'],D(0))
        for raw,metadata in ((body+b'changed',doc),(body,{**doc,'report_date':'2019-12-31'})):
            with self.assertRaises(ValueError):check_note(raw,metadata,review)


if __name__=='__main__':unittest.main()
