"""Evidence-pack numbers for one run: results over T-bills, periods, uncertainty and overlap.

The excess return of a session is x = r - c: the portfolio's return minus what one
unit of idle cash earned over the same interval under the run's own rate series
(zero without one). Sharpe and Sortino use x; volatility and drawdowns use r.
Formulas: docs/VALIDATION.md, "Evidence metrics".
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from random import Random

from quant_core.analytics import CONTEXT, mean, return_metrics, sharpe, summarize_run
from quant_core.analytics.trades import round_trips
from quant_core.data import number
from quant_core.validation.statistics import (
    deflated_sharpe, percentile_interval, return_moments, sharpe_variance, stationary_indices,
)

ZERO, ONE = Decimal(0), Decimal(1)
GAP_REJECTIONS = ("insufficient_cash", "insufficient_cash_for_fees")
# The evidence standard's predeclared windows; the last runs to the end of the data.
WINDOWS = (("2016-2019", date(2016, 1, 1), date(2019, 12, 31)), ("2020-2022", date(2020, 1, 1), date(2022, 12, 31)),
           ("2023-end", date(2023, 1, 1), date.max))


@dataclass(frozen=True)
class RunSeries:
    """The daily series an evidence pack needs from one run; weights are position value over equity."""
    sessions: tuple[date, ...]
    returns: tuple[Decimal, ...]
    excess: tuple[Decimal, ...]
    equity: tuple[Decimal, ...]
    weights: tuple[tuple[tuple[str, Decimal], ...], ...]
    initial_cash: Decimal


def run_series(result) -> RunSeries:
    """Daily returns, returns over T-bills, equity and holdings of a completed run."""
    rates, states = result.manifest.config.cash_rates, result.equity
    if any(state.session_return is None for state in states):
        raise ValueError("Evidence needs a defined return for every session")
    returns, excess, weights = [], [], []
    with localcontext(CONTEXT):
        for index, state in enumerate(states):
            bills = rates.accrual(ONE, states[index - 1].session, state.session) if index and rates else ZERO
            returns.append(state.session_return)
            excess.append(state.session_return - bills)
            weights.append(tuple(sorted((p.security_id, p.market_value / state.equity) for p in state.positions))
                           if state.equity > 0 else ())
    return RunSeries(tuple(s.session for s in states), tuple(returns), tuple(excess),
                     tuple(s.equity for s in states), tuple(weights), result.summary.initial_cash)


def results(result) -> dict:
    """The evidence pack's results row for one run."""
    series, summary = run_series(result), summarize_run(result)
    with localcontext(CONTEXT):
        raw, over_bills = return_metrics(series.returns), return_metrics(series.excess)
        years = Decimal(summary["calendar_days_inclusive"]) / Decimal("365.2425")
        return {
            "first_session": series.sessions[0].isoformat(), "last_session": series.sessions[-1].isoformat(),
            "sessions": len(series.sessions), "cagr": summary["cagr_calendar"], "volatility": raw["volatility"],
            "sharpe": over_bills["sharpe"], "sortino": over_bills["sortino"], "max_drawdown": raw["max_drawdown"],
            "calmar": summary["calmar"], "longest_underwater_sessions": raw["longest_underwater_sessions"],
            "average_gross_exposure": summary["average_gross_exposure"],
            "annual_turnover": summary["notional_turnover"] / years, "trades": len(round_trips(result)),
            "whole_share_shortfalls": sum(1 for d in result.signal_decisions
                                          if d.selected and "below_one_share" in d.reason_codes),
            "opening_gap_rejections": sum(1 for o in result.orders
                                          if o.status == "rejected" and o.reason_code in GAP_REJECTIONS),
            "interest_income": summary["interest_income"],
        }


