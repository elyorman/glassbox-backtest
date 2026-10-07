"""Common-warmup chronology, honest ranking and benchmark invalidation."""

from datetime import date, timedelta
from types import SimpleNamespace
import unittest

from quant_core.strategies import initial_recipes, benchmark_recipes
from research.compare_strategies import common_start, rank_candidates, valid_benchmark


class ComparisonTests(unittest.TestCase):
    def test_common_start_uses_longest_history_and_calendar_without_prices(self):
        days, day = [], date(2016, 1, 4)
        while day <= date(2017, 3, 2):
            if day.weekday() < 5:
                days.append(day)
            day += timedelta(days=1)
        data = SimpleNamespace(sessions=tuple(days))  # No prices to inspect.
        # This synthetic weekday calendar has no exchange holidays; readiness
        # occurs earlier than on the actual market calendar.
        self.assertEqual(common_start(data, initial_recipes(("A",))), date(2016, 12, 30))
        with self.assertRaises(ValueError):
            common_start(SimpleNamespace(sessions=tuple(days[:200])), initial_recipes(("A",)))

    def test_ranking_excludes_failures_benchmarks_other_windows_and_undefined_ratio(self):
        def trial(name, sharpe, cagr="0.1", **changes):
            row = dict(recipe=name, window="common_warmup", scenario="primary10", purpose="research_candidate",
                       status="completed", metrics=dict(sharpe=sharpe, cagr_calendar=cagr))
            row.update(changes)
            return row
        rows = [trial("undefined", None, "0.9"), trial("ordinary", "0.5"), trial("tie_b", "0.8"),
                trial("tie_a", "0.8"), trial("higher_cagr", "0.8", "0.2"),
                trial("failed", "9", status="failed"), trial("benchmark", "8", purpose="benchmark"),
                trial("different_window", "7", window="ten_year"), trial("different_cost", "6", scenario="cost5")]
        self.assertEqual([r["recipe"] for r in rank_candidates(rows)],
                         ["higher_cagr", "tie_a", "tie_b", "ordinary", "undefined"])

    def test_cash_is_valid_but_unfilled_or_rejected_invested_reference_is_invalid(self):
        reference, _, equal_weight, cash = benchmark_recipes(("A",), "SPY")
        empty = SimpleNamespace(fills=(), summary=SimpleNamespace(rejected_order_count=0))
        self.assertTrue(valid_benchmark(cash, empty))
        self.assertFalse(valid_benchmark(reference, empty))
        self.assertFalse(valid_benchmark(equal_weight, empty))
        filled = SimpleNamespace(fills=(SimpleNamespace(side="buy"),), summary=SimpleNamespace(rejected_order_count=0))
        self.assertTrue(valid_benchmark(reference, filled))
        filled.summary.rejected_order_count = 1
        self.assertFalse(valid_benchmark(reference, filled))


if __name__ == "__main__":
    unittest.main()
