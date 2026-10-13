"""Cash-rate series contract: lagged lookup, staleness and ACT/365 accrual."""

from datetime import date, datetime, timezone
from decimal import Context, Decimal, localcontext
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.data.rates import CashRateSeries
from quant_core.data.storage import load_cash_rates, save_cash_rates
from quant_core.provenance import content_hash

AT = datetime(2024, 1, 10, tzinfo=timezone.utc)


def series(*observations):
    return CashRateSeries("test_source", "test_3m", AT, observations)


class CashRateSeriesTests(unittest.TestCase):
    def test_rate_before_is_strictly_lagged(self):
        rates = series((date(2024, 1, 3), "0.05"), (date(2024, 1, 4), "0.06"))
        self.assertEqual(rates.rate_before(date(2024, 1, 4)), Decimal("0.05"))
        self.assertEqual(rates.rate_before(date(2024, 1, 5)), Decimal("0.06"))

    def test_missing_and_stale_rates_are_refused(self):
        rates = series((date(2024, 1, 3), "0.05"))
        with self.assertRaisesRegex(ValueError, "No test_3m observation before 2024-01-03"):
            rates.rate_before(date(2024, 1, 3))
        self.assertEqual(rates.rate_before(date(2024, 1, 13)), Decimal("0.05"))  # Ten days old.
        with self.assertRaisesRegex(ValueError, "stale for 2024-01-14"):
            rates.rate_before(date(2024, 1, 14))

    def test_accrual_is_simple_act_365(self):
        rates = series((date(2024, 1, 4), "0.05"), (date(2024, 1, 5), "0.09"))
        with localcontext(Context(prec=28)):
            # Cash held from Friday's close to Monday earns three calendar days at Thursday's rate.
            self.assertEqual(rates.accrual(Decimal("10000"), date(2024, 1, 5), date(2024, 1, 8)),
                             Decimal(1500) / 365)
        with self.assertRaisesRegex(ValueError, "later session"):
            rates.accrual(Decimal("10000"), date(2024, 1, 8), date(2024, 1, 8))

    def test_observations_are_validated(self):
        good = (date(2024, 1, 3), "0.05")
        for observations in ((), ((date(2024, 1, 3), 0.05),), ((datetime(2024, 1, 3), "0.05"),),
                             (good, good), ((date(2024, 1, 4), "0.05"), good),
                             ((date(2024, 1, 3), "-1"),), ((date(2024, 1, 3), "1.01"),), ("x",)):
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                series(*observations)
        for source, name, at in (("", "s", AT), ("s", " ", AT), ("s", "s", datetime(2024, 1, 10))):
            with self.subTest(source=source, name=name), self.assertRaises(ValueError):
                CashRateSeries(source, name, at, (good,))
        self.assertEqual(series((date(2024, 1, 3), 1)).observations, ((date(2024, 1, 3), Decimal(1)),))

    def test_growth_compounds_each_session_in_the_engine_context(self):
        rates = series((date(2024, 1, 2), "0.365"))
        sessions = (date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 8))
        with localcontext(Context(prec=3)):  # The caller's context must not round the result.
            # One day earns 0.365 / 365 = 0.001; then 1.001 earns 0.001 a day for four days.
            self.assertEqual(rates.growth(sessions), Decimal("1.005004"))
        self.assertEqual(rates.growth(sessions[:1]), Decimal(1))
        with self.assertRaisesRegex(ValueError, "at least one session"):
            rates.growth(())
        with self.assertRaisesRegex(ValueError, "stale for 2024-01-15"):
            rates.growth((date(2024, 1, 15), date(2024, 1, 16)))
        with self.assertRaisesRegex(ValueError, "later session"):
            rates.growth((date(2024, 1, 4), date(2024, 1, 3)))


class SavedRatesTests(unittest.TestCase):
    RATES = series((date(2024, 1, 3), "0.0525"), (date(2024, 1, 4), "0.053"))

    def test_saved_rates_round_trip_with_their_hash(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "rates.json"
            save_cash_rates(self.RATES, path)
            self.assertEqual(load_cash_rates(path), self.RATES)
            envelope = json.loads(path.read_text())
            self.assertEqual(envelope["rates_hash"], content_hash(self.RATES))
            with self.assertRaises(FileExistsError):
                save_cash_rates(self.RATES, path)  # A saved series is never replaced.

    def test_tampered_or_noncanonical_files_are_refused(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "rates.json"
            save_cash_rates(self.RATES, path)
            text = path.read_text()
            path.write_text(text.replace('"0.053"', '"0.054"'))
            with self.assertRaisesRegex(ValueError, "integrity hash mismatch"):
                load_cash_rates(path)
            envelope = json.loads(text)
            envelope["rates"]["observations"][1][1] = "5.3E-2"  # Same number, another spelling.
            envelope["rates_hash"] = content_hash(envelope["rates"])
            path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError, "canonical"):
                load_cash_rates(path)
            for broken in ({"rates": {}}, {**envelope, "schema_version": 2}, {**envelope, "extra": 1}):
                path.write_text(json.dumps(broken))
                with self.subTest(broken=sorted(broken)), self.assertRaises(ValueError):
                    load_cash_rates(path)
            good = json.loads(text)
            for version in (True, 1.0, "1"):
                path.write_text(json.dumps({**good, "schema_version": version}))
                with self.subTest(version=version), self.assertRaisesRegex(ValueError, "Unexpected cash rate file"):
                    load_cash_rates(path)
            good["rates"]["observations"][0].append("extra")
            good["rates_hash"] = content_hash(good["rates"])
            path.write_text(json.dumps(good))
            with self.assertRaisesRegex(ValueError, f"Cash rate file {path}: .*\\[date, rate\\] pairs of strings"):
                load_cash_rates(path)
        with self.assertRaisesRegex(ValueError, "not float"):
            series((date(2024, 1, 3), 0.05))  # The underlying reason is kept.

    def test_only_a_rate_series_can_be_saved(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Only a CashRateSeries"):
                save_cash_rates({"source": "x"}, Path(directory) / "rates.json")
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
