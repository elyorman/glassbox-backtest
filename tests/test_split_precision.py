"""Audit regressions with independently calculated split and wipeout outcomes."""

from datetime import date, datetime, timezone
from copy import deepcopy
from decimal import Decimal as D, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.analytics import paired_metrics, return_metrics, summarize_run
from quant_core.backtest import OrderSchedule, RunConfig, ScheduledOrder, run_backtest
from quant_core.data import Bar, CashDelisting, DataMetadata, Security, Snapshot, Split, snapshot_payload
from quant_core.data.adjustments import normalized_history
from quant_core.data.storage import load_snapshot, save_snapshot
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.features import signal_prices
from quant_core.risk import RiskPolicy
from quant_core.sizing import EntryIntent
from quant_core.strategies import StrategyConfig, build_strategy

DAYS = tuple(map(date.fromisoformat, ("2023-12-29", "2024-01-02", "2024-01-31", "2024-02-01")))
META = DataMetadata("synthetic", datetime(2024, 1, 6, tzinfo=timezone.utc),
                    "fixed_synthetic_universe", True, "synthetic_explicit_sessions")
FREE = ExecutionProfile("0")


def snapshot(prices=(10, 10, 10, 10), actions=(), securities=None):
    bars = tuple(Bar("A", day, p, p, p, p, 700) for day, p in zip(DAYS, prices) if p is not None)
    return Snapshot(DAYS, bars, META, securities or (Security("A", "AAA", "SYNTHETIC"),), actions)


def run(data, entries, cash="100", risk=None):
    return run_backtest(data, OrderSchedule(tuple(entries)), RunConfig(cash, FREE, risk=risk))


def request(day, side="buy", quantity="1", stop=None):
    return ScheduledOrder(day, OrderRequest("A", side, quantity, stop_price=stop))


def policy():
    return RiskPolicy(max_trade_risk="1", max_position_fraction="1", max_gross_fraction="1",
                      cash_reserve_fraction="0", max_portfolio_heat="1", volume_lookback=1,
                      max_volume_participation="1", drawdown_halt="1")


class FractionalRebalanceTests(unittest.TestCase):
    def test_whole_buy_delta_retains_split_fraction_and_reports_rounding(self):
        for price, bought, final_quantity in ((6, 0, "13.5"), (3, 1, "14.5")):
            with self.subTest(price=price):
                data = snapshot((10, 10, price, price), (Split("A", DAYS[2], "1.5"),))
                cfg = StrategyConfig("equal_weight", "equal_weight", ("A",), invested_fraction="0.95",
                                     volume_lookback=1, max_volume_participation="1")
                result = run_backtest(data, build_strategy(data, cfg, execution=FREE), RunConfig("100", FREE))
                self.assertEqual(result.fills[0].quantity, 9)
                self.assertEqual(sum((f.quantity for f in result.fills[1:] if f.side == "buy"), D(0)), bought)
                self.assertEqual(result.equity[-1].positions[0].quantity, D(final_quantity))
                decision = next(d for d in result.signal_decisions if d.session == DAYS[2])
                self.assertIn("whole_share_buy_rounding", decision.reason_codes)

    def test_fractional_rebalance_sale_is_not_rounded(self):
        data = snapshot(actions=(Split("A", DAYS[2], "1.5"),))
        cfg = StrategyConfig("equal_weight", "equal_weight", ("A",), invested_fraction="0.95", volume_lookback=1,
                             max_volume_participation="1")
        result = run_backtest(data, build_strategy(data, cfg, execution=FREE), RunConfig("100", FREE))
        self.assertEqual(result.fills[-1].side, "sell")
        self.assertEqual(result.fills[-1].quantity, D("0.5"))


