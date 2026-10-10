"""Provider back-adjusted closes cross-check declared splits and dividends."""

from datetime import date
from decimal import Decimal
import unittest

from quant_core.data import Dividend, Split
from quant_core.data.adjustments import provider_adjustment_disagreements

D1, D2 = date(2024, 1, 2), date(2024, 1, 3)


def observations(*rows):
    return tuple((day, Decimal(raw), Decimal(adjusted)) for day, raw, adjusted in rows)


class ProviderAdjustmentTests(unittest.TestCase):
    def test_declared_split_explains_provider_adjustment(self):
        rows = observations((D1, "100", "50"), (D2, "50.5", "50.5"))
        split = Split("A", D2, new_shares=2, old_shares=1)
        self.assertEqual(provider_adjustment_disagreements(rows, (split,)), ())

    def test_unrecorded_split_with_ordinary_gap_is_reported(self):
        rows = observations((D1, "100", "50"), (D2, "50.5", "50.5"))
        (found,) = provider_adjustment_disagreements(rows, ())
        self.assertEqual((found.session, found.implied_factor, found.expected_factor),
                         (D2, Decimal("0.5"), Decimal("1")))

    def test_genuine_large_move_is_not_an_adjustment(self):
        rows = observations((D1, "150", "150"), (D2, "100", "100"))
        self.assertEqual(provider_adjustment_disagreements(rows, ()), ())

    def test_cash_dividend_factor_uses_previous_close(self):
        rows = observations((D1, "100", "98"), (D2, "99", "99"))
        self.assertEqual(provider_adjustment_disagreements(rows, (Dividend("A", D2, "2", D2),)), ())
        (found,) = provider_adjustment_disagreements(rows, ())
        self.assertEqual(found.implied_factor, Decimal("0.98"))

    def test_same_day_split_then_post_split_dividend(self):
        rows = observations((D1, "200", "99"), (D2, "99", "99"))
        actions = (Split("A", D2, new_shares=2, old_shares=1), Dividend("A", D2, "1", D2))
        self.assertEqual(provider_adjustment_disagreements(rows, actions), ())

    def test_provider_rounding_of_small_adjusted_values_is_allowed(self):
        rows = observations((D1, "100", "0.0050"), (D2, "100", "0.0051"))
        self.assertEqual(provider_adjustment_disagreements(rows, ()), ())

    def test_invalid_observations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "ascending"):
            provider_adjustment_disagreements(observations((D2, "1", "1"), (D1, "1", "1")), ())
        with self.assertRaisesRegex(ValueError, "positive"):
            provider_adjustment_disagreements(observations((D1, "1", "0")), ())


if __name__ == "__main__":
    unittest.main()
