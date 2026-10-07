"""Stock research: hand-derived signals, explicit gaps and frozen retest gates."""
from dataclasses import replace
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal as D
import unittest

from quant_core.features import realized_volatility
from quant_core.data import Bar, DataMetadata, Security, Snapshot, Split, Dividend
from quant_core.strategies import build_strategy
from test_strategies import config, snapshot, run, DAYS
from research.stock_data import normalize_records
from research.stock_campaign import economic_pass, make_plan, validate_trials, validate_retest_inputs, compare_retest


class StockSignalTests(unittest.TestCase):
    def test_volatility_uses_exact_last_returns_and_population_variance(self):
        self.assertEqual(realized_volatility((D(50), D(100), D(110), D(99)), 2), D('.1'))
        self.assertEqual(realized_volatility((D(10), D(11), D('12.1')), 2), D(0))
        self.assertIsNone(realized_volatility((D(10), D(11)), 2))
        for window in (0, -1, True):
            with self.assertRaises(ValueError): realized_volatility((D(10), D(11)), window)
        with self.assertRaises(ValueError): realized_volatility((D(0), D(11)), 1)

    def test_low_vol_selects_lowest_risk_not_highest_return(self):
        data = snapshot(paths={'A': (100,110,99,99,99,99), 'B': (100,100,100,100,100,100)})
        result = run(config(family='low_vol', volatility_window=2), data)
        decisions = [s for s in result.signal_decisions if s.session == DAYS[2]]
        self.assertEqual([s.security_id for s in decisions if s.selected], ['B'])
        self.assertEqual(next(s.score for s in decisions if s.security_id == 'A'), D('.1'))
        self.assertEqual(next(s.score for s in decisions if s.security_id == 'B'), D(0))
        self.assertEqual(result.fills[0].security_id, 'B')
        self.assertEqual(result.fills[0].execution_date, DAYS[3])

    def test_low_vol_ties_are_id_order_and_future_cannot_change_orders(self):
        cfg = config(family='low_vol', volatility_window=2)
        data = snapshot(paths={'A': (100,100,100,100,100,100), 'B': (100,100,100,100,100,100)})
        baseline = run(cfg, data)
        changed = replace(data, bars=tuple(replace(b, close=D(10000), high=D(10000)) if b.session == DAYS[-1] else b for b in data.bars),
                          actions=(Split('A', DAYS[-1], 2),))
        modified = run(cfg, changed)
        self.assertEqual(baseline.fills[0].security_id, 'A')
        self.assertEqual(baseline.fills, modified.fills)
        self.assertEqual(baseline.signal_decisions[:2], modified.signal_decisions[:2])

    def test_incomplete_actions_only_run_under_explicit_diagnostic_policy(self):
        data = snapshot(); data = replace(data, metadata=replace(data.metadata, actions_complete=False))
        with self.assertRaises(ValueError): run(data=data)
        result = run(data=data, actions_policy='allow_incomplete_diagnostic')
        self.assertTrue(result.fills)
        self.assertFalse(result.manifest.data.actions_complete)
        self.assertTrue(any('unqualified' in s for s in result.manifest.assumptions))


