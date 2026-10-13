"""Cash-rate series contract: lagged lookup, staleness and ACT/365 accrual."""

from datetime import date, datetime, timezone
from decimal import Context, Decimal, localcontext
import unittest

from quant_core.data.rates import CashRateSeries

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
        with self.assertRaisesRegex(ValueError, "stale for 2024-01-15"):
            rates.growth((date(2024, 1, 15), date(2024, 1, 16)))
        with self.assertRaisesRegex(ValueError, "later session"):
            rates.growth((date(2024, 1, 4), date(2024, 1, 3)))


if __name__ == "__main__":
    unittest.main()
