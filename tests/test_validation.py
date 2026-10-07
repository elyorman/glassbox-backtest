"""Independent financial examples, chronology checks and campaign state transitions."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, ROUND_DOWN, localcontext
from io import StringIO
import json
import csv
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_core.analytics import paired_metrics, return_metrics, summarize_run
from quant_core.backtest.contracts import RunConfig
from quant_core.backtest.engine import run_backtest
from quant_core.backtest.sources import OrderSchedule, ScheduledOrder
from quant_core.data import Bar, CashDelisting, DataMetadata, Dividend, Security, Snapshot, Split
from quant_core.data.storage import save_snapshot
from quant_core.execution import ExecutionProfile, OrderRequest
from quant_core.provenance import canonical_json, content_hash, primitive
from quant_core.strategies import StrategyConfig, benchmark_recipes
from quant_core.validation.campaign import (
    _nomination, bounded_snapshot, crosscheck, nominate, open_campaign, register_campaign, run_final, run_phase, verify_campaign,
)
from quant_core.validation.cli import main
from quant_core.validation.contracts import (
    CAPABILITIES, CampaignSpec, Capability, Criteria, Qualification, load_document, parse_spec,
)
from quant_core.validation.registry import Registry, publish
from quant_core.validation.statistics import fold_score_bootstrap, paired_bootstrap, search_diagnostic, stationary_indices
from quant_core.validation.temporal import LabelInterval, Period, past_training_samples


def fixture():
    days, day = [], date(2023, 1, 2)
    while len(days) < 90:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    bars = []
    for asset in ("A", "B", "SPY"):
        previous = D(100)
        for i, day in enumerate(days):
            close = D(100) + D(i) / 2 + D((i % 7) - 3) if asset == "A" else D(100) + D(i % 5) / 10 if asset == "B" else D(100) + D(i) / 4
            bars.append(Bar(asset, day, previous, max(previous, close) + 1, min(previous, close) - 1, close, 100000))
            previous = close
    meta = DataMetadata("synthetic_validation_fixture", datetime(2026, 10, 3, tzinfo=timezone.utc),
                        "fixed_engineering_sample", True, "synthetic_weekdays_not_exchange_calendar",
                        limitations=("Synthetic accounting/validation fixture, not performance evidence",))
    data = Snapshot(days, tuple(bars), meta, tuple(Security(a, a, "SYNTHETIC") for a in ("A", "B", "SPY")))
    recipes = (StrategyConfig("trend3", "trend", ("A", "B"), mean_window=3, volume_lookback=1,
                              max_volume_participation="1", purpose="engineering_fixture"),
               StrategyConfig("momentum3", "momentum", ("A", "B"), momentum_lookback=3, momentum_skip=1,
                              top_k=1, volume_lookback=1, max_volume_participation="1", purpose="engineering_fixture"))
    benchmarks = tuple(replace(c, volume_lookback=1, max_volume_participation=D(1)) for c in benchmark_recipes(("A", "B"), "SPY"))
    spec = CampaignSpec("synthetic_validation_v1", "Verify chronology and reporting; no alpha hypothesis",
                        data.dataset_hash, recipes, benchmarks,
                        (Period("fold1", days[5], days[19]), Period("fold2", days[20], days[34])),
                        Period("selection", days[35], days[59]), Period("holdout", days[60], days[89]),
                        criteria=Criteria(minimum_sessions=10, removed_winner_sessions=2),
                        bootstrap_blocks=(2, 5), bootstrap_repetitions=100, purpose="engineering_fixture",
                        initial_cash="10000")
    qualification = Qualification(data.dataset_hash, "engineering_fixture", "synthetic_fixture_author",
                                  date(2026, 10, 3), tuple(Capability(c, "passed", "Constructed synthetic fixture; no provider qualification")
                                                        for c in CAPABILITIES),
                                  ("Synthetic surviving sample and known daily execution approximation",))
    return data, spec, qualification


class MetricsTests(unittest.TestCase):
    def test_hand_calculated_compounding_drawdown_and_sample_variance(self):
        values = return_metrics(("0.1", "-0.1"))
        self.assertEqual(values["total_return"], D("-0.01"))
        self.assertEqual(values["max_drawdown"], D("0.1"))
        self.assertEqual(values["longest_underwater_sessions"], 1)
        self.assertEqual(values["volatility"], D("5.04").sqrt())
        self.assertEqual(values["sharpe"], 0)
        self.assertEqual(values["sortino"], 0)

    def test_initial_loss_peak_recovery_and_terminal_bankruptcy(self):
        values = return_metrics(("-0.2", "0.25", "0", "-1"))
        self.assertEqual(values["total_return"], -1)
        self.assertEqual(values["max_drawdown"], 1)
        self.assertEqual(values["longest_underwater_sessions"], 1)

    def test_zero_variance_ratios_are_null_even_for_positive_returns(self):
        for values in ((0, 0), ("0.01", "0.01"), (0,)):
            self.assertIsNone(return_metrics(values)["sharpe"])
        self.assertIsNone(return_metrics((0, 0))["sortino"])
        self.assertIsNone(return_metrics((0, 0))["calmar_session_annualized"])
        self.assertIsNone(paired_metrics((0, 0), (0, 0))["beta"])

    def test_metrics_reject_float_bad_returns_and_unpaired_data(self):
        for values in ((), (0.1,), ("-1.01",), ("NaN",)):
            with self.assertRaises(ValueError):
                return_metrics(values)
        with self.assertRaises(ValueError):
            paired_metrics((0, 1), (0,))

    def test_beta_and_identical_benchmark_sharpe_difference(self):
        values = (D("0.01"), D("-0.02"), D("0.03"), D("0.005"))
        metrics = paired_metrics(values, values)
        self.assertEqual(metrics["beta"], 1)
        self.assertEqual(metrics["sharpe_difference"], 0)
        self.assertEqual(metrics["mean_daily_excess"], 0)

    def test_fresh_decimal_context_produces_same_values(self):
        original = return_metrics(("0.1", "-0.1", "0.02"))
        with localcontext() as context:
            context.prec, context.rounding = 6, ROUND_DOWN
            self.assertEqual(return_metrics(("0.1", "-0.1", "0.02")), original)

    def test_asset_pnl_reconciles_fees_dividends_split_and_delisting(self):
        data, _, _ = fixture()
        days = data.sessions[:6]
        data = replace(data, sessions=days, securities=(Security("A", "A", "SYN", delisted_on=days[5]),),
                       bars=tuple(Bar("A", day, p, p, p, p, 10000) for day, p in zip(days[:5], (100, 100, 49, 50, 50))),
                       actions=(Split("A", days[2], 2), Dividend("A", days[2], 1, days[5]), CashDelisting("A", days[5], 55)))
        schedule = OrderSchedule((ScheduledOrder(days[0], OrderRequest("A", "buy", 2)),))
        result = run_backtest(data, schedule, RunConfig("1000", ExecutionProfile("0", fee_per_order="1")))
        summary = summarize_run(result)
        # Two shares cost 201; split to four; dividend 4; terminal cash 220 => P&L23.
        self.assertEqual(result.summary.final_equity, 1023)
        self.assertEqual(summary["asset_pnl"], {"A": D(23)})
        self.assertEqual(summary["notional_turnover"], D(200) / 999)
        self.assertEqual(summary["sale_fill_count"], 0)  # Cash settlement is not a market-sale fill.
        self.assertEqual(summary["calendar_days_inclusive"], 8)
        self.assertEqual(summary["cagr_calendar"], (D(1023) / 1000) ** (D("365.2425") / 8) - 1)
        self.assertEqual(summary["calmar"], summary["cagr_calendar"] / summary["max_drawdown"])

    def test_unheld_benchmark_dividend_audit_does_not_break_candidate_metrics(self):
        data, _, _ = fixture()
        data = replace(data, actions=(Dividend("SPY", data.sessions[2], 1, data.sessions[4]),))
        schedule = OrderSchedule((ScheduledOrder(data.sessions[0], OrderRequest("A", "buy", 2)),))
        result = run_backtest(data, schedule, RunConfig("1000", ExecutionProfile("0"), ("A",)))
        self.assertTrue(any(a.security_id == "SPY" and a.amount == 0 for a in result.corporate_actions))
        metrics = summarize_run(result)
        self.assertEqual(set(metrics["asset_pnl"]), {"A"})
        self.assertEqual(metrics["asset_pnl"]["A"], result.summary.final_equity - 1000)
        bad = replace(result, corporate_actions=tuple(
            replace(a, amount=D(1)) if a.security_id == "SPY" and a.kind == "dividend_entitlement" else a
            for a in result.corporate_actions))
        with self.assertRaises(ArithmeticError):
            summarize_run(bad)


class StatisticalTests(unittest.TestCase):
    def test_identical_procedures_have_zero_median_fold_score_difference(self):
        values = ("0.01", "-0.02", "0.005", "0", "0.03", "-0.01") * 3
        folds = (tuple(range(9)), tuple(range(9, 18)))
        result = fold_score_bootstrap(values, values, values, folds, 3, 100, 42)
        self.assertEqual(result["median_fold_score_difference_95"], (0, 0))
        with self.assertRaises(ValueError):
            fold_score_bootstrap(values, values, values, ((0, 1), (1, 2)), 1, 100, 42)

    def test_paired_resampling_identical_series_has_zero_advantage(self):
        values = ("0.01", "-0.02", "0.005", "0", "0.03", "-0.01") * 3
        result = paired_bootstrap(values, values, 3, 100, 42)
        self.assertEqual(result["mean_excess_95"], (0, 0))
        self.assertEqual(result["sharpe_difference_95"], (0, 0))
        self.assertEqual(result, paired_bootstrap(values, values, 3, 100, 42))

    def test_stationary_samples_valid_contiguous_indices_and_reproducible_seed(self):
        first = stationary_indices(30, 5, Random(42))
        self.assertEqual(len(first), 30)
        self.assertTrue(all(0 <= i < 30 for i in first))
        self.assertEqual(first, stationary_indices(30, 5, Random(42)))
        self.assertTrue(any(b == (a + 1) % 30 for a, b in zip(first, first[1:])))

    def test_search_diagnostic_identical_returns_is_one_not_false_significance(self):
        result = search_diagnostic(((0,) * 10,) * 3, (0,) * 10, 2, 100, 42)
        self.assertEqual(result["p_value"], 1)
        self.assertEqual(result["candidate_count"], 3)

    def test_search_diagnostic_centered_constant_edge_has_declared_finite_sample_floor(self):
        result = search_diagnostic((("0.01",) * 10, ("-0.01",) * 10), (0,) * 10, 2, 100, 42)
        self.assertEqual(result["p_value"], D(1) / 101)
        self.assertEqual(result["maximum_mean_excess"], D("0.01"))

    def test_invalid_settings_undefined_sharpe_and_complete_panel_requirement(self):
        undefined = paired_bootstrap((0,) * 10, (0,) * 10, 2, 100, 0)
        self.assertEqual(undefined["defined_sharpe_replicates"], 0)
        self.assertEqual(undefined["sharpe_difference_95"], (None, None))
        for kwargs in ({"block": 11}, {"repetitions": 99}, {"seed": True}):
            with self.assertRaises(ValueError):
                paired_bootstrap((0,) * 10, (0,) * 10, **kwargs)
        with self.assertRaises(ValueError):
            search_diagnostic(((0, 1), (0,)), (0, 1), 1, 100, 0)


class TemporalTests(unittest.TestCase):
    def test_panel_labels_are_purged_by_end_timestamp_not_symbol_row_gap(self):
        data, _, _ = fixture()
        days = data.sessions
        labels = (LabelInterval("A", days[0], days[1], days[5]),
                  LabelInterval("B", days[0], days[1], days[5]),
                  LabelInterval("A", days[2], days[3], days[6]),
                  LabelInterval("A", days[3], days[4], days[7]))
        self.assertEqual(past_training_samples(labels, days[5], days[6]), labels[:2])

    def test_fit_at_or_after_evaluation_and_invalid_intervals_reject(self):
        data, _, _ = fixture()
        days = data.sessions
        with self.assertRaises(ValueError):
            past_training_samples((), days[1], days[1])
        with self.assertRaises(ValueError):
            LabelInterval("A", days[0], days[0], days[1])
        item = LabelInterval("A", days[0], days[1], days[2])
        with self.assertRaises(ValueError):
            past_training_samples((item, item), days[2], days[3])

    def test_delayed_execution_retains_original_signal_and_adjusts_pending_splits(self):
        data, _, _ = fixture()
        days = data.sessions[:5]
        data = replace(data, sessions=days, securities=(Security("A", "A", "SYN"),),
                       bars=tuple(Bar("A", d, p, p, p, p, 10000) for d, p in zip(days, (100, 100, 50, 50, 50))),
                       actions=(Split("A", days[1], 2),))
        orders = OrderSchedule((ScheduledOrder(days[0], OrderRequest("A", "buy", 2)),))
        result = run_backtest(data, orders, RunConfig("1000", ExecutionProfile("0"), execution_delay_sessions=2))
        self.assertEqual(result.fills[0].signal_date, days[0])
        self.assertEqual(result.fills[0].execution_date, days[2])
        self.assertEqual(result.fills[0].quantity, 4)
        self.assertEqual(result.fills[0].price, 50)
        self.assertFalse(result.equity[1].positions)
        self.assertIn("Close-generated market requests execute once at the second supplied session open", result.manifest.assumptions)
        self.assertNotIn("Close-generated market requests execute once at the next supplied session open", result.manifest.assumptions)

    def test_delayed_orders_expire_without_inventing_a_fill_after_end(self):
        data, _, _ = fixture()
        days = data.sessions
        orders = OrderSchedule((ScheduledOrder(days[0], OrderRequest("A", "buy", 1)),))
        result = run_backtest(data, orders, RunConfig("1000", ExecutionProfile("0"), end=days[1], execution_delay_sessions=2))
        self.assertFalse(result.fills)
        self.assertEqual(result.orders[0].status, "expired")

    def test_delayed_execution_rejects_risk_profile_and_invalid_delay(self):
        from quant_core.risk import RiskPolicy
        for delay in (0, 3, True, 1.0):
            with self.assertRaises(ValueError):
                RunConfig(execution_delay_sessions=delay)
        with self.assertRaises(ValueError):
            RunConfig(risk=RiskPolicy(), execution_delay_sessions=2)


class ContractTests(unittest.TestCase):
    def test_campaign_configuration_round_trip_preserves_hash(self):
        _, spec, _ = fixture()
        self.assertEqual(parse_spec(primitive(spec)), spec)
        self.assertEqual(parse_spec(primitive(spec)).campaign_hash, spec.campaign_hash)

    def test_chronology_duplicates_and_unknown_configuration_reject(self):
        _, spec, _ = fixture()
        for changes in ({"selection": spec.development_folds[-1]}, {"candidates": spec.candidates * 2},
                        {"prior_holdout_use": "maybe"}, {"costs_bps": ("0", "10", "25")},
                        {"bootstrap_blocks": (True,)}, {"bootstrap_repetitions": 99}, {"seed": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(spec, **changes)
        row = primitive(spec)
        row["optimizer"] = "best_return"
        with self.assertRaises(TypeError):
            parse_spec(row)

    def test_candidate_universe_profiles_and_benchmark_roles_are_frozen(self):
        _, spec, _ = fixture()
        for changes in ({"candidates": (replace(spec.candidates[0], profile="atr_protected"),)},
                        {"candidates": (spec.candidates[0], replace(spec.candidates[1], universe=("A",)))},
                        {"benchmarks": spec.benchmarks[:-1]},
                        {"benchmarks": tuple(replace(c, invested_fraction="0.9") if c.name == "broad_market_buy_hold" else c for c in spec.benchmarks)}):
            with self.assertRaises(ValueError):
                replace(spec, **changes)

    def test_qualification_requires_evidence_for_every_capability(self):
        _, _, qualification = fixture()
        for changes in ({"capabilities": qualification.capabilities[:-1]}, {"limitations": ()},
                        {"dataset_hash": "bad"}, {"scope": "historical_sp500"}):
            with self.assertRaises(ValueError):
                replace(qualification, **changes)
        self.assertFalse(replace(qualification, capabilities=tuple(replace(c, status="unresolved") for c in qualification.capabilities)).passed)


class RegistryTests(unittest.TestCase):
    def test_registry_rejects_writes_without_its_lock(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "exclusive lock"):
                Registry(temporary).append("unlocked", {})

    def test_registry_hash_chain_detects_modification_and_missing_middle_event(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = Registry(root)
            with registry.exclusive():
                registry.append("one", {"a": 1})
                registry.append("two", {"b": 2})
                registry.append("three", {"c": 3})
            self.assertEqual(len(registry.events()), 3)
            file = root / "events" / "000002.json"
            payload = file.read_text()
            file.write_text(payload.replace('"b":2', '"b":3'))
            with self.assertRaisesRegex(ValueError, "integrity"):
                registry.events()
            file.write_text(payload)
            file.unlink()
            with self.assertRaisesRegex(ValueError, "sequence"):
                registry.events()

    def test_exclusive_lock_and_immutable_publication_refuse_replacement(self):
        with TemporaryDirectory() as temporary:
            registry = Registry(temporary)
            with registry.exclusive():
                with self.assertRaises(FileExistsError), registry.exclusive():
                    pass
            file = Path(temporary) / "test.json"
            publish(file, {"a": 1})
            with self.assertRaises(FileExistsError):
                publish(file, {"a": 2})


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.data, self.spec, self.qualification = fixture()
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "campaign"

    def register(self, **changes):
        register_campaign(replace(self.spec, **changes), self.data, self.qualification, self.root)

    def test_failed_qualification_is_retained_and_cannot_run(self):
        qualification = replace(self.qualification, capabilities=tuple(replace(c, status="unresolved") for c in self.qualification.capabilities))
        with self.assertRaisesRegex(ValueError, "qualification"):
            register_campaign(self.spec, self.data, qualification, self.root)
        self.assertTrue(Registry(self.root).has("qualification_failed"))
        with self.assertRaisesRegex(ValueError, "qualification"):
            run_phase(self.root, self.data, "development")

    def test_common_start_warmup_calendar_and_synthetic_empirical_mismatch_reject(self):
        short = replace(self.spec, development_folds=(Period("early", self.data.sessions[0], self.data.sessions[34]),))
        with self.assertRaisesRegex(ValueError, "warmup"):
            register_campaign(short, self.data, self.qualification, self.root)
        with self.assertRaises(ValueError):
            register_campaign(replace(self.spec, purpose="exploratory_research"), self.data, self.qualification,
                              self.root.parent / "empirical")

    def test_selection_final_and_repeat_development_are_gated(self):
        self.register()
        with self.assertRaises(FileNotFoundError):
            run_phase(self.root, self.data, "selection")
        with self.assertRaises(FileNotFoundError):
            run_final(self.root, self.data, self.data)
        development = run_phase(self.root, self.data, "development")
        self.assertEqual(development["status"], "completed")
        self.assertEqual(development["trial_count"], 36)
        self.assertEqual(len(development["search_diagnostics"]), 2)
        with self.assertRaisesRegex(ValueError, "already attempted"):
            run_phase(self.root, self.data, "development")

    def test_full_engineering_campaign_verifies_and_cannot_nominate(self):
        self.register()
        run_phase(self.root, self.data, "development")
        run_phase(self.root, self.data, "selection")
        decision = nominate(self.root)
        self.assertEqual(decision["status"], "engineering_only")
        self.assertIsNone(decision["nominee"])
        self.assertEqual(verify_campaign(self.root)["verified_run_count"], 72)
        with self.assertRaisesRegex(ValueError, "No eligible"):
            run_final(self.root, self.data, self.data)
        with self.assertRaisesRegex(ValueError, "already decided"):
            nominate(self.root)

    def test_failures_are_retained_and_incomplete_development_cannot_expose_selection(self):
        self.register()
        with patch("quant_core.validation.campaign.run_backtest", side_effect=ValueError("deliberate fixture failure")):
            report = run_phase(self.root, self.data, "development")
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(report["trials"]), 36)
        self.assertTrue(all(r["status"] == "failed" for r in report["trials"]))
        self.assertEqual(sum(e["kind"] == "trial_failed" for e in Registry(self.root).events()), 36)
        with self.assertRaisesRegex(ValueError, "Complete development"):
            run_phase(self.root, self.data, "selection")

    def test_modified_final_prices_never_reach_development_simulation(self):
        cutoff = self.spec.holdout.start
        modified = replace(self.data, bars=tuple(replace(b, open=b.open * 10, high=b.high * 10, low=b.low * 10,
                                                        close=b.close * 10) if b.session >= cutoff else b for b in self.data.bars))
        self.assertEqual(bounded_snapshot(self.data, self.spec.selection.end), bounded_snapshot(modified, self.spec.selection.end))
        self.register()
        real = run_backtest
        observed = []
        def probe(data, source, config):
            observed.append(data)
            self.assertTrue(all(b.session <= self.spec.development_folds[-1].end for b in data.bars))
            self.assertTrue(all(a.session <= self.spec.development_folds[-1].end for a in data.actions))
            return real(data, source, config)
        with patch("quant_core.validation.campaign.run_backtest", side_effect=probe):
            run_phase(self.root, self.data, "development")
        self.assertEqual(len(observed), 36)

    def test_missing_bar_and_nonconsecutive_fold_preflight_failure(self):
        missing = replace(self.data, bars=tuple(b for b in self.data.bars if not (b.security_id == "A" and b.session == self.data.sessions[10])))
        with self.assertRaisesRegex(ValueError, "coverage"):
            register_campaign(replace(self.spec, dataset_hash=missing.dataset_hash), missing,
                              replace(self.qualification, dataset_hash=missing.dataset_hash), self.root)
        gap = replace(self.spec, development_folds=(self.spec.development_folds[0], replace(self.spec.development_folds[1], start=self.data.sessions[21])))
        with self.assertRaisesRegex(ValueError, "consecutive"):
            register_campaign(gap, self.data, self.qualification, self.root.parent / "gap")

    def test_manifest_report_and_bundle_tampering_are_detected(self):
        self.register()
        report = run_phase(self.root, self.data, "development")
        path = self.root / "development.json"
        envelope = json.loads(path.read_text())
        envelope["report"]["trial_count"] = 1
        path.write_text(canonical_json(envelope))
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify_campaign(self.root)
        path.write_text(canonical_json({"hash": content_hash(report), "report": report}))
        (self.root / report["trials"][0]["run_path"] / "signals.csv").write_text("altered")
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify_campaign(self.root)

    def test_comparison_csv_covers_all_attempts_and_preserves_undefined_ratios(self):
        self.register()
        run_phase(self.root, self.data, "development")
        path = self.root / "development.csv"
        with path.open(newline="") as stream:
            rows = tuple(csv.DictReader(stream))
        self.assertEqual(len(rows), 36)
        cash = next(row for row in rows if row["recipe"] == "cash_control")
        self.assertEqual(cash["status"], "completed")
        self.assertEqual(D(cash["total_return"]), 0)
        self.assertEqual(cash["sharpe"], "")
        path.write_text("modified")
        with self.assertRaisesRegex(ValueError, "CSV integrity"):
            verify_campaign(self.root)

    def test_runtime_changed_after_registration_blocks_execution_but_not_verification(self):
        self.register()
        with patch("quant_core.validation.campaign._engine_hash", return_value="a" * 64):
            with self.assertRaisesRegex(ValueError, "Runtime changed"):
                run_phase(self.root, self.data, "development")
            self.assertEqual(verify_campaign(self.root)["verified_run_count"], 0)

    def test_analysis_failure_is_retained_and_does_not_hide_successful_trials(self):
        self.register()
        with patch("quant_core.validation.campaign._comparison", side_effect=ArithmeticError("fixture statistics failure")):
            report = run_phase(self.root, self.data, "development")
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["analysis_error"], "fixture statistics failure")
        self.assertTrue(all(t["status"] == "completed" for t in report["trials"]))
        self.assertTrue(Registry(self.root).has("phase_analysis_failed"))
        self.assertEqual(verify_campaign(self.root)["verified_run_count"], 36)

    def test_cli_registration_execution_verification_and_error_status(self):
        root = self.root.parent
        save_snapshot(self.data, root / "data.json")
        publish(root / "spec.json", {"schema_version": 1, "campaign": self.spec})
        publish(root / "qual.json", {"schema_version": 1, "qualification": self.qualification})
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["register", str(root / "spec.json"), str(root / "data.json"),
                                   "--qualification", str(root / "qual.json"), "--output", str(self.root)]), 0)
            self.assertEqual(main(["verify", str(self.root)]), 0)
            self.assertEqual(main(["selection", str(self.root), str(root / "data.json")]), 1)
            self.assertEqual(main(["development", str(self.root), str(root / "data.json")]), 0)
            self.assertEqual(main(["development", str(self.root), str(root / "data.json")]), 1)

    def test_buy_hold_gap_rejection_invalidates_campaign_comparison(self):
        modified = replace(self.data, bars=tuple(replace(b, open=b.open * 2, high=max(b.high, b.open * 2))
                                                if b.security_id == "SPY" and b.session == self.data.sessions[6] else b
                                                for b in self.data.bars))
        register_campaign(replace(self.spec, dataset_hash=modified.dataset_hash), modified,
                          replace(self.qualification, dataset_hash=modified.dataset_hash), self.root)
        report = run_phase(self.root, modified, "development")
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(any(t["status"] == "invalid_benchmark" for t in report["trials"]))

    def test_extra_manual_experiment_is_retained_and_visible_to_nomination(self):
        self.register()
        experiment = {"hypothesis": "Additional filter", "configuration": {"filter": "new"},
                      "dataset_hash": self.data.dataset_hash, "seed": 1, "status": "failed", "reason": "Registered manually"}
        file = self.root.parent / "extra.json"
        file.write_text(canonical_json(experiment))
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["record-experiment", str(self.root), str(file)]), 0)
        self.assertTrue(Registry(self.root).has("external_experiment"))
        run_phase(self.root, self.data, "development")
        run_phase(self.root, self.data, "selection")
        outcome = nominate(self.root)
        self.assertEqual(outcome["status"], "inconclusive")
        self.assertIn("additional_search_requires_a_new_registered_research_version", outcome["reasons"])

    def _frozen_gate_fixture(self):
        # Artificial nomination ONLY to exercise lifecycle gates; tests do not claim
        # these synthetic returns pass the statistical nomination policy.
        self.spec = replace(self.spec, purpose="exploratory_research",
                            candidates=tuple(replace(c, purpose="research_candidate") for c in self.spec.candidates))
        self.qualification = replace(self.qualification, scope="exploratory_fixed_sample")
        self.register()
        run_phase(self.root, self.data, "development")
        run_phase(self.root, self.data, "selection")
        outcome = {"status": "nominated_for_independent_retest", "nominee": self.spec.candidates[0].name,
                   "decisions": [], "reasons": [], "registered_trial_count": 72}
        with patch("quant_core.validation.campaign._nomination", return_value=outcome):
            nominate(self.root)
        other = replace(self.data, metadata=replace(self.data.metadata, source="second_constructed_fixture"))
        qualification = replace(self.qualification, dataset_hash=other.dataset_hash,
                                scope="independent_retest_fixed_sample", independent_from=self.data.dataset_hash,
                                independence_evidence="Synthetic lifecycle test; no actual independent provider assertion")
        return other, qualification, outcome

    def test_final_requires_independent_reviewed_snapshot_and_consumes_once(self):
        other, qualification, outcome = self._frozen_gate_fixture()
        with self.assertRaises(FileNotFoundError):
            run_final(self.root, self.data, other)
        with self.assertRaisesRegex(ValueError, "Independent-retest"):
            crosscheck(self.root, self.data, self.qualification)
        with patch("quant_core.validation.campaign._nomination", return_value=outcome):
            result = crosscheck(self.root, other, qualification)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(D(d["total_return_difference"]) == 0 for d in result["differences"]))
        with self.assertRaisesRegex(ValueError, "already attempted"):
            crosscheck(self.root, other, qualification)
        final = run_final(self.root, self.data, other)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(len(final["providers"]), 2)
        self.assertEqual(len(final["providers"][0]["trials"]), 30)
        self.assertEqual(verify_campaign(self.root)["verified_run_count"], 192)
        with self.assertRaisesRegex(ValueError, "already consumed"):
            run_final(self.root, self.data, other)

    def test_failed_final_run_is_still_consumed_and_cannot_be_retried(self):
        other, qualification, outcome = self._frozen_gate_fixture()
        with patch("quant_core.validation.campaign._nomination", return_value=outcome):
            crosscheck(self.root, other, qualification)
        with patch("quant_core.validation.campaign.run_backtest", side_effect=ValueError("final fixture failure")):
            result = run_final(self.root, self.data, other)
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(Registry(self.root).has("final_consumed"))
        with self.assertRaisesRegex(ValueError, "already consumed"):
            run_final(self.root, self.data, other)

    def test_provider_degradation_blocks_final_and_is_not_another_tuning_attempt(self):
        other, qualification, outcome = self._frozen_gate_fixture()
        # Reviewed evidence binds the exact snapshot; substantive historical change
        # is visible in the frozen crosscheck rather than silently repaired.
        other = replace(other, bars=tuple(replace(b, open=b.open / 2, high=b.high / 2, low=b.low / 2, close=b.close / 2)
                                         if b.security_id == "A" and b.session >= self.data.sessions[25] else b for b in other.bars))
        qualification = replace(qualification, dataset_hash=other.dataset_hash)
        with patch("quant_core.validation.campaign._nomination", return_value=outcome):
            result = crosscheck(self.root, other, qualification)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(not d["passed"] for d in result["differences"]))
        with self.assertRaisesRegex(ValueError, "did not pass"):
            run_final(self.root, self.data, other)
        self.assertFalse(Registry(self.root).has("final_consumed"))

    def test_external_holdout_exposure_is_recorded_after_freeze_and_blocks_final(self):
        other, _, _ = self._frozen_gate_fixture()
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["record-holdout-exposure", str(self.root), "--reason", "External performance inspected accidentally"]), 0)
        self.assertTrue(verify_campaign(self.root)["external_holdout_exposure"])
        with self.assertRaisesRegex(ValueError, "Holdout exposure"):
            run_final(self.root, self.data, other)


def nomination_reports(spec):
    """Fabricated policy inputs, independent of engine returns or statistical fits."""
    reports = []
    for phase in ("development", "selection"):
        trials, comparisons = [], {}
        scenarios = ("cost_10", "cost_25", "delay_one_extra_session", "half_entry_participation")
        for scenario in scenarios:
            trials.append({"recipe": "same_universe_equal_weight", "scenario": scenario,
                           "returns": ("-0.01", "0.01", "-0.02", "0.01"), "metrics": {"max_drawdown": "0.1"}})
            for cfg in spec.candidates:
                trials.append({"recipe": cfg.name, "scenario": scenario,
                               "returns": ("0.03", "0.01", "-0.01", "0.02"),
                               "metrics": {"max_drawdown": "0.1", "notional_turnover": "2"}})
                comparisons.setdefault(cfg.name, {})[scenario] = {
                    "sharpe_difference": "1", "mean_excess_without_largest_winner_sessions": "0.001",
                    "median_fold_sharpe_difference": "1", "bootstrap": [{"sharpe_difference_95": ("0.1", "2"),
                                                                            "defined_sharpe_replicates": 100}]}
        reports.append({"status": "completed", "trials": trials, "candidate_comparisons": comparisons,
                        "search_diagnostics": {"cost_10": [{"p_value": "0.01"}], "cost_25": [{"p_value": "0.01"}]}})
    return reports


class NominationPolicyTests(unittest.TestCase):
    def setUp(self):
        _, spec, _ = fixture()
        self.spec = replace(spec, purpose="exploratory_research",
                            candidates=tuple(replace(c, purpose="research_candidate") for c in spec.candidates))
        self.development, self.selection = nomination_reports(self.spec)

    def test_nominee_rank_uses_development_score_then_turnover_then_id(self):
        result = _nomination(self.spec, self.development, self.selection)
        self.assertEqual(result["nominee"], "trend3")  # Unresolved tie, identical turnover: simpler trend.
        row = next(t for t in self.development["trials"] if t["recipe"] == "trend3" and t["scenario"] == "cost_10")
        row["metrics"]["notional_turnover"] = "1"
        self.assertEqual(_nomination(self.spec, self.development, self.selection)["nominee"], "trend3")
        self.development["candidate_comparisons"]["momentum3"]["cost_10"]["median_fold_sharpe_difference"] = "2"
        self.assertEqual(_nomination(self.spec, self.development, self.selection)["nominee"], "trend3")

    def test_weak_paired_or_search_uncertainty_is_inconclusive_not_profitable(self):
        for cfg in self.spec.candidates:
            self.selection["candidate_comparisons"][cfg.name]["cost_25"]["bootstrap"][0]["sharpe_difference_95"] = ("-1", "2")
        result = _nomination(self.spec, self.development, self.selection)
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["nominee"])
        self.assertTrue(all("paired_uncertainty_unresolved" in d["reasons"] for d in result["decisions"]))
        self.development, self.selection = nomination_reports(self.spec)
        self.selection["search_diagnostics"]["cost_25"][0]["p_value"] = "0.9"
        self.assertIsNone(_nomination(self.spec, self.development, self.selection)["nominee"])

    def test_higher_costs_drawdown_concentration_or_delay_can_reject_every_candidate(self):
        for cfg in self.spec.candidates:
            self.selection["candidate_comparisons"][cfg.name]["cost_25"]["sharpe_difference"] = "-1"
            self.development["candidate_comparisons"][cfg.name]["cost_10"]["mean_excess_without_largest_winner_sessions"] = "-0.1"
        for row in self.selection["trials"]:
            if row["recipe"] != "same_universe_equal_weight":
                row["metrics"]["max_drawdown"] = "0.4"
                if row["scenario"] == "delay_one_extra_session":
                    row["returns"] = ("-0.1", "0", "-0.2", "0.01")
        result = _nomination(self.spec, self.development, self.selection)
        self.assertEqual(result["status"], "rejected")
        for decision in result["decisions"]:
            self.assertTrue({"nonpositive_sharpe_advantage", "drawdown_budget_exceeded",
                             "advantage_depends_on_largest_winner_sessions", "delay_or_capacity_sensitivity_failed"} <= set(decision["reasons"]))

    def test_known_holdout_contamination_prevents_freeze(self):
        result = _nomination(replace(self.spec, prior_holdout_use="exposed", prior_holdout_disclosure="Prior manual strategy tests"),
                             self.development, self.selection)
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["nominee"])

    def test_incomplete_panel_blocks_nomination(self):
        self.development["status"] = "incomplete"
        self.assertEqual(_nomination(self.spec, self.development, self.selection)["status"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
