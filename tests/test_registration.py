"""Registrations and plan configurations as plain JSON: everything fixed before a registered run."""

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quant_core.provenance import content_hash
from quant_core.strategies.plans import (
    FixedWeightPlan, PlanConfig, TrendPlan, builtin_plans, plan_from_dict, plan_to_dict,
)
from quant_core.validation.registration import load_registration, parse_registration

D = Decimal
PARENT = TrendPlan(name="trend_fixture", universe=("A", "B"), average_months=2)


def example():
    """A complete, valid registration of a synthetic trend study."""
    return {
        "schema_version": 1, "study": "trend-fixture", "role": "Cross-asset trend following",
        "tag": "study/trend-fixture-2026-10-15", "registered_at": "2026-10-15T09:00:00+00:00",
        "code_hash": "a" * 64, "dataset": {"id": "b" * 64, "tickers": ["A", "B", "IEF", "SPY"]},
        "plan": plan_to_dict(PARENT),
        "neighbours": [plan_to_dict(TrendPlan(name="trend_fixture_3", universe=("A", "B"), average_months=3)),
                       plan_to_dict(TrendPlan(name="trend_fixture_4", universe=("A", "B"), average_months=4))],
        "rebalance_shifts": [-2, 2], "period": {"start": "2024-01-31", "end": "2026-06-30"},
        "publication": {"date": "2025-01-01", "source": "A synthetic paper"},
        "segments": [{"name": "early", "start": "2024-01-31", "end": "2024-12-31"}],
        "costs_bps": ["10", "25", "50"], "primary_cost_bps": "10", "initial_cash": "100000",
        "primary_reference": "sixty_forty",
        "bootstrap": {"block_lengths": [5, 20], "repetitions": 100, "seed": 1729},
        "trials": {"cumulative": 50, "this_study": 5, "per_role": 5, "historical_floor": "0.000197"},
        "sources": [{"parameter": "average_months", "source": "A synthetic paper, p. 1"}],
        "departures": [{"what": "Fills at the next open", "reason": "The engine never fills on the signal bar"}],
        "related_ledger_rows": ["2026-10-03 trend recipes"],
        "cross_check": {"decision": "None for the tester round", "reason": "Owner decision"},
        "disclosures": ["Synthetic data only."], "earlier_studies": [],
    }


class PlanDictTests(unittest.TestCase):
    def test_every_plan_round_trips_through_json(self):
        reference = FixedWeightPlan(name="r", universe=("SPY", "IEF"), weights=(("SPY", "0.6"), ("IEF", "0.4")))
        for plan in builtin_plans() + (reference,):
            with self.subTest(plan=plan.name):
                values = json.loads(json.dumps(plan_to_dict(plan)))
                self.assertEqual(plan_from_dict(values), plan)
                self.assertEqual(values["rule"], plan.RULE)
        self.assertEqual(plan_to_dict(PARENT)["invested_fraction"], "0.95")  # Decimals are written as text.

    def test_unknown_or_malformed_plans_are_refused(self):
        for values in ({"rule": "magic"}, {"name": "x"}, [], {**plan_to_dict(PARENT), "extra": 1}, {"rule": []},
                       {"rule": {}}, {**plan_to_dict(PARENT), "universe": "AB"}):  # Not ("A", "B").
            with self.subTest(values=values), self.assertRaises(ValueError):
                plan_from_dict(values)
        for value in ("trend", PlanConfig(name="base", universe=("A",))):  # The base class has no rule.
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Only a plan configuration"):
                plan_to_dict(value)


