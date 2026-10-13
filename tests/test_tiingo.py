"""Tiingo downloads and normalization; fixtures are synthetic rows in Tiingo's response format."""

from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from quant_core.data import Dividend, Security, Split, require_raw_volume
from quant_core.data.quality import check_quality
from quant_core.data.remote import RequestBudget, RequestBudgetExhausted, RequestCache
from quant_core.data.tiingo import NO_PAYMENT_DATES, TiingoClient, TiingoJsonSource, TiingoResponse

AT = datetime(2024, 1, 10, 23, 30, tzinfo=timezone.utc)
D1, D2, D3 = date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)


def row(day, close, adjusted=None, div="0.0", split="1.0", volume="1000", day_text=None):
    adjusted = close if adjusted is None else adjusted
    return (f'{{"date":"{day_text or day.isoformat() + "T00:00:00.000Z"}","close":{close},"high":{close},'
            f'"low":{close},"open":{close},"volume":{volume},"adjClose":{adjusted},"adjHigh":{adjusted},'
            f'"adjLow":{adjusted},"adjOpen":{adjusted},"adjVolume":{volume},"divCash":{div},"splitFactor":{split}}}')


def prices(*rows, at=AT):
    return TiingoResponse(("[" + ",".join(rows) + "]").encode(), at)


def meta(ticker, exchange="NYSE ARCA"):
    return TiingoResponse(f'{{"ticker":"{ticker}","name":"x","startDate":"1993-01-29","endDate":"2024-01-10",'
                          f'"exchangeCode":"{exchange}"}}'.encode(), AT)


# SPY pays 2.00 on D3. Back-adjusted closes before the ex-date carry the factor (101 - 2) / 101.
SPY = prices(row(D1, "100", "98.0198019802"), row(D2, "101", "99"), row(D3, "99", "99", div="2.0"))


def load(price_map, metadata=None, **options):
    metadata = metadata or {ticker: meta(ticker) for ticker in price_map}
    return TiingoJsonSource(price_map, metadata, **options).load()


