"""Directional falsification, missing evidence and frozen-budget enforcement."""
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research.volume_campaign import (PARENT, CONTROL, volume_entries, adapt_plan,
    direction_comparison, volume_diagnostics, volume_decisions, guard_registration,
    verify_file_map, verify_volume_signals)
from research.stock_campaign import REFERENCE, EQUAL, expected_panel
from research.high_campaign import digest


def payload(returns):
    return {"equity": [{"session":f"2024-01-{i+1:02d}", "session_return":v}
                       for i,v in enumerate(returns)]}


def plan_and_rows():
    base = dict(stocks=["A", "B"], entries=[], source_hashes={}, trial_budget=99,
        uncertainty={"blocks":[20,60],"repetitions":500,"seed":1729},
        objectives={"return_seeking":"unchanged"}, freeze_rule="unchanged",
        periods=[dict(name="continuous",scenarios=[["primary10","10",1],["stress25","25",1],["delay10","10",2]])] +
        [dict(name="fold_"+str(i),scenarios=[["primary10","10",1],["stress25","25",1]]) for i in range(3)])
    plan = adapt_plan(base)
    rows = [dict(key=key, period=p["name"], scenario=s[0], recipe=e["configuration"]["name"],
        role=e["role"], parent=e["parent"], status="completed",metrics={"cagr_calendar":".1"},
        sharpe_historical_reference="1" if e["role"]=="reference" else "2")
        for key,(p,s,e) in expected_panel(plan).items()]
    directions = {p["name"]+"_"+s[0]:{"status":"complete","mean_daily_parent_minus_control":".001"}
        for p in plan["periods"] for s in p["scenarios"]}
    return plan, rows, directions


