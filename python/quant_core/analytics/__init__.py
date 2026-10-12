"""Exact, explicitly defined daily portfolio and benchmark statistics."""

from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from quant_core.data import number
from quant_core.portfolio import reconciles

ZERO, ONE = Decimal(0), Decimal(1)
CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)


def mean(values):
    return sum(values, ZERO) / len(values) if values else None


def variance(values):
    if len(values) < 2:
        return None
    center = mean(values)
    return sum(((v - center) ** 2 for v in values), ZERO) / (len(values) - 1)


def sharpe(values, annual_sessions=252):
    var = variance(values)
    return mean(values) / var.sqrt() * Decimal(annual_sessions).sqrt() if var and var > 0 else None


def return_metrics(values, annual_sessions=252):
    """Undefined returns after a wipeout remain null, never fabricated zeros."""
    values = tuple(number(v) if v is not None else None for v in values)
    if not values or any(v is not None and v < -1 for v in values):
        raise ValueError("Need nonempty returns >= -1")
    if type(annual_sessions) is not int or annual_sessions <= 0:
        raise ValueError("Annual sessions must be a positive integer")
    with localcontext(CONTEXT):
        growth, peak, max_dd, duration, longest = ONE, ONE, ZERO, 0, 0
        undefined = False
        for value in values:
            if value is None:
                if growth != ZERO:
                    raise ValueError("Undefined returns require a preceding complete loss")
                undefined = True
            else:
                if undefined:
                    raise ValueError("Returns cannot resume after an undefined zero-equity interval")
                growth *= 1 + value
            peak = max(peak, growth)
            dd = 1 - growth / peak
            max_dd = max(max_dd, dd)
            duration = duration + 1 if dd > 0 else 0
            longest = max(longest, duration)
        var = variance(values) if not undefined else None
        volatility = (var * annual_sessions).sqrt() if var is not None else None
        downside = ((sum((min(v, ZERO) ** 2 for v in values), ZERO)
                     / len(values) * annual_sessions).sqrt() if not undefined else None)
        annual_return = growth ** (Decimal(annual_sessions) / len(values)) - 1
        return {"session_count": len(values), "total_return": growth - 1,
                "annualized_return_252": annual_return, "volatility": volatility,
                "sharpe": sharpe(values, annual_sessions) if not undefined else None,
                "sortino": mean(values) * annual_sessions / downside if downside else None,
                "calmar_session_annualized": annual_return / max_dd if max_dd and not undefined else None,
                "max_drawdown": max_dd, "longest_underwater_sessions": longest}


def paired_metrics(candidate, benchmark, annual_sessions=252):
    candidate, benchmark = tuple(candidate), tuple(benchmark)
    if len(candidate) != len(benchmark) or not candidate:
        raise ValueError("Paired returns require identical nonempty dates")
    if any(v is None for v in candidate + benchmark):
        # Validate the wipeout contract; never drop dates or manufacture returns.
        return_metrics(candidate, annual_sessions)
        return_metrics(benchmark, annual_sessions)
        return {"sharpe_difference": None, "mean_daily_excess": None, "beta": None}
    candidate, benchmark = tuple(map(number, candidate)), tuple(map(number, benchmark))
    with localcontext(CONTEXT):
        left, right = sharpe(candidate, annual_sessions), sharpe(benchmark, annual_sessions)
        c, b = mean(candidate), mean(benchmark)
        covariance = (sum(((x - c) * (y - b) for x, y in zip(candidate, benchmark)), ZERO)
                      / (len(candidate) - 1)) if len(candidate) > 1 else None
        var = variance(benchmark)
        return {"sharpe_difference": left - right if left is not None and right is not None else None,
                "mean_daily_excess": mean(tuple(x - y for x, y in zip(candidate, benchmark))),
                "beta": covariance / var if var and covariance is not None else None}


def summarize_run(result):
    """Actual filled-notional turnover; sale fills are not round-trip trade counts."""
    with localcontext(CONTEXT):
        returns = tuple(s.session_return for s in result.equity)
        metrics = return_metrics(returns)
        if result.manifest.config.cash_rates is not None:
            # Against a zero reference rate, Treasury interest would count as excess return. Excess-return
            # ratios over the run's own cash accrual come with the evidence report (roadmap step E).
            metrics.update(sharpe=None, sortino=None)
        states = {s.session: s for s in result.equity}
        turnover = sum((f.notional / states[f.execution_date].equity for f in result.fills
                        if states[f.execution_date].equity > 0), ZERO)
        exits = tuple(f.realized_pnl for f in result.fills if f.side == "sell")
        wins, losses = tuple(v for v in exits if v > 0), tuple(v for v in exits if v < 0)
        contributions = {a: ZERO for a in result.manifest.config.universe}
        for fill in result.fills:
            contributions[fill.security_id] += (fill.notional - fill.fees if fill.side == "sell"
                                                else -fill.notional - fill.fees)
        for action in result.corporate_actions:
            if action.kind in ("dividend_entitlement", "cash_delisting"):
                if action.security_id not in contributions:
                    if action.amount != ZERO:
                        raise ArithmeticError("Nonzero corporate-action income outside the run universe")
                    continue
                contributions[action.security_id] += action.amount
        for position in result.equity[-1].positions:
            contributions[position.security_id] += position.market_value
        interest = result.equity[-1].interest_income
        if not reconciles(sum(contributions.values(), ZERO) + interest,
                          result.summary.final_equity - result.summary.initial_cash, result.summary.final_equity):
            raise ArithmeticError("Asset contributions and interest do not reconcile")
        calendar_days = (result.equity[-1].session - result.equity[0].session).days + 1
        cagr = (result.summary.final_equity / result.summary.initial_cash) ** (Decimal("365.2425") / calendar_days) - 1
        metrics.update({"cagr_calendar": cagr,
                        "calmar": cagr / metrics["max_drawdown"] if metrics["max_drawdown"]
                                  and all(v is not None for v in returns) else None,
                        "calendar_days_inclusive": calendar_days,
                        "fees": result.summary.fees, "slippage": result.summary.slippage,
                        "interest_income": interest,
                        "fill_count": len(result.fills), "sale_fill_count": len(exits),
                        "rejected_orders": result.summary.rejected_order_count,
                        "expired_orders": result.summary.expired_order_count,
                        "notional_turnover": turnover,
                        "average_gross_exposure": mean(tuple(s.market_value / s.equity for s in result.equity if s.equity > 0)),
                        "average_cash_fraction": mean(tuple(s.cash / s.equity for s in result.equity if s.equity > 0)),
                        "sale_fill_win_rate": Decimal(len(wins)) / len(exits) if exits else None,
                        "mean_sale_fill_pnl": mean(exits),
                        "sale_fill_profit_factor": sum(wins, ZERO) / -sum(losses, ZERO) if losses else None,
                        "asset_pnl": contributions})
        return metrics
