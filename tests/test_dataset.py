"""Frozen datasets: a budgeted download, quality checks, saving once and verified reloading."""

from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core.data.dataset import DownloadIncomplete, download_dataset, load_dataset, save_dataset
from quant_core.data.rates import CashRateSeries
from quant_core.data.remote import RequestBudget
from quant_core.data.storage import save_cash_rates, save_snapshot
from quant_core.data.tiingo import TiingoClient, TiingoResponse, metadata_start
from quant_core.data.treasury import FIRST_YEAR, TreasuryResponse
from quant_core.provenance import code_hash, content_hash
from test_tiingo import AT, D1, D2, D3, row

BASE = "https://api.tiingo.com/tiingo/daily/"
STARTS = {"SPY": D1, "GLD": D2}


def metadata(ticker, start):
    return (f'{{"ticker":"{ticker}","name":"x","startDate":"{start.isoformat()}","endDate":"2024-01-10",'
            f'"exchangeCode":"NYSE ARCA"}}').encode()


def body(*rows):
    return ("[" + ",".join(rows) + "]").encode()


# SPY pays 2.00 on D3 (adjusted closes as in test_tiingo); GLD lists on D2.
SPY_ROWS = body(row(D1, "100", "98.0198019802"), row(D2, "101", "99"), row(D3, "99", "99", div="2.0"))
GLD_ROWS = body(row(D2, "50"), row(D3, "51"))
URLS = {BASE + "GLD": metadata("GLD", D2), BASE + "SPY": metadata("SPY", D1),
        BASE + "GLD/prices?startDate=2024-01-03&endDate=2024-01-04&format=json": GLD_ROWS,
        BASE + "SPY/prices?startDate=2024-01-02&endDate=2024-01-04&format=json": SPY_ROWS}


class FakeTiingo:
    def __init__(self, bodies, starts=STARTS):
        self.bodies, self.starts, self.calls = bodies, starts, []

    def metadata(self, ticker):
        self.calls.append(("metadata", ticker))
        return TiingoResponse(metadata(ticker, self.starts[ticker]), AT)

    def prices(self, ticker, start, end):
        self.calls.append(("prices", ticker, start, end))
        return TiingoResponse(self.bodies[ticker], AT)


class FakeTreasury:
    """Two synthetic 3-month observations a year, newest first like the Treasury's files."""

    def __init__(self):
        self.years = []

    def year(self, year):
        self.years.append(year)
        return TreasuryResponse(year, f'Date,"3 Mo"\n12/31/{year},4.10\n01/02/{year},4.00\n'.encode(), AT)


@contextmanager
def tiingo_server(bodies):
    """Answer Tiingo URLs from `bodies` at retrieval time AT; yields the requests actually sent."""
    sent = []

    def answer(request, timeout):
        sent.append(request)
        return BytesIO(bodies[request.full_url])

    with patch("quant_core.data.remote.build_opener") as opener, patch("quant_core.data.tiingo._now", return_value=AT):
        opener.return_value.open.side_effect = answer
        yield sent