class WipeoutTests(unittest.TestCase):
    def test_paired_statistics_are_null_after_valid_wipeout_without_dropping_dates(self):
        for left, right in (((0, -1, None), (0, 0, 0)), ((0, 0, 0), (0, -1, None))):
            with self.subTest(left=left):
                self.assertEqual(paired_metrics(left, right),
                                 {"sharpe_difference": None, "mean_daily_excess": None, "beta": None})
        with self.assertRaises(ValueError):
            paired_metrics((0, None), (0, 0))

    def test_mid_run_wipeout_keeps_undefined_returns_and_summarizes_total_loss(self):
        data = snapshot((10, 10, None, None), (CashDelisting("A", DAYS[2], 0),),
                        (Security("A", "AAA", "SYNTHETIC", delisted_on=DAYS[2]),))
        result = run(data, (request(DAYS[0], quantity=10),))
        self.assertEqual(tuple(s.session_return for s in result.equity), (D(0), D(0), D(-1), None))
        metrics = summarize_run(result)
        self.assertEqual(metrics["total_return"], -1)
        self.assertEqual(metrics["cagr_calendar"], -1)
        self.assertEqual(metrics["annualized_return_252"], -1)
        self.assertEqual(metrics["session_count"], 4)
        self.assertEqual(metrics["max_drawdown"], 1)
        self.assertEqual(metrics["longest_underwater_sessions"], 2)
        for name in ("volatility", "sharpe", "sortino", "calmar", "calmar_session_annualized"):
            self.assertIsNone(metrics[name], name)

    def test_undefined_returns_are_allowed_only_after_complete_loss(self):
        for values in ((None,), (0, None), (-1, None, 0), (-1, None, "0.1")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                return_metrics(values)
        self.assertEqual(return_metrics((0, -1, None, None))["total_return"], -1)


class FinalSessionRiskTests(unittest.TestCase):
    def test_valid_final_explicit_buy_and_entry_intent_expire_with_stop_audit(self):
        for item in (OrderRequest("A", "buy", 1, stop_price=9),
                     EntryIntent("A", "fixed_allocation", allocation="0.1", stop_price=9)):
            with self.subTest(item=item):
                result = run(snapshot(), (ScheduledOrder(DAYS[-1], item),), risk=policy())
                self.assertEqual(result.summary.expired_order_count, 1)
                self.assertEqual(result.summary.rejected_order_count, 0)
                self.assertEqual(result.orders[0].reason_code, "no_next_session")
                self.assertEqual(result.orders[0].adjusted_stop_price, 9)
                decision = next(d for d in result.risk_decisions if d.phase == "close")
                self.assertEqual(decision.status, "approved")
                self.assertEqual(decision.order_id, result.orders[0].order_id)
                self.assertEqual(decision.stop_price, 9)

    def test_invalid_final_buy_is_still_a_risk_rejection(self):
        result = run(snapshot(), (request(DAYS[-1]),), risk=policy())
        self.assertEqual(result.summary.rejected_order_count, 1)
        self.assertEqual(result.summary.expired_order_count, 0)
        self.assertIn("missing_protective_stop", result.orders[0].reason_code)


class ExactSplitTests(unittest.TestCase):
    def test_shared_snapshot_decoder_preserves_precision_and_rejects_noncanonical_payloads(self):
        from quant_core.data.storage import snapshot_from_payload

        for event in (Split("A", DAYS[2], "0.5"), Split("A", DAYS[2], new_shares=1, old_shares=7)):
            data = snapshot((1, 1, 7, 7), (event,))
            payload = snapshot_payload(data)
            self.assertEqual(snapshot_from_payload(payload), data)
            altered = deepcopy(payload)
            altered["bars"][0]["close"] = "1.0"
            # Valid decimal spellings remain data, never globally normalized.
            self.assertNotEqual(snapshot_from_payload(altered).dataset_hash, data.dataset_hash)
            malformed = deepcopy(payload)
            malformed["schema_version"] = 2 if payload["schema_version"] == 1 else 1
            with self.assertRaisesRegex(ValueError, "canonical"):
                snapshot_from_payload(malformed)

    def test_reverse_split_full_sale_and_pending_order_use_original_counts(self):
        event = Split("A", DAYS[2], new_shares=1, old_shares=7)
        data = snapshot((1, 1, 7, 7), (event,))
        for sell_day, sell_quantity in ((DAYS[1], 700), (DAYS[2], 100)):
            with self.subTest(sell_day=sell_day):
                result = run(data, (request(DAYS[0], quantity=700), request(sell_day, "sell", sell_quantity)), cash="700")
                self.assertEqual(result.fills[-1].quantity, 100)
                self.assertEqual(result.fills[-1].realized_pnl, 0)
                self.assertEqual(result.summary.final_equity, 700)
                self.assertEqual(result.summary.rejected_order_count, 0)

    def test_exact_counts_preserve_history_volume_and_flat_signal(self):
        data = snapshot((1, 1, 7, 7), (Split("A", DAYS[2], new_shares=1, old_shares=7),))
        history = normalized_history(data.bars, data.actions)
        self.assertEqual(history[0].close, 7)
        self.assertEqual(history[0].volume, 100)
        self.assertEqual(signal_prices(data.bars, data.actions), (D(1),) * 4)

    def test_exact_reverse_split_preserves_pending_and_held_stops_and_volume(self):
        data = snapshot((1, 1, 7, 7), (Split("A", DAYS[2], new_shares=1, old_shares=7),))
        for signal_day in (DAYS[0], DAYS[1]):
            with self.subTest(signal_day=signal_day):
                result = run(data, (request(signal_day, quantity=700, stop="0.9"),), cash="700", risk=policy())
                self.assertEqual(result.equity[-1].positions[0].quantity, 100)
                self.assertEqual(result.equity[-1].equity, 700)
                if signal_day == DAYS[1]:
                    self.assertEqual(result.orders[0].adjusted_quantity, 100)
                    self.assertEqual(result.orders[0].adjusted_stop_price, D("6.3"))
                    decision = next(d for d in result.risk_decisions if d.phase == "open")
                    self.assertEqual(decision.average_volume, 100)
                    self.assertEqual(decision.stop_price, D("6.3"))

                # The transformed held stop must trigger at 6.3, not at 0.9.
                bars = tuple(Bar(b.security_id, b.session, b.open, b.high,
                                 D("6.3") if b.session == DAYS[-1] else b.low, b.close, b.volume)
                             for b in data.bars)
                stopped = run(Snapshot(data.sessions, bars, data.metadata, data.securities, data.actions),
                              (request(signal_day, quantity=700, stop="0.9"),), cash="700", risk=policy())
                self.assertEqual(stopped.fills[-1].execution_kind, "stop_intraday")
                self.assertEqual(stopped.fills[-1].quantity, 100)
                self.assertEqual(stopped.fills[-1].price, D("6.3"))

    def test_exact_split_counts_round_trip_and_are_independent_of_caller_precision(self):
        with localcontext() as ctx:
            ctx.prec = 6
            event = Split("A", DAYS[2], new_shares=1, old_shares=7)
        data = snapshot((1, 1, 7, 7), (event,))
        self.assertEqual(snapshot_payload(data)["schema_version"], 2)
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.json"
            save_snapshot(data, path)
            self.assertEqual(load_snapshot(path), data)

    def test_invalid_or_inconsistent_exact_counts_are_rejected(self):
        for options in ({"new_shares": 1}, {"new_shares": 0, "old_shares": 7},
                        {"new_shares": 1, "old_shares": True}, {"new_shares": "1", "old_shares": 7},
                        {"ratio": "0.5", "new_shares": 1, "old_shares": 7}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                Split("A", DAYS[2], **options)

    def test_legacy_scalar_snapshot_hash_and_fields_remain_unchanged(self):
        day = date(2024, 1, 2)
        data = Snapshot((day,), (Bar("A", day, 10, 10, 10, 10, 100),), META,
                        (Security("A", "AAA", "SYNTHETIC"),), (Split("A", day, "0.5"),))
        self.assertEqual(data.dataset_hash, "e1cf2fd014087d239e9730a61f8d109bf9876c65ed74ff0c1be1c83fbe12357a")
        self.assertEqual(snapshot_payload(data)["schema_version"], 1)
        self.assertEqual(set(snapshot_payload(data)["actions"][0]), {"kind", "security_id", "session", "ratio"})
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.json"
            save_snapshot(data, path)
            self.assertEqual(load_snapshot(path), data)