class RegistrationTests(unittest.TestCase):
    def test_a_complete_registration_loads_with_its_hash(self):
        payload = example()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "trend-fixture.json"
            path.write_text(json.dumps(payload))
            registration = load_registration(path)
        self.assertEqual((registration.study, registration.hash), ("trend-fixture", content_hash(payload)))
        self.assertEqual((registration.plan, len(registration.neighbours)), (PARENT, 2))
        self.assertEqual((registration.start, registration.end, registration.publication),
                         (date(2024, 1, 31), date(2026, 6, 30), date(2025, 1, 1)))
        self.assertEqual(registration.segments, (("early", date(2024, 1, 31), date(2024, 12, 31)),))
        self.assertEqual((registration.costs_bps, registration.primary_cost_bps, registration.initial_cash),
                         ((D(10), D(25), D(50)), D(10), D(100000)))
        self.assertEqual((registration.trials, registration.trials_this_study, registration.historical_floor),
                         (50, 5, D("0.000197")))
        self.assertEqual(registration.registered_at, datetime(2026, 10, 15, 9, tzinfo=timezone.utc))
        self.assertEqual(registration.rebalance_shifts, (-2, 2))

    def test_every_rule_is_enforced(self):
        def change(path, value):
            def apply(payload):
                *parents, last = path
                target = payload
                for key in parents:
                    target = target[key]
                if value is DELETE:
                    del target[last]
                else:
                    target[last] = value
            return apply

        cases = [
            (change(("extra",), 1), "exactly the documented fields"),
            (change(("earlier_studies",), DELETE), "exactly the documented fields"),
            (change(("schema_version",), 2), "schema version"),
            (change(("study",), "Trend Fixture"), "lower-case words"),
            (change(("tag",), "study/other-2026-10-15"), "study/<study>-<YYYY-MM-DD>"),
            (change(("tag",), "study/trend-fixture-latest"), "study/<study>-<YYYY-MM-DD>"),
            (change(("tag",), "study/trend-fixture-2026-13-45"), "study/<study>-<YYYY-MM-DD>"),
            (change(("tag",), "study/trend-fixture-2026-10-16"), "tag date must be the registration date"),
            (change(("role",), "Momentum"), "role must be one of the standard's roles"),
            (change(("registered_at",), "2026-10-15T09:00:00"), "time zone"),
            (change(("code_hash",), "x"), "code_hash must be a SHA-256"),
            (change(("dataset", "id"), "x"), "dataset id"),
            (change(("dataset", "tickers"), ["A", "B", "SPY"]), "lack IEF"),
            (change(("dataset", "tickers"), ["A", "A", "B", "IEF", "SPY"]), "tickers must be distinct"),
            (change(("plan",), plan_to_dict(FixedWeightPlan(name="f", universe=("A", "B"), purpose="built_in_plan",
                                                            weights=(("A", "0.5"), ("B", "0.5"))))),
             "comparison portfolio cannot be registered"),
            (change(("plan", "name"), "Trend_Fixture"), "lower-case letters, digits and underscores"),
            (change(("neighbours", 1, "name"), "trend_fixture_3"), "need distinct names"),
            (change(("neighbours", 0), plan_to_dict(replace(PARENT, name="trend_fixture_scaled",
                                                            invested_fraction=D("0.9")))),
             "more than their names and invested fraction"),
            (change(("neighbours",), example()["neighbours"][:1]), "at least two neighbours"),
            (change(("neighbours", 0), plan_to_dict(FixedWeightPlan(name="f", universe=("A",), weights=(("A", "1"),),
                                                                    purpose="built_in_plan"))),
             "at least two neighbours of the parent's rule"),
            (change(("neighbours", 0), plan_to_dict(PARENT)), "distinct built-in plans"),
            (change(("plan", "decision_offset"), 1), "without a decision offset"),
            (change(("neighbours", 1, "purpose"), "engineering_fixture"), "distinct built-in plans"),
            (change(("rebalance_shifts",), [0]), "shifts must be -2 and 2 sessions"),
            (change(("rebalance_shifts",), [-3, 3]), "shifts must be -2 and 2 sessions"),
            (change(("rebalance_shifts",), [2, 2]), "shifts must be -2 and 2 sessions"),
            (change(("rebalance_shifts",), [2]), "shifts must be -2 and 2 sessions"),
            (change(("period", "start"), "2024-W05-3"), "YYYY-MM-DD date"),  # An ISO week date.
            (change(("period", "end"), "2024-01-31"), "start before it ends"),
            (change(("publication", "date"), "2027-01-01"), "must not follow the period end"),
            (change(("segments", 0, "end"), "2024-01-01"), "segment must start before"),
            (change(("segments",), example()["segments"] * 2), "segment names must be distinct"),
            (change(("costs_bps",), ["25", "50"]), "the standard's 10, 25 and 50 bps"),
            (change(("costs_bps",), "102550"), "costs must be a list"),
            (change(("primary_cost_bps",), "25"), "primary cost must be 10 bps"),
            (change(("costs_bps",), [10.5, 25]), "floor must be decimal strings"),  # Floats are not exact.
            (change(("costs_bps",), ["ten"]), "floor must be decimal strings"),
            (change(("costs_bps",), ["10", "10", "50"]), "the standard's 10, 25 and 50 bps"),
            (change(("costs_bps",), ["10", "10", "25", "50"]), "the standard's 10, 25 and 50 bps"),
            (change(("costs_bps",), ["10", "-25", "50"]), "the standard's 10, 25 and 50 bps"),
            (change(("initial_cash",), "0"), "initial cash must be positive"),
            (change(("trials", "historical_floor"), "-0.1"), "floor nonnegative"),
            (change(("primary_reference",), "tbills"), "primary reference must be one of"),
            (change(("bootstrap", "repetitions"), 99), "at least 100"),
            (change(("bootstrap", "block_lengths"), [5, 5]), "distinct"),
            (change(("bootstrap", "block_lengths"), []), "distinct"),
            (change(("bootstrap", "block_lengths"), [0, 5]), "block length must be an integer of at least 1"),
            (change(("bootstrap", "block_lengths"), [[5]]), "block length must be an integer of at least 1"),
            (change(("bootstrap", "seed"), -1), "seed must be an integer of at least 0"),
            (change(("trials", "this_study"), 3), "parent, its neighbours and its shifts"),
            (change(("trials", "cumulative"), 4), "cumulative trial count must be an integer of at least 5"),
            (change(("trials", "per_role"), 51), "per-role trial count cannot exceed"),
            (change(("trials", "per_role"), 4), "per-role trial count must be an integer of at least 5"),
            (change(("trials", "historical_floor"), DELETE), "trials must have exactly the fields"),
            (change(("sources",), []), "at least one parameter source"),
            (change(("departures", 0, "reason"), " "), "departure reason must be nonempty"),
            (change(("cross_check",), {"decision": "x"}), "cross-check must have exactly"),
            (change(("disclosures",), "text"), "disclosures must be a list"),
            (change(("earlier_studies",), [{"study": "x"}]), "earlier study must have exactly"),
            (change(("earlier_studies",), [{"study": "x", "runs": "local\\x\\runs\\plan-10bps"}]),
             "forward slashes"),
        ]
        for apply, message in cases:
            payload = deepcopy(example())
            apply(payload)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_registration(payload)

    def test_a_primary_cost_written_as_10_0_keeps_the_ladder_s_spelling(self):
        registration = parse_registration({**example(), "primary_cost_bps": "10.0"})
        self.assertEqual(format(registration.primary_cost_bps, "f"), "10")  # So the run keys agree.

    def test_the_hash_ignores_layout_and_key_order(self):
        payload = example()
        with TemporaryDirectory() as directory:
            compact, spread = Path(directory) / "a.json", Path(directory) / "b.json"
            compact.write_text(json.dumps(payload, separators=(",", ":")))
            spread.write_text(json.dumps(dict(reversed(list(payload.items()))), indent=4))
            self.assertEqual(load_registration(compact).hash, load_registration(spread).hash)

    def test_the_file_must_be_json(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{")
            with self.assertRaisesRegex(ValueError, "is not JSON"):
                load_registration(path)


DELETE = object()


if __name__ == "__main__":
    unittest.main()
