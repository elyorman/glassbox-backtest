"""A prospective journal must reject retroactive or late signals."""
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core.data.storage import save_snapshot
from quant_core.provenance import primitive
from test_strategies import config, snapshot, DAYS
from research.forward_shadow import register_journal, record_signal, verify_journal, capture_records


def stamp(value): return datetime.fromisoformat(value.replace('Z','+00:00'))


class ForwardShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.journal=self.root/'journal'
        self.calendar=self.root/'calendar.json'
        rows=[dict(date=d.isoformat(),open='09:30',close='16:00') for d in DAYS]
        self.calendar.write_text(json.dumps(rows))
        self.cfg=config(family='trend')
        self.data=replace(snapshot(),metadata=replace(snapshot().metadata,retrieved_at=stamp('2024-01-31T21:10:00Z')))
        self.path=self.root/'snapshot.json';save_snapshot(self.data,self.path)

    def register(self, at='2024-01-30T22:00:00Z'):
        with patch('research.forward_shadow.now',return_value=stamp(at)):
            return register_journal(self.journal,self.cfg,self.calendar)

    def record(self,at='2024-01-31T21:15:00Z',day=DAYS[2],path=None):
        with patch('research.forward_shadow.now',return_value=stamp(at)):
            return record_signal(self.journal,path or self.path,day)

    def test_signal_matches_frozen_rule_with_no_positions_and_no_orders_sent(self):
        self.register(); row=self.record()
        selected=[s for s in row['decisions'] if s['selected']]
        self.assertEqual([s['security_id'] for s in selected],['A'])
        self.assertEqual(Decimal(selected[0]['target_fraction']),Decimal('.25'))
        self.assertEqual(row['eligible_execution_session'],'2024-02-01')
        self.assertFalse(row['broker_orders_sent'])
        self.assertEqual(verify_journal(self.journal)['signal_records'],1)

    def test_registration_after_signal_close_cannot_backdate_record(self):
        self.register('2024-01-31T21:05:00Z')
        with self.assertRaisesRegex(ValueError,'registration'): self.record()

    def test_before_close_and_after_next_open_are_both_rejected(self):
        self.register()
        for at in ('2024-01-31T20:59:00Z','2024-02-01T14:30:00Z'):
            with self.assertRaises(ValueError):self.record(at)
        self.assertEqual(verify_journal(self.journal)['signal_records'],0)

    def test_non_rebalance_date_cannot_be_substituted(self):
        self.register()
        with self.assertRaisesRegex(ValueError,'rebalance'):self.record(day=DAYS[3])

    def test_snapshot_retrieval_must_be_after_close_and_before_recording(self):
        self.register()
        for n,at in enumerate(('2024-01-31T20:59:00Z','2024-01-31T21:20:00Z')):
            data=replace(self.data,metadata=replace(self.data.metadata,retrieved_at=stamp(at)))
            path=self.root/f'invalid-{n}.json';save_snapshot(data,path)
            with self.assertRaisesRegex(ValueError,'retrieval'):self.record(path=path)

    def test_future_prices_and_actions_do_not_change_current_decisions(self):
        self.register(); row=self.record()
        from quant_core.data import Split
        future=replace(self.data,bars=tuple(replace(b,open=10000,high=10000,low=10000,close=10000)
            if b.session>DAYS[2] else b for b in self.data.bars),actions=(Split('A',DAYS[4],2),))
        path=self.root/'future.json';save_snapshot(future,path)
        second=self.root/'second'
        with patch('research.forward_shadow.now',return_value=stamp('2024-01-30T22:00:00Z')):
            register_journal(second,self.cfg,self.calendar)
        with patch('research.forward_shadow.now',return_value=stamp('2024-01-31T21:15:00Z')):
            changed=record_signal(second,path,DAYS[2])
        self.assertEqual(row['decisions'],changed['decisions'])

    def test_duplicate_signal_is_rejected_and_existing_bytes_unchanged(self):
        self.register();self.record();path=self.journal/'records/000001.json';before=path.read_bytes()
        with self.assertRaises(ValueError):self.record()
        self.assertEqual(path.read_bytes(),before)

    def test_missing_current_bar_is_rejected_without_empty_signal(self):
        self.register();path=self.root/'missing.json'
        save_snapshot(replace(self.data,bars=tuple(b for b in self.data.bars if not(b.security_id=='A' and b.session==DAYS[2]))),path)
        with self.assertRaisesRegex(ValueError,'coverage'):self.record(path=path)

    def test_calendar_and_record_and_snapshot_mutation_are_detected(self):
        for target in ('calendar.json','records/000001.json','snapshot'):
            with self.subTest(target=target),TemporaryDirectory() as temp:
                journal=Path(temp)/'journal'
                with patch('research.forward_shadow.now',return_value=stamp('2024-01-30T22:00:00Z')):
                    register_journal(journal,self.cfg,self.calendar)
                with patch('research.forward_shadow.now',return_value=stamp('2024-01-31T21:15:00Z')):
                    record_signal(journal,self.path,DAYS[2])
                path=self.path if target=='snapshot' else journal/target
                before=path.read_bytes();path.write_bytes(before+b' ')
                with self.assertRaises(ValueError):verify_journal(journal)
                path.write_bytes(before)

    def test_invalid_calendar_order_and_sessions_rejected(self):
        for rows in ([{'date':'2024-01-31','open':'16:00','close':'09:30'}],
                     [{'date':'2024-01-31','open':'09:30','close':'16:00'}]*2):
            self.calendar.write_text(json.dumps(rows))
            with self.assertRaises(ValueError):self.register()

    def test_dst_change_uses_distinct_close_and_next_open_utc_offsets(self):
        from research.forward_shadow import calendar_sessions
        sessions=calendar_sessions([dict(date='2026-10-30',open='09:30',close='16:00'),
            dict(date='2026-11-02',open='09:30',close='16:00')])
        self.assertEqual(sessions[0][2].astimezone(timezone.utc),stamp('2026-10-30T20:00:00Z'))
        self.assertEqual(sessions[1][1].astimezone(timezone.utc),stamp('2026-11-02T14:30:00Z'))

    def test_nontrend_recipe_cannot_enter_sma_journal(self):
        with self.assertRaises(ValueError):register_journal(self.journal,config(),self.calendar)

    def test_self_consistent_hash_cannot_hide_wrong_execution_date(self):
        from quant_core.provenance import content_hash,canonical_json
        self.register();self.record();path=self.journal/'records/000001.json'
        row=json.loads(path.read_text());row['eligible_execution_session']='2024-02-02'
        row['record_hash']=content_hash({k:v for k,v in row.items() if k!='record_hash'})
        path.write_text(canonical_json(row)+'\n')
        with self.assertRaisesRegex(ValueError,'execution'):verify_journal(self.journal)

    def test_capture_before_close_performs_no_network_or_directory_write(self):
        from research.forward_shadow import capture_signal
        self.register();output=self.root/'capture'
        with patch('research.forward_shadow.now',return_value=stamp('2024-01-31T20:59:00Z')):
            with self.assertRaisesRegex(ValueError,'after signal close'):
                capture_signal(self.journal,output,DAYS[2],self.root/'nonexistent.env')
        self.assertFalse(output.exists())

    def test_capture_preserves_raw_prices_and_defers_unknown_spy_payment(self):
        from quant_core.data import Dividend
        rows={}
        for asset in ('A','B','SPY'):
            rows[asset]=[dict(t=d.isoformat()+'T05:00:00Z',o=100,h=100,l=100,c=100,v=10000) for d in DAYS]
        data,readiness=capture_records(rows,{'cash_dividends':[dict(symbol='SPY',ex_date=DAYS[1].isoformat(),rate='1')]},
            DAYS,('A','B'),stamp('2024-01-31T21:10:00Z'),(('raw.json','a'*64),))
        self.assertEqual(data.bars[0].close,Decimal(100))
        self.assertGreater(next(a for a in data.actions if isinstance(a,Dividend)).pay_date,DAYS[-1])
        self.assertEqual(readiness['spy_unknown_payable_dates'],1)
        self.assertFalse(data.metadata.actions_complete)

    def test_capture_rejects_unsupported_spy_event(self):
        with self.assertRaisesRegex(ValueError,'SPY'):
            capture_records({}, {'spin_offs':[dict(symbol='SPY')]},DAYS,('A','B'),stamp('2024-01-31T21:10:00Z'),())
