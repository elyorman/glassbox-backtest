"""Split-adjusted provider volume must never reach raw-share liquidity rules."""

from dataclasses import replace
import json
import unittest

import test_universe_strategy as dated
from quant_core.backtest import OrderSchedule, RunConfig, run_backtest
from quant_core.data import RAW_PRICES_SPLIT_ADJUSTED_VOLUME
from quant_core.data.eodhd import EodhdJsonSource
from quant_core.execution import ExecutionProfile
from quant_core.risk import RiskPolicy
from quant_core.strategies import build_strategy


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
        result = run_backtest(adjusted(data), OrderSchedule(()), RunConfig("1000", ExecutionProfile("0")))
        self.assertEqual(result.summary.final_equity, 1000)

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
