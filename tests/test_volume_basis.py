"""Split-adjusted provider volume must never reach raw-share liquidity rules."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import test_universe_strategy as dated
from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.data import RAW_PRICES_SPLIT_ADJUSTED_VOLUME, SPLIT_ADJUSTED_VOLUME_LIMITATION
from quant_core.data.eodhd import EodhdJsonSource
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.risk import RiskPolicy
from quant_core.strategies import build_strategy
from quant_core.strategies.volume import VolumeConfig, build_volume_strategy


def adjusted(snapshot):
    return replace(snapshot, metadata=replace(snapshot.metadata, adjustment_policy=RAW_PRICES_SPLIT_ADJUSTED_VOLUME))


class VolumeBasisTests(unittest.TestCase):
    def test_rule_strategy_refuses_split_adjusted_volume(self):
        data, members, recipe = dated.fixture()
        data, execution = adjusted(data), ExecutionProfile("0")
        source = build_strategy(data, recipe, execution=execution, membership=members)
        with self.assertRaisesRegex(ValueError, "Strategy liquidity rules: raw share volume required"):
            run_backtest(data, source, RunConfig("1000", execution, recipe.universe))

    def test_risk_enabled_run_refuses_split_adjusted_volume(self):
        data, _, _ = dated.fixture()
        with self.assertRaisesRegex(ValueError, "Risk liquidity limits: raw share volume required"):
            run_backtest(adjusted(data), OrderSchedule(()), RunConfig("1000", ExecutionProfile("0"), risk=RiskPolicy()))

    def test_explicit_orders_without_liquidity_rules_still_run(self):
        data, _, _ = dated.fixture()
        orders = OrderSchedule((ScheduledOrder(data.sessions[0], OrderRequest("A", "buy", 1)),))
        result = run_backtest(adjusted(data), orders, RunConfig("1000", ExecutionProfile("0")))
        self.assertEqual([(f.security_id, f.quantity) for f in result.fills], [("A", 1)])

    def test_volume_strategy_refuses_split_adjusted_volume(self):
        data, _, _ = dated.fixture()
        data, execution = adjusted(data), ExecutionProfile("0")
        config = VolumeConfig("volume_probe", ("A", "B"), window_sessions=2, top_k=1, volume_lookback=1)
        with self.assertRaisesRegex(ValueError, "Strategy liquidity rules: raw share volume required"):
            run_backtest(data, build_volume_strategy(data, config, execution=execution),
                         RunConfig("1000", execution, ("A", "B")))

    def test_pre_label_eodhd_snapshot_is_refused_by_its_limitation(self):
        data, members, recipe = dated.fixture()
        legacy = replace(data, metadata=replace(data.metadata, limitations=(SPLIT_ADJUSTED_VOLUME_LIMITATION,)))
        execution = ExecutionProfile("0")
        with self.assertRaisesRegex(ValueError, r"EODHD import before 0\.5\.2"):
            run_backtest(legacy, build_strategy(legacy, recipe, execution=execution, membership=members),
                         RunConfig("1000", execution, recipe.universe))

    def test_volume_basis_survives_json_storage(self):
        data, _, _ = dated.fixture()
        with TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            save_snapshot(adjusted(data), path)
            loaded = load_snapshot(path)
        self.assertEqual(loaded.metadata.adjustment_policy, RAW_PRICES_SPLIT_ADJUSTED_VOLUME)
        self.assertEqual(loaded.dataset_hash, adjusted(data).dataset_hash)

    def test_eodhd_import_labels_volume_basis_and_strategy_refuses_it(self):
        data, members, recipe = dated.fixture()
        responses = {asset + ".US": json.dumps([{"date": b.session.isoformat(), "open": str(b.open),
                                                  "high": str(b.high), "low": str(b.low), "close": str(b.close),
                                                  "volume": int(b.volume)} for b in data.bars
                                                 if b.security_id == asset]).encode()
                     for asset in recipe.universe}
        imported = EodhdJsonSource(responses, {a + ".US": a for a in recipe.universe}, data.sessions,
                                   data.securities, replace(data.metadata, source="eodhd", actions_complete=False)).load()
        self.assertEqual(imported.metadata.adjustment_policy, RAW_PRICES_SPLIT_ADJUSTED_VOLUME)
        execution = ExecutionProfile("0")
        with self.assertRaisesRegex(ValueError, "raw share volume required"):
            run_backtest(imported, build_strategy(imported, recipe, execution=execution, membership=members),
                         RunConfig("1000", execution, recipe.universe, actions_policy="allow_incomplete_diagnostic"))


if __name__ == "__main__":
    unittest.main()
