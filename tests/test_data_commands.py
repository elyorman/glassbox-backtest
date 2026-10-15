"""Developer commands connect original responses and portable snapshot storage."""

from contextlib import redirect_stdout
from io import StringIO
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.cli import main
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


if __name__ == "__main__":
    unittest.main()