class VolumeCampaignTests(unittest.TestCase):
    def test_adaptation_preserves_periods_and_exact_budget_with_three_new_recipes(self):
        plan, rows, _ = plan_and_rows()
        self.assertEqual(len(rows),54)
        self.assertEqual(sum(r["role"]!="reference" for r in rows),27)
        entries = volume_entries(("B", "A"))
        self.assertEqual([e["role"] for e in entries[:3]], ["parent","neighbor","direction_control"])
        self.assertEqual([e["configuration"]["window_sessions"] for e in entries[:3]], [50,55,50])
        parent, neighbor, control = (dict(e["configuration"]) for e in entries[:3])
        for c in (parent,neighbor,control): c.pop("name")
        neighbor["window_sessions"] = 50; control["direction"] = "descending"
        self.assertEqual(parent,neighbor); self.assertEqual(parent,control)
        self.assertEqual(parent["min_average_dollar_volume"],"10000000")

    def test_hand_calculated_direction_uses_net_returns_without_dropping_dates(self):
        result = direction_comparison(payload([".01","-.02",".03"]), payload(["0","-.03",".02"]))
        self.assertEqual(D(result["mean_daily_parent_minus_control"]),D(".01"))
        self.assertTrue(result["positive"])
        self.assertFalse(direction_comparison(payload(["0","0"]),payload(["0","0"]))["positive"])

    def test_missing_invalid_or_unaligned_direction_is_incomplete(self):
        for left,right in ((payload(["0",None]),payload(["0","0"])),
                           (payload(["0"]),payload(["0","0"])),
                           (payload(["NaN"]),payload(["0"]))):
            with self.subTest(left=left):
                self.assertEqual(direction_comparison(left,right)["status"],"incomplete")

    def test_control_loss_rejects_and_control_cannot_replace_parent(self):
        plan,rows,directions = plan_and_rows()
        self.assertTrue(volume_decisions(plan,rows,directions)[PARENT]["freeze_for_retest"])
        directions["continuous_stress25"]["mean_daily_parent_minus_control"] = "-.001"
        result = volume_decisions(plan,rows,directions)
        self.assertEqual(set(result),{PARENT})
        self.assertFalse(result[PARENT]["freeze_for_retest"])
        self.assertEqual(result[PARENT]["decision"],"reject_on_this_sample")

    def test_freezing_requires_two_complete_passing_panels(self):
        from research.volume_campaign import freeze_for_both_samples
        for panels, expected in (({},False), ({"original22":{PARENT:{"freeze_for_retest":True}}},False),
                ({"original22":{PARENT:{"freeze_for_retest":True}},"transfer47":{PARENT:{"freeze_for_retest":False}}},False),
                ({"original22":{PARENT:{"freeze_for_retest":True}},"transfer47":{PARENT:{"freeze_for_retest":True}}},True)):
            with self.subTest(panels=panels):
                self.assertEqual(freeze_for_both_samples(panels),expected)

    def test_required_missing_neighbor_fold_sharpe_or_control_is_incomplete(self):
        for role, period, field, value in (("neighbor","continuous","status","failed"),
                ("parent","fold_0","status","failed"),
                ("parent","continuous","sharpe_historical_reference",None),
                ("direction_control","continuous","status","invalid_benchmark")):
            plan,rows,directions = plan_and_rows()
            target=next(r for r in rows if r["role"]==role and r["period"]==period)
            target[field]=value
            result=volume_decisions(plan,rows,directions)[PARENT]
            self.assertEqual(result["decision"],"incomplete")
            self.assertFalse(result["freeze_for_retest"])

    def test_volume_diagnostics_expose_non_extreme_choices_and_ties(self):
        rows=[dict(session="2024-01-31",security_id=a,eligible=True,selected=s,score=v)
              for a,s,v in (("A",True,".5"),("B",True,"1"),("C",False,".5"))]
        result=volume_diagnostics({"signal_decisions":rows})
        self.assertEqual(result["selected_below_090_fraction"],"0.5")
        self.assertEqual(result["cross_stock_tie_session_fraction"],"1")
        self.assertEqual(result["rows"][0]["score_range"],"0.5")
        self.assertFalse(result["selection_gate"])

    def test_preflight_rejects_changed_allocation_uncertainty_and_budget(self):
        from research.volume_campaign import validate_frozen_protocol
        plan,_,_=plan_and_rows()
        spec=dict(allocation={"invested_fraction":".95","top_k":5,"min_raw_price":"5",
            "min_average_dollar_volume":"10000000","average_volume_window":20,"entry_participation":".01",
            "profile":"scheduled_slots"},recipes=[dict(name=e["configuration"]["name"],role=e["role"],
                window_sessions=e["configuration"]["window_sessions"],direction=e["configuration"]["direction"])
                for e in plan["entries"][:3]],uncertainty={"expected_blocks":[20,60],"repetitions":500,"seed":1729},
            trial_budget={"per_panel":54,"new_simulations":54,"reused_reference_scenarios":54,"search_candidate_count":3})
        validate_frozen_protocol(plan,spec)
        for path,value in (("allocation",".90"),("uncertainty",100),("budget",55),("extra_control",None)):
            changed=deepcopy(plan)
            if path=="allocation":changed["entries"][0]["configuration"]["invested_fraction"]=value
            elif path=="uncertainty":changed["uncertainty"]["repetitions"]=value
            elif path=="budget":changed["trial_budget"]=value
            else:changed["entries"].append(deepcopy(changed["entries"][2]))
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_frozen_protocol(changed,spec)

    def test_registration_changed_bytes_stop_before_loading_inputs(self):
        with TemporaryDirectory() as temp:
            root=Path(temp); p=root/"REGISTRATION.json";p.write_text("{}")
            (root/"REGISTRATION_HASH.json").write_text(json.dumps({"sha256":digest(p)}))
            p.write_text("{} ")
            with self.assertRaisesRegex(ValueError,"Registration bytes"):
                guard_registration(root)

    def test_recovery_binds_original_failure_evidence_and_forbids_financial_changes(self):
        from research.volume_campaign import verify_recovery
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/"failure.json").write_text('{"status":"failed"}')
            sources={"quant_core/strategies/volume.py":"a"*64,"research/volume_campaign.py":"b"*64}
            (root/"REGISTRATION.json").write_text(json.dumps({"source_hashes":sources}))
            files={name:digest(root/name) for name in ("failure.json","REGISTRATION.json")}
            (root/"COMPLETE.json").write_text(json.dumps({"files":files}))
            reg=dict(source_hashes=dict(sources,**{"research/volume_campaign.py":"c"*64}),
                recovery=dict(root=str(root),files=files,complete_sha256=digest(root/"COMPLETE.json"),
                    original_registration_sha256=digest(root/"REGISTRATION.json"),original_source_hashes=sources))
            verify_recovery(reg)
            changed=deepcopy(reg);changed["recovery"]["files"]={}
            with self.assertRaises(ValueError):verify_recovery(changed)
            changed=deepcopy(reg);changed["source_hashes"]["quant_core/strategies/volume.py"]="d"*64
            with self.assertRaises(ValueError):verify_recovery(changed)
            (root/"failure.json").write_text('{"status":"completed"}')
            with self.assertRaises(ValueError):verify_recovery(reg)

    def test_file_map_rejects_missing_changed_and_unsafe_evidence(self):
        with TemporaryDirectory() as temp:
            root=Path(temp); (root/"a").write_text("original")
            hashes={"a":digest(root/"a")};verify_file_map(root,hashes)
            (root/"a").write_text("changed")
            with self.assertRaises(ValueError):verify_file_map(root,hashes)
            with self.assertRaises(ValueError):verify_file_map(root,{"../a":"0"*64})

    def test_signal_replay_detects_changed_raw_feature_or_selection(self):
        from test_volume_strategy import simulate, cfg
        from test_strategies import snapshot, DAYS
        from quant_core.execution import ExecutionProfile
        from quant_core.strategies.volume import build_volume_strategy
        from quant_core.reporting import save_run, verify_run
        data=snapshot(); configuration=cfg(max_volume_participation="1")
        source=build_volume_strategy(data,configuration,DAYS[2],ExecutionProfile("0"))
        with TemporaryDirectory() as temp:
            save_run(simulate(data,configuration),Path(temp)/"run"); saved=verify_run(Path(temp)/"run")
            verify_volume_signals(data,source,saved)
            changed=deepcopy(saved); changed["signal_decisions"][0]["score"]=".123"
            with self.assertRaisesRegex(ValueError,"Volume signal"):
                verify_volume_signals(data,source,changed)

    def test_order_replay_respects_engine_priority_instead_of_security_order(self):
        from test_volume_strategy import simulate, cfg
        from test_strategies import snapshot, DAYS
        from quant_core.execution import ExecutionProfile
        from quant_core.strategies.volume import build_volume_strategy
        from quant_core.reporting import save_run, verify_run
        data=snapshot(paths={"A":(10,)*6,"B":(10,)*6},
                      volumes={"A":(100,100,50,50,50,50),"B":(100,100,200,200,200,200)})
        configuration=cfg(max_volume_participation="1")
        source=build_volume_strategy(data,configuration,DAYS[2],ExecutionProfile("0"))
        with TemporaryDirectory() as temp:
            save_run(simulate(data,configuration),Path(temp)/"run");saved=verify_run(Path(temp)/"run")
            self.assertEqual([r["request"]["security_id"] for r in saved["orders"]],["B","A"])
            self.assertEqual(verify_volume_signals(data,source,saved)["status"],"passed")
            changed=deepcopy(saved); changed["orders"][0]["request"]["quantity"]="999"
            with self.assertRaisesRegex(ValueError,"Volume order"):
                verify_volume_signals(data,source,changed)

    def test_order_replay_checks_sales_before_new_entries_at_second_rebalance(self):
        from datetime import date
        from test_strategies import snapshot
        from quant_core.backtest import RunConfig, run_backtest
        from quant_core.execution import ExecutionProfile
        from quant_core.strategies.volume import VolumeConfig, build_volume_strategy
        from quant_core.reporting import save_run, verify_run
        days=tuple(date.fromisoformat(d) for d in ("2024-01-29","2024-01-30","2024-01-31",
                                                   "2024-02-01","2024-02-28","2024-03-01"))
        data=snapshot(paths={a:(100,)*6 for a in ("A","B","C")},sessions=days,
            volumes={"A":(10000,10000,1000,1000,20000,20000),"B":(10000,10000,20000,20000,20000,20000),
                     "C":(10000,10000,10000,10000,1000,1000)})
        configuration=VolumeConfig("sales_fixture",("A","B","C"),window_sessions=3,volume_lookback=2,
                                   top_k=2,max_volume_participation="1")
        execution=ExecutionProfile("0");source=build_volume_strategy(data,configuration,days[2],execution)
        result=run_backtest(data,source,RunConfig("100000",execution,configuration.universe,days[2],days[-1]))
        with TemporaryDirectory() as temp:
            save_run(result,Path(temp)/"run");saved=verify_run(Path(temp)/"run")
            self.assertEqual([(r["request"]["side"],r["request"]["security_id"]) for r in saved["orders"]
                if r["signal_date"]=="2024-02-28"],[("sell","C"),("buy","A")])
            self.assertEqual(verify_volume_signals(data,source,saved)["status"],"passed")
