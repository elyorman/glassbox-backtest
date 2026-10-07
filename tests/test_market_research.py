"""Independent checks for issuer distribution import and warmup-only signals."""

from dataclasses import replace
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from quant_core.backtest import RunConfig, run_backtest
from quant_core.backtest.sources import SessionContext
from quant_core.backtest.sources import OrderSchedule, ScheduledOrder
from quant_core.data import Bar, DataMetadata, Security, Snapshot
from quant_core.execution import ExecutionProfile
from quant_core.execution import OrderRequest
from quant_core.data import Dividend, Split
from quant_core.provenance import primitive
from quant_core.strategies import StrategyConfig, build_strategy
from research.market_backtest import (SYMBOLS, SPIN_EX, SPIN_PAY, SPIN_VALUE,
    WarmupDistributionStrategy, cash_distributions, issuer_rows, parse_issuer_date)
from research.market_report import audit


def rows():
    return [{"B": a, "C": a + "-CUSIP", "D": "09/16/2016", "F": "09/26/2016",
             "G": "0.1", "H": "0.02", "I": "0.003"} for a in SYMBOLS] + [
                {"B": "XLF", "C": "XLF-CUSIP", "D": "09/19/2016", "F": "09/22/2016", "G": "0.139146"}]


class IssuerResearchTests(unittest.TestCase):
    def test_cash_includes_capital_gains_but_excludes_non_cash_share_ratio(self):
        distributions, ids, excluded = cash_distributions(rows(), date(2016, 1, 1), date(2016, 12, 31))
        self.assertEqual(len(distributions), 10)
        self.assertEqual(distributions["XLF", date(2016, 9, 16)].amount, Decimal("0.123"))
        self.assertNotIn(("XLF", SPIN_EX), distributions)
        self.assertEqual(len(excluded), 1)

    def test_missing_payment_or_duplicate_distribution_fails(self):
        for values in (rows() + [rows()[0]], [dict(r, F="") if i == 0 else r for i, r in enumerate(rows())]):
            with self.assertRaises(ValueError):
                cash_distributions(values, date(2016, 1, 1), date(2016, 12, 31))

    def test_excel_serial_and_text_dates_agree(self):
        self.assertEqual(parse_issuer_date("09/19/2016"), parse_issuer_date("42632"))

    def test_xlsx_decimal_text_is_preserved_and_formula_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.xlsx"
            for formula in ("", "<f>1+1</f>"):
                with ZipFile(path, "w") as archive:
                    archive.writestr("xl/sharedStrings.xml", '<sst><si><t> 0.1234567890123456789 </t></si></sst>')
                    archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="G1" t="s">' + formula + '<v>0</v></c></row></sheetData></worksheet>')
                if formula:
                    with self.assertRaises(ValueError):
                        list(issuer_rows(path))
                else:
                    self.assertEqual(list(issuer_rows(path)), [{"G": "0.1234567890123456789"}])

    def test_warmup_proxy_changes_signal_and_never_credits_portfolio_cash(self):
        days = (date(2016, 9, 16), SPIN_EX, SPIN_PAY, date(2016, 9, 30), date(2016, 10, 3))
        prices = (Decimal(25), Decimal(20), Decimal(20), Decimal(20), Decimal(20))
        bars = tuple(Bar("XLF", d, p, p, p, p, 10000) for d, p in zip(days, prices))
        snapshot = Snapshot(days, bars, DataMetadata("synthetic", datetime(2026, 10, 3, tzinfo=timezone.utc),
            "synthetic", True, "synthetic"), (Security("XLF", "XLF", "SYNTHETIC"),))
        recipe = StrategyConfig("synthetic_warmup", "momentum", ("XLF",), momentum_lookback=3,
                                momentum_skip=0, top_k=1, volume_lookback=1, purpose="engineering_fixture")
        execution = ExecutionProfile("0")
        base = build_strategy(snapshot, recipe, days[3], execution)
        source = WarmupDistributionStrategy(base)
        context = SessionContext(days[3], ("XLF",), Decimal(1000), Decimal(1000), (),
                                 {"XLF": bars}, {"XLF": days}, (), ())
        signal = source.orders(context).decisions[0]
        self.assertEqual(signal.score, (Decimal(20) + SPIN_VALUE) / Decimal(25) - 1)
        result = run_backtest(snapshot, source, RunConfig("1000", execution, ("XLF",), days[3], days[4]))
        self.assertEqual(result.summary.final_equity, Decimal(1000))
        self.assertFalse(result.corporate_actions)
        self.assertEqual(snapshot.actions, ())
        with self.assertRaises(ValueError):
            source.validate_run(snapshot, RunConfig("1000", execution, ("XLF",), SPIN_PAY, days[4]))
        with self.assertRaises(ValueError):
            source.orders(replace(context, as_of=SPIN_EX))

    def test_independent_report_audit_rebuilds_splits_dividends_cash_and_fills(self):
        days = tuple(date(2024, 1, i) for i in range(2, 7))
        bars = tuple(Bar("A", d, p, p, p, p, 10000) for d, p in zip(days, (100, 100, 49, 50, 51)))
        snapshot = Snapshot(days, bars, DataMetadata("synthetic", datetime(2026, 10, 3, tzinfo=timezone.utc),
            "synthetic", True, "synthetic"), (Security("A", "A", "SYNTHETIC"),),
            (Split("A", days[2], 2), Dividend("A", days[2], 1, days[4])))
        schedule = OrderSchedule((ScheduledOrder(days[0], OrderRequest("A", "buy", 2)),))
        result = run_backtest(snapshot, schedule, RunConfig("1000", ExecutionProfile("10"), ("A",)))
        payload = primitive(result)
        self.assertEqual(result.summary.final_equity, Decimal("1007.8"))
        self.assertEqual(audit(snapshot, payload), {"sessions_checked": 5, "fills_checked": 1, "status": "passed"})
        for change in ("cash", "price", "timing"):
            bad = deepcopy(payload)
            if change == "cash":
                bad["equity"][2]["cash"] = "800"
            elif change == "price":
                bad["fills"][0]["price"] = "100.2"
            else:
                bad["fills"][0]["signal_date"] = bad["fills"][0]["execution_date"]
            with self.subTest(change=change), self.assertRaises(ArithmeticError):
                audit(snapshot, bad)


if __name__ == "__main__":
    unittest.main()
