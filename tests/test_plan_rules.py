"""The four plan rules on hand-worked month-end values, without the engine."""

from decimal import Decimal
import unittest

from quant_core.strategies.plans import (
    DualMomentumPlan, InverseVolatilityPlan, SectorRotationPlan, TrendPlan, builtin_plans,
)

D = Decimal


def values(**series):
    return {asset: tuple(D(v) for v in points) for asset, points in series.items()}


def weights(targets):
    return {asset: target.weight for asset, target in targets.items()}


class TrendRuleTests(unittest.TestCase):
    PLAN = TrendPlan(name="t", universe=("A", "B", "C"), average_months=3, purpose="engineering_fixture")

    def test_each_asset_holds_its_share_only_while_strictly_above_its_average(self):
        # Averages are all 11: A ends above, B below, C exactly on it.
        targets = self.PLAN.targets(values(A=(10, 11, 12), B=(12, 11, 10), C=(11, 11, 11)))
        self.assertEqual(weights(targets), {"A": D(1) / 3, "B": 0, "C": 0})
        self.assertEqual(targets["A"].reasons, ("above_average",))
        self.assertEqual(targets["C"].reasons, ("not_above_average",))
        self.assertEqual(targets["A"].score, D(12) / 11 - 1)
        self.assertEqual(dict(targets["A"].features), {"month_end_value": 12, "average_month_end_value": 11})
        self.assertEqual(self.PLAN.samples("A"), 3)

    def test_a_skipped_asset_leaves_its_share_in_cash(self):
        self.assertEqual(weights(self.PLAN.targets(values(A=(10, 11, 12)))), {"A": D(1) / 3})


class DualMomentumRuleTests(unittest.TestCase):
    PLAN = DualMomentumPlan(name="d", universe=("U", "N", "B"), us_stocks="U", non_us_stocks="N", bonds="B",
                            lookback_months=2, purpose="engineering_fixture")
    BILLS = (D("1.01"), D("1.01"))  # Two months at 1%: T-bills return 2.01%.

    def decide(self, us, non_us):
        return self.PLAN.targets(values(U=(100, 100, us), N=(100, 100, non_us), B=(50,)), self.BILLS)

    def test_the_stronger_stock_market_when_us_stocks_beat_t_bills(self):
        targets = self.decide(110, 120)  # US +10% beats 2.01%; non-US +20% is stronger.
        self.assertEqual(weights(targets), {"U": 0, "N": 1, "B": 0})
        self.assertEqual(targets["N"].reasons, ("us_stocks_beat_bills", "higher_lookback_return"))
        self.assertEqual(targets["U"].reasons, ("us_stocks_beat_bills", "lower_lookback_return"))
        self.assertEqual(dict(targets["U"].features), {"bill_lookback_return": D("0.0201"),
                                                      "lookback_return": D("0.10")})
        self.assertEqual(weights(self.decide(110, 105)), {"U": 1, "N": 0, "B": 0})
        self.assertEqual(weights(self.decide(110, 110)), {"U": 1, "N": 0, "B": 0})  # A tie stays in the US.

    def test_bonds_when_t_bills_match_or_beat_us_stocks_even_if_non_us_is_strong(self):
        for us in ("102.01", "101"):
            targets = self.decide(us, 150)
            self.assertEqual(weights(targets), {"U": 0, "N": 0, "B": 1})
            self.assertEqual(targets["B"].reasons, ("bills_beat_us_stocks", "bond_fallback"))
            self.assertEqual(targets["N"].reasons, ("bills_beat_us_stocks",))

    def test_cash_when_any_security_is_unavailable(self):
        targets = self.PLAN.targets(values(U=(100, 100, 110), N=(100, 100, 120)), None)
        self.assertEqual(weights(targets), {"U": 0, "N": 0})
        self.assertEqual(targets["U"].reasons, ("plan_input_unavailable",))
        self.assertEqual((self.PLAN.samples("U"), self.PLAN.samples("B")), (3, 1))
        with self.assertRaisesRegex(ValueError, "one T-bill growth factor per lookback month"):
            self.PLAN.targets(values(U=(100, 100, 110), N=(100, 100, 120), B=(50,)), self.BILLS[:1])


class SectorRotationRuleTests(unittest.TestCase):
    PLAN = SectorRotationPlan(name="s", universe=("A", "B", "C", "D"), lookback_months=3, top=2,
                              purpose="engineering_fixture")

    def test_top_ranks_by_return_skipping_the_latest_month(self):
        # 12-1 style over 3 months: compare one month ago with three months ago.
        targets = self.PLAN.targets(values(A=(100, 110, 120, 90),   # +20%; the last month's fall is skipped
                                           B=(100, 100, 110, 200),  # +10%; the last month's jump is skipped
                                           C=(100, 90, 80, 85),     # -20%
                                           D=(100, 95, 90, 95)))    # -10%
        self.assertEqual(weights(targets), {"A": D("0.5"), "B": D("0.5"), "C": 0, "D": 0})
        self.assertEqual({a: t.rank for a, t in targets.items()}, {"A": 1, "B": 2, "C": 4, "D": 3})
        self.assertEqual(targets["A"].score, D("0.2"))
        self.assertEqual(targets["D"].reasons, ("below_selection_cutoff",))

    def test_always_invested_ties_by_ticker_and_empty_slots_in_cash(self):
        self.assertEqual(weights(self.PLAN.targets(values(C=(100, 90, 80, 85), D=(100, 95, 90, 95)))),
                         {"C": D("0.5"), "D": D("0.5")})  # Both negative, still held.
        self.assertEqual(weights(self.PLAN.targets(values(B=(100, 1, 110, 1), A=(100, 1, 110, 1),
                                                          C=(100, 1, 110, 1)))),
                         {"A": D("0.5"), "B": D("0.5"), "C": 0})
        self.assertEqual(weights(self.PLAN.targets(values(A=(100, 110, 120, 90)))), {"A": D("0.5")})


