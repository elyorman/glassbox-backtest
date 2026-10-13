"""Frozen datasets: a budgeted download, quality checks, saving once and verified reloading."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import replace
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
from shutil import rmtree
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core import __version__
from quant_core.cli import main, plan_tickers
from quant_core.data.dataset import DownloadIncomplete, download_dataset, load_dataset, save_dataset
from quant_core.data.rates import CashRateSeries
from quant_core.data.remote import RequestBudget, RequestBudgetExhausted
from quant_core.data.storage import save_cash_rates, save_snapshot
from quant_core.data.tiingo import TiingoClient, TiingoResponse, metadata_start
from quant_core.data.treasury import FIRST_YEAR, TreasuryClient, TreasuryResponse
from quant_core.provenance import code_hash, content_hash
from test_tiingo import AT, D1, D2, D3, row

BASE = "https://api.tiingo.com/tiingo/daily/"
STARTS = {"SPY": D1, "GLD": D2, "TLT": D1}


def metadata(ticker, start):
    return (f'{{"ticker":"{ticker}","name":"x","startDate":"{start.isoformat()}","endDate":"2024-01-10",'
            f'"exchangeCode":"NYSE ARCA"}}').encode()


def body(*rows):
    return ("[" + ",".join(rows) + "]").encode()


def prices_url(ticker, start, end):
    return f"{BASE}{ticker}/prices?startDate={start.isoformat()}&endDate={end.isoformat()}&format=json"


# SPY pays 2.00 on D3 (adjusted closes as in test_tiingo); GLD lists on D2 with no volume that day.
SPY_ROWS = body(row(D1, "100", "98.0198019802"), row(D2, "101", "99"), row(D3, "99", "99", div="2.0"))
GLD_ROWS = body(row(D2, "50", volume="0"), row(D3, "51"))
TLT_ROWS = body(row(D1, "90"), row(D2, "91"), row(D3, "92"))
URLS = {BASE + "SPY": metadata("SPY", D1), BASE + "GLD": metadata("GLD", D2), BASE + "TLT": metadata("TLT", D1),
        prices_url("SPY", D1, D3): SPY_ROWS, prices_url("GLD", D2, D3): GLD_ROWS, prices_url("TLT", D1, D3): TLT_ROWS}


def treasury_csv(year):
    """Four synthetic 3-month observations a year, newest first like the Treasury's files."""
    return f'Date,"3 Mo"\n12/31/{year},4.10\n01/05/{year},4.03\n01/04/{year},4.02\n01/02/{year},4.00\n'.encode()


class FakeTiingo:
    def __init__(self, bodies, starts=STARTS, log=None):
        self.bodies, self.starts, self.calls = bodies, starts, [] if log is None else log

    def metadata(self, ticker):
        self.calls.append(("metadata", ticker))
        return TiingoResponse(metadata(ticker, self.starts[ticker]), AT)

    def prices(self, ticker, start, end):
        self.calls.append(("prices", ticker, start, end))
        return TiingoResponse(self.bodies[ticker], AT)


class FakeTreasury:
    def __init__(self, log=None):
        self.calls = [] if log is None else log

    def year(self, year):
        self.calls.append(("year", year))
        return TreasuryResponse(year, treasury_csv(year), AT)


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


def recorded(raw, **fields):
    return {**fields, "sha256": sha256(raw).hexdigest(), "retrieved_at": AT.isoformat()}