class StockNormalizationTests(unittest.TestCase):
    def fixture(self):
        spy = snapshot(paths={'SPY': (100,100,100,100,100,100)})
        bars = {'bars': {'A': [{'t': d.isoformat()+'T05:00:00Z', 'o':100,'h':100,'l':100,'c':100,'v':10000} for d in DAYS]}}
        return spy, bars

    def normalize(self, actions, defer=False, bars=None):
        spy, default = self.fixture()
        return normalize_records(bars or default, {'corporate_actions':actions}, DAYS, spy, ('A',),
                                 (('raw.json', 'a'*64),), datetime(2026,10,3,tzinfo=timezone.utc), defer)

    def test_missing_payment_date_is_not_cash_at_exdate(self):
        actions={'cash_dividends':[{'symbol':'A','ex_date':DAYS[1].isoformat(),'rate':'1','payable_date':None}]}
        with self.assertRaises(ValueError): self.normalize(actions)
        data, report = self.normalize(actions, True)
        dividend = next(a for a in data.actions if isinstance(a, Dividend))
        self.assertEqual(dividend.pay_date, DAYS[-1]+timedelta(days=366))
        self.assertEqual(report['missing_payable_dates'][0]['ex_date'], DAYS[1].isoformat())
        self.assertFalse(data.metadata.actions_complete)
        self.assertFalse(report['qualified'])

    def test_split_ratio_and_known_paydate_preserve_raw_prices(self):
        actions={'forward_splits':[{'symbol':'A','ex_date':DAYS[1].isoformat(),'new_rate':'4','old_rate':'1'}],
                 'cash_dividends':[{'symbol':'A','ex_date':DAYS[2].isoformat(),'rate':'.5','payable_date':DAYS[4].isoformat()}]}
        data, report = self.normalize(actions)
        self.assertEqual(next(a.ratio for a in data.actions if isinstance(a,Split)),D(4))
        self.assertEqual(next(a.pay_date for a in data.actions if isinstance(a,Dividend)),DAYS[4])
        self.assertEqual(next(b.open for b in data.bars if b.security_id=='A'),D(100))
        self.assertEqual(report['missing_payable_dates'],[])

    def test_unsupported_action_and_missing_bar_are_hard_failures(self):
        with self.assertRaises(ValueError): self.normalize({'spin_offs':[{'symbol':'A'}]})
        _, bars = self.fixture(); bars['bars']['A'].pop(2)
        with self.assertRaises(ValueError): self.normalize({}, bars=bars)

    def test_duplicate_event_does_not_double_credit_dividend(self):
        row={'symbol':'A','ex_date':DAYS[1].isoformat(),'rate':'1','payable_date':DAYS[4].isoformat()}
        with self.assertRaises(ValueError): self.normalize({'cash_dividends':[row,row]})

    def test_acquirer_only_merger_is_not_income_to_existing_holders(self):
        data,report=self.normalize({'cash_mergers':[{'acquirer_symbol':'A','acquiree_symbol':'OTHER','rate':100}]})
        self.assertFalse(data.actions)
        self.assertEqual(report['non_position_transforming_actions'][0]['reason'],'acquirer_only')
        with self.assertRaises(ValueError):
            self.normalize({'cash_mergers':[{'acquirer_symbol':'OTHER','acquiree_symbol':'A','rate':100}]})

    def test_same_symbol_name_change_remains_unqualified_identity_evidence(self):
        _,report=self.normalize({'name_changes':[{'old_symbol':'A','new_symbol':'A','old_cusip':'old','new_cusip':'new'}]})
        self.assertEqual(report['non_position_transforming_actions'][0]['reason'],'same_symbol_identity_metadata_only')
        self.assertFalse(report['qualified'])

    def test_merger_outside_eligible_panel_is_retained_without_position_effect(self):
        data,report=self.normalize({'cash_mergers':[{'acquirer_symbol':'EXCLUDED','acquiree_symbol':'OTHER','rate':100}]})
        self.assertFalse(data.actions)
        self.assertEqual(report['non_position_transforming_actions'][0]['reason'],'outside_panel')

    def test_in_sample_entitlement_processed_after_sample_is_not_lost(self):
        _,report=self.normalize({'cash_dividends':[{'symbol':'A','ex_date':DAYS[-1].isoformat(),
                    'process_date':'2024-03-01','rate':'1','payable_date':'2024-03-01'}]})
        self.assertEqual(report['action_counts']['Dividend'],1)


