"""Deflated Sharpe ratio against Bailey and Lopez de Prado's (2014) worked example and hand-worked moments."""

from decimal import Decimal
from statistics import NormalDist
import unittest

from quant_core.validation.statistics import (
    deflated_sharpe, deflated_sharpe_ratio, expected_maximum_sharpe, return_moments, sharpe_variance,
)

D = Decimal
FOUR = D("0.0001")
# The paper's example (pp.9-10): annualized Sharpe 2.5 and trial variance 1/2, with 250 returns a year.
SHARPE, VARIANCE = D("2.5") / D(250).sqrt(), D("0.5") / 250


class PaperExampleTests(unittest.TestCase):
    def test_expected_maximum_sharpe_of_100_trials(self):
        self.assertEqual(expected_maximum_sharpe(100, VARIANCE).quantize(FOUR), D("0.1132"))

    def test_deflated_sharpe_ratio_and_its_two_variants(self):
        self.assertEqual(deflated_sharpe_ratio(SHARPE, 1250, -3, 10, 100, VARIANCE).quantize(FOUR), D("0.9004"))
        self.assertEqual(deflated_sharpe_ratio(SHARPE, 1250, -3, 10, 46, VARIANCE).quantize(FOUR), D("0.9505"))
        # Normal returns (skewness 0, kurtosis 3) reach the same 0.9505 with 88 trials.
        self.assertEqual(deflated_sharpe_ratio(SHARPE, 1250, 0, 3, 88, VARIANCE).quantize(FOUR), D("0.9505"))

    def test_more_trials_or_more_variance_raise_the_bar(self):
        base = deflated_sharpe_ratio(SHARPE, 1250, -3, 10, 100, VARIANCE)
        self.assertLess(deflated_sharpe_ratio(SHARPE, 1250, -3, 10, 1000, VARIANCE), base)
        self.assertLess(deflated_sharpe_ratio(SHARPE, 1250, -3, 10, 100, VARIANCE * 2), base)
        self.assertEqual(expected_maximum_sharpe(100, 0), 0)

    def test_results_keep_twelve_decimals(self):
        # Float-derived digits beyond about 16 are noise and may differ between platforms' maths libraries.
        self.assertEqual(expected_maximum_sharpe(100, VARIANCE), D("0.113172001865"))
        self.assertEqual(deflated_sharpe_ratio(SHARPE, 1250, -3, 10, 100, VARIANCE).as_tuple().exponent, -12)

    def test_sharpe_variance_is_the_sample_variance(self):
        # Deviations -0.01, 0 and +0.01 from 0.02: (0.0001 + 0 + 0.0001) / (3 - 1).
        self.assertEqual(sharpe_variance(("0.01", "0.02", "0.03")), D("0.0001"))
        with self.assertRaisesRegex(ValueError, "at least two"):
            sharpe_variance(("0.01",))


class MomentTests(unittest.TestCase):
    def test_symmetric_returns(self):
        # Mean 0.01 and deviations -0.02, 0, +0.02: sample deviation 0.02, so Sharpe 0.5; m4 / m2^2 = 1.5.
        moments = return_moments(("-0.01", "0.01", "0.03"))
        self.assertEqual(moments, {"observations": 3, "sharpe": D("0.5"), "skewness": 0, "kurtosis": D("1.5")})

    def test_skewed_returns(self):
        # One gain in four: mean 0.0075, sample deviation 0.015, Sharpe 0.5; a quarter-probability
        # two-point distribution has skewness 2 / sqrt(3) and kurtosis 7/3.
        moments = return_moments(("0", "0", "0", "0.03"))
        self.assertEqual(moments["sharpe"], D("0.5"))
        self.assertEqual(moments["skewness"].quantize(D("1e-20")), (2 / D(3).sqrt()).quantize(D("1e-20")))
        self.assertEqual(moments["kurtosis"].quantize(D("1e-20")), (D(7) / 3).quantize(D("1e-20")))

    def test_the_combined_report_keeps_every_input(self):
        report = deflated_sharpe(("0", "0", "0", "0.03"), 10, "0.01")
        moments = return_moments(("0", "0", "0", "0.03"))
        self.assertEqual(report["deflated_sharpe_ratio"], deflated_sharpe_ratio(
            moments["sharpe"], 4, moments["skewness"], moments["kurtosis"], 10, "0.01"))
        self.assertEqual((report["trials"], report["sharpe_variance"], report["expected_maximum_sharpe"]),
                         (10, D("0.01"), expected_maximum_sharpe(10, "0.01")))
        # z is the statistic inside the normal distribution, so a reader can check the last step.
        self.assertEqual(D(repr(NormalDist().cdf(float(report["z"])))).quantize(D("1e-12")),
                         report["deflated_sharpe_ratio"])


class RefusalTests(unittest.TestCase):
    def test_invalid_inputs_are_refused(self):
        for args, message in (((SHARPE, 1250, -3, 10, 1, VARIANCE), "Trials must be an integer of at least 2"),
                              ((SHARPE, 1250, -3, 10, 2.0, VARIANCE), "Trials must be an integer"),
                              ((SHARPE, 1250, -3, 10, 100, -1), "variance cannot be negative"),
                              ((SHARPE, 1, -3, 10, 100, VARIANCE), "Observations must be"),
                              ((SHARPE, 1250, 100, 3, 100, VARIANCE), "no valid Sharpe ratio variance"),
                              ((1, 1250, 1, 1, 100, VARIANCE), "no valid Sharpe ratio variance"),  # Exactly zero.
                              ((0.1, 1250, -3, 10, 100, VARIANCE), "not float")):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, message):
                deflated_sharpe_ratio(*args)
        for returns in (("0.01",), ("0.01", "0.01")):
            with self.subTest(returns=returns), self.assertRaises(ValueError):
                return_moments(returns)


if __name__ == "__main__":
    unittest.main()
