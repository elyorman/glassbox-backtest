"""Comparison portfolios on the monthly runner: fixed weights and equal weights, by hand."""

from decimal import Decimal
import unittest

from quant_core.strategies.plans import EqualWeightPlan, FixedWeightPlan
from test_monthly_plans import A27, F27, F28, J28, M27, M28, PRICES, decided, fills, fixture, run, snapshot

D = Decimal


def values(**series):
    return {asset: tuple(D(v) for v in points) for asset, points in series.items()}


class FixedWeightTests(unittest.TestCase):
    PLAN = FixedWeightPlan(name="f", universe=("A", "B"), weights=(("B", "0.4"), ("A", "0.6")),
                           purpose="benchmark")

    def test_weights_are_constant_and_a_skipped_security_stays_in_cash(self):
        targets = self.PLAN.targets(values(A=(10,), B=(20,)))
        self.assertEqual({a: t.weight for a, t in targets.items()}, {"A": D("0.6"), "B": D("0.4")})
        self.assertEqual(targets["A"].reasons, ("fixed_weight",))
        self.assertEqual({a: t.weight for a, t in self.PLAN.targets(values(A=(10,))).items()}, {"A": D("0.6")})
        self.assertEqual((self.PLAN.weights, self.PLAN.samples("A")), ((("A", D("0.6")), ("B", D("0.4"))), 1))

    def test_invalid_weights_are_refused(self):
        for weights in ((("A", "0.6"), ("B", "0.5")), (("A", "0.6"),), (("A", "0"), ("B", "0.4")),
                        (("A", "0.6"), ("C", "0.4"))):
            with self.subTest(weights=weights), self.assertRaisesRegex(ValueError, "Fixed weights must"):
                FixedWeightPlan(name="f", universe=("A", "B"), weights=weights)

    def test_sixty_forty_rebalances_monthly_through_the_engine(self):
        plan = fixture(FixedWeightPlan, universe=("A", "B"), weights=(("A", "0.6"), ("B", "0.4")))
        result = run(plan)
        # Half of $1,000 invested: Jan 28 buys floor(300 / 10) = 30 A and floor(200 / 20) = 10 B.
        # Feb 28: equity 480 + 30 x 12 + 10 x 18 = 1,020 targets floor(306 / 12) = 25 A and floor(204 / 18) = 11 B.
        # Mar 28: equity 522 + 25 x 11 + 11 x 21 = 1,028 targets floor(308.4 / 11) = 28 A and floor(205.6 / 21) = 9 B.
        self.assertEqual(fills(result), [(F27, "A", "buy", 30, 11), (F27, "B", "buy", 10, 19),
                                         (M27, "A", "sell", 5, 12), (M27, "B", "buy", 1, 18),
                                         (A27, "B", "sell", 2, 21), (A27, "A", "buy", 3, 11)])
        self.assertEqual(result.summary.final_equity, D("1028"))
        self.assertEqual(decided(result, J28)["A"].target_fraction, D("0.30"))


class EqualWeightTests(unittest.TestCase):
    def test_equal_shares_over_the_securities_that_pass_the_checks(self):
        plan = EqualWeightPlan(name="e", universe=("A", "B", "C"), purpose="benchmark")
        self.assertEqual({a: t.weight for a, t in plan.targets(values(A=(1,), B=(2,))).items()},
                         {"A": D("0.5"), "B": D("0.5")})
        self.assertEqual(plan.targets({}), {})

    def test_a_late_listing_joins_and_the_shares_are_rescaled(self):
        prices = dict(PRICES, C=(None, None, 30, 30, 30, 33, 33, 33))
        result = run(fixture(EqualWeightPlan, universe=("A", "B", "C")), snapshot(prices, listed={"C": F27}))
        self.assertEqual({a: d.target_fraction for a, d in decided(result, J28).items()},
                         {"A": D("0.25"), "B": D("0.25"), "C": 0})
        third = D(1) / 3 * D("0.5")  # A third of the invested half, rounded as the runner rounds it.
        self.assertEqual({a: d.target_fraction for a, d in decided(result, F28).items()},
                         {"A": third, "B": third, "C": third})
        self.assertEqual(decided(result, J28)["C"].reason_codes, ("outside_security_lifetime",))
        self.assertTrue(all(d.reason_codes == ("equal_weight",) for d in decided(result, M28).values()))


if __name__ == "__main__":
    unittest.main()