def period(series, start, end):
    """Return, maximum drawdown and Sharpe over T-bills of the sessions from `start` to `end`; None if none."""
    chosen = [i for i, day in enumerate(series.sessions) if start <= day <= end]
    if not chosen:
        return None
    with localcontext(CONTEXT):
        raw = return_metrics(tuple(series.returns[i] for i in chosen))
        over_bills = return_metrics(tuple(series.excess[i] for i in chosen))
    return {"first_session": series.sessions[chosen[0]].isoformat(),
            "last_session": series.sessions[chosen[-1]].isoformat(), "sessions": len(chosen),
            "return": raw["total_return"], "max_drawdown": raw["max_drawdown"], "sharpe": over_bills["sharpe"]}


def calendar_years(series):
    return {str(year): period(series, date(year, 1, 1), date(year, 12, 31))
            for year in sorted({day.year for day in series.sessions})}


def twelve_month_extremes(series):
    """Best and worst returns between month-end sessions twelve months apart; None with fewer than 13 months."""
    month_ends = {}
    for index, day in enumerate(series.sessions):
        month_ends[(day.year, day.month)] = index
    keys = sorted(month_ends)
    rows = []
    with localcontext(CONTEXT):
        for first, last in zip(keys, keys[12:]):
            if (last[0] - first[0]) * 12 + last[1] - first[1] != 12:
                continue  # A month without sessions would stretch the window.
            a, b = month_ends[first], month_ends[last]
            rows.append({"start": series.sessions[a].isoformat(), "end": series.sessions[b].isoformat(),
                         "return": series.equity[b] / series.equity[a] - ONE})
    if not rows:
        return None
    return {"best": max(rows, key=lambda row: row["return"]), "worst": min(rows, key=lambda row: row["return"])}


def drawdowns(series, count=5):
    """The `count` deepest falls below a previous peak (initial capital counts), deepest first.

    A fall ends when equity regains its peak; a peak of initial capital that no
    session closed at has no peak session, and sessions are counted from the start.
    """
    episodes, peak, peak_index, trough, falling = [], series.initial_cash, None, None, False
    for index, value in enumerate(series.equity):
        if value >= peak:
            if falling:
                episodes.append((peak, peak_index, trough, index))
                falling = False
            peak, peak_index = value, index
        elif not falling:
            falling, trough = True, index
        elif value < series.equity[trough]:
            trough = index
    if falling:
        episodes.append((peak, peak_index, trough, None))
    rows = []
    with localcontext(CONTEXT):
        for peak, peak_index, trough, recovery in episodes:
            origin = -1 if peak_index is None else peak_index
            rows.append({"depth": ONE - series.equity[trough] / peak,
                         "peak_session": None if peak_index is None else series.sessions[peak_index].isoformat(),
                         "trough_session": series.sessions[trough].isoformat(),
                         "recovery_session": None if recovery is None else series.sessions[recovery].isoformat(),
                         "sessions_to_trough": trough - origin,
                         "sessions_to_recovery": None if recovery is None else recovery - origin})
    return sorted(rows, key=lambda row: (-row["depth"], row["trough_session"]))[:count]


def periods(series, publication=None, segments=()):
    """Every period section of an evidence pack; `segments` are (name, start, end) triples."""
    return {"calendar_years": calendar_years(series),
            "windows": {name: period(series, start, end) for name, start, end in WINDOWS},
            "since_publication": period(series, publication, date.max) if publication is not None else None,
            "segments": {name: period(series, start, end) for name, start, end in segments},
            "twelve_months": twelve_month_extremes(series), "drawdowns": drawdowns(series)}


def _max_drawdown(returns):
    growth, peak, worst = ONE, ONE, ZERO
    for value in returns:
        growth *= ONE + value
        peak = max(peak, growth)
        worst = max(worst, ONE - growth / peak)
    return worst


