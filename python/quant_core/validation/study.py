"""A registered study: every run its registration declares, run once on the registered dataset and code.

docs/VALIDATION.md, "Registered studies". The parent plan runs at each cost; at the
primary cost also with a second-open delay, with idle cash earning 0%, with each
rebalance shift and as each neighbour; every comparison portfolio runs at each cost
and with 0% cash. Runs are saved under <output>/runs/<key>/ and never replaced.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from quant_core.backtest import OrderSchedule, RunConfig, run_backtest
from quant_core.execution import ExecutionProfile
from quant_core.provenance import code_hash
from quant_core.reporting import save_run
from quant_core.strategies import StrategyConfig, build_strategy
from quant_core.strategies.plans import EqualWeightPlan, FixedWeightPlan, PlanConfig, build_plan

TBILLS = "tbills"


@dataclass(frozen=True)
class PlannedRun:
    """One run of a study: `source` is a plan, a rule strategy, or None for T-bills alone."""
    key: str
    role: str
    source: PlanConfig | StrategyConfig | None
    cost_bps: Decimal
    delay: int = 1
    cash: bool = True


def references(registration):
    """The comparison portfolios, by name: 95% invested, the same costs and cash as the plan."""
    return {"spy_buy_hold": StrategyConfig("spy_buy_hold", "buy_hold", ("SPY",), invested_fraction="0.95",
                                           purpose="benchmark"),
            "sixty_forty": FixedWeightPlan(name="sixty_forty", universe=("SPY", "IEF"),
                                           weights=(("SPY", "0.6"), ("IEF", "0.4"))),
            "equal_weight": EqualWeightPlan(name="equal_weight", universe=registration.plan.universe),
            TBILLS: None}


def _bps(cost):
    return format(cost, "f")


def planned_runs(registration):
    """Every run a registration declares, in a fixed order."""
    plan, primary = registration.plan, registration.primary_cost_bps
    runs = [PlannedRun(f"plan-{_bps(cost)}bps", "plan", plan, cost) for cost in registration.costs_bps]
    runs += [PlannedRun(f"plan-{_bps(primary)}bps-delay2", "delay", plan, primary, delay=2),
             PlannedRun(f"plan-{_bps(primary)}bps-cash0", "cash0", plan, primary, cash=False)]
    for shift in registration.rebalance_shifts:
        name = f"{plan.name}_shift_{'plus' if shift > 0 else 'minus'}_{abs(shift)}"
        runs.append(PlannedRun(f"shift{shift:+d}-{_bps(primary)}bps", "shift",
                               replace(plan, name=name, decision_offset=shift), primary))
    runs += [PlannedRun(f"neighbour-{neighbour.name}-{_bps(primary)}bps", "neighbour", neighbour, primary)
             for neighbour in registration.neighbours]
    for name, source in references(registration).items():
        runs += [PlannedRun(f"{name}-{_bps(cost)}bps", "reference", source, cost) for cost in registration.costs_bps]
        runs.append(PlannedRun(f"{name}-{_bps(primary)}bps-cash0", "reference_cash0", source, primary, cash=False))
    return tuple(runs)


def _run(planned, registration, dataset):
    snapshot, execution, start = dataset.snapshot, ExecutionProfile(planned.cost_bps), registration.start
    if isinstance(planned.source, PlanConfig):
        universe = planned.source.universe
        source = build_plan(snapshot, planned.source, start, execution,
                            dataset.rates if planned.source.USES_BILLS else None)  # Signals keep the T-bills.
    elif isinstance(planned.source, StrategyConfig):
        universe = planned.source.universe
        source = build_strategy(snapshot, planned.source, start, execution)
    else:
        universe, source = ("SPY",), OrderSchedule((), TBILLS, "1")
    config = RunConfig(registration.initial_cash, execution, universe, start, registration.end,
                       execution_delay_sessions=planned.delay, cash_rates=dataset.rates if planned.cash else None)
    return run_backtest(snapshot, source, config)


def run_study(registration, dataset, output):
    """Run and save every planned run; refuses another dataset, other code, or an existing output directory."""
    if dataset.manifest.get("dataset_id") != registration.dataset_id:
        raise ValueError("The dataset is not the registered one")
    if code_hash() != registration.code_hash:
        raise ValueError("The code differs from the registered code; check out the registration's tag")
    output = Path(output)
    if output.exists():
        raise ValueError(f"{output} already exists; a registered study runs once")
    output.mkdir(parents=True)
    results = {}
    for planned in planned_runs(registration):
        results[planned.key] = _run(planned, registration, dataset)
        save_run(results[planned.key], output / "runs" / planned.key)
    return results
