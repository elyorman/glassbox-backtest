"""Developer commands connect original responses and portable snapshot storage."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.cli import main
from quant_core.data.storage import load_snapshot
from quant_core.data.parquet import load_parquet_snapshot
import test_data as fixtures


class DataCommandsTests(unittest.TestCase):
    def test_csv_actions_can_preserve_original_exact_split_counts(self):
        from quant_core.data.csv_source import load_actions
        with TemporaryDirectory() as folder:
            path = Path(folder)/"actions.csv"
            path.write_text("kind,security_id,session_date,ratio,amount,pay_date,new_shares,old_shares\n"
                            "Split,A,2024-01-03,,,,1,3\n")
            actions, _ = load_actions(path)
        self.assertEqual(actions[0].adjust_quantity(fixtures.Decimal(300)), 100)
        self.assertEqual((actions[0].new_shares, actions[0].old_shares), (1, 3))

    @unittest.skipUnless(find_spec("pyarrow"), "Optional PyArrow is not installed")
    def test_json_snapshot_exports_to_parquet_and_is_inspectable(self):
        with TemporaryDirectory() as folder:
            source, output = Path(folder)/"source.json", Path(folder)/"parquet"
            from quant_core.data.storage import save_snapshot
            save_snapshot(fixtures.snapshot(), source)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["export-parquet", str(source), "--output", str(output)]), 0)
                self.assertEqual(main(["inspect", str(output)]), 0)
            self.assertEqual(load_parquet_snapshot(output), fixtures.snapshot())

    def test_eodhd_response_import_keeps_raw_prices_and_incomplete_actions(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            response = root/"response.json"
            response.write_text(json.dumps([{"date":d.isoformat(), "open":100,"high":100,
                                              "low":100,"close":100,"adjusted_close":75,"volume":1000}
                                             for d in fixtures.DAYS]))
            securities = root/"securities.csv"
            securities.write_text("security_id,symbol,exchange,listed_on,delisted_on\nA,AAA,X,,\n")
            output = root/"snapshot.json"
            args = ["import-eodhd", "--response", "AAA.US="+str(response),
                    "--security-map", "AAA.US=A", "--calendar", str(fixtures.FIXTURES/"calendar.csv"),
                    "--securities", str(securities), "--retrieved-at", "2024-01-05T00:00:00+00:00",
                    "--calendar-name", "synthetic", "--universe-policy", "fixed_synthetic",
                    "--output", str(output)]
            with redirect_stdout(StringIO()):
                self.assertEqual(main(args), 0)
            data = load_snapshot(output)
            self.assertEqual(data.bars[0].close, 100)
            self.assertFalse(data.metadata.actions_complete)
            self.assertEqual(data.metadata.source, "eodhd")


if __name__ == "__main__":
    unittest.main()