class DatasetTests(unittest.TestCase):
    def test_a_download_is_checked_saved_and_reloaded(self):
        log = []
        dataset = download_dataset(["SPY", "GLD"], D3, FakeTiingo({"SPY": SPY_ROWS, "GLD": GLD_ROWS}, log=log),
                                   FakeTreasury(log))
        # The Treasury first (it needs no budget), then SPY, then the others ending on SPY's last session.
        self.assertEqual(log, [("year", year) for year in range(FIRST_YEAR, 2025)]
                         + [("metadata", "SPY"), ("prices", "SPY", D1, D3), ("metadata", "GLD"),
                            ("prices", "GLD", D2, D3)])
        expected = {
            "schema_version": 1, "kind": "tiingo_treasury_dataset", "program_version": __version__,
            "code_hash": code_hash(), "tickers": ["GLD", "SPY"], "requested_end": "2024-01-04", "end": "2024-01-04",
            "requests": [recorded(metadata("SPY", D1), endpoint="metadata", ticker="SPY"),
                         recorded(SPY_ROWS, endpoint="prices", ticker="SPY", start="2024-01-02", end="2024-01-04"),
                         recorded(metadata("GLD", D2), endpoint="metadata", ticker="GLD"),
                         recorded(GLD_ROWS, endpoint="prices", ticker="GLD", start="2024-01-03", end="2024-01-04")],
            "treasury_years": [recorded(treasury_csv(year), year=year) for year in range(FIRST_YEAR, 2025)],
            "snapshot": {"file": "snapshot.json", "dataset_hash": dataset.snapshot.dataset_hash, "sessions": 3,
                         "first_session": "2024-01-02", "last_session": "2024-01-04", "actions": 1},
            "securities": {"GLD": {"first_session": "2024-01-03", "last_session": "2024-01-04", "bars": 2},
                           "SPY": {"first_session": "2024-01-02", "last_session": "2024-01-04", "bars": 3}},
            # 34 years of four observations, then 2024's two up to and including the end date.
            "rates": {"file": "rates.json", "rates_hash": content_hash(dataset.rates),
                      "series": "treasury_3_month_par_yield", "observations": 138, "first": "1990-01-02",
                      "last": "2024-01-04"},
            "quality_warnings": {"source_limitation": 4, "zero_volume": 1},  # The snapshot's four disclosures.
        }
        expected["dataset_id"] = content_hash(expected)
        self.assertEqual(dataset.manifest, expected)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dataset"
            self.assertEqual(save_dataset(path, dataset), expected["dataset_id"])
            self.assertEqual(sorted(p.name for p in path.iterdir()), ["manifest.json", "rates.json", "snapshot.json"])
            self.assertEqual(load_dataset(path), dataset)

    def test_any_end_date_gives_requests_that_end_on_a_trading_day(self):
        log = []
        saturday = D3.replace(day=6)
        dataset = download_dataset(["SPY", "GLD"], saturday, FakeTiingo({"SPY": SPY_ROWS, "GLD": GLD_ROWS}, log=log),
                                   FakeTreasury())
        self.assertEqual(log[1::2], [("prices", "SPY", D1, saturday), ("prices", "GLD", D2, D3)])
        self.assertEqual((dataset.manifest["requested_end"], dataset.manifest["end"]), ("2024-01-06", "2024-01-04"))
        self.assertEqual(dataset.manifest["rates"]["last"], "2024-01-04")  # Not 2024-01-05, after the last session.
        late = download_dataset(["SPY", "GLD"], D3, FakeTiingo({"SPY": SPY_ROWS, "GLD": body(row(D3, "51"))},
                                                               {"SPY": D1, "GLD": D3}), FakeTreasury())
        self.assertEqual(late.manifest["securities"]["GLD"]["first_session"], "2024-01-04")  # Starts on the end.

    def test_existing_directories_and_mismatched_files_are_refused(self):
        dataset = download_dataset(["SPY"], D3, FakeTiingo({"SPY": SPY_ROWS}), FakeTreasury())
        other = download_dataset(["SPY", "GLD"], D3, FakeTiingo({"SPY": SPY_ROWS, "GLD": GLD_ROWS}), FakeTreasury())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dataset"
            altered = replace(dataset, manifest={**dataset.manifest, "end": "2024-01-05"})
            with self.assertRaisesRegex(ValueError, "manifest integrity"):
                save_dataset(path, altered)  # Checked before anything is written.
            self.assertFalse(path.exists())
            save_dataset(path, dataset)
            with self.assertRaisesRegex(ValueError, "already exists; datasets are never overwritten"):
                save_dataset(path, dataset)
            manifest = (path / "manifest.json").read_text()
            (path / "manifest.json").write_text(manifest.replace('"end":"2024-01-04"', '"end":"2024-01-05"'))
            with self.assertRaisesRegex(ValueError, "manifest integrity"):
                load_dataset(path)
            newer = {**json.loads(manifest), "schema_version": 2}
            newer["dataset_id"] = content_hash({k: v for k, v in newer.items() if k != "dataset_id"})
            (path / "manifest.json").write_text(json.dumps(newer))
            with self.assertRaisesRegex(ValueError, "manifest integrity"):
                load_dataset(path)
            (path / "manifest.json").write_text(manifest)
            (path / "snapshot.json").unlink()
            save_snapshot(other.snapshot, path / "snapshot.json")  # A valid snapshot, but not this one.
            with self.assertRaisesRegex(ValueError, "snapshot.json does not match its manifest"):
                load_dataset(path)
            (path / "snapshot.json").unlink()
            save_snapshot(dataset.snapshot, path / "snapshot.json")
            (path / "rates.json").unlink()
            save_cash_rates(CashRateSeries("x", "y", AT, ((D1, "0.01"),)), path / "rates.json")  # Valid, but not these.
            with self.assertRaisesRegex(ValueError, "rates.json does not match its manifest"):
                load_dataset(path)

    def test_a_failed_save_leaves_no_manifest_and_cannot_be_loaded(self):
        dataset = download_dataset(["SPY"], D3, FakeTiingo({"SPY": SPY_ROWS}), FakeTreasury())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dataset"
            with patch("quant_core.data.dataset.save_cash_rates", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_dataset(path, dataset)
            self.assertFalse((path / "manifest.json").exists())  # The manifest is written last.
            with self.assertRaisesRegex(ValueError, "is incomplete or unreadable"):
                load_dataset(path)
            with self.assertRaisesRegex(ValueError, "exists but is incomplete .no manifest.json.: a save failed; "
                                                    "delete it"):
                save_dataset(path, dataset)
            unrelated = Path(directory) / "notes"
            unrelated.mkdir()
            (unrelated / "thesis.txt").write_text("mine")
            with self.assertRaisesRegex(ValueError, "notes already exists; datasets are never overwritten"):
                save_dataset(unrelated, dataset)  # Never told to delete a folder that is not a failed save.

    def test_a_spent_budget_stops_the_download_and_a_later_run_resumes_from_the_cache(self):
        with TemporaryDirectory() as directory:
            def client(limit):
                return TiingoClient("SECRET-1", Path(directory), budget=RequestBudget(limit))

            with tiingo_server(URLS):
                download_dataset(["SPY", "TLT"], D3, client(4), FakeTreasury())  # SPY and TLT are now cached.
            with tiingo_server(URLS) as sent, self.assertRaises(DownloadIncomplete) as caught:
                download_dataset(["SPY", "GLD", "TLT"], D3, client(1), FakeTreasury())
            # GLD's metadata spends the only request; TLT, after GLD, still comes from the cache.
            self.assertEqual([r.full_url for r in sent], [BASE + "GLD"])
            self.assertEqual(caught.exception.remaining, ("GLD",))
            self.assertIn("1 ticker(s) still to download: GLD", str(caught.exception))
            with tiingo_server(URLS) as sent:
                dataset = download_dataset(["SPY", "GLD", "TLT"], D3, client(1), FakeTreasury())
            self.assertEqual([r.full_url for r in sent], [prices_url("GLD", D2, D3)])
            self.assertEqual(dataset.manifest["tickers"], ["GLD", "SPY", "TLT"])
        with TemporaryDirectory() as directory, tiingo_server(URLS) as sent:
            with self.assertRaises(DownloadIncomplete) as caught:
                download_dataset(["SPY", "GLD"], D3, TiingoClient("SECRET-1", Path(directory),
                                                                  budget=RequestBudget(1)), FakeTreasury())
            self.assertEqual(caught.exception.remaining, ("SPY", "GLD"))  # Nothing else is asked without SPY.
            self.assertEqual([r.full_url for r in sent], [BASE + "SPY"])

        class SpentOnSpy(FakeTiingo):
            def prices(self, ticker, start, end):
                raise RequestBudgetExhausted("spent")

        tiingo = SpentOnSpy({})
        with self.assertRaises(DownloadIncomplete):
            download_dataset(["SPY", "GLD"], D3, tiingo, FakeTreasury())
        self.assertEqual(tiingo.calls, [("metadata", "SPY")])  # GLD, even if cached, is not touched.

    def test_quality_errors_and_uncovered_rates_refuse_the_dataset(self):
        gap = body(row(D1, "50"), row(D3, "51"))  # GLD trades from D1 but has no bar on D2.
        with self.assertRaisesRegex(ValueError, "Data quality error: missing_bar for GLD on 2024-01-03; "
                                                "the dataset was not saved"):
            download_dataset(["SPY", "GLD"], D3, FakeTiingo({"SPY": SPY_ROWS, "GLD": gap},
                                                            {"SPY": D1, "GLD": D1}), FakeTreasury())

        class StaleTreasury(FakeTreasury):
            def year(self, year):  # Nothing after 2023-12-01: 32 days before the first session.
                raw = {2023: b'Date,"3 Mo"\n12/01/2023,5.25\n01/03/2023,4.40\n', 2024: b'Date,"3 Mo"\n'}.get(year)
                return TreasuryResponse(year, raw, AT) if raw else super().year(year)

        with self.assertRaisesRegex(ValueError, "Treasury rates do not cover the dataset: treasury_3_month_par_yield "
                                                "is stale for 2024-01-02"):
            download_dataset(["SPY"], D3, FakeTiingo({"SPY": SPY_ROWS}), StaleTreasury())

    def test_errors_name_the_ticker_and_requests_are_validated_first(self):
        class MissingGld(FakeTiingo):
            def prices(self, ticker, start, end):
                if ticker == "GLD":
                    raise ValueError("Tiingo does not know this ticker (HTTP 404)")
                return super().prices(ticker, start, end)

        with self.assertRaisesRegex(ValueError, "^GLD: Tiingo does not know this ticker"):
            download_dataset(["SPY", "GLD"], D3, MissingGld({"SPY": SPY_ROWS}), FakeTreasury())
        tiingo, treasury = FakeTiingo({"SPY": SPY_ROWS, "GLD": GLD_ROWS}), FakeTreasury()
        for tickers, end, message in ((["GLD"], D3, "needs SPY"), (["SPY", "gld"], D3, "upper-case"),
                                      (["SPY"], "2024-01-04", "must be a date")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                download_dataset(tickers, end, tiingo, treasury)
        self.assertEqual((tiingo.calls, treasury.calls), ([], []))
        with self.assertRaisesRegex(ValueError, "GLD: starts trading on 2024-01-03, after the dataset end 2024-01-02"):
            download_dataset(["SPY", "GLD"], D1, FakeTiingo({"SPY": body(row(D1, "100")), "GLD": GLD_ROWS}),
                             FakeTreasury())
        self.assertEqual(metadata_start(metadata("SPY", D1), "SPY"), D1)
        for start in (None, "1993-1-29", "1993-02-30"):
            raw = json.dumps({"ticker": "SPY", "exchangeCode": "NYSE ARCA", "startDate": start}).encode()
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "SPY lacks a valid start date"):
                metadata_start(raw, "SPY")


def command(*args, key=None):
    """Run the CLI with the given TIINGO_API_KEY environment value (None: unset); returns (code, out, err)."""
    out, err = StringIO(), StringIO()
    with patch.dict(os.environ), patch.object(TreasuryClient, "year", lambda self, year: FakeTreasury().year(year)):
        os.environ.pop("TIINGO_API_KEY", None)
        if key is not None:
            os.environ["TIINGO_API_KEY"] = key
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class DownloadCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / ".env").write_text("OTHER=1\nexport TIINGO_API_KEY='SECRET-1'\n")

    def tearDown(self):
        self.directory.cleanup()

    def download(self, *extra, key=None, urls=URLS, tickers=("SPY", "GLD")):
        selection = ("--tickers", *tickers) if tickers else ()
        with tiingo_server(urls) as sent, patch("quant_core.cli._now", return_value=AT):
            code, out, err = command("download-tiingo", "--output", str(self.root / "dataset"), *selection,
                                     "--env-file", str(self.root / ".env"), "--tiingo-cache",
                                     str(self.root / "tiingo"), "--treasury-cache", str(self.root / "treasury"),
                                     *extra, key=key)
        return code, out, err, sent

    def test_the_command_saves_a_dataset_and_never_shows_the_key(self):
        code, out, err, sent = self.download("--end", "2024-01-04")
        self.assertEqual((code, err), (0, ""))
        summary = json.loads(out)
        self.assertEqual(summary["dataset_id"], load_dataset(self.root / "dataset").manifest["dataset_id"])
        self.assertEqual((summary["requested_end"], summary["securities"]["GLD"]["first_session"]),
                         ("2024-01-04", "2024-01-03"))
        self.assertEqual({r.get_header("Authorization") for r in sent}, {"Token SECRET-1"})  # From the env file.
        for path in self.root.rglob("*"):
            if path.is_file() and path.name != ".env":
                self.assertNotIn(b"SECRET", path.read_bytes(), path)
        self.assertNotIn("SECRET", out + err)

    def test_defaults_are_the_environment_key_the_latest_final_day_and_the_plans_tickers(self):
        urls = {**URLS, prices_url("SPY", D1, D3.replace(day=10)): SPY_ROWS}  # The latest final day at AT.
        with patch("quant_core.cli.plan_tickers", return_value=("GLD", "SPY")):
            code, out, err, sent = self.download(key="SECRET-2", urls=urls, tickers=())
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((json.loads(out)["requested_end"], json.loads(out)["end"]), ("2024-01-10", "2024-01-04"))
        self.assertEqual(load_dataset(self.root / "dataset").manifest["tickers"], ["GLD", "SPY"])
        self.assertEqual({r.get_header("Authorization") for r in sent}, {"Token SECRET-2"})

    def test_env_files_written_on_windows_are_understood(self):
        for raw, key in ((b"\xef\xbb\xbfTIINGO_API_KEY=SECRET-3\r\n", "SECRET-3"),  # A byte-order mark.
                         (b"# my keys\r\nTIINGO_API_KEY=OLD\r\nTIINGO_API_KEY=SECRET-5  # newer\r\n", "SECRET-5"),
                         (b'TIINGO_API_KEY="SECRET-6" # personal key\n', "SECRET-6")):
            (self.root / ".env").write_bytes(raw)
            code, _, err, sent = self.download("--end", "2024-01-04")
            self.assertEqual((code, err), (0, ""))
            self.assertEqual({r.get_header("Authorization") for r in sent}, {"Token " + key})  # The last one wins.
            rmtree(self.root / "dataset")
            rmtree(self.root / "tiingo")
        (self.root / ".env").write_bytes("TIINGO_API_KEY=SECRET-4\n".encode("utf-16"))
        code, _, err, sent = self.download("--end", "2024-01-04")
        self.assertEqual((code, sent), (2, []))
        self.assertIn("save it as UTF-8 text", err)

    def test_exit_codes_explain_what_to_do(self):
        code, out, err, sent = self.download("--end", "2024-01-04", "--max-requests", "1")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("Download incomplete: 2 ticker(s) still to download: SPY, GLD", err)
        self.assertIn("Resume with --end 2024-01-04.", err)
        self.assertFalse((self.root / "dataset").exists())
        code, _, err, sent = self.download("--end", "2024-01-11")
        self.assertEqual((code, sent), (2, []))
        self.assertIn("--end must be on or before 2024-01-10", err)
        (self.root / "dataset").mkdir()
        (self.root / "dataset" / "snapshot.json").write_text("{}")  # Left by a failed save.
        code, _, err, sent = self.download("--end", "2024-01-04")
        self.assertEqual((code, sent), (2, []))
        self.assertIn("exists but is incomplete (no manifest.json): a save failed; delete it", err)
        (self.root / "dataset" / "notes.txt").write_text("mine")
        code, _, err, sent = self.download("--end", "2024-01-04")
        self.assertEqual((code, sent), (2, []))
        self.assertIn("already exists; datasets are never overwritten", err)
        rmtree(self.root / "dataset")
        (self.root / ".env").write_text("OTHER=1\n")
        code, _, err, sent = self.download("--end", "2024-01-04")
        self.assertEqual((code, sent), (2, []))
        self.assertIn("Set TIINGO_API_KEY in the environment or in", err)

    def test_default_tickers_are_every_ticker_the_built_in_plans_trade(self):
        self.assertEqual(plan_tickers(), ("AGG", "EFA", "GSG", "IEF", "LQD", "SPY", "VNQ", "XLB", "XLC", "XLE",
                                          "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"))


if __name__ == "__main__":
    unittest.main()
