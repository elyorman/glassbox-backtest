"""Hand-calculated robustness diagnostics; no market-performance expectations."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research import robustness_metrics as metrics

D = Decimal


def ledger_fixture():
    # Two shares at 100; split 2:1 and $1/share dividend; partial then full exit.
    states = []
    for day, qty, value, cash, receivable, equity in (
        ('2024-01-02', 2, 200, 800, 0, 1000),
        ('2024-01-03', 4, 196, 800, 4, 1000),
        ('2024-01-04', 2, 120, 919, 4, 1043),
        ('2024-01-05', 0, 0, 1040, 4, 1044)):
        states.append(dict(session=day, cash=str(cash), receivables=str(receivable),
                           market_value=str(value), equity=str(equity),
                           session_return='0', positions=[dict(security_id='A',quantity=str(qty),
                           market_value=str(value))] if qty else []))
    fills = [dict(execution_date=day,security_id='A',side=side,quantity=str(qty),
                  notional=str(value),fees=str(fee),position_quantity_after=str(after))
             for day,side,qty,value,fee,after in (
                 ('2024-01-02','buy',2,200,0,2),
                 ('2024-01-04','sell',2,120,1,2),
                 ('2024-01-05','sell',2,122,1,0))]
    return dict(manifest=dict(config=dict(initial_cash='1000',universe=['A'])),
                equity=states, fills=fills, corporate_actions=[dict(session='2024-01-03',
                security_id='A',kind='dividend_entitlement',amount='4')])


class AttributionTests(unittest.TestCase):
    def test_daily_asset_pnl_reconciles_split_dividend_partial_exit_and_fees(self):
        result = metrics.attribution(ledger_fixture())
        self.assertEqual([r['pnl_usd'] for r in result['daily']], [D(0),D(0),D(43),D(1)])
        self.assertEqual(result['assets'][0]['pnl_usd'], D(44))
        episode = result['episodes'][0]
        self.assertEqual((episode['pnl_usd'],episode['calendar_days'],episode['status']),
                         (D(44),3,'closed'))

    def test_open_episode_includes_terminal_market_value_without_fake_exit(self):
        run = ledger_fixture();run['equity'].pop();run['fills'].pop()
        result = metrics.attribution(run)
        self.assertEqual(result['episodes'][0]['pnl_usd'],D(43))
        self.assertEqual(result['episodes'][0]['status'],'open')
        self.assertIsNone(result['episodes'][0]['exit_date'])

    def test_unexplained_equity_or_nonzero_outside_income_is_rejected(self):
        run=ledger_fixture();run['equity'][2]['equity']='1044'
        with self.assertRaises(ArithmeticError):metrics.attribution(run)
        run=ledger_fixture();run['corporate_actions'][0]['security_id']='OUTSIDE'
        with self.assertRaises(ArithmeticError):metrics.attribution(run)


class TimeSeriesTests(unittest.TestCase):
    def test_recovery_duration_counts_sessions_and_calendar_days_and_open_drawdown(self):
        result=metrics.recoveries(('2024-01-05','2024-01-08','2024-01-09','2024-01-10','2024-01-11'),
                                 (D(100),D(90),D(80),D(100),D(95)),D(100))
        self.assertEqual(result[0]['max_drawdown'],D('.2'))
        self.assertEqual((result[0]['sessions_to_recovery'],result[0]['calendar_days']), (3,5))
        self.assertEqual(result[1]['status'],'open')
        self.assertIsNone(result[1]['sessions_to_recovery'])

    def test_rolling_compounds_only_window_and_excludes_appended_future(self):
        days=('2024-01-02','2024-01-03','2024-01-04','2024-01-05')
        candidate=(D(0),D('.1'),D('-.1'),D('.5'));reference=(D(0),)*4
        result=metrics.rolling(days,candidate,reference,(D(0),)*4,window=2)
        self.assertEqual(result[1]['total_return'],D('-.01'))
        self.assertEqual(result[1]['relative_growth'],D('-.01'))
        short=metrics.rolling(days[:3],candidate[:3],reference[:3],(D(0),)*3,window=2)
        self.assertEqual(result[:2],short)

    def test_benchmark_regression_reports_undefined_when_benchmark_has_no_variance(self):
        result=metrics.regression((D('.1'),D('-.1')), (D(0),D(0)),(D(0),D(0)))
        self.assertIsNone(result['beta'])
        self.assertIsNone(result['alpha_arithmetic_252'])

    def test_regression_uses_excess_returns_and_arithmetic_not_compounded_alpha(self):
        # x = .01 + 2*y; with constant .01 risk-free, excess intercept is .02.
        result=metrics.regression((D('.01'),D('.03'),D('.05')),
                                  (D(0),D('.01'),D('.02')),(D('.01'),)*3)
        self.assertEqual(result['beta'],D(2))
        self.assertEqual(result['alpha_arithmetic_252'],D('5.04'))

    def test_concentration_adjustment_is_paired_and_does_not_remove_losses(self):
        result=metrics.concentration((D('.1'),D('-.1'),D('.02')), (D(0),)*3,
                                     ('2024-01-02','2024-01-03','2024-01-04'),count=1)
        self.assertEqual(result['mean_excess_after_zeroing'],D('-.08')/3)
        self.assertEqual(result['zeroed_dates'],['2024-01-02'])


class CashTests(unittest.TestCase):
    def test_rate_lag_weekend_interest_and_no_same_day_future_use(self):
        rates=((date(2024,1,4),D('.0365')),(date(2024,1,5),D('.99')))
        aligned=metrics.cash_intervals(('2024-01-05','2024-01-08'),rates)
        self.assertEqual(aligned[1]['return'],D('.0003'))
        self.assertEqual(aligned[1]['observation_date'],date(2024,1,4))
        future=rates+((date(2024,1,8),D('.8')),)
        self.assertEqual(aligned,metrics.cash_intervals(('2024-01-05','2024-01-08'),future))

    def test_missing_stale_duplicate_and_nonfinite_rates_fail(self):
        days=('2024-01-05','2024-01-08')
        for rates in ((),((date(2023,12,1),D('.01')),),
                      ((date(2024,1,4),D('.01')),(date(2024,1,4),D('.02'))),
                      ((date(2024,1,4),D('NaN')),)):
            with self.subTest(rates=rates),self.assertRaises(ValueError):
                metrics.cash_intervals(days,rates)

    def test_cash_overlay_accrues_previous_cash_and_interest_but_not_receivables(self):
        run=ledger_fixture();run['equity']=run['equity'][:3]
        result=metrics.cash_overlay(run,(D(0),D('.01'),D('.01')))
        self.assertEqual(result['interest_usd'],D('16.08'))
        self.assertEqual(result['final_equity_usd'],D('1059.08'))
        self.assertEqual(run['equity'][-1]['equity'],'1043')

    def test_rate_csv_skips_missing_and_rejects_duplicate_or_tampered_units(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'rates.csv'
            path.write_text('observation_date,annual_percent\n2024-01-04,3.65\n2024-01-05,.\n')
            self.assertEqual(metrics.load_rates(path),((date(2024,1,4),D('.0365')),))
            path.write_text('observation_date,annual_percent\n2024-01-04,3.65\n2024-01-04,4\n')
            with self.assertRaises(ValueError):metrics.load_rates(path)


class ExperimentTests(unittest.TestCase):
    def test_registered_plan_does_not_mutate_when_original_results_are_enriched(self):
        import json
        from quant_core.provenance import content_hash
        from research.robustness_audit import register_plan
        with TemporaryDirectory() as tmp:
            original=[{'recipe':'fixed','metrics':{'cagr_calendar':'.1'}}]
            frozen,expected=register_plan(Path(tmp),{'original_portfolios':original})
            original[0]['cash_overlay']={'interest':'10'}
            self.assertEqual(content_hash(frozen),expected)
            self.assertEqual(json.loads((Path(tmp)/'EXPERIMENT_PLAN.json').read_text())['original_portfolios'],
                             [{'recipe':'fixed','metrics':{'cagr_calendar':'.1'}}])

    def test_stop_ledger_reconstruction_checks_intraday_and_adverse_gap_prices(self):
        from research.robustness_audit import audit_ledger
        from quant_core.provenance import primitive
        from test_risk import data, bar, run, raw, DAYS
        for opening,low,kind,price in ((85,85,'stop_gap',D(85)),(100,85,'stop_intraday',D(90))):
            bars=[bar(d) if i!=2 else bar(d,price=str(opening),low=low)
                  for i,d in enumerate(DAYS)]
            snapshot=data(bars)
            result=run((raw(quantity='2'),),snapshot=snapshot)
            payload=primitive(result)
            self.assertEqual(result.fills[1].execution_kind,kind)
            self.assertEqual(result.fills[1].price,price)
            self.assertEqual(audit_ledger(snapshot,payload)['fills_checked'],2)
            payload['fills'][1]['trigger_price']='80'
            with self.assertRaises(ArithmeticError):audit_ledger(snapshot,payload)

    def test_audit_rejects_a_different_touched_stop_even_with_reconciled_equity(self):
        from research.robustness_audit import audit_ledger
        from quant_core.provenance import primitive
        from test_risk import data,bar,run,raw,DAYS
        snapshot=data([bar(d,low=85) if i==2 else bar(d) for i,d in enumerate(DAYS)])
        payload=primitive(run((raw(quantity='2'),),snapshot=snapshot))
        exit_=payload['fills'][1]
        exit_.update(trigger_price='95',price='95',raw_execution_price='95',notional='190')
        for state in payload['equity'][2:]:
            state['cash']=str(D(state['cash'])+10)
            state['equity']=str(D(state['equity'])+10)
        with self.assertRaises(ArithmeticError):audit_ledger(snapshot,payload)

    def test_audit_rejects_unprocessed_fill_and_missing_session(self):
        from copy import deepcopy
        from research.robustness_audit import audit_ledger
        from quant_core.provenance import primitive
        from test_risk import data,run,raw
        snapshot=data();payload=primitive(run((raw(quantity='2'),),snapshot=snapshot))
        extra=deepcopy(payload['fills'][0]);extra['execution_date']='2030-01-01'
        payload['fills'].append(extra)
        with self.assertRaises(ArithmeticError):audit_ledger(snapshot,payload)
        payload=primitive(run((raw(quantity='2'),),snapshot=snapshot));payload['equity'].pop()
        with self.assertRaises(ArithmeticError):audit_ledger(snapshot,payload)

    def test_audit_reconstructs_split_adjusted_stop(self):
        from research.robustness_audit import audit_ledger
        from quant_core.provenance import primitive
        from quant_core.data import Split
        from test_risk import data,bar,run,raw,DAYS
        snapshot=data([bar(d,price='100' if i<2 else '50' if i==2 else '44') for i,d in enumerate(DAYS)],
                      actions=(Split('A',DAYS[2],2),))
        payload=primitive(run((raw(quantity='2'),),snapshot=snapshot))
        self.assertEqual(payload['fills'][1]['trigger_price'],'45')
        self.assertEqual(audit_ledger(snapshot,payload)['fills_checked'],2)
        payload['fills'][1]['trigger_price']='46'
        with self.assertRaises(ArithmeticError):audit_ledger(snapshot,payload)

    def test_audit_detects_omitted_triggered_exit_in_self_consistent_ledger(self):
        from copy import deepcopy
        from research.robustness_audit import audit_ledger
        from quant_core.provenance import primitive
        from test_risk import data,bar,run,raw,DAYS
        snapshot=data([bar(d,low=85) if i==2 else bar(d) for i,d in enumerate(DAYS)])
        payload=primitive(run((raw(quantity='2'),),snapshot=snapshot))
        exit_=payload['fills'].pop()
        payload['orders']=[o for o in payload['orders'] if o['order_id']!=exit_['order_id']]
        positions=deepcopy(payload['equity'][1]['positions'])
        for state in payload['equity'][2:]:
            state.update(cash='9800',equity='10000',market_value='200',positions=deepcopy(positions))
        with self.assertRaises(ArithmeticError):audit_ledger(snapshot,payload)

    def test_derived_evidence_tampering_is_detected_before_report(self):
        import json
        from research.robustness_report import seal_evidence,verify_evidence
        with TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'RESULTS.json';path.write_text(json.dumps({'cagr':'.1'}))
            seal_evidence(root,['RESULTS.json'])
            verify_evidence(root)
            path.write_text(json.dumps({'cagr':'.9'}))
            with self.assertRaises(ValueError):verify_evidence(root)

    def test_exposure_matching_uses_prior_exposure_not_current_or_future(self):
        from research.robustness_metrics import exposure_match
        run=ledger_fixture()
        values=exposure_match(run,(D(0),D('.1'),D('.2'),D('.3')),(D(0),)*4)
        self.assertEqual(values[1],D('.02'))
        self.assertEqual(values[2],D('.0392'))

    def test_cash_overlay_exposure_uses_overlay_equity_denominator(self):
        run=ledger_fixture()
        result=metrics.exposure_match(run,(D(0),D('.1'),D('.2'),D('.3')),(D(0),)*4,
                                      equities=(D(1010),D(1020),D(1063),D(1074)))
        self.assertEqual(result[1],D(200)/1010*D('.1'))
        self.assertEqual(result[2],D(196)/1020*D('.2'))

    def test_registered_trial_panel_rejects_duplicate_replacing_missing_recipe(self):
        from research.robustness_report import verify_panel
        plan=dict(entries=[dict(parent='fixed',role='parent',configuration={'name':'fixed'}),
                           dict(parent='fixed',role='neighbor',configuration={'name':'neighbor'})],
                  scenarios=[('primary10','10'),('stress25','25')],trial_budget=4)
        rows=[dict(parent='fixed',role=role,recipe=name,scenario=s,status='completed')
              for s in ('primary10','stress25') for name,role in (('fixed','parent'),('neighbor','neighbor'))]
        verify_panel(plan,rows)
        rows[-1]=dict(rows[0])
        with self.assertRaises(ValueError):verify_panel(plan,rows)

    def test_fully_invested_market_leg_accounts_for_split_dividend_and_ignores_future(self):
        from research.robustness_metrics import total_return_leg
        from quant_core.data import Split,Dividend
        from test_strategies import snapshot,DAYS
        events=(Split('A',DAYS[1],2),Dividend('A',DAYS[1],1,DAYS[2]))
        data=snapshot({'A':(100,49,49,10000)},sessions=DAYS[:4],actions=events)
        self.assertEqual(total_return_leg(data,DAYS[:3],asset='A'),(D(0),D(0),D(0)))

    def test_neighbor_stability_is_separate_from_parent_objective(self):
        from research.robustness_audit import decisions
        rows=[]
        for scenario in ('primary10','stress25'):
            rows.append(dict(parent='trend_sma_200',role='parent',scenario=scenario,status='completed',
                             recipe='trend_sma_200',metrics={'cagr_calendar':'.08','max_drawdown':'.1'},
                             spy_metrics={'cagr_calendar':'.12','max_drawdown':'.3'}))
            for name in ('trend180','trend220'):
                rows.append(dict(parent='trend_sma_200',role='neighbor',scenario=scenario,status='completed',
                                 recipe=name,metrics={'cagr_calendar':'-.01'}))
        result=decisions(rows)['trend_sma_200']
        self.assertTrue(result['objective_passed'])
        self.assertFalse(result['parameter_stable'])
        self.assertEqual(result['decision'],'retain_for_research')

    def test_failed_or_missing_neighbor_prevents_a_complete_stability_decision(self):
        from research.robustness_audit import decisions
        rows=[]
        for scenario in ('primary10','stress25'):
            rows.append(dict(parent='trend_sma_200',role='parent',scenario=scenario,status='completed',
                             recipe='trend_sma_200',metrics={'cagr_calendar':'.08','max_drawdown':'.1'},
                             spy_metrics={'cagr_calendar':'.12','max_drawdown':'.3'}))
            for name in ('trend180','trend220'):
                rows.append(dict(parent='trend_sma_200',role='neighbor',scenario=scenario,status='completed',
                                 recipe=name,metrics={'cagr_calendar':'.05'}))
        self.assertEqual(decisions(rows)['trend_sma_200']['decision'],'retain_for_research')
        rows[1]['status']='failed'
        self.assertEqual(decisions(rows)['trend_sma_200']['decision'],'incomplete')
        rows.pop(1)
        self.assertEqual(decisions(rows)['trend_sma_200']['decision'],'incomplete')

    def test_different_neighbor_panels_across_costs_are_incomplete(self):
        from research.robustness_audit import decisions
        rows=[]
        for scenario in ('primary10','stress25'):
            rows.append(dict(parent='trend_sma_200',role='parent',scenario=scenario,status='completed',
                             recipe='trend_sma_200',metrics={'cagr_calendar':'.08','max_drawdown':'.1'},
                             spy_metrics={'cagr_calendar':'.12','max_drawdown':'.3'}))
            for name in ('trend180','trend220'):
                rows.append(dict(parent='trend_sma_200',role='neighbor',scenario=scenario,status='completed',
                                 recipe=name + ('changed' if scenario=='stress25' else ''),metrics={'cagr_calendar':'.05'}))
        self.assertEqual(decisions(rows)['trend_sma_200']['decision'],'incomplete')

    def test_raw_or_normalized_cash_tampering_is_rejected(self):
        import hashlib,json
        from research.robustness_audit import verified_cash_inputs
        with TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw.csv';raw.write_text('source bytes')
            normalized=root/'cash_rates.csv'
            normalized.write_text('observation_date,annual_percent\n2024-01-04,3.65\n')
            source=dict(sha256=hashlib.sha256(normalized.read_bytes()).hexdigest(),
                        raw_files=[dict(file='raw.csv',sha256=hashlib.sha256(raw.read_bytes()).hexdigest())])
            (root/'SOURCE.json').write_text(json.dumps(source))
            self.assertEqual(verified_cash_inputs(normalized)[1][0][1],D('.0365'))
            raw.write_text('changed bytes')
            with self.assertRaises(ValueError):verified_cash_inputs(normalized)
            raw.write_text('source bytes');normalized.write_text('changed normalized bytes')
            with self.assertRaises(ValueError):verified_cash_inputs(normalized)

    def test_report_rejects_diagnostic_plan_tampering_before_export(self):
        import json
        from quant_core.provenance import content_hash
        from research.robustness_report import verify_inputs
        with TemporaryDirectory() as tmp:
            root=Path(tmp);plan={'trial_budget':30};expected=content_hash(plan)
            for name,payload in (('EXPERIMENT_PLAN.json',plan),
                                 ('RESULTS.json',{'plan_hash':expected}),
                                 ('DIAGNOSTICS.json',{'plan_hash':'changed'}),
                                 ('TRIAL_RESULTS.json',{'plan_hash':expected})):
                (root/name).write_text(json.dumps(payload))
            with self.assertRaises(ValueError):verify_inputs(root)
            self.assertFalse((root/'REPORT.html').exists())
