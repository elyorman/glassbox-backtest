"""Saved action responses propose accounting events, never certify coverage."""

from contextlib import redirect_stdout, redirect_stderr
from datetime import date, datetime, timezone
from dataclasses import replace
from decimal import Decimal
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

DAY = date(2024, 1, 3)
RETRIEVED = datetime(2024, 1, 5, tzinfo=timezone.utc)
SPLITS = b'[{"date":"2024-01-03","split":"1.000000/3.000000"}]'
DIVIDENDS = b'[{"date":"2024-01-03","value":0.10,"unadjustedValue":0.30,"currency":"USD","paymentDate":"2024-01-08"}]'


def audit(**changes):
    from quant_core.data.eodhd_actions import audit_actions
    values = dict(ticker="TEST.US", security_id="A", splits_raw=SPLITS, dividends_raw=DIVIDENDS,
                  start=date(2024, 1, 2), end=date(2024, 1, 4), retrieved_at=RETRIEVED)
    values.update(changes)
    return audit_actions(**values)


class EodhdActionTests(unittest.TestCase):
    def reviewed(self):
        from quant_core.data.eodhd_actions import ReviewedSplit
        return (ReviewedSplit(DAY, "1.000000/3.000000", "a" * 64),)

    def test_reviewed_reverse_split_uses_exact_counts_and_original_cash(self):
        from quant_core.data import Dividend, Split
        result = audit(split_reviews=self.reviewed())
        self.assertFalse(result.has_unresolved)
        split = next(a for a in result.actions if isinstance(a, Split))
        dividend = next(a for a in result.actions if isinstance(a, Dividend))
        self.assertEqual(split.adjust_quantity(Decimal(300)), 100)
        self.assertEqual((split.new_shares, split.old_shares), (1, 3))
        self.assertEqual(dividend.amount, Decimal("0.30"))
        self.assertEqual(dividend.pay_date, date(2024, 1, 8))
        self.assertFalse(result.coverage_qualified)
        self.assertEqual(len(result.input_hashes), 3)

    def test_even_tidy_split_ratio_needs_independent_event_classification(self):
        result = audit()
        self.assertTrue(result.has_unresolved)
        self.assertEqual([i.code for i in result.issues], ["unclassified_split_event"])
        self.assertEqual(len(result.actions), 1)  # Cash remains a proposal; no split is invented.
        result = audit(splits_raw=SPLITS.replace(b"1.000000/3.000000", b"104.000000/100.000000"))
        self.assertTrue(result.has_unresolved)

    def test_empty_action_feeds_do_not_prove_complete_coverage(self):
        result = audit(splits_raw=b"[]", dividends_raw=b"[]")
        self.assertEqual(result.actions, ())
        self.assertFalse(result.coverage_qualified)
        self.assertIn("noncash", " ".join(result.limitations))

    def test_missing_original_amount_pay_date_and_wrong_currency_remain_unresolved(self):
        row = json.loads(DIVIDENDS)[0]
        for field, code in (("unadjustedValue", "missing_unadjusted_cash"),
                            ("paymentDate", "missing_payment_date"), ("currency", "unsupported_currency")):
            modified = dict(row)
            modified[field] = None
            result = audit(splits_raw=b"[]", dividends_raw=json.dumps([modified]).encode())
            self.assertTrue(result.has_unresolved)
            self.assertIn(code, [i.code for i in result.issues])
            self.assertEqual(result.actions, ())

    def test_adjusted_value_is_never_fallback_and_currency_is_not_converted(self):
        row = json.loads(DIVIDENDS)[0]
        del row["unadjustedValue"]
        result = audit(splits_raw=b"[]", dividends_raw=json.dumps([row]).encode())
        self.assertFalse(result.actions)
        row.update(unadjustedValue="0.30", currency="EUR")
        self.assertFalse(audit(splits_raw=b"[]", dividends_raw=json.dumps([row]).encode()).actions)

    def test_invalid_payment_date_and_cash_are_visible_without_invented_dates(self):
        for field, value, code in (("paymentDate", "2024-01-02", "invalid_payment_date"),
                                   ("paymentDate", "20240108", "invalid_payment_date"),
                                   ("unadjustedValue", "NaN", "invalid_cash_amount"),
                                   ("unadjustedValue", True, "invalid_cash_amount")):
            row = json.loads(DIVIDENDS)[0]
            row[field] = value
            result = audit(splits_raw=b"[]", dividends_raw=json.dumps([row]).encode())
            self.assertIn(code, [i.code for i in result.issues])
            self.assertFalse(result.actions)

    def test_stale_or_unused_split_classification_is_rejected(self):
        from quant_core.data.eodhd_actions import ReviewedSplit
        for review in (ReviewedSplit(DAY, "2/1", "a" * 64),
                       ReviewedSplit(date(2024, 1, 4), "1/3", "a" * 64)):
            with self.assertRaisesRegex(ValueError, "review"):
                audit(split_reviews=(review,))

    def test_ratio_format_errors_remain_unresolved_and_never_create_shares(self):
        for ratio in ("1/0", "-1/3", "1.5/2", "3", "NaN/1"):
            raw = json.dumps([{"date": DAY.isoformat(), "split": ratio}]).encode()
            result = audit(splits_raw=raw, dividends_raw=b"[]")
            self.assertTrue(result.has_unresolved)
            self.assertIn("invalid_split_ratio", [i.code for i in result.issues])
            self.assertFalse(result.actions)

    def test_duplicate_dates_fields_wrong_windows_and_future_events_fail_safely(self):
        cases = [dict(splits_raw=SPLITS[:-1]+b","+SPLITS[1:]),
                 dict(splits_raw=SPLITS.replace(b'"date":', b'"date":"2024-01-03","date":')),
                 dict(splits_raw=SPLITS.replace(b"2024-01-03", b"2024-01-09")),
                 dict(dividends_raw=DIVIDENDS[:-1]+b","+DIVIDENDS[1:]),
                 dict(retrieved_at=datetime(2024, 1, 2, tzinfo=timezone.utc))]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                audit(**changes)

    def test_provider_errors_redacted_and_not_cached(self):
        raw = b'{"error":"api_token=SECRET"}'
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as caught:
                audit(splits_raw=raw, cache_dir=Path(directory))
            self.assertNotIn("SECRET", str(caught.exception))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_raw_cache_and_provenance_are_immutable_and_ratio_bound(self):
        with TemporaryDirectory() as directory:
            result = audit(split_reviews=self.reviewed(), cache_dir=Path(directory))
            self.assertEqual(result, audit(split_reviews=self.reviewed(), cache_dir=Path(directory)))
            files = list(Path(directory).glob("*.json"))
            self.assertEqual(len(files), 2)
            files[0].write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "cache"):
                audit(split_reviews=self.reviewed(), cache_dir=Path(directory))

    def test_audited_actions_still_require_overall_review_to_supply_price_source(self):
        from quant_core.data import Security
        from test_eodhd import source
        result = audit(split_reviews=self.reviewed())
        with self.assertRaisesRegex(ValueError, "review"):
            source(actions=result.actions).load()
        # ID mapping in this engineering example is explicit.
        data = source(ticker_security_ids={"SYNTH.US":"A"},
                      securities=(Security("A","A","X"),),
                      metadata=replace(source().metadata, input_hashes=result.input_hashes),
                      actions=result.actions, actions_review_hash="b"*64).load()
        self.assertEqual(data.actions, result.actions)
        self.assertFalse(data.metadata.actions_complete)
        self.assertTrue(set(result.input_hashes) <= set(data.metadata.input_hashes))

    def test_cli_reviewed_export_preserves_exact_counts_in_csv(self):
        from quant_core.data.csv_source import load_actions
        from quant_core.data.eodhd_actions import main
        with TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'splits.json').write_bytes(SPLITS)
            (root/'dividends.json').write_bytes(DIVIDENDS)
            (root/'review.json').write_text(json.dumps([{'session':DAY.isoformat(),
                'ratio_text':'1.000000/3.000000','evidence_hash':'a'*64}]))
            args=['--ticker','TEST.US','--security-id','A','--splits',str(root/'splits.json'),
                  '--dividends',str(root/'dividends.json'),'--start','2024-01-02','--end','2024-01-04',
                  '--retrieved-at',RETRIEVED.isoformat(),'--output',str(root/'audit.json'),
                  '--split-review',str(root/'review.json'),'--actions-output',str(root/'actions.csv')]
            with redirect_stdout(StringIO()):
                self.assertEqual(main(args),0)
                self.assertEqual(main(args),0)  # Identical observations may be verified/reused.
            actions,_=load_actions(root/'actions.csv')
            self.assertEqual(len(actions),2)
            split=next(a for a in actions if hasattr(a,'new_shares'))
            self.assertEqual(split.adjust_quantity(Decimal(300)),100)

    def test_cli_writes_unresolved_report_but_refuses_partial_action_csv(self):
        from quant_core.data.eodhd_actions import main
        with TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'splits.json').write_bytes(SPLITS)
            (root/'dividends.json').write_bytes(DIVIDENDS)
            args=['--ticker','TEST.US','--security-id','A','--splits',str(root/'splits.json'),
                  '--dividends',str(root/'dividends.json'),'--start','2024-01-02','--end','2024-01-04',
                  '--retrieved-at',RETRIEVED.isoformat(),'--output',str(root/'audit.json'),
                  '--actions-output',str(root/'actions.csv')]
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main(args), 1)
            self.assertTrue((root/'audit.json').exists())
            self.assertFalse((root/'actions.csv').exists())
            payload=json.loads((root/'audit.json').read_text())
            self.assertFalse(payload['coverage_qualified'])

    def test_split_review_cannot_silently_ignore_non_split_classification(self):
        from quant_core.data.eodhd_actions import main
        with TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'splits.json').write_bytes(SPLITS)
            (root/'dividends.json').write_bytes(DIVIDENDS)
            (root/'review.json').write_text(json.dumps([{'session':DAY.isoformat(),
                'ratio_text':'1.000000/3.000000','evidence_hash':'a'*64,'classification':'spinoff'}]))
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                result=main(['--ticker','TEST.US','--security-id','A','--splits',str(root/'splits.json'),
                    '--dividends',str(root/'dividends.json'),'--start','2024-01-02','--end','2024-01-04',
                    '--retrieved-at',RETRIEVED.isoformat(),'--split-review',str(root/'review.json'),
                    '--output',str(root/'audit.json')])
            self.assertEqual(result,2)
            self.assertFalse((root/'audit.json').exists())


if __name__ == '__main__':
    unittest.main()