class DatasetTests(unittest.TestCase):
    def test_a_download_is_checked_saved_and_reloaded(self):
        tiingo, treasury = FakeTiingo({"SPY": SPY_ROWS, "GLD": GLD_ROWS}), FakeTreasury()
        dataset = download_dataset(["SPY", "GLD"], D3, tiingo, treasury)
        self.assertEqual(tiingo.calls, [("metadata", "GLD"), ("prices", "GLD", D2, D3),
                                        ("metadata", "SPY"), ("prices", "SPY", D1, D3)])
        self.assertEqual(treasury.years, list(range(FIRST_YEAR, 2025)))
        manifest = dataset.manifest
        self.assertEqual((manifest["tickers"], manifest["end"], manifest["code_hash"]),
                         (["GLD", "SPY"], "2024-01-04", code_hash()))
        self.assertEqual(manifest["requests"][1], {"endpoint": "prices", "ticker": "GLD", "start": "2024-01-03",
                                                   "end": "2024-01-04", "sha256": sha256(GLD_ROWS).hexdigest(),
                                                   "retrieved_at": AT.isoformat()})
        self.assertEqual(manifest["securities"]["GLD"],
                         {"first_session": "2024-01-03", "last_session": "2024-01-04", "bars": 2})
        self.assertEqual((manifest["snapshot"]["sessions"], manifest["snapshot"]["dataset_hash"]),
                         (3, dataset.snapshot.dataset_hash))
        # 34 full years of two observations, then 2024's rows up to the end date only.
        self.assertEqual((manifest["rates"]["first"], manifest["rates"]["last"], manifest["rates"]["observations"]),
                         ("1990-01-02", "2024-01-02", 69))
        self.assertEqual(manifest["dataset_id"], content_hash({k: v for k, v in manifest.items() if k != "dataset_id"}))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dataset"
            self.assertEqual(save_dataset(path, dataset), manifest["dataset_id"])
            self.assertEqual(sorted(p.name for p in path.iterdir()), ["manifest.json", "rates.json", "snapshot.json"])
            self.assertEqual(load_dataset(path), dataset)

    def test_existing_directories_and_mismatched_files_are_refused(self):
        dataset = download_dataset(["SPY"], D3, FakeTiingo({"SPY": SPY_ROWS}), FakeTreasury())
        other = download_dataset(["SPY", "GLD"], D3, FakeTiingo({"SPY": SPY_ROWS, "GLD": GLD_ROWS}), FakeTreasury())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dataset"
            save_dataset(path, dataset)
            with self.assertRaisesRegex(ValueError, "already exists; datasets are never overwritten"):
                save_dataset(path, dataset)
            manifest = (path / "manifest.json").read_text()
            (path / "manifest.json").write_text(manifest.replace('"end":"2024-01-04"', '"end":"2024-01-05"'))
            with self.assertRaisesRegex(ValueError, "manifest integrity"):
                load_dataset(path)
            (path / "manifest.json").write_text(manifest)
            (path / "snapshot.json").unlink()
            save_snapshot(other.snapshot, path / "snapshot.json")  # A valid snapshot, but not this one.
            with self.assertRaisesRegex(ValueError, "do not match its manifest"):
                load_dataset(path)
            (path / "snapshot.json").unlink()
            save_snapshot(dataset.snapshot, path / "snapshot.json")
            (path / "rates.json").unlink()
            save_cash_rates(CashRateSeries("x", "y", AT, ((D1, "0.01"),)), path / "rates.json")  # Valid, but not these.
            with self.assertRaisesRegex(ValueError, "do not match its manifest"):
                load_dataset(path)

    def test_a_spent_budget_stops_the_download_and_a_later_run_resumes_from_the_cache(self):
        with TemporaryDirectory() as directory:
            def client(limit):
                return TiingoClient("SECRET-1", Path(directory), budget=RequestBudget(limit))

            with tiingo_server(URLS) as sent, self.assertRaises(DownloadIncomplete) as caught:
                download_dataset(["SPY", "GLD"], D3, client(3), FakeTreasury())
            self.assertEqual(len(sent), 3)  # GLD's two requests and SPY's metadata.
            self.assertEqual(caught.exception.remaining, ("SPY",))
            self.assertIn("1 ticker(s) still to download: SPY", str(caught.exception))
            with tiingo_server(URLS) as sent:
                dataset = download_dataset(["SPY", "GLD"], D3, client(1), FakeTreasury())
            self.assertEqual([r.full_url for r in sent],
                             [BASE + "SPY/prices?startDate=2024-01-02&endDate=2024-01-04&format=json"])
            self.assertEqual(dataset.manifest["tickers"], ["GLD", "SPY"])

    def test_a_quality_error_refuses_the_dataset(self):
        gap = body(row(D1, "50"), row(D3, "51"))  # GLD trades from D1 but has no bar on D2.
        with self.assertRaisesRegex(ValueError, "Data quality error: missing_bar for GLD on 2024-01-03; "
                                                "the dataset was not saved"):
            download_dataset(["SPY", "GLD"], D3, FakeTiingo({"SPY": SPY_ROWS, "GLD": gap},
                                                            {"SPY": D1, "GLD": D1}), FakeTreasury())

    def test_requests_are_validated_before_anything_is_sent(self):
        tiingo = FakeTiingo({"SPY": SPY_ROWS, "GLD": GLD_ROWS})
        for tickers, end, message in ((["GLD"], D3, "needs SPY"), (["SPY", "gld"], D3, "upper-case"),
                                      (["SPY"], "2024-01-04", "must be a date")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                download_dataset(tickers, end, tiingo, FakeTreasury())
        self.assertEqual(tiingo.calls, [])
        with self.assertRaisesRegex(ValueError, "GLD starts trading on 2024-01-03, after the dataset end 2024-01-02"):
            download_dataset(["SPY", "GLD"], D1, tiingo, FakeTreasury())
        self.assertEqual(metadata_start(metadata("SPY", D1), "SPY"), D1)
        for start in (None, "1993-1-29", "1993-02-30"):
            raw = json.dumps({"ticker": "SPY", "exchangeCode": "NYSE ARCA", "startDate": start}).encode()
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "SPY lacks a valid start date"):
                metadata_start(raw, "SPY")


if __name__ == "__main__":
    unittest.main()
