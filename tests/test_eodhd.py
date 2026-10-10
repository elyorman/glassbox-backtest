"""Offline provider normalization; fixtures are synthetic, never live downloads."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from quant_core.data import DataMetadata, Dividend, Security, Split
from quant_core.data.eodhd import EodhdClient, EodhdJsonSource
from quant_core.provenance import canonical_json, content_hash


RAW = (b'[{"date":"2024-01-02","open":100.000000000000000000001,'
       b'"high":102,"low":99,"close":101,"adjusted_close":50.5,"volume":1000}]')
SPLIT_RAW = (b'[{"date":"2024-01-02","open":100,"high":100,"low":100,"close":100,"adjusted_close":50,"volume":1000},'
             b'{"date":"2024-01-03","open":50.5,"high":50.5,"low":50.5,"close":50.5,"adjusted_close":50.5,"volume":2000}]')
REVIEW = "a" * 64

DAYS3 = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))


def response(*rows):
    """EODHD-style JSON with literal numbers; `adjusted` is inserted verbatim (may be any JSON value)."""
    body = ",".join(f'{{"date":"{day}","open":{close},"high":{close},"low":{close},"close":{close},'
                    f'"adjusted_close":{adjusted},"volume":1000}}' for day, close, adjusted in rows)
    return ("[" + body + "]").encode()


def source(**changes):
    values = dict(responses={"SYNTH.US": RAW}, ticker_security_ids={"SYNTH.US": "ID-1"},
                  sessions=(date(2024, 1, 2), date(2024, 1, 3)),
                  securities=(Security("ID-1", "SYNTH", "XNAS"),),
                  metadata=DataMetadata("eodhd", datetime(2024, 1, 4, tzinfo=timezone.utc),
                                        "supplied_static_panel", False, "supplied_calendar"))
    values.update(changes)
    return EodhdJsonSource(**values)


class EodhdTests(unittest.TestCase):
    def test_adjusted_close_confirms_declared_split(self):
        data = source(responses={"SYNTH.US": SPLIT_RAW}, actions_review_hash=REVIEW,
                      actions=(Split("ID-1", date(2024, 1, 3), new_shares=2, old_shares=1),),
                      metadata=replace(source().metadata, actions_complete=True)).load()
        self.assertFalse(any("adjusted_close" in s for s in data.metadata.limitations))

    def test_declared_complete_actions_missing_a_split_are_refused(self):
        with self.assertRaisesRegex(ValueError, r"disagree with EODHD adjusted_close: SYNTH\.US .*2024-01-03"):
            source(responses={"SYNTH.US": SPLIT_RAW}, actions_review_hash=REVIEW,
                   metadata=replace(source().metadata, actions_complete=True)).load()

    def test_incomplete_actions_record_unexplained_provider_adjustments(self):
        data = source(responses={"SYNTH.US": SPLIT_RAW}).load()
        self.assertTrue(any("not explained by supplied actions" in s for s in data.metadata.limitations))

    def test_missing_adjusted_close_skips_crosscheck_visibly(self):
        raw = SPLIT_RAW.replace(b',"adjusted_close":50,"volume":1000', b',"volume":1000')
        data = source(responses={"SYNTH.US": raw}).load()
        self.assertTrue(any("fewer than two usable sessions for SYNTH.US" in s
                            for s in data.metadata.limitations))

    def test_rows_without_adjusted_close_are_excluded_visibly(self):
        third = b',{"date":"2024-01-04","open":50,"high":50,"low":50,"close":50,"adjusted_close":50,"volume":2000}]'
        raw = (SPLIT_RAW[:-1] + third).replace(b'"adjusted_close":50.5,', b'')
        data = source(responses={"SYNTH.US": raw},
                      sessions=(date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))).load()
        self.assertTrue(any("excluded from the provider adjustment cross-check" in s for s in data.metadata.limitations))
        self.assertTrue(any("not explained by supplied actions" in s for s in data.metadata.limitations))

    def test_complete_actions_must_include_dividends_the_provider_applied(self):
        raw = response(("2024-01-02", 100, 98), ("2024-01-03", 99, 99))
        dividend = Dividend("ID-1", date(2024, 1, 3), "2", date(2024, 1, 3))
        complete = replace(source().metadata, actions_complete=True)
        source(responses={"SYNTH.US": raw}, actions=(dividend,), actions_review_hash=REVIEW, metadata=complete).load()
        with self.assertRaisesRegex(ValueError, "2024-01-02 to 2024-01-03"):
            source(responses={"SYNTH.US": raw}, actions_review_hash=REVIEW, metadata=complete).load()

    def test_each_ticker_is_checked_against_its_own_actions(self):
        responses = {"SYNTH.US": SPLIT_RAW, "OTHER.US": response(("2024-01-02", 100, 100), ("2024-01-03", 101, 101))}
        ids = {"SYNTH.US": "ID-1", "OTHER.US": "ID-2"}
        securities = (Security("ID-1", "SYNTH", "XNAS"), Security("ID-2", "OTHER", "XNAS"))
        complete = replace(source().metadata, actions_complete=True)

        def load(split_owner):
            split = Split(split_owner, date(2024, 1, 3), new_shares=2, old_shares=1)
            return source(responses=responses, ticker_security_ids=ids, securities=securities,
                          actions=(split,), actions_review_hash=REVIEW, metadata=complete).load()

        load("ID-1")
        with self.assertRaisesRegex(ValueError, r"OTHER\.US"):
            load("ID-2")

    def test_unusable_adjusted_values_are_excluded_not_trusted(self):
        for bad in ("0", "-5", '"50"', "true", "1E+999999", "1E-999999"):
            with self.subTest(bad=bad):
                raw = response(("2024-01-02", 100, 50), ("2024-01-03", 50.5, bad), ("2024-01-04", 50, 50))
                notes = source(responses={"SYNTH.US": raw}, sessions=DAYS3).load().metadata.limitations
                self.assertTrue(any("excluded from the provider adjustment cross-check" in s for s in notes))
                self.assertTrue(any("not explained by supplied actions" in s for s in notes))
                self.assertTrue(all(len(s) < 400 for s in notes))

    def test_too_coarse_provider_rounding_is_disclosed_not_fatal(self):
        raw = response(("2024-01-02", 100, 0.0001), ("2024-01-03", 50, 0.0001))
        split = Split("ID-1", date(2024, 1, 3), new_shares=2, old_shares=1)
        data = source(responses={"SYNTH.US": raw}, actions=(split,), actions_review_hash=REVIEW,
                      metadata=replace(source().metadata, actions_complete=True)).load()
        self.assertTrue(any("too coarsely rounded to verify 1 session pair" in s for s in data.metadata.limitations))

    def test_duplicate_sessions_report_the_snapshot_contract_error(self):
        raw = response(("2024-01-02", 100, 50), ("2024-01-02", 100, 50))
        with self.assertRaisesRegex(ValueError, "violates supplied calendar"):
            source(responses={"SYNTH.US": raw}).load()

    def test_raw_ohlc_and_json_decimals_survive_without_adjusted_execution(self):
        data = source().load()
        self.assertEqual(data.bars[0].open, Decimal("100.000000000000000000001"))
        self.assertEqual(data.bars[0].close, Decimal("101"))
        self.assertEqual(data.bars[0].volume, Decimal("1000"))
        self.assertEqual(data.sessions, (date(2024, 1, 2), date(2024, 1, 3)))
        self.assertEqual(data.bars[0].security_id, "ID-1")
        self.assertFalse(data.metadata.actions_complete)
        self.assertIn(("eodhd:response:SYNTH.US", sha256(RAW).hexdigest()), data.metadata.input_hashes)
        self.assertTrue(any("split-adjusted volume" in s for s in data.metadata.limitations))
        self.assertEqual(data.metadata.adjustment_policy, "raw_prices_split_adjusted_volume")
        self.assertTrue(any("incomplete" in s for s in data.metadata.limitations))

    def test_content_addressed_cache_is_immutable_and_contains_original_bytes(self):
        with TemporaryDirectory() as directory:
            data = source(cache_dir=Path(directory)).load()
            path = Path(directory) / (sha256(RAW).hexdigest() + ".json")
            self.assertEqual(path.read_bytes(), RAW)
            self.assertEqual(source(cache_dir=Path(directory)).load(), data)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            path.write_bytes(b"corruption")
            with self.assertRaisesRegex(ValueError, "cache integrity"):
                source(cache_dir=Path(directory)).load()
            self.assertEqual(path.read_bytes(), b"corruption")

    def test_failed_cache_publication_removes_partial_files(self):
        with TemporaryDirectory() as directory:
            with patch("quant_core.data.eodhd.os.link", side_effect=OSError("blocked")):
                with self.assertRaisesRegex(ValueError, "cache"):
                    source(cache_dir=Path(directory)).load()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_provider_errors_and_malicious_values_never_leak_raw_content(self):
        secret = "https://eodhd.com/api/eod/A?api_token=SECRET-123"
        raw_errors = [secret.encode(), ('{"error":"' + secret + '"}').encode(),
                      RAW.replace(b'101', ('"' + secret + '"').encode()),
                      RAW.replace(b'2024-01-02', secret.encode())]
        for raw in raw_errors:
            with self.subTest(raw=raw), TemporaryDirectory() as directory:
                with self.assertRaises(ValueError) as caught:
                    source(responses={"SYNTH.US": raw}, cache_dir=Path(directory)).load()
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("https:", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_missing_mapping_unknown_ids_duplicate_dates_and_outside_calendar_rejected(self):
        cases = [dict(ticker_security_ids={}),
                 dict(ticker_security_ids={"SYNTH.US": "UNKNOWN"}),
                 dict(responses={"SYNTH.US": RAW[:-1] + b',' + RAW[1:]}),
                 dict(sessions=(date(2024, 1, 3),)),
                 dict(responses={"SYNTH.US?api_token=SECRET": RAW}),
                 dict(responses={"SYNTH.US": []})]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                source(**changes).load()

    def test_malformed_dates_future_observations_invalid_volume_and_duplicate_json_keys(self):
        rows = [RAW.replace(b'2024-01-02', b'20240102'),
                RAW.replace(b'2024-01-02', b'2024-01-02T00:00:00Z'),
                RAW.replace(b'1000', b'1.5'), RAW.replace(b'1000', b'true'),
                RAW.replace(b'"close":101', b'"close":101,"close":102')]
        for raw in rows:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                source(responses={"SYNTH.US": raw}).load()
        with self.assertRaisesRegex(ValueError, "retrieval"):
            source(metadata=replace(source().metadata,
                                    retrieved_at=datetime(2024, 1, 1, tzinfo=timezone.utc))).load()

    def test_supplied_reviewed_actions_preserved_without_fabricated_pay_dates(self):
        dividend = Dividend("ID-1", date(2024, 1, 2), "1.20", date(2024, 1, 5))
        data = source(actions=(dividend,), actions_review_hash="a" * 64,
                      metadata=replace(source().metadata, actions_complete=True)).load()
        self.assertEqual(data.actions, (dividend,))
        self.assertTrue(data.metadata.actions_complete)
        self.assertIn(("eodhd:reviewed_actions", "a" * 64), data.metadata.input_hashes)
        with self.assertRaisesRegex(ValueError, "review"):
            source(metadata=replace(source().metadata, actions_complete=True)).load()
        with self.assertRaisesRegex(ValueError, "review"):
            source(actions=(dividend,)).load()
        with self.assertRaises(ValueError):
            source(actions=({"paymentDate": None},), actions_review_hash="a" * 64).load()

    def test_exact_share_counts_are_retained_in_reviewed_splits(self):
        action = Split("ID-1", date(2024, 1, 2), new_shares=1, old_shares=3)
        data = source(actions=(action,), actions_review_hash="b" * 64).load()
        self.assertEqual(data.actions[0].new_shares, 1)
        self.assertEqual(data.actions[0].old_shares, 3)


class EodhdClientTests(unittest.TestCase):
    def test_explicit_request_and_cached_download_retain_original_retrieval_time(self):
        requests = []

        def open_request(request, timeout):
            requests.append(request.full_url)
            self.assertEqual(timeout, 30)
            self.assertEqual(request.full_url,
                             "https://eodhd.com/api/eod/SYNTH.US?api_token=SECRET-123&fmt=json&period=d&order=a&from=2024-01-02&to=2024-01-03")
            return BytesIO(RAW)

        with TemporaryDirectory() as directory:
            client = EodhdClient("SECRET-123", Path(directory))
            self.assertNotIn("SECRET", repr(client))
            with patch("quant_core.data.eodhd.build_opener") as opener:
                opener.return_value.open.side_effect = open_request
                first = client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))
            self.assertEqual(first.raw, RAW)
            self.assertIsNotNone(first.retrieved_at.utcoffset())
            with patch("quant_core.data.eodhd.build_opener", side_effect=AssertionError("cache must prevent network")):
                second = client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))
            self.assertEqual(second, first)
            self.assertEqual(len(requests), 1)
            self.assertNotIn("SECRET", repr(first))
            for path in Path(directory).iterdir():
                self.assertNotIn("SECRET", path.name)
                self.assertNotIn("SECRET", path.read_text())

    def test_http_rate_limit_auth_and_transport_errors_redact_credentials(self):
        url = "https://eodhd.com/api/eod/SYNTH.US?api_token=SECRET-123"
        errors = [HTTPError(url, code, "SECRET-123", {}, BytesIO(b"SECRET-123"))
                  for code in (401, 403, 429, 500)] + [URLError(url)]
        for error in errors:
            with self.subTest(error=type(error)), TemporaryDirectory() as directory:
                client = EodhdClient("SECRET-123", Path(directory))
                with patch("quant_core.data.eodhd.build_opener") as opener:
                    opener.return_value.open.side_effect = error
                    with self.assertRaises(ValueError) as caught:
                        client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("https:", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_request_and_response_bounds_do_not_create_cache(self):
        with TemporaryDirectory() as directory:
            client = EodhdClient("SECRET-123", Path(directory))
            for ticker, start, end in (("URL?api_token=SECRET", date(2024, 1, 2), date(2024, 1, 3)),
                                        ("SYNTH.US", datetime(2024, 1, 2), date(2024, 1, 3)),
                                        ("SYNTH.US", date(2024, 1, 3), date(2024, 1, 2))):
                with self.subTest(ticker=ticker), patch("quant_core.data.eodhd.build_opener", side_effect=AssertionError("no request")):
                    with self.assertRaises(ValueError):
                        client.download(ticker, start, end)
            for raw in (b'{"error":"SECRET-123"}', RAW):
                with patch("quant_core.data.eodhd.build_opener") as opener:
                    opener.return_value.open.return_value = BytesIO(raw)
                    with self.assertRaises(ValueError):
                        client.download("SYNTH.US", date(2024, 1, 3), date(2024, 1, 3))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cache_corruption_is_rejected_without_network_or_overwrite(self):
        with TemporaryDirectory() as directory:
            client = EodhdClient("SECRET-123", Path(directory))
            with patch("quant_core.data.eodhd.build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(RAW)
                client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))
            raw_path = Path(directory) / (sha256(RAW).hexdigest() + ".json")
            raw_path.write_bytes(b"broken")
            with patch("quant_core.data.eodhd.build_opener", side_effect=AssertionError("no request")):
                with self.assertRaisesRegex(ValueError, "cache"):
                    client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))
            self.assertEqual(raw_path.read_bytes(), b"broken")

    def test_rehashed_cache_still_requires_valid_dates_rows_and_requested_bounds(self):
        cases = [(RAW.replace(b'2024-01-02', b'2024-01-01'), None),
                 (b'{"error":"SECRET-123"}', None),
                 (RAW, "2024-01-04T00:00:00"), (RAW, "2024-01-01T00:00:00+00:00")]
        for raw, timestamp in cases:
            with self.subTest(timestamp=timestamp), TemporaryDirectory() as directory:
                client = EodhdClient("SECRET-123", Path(directory))
                with patch("quant_core.data.eodhd.build_opener") as opener:
                    opener.return_value.open.return_value = BytesIO(RAW)
                    client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))
                manifest_path = next(Path(directory).glob("*.request.json"))
                envelope = json.loads(manifest_path.read_text())
                envelope["manifest"]["response_hash"] = sha256(raw).hexdigest()
                if timestamp is not None:
                    envelope["manifest"]["retrieved_at"] = timestamp
                envelope["manifest_hash"] = content_hash(envelope["manifest"])
                manifest_path.write_text(canonical_json(envelope))
                (Path(directory) / (sha256(raw).hexdigest() + ".json")).write_bytes(raw)
                with patch("quant_core.data.eodhd.build_opener", side_effect=AssertionError("no request")):
                    with self.assertRaisesRegex(ValueError, "cache"):
                        client.download("SYNTH.US", date(2024, 1, 2), date(2024, 1, 3))


if __name__ == "__main__":
    unittest.main()
