"""Coverage and selection must never reward attractive returns."""
from datetime import datetime, timezone
from decimal import Decimal
import unittest

import test_stock_research as fixtures
from research.universe_transfer import select_roster, assess_member, request_pages


def roster(day='Oct 02, 2026', rows='A,Alpha,Equity,99\nB,Beta,Equity,1\nC,Cash,Cash,0\n'):
    return ('Fund\nFund Holdings as of,"'+day+'"\n\nTicker,Name,Asset Class,Weight (%)\n'+rows).encode()


class SelectionTests(unittest.TestCase):
    def test_response_date_must_match_even_when_http_status_is_success(self):
        with self.assertRaisesRegex(ValueError, 'date'):
            select_roster(roster(), 'Dec 31, 2015', (), 'seed', 2)
        with self.assertRaises(ValueError):
            select_roster(b'<!DOCTYPE html>current holdings</html>', 'Oct 02, 2026', (), 'seed', 2)

    def test_selection_ignores_weights_row_order_and_excludes_originals(self):
        first=select_roster(roster(), 'Oct 02, 2026', (), 'seed', 2)
        second=select_roster(roster(rows='B,Beta,Equity,99\nA,Alpha,Equity,1\n'), 'Oct 02, 2026', (), 'seed', 2)
        self.assertEqual(first,second)
        self.assertEqual({r['Ticker'] for r in first},{'A','B'})
        self.assertEqual([r['Ticker'] for r in select_roster(roster(), 'Oct 02, 2026', ('A',), 'seed', 2)],['B'])

    def test_duplicate_ticker_and_invalid_sample_count_rejected(self):
        with self.assertRaises(ValueError):
            select_roster(roster(rows='A,A,Equity,1\nA,A,Equity,2\n'),'Oct 02, 2026',(),'seed',1)
        for count in (0,True,-1):
            with self.assertRaises(ValueError): select_roster(roster(),'Oct 02, 2026',(),'seed',count)

    def test_offline_pagination_cannot_infer_missing_page_is_empty(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json,hashlib
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/'raw').mkdir()
            body=b'{"bars":{},"next_page_token":"second"}'
            (root/'raw/bars.0000.json').write_bytes(body)
            endpoint='https://data.alpaca.markets/v2/stocks/bars'
            (root/'raw/bars.0000.request.json').write_text(json.dumps(dict(endpoint=endpoint,parameters={},status=200,
                sha256=hashlib.sha256(body).hexdigest())))
            with self.assertRaisesRegex(ValueError,'Incomplete cached pagination'):
                list(request_pages(root,'bars',endpoint,{}, {},offline=True))

    def test_unapproved_endpoint_is_rejected_before_credentials_can_leave_machine(self):
        from pathlib import Path
        with self.assertRaisesRegex(ValueError,'Unapproved'):
            list(request_pages(Path('/tmp'),'probe','https://example.com',{}, {'secret':'never transmit'}))


class CoverageTests(unittest.TestCase):
    def fixture(self):
        spy,bars=fixtures.StockNormalizationTests().fixture()
        return spy,bars['bars']['A']

    def assess(self,rows,events):
        spy,_=self.fixture()
        return assess_member('A',rows,events,spy,datetime(2026,10,5,tzinfo=timezone.utc))

    def test_missing_name_is_retained_without_replacement(self):
        data,report=self.assess([],{})
        self.assertIsNone(data)
        self.assertEqual(report['symbol'],'A')
        self.assertFalse(report['eligible'])
        self.assertIn('missing_bar',report['reason'])

    def test_full_coverage_and_unknown_paydate_remain_unqualified(self):
        spy,rows=self.fixture()
        data,report=self.assess(rows,{'cash_dividends':[{'symbol':'A','ex_date':spy.sessions[1].isoformat(),'rate':'1'}]})
        self.assertTrue(report['eligible'])
        self.assertEqual(len(report['missing_payable_dates']),1)
        self.assertFalse(data.metadata.actions_complete)
        self.assertGreater(data.actions[0].pay_date,spy.sessions[-1])

    def test_unsupported_action_excludes_member_before_any_performance(self):
        _,rows=self.fixture()
        data,report=self.assess(rows,{'spin_offs':[{'symbol':'A','new_symbol':'OTHER'}]})
        self.assertIsNone(data)
        self.assertIn('Unsupported corporate actions',report['reason'])

    def test_bad_ohlc_and_duplicate_date_are_visible_exclusions(self):
        _,rows=self.fixture()
        for values in (rows+[rows[0]], [dict(rows[0],h='1')]+rows[1:]):
            data,report=self.assess(values,{})
            self.assertIsNone(data)
            self.assertFalse(report['eligible'])

    def test_unexplained_split_sized_gap_blocks_member(self):
        _,rows=self.fixture()
        changed=[dict(r,o=50,h=50,l=50,c=50) if i else r for i,r in enumerate(rows)]
        data,report=self.assess(changed,{})
        self.assertIsNone(data)
        self.assertIn('price_discontinuity',report['reason'])