def bootstrap(series, reference=None, block_lengths=(5, 20, 60), repetitions=500, seed=1729):
    """Stationary-bootstrap 95% intervals of the 252-session annualized return, Sharpe over T-bills and worst
    fall; with a reference run on the same sessions, of the Sharpe difference too, from the same indices.
    Each block length starts the generator again at `seed`."""
    if reference is not None and reference.sessions != series.sessions:
        raise ValueError("A bootstrap reference must cover the same sessions")
    if type(repetitions) is not int or repetitions < 100 or type(seed) is not int or seed < 0:
        raise ValueError("Bootstrap requires >=100 repetitions and a nonnegative integer seed")
    count, blocks = len(series.returns), {}
    with localcontext(CONTEXT):
        for block in block_lengths:
            random, annual, ratios, falls, differences = Random(seed), [], [], [], []
            for _ in range(repetitions):
                indices = stationary_indices(count, block, random)
                returns = tuple(series.returns[i] for i in indices)
                growth = ONE
                for value in returns:
                    growth *= ONE + value
                annual.append(growth ** (Decimal(252) / count) - ONE)
                falls.append(_max_drawdown(returns))
                ratio = sharpe(tuple(series.excess[i] for i in indices))
                if ratio is not None:
                    ratios.append(ratio)
                    other = sharpe(tuple(reference.excess[i] for i in indices)) if reference is not None else None
                    if other is not None:
                        differences.append(ratio - other)
            blocks[str(block)] = {
                "annualized_return_252": percentile_interval(annual), "sharpe": percentile_interval(ratios),
                "max_drawdown": percentile_interval(falls),
                "sharpe_minus_reference": percentile_interval(differences) if reference is not None else None,
                "defined_sharpe_replicates": len(ratios)}
    return {"repetitions": repetitions, "seed": seed, "blocks": blocks}


def deflated(parent, neighbours, trials, floor):
    """The deflated Sharpe ratio of the parent's excess returns; V is the larger of the study's own variance
    (parent and neighbours) and the historical floor, and the smaller gives the alternative."""
    neighbours = tuple(neighbours)
    if len(neighbours) < 2:
        raise ValueError("The study's own V needs the parent and at least two neighbours")
    own = sharpe_variance(tuple(return_moments(run.excess)["sharpe"] for run in (parent,) + neighbours))
    floor = number(floor)
    return {"trials": trials, "own_variance": own, "floor_variance": floor,
            "primary": deflated_sharpe(parent.excess, trials, max(own, floor)),
            "alternative": deflated_sharpe(parent.excess, trials, min(own, floor))}


def correlation(a, b):
    """Pearson correlation of daily excess returns on the sessions both runs share; None without variance."""
    shared = sorted(set(a.sessions) & set(b.sessions))
    left, right = dict(zip(a.sessions, a.excess)), dict(zip(b.sessions, b.excess))
    x, y = tuple(left[day] for day in shared), tuple(right[day] for day in shared)
    if len(shared) < 2:
        return None
    with localcontext(CONTEXT):
        mx, my = mean(x), mean(y)
        sxy = sum(((p - mx) * (q - my) for p, q in zip(x, y)), ZERO)
        sxx, syy = sum(((p - mx) ** 2 for p in x), ZERO), sum(((q - my) ** 2 for q in y), ZERO)
        return sxy / (sxx * syy).sqrt() if sxx and syy else None


def holdings_overlap(a, b):
    """Mean over the month-end sessions both runs share of the sum of min(weight in a, weight in b)."""
    month_ends = {}
    for day in sorted(set(a.sessions) & set(b.sessions)):
        month_ends[(day.year, day.month)] = day
    if not month_ends:
        return None
    left = {day: dict(weights) for day, weights in zip(a.sessions, a.weights)}
    right = {day: dict(weights) for day, weights in zip(b.sessions, b.weights)}
    with localcontext(CONTEXT):
        overlaps = [sum((min(left[day].get(asset, ZERO), weight) for asset, weight in right[day].items()), ZERO)
                    for day in month_ends.values()]
        return sum(overlaps, ZERO) / len(overlaps)
