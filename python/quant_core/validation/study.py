"""A registered study: every run its registration declares, run once on the registered dataset and code.

docs/ENGINE.md, "Registered studies". The parent plan runs at each cost; at the
primary cost also with a second-open delay, with idle cash earning 0%, with each
rebalance shift and as each neighbour; every comparison portfolio runs at each cost
and with 0% cash. Every run completes in memory before anything is saved; runs are
saved under <output>/runs/<key>/ and never replaced.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from quant_core.backtest import RunConfig, run_backtest
from quant_core.execution import ExecutionProfile
from quant_core.provenance import code_hash
from quant_core.reporting import save_run
from quant_core.strategies import StrategyConfig, build_strategy
from quant_core.strategies.plans import EqualWeightPlan, FixedWeightPlan, PlanConfig, build_plan
from quant_core.validation.registration import shift_name

TBILLS = "tbills"


@dataclass(frozen=True)
class PlannedRun:
    """One run of a study: `source` is a plan or a rule strategy."""
    key: str
    role: str
    source: PlanConfig | StrategyConfig
    cost_bps: Decimal
    delay: int = 1
    cash: bool = True


def references(registration):
    """The comparison portfolios, by name: 95% invested, the same costs and cash as the plan. SPY is set back to
    95% at each month end, so its dividends are reinvested rather than left in cash."""
    return {"spy_buy_hold": FixedWeightPlan(name="spy_buy_hold", universe=("SPY",), weights=(("SPY", "1"),)),
            "sixty_forty": FixedWeightPlan(name="sixty_forty", universe=("SPY", "IEF"),
                                           weights=(("SPY", "0.6"), ("IEF", "0.4"))),
            "equal_weight": EqualWeightPlan(name="equal_weight", universe=registration.plan.universe),
            TBILLS: StrategyConfig(TBILLS, "cash", ("SPY",), purpose="benchmark")}  # Holds nothing.


def _bps(cost):
    return format(cost, "f")


def planned_runs(registration):
    """Every run a registration declares, in a fixed order."""
    plan, primary = registration.plan, registration.primary_cost_bps
    runs = [PlannedRun(f"plan-{_bps(cost)}bps", "plan", plan, cost) for cost in registration.costs_bps]
    runs += [PlannedRun(f"plan-{_bps(primary)}bps-delay2", "delay", plan, primary, delay=2),
             PlannedRun(f"plan-{_bps(primary)}bps-cash0", "cash0", plan, primary, cash=False)]
    for shift in registration.rebalance_shifts:
        runs.append(PlannedRun(f"shift{shift:+d}-{_bps(primary)}bps", "shift",
                               replace(plan, name=shift_name(plan.name, shift), decision_offset=shift), primary))
    runs += [PlannedRun(f"neighbour-{neighbour.name}-{_bps(primary)}bps", "neighbour", neighbour, primary)
             for neighbour in registration.neighbours]
    for name, source in references(registration).items():
        runs += [PlannedRun(f"{name}-{_bps(cost)}bps", "reference", source, cost) for cost in registration.costs_bps]
        runs.append(PlannedRun(f"{name}-{_bps(primary)}bps-cash0", "reference_cash0", source, primary, cash=False))
    if len({run.key for run in runs}) != len(runs):
        raise ValueError("Planned run keys must be unique")
    return tuple(runs)


def _start(planned, registration, sessions):
    """A copy decided k sessions before month end starts k sessions early, so it keeps its first month."""
    offset = planned.source.decision_offset if isinstance(planned.source, PlanConfig) else 0
    if offset >= 0:
        return registration.start
    if registration.start not in sessions or sessions.index(registration.start) + offset < 0:
        raise ValueError("The registered start must be a session with sessions before it for the -2 shift")
    return sessions[sessions.index(registration.start) + offset]


def _run(planned, registration, dataset):
    snapshot, execution = dataset.snapshot, ExecutionProfile(planned.cost_bps)
    start, universe = _start(planned, registration, snapshot.sessions), planned.source.universe
    if isinstance(planned.source, PlanConfig):
        source = build_plan(snapshot, planned.source, start, execution,
                            dataset.rates if planned.source.USES_BILLS else None)  # Signals keep the T-bills.
    else:
        source = build_strategy(snapshot, planned.source, start, execution)
    config = RunConfig(registration.initial_cash, execution, universe, start, registration.end,
                       execution_delay_sessions=planned.delay, cash_rates=dataset.rates if planned.cash else None)
    return run_backtest(snapshot, source, config)


def check_study(registration, dataset):
    """Refuse a dataset or code other than the registered ones."""
    if dataset.manifest.get("dataset_id") != registration.dataset_id:
        raise ValueError("The dataset is not the registered one")
    if code_hash() != registration.code_hash:
        raise ValueError("The code differs from the registered code; check out the registration's tag")
    missing = set(registration.tickers) - {security.security_id for security in dataset.snapshot.securities}
    if missing:
        raise ValueError(f"The dataset lacks registered tickers: {', '.join(sorted(missing))}")


def first_decision(result):
    """A plan's first decision session, the ETFs without enough history then, and the ETFs without data then
    (not yet listed, or no bar that session)."""
    if not result.signal_decisions:
        raise ValueError("A plan makes no decision in the registered period")
    first = min(decision.session for decision in result.signal_decisions)
    at = [decision for decision in result.signal_decisions if decision.session == first]
    return (first, frozenset(d.security_id for d in at if "insufficient_history" in d.reason_codes),
            frozenset(d.security_id for d in at
                      if {"outside_security_lifetime", "missing_signal_bar"} & set(d.reason_codes)))


def simulate_study(registration, dataset):
    """Every planned run, in memory, after the dataset and code checks; nothing is saved or shown.

    The registered start must be the parent's first decision (a month end), and it
    must come after every warmup: at that decision the parent and each neighbour
    have enough history for every ETF that is trading, so the study's own V compares
    one period (docs/ENGINE.md, "Registered studies"). An ETF not yet trading joins
    later, like any later listing.
    """
    check_study(registration, dataset)
    results = {planned.key: _run(planned, registration, dataset) for planned in planned_runs(registration)}
    primary = _bps(registration.primary_cost_bps)
    if first_decision(results[f"plan-{primary}bps"])[0] != registration.start:
        raise ValueError("The registered start must be the parent's first decision session, a month end")
    for name, key in [(registration.plan.name, f"plan-{primary}bps")] + [
            (n.name, f"neighbour-{n.name}-{primary}bps") for n in registration.neighbours]:
        lacking = first_decision(results[key])[1]
        if lacking:
            raise ValueError(f"The period starts inside a warmup: at the first decision {name} lacks history for "
                             f"{', '.join(sorted(lacking))}; register a later start")
    return results


def check_output(output):
    """Refuse an output directory that exists: a registered study runs once."""
    if Path(output).exists():
        raise ValueError(f"{output} already exists; a registered study runs once")


def save_study(results, output):
    """Save each completed run once under <output>/runs/<key>/."""
    check_output(output)
    Path(output).mkdir(parents=True)
    for key, result in results.items():
        save_run(result, Path(output) / "runs" / key)


def run_study(registration, dataset, output):
    """Every planned run, saved once each after all of them completed; refuses an existing output directory."""
    check_output(output)
    results = simulate_study(registration, dataset)
    save_study(results, output)
    return results
