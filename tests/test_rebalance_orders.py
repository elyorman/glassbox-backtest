"""The shared whole-share rebalance order used by rule strategies and built-in plans."""

from decimal import Decimal
import unittest

from quant_core.execution import ExecutionProfile
from quant_core.strategies import rebalance_order

D = Decimal
FREE = ExecutionProfile("0")


def order(held="0", fraction="0.5", price="120", volume="1000", equity="1000", execution=FREE):
    return rebalance_order(D(equity), D(fraction), D(price) if price else None, D(held),
                           D(volume) if volume else None, D("0.01"), execution)


class RebalanceOrderTests(unittest.TestCase):
    def test_moves_holdings_to_the_whole_share_budget(self):
        # $1,000 at 50% buys floor(500 / 120) = 4 shares.
        self.assertEqual(order(), ("buy", 4, 4, ()))
        self.assertEqual(order(held="4"), ("hold", 0, 4, ()))
        self.assertEqual(order(held="6"), ("sell", 2, 4, ()))
        # A split left 1.5 shares: buy 2 whole shares, not 2.5.
        self.assertEqual(order(held="1.5"), ("buy", 2, 4, ("whole_share_buy_rounding",)))

    def test_zero_fraction_exits_fully_without_a_price(self):
        self.assertEqual(order(held="2.5", fraction="0", price=None, volume=None), ("sell", D("2.5"), 0, ()))
        self.assertEqual(order(fraction="0", price=None, volume=None), ("skip", 0, 0, ()))

    def test_buys_are_capped_at_one_percent_of_average_volume(self):
        self.assertEqual(order(volume="150"), ("buy", 1, 4, ("entry_participation_cap",)))
        self.assertEqual(order(volume="50"), ("skip", 0, 4, ("entry_participation_cap", "below_one_share")))

    def test_a_budget_below_one_share_is_a_skip_not_a_hold(self):
        self.assertEqual(order(equity="100"), ("skip", 0, 0, ("below_one_share",)))
        self.assertEqual(order(held="1", equity="100"), ("sell", 1, 0, ()))  # $50 buys no $120 share.

    def test_entry_costs_are_inside_the_budget(self):
        # 1% slippage: floor(500 / 101) = 4, not 5.
        self.assertEqual(order(price="100", execution=ExecutionProfile("100")), ("buy", 4, 4, ()))
        # A $10 order fee comes out of the budget: floor(490 / 100) = 4.
        self.assertEqual(order(price="100", execution=ExecutionProfile("0", "0", "10")), ("buy", 4, 4, ()))
        self.assertEqual(order(price="100"), ("buy", 5, 5, ()))


if __name__ == "__main__":
    unittest.main()
