"""Predeclared selection overlap and bounded high-anchor campaign diagnostics."""
from datetime import date
from decimal import Decimal as D
import unittest

from quant_core.provenance import primitive
from quant_core.strategies import StrategyConfig
from research.high_campaign import high_entries, adapt_plan, rank_correlation, overlap_diagnostics, reuse_reference


def decision(day,asset,score,selected):
    return dict(session=day,security_id=asset,eligible=True,selected=selected,score=score)


def run(signals,returns=(D(0),D('.1'),D('-.1'))):
    return dict(signal_decisions=signals,equity=[dict(session=f'2024-01-{i+1:02d}',session_return=None if value is None else str(value))
        for i,value in enumerate(returns)])


class HighPlanTests(unittest.TestCase):
    def test_only_one_hypothesis_and_one_factor_neighbor(self):
        entries=high_entries(('B','A'))
        parent,neighbor=entries[:2]
        self.assertEqual(parent['role'],'parent');self.assertEqual(neighbor['role'],'neighbor')
        first,second=dict(parent['configuration']),dict(neighbor['configuration'])
        self.assertEqual(first['family'],'nearness_high');self.assertEqual(first['high_window'],252)
        self.assertEqual(second['high_window'],231)
        first.pop('name');second.pop('name');first.pop('high_window');second.pop('high_window')
        self.assertEqual(first,second)
        self.assertEqual(len(entries),5)

    def test_campaign_keeps_periods_objectives_costs_and_exact_trial_budget(self):
        base=dict(entries=[],stocks=['A','B'],source_hashes={'x':'old'},trial_budget=99,
            periods=[dict(name='continuous',scenarios=[['primary10','10',1],['stress25','25',1],['delay10','10',2]])]+
                [dict(name='fold_'+str(i),scenarios=[['primary10','10',1],['stress25','25',1]]) for i in range(3)],
            objectives={'return_seeking':'unchanged'},freeze_rule='unchanged',uncertainty={'seed':1729})
        plan=adapt_plan(base)
        self.assertEqual(plan['trial_budget'],45)
        for key in ('periods','objectives','freeze_rule','uncertainty'):self.assertEqual(plan[key],base[key])
        self.assertEqual(base['trial_budget'],99)

    def test_registration_bytes_are_pinned_before_runtime_or_inputs_are_examined(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json,hashlib
        from research.high_campaign import guard_registration
        with TemporaryDirectory() as temp:
            root=Path(temp);path=root/'REGISTRATION.json';body=b'{"source_hashes":{},"panels":[]}'
            path.write_bytes(body)
            (root/'REGISTRATION_HASH.json').write_text(json.dumps(dict(sha256=hashlib.sha256(body).hexdigest())))
            path.write_bytes(body+b' ')
            with self.assertRaisesRegex(ValueError,'Registration bytes'):guard_registration(root)


class RankTests(unittest.TestCase):
    def test_average_tie_ranks_have_hand_derived_correlation(self):
        self.assertEqual(rank_correlation((D(1),D(1),D(3)),(D(1),D(1),D(3))),D(1))
        self.assertEqual(rank_correlation((D(1),D(2),D(3)),(D(3),D(2),D(1))),D(-1))
        self.assertAlmostEqual(rank_correlation((D(1),D(1),D(3)),(D(1),D(2),D(3))),D('.8660254037844386467637231708'))

    def test_constant_or_small_samples_are_undefined(self):
        self.assertIsNone(rank_correlation((D(1),D(1)),(D(1),D(2))))
        self.assertIsNone(rank_correlation((D(1),),(D(2),)))
        with self.assertRaises(ValueError):rank_correlation((D(1),D(2)),(D(1),))


class OverlapTests(unittest.TestCase):
    def sample(self):
        left=[decision('2024-01-31','A','1',True),decision('2024-01-31','B','2',True),
              decision('2024-01-31','C','3',False)]
        right=[decision('2024-01-31','A','3',False),decision('2024-01-31','B','2',True),
               decision('2024-01-31','C','1',True)]
        return left,right

    def test_partial_set_overlap_and_reverse_score_ranks_are_exact(self):
        left,right=self.sample();result=overlap_diagnostics(run(left),run(right))
        self.assertEqual(D(result['mean_jaccard']),D(1)/3)
        self.assertEqual(D(result['mean_rank_spearman']),D(-1))
        self.assertEqual(D(result['daily_return_correlation']),D(1))
        self.assertTrue(result['overlap_warning'])
        self.assertEqual(result['exact_set_fraction'],'0')

    def test_empty_selections_are_not_claimed_as_perfect_overlap(self):
        left,right=self.sample()
        for row in left+right:row['selected']=False
        result=overlap_diagnostics(run(left),run(right))
        self.assertIsNone(result['mean_jaccard'])
        self.assertEqual(result['empty_union_sessions'],1)
        self.assertIsNone(result['exact_set_fraction'])

    def test_missing_signal_date_and_duplicate_decision_are_failures(self):
        left,right=self.sample()
        for changed in (right+[right[0]], [dict(row,session='2024-02-29') for row in right],right[:-1]):
            with self.assertRaises(ValueError):overlap_diagnostics(run(left),run(changed))

    def test_returns_are_not_aligned_by_silently_dropping_sessions(self):
        left,right=self.sample();changed=run(right);changed['equity'].pop()
        with self.assertRaises(ValueError):overlap_diagnostics(run(left),changed)

    def test_undefined_rank_and_return_correlation_are_visible(self):
        left,right=self.sample()
        for row in left+right:row['score']='1'
        result=overlap_diagnostics(run(left,(D(0),)*3),run(right,(D(0),)*3))
        self.assertIsNone(result['mean_rank_spearman'])
        self.assertIsNone(result['daily_return_correlation'])
        self.assertFalse(result['overlap_warning'])

    def test_missing_economic_interval_is_undefined_not_dropped_or_zero_filled(self):
        left,right=self.sample();result=overlap_diagnostics(run(left,(D(0),None,D('.1'))),run(right))
        self.assertIsNone(result['daily_return_correlation'])
        self.assertEqual(result['missing_return_intervals'],1)
        self.assertEqual(result['equity_sessions'],3)


class ReferenceReuseTests(unittest.TestCase):
    def fixture(self,root):
        from unittest.mock import patch
        from test_strategies import snapshot,config,DAYS
        from research.stock_campaign import simulate_trial
        from research.robustness_audit import source_hashes
        data=snapshot(paths={'SPY':(100,101,102,103,104,105)})
        entry=dict(configuration=primitive(config(family='buy_hold',universe=('SPY',))),role='reference',parent=None)
        p=dict(name='continuous',start=DAYS[2].isoformat(),end=DAYS[-1].isoformat());s=('primary10','10',1)
        plan=dict(source_hashes=source_hashes(),cash_path='engineering reference',dataset_hash=data.dataset_hash)
        old=root/'old';old.mkdir()
        with patch('research.stock_campaign.verified_cash_inputs',return_value=({},tuple((d,D(0)) for d in DAYS))):
            record,_=simulate_trial(data,plan,p,s,entry,old)
        self.assertEqual(record['status'],'completed')
        return data,plan,p,s,entry,record

    def test_reused_ledger_and_metrics_are_identical_with_explicit_origin(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from quant_core.reporting import verify_run
        from quant_core.provenance import content_hash
        with TemporaryDirectory() as temp:
            root=Path(temp);data,plan,p,s,entry,old=self.fixture(root);new=root/'new';new.mkdir()
            record,audit=reuse_reference(data,dict(plan,research_version='new'),p,s,entry,old,new)
            self.assertEqual(record['metrics'],old['metrics'])
            self.assertEqual(record['reused_from'],old['bundle'])
            self.assertEqual(record['result_hash'],content_hash(verify_run(Path(record['bundle']))))
            self.assertEqual(audit['status'],'passed')

    def test_changed_cost_or_dataset_is_rejected_before_copying(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            root=Path(temp);data,plan,p,s,entry,old=self.fixture(root)
            for index,(modified,scenario) in enumerate(((dict(plan,dataset_hash='different'),s),(plan,('primary10','25',1)))):
                new=root/f'bad-{index}';new.mkdir()
                with self.assertRaisesRegex(ValueError,'differs'):reuse_reference(data,modified,p,scenario,entry,old,new)
                self.assertEqual(list(new.iterdir()),[])

    def test_corrupted_source_bundle_cannot_be_reused(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            root=Path(temp);data,plan,p,s,entry,old=self.fixture(root)
            (Path(old['bundle'])/'fills.csv').write_text('corrupted')
            new=root/'new';new.mkdir()
            with self.assertRaises(ValueError):reuse_reference(data,plan,p,s,entry,old,new)

    def test_candidate_is_not_accepted_as_a_reference(self):
        from pathlib import Path
        with self.assertRaisesRegex(ValueError,'references'):
            reuse_reference(None,{},None,None,dict(role='parent'),dict(status='completed'),Path('/tmp'))
