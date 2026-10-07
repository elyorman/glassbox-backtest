"""Synthetic ledger checks; review/original-campaign boundaries are explicitly mocked.

No passed provider qualification or real market dataset is manufactured here.
"""

from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core.data import Dividend, Split
from quant_core.data.storage import save_snapshot
from quant_core.provenance import content_hash, primitive
from quant_core.reporting import verify_run
from quant_core.strategies import benchmark_recipes
from research.market_backtest import saved_model
from research.robustness_audit import source_hashes, verified_cash_inputs
from research import stock_campaign as campaign
from research.stock_retest import EVIDENCE, report_retest, verify_retest
from test_strategies import DAYS, config, snapshot


class StockRetestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original_path, self.output = self.root / 'original', self.root / 'retest'
        self.original_path.mkdir(); self.output.mkdir()
        self.cash_path = self.root / 'cash_rates.csv'
        self.cash_path.write_text('observation_date,annual_percent\n' + ''.join(
            f'{day.isoformat()},0\n' for day in (DAYS[0] - timedelta(days=1),) + DAYS))
        cashmeta = {'sha256': hashlib.sha256(self.cash_path.read_bytes()).hexdigest(), 'raw_files': []}
        self.write(self.root / 'SOURCE.json', cashmeta)
        data = snapshot(paths={'A': (100,110,120,60,62,63), 'B': (100,99,98,98,99,100),
                               'SPY': (100,101,102,103,104,105)},
                        actions=(Split('A', DAYS[3], 2), Dividend('A', DAYS[4], 1, DAYS[5])))
        self.data = replace(data, metadata=replace(data.metadata, source='synthetic_independent_fixture'))
        self.original_data = replace(data, metadata=replace(data.metadata, source='synthetic_primary_fixture'))
        self.snapshot_path = self.root / 'independent.snapshot.json'
        save_snapshot(self.data, self.snapshot_path)
        parent = config(name='fixture_parent', momentum_lookback=2, volume_lookback=1)
        self.frozen = [dict(configuration=primitive(parent), role='parent', parent=parent.name,
                            objective='return_seeking')]
        references = [dict(configuration=primitive(replace(recipe, volume_lookback=1,
                        max_volume_participation='1')), role='reference', parent=None, objective='reference')
                      for recipe in benchmark_recipes(('A','B'), 'SPY')
                      if recipe.name != 'broad_market_buy_hold']
        self.original = primitive(dict(dataset_hash=self.original_data.dataset_hash,
            source_provider=self.original_data.metadata.source, stocks=('A','B'), benchmark='SPY',
            calendar=DAYS, start=DAYS[2], end=DAYS[-1], entries=self.frozen + references,
            periods=[dict(name='continuous', start=DAYS[2], end=DAYS[-1], scenarios=campaign.SCENARIOS)],
            trial_budget=12, source_hashes=source_hashes(), cash_path=str(self.cash_path.resolve()),
            cash_source=verified_cash_inputs(self.cash_path)[0],
            cross_provider_tolerances={'total_return':'.05', 'daily_return':'.005'}))
        self.write(self.original_path / 'FROZEN_CANDIDATES.json', {'entries':self.frozen})
        original_rows, original_payloads = [], {}
        for scenario in campaign.SCENARIOS:
            for entry in self.original['entries']:
                row, _ = campaign.simulate_trial(self.original_data, self.original,
                    self.original['periods'][0], scenario, entry, self.original_path)
                original_rows.append(row)
                if row['status'] != 'failed': original_payloads[row['key']] = verify_run(Path(row['bundle']))
        self.original_results = {'trials':original_rows}
        self.original_payloads = original_payloads
        self.qualification_path = self.root / 'review_boundary.txt'
        self.qualification_path.write_text('Review ingestion is mocked in this test; this is not qualification.\n')
        self.plan = primitive(dict(self.original, dataset_hash=self.data.dataset_hash,
            snapshot=str(self.snapshot_path.resolve()), original_campaign=str(self.original_path.resolve()),
            original_dataset_hash=self.original['dataset_hash'], original_plan_hash=content_hash(self.original),
            qualification=None, qualification_path=str(self.qualification_path.resolve()),
            qualification_hash=hashlib.sha256(self.qualification_path.read_bytes()).hexdigest(),
            entries=self.frozen + references, periods=self.original['periods'][:1], trial_budget=12))
        self.write(self.output / 'EXPERIMENT_PLAN.json', self.plan)
        rows, audits = [], []
        for scenario in campaign.SCENARIOS:
            for entry in self.plan['entries']:
                row, audit = campaign.simulate_trial(self.data, self.plan, self.plan['periods'][0],
                    scenario, entry, self.output, 'require_complete')
                self.assertNotEqual(row['status'], 'failed', row.get('error'))
                rows.append(row); audits.append(audit)
                self.write(self.output / (row['key'] + '.completed.json'), row)
        previous = {(row['scenario'],row['recipe']):row for row in original_rows}
        comparisons = []
        for row in rows:
            entry = next(entry for entry in self.plan['entries'] if entry['configuration']['name']==row['recipe'])
            before = previous[row['scenario'],row['recipe']]
            refs = [next(item for item in rows if item['scenario']==row['scenario'] and item['recipe']==name)
                    for name in (campaign.REFERENCE,campaign.EQUAL)]
            objective = campaign.economic_pass(row,refs,entry['objective']) if entry['role']=='parent' else None
            comparisons.append(campaign.compare_retest(row,before,
                saved_model(verify_run(Path(row['bundle']))) if row['status']=='completed' else None,
                saved_model(original_payloads[before['key']]) if before['status']=='completed' else None,
                objective,self.plan['cross_provider_tolerances']))
        self.results = dict(plan_hash=content_hash(self.plan),trials=rows,comparisons=comparisons,
                            strategy_selected=False,fresh_final_test=False)
        self.write(self.output / 'RESULTS.json', self.results)
        self.write(self.output / 'INDEPENDENT_LEDGER_AUDIT.json', {'trials':audits})
        self.seal()
        self.mock_original = patch('research.stock_campaign.verify_campaign', return_value=(
            self.original,self.original_results,self.original_payloads)).start()
        self.mock_review = patch('quant_core.validation.contracts.load_document', return_value=None).start()
        self.mock_gate = patch('research.stock_campaign.validate_retest_inputs').start()
        self.addCleanup(patch.stopall)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value,sort_keys=True)+'\n')

    def seal(self):
        names = list(EVIDENCE) + [row['key']+suffix for row in self.results['trials']
                                 for suffix in ('.started.json','.completed.json')]
        self.write(self.output / 'EVIDENCE_HASHES.json', {'files':{
            name:hashlib.sha256((self.output/name).read_bytes()).hexdigest() for name in names}})

    def test_verified_split_dividend_ledgers_report_exclusively(self):
        plan, results, payloads = verify_retest(self.output)
        self.assertEqual(plan,self.plan); self.assertEqual(results,self.results)
        self.assertEqual(len(payloads),12)
        self.mock_gate.assert_called_once_with(self.original,self.data,None)
        summary = report_retest(self.output)
        self.assertEqual(summary['verified_bundles'],12)
        manifest = json.loads((self.output/'RETEST_REPORT_HASHES.json').read_text())
        for name,digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((self.output/name).read_bytes()).hexdigest(),digest)
        self.assertIn('does not establish', (self.output/'RETEST_REPORT.html').read_text())
        with self.assertRaises(FileExistsError): report_retest(self.output)

    def test_retest_entrypoint_produces_verifiable_synthetic_evidence(self):
        executed=self.root/'executed_retest'
        with patch('research.stock_campaign.load_document',return_value=None):
            campaign.retest(self.original_path,self.snapshot_path,self.qualification_path,executed)
        plan,results,payloads=verify_retest(executed)
        self.assertEqual(len(payloads),12)
        self.assertEqual(plan['entries'],self.frozen+[e for e in self.original['entries'] if e['role']=='reference'])
        self.assertFalse(results['fresh_final_test'])
        self.assertFalse(results['strategy_selected'])

    def test_changed_metrics_resealed_evidence_still_fails_ledger_reconciliation(self):
        row=self.results['trials'][0]; row['metrics']['total_return']='999'
        self.write(self.output/(row['key']+'.completed.json'),row)
        self.write(self.output/'RESULTS.json',self.results); self.seal()
        with self.assertRaisesRegex(ValueError,'derived metrics'): verify_retest(self.output)

    def test_resealed_comparison_cannot_claim_provider_agreement(self):
        self.results['comparisons'][0]['total_return_difference']='999'
        self.write(self.output/'RESULTS.json',self.results); self.seal()
        with self.assertRaisesRegex(ValueError,'comparisons'): verify_retest(self.output)

    def test_resealed_audit_cannot_claim_unchecked_inventory(self):
        path=self.output/'INDEPENDENT_LEDGER_AUDIT.json'; value=json.loads(path.read_text())
        value['trials'][0]['fills_checked']+=1; self.write(path,value); self.seal()
        with self.assertRaisesRegex(ValueError,'ledger audit'): verify_retest(self.output)

    def test_qualification_bytes_and_frozen_procedure_are_pinned(self):
        self.qualification_path.write_text('Changed review boundary')
        with self.assertRaisesRegex(ValueError,'qualification bytes'): verify_retest(self.output)
        self.qualification_path.write_text('Review ingestion is mocked in this test; this is not qualification.\n')
        self.plan['entries'][0]['configuration']['top_k']=2
        self.results['plan_hash']=content_hash(self.plan)
        self.write(self.output/'EXPERIMENT_PLAN.json',self.plan)
        self.write(self.output/'RESULTS.json',self.results); self.seal()
        with self.assertRaisesRegex(ValueError,'frozen campaign'): verify_retest(self.output)


if __name__=='__main__': unittest.main()
