"""Provider back-adjusted closes cross-check declared splits and dividends."""

from datetime import date
from decimal import Decimal
import unittest

from quant_core.data import CashDelisting, Dividend, Split
from quant_core.data.adjustments import provider_adjustment_disagreements

D1, D2, D3 = date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)
TWO_FOR_ONE = Split("A", D2, new_shares=2, old_shares=1)


def observations(*rows):
    return tuple((day, Decimal(raw), Decimal(adjusted)) for day, raw, adjusted in rows)


class ProviderAdjustmentTests(unittest.TestCase):
    def test_declared_split_explains_provider_adjustment(self):
        rows = observations((D1, "100", "50"), (D2, "50.5", "50.5"))
        self.assertEqual(provider_adjustment_disagreements(rows, (TWO_FOR_ONE,), tolerance="0"), ())

    def test_unrecorded_split_with_ordinary_gap_is_reported(self):
        rows = observations((D1, "100", "50"), (D2, "50.5", "50.5"))
        (found,) = provider_adjustment_disagreements(rows, ())
        self.assertEqual((found.previous_session, found.session, found.implied_factor,
                          found.expected_factor, found.reason),
                         (D1, D2, Decimal("0.5"), Decimal("1"), "factor_mismatch"))

    def test_declared_split_the_provider_never_applied_is_reported(self):
        rows = observations((D1, "100", "100"), (D2, "50", "50"))
        (found,) = provider_adjustment_disagreements(rows, (TWO_FOR_ONE,))
        self.assertEqual((found.implied_factor, found.expected_factor), (Decimal("1"), Decimal("0.5")))

    def test_reverse_split(self):
        rows = observations((D1, "2", "20"), (D2, "20.4", "20.4"))
        reverse = Split("A", D2, new_shares=1, old_shares=10)
        self.assertEqual(provider_adjustment_disagreements(rows, (reverse,), tolerance="0"), ())
        self.assertEqual(len(provider_adjustment_disagreements(rows, ())), 1)

    def test_genuine_large_move_is_not_an_adjustment(self):
        rows = observations((D1, "150", "150"), (D2, "100", "100"))
        self.assertEqual(provider_adjustment_disagreements(rows, (), tolerance="0"), ())

    def test_cash_dividend_factor_uses_previous_close(self):
        rows = observations((D1, "100", "98"), (D2, "90", "90"))
        dividend = Dividend("A", D2, "2", D2)
        self.assertEqual(provider_adjustment_disagreements(rows, (dividend,), tolerance="0"), ())
        (omitted,) = provider_adjustment_disagreements(rows, (), tolerance="0")
        self.assertEqual(omitted.implied_factor, Decimal("0.98"))

    def test_same_day_split_then_post_split_dividend(self):
        rows = observations((D1, "200", "99"), (D2, "99", "99"))
        dividend = Dividend("A", D2, "1", D2)
        self.assertEqual(provider_adjustment_disagreements(rows, (dividend, TWO_FOR_ONE), tolerance="0"), ())
        self.assertEqual(len(provider_adjustment_disagreements(rows, (TWO_FOR_ONE,), tolerance="0")), 1)

    def test_actions_across_a_missing_bar_combine_in_date_order(self):
        rows = observations((D1, "100", "49"), (D3, "50", "50"))
        actions = (Dividend("A", D3, "1", D3), TWO_FOR_ONE, CashDelisting("A", D3, "0"))
        self.assertEqual(provider_adjustment_disagreements(rows, actions, tolerance="0"), ())

    def test_dividend_exhausting_the_previous_close_is_reported(self):
        rows = observations((D1, "2", "1"), (D2, "1", "1"))
        (found,) = provider_adjustment_disagreements(rows, (Dividend("A", D2, "2", D2),))
        self.assertEqual((found.expected_factor, found.reason), (Decimal("0"), "factor_mismatch"))

    def test_rounding_unit_comes_from_the_finest_printed_digit(self):
        rows = observations((D1, "100", "50.5"), (D2, "100", "50.5253"))
        self.assertEqual(len(provider_adjustment_disagreements(rows, (), tolerance="0")), 1)

    def test_small_adjusted_values_within_rounding_are_accepted(self):
        rows = observations((D1, "100", "0.0050"), (D2, "100", "0.0051"))
        self.assertEqual(provider_adjustment_disagreements(rows, ()), ())

    def test_imprecise_tiny_adjusted_values_are_reported_not_trusted(self):
        rows = observations((D1, "100", "0.0002"), (D2, "50", "0.0002"))
        (found,) = provider_adjustment_disagreements(rows, ())
        self.assertEqual(found.reason, "insufficient_precision")

    def test_integer_inputs_are_exact(self):
        rows = ((D1, 100, 50), (D2, 50, 50))
        self.assertEqual(provider_adjustment_disagreements(rows, (TWO_FOR_ONE,), tolerance="0"), ())

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "ascending"):
            provider_adjustment_disagreements(observations((D2, "1", "1"), (D1, "1", "1")), ())
        with self.assertRaisesRegex(ValueError, "positive"):
            provider_adjustment_disagreements(observations((D1, "1", "0")), ())
        with self.assertRaisesRegex(ValueError, "negative"):
            provider_adjustment_disagreements((), (), tolerance="-0.01")
        with self.assertRaises(ValueError):
            provider_adjustment_disagreements(((D1, 100.0, 50.0),), ())


if __name__ == "__main__":
    unittest.main()
