"""Hand-calculated volume rules and real portfolio accounting."""
from dataclasses import replace
from decimal import Decimal as D
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from quant_core.backtest import RunConfig, run_backtest
from quant_core.data import Bar, Split
from quant_core.execution import ExecutionProfile
from quant_core.reporting import save_run, verify_run
from quant_core.features.volume import dollar_volume_percentile
from quant_core.strategies.volume import VolumeConfig, build_volume_strategy
from research.robustness_audit import audit_ledger
from test_strategies import snapshot, DAYS


def cfg(**changes):
    return VolumeConfig("volume_fixture", ("A", "B"), window_sessions=3,
                        volume_lookback=2, **changes)


def simulate(data=None, configuration=None, end=None, execution=None):
    data = data or snapshot(volumes={"A": (10, 20, 30, 30, 30, 30), "B": (10, 20, 5, 5, 5, 5)})
    configuration = configuration or cfg()
    execution = execution or ExecutionProfile("0")
    source = build_volume_strategy(data, configuration, DAYS[2], execution)
    return run_backtest(data, source, RunConfig("100000", execution, configuration.universe,
                                               DAYS[2], end or DAYS[-1]))


class VolumeFeatureTests(unittest.TestCase):
    def bars(self, values, prices=None):
        prices = prices or [10] * len(values)
        return tuple(Bar("A", day, p, p, p, p, v) for day, p, v in zip(DAYS, prices, values))

    def test_midpoint_ties_exclude_current_observation(self):
        feature = dollar_volume_percentile(self.bars([1, 2, 2, 4, 2]), DAYS[:5], 5)
        # one lower and two ties in FOUR reference observations
        self.assertEqual(feature.score, D("0.5"))
        self.assertEqual((feature.lower_count, feature.equal_count), (1, 2))

    def test_exact_window_excludes_older_bar(self):
        feature = dollar_volume_percentile(self.bars([100, 1, 2, 3]), DAYS[:4], 3)
        self.assertEqual(feature.score, 1)
        self.assertEqual(tuple(b.session for b in feature.observations), DAYS[1:4])

    def test_constant_positive_series_and_extremes(self):
        for volumes, expected in (([2, 2, 2], ".5"), ([2, 3, 1], "0"), ([2, 3, 4], "1")):
            with self.subTest(volumes=volumes):
                self.assertEqual(dollar_volume_percentile(self.bars(volumes), DAYS[:3], 3).score, D(expected))

    def test_missing_exact_session_is_not_dropped(self):
        bars = self.bars([1, 2, 3, 4])
        feature = dollar_volume_percentile((bars[0], bars[2], bars[3]), DAYS[:4], 3)
        self.assertIsNone(feature.score)
        self.assertEqual(feature.reason, "missing_history_session")

    def test_zero_volume_and_insufficient_history_are_ineligible(self):
        for volumes, expected in (([1, 0, 3], "nonpositive_volume"), ([1, 2], "insufficient_history")):
            f = dollar_volume_percentile(self.bars(volumes), DAYS[:len(volumes)], 3)
            self.assertEqual(f.reason, expected)
            self.assertIsNone(f.score)

    def test_raw_split_units_preserve_dollar_volume(self):
        f = dollar_volume_percentile(self.bars([100, 100, 200], [10, 10, 5]), DAYS[:3], 3)
        self.assertEqual(f.score, D(".5"))

    def test_future_bars_cannot_change_score(self):
        bars = self.bars([1, 2, 3, 1000])
        self.assertEqual(dollar_volume_percentile(bars, DAYS[:3], 3),
                         dollar_volume_percentile(bars[:3], DAYS[:3], 3))

    def test_invalid_window_calendar_and_mixed_security_are_rejected(self):
        for window in (0, 1, True, 2.0):
            with self.assertRaises(ValueError):
                dollar_volume_percentile(self.bars([1, 2, 3]), DAYS[:3], window)
        with self.assertRaises(ValueError):
            dollar_volume_percentile(self.bars([1, 2, 3]), DAYS[:3][::-1], 3)
        bars = list(self.bars([1, 2, 3])); bars[-1] = replace(bars[-1], security_id="B")
        with self.assertRaises(ValueError):
            dollar_volume_percentile(bars, DAYS[:3], 3)


class VolumePortfolioTests(unittest.TestCase):
    def test_direction_and_security_id_ties(self):
        data = snapshot(paths={"A": (10,) * 6, "B": (10,) * 6},
                        volumes={"A": (100, 100, 200, 200, 200, 200), "B": (100, 100, 50, 50, 50, 50)})
        for direction, expected in (("descending", "A"), ("ascending", "B")):
            result = simulate(data, cfg(top_k=1, direction=direction))
            self.assertEqual([r.security_id for r in result.signal_decisions if r.selected], [expected])
        tied = snapshot(paths={"A": (10,) * 6, "B": (10,) * 6})
        result = simulate(tied, cfg(top_k=1))
        self.assertEqual([r.security_id for r in result.signal_decisions if r.selected], ["A"])

    def test_fixed_slots_next_open_participation_and_raw_provenance(self):
        result = simulate()
        row = next(r for r in result.signal_decisions if r.security_id == "A")
        self.assertEqual(row.target_fraction, D(".19"))
        self.assertEqual(row.requested_quantity, 0)  # floor(25 shares * 1%)
        result = simulate(configuration=cfg(max_volume_participation="1"))
        buys = [f for f in result.fills if f.side == "buy"]
        self.assertTrue(buys)
        self.assertTrue(all(f.execution_date == DAYS[3] for f in buys))
        row = next(r for r in result.signal_decisions if r.security_id == "A")
        values = dict(row.features)
        self.assertEqual(values["volume_raw_close_lag0"], 120)
        self.assertEqual(values["volume_raw_shares_lag0"], 30)
        self.assertEqual(values["volume_calendar_ordinal_lag0"], 2)
        with TemporaryDirectory() as directory:
            save_run(result, Path(directory)/"run")
            self.assertEqual(audit_ledger(snapshot(volumes={"A": (10, 20, 30, 30, 30, 30),
                "B": (10, 20, 5, 5, 5, 5)}), verify_run(Path(directory)/"run"))["status"], "passed")

    def test_future_actions_and_prices_leave_prefix_decisions_unchanged(self):
        data = snapshot()
        changed = snapshot(paths={"A": (100, 110, 120, 999, 999, 999), "B": (100, 95, 90, 1, 1, 1)},
                           actions=(Split("A", DAYS[4], 2),))
        self.assertEqual(simulate(data).signal_decisions, simulate(changed).signal_decisions)

    def test_zero_volume_is_visible_ineligibility(self):
        data = snapshot(volumes={"A": (100, 0, 100, 100, 100, 100), "B": (100,) * 6})
        result = simulate(data)
        row = next(r for r in result.signal_decisions if r.security_id == "A")
        self.assertFalse(row.eligible)
        self.assertIn("nonpositive_volume", row.reason_codes)

    def test_allocation_cost_binding_and_config_validation(self):
        source = build_volume_strategy(snapshot(), cfg(), DAYS[2], ExecutionProfile("10"))
        with self.assertRaises(ValueError):
            run_backtest(snapshot(), source, RunConfig("100000", ExecutionProfile("25"), ("A", "B"), DAYS[2], DAYS[-1]))
        for values in ({"direction":"sideways"}, {"window_sessions":1}, {"top_k":True},
                       {"invested_fraction":"1.1"}, {"max_volume_participation":0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                VolumeConfig("bad", ("A", "B"), **values)