class InverseVolatilityRuleTests(unittest.TestCase):
    PLAN = InverseVolatilityPlan(name="v", universe=("A", "B", "C", "Z"), volatility_months=3,
                                 purpose="engineering_fixture")
    BILLS = (D("1.02"), D("1.00"), D("1.00"))
    # Monthly returns minus T-bills: A (+12%, 0, -10%) -> (0.10, 0, -0.10), sample deviation 0.10;
    # B -> (0.20, 0, -0.20), 0.20; C -> (0.05, 0, -0.05), 0.05.
    SERIES = values(A=(100, 112, 112, "100.8"), B=(100, 122, 122, "97.6"), C=(100, 107, 107, "101.65"))

    def test_weights_are_inverse_volatility_of_excess_returns_scaled_to_one(self):
        targets = self.PLAN.targets(self.SERIES, self.BILLS)
        self.assertEqual({a: t.score for a, t in targets.items()}, {"A": D("0.1"), "B": D("0.2"), "C": D("0.05")})
        # 1/sigma = 10, 5 and 20, out of 35.
        self.assertEqual(weights(targets), {"A": D(2) / 7, "B": D(1) / 7, "C": D(4) / 7})
        self.assertEqual(targets["A"].reasons, ("inverse_volatility_weight",))

    def test_missing_or_zero_volatility_assets_share_out_their_weight(self):
        two = {a: self.SERIES[a] for a in ("A", "B")}
        self.assertEqual(weights(self.PLAN.targets(two, self.BILLS)), {"A": D(2) / 3, "B": D(1) / 3})
        flat_bills = (D("1.01"),) * 3
        series = values(A=(100, 110, 110, 99), Z=(100, 101, "102.01", "103.0301"))  # Z tracks T-bills exactly.
        targets = self.PLAN.targets(series, flat_bills)
        self.assertEqual(weights(targets), {"A": 1, "Z": 0})
        self.assertEqual((targets["Z"].qualifies, targets["Z"].reasons), (False, ("zero_volatility",)))
        with self.assertRaisesRegex(ValueError, "one T-bill growth factor per month"):
            self.PLAN.targets(two, self.BILLS[:2])


class PlanConfigurationTests(unittest.TestCase):
    def test_the_four_builtin_plans_follow_their_sources(self):
        trend, dual, sectors, inverse = builtin_plans()
        self.assertEqual((trend.RULE, trend.universe, trend.average_months),
                         ("trend", ("EFA", "GSG", "IEF", "SPY", "VNQ"), 10))
        self.assertEqual((dual.us_stocks, dual.non_us_stocks, dual.bonds, dual.lookback_months),
                         ("SPY", "EFA", "AGG", 12))
        self.assertEqual((len(sectors.universe), sectors.lookback_months, sectors.skip_months, sectors.top),
                         (11, 12, 1, 3))
        self.assertEqual((inverse.universe, inverse.volatility_months), (("GSG", "IEF", "LQD", "SPY"), 36))
        for plan in builtin_plans():
            self.assertEqual((plan.invested_fraction, plan.decision_offset, plan.volume_lookback,
                              plan.max_volume_participation, plan.purpose),
                             (D("0.95"), 0, 20, D("0.01"), "built_in_plan"))
        self.assertEqual([p.USES_BILLS for p in builtin_plans()], [False, True, False, True])

    def test_invalid_settings_are_refused(self):
        base = dict(name="t", universe=("A",), purpose="engineering_fixture")
        for changes in ({"universe": ()}, {"universe": ("A", "A")}, {"invested_fraction": "0"},
                        {"invested_fraction": "1.1"}, {"decision_offset": 3}, {"decision_offset": True},
                        {"volume_lookback": 0}, {"max_volume_participation": "0"}, {"purpose": "x"},
                        {"average_months": 1}, {"invested_fraction": 0.95}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                TrendPlan(**{**base, **changes})
        with self.assertRaises(ValueError):
            SectorRotationPlan(name="s", universe=("A",), lookback_months=3, skip_months=3)
        with self.assertRaises(ValueError):
            InverseVolatilityPlan(name="v", universe=("A",), volatility_months=1)
        with self.assertRaisesRegex(ValueError, "distinct US stock"):
            DualMomentumPlan(name="d", universe=("U", "N", "X"), us_stocks="U", non_us_stocks="N", bonds="B")


if __name__ == "__main__":
    unittest.main()