class TiingoSourceTests(unittest.TestCase):
    def test_raw_bars_and_reported_dividends_become_a_raw_snapshot(self):
        data = load({"SPY": SPY})
        self.assertEqual(data.sessions, (D1, D2, D3))
        self.assertEqual([b.close for b in data.bars], [100, 101, 99])
        self.assertEqual(data.actions, (Dividend("SPY", D3, "2.0", D3),))
        self.assertEqual(data.securities, (Security("SPY", "SPY", "NYSE ARCA", listed_on=D1),))
        self.assertEqual((data.metadata.source, data.metadata.adjustment_policy, data.metadata.actions_complete),
                         ("tiingo", "raw", True))
        self.assertEqual(data.metadata.retrieved_at, AT)
        self.assertIn(NO_PAYMENT_DATES, data.metadata.limitations)
        self.assertTrue(any("SPY trading days" in s for s in data.metadata.limitations))
        self.assertEqual([name for name, _ in data.metadata.input_hashes], ["tiingo:metadata:SPY", "tiingo:prices:SPY"])
        require_raw_volume(data.metadata, "test")
        self.assertFalse(check_quality(data).has_errors)

    def test_split_factors_become_exact_share_counts(self):
        eem = prices(row(D1, "90", "30"), row(D2, "30", "30", split="3.000003"), row(D3, "30"))
        bil = prices(row(D1, "45", "90"), row(D2, "90", "90", split="0.5"), row(D3, "90"))
        data = load({"SPY": SPY, "EEM": eem, "BIL": bil})
        splits = {a.security_id: (a.new_shares, a.old_shares) for a in data.actions if isinstance(a, Split)}
        self.assertEqual(splits, {"EEM": (3, 1), "BIL": (1, 2)})
        self.assertIn("Tiingo split factor 3.000003 for EEM on 2024-01-03 is treated as 3-for-1.",
                      data.metadata.limitations)
        self.assertFalse(any("BIL on" in s for s in data.metadata.limitations))

    def test_adjustments_the_provider_did_not_report_stop_the_import(self):
        unreported = prices(row(D1, "100", "98.0198019802"), row(D2, "101", "99"), row(D3, "99", "99"))
        with self.assertRaisesRegex(ValueError, r"adjClose for SPY disagrees .*first 2024-01-03 to 2024-01-04"):
            load({"SPY": unreported})

    def test_dividends_follow_tiingos_ex_date_close_convention(self):
        # A 1.2 dividend with a 10% fall on the ex-date: Tiingo's factor is 90 / 91.2; the previous-close
        # convention, (100 - 1.2) / 100, differs by 0.12% and would wrongly stop the import.
        volatile = prices(row(D1, "100", "98.6842105263"), row(D2, "100", "98.6842105263"),
                          row(D3, "90", "90", div="1.2"))
        self.assertEqual(load({"SPY": volatile}).actions, (Dividend("SPY", D3, "1.2", D3),))
        # A 0.05 dividend on a 91.5 price (0.055%) that adjClose applies but divCash omits is caught.
        dropped = prices(row(D1, "91.5", "91.4500273224"), row(D2, "91.5", "91.4500273224"), row(D3, "91.5"))
        with self.assertRaisesRegex(ValueError, "adjClose for SPY disagrees"):
            load({"SPY": dropped})

    def test_a_split_and_dividend_on_the_same_day_combine(self):
        # Our assumption, unverified against Tiingo: split first, then the dividend per post-split share.
        both = prices(row(D1, "100", "49.5049504950"), row(D2, "50", "50", div="0.5", split="2.0"), row(D3, "50"))
        data = load({"SPY": both})
        self.assertEqual(data.actions, (Dividend("SPY", D2, "0.5", D2), Split("SPY", D2, new_shares=2, old_shares=1)))

    def test_coarse_adjusted_closes_are_disclosed_not_trusted(self):
        coarse = prices(row(D1, "100", "0.0001"), row(D2, "50", "0.0001", split="2.0"), row(D3, "50", "0.0001"))
        notes = load({"SPY": coarse}).metadata.limitations
        self.assertIn("Tiingo adjClose for SPY is too coarsely rounded to verify 2 session pair(s).", notes)

    def test_retrieval_times_are_aware_and_recorded_in_utc(self):
        new_york = datetime.fromisoformat("2024-01-04T17:30:00-05:00")  # 22:30 UTC.
        with self.assertRaisesRegex(ValueError, "before 23:00 UTC"):
            load({"SPY": prices(row(D1, "100"), row(D3, "100"), at=new_york)})
        later = datetime.fromisoformat("2024-01-11T09:00:00+09:00")  # Midnight UTC, after AT, in Seoul time.
        data = load({"SPY": SPY}, {"SPY": TiingoResponse(meta("SPY").raw, later)})
        self.assertEqual((data.metadata.retrieved_at, data.metadata.retrieved_at.utcoffset()),
                         (later, timezone.utc.utcoffset(None)))
        for raw, at in ((b"[]", datetime(2024, 1, 10)), ("[]", AT), (b"[]", "2024-01-10")):
            with self.subTest(at=at), self.assertRaisesRegex(ValueError, "Tiingo"):
                TiingoResponse(raw, at)

    def test_bars_that_may_be_partial_sessions_are_refused(self):
        before_close = datetime(2024, 1, 4, 22, 0, tzinfo=timezone.utc)  # 17:00 in New York.
        with self.assertRaisesRegex(ValueError, "2024-01-04 for SPY may be a partial session"):
            load({"SPY": prices(row(D1, "100"), row(D3, "100"), at=before_close)})
        load({"SPY": prices(row(D1, "100"), row(D3, "100"), at=datetime(2024, 1, 4, 23, 0, tzinfo=timezone.utc))})

    def test_calendar_is_the_calendar_tickers_days(self):
        late = prices(row(D2, "50"), row(D3, "50"))
        data = load({"SPY": SPY, "GLD": late})
        self.assertEqual({s.security_id: s.listed_on for s in data.securities}, {"SPY": D1, "GLD": D2})
        with self.assertRaisesRegex(ValueError, "2024-01-05 for GLD is after the last SPY session in the download"):
            load({"SPY": SPY, "GLD": prices(row(D3, "50"), row(date(2024, 1, 5), "50"))})
        with self.assertRaisesRegex(ValueError, "2024-01-01 for GLD is before the first SPY session in the download"):
            load({"SPY": SPY, "GLD": prices(row(date(2024, 1, 1), "50"), row(D2, "50"))})
        with self.assertRaisesRegex(ValueError, "2024-01-03 for GLD is not a SPY trading day"):
            load({"SPY": prices(row(D1, "100"), row(D3, "100")), "GLD": prices(row(D2, "50"), row(D3, "50"))})
        with self.assertRaisesRegex(ValueError, "Calendar ticker SPY"):
            load({"GLD": late})

    def test_malformed_rows_are_refused_without_echoing_content(self):
        cases = [row(D1, "100", day_text="2024-01-02"), row(D1, '"100"'), row(D1, "100", volume="true"),
                 row(D1, "100", volume="10.5"), row(D1, "100", div="-1"), row(D1, "100", split="1.0001234567"),
                 row(D1, "100", split="1.000001"), row(D1, "100", split="2.7182818"),
                 row(D1, "100", split="1e+2000000"), row(D1, "1e+999"), row(D1, "100", split="0.367879"),
                 row(D1, "100", split="3.000000000000000000000000000000000000001"),
                 row(D1, "100", adjusted="0"), row(D1, "100").replace('"close"', '"x"'),
                 row(D1, "100").replace('"low":100', '"low":101'),
                 row(D1, '"SECRET-1"'), row(D1, "100").replace('"open":100', '"open":100,"open":100')]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "Tiingo") as caught:
                load({"SPY": prices(bad)})
            self.assertNotIn("SECRET", str(caught.exception))
        for raw in (b'{"detail":"Not found."}', b"[]", b"not json"):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "Tiingo prices for SPY"):
                load({"SPY": TiingoResponse(raw, AT)})
        with self.assertRaisesRegex(ValueError, "ascending"):
            load({"SPY": prices(row(D2, "100"), row(D1, "100"))})
        with self.assertRaisesRegex(ValueError, r"row 1 \(2024-01-02\) for SPY"):
            load({"SPY": prices(row(D1, "100").replace('"low":100', '"low":101'))})

    def test_metadata_and_tickers_are_validated(self):
        for metadata in (meta("IEF"), meta("SPY", exchange=" "), TiingoResponse(b"{", AT)):
            with self.subTest(metadata=metadata.raw), self.assertRaisesRegex(ValueError, "metadata for SPY"):
                load({"SPY": SPY}, {"SPY": metadata})
        with self.assertRaisesRegex(ValueError, "same tickers"):
            load({"SPY": SPY}, {"IEF": meta("IEF")})
        for tickers in ({"SPY": SPY, "gld": SPY}, {"SPY": SPY, 7: SPY}):
            with self.subTest(tickers=tuple(tickers)), self.assertRaisesRegex(ValueError, "upper-case"):
                load(tickers, {ticker: meta("SPY") for ticker in tickers})


