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
