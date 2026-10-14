"""Evidence-pack numbers for one run: results over T-bills, periods, uncertainty and overlap.

The excess return of a session is x = r - c: the portfolio's return minus what one
unit of idle cash earned over the same interval under the run's own rate series
(zero without one). Sharpe and Sortino use x; volatility and drawdowns use r.
Formulas: docs/VALIDATION.md, "Evidence metrics".
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from quant_core.analytics import CONTEXT, return_metrics, summarize_run
from quant_core.analytics.trades import round_trips

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