class TiingoClientTests(unittest.TestCase):
    RAW = ("[" + row(D1, "100") + "]").encode()

    def call(self, client, method, *args, raw=None, error=None):
        with patch("quant_core.data.remote.build_opener") as opener:
            if error is not None:
                opener.return_value.open.side_effect = error
            else:
                opener.return_value.open.return_value = BytesIO(self.RAW if raw is None else raw)
            response = getattr(client, method)(*args)
        return response, opener.return_value.open.call_args_list

    def test_key_travels_only_in_the_header_and_final_requests_are_cached(self):
        with TemporaryDirectory() as directory:
            client = TiingoClient("SECRET-1", Path(directory))
            self.assertNotIn("SECRET", repr(client))
            first, calls = self.call(client, "prices", "SPY", D1, D3)
            (request,), kwargs = calls[0]
            self.assertEqual(request.full_url, "https://api.tiingo.com/tiingo/daily/SPY/prices"
                                               "?startDate=2024-01-02&endDate=2024-01-04&format=json")
            self.assertEqual(request.get_header("Authorization"), "Token SECRET-1")
            self.assertEqual(kwargs, {"timeout": 30})
            self.assertEqual(first.raw, self.RAW)
            with patch("quant_core.data.remote.build_opener", side_effect=AssertionError("cached")):
                self.assertEqual(client.prices("SPY", D1, D3), first)
            for path in Path(directory).iterdir():
                self.assertNotIn("SECRET", path.name + path.read_text())

    def test_requests_that_end_today_or_later_are_sent_again(self):
        with TemporaryDirectory() as directory:
            client = TiingoClient("SECRET-1", Path(directory))
            for _ in range(2):
                _, calls = self.call(client, "prices", "SPY", D1, date(2999, 1, 1))
                self.assertEqual(len(calls), 1)
            self.assertEqual(list(Path(directory).glob("*.request.json")), [])
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)

    def test_a_price_response_is_final_once_it_holds_its_end_date_or_a_week_has_passed(self):
        three = ("[" + ",".join((row(D1, "100"), row(D2, "100"), row(D3, "100"))) + "]").encode()
        cases = [(datetime(2024, 1, 4, 23, 0, tzinfo=timezone.utc), three, True),  # End-date bar present.
                 (datetime(2024, 1, 4, 23, 0, tzinfo=timezone.utc), self.RAW, False),  # Missing: may come late.
                 (datetime(2024, 1, 10, 23, 0, tzinfo=timezone.utc), self.RAW, False),  # Six days on.
                 (datetime(2024, 1, 11, 23, 0, tzinfo=timezone.utc), self.RAW, True)]  # Seven days on.
        for now, raw, cached in cases:
            with self.subTest(now=now, cached=cached), TemporaryDirectory() as directory, \
                    patch("quant_core.data.tiingo._now", return_value=now):
                self.call(TiingoClient("SECRET-1", Path(directory)), "prices", "SPY", D1, D3, raw=raw)
                self.assertEqual(len(list(Path(directory).glob("*.request.json"))), int(cached))
        before = datetime(2024, 1, 4, 22, 59, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory, patch("quant_core.data.tiingo._now", return_value=before):
            with self.assertRaisesRegex(ValueError, "partial session"):
                self.call(TiingoClient("SECRET-1", Path(directory)), "prices", "SPY", D1, D3, raw=three)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_only_requests_actually_sent_spend_the_budget(self):
        with TemporaryDirectory() as directory:
            budget = RequestBudget(1)
            client = TiingoClient("SECRET-1", Path(directory), budget=budget)
            first, _ = self.call(client, "prices", "SPY", D1, D3)
            self.assertEqual(budget.used, 1)
            self.assertEqual(self.call(client, "prices", "SPY", D1, D3), (first, []))  # Cached: free.
            with self.assertRaisesRegex(RequestBudgetExhausted, "Tiingo request budget of 1 is spent"):
                self.call(client, "metadata", "SPY")
            with patch("quant_core.data.remote.build_opener", side_effect=AssertionError("sent")):
                with self.assertRaises(RequestBudgetExhausted):
                    client.metadata("SPY")
            self.assertEqual(budget.used, 1)
        with self.assertRaisesRegex(ValueError, "RequestBudget"):
            TiingoClient("SECRET-1", Path("unused"), budget=1)

    def test_failed_and_unfinished_requests_spend_the_budget_too(self):
        url = "https://api.tiingo.com/tiingo/daily/SPY/prices"
        with TemporaryDirectory() as directory:
            budget = RequestBudget(3)
            client = TiingoClient("SECRET-1", Path(directory), budget=budget)
            with self.assertRaisesRegex(ValueError, "HTTP 500"):
                self.call(client, "prices", "SPY", D1, D3, error=HTTPError(url, 500, "x", {}, BytesIO(b"")))
            with self.assertRaisesRegex(ValueError, "metadata for SPY"):
                self.call(client, "metadata", "SPY")  # A price array is not metadata: sent, then refused.
            self.call(client, "prices", "SPY", D1, date(2999, 1, 1))  # Not final: sent, so spent.
            self.assertEqual(budget.used, 3)
            with self.assertRaises(RequestBudgetExhausted):
                self.call(client, "prices", "SPY", D1, date(2999, 1, 1))  # Never cached, so never free.

    def test_cached_responses_are_validated_again(self):
        with TemporaryDirectory() as directory:
            request = {"startDate": "2024-01-02", "endDate": "2024-01-04", "endpoint": "prices", "ticker": "SPY"}
            RequestCache(Path(directory), "Tiingo", ".json").store(request, b"[]", AT)
            with patch("quant_core.data.remote.build_opener", side_effect=AssertionError("cached")):
                with self.assertRaisesRegex(ValueError, "not a nonempty daily array"):
                    TiingoClient("SECRET-1", Path(directory)).prices("SPY", D1, D3)

    def test_metadata_is_validated_and_cached(self):
        with TemporaryDirectory() as directory:
            client = TiingoClient("SECRET-1", Path(directory))
            response, calls = self.call(client, "metadata", "SPY", raw=meta("SPY").raw)
            self.assertEqual(calls[0][0][0].full_url, "https://api.tiingo.com/tiingo/daily/SPY")
            self.assertEqual(self.call(client, "metadata", "SPY")[1], [])
            with self.assertRaisesRegex(ValueError, "metadata for IEF"):
                self.call(client, "metadata", "IEF", raw=meta("SPY").raw)

    def test_errors_explain_the_problem_without_the_key(self):
        url = "https://api.tiingo.com/tiingo/daily/SPY/prices"
        cases = [(401, "rejected the API key"), (403, "rejected the API key"), (404, "does not know this ticker"),
                 (429, "rate limit .* resume later"), (500, r"HTTP 500")]
        for code, message in cases:
            with self.subTest(code=code), TemporaryDirectory() as directory:
                error = HTTPError(url, code, "SECRET-1", {}, BytesIO(b"SECRET-1"))
                with self.assertRaisesRegex(ValueError, message) as caught:
                    self.call(TiingoClient("SECRET-1", Path(directory)), "prices", "SPY", D1, D3, error=error)
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertEqual(list(Path(directory).iterdir()), [])
        with TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "transport"):
            self.call(TiingoClient("SECRET-1", Path(directory)), "prices", "SPY", D1, D3, error=URLError(url))

    def test_invalid_requests_and_responses_leave_no_cache(self):
        with TemporaryDirectory() as directory:
            client = TiingoClient("SECRET-1", Path(directory))
            for args in (("spy", D1, D3), ("SPY/../x", D1, D3), ("SPY", D3, D1), ("SPY", datetime(2024, 1, 2), D3)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    self.call(client, "prices", *args)
            partial = ("[" + row(date(2999, 1, 2), "100") + "]").encode()
            with self.assertRaisesRegex(ValueError, "partial session"):
                self.call(client, "prices", "SPY", D1, date(2999, 12, 31), raw=partial)
            with self.assertRaisesRegex(ValueError, "outside the requested dates"):
                self.call(client, "prices", "SPY", D2, D3)
            two = ("[" + ",".join((row(D1, "100"), row(D2, "100"))) + "]").encode()
            with self.assertRaisesRegex(ValueError, "outside the requested dates"):
                self.call(client, "prices", "SPY", D1, D1, raw=two)
            with self.assertRaisesRegex(ValueError, "upper-case"):
                self.call(client, "metadata", "spy")
            self.assertEqual(list(Path(directory).iterdir()), [])
        for token in ("", "two words", None, "k\u00e9y"):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "printable ASCII"):
                TiingoClient(token, Path("unused"))
        with self.assertRaisesRegex(ValueError, "timeout"):
            TiingoClient("SECRET-1", Path("unused"), timeout=0)


if __name__ == "__main__":
    unittest.main()