class StockCampaignTests(unittest.TestCase):
    def test_recovery_cannot_change_rules_or_any_financial_source(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        from research.stock_campaign import reuse_registration
        old={'objective':'frozen','source_hashes':{'research/stock_campaign.py':'a','quant_core/engine.py':'b'}}
        with TemporaryDirectory() as temp:
            path=Path(temp);(path/'EXPERIMENT_PLAN.json').write_text(json.dumps(old))
            with self.assertRaisesRegex(ValueError,'data/recipes/criteria'):
                reuse_registration(dict(old,objective='relaxed'),path)
            with self.assertRaisesRegex(ValueError,'postprocessing source'):
                reuse_registration(dict(old,source_hashes={'research/stock_campaign.py':'c','quant_core/engine.py':'changed'}),path)

    def test_diagnostics_use_verified_primitive_candidate_and_reference_ledgers(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from quant_core.provenance import primitive
        from research.stock_campaign import simulate_trial, campaign_diagnostics, REFERENCE
        from research.robustness_audit import source_hashes
        data=snapshot(paths={'A':(100,110,120,125,128,130),'B':(100,95,90,90,85,80),'SPY':(100,101,102,103,104,105)})
        plan={'source_hashes':source_hashes(),'cash_path':'engineering rate boundary'}
        period={'name':'continuous','start':DAYS[2].isoformat(),'end':DAYS[-1].isoformat()}
        parent={'configuration':primitive(config()),'role':'parent','parent':config().name}
        reference={'configuration':primitive(config(family='buy_hold',name=REFERENCE,universe=('SPY',))), 'role':'reference','parent':None}
        rates=tuple((d,D(0)) for d in DAYS)
        with TemporaryDirectory() as temp, patch('research.stock_campaign.verified_cash_inputs',return_value=({},rates)):
            rows=[simulate_trial(data,plan,period,('primary10','10',1),e,Path(temp))[0] for e in (parent,reference)]
            self.assertTrue(all(r['status']=='completed' for r in rows))
            diagnostics=campaign_diagnostics(data,rows,rates)
            self.assertEqual(set(diagnostics),{config().name})
            self.assertIn('attribution',diagnostics[config().name])
            self.assertIn('recovery',diagnostics[config().name])

    def test_plan_freezes_four_families_and_exact_99_trial_budget_before_prices(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        days=tuple(date(2016,1,4)+timedelta(days=i) for i in range((date(2026,10,2)-date(2016,1,4)).days+1)
                   if (date(2016,1,4)+timedelta(days=i)).weekday()<5)
        # Calendar-only engineering input proves registration cannot inspect outcomes.
        data=Snapshot(days,(),snapshot().metadata,tuple(Security(a,a,'SYNTHETIC') for a in ('A','B','C','D','E','SPY')))
        with TemporaryDirectory() as temp, patch('research.stock_campaign.verified_cash_inputs',return_value=({},())):
            path=Path(temp)/'readiness.json'; path.write_text('{}')
            plan=make_plan(data,Path(temp)/'snapshot.json',path,Path(temp)/'cash.csv')
        self.assertEqual(plan['trial_budget'],99)
        self.assertEqual({e['configuration']['family'] for e in plan['entries'] if e['role']=='parent'},
                         {'momentum','trend','reversal','low_vol'})
        self.assertEqual(len(plan['entries']),11)
        self.assertEqual(len(plan['periods']),4)
        self.assertFalse(plan['fresh_final_test'])
        self.assertFalse(plan['production_nomination'])

    def test_trial_saves_audited_bundle_and_preserves_failed_registration(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from quant_core.provenance import primitive
        from research.stock_campaign import simulate_trial
        from research.robustness_audit import source_hashes
        from quant_core.reporting import verify_run
        entry={'configuration':primitive(config()),'role':'parent','parent':config().name}
        period={'name':'continuous','start':DAYS[2].isoformat(),'end':DAYS[-1].isoformat()}
        plan={'source_hashes':source_hashes(),'cash_path':'unused engineering rate fixture'}
        rates=tuple((d,D(0)) for d in DAYS)
        with TemporaryDirectory() as temp, patch('research.stock_campaign.verified_cash_inputs',return_value=({},rates)):
            output=Path(temp)
            row,audit=simulate_trial(snapshot(),plan,period,('primary10','10',1),entry,output)
            self.assertEqual(row['status'],'completed')
            self.assertEqual(audit['status'],'passed')
            payload=verify_run(Path(row['bundle']))
            self.assertEqual(payload['fills'][0]['execution_date'],DAYS[3].isoformat())
            self.assertEqual(D(payload['fills'][0]['price']),D(125)*D('1.001'))
            failed,audit=simulate_trial(snapshot(),dict(plan,source_hashes={}),period,('stress25','25',1),entry,output)
            self.assertEqual(failed['status'],'failed')
            self.assertIsNone(audit)
            self.assertTrue((output/(failed['key']+'.started.json')).exists())
            self.assertIn('Source changed',failed['error'])

    def test_independent_comparison_checks_daily_path_and_objective_not_just_endpoint(self):
        from types import SimpleNamespace
        before = SimpleNamespace(equity=tuple(SimpleNamespace(session=d, session_return=D(0)) for d in DAYS))
        after = SimpleNamespace(equity=tuple(SimpleNamespace(session=d, session_return=D('.006') if i == 1 else D(0)) for i,d in enumerate(DAYS)))
        row = dict(self.row(), recipe='A', scenario='primary10')
        row['metrics']['total_return']='.1'
        result=compare_retest(row,row,after,before,True,{'total_return':'.05','daily_return':'.005'})
        self.assertFalse(result['cross_provider_tolerances_passed'])
        self.assertEqual(D(result['maximum_daily_return_difference']),D('.006'))
        self.assertTrue(result['objective_passed'])
        self.assertFalse(result['production_nomination'])
        with self.assertRaises(ValueError):
            compare_retest(row,row,SimpleNamespace(equity=after.equity[1:]),before,True,{'total_return':'.05','daily_return':'.005'})

    def test_fully_reviewed_synthetic_independent_panel_is_accepted(self):
        from quant_core.validation.contracts import Qualification, Capability, CAPABILITIES
        data=snapshot(paths={'A':(100,)*6,'B':(100,)*6,'SPY':(100,)*6})
        data=replace(data,metadata=replace(data.metadata,source='independent engineering fixture'))
        plan={'dataset_hash':'b'*64,'source_provider':'other','calendar':[d.isoformat() for d in data.sessions],'stocks':['A','B'],'benchmark':'SPY'}
        q=Qualification(data.dataset_hash,'independent_retest_fixed_sample','synthetic test',date(2026,10,3),
            tuple(Capability(c,'passed','synthetic fixture only') for c in CAPABILITIES),('not empirical qualification',),'b'*64,'synthetic source isolation')
        validate_retest_inputs(plan,data,q)
        with self.assertRaises(ValueError): validate_retest_inputs(dict(plan,stocks=['A']),data,q)

    def row(self,cagr='.12',dd='.20',sr='1'):
        return {'status':'completed','metrics':{'cagr_calendar':cagr,'max_drawdown':dd},'sharpe_historical_reference':sr}

    def test_return_objective_requires_both_benchmarks_and_defined_ratios(self):
        refs=[self.row(sr='.8'),self.row(sr='1.1')]
        self.assertFalse(economic_pass(self.row(),refs,'return_seeking'))
        self.assertTrue(economic_pass(self.row(sr='1.2'),refs,'return_seeking'))
        self.assertFalse(economic_pass(self.row(sr=None),refs,'return_seeking'))
        self.assertFalse(economic_pass(self.row(cagr='-.01',sr='2'),refs,'return_seeking'))

    def test_defensive_objective_does_not_reward_negative_benchmark_threshold(self):
        refs=[self.row(cagr='.12',dd='.4'),self.row(cagr='.1',dd='.3')]
        self.assertTrue(economic_pass(self.row(cagr='.06',dd='.2'),refs,'defensive'))
        self.assertFalse(economic_pass(self.row(cagr='.05',dd='.2'),refs,'defensive'))
        self.assertFalse(economic_pass(self.row(cagr='.06',dd='.25'),refs,'defensive'))
        self.assertIsNone(economic_pass(self.row(),[self.row(cagr='-.01'),refs[1]],'defensive'))

    def test_incomplete_or_duplicate_trials_cannot_be_a_completed_campaign(self):
        plan={'entries':[{'configuration':{'name':'A'},'role':'parent','parent':'A'}],
              'periods':[{'name':'continuous','scenarios':[['primary10','10',1],['stress25','25',1]]}], 'trial_budget':2}
        a={'key':'continuous_primary10_A','period':'continuous','scenario':'primary10','recipe':'A','role':'parent','parent':'A','status':'completed'}
        b=dict(a,key='continuous_stress25_A',scenario='stress25')
        validate_trials(plan,[a,b])
        for rows in ([a],[a,a], [a,dict(b,role='reference')]):
            with self.assertRaises(ValueError): validate_trials(plan,rows)

    def test_same_source_or_unqualified_data_never_authorizes_independent_retest(self):
        from quant_core.validation.contracts import Qualification, Capability, CAPABILITIES
        data=snapshot(); data=replace(data,metadata=replace(data.metadata,source='same'))
        plan={'dataset_hash':'b'*64,'source_provider':'same','calendar':[x.isoformat() for x in data.sessions],
              'stocks':['A','B'],'benchmark':'SPY'}
        caps=tuple(Capability(x,'passed','fabricated engineering test evidence') for x in CAPABILITIES)
        q=Qualification(data.dataset_hash,'independent_retest_fixed_sample','synthetic test',date(2026,10,3),caps,
                        ('synthetic test only',),'b'*64,'engineering evidence only')
        with self.assertRaises(ValueError): validate_retest_inputs(plan,data,q)
        data=replace(data,metadata=replace(data.metadata,source='different',actions_complete=False))
        with self.assertRaises(ValueError): validate_retest_inputs(plan,data,replace(q,dataset_hash=data.dataset_hash))


if __name__ == '__main__': unittest.main()
