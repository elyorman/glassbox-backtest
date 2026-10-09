"""Dated members constrain decisions, rather than relabeling a static universe."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from importlib.util import find_spec
import json
from tempfile import TemporaryDirectory
import unittest

from quant_core.backtest import RunConfig, run_backtest
from quant_core.data import Bar, DataMetadata, Security, Snapshot
from quant_core.execution import ExecutionProfile
from quant_core.provenance import primitive
from quant_core.reporting import save_run, verify_run
from quant_core.strategies import StrategyConfig, build_strategy
from quant_core.universes import DatedUniverse, MembershipInterval


def fixture():
    days = tuple(date(2024, 1, 25) + timedelta(days=i) for i in range(41)
                 if (date(2024, 1, 25) + timedelta(days=i)).weekday() < 5)
    snapshot = Snapshot(days, tuple(Bar(a, d, p, p, p, p, 100000)
                                   for a, p in (("A", "100"), ("B", "50")) for d in days),
                        DataMetadata("synthetic", datetime(2024, 4, 1, tzinfo=timezone.utc),
                                     "dated_synthetic", True, "synthetic_weekdays"),
                        (Security("A", "A", "X"), Security("B", "B", "X")))
    members = DatedUniverse("example", days[0], days[-1],
                           (MembershipInterval("A", days[0], days[0], date(2024, 2, 20), date(2024, 2, 19)),
                            MembershipInterval("B", date(2024, 2, 20), date(2024, 2, 19))),
                           "synthetic", datetime(2024, 4, 1, tzinfo=timezone.utc), days[0])
    recipe = StrategyConfig("dated_equal", "equal_weight", ("A", "B"), invested_fraction="1",
                            volume_lookback=1, max_volume_participation="1", purpose="engineering_fixture")
    return snapshot, members, recipe


class UniverseStrategyTests(unittest.TestCase):
    @unittest.skipUnless(find_spec("pyarrow"), "Optional PyArrow is not installed")
    def test_provider_response_roundtrips_and_raw_volume_portfolio_runs_from_parquet(self):
        from quant_core.data import RAW_PRICES_SPLIT_ADJUSTED_VOLUME
        from quant_core.data.eodhd import EodhdJsonSource
        from quant_core.data.parquet import save_parquet_snapshot, load_parquet_snapshot
        data, members, recipe = fixture()
        responses = {asset+".US": json.dumps([{"date":b.session.isoformat(), "open":str(b.open),
                                                "high":str(b.high), "low":str(b.low), "close":str(b.close),
                                                "volume":int(b.volume)} for b in data.bars if b.security_id == asset]).encode()
                     for asset in recipe.universe}
        imported = EodhdJsonSource(responses, {a+".US":a for a in recipe.universe}, data.sessions,
                                  data.securities, replace(data.metadata, source="eodhd", actions_complete=False)).load()
        with TemporaryDirectory() as folder:
            save_parquet_snapshot(imported, Path(folder)/"provider")
            save_parquet_snapshot(data, Path(folder)/"raw")
            provider = load_parquet_snapshot(Path(folder)/"provider")
            raw = load_parquet_snapshot(Path(folder)/"raw")
        self.assertEqual(provider.dataset_hash, imported.dataset_hash)
        self.assertEqual(provider.metadata.adjustment_policy, RAW_PRICES_SPLIT_ADJUSTED_VOLUME)
        execution = ExecutionProfile("0")
        with self.assertRaisesRegex(ValueError, "raw share volume required"):
            run_backtest(provider, build_strategy(provider, recipe, execution=execution, membership=members),
                         RunConfig("1000", execution, recipe.universe, actions_policy="allow_incomplete_diagnostic"))
        result = run_backtest(raw, build_strategy(raw, recipe, execution=execution, membership=members),
                              RunConfig("1000", execution, recipe.universe))
        self.assertEqual([f.security_id for f in result.fills], ["A", "A", "B"])
        self.assertEqual(result.summary.final_equity, 1000)

    def test_member_removal_exits_and_new_member_enters_at_scheduled_rebalance(self):
        data, members, recipe = fixture()
        execution = ExecutionProfile("0")
        source = build_strategy(data, recipe, execution=execution, membership=members)
        result = run_backtest(data, source, RunConfig("1000", execution, recipe.universe))
        self.assertEqual([(f.execution_date, f.security_id, f.side, f.quantity) for f in result.fills],
                         [(date(2024, 2, 1), "A", "buy", 10),
                          (date(2024, 3, 1), "A", "sell", 10),
                          (date(2024, 3, 1), "B", "buy", 20)])
        excluded = next(s for s in result.signal_decisions
                        if s.session == date(2024, 1, 31) and s.security_id == "B")
        self.assertFalse(excluded.eligible)
        self.assertIn("outside_dated_universe", excluded.reason_codes)
        self.assertEqual(result.summary.final_equity, 1000)
        with TemporaryDirectory() as root:
            save_run(result, Path(root)/"run")
            payload = verify_run(Path(root)/"run")
        self.assertEqual(payload["manifest"]["source"]["membership"], primitive(members))

    def test_future_membership_change_does_not_change_earlier_decisions(self):
        data, members, recipe = fixture()
        changed = replace(members, intervals=(replace(members.intervals[0], left_on=date(2024, 2, 27)),
                                               replace(members.intervals[1], entered_on=date(2024, 2, 27))))
        execution = ExecutionProfile("0")
        results = [run_backtest(data, build_strategy(data, recipe, execution=execution, membership=m),
                               RunConfig("1000", execution, recipe.universe)) for m in (members, changed)]
        decisions = [tuple(s for s in r.signal_decisions if s.session < date(2024, 2, 20)) for r in results]
        self.assertEqual(decisions[0], decisions[1])
        self.assertNotEqual(results[0].manifest.source.artifact_hash, results[1].manifest.source.artifact_hash)

    def test_unknown_membership_coverage_blocks_run(self):
        data, members, recipe = fixture()
        source = build_strategy(data, recipe, membership=replace(members, coverage_end=date(2024, 2, 1)))
        with self.assertRaisesRegex(ValueError, "coverage"):
            run_backtest(data, source, RunConfig("1000", ExecutionProfile(), recipe.universe))

    def test_membership_unknown_security_is_rejected(self):
        data, members, recipe = fixture()
        unknown = replace(members, intervals=members.intervals +
                          (MembershipInterval("X", data.sessions[0], data.sessions[0]),))
        with self.assertRaisesRegex(ValueError, "security|universe"):
            build_strategy(data, recipe, membership=unknown)


if __name__ == "__main__":
    unittest.main()
