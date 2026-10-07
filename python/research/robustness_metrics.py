"""Offline robustness diagnostics on verified portfolio ledgers.

Cash overlays and exposure-matched mixes are explicit diagnostics, not new
executable portfolios. Dollar contributions include actual filled costs.
"""

from bisect import bisect_left
from collections import defaultdict
import csv
from datetime import date
from decimal import Decimal

from quant_core.analytics import mean, paired_metrics, return_metrics, sharpe
from quant_core.data import Split, Dividend
from quant_core.features import signal_prices

ZERO, ONE = Decimal(0), Decimal(1)


def dates(values):
    result = tuple(date.fromisoformat(v) if isinstance(v, str) else v for v in values)
    if not result or any(type(d) is not date for d in result) or any(a >= b for a, b in zip(result, result[1:])):
        raise ValueError("Need nonempty strictly increasing session dates")
    return result


def load_rates(path):
    """Normalized annual-percent CSV; missing observations are never zero rates."""
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['observation_date', 'annual_percent']:
            raise ValueError("Expected normalized 3-month Treasury annual-percent columns")
        rows = [(date.fromisoformat(r['observation_date']), Decimal(r['annual_percent']) / 100)
                for r in reader if r['annual_percent'] not in ('', '.', 'N/A')]
    if not rows:
        raise ValueError("No usable cash-rate observations")
    dates([d for d, _ in rows])
    if any(not v.is_finite() or v <= -1 or v > 1 for _, v in rows):
        raise ValueError("Invalid annual fractional cash rate")
    return tuple(rows)


def cash_intervals(sessions, rates, max_stale_days=10):
    """Strictly lagged yield, simple ACT/365 accrual between portfolio sessions."""
    sessions = dates(sessions)
    if not rates:
        raise ValueError("Missing cash-rate history")
    rate_days = dates([d for d, _ in rates])
    if any(not v.is_finite() or v <= -1 or v > 1 for _, v in rates):
        raise ValueError("Invalid annual fractional cash rate")
    output = [dict(session=sessions[0], observation_date=None, calendar_days=0, annual_rate=None, return_=ZERO)]
    for previous, current in zip(sessions, sessions[1:]):
        index = bisect_left(rate_days, previous) - 1
        if index < 0 or (previous - rate_days[index]).days > max_stale_days:
            raise ValueError(f"Missing/stale lagged cash rate before {previous}")
        day, rate = rates[index]
        elapsed = (current - previous).days
        output.append(dict(session=current, observation_date=day, calendar_days=elapsed,
                           annual_rate=rate, return_=rate * elapsed / 365))
    return [{('return' if k == 'return_' else k): v for k, v in row.items()} for row in output]


def cash_overlay(run, cash_returns):
    states = run['equity']
    if len(states) != len(cash_returns) or not states or cash_returns[0] != ZERO:
        raise ValueError("Cash overlay needs aligned intervals beginning with zero")
    initial = Decimal(run['manifest']['config']['initial_cash'])
    interest, previous_cash, previous_equity = ZERO, initial, initial
    returns, equities = [], []
    for state, cash_return in zip(states, cash_returns):
        interest += (previous_cash + interest) * cash_return
        equity = Decimal(state['equity']) + interest
        returns.append(equity / previous_equity - ONE)
        equities.append(equity)
        previous_cash, previous_equity = Decimal(state['cash']), equity
    metrics = return_metrics(returns)
    days = (date.fromisoformat(states[-1]['session']) - date.fromisoformat(states[0]['session'])).days + 1
    metrics.update(interest_usd=interest, final_equity_usd=equities[-1],
                   cagr_calendar=(equities[-1] / initial) ** (Decimal('365.2425') / days) - ONE,
                   sharpe_historical_reference=sharpe(tuple(r - f for r, f in zip(returns, cash_returns))),
                   returns=tuple(returns), equities=tuple(equities),
                   convention='fixed_orders_previous_cash_plus_interest_no_receivables')
    return metrics


def regression(candidate, reference, cash_returns):
    if len(candidate) != len(reference) or len(candidate) != len(cash_returns) or not candidate:
        raise ValueError("Regression needs aligned nonempty returns")
    left = tuple(x - f for x, f in zip(candidate, cash_returns))
    right = tuple(x - f for x, f in zip(reference, cash_returns))
    result = paired_metrics(left, right)
    result['alpha_arithmetic_252'] = ((mean(left) - result['beta'] * mean(right)) * 252
                                      if result['beta'] is not None else None)
    result['sharpe_historical_reference'] = sharpe(left)
    return result


def exposure_match(run, reference, cash_returns, equities=None):
    states = run['equity']
    if len(states) != len(reference) or len(states) != len(cash_returns):
        raise ValueError("Exposure mix requires aligned intervals")
    equities = equities if equities is not None else tuple(Decimal(s['equity']) for s in states)
    if len(equities) != len(states):
        raise ValueError("Exposure equity must align with intervals")
    previous = ZERO
    output = []
    for state, market, cash, equity in zip(states, reference, cash_returns, equities):
        output.append(previous * market + (ONE - previous) * cash)
        previous = Decimal(state['market_value']) / equity
        if not ZERO <= previous <= ONE:
            raise ValueError("Exposure diagnostic requires unlevered positive-equity portfolios")
    return tuple(output)


def total_return_leg(snapshot, sessions, asset='SPY'):
    """Fully invested ex-date-reinvested signal index; diagnostic, not a ledger."""
    sessions = dates(sessions)
    bars = sorted((b for b in snapshot.bars if b.security_id == asset and b.session <= sessions[-1]), key=lambda b: b.session)
    prices = signal_prices(bars, tuple(a for a in snapshot.actions if isinstance(a, Split)),
                            tuple(a for a in snapshot.actions if isinstance(a, Dividend)))
    changes = {b.session: current / previous - ONE for b, previous, current in zip(bars[1:], prices, prices[1:])}
    if not set(sessions).issubset({b.session for b in bars}):
        raise ValueError("Market leg has missing sessions")
    return (ZERO,) + tuple(changes[d] for d in sessions[1:])


def rolling(sessions, candidate, reference, cash_returns, window=252):
    sessions = dates(sessions)
    if type(window) is not int or window < 2 or any(len(v) != len(sessions) for v in (candidate, reference, cash_returns)):
        raise ValueError("Rolling statistics need aligned returns and window >= 2")
    output = []
    for stop in range(window, len(sessions) + 1):
        start = stop - window
        left, right, rf = candidate[start:stop], reference[start:stop], cash_returns[start:stop]
        metrics = return_metrics(left)
        benchmark = return_metrics(right)
        growth = ONE + benchmark['total_return']
        output.append(dict(session=sessions[stop - 1], window_start=sessions[start],
            total_return=metrics['total_return'], max_drawdown=metrics['max_drawdown'],
            sharpe_zero_reference=metrics['sharpe'],
            relative_growth=(ONE + metrics['total_return']) / growth - ONE if growth else None,
            **regression(left, right, rf)))
    return output


def recoveries(sessions, equities, initial):
    sessions = dates(sessions)
    if len(sessions) != len(equities) or initial <= 0:
        raise ValueError("Recovery analysis needs aligned positive-capital equity")
    peak, peak_index, peak_day, current, output = initial, -1, sessions[0], None, []
    for index, (day, equity) in enumerate(zip(sessions, equities)):
        if equity >= peak:
            if current:
                current.update(status='recovered', recovery_date=day,
                    sessions_to_recovery=index - peak_index, calendar_days=(day - peak_day).days)
                output.append(current)
                current = None
            peak, peak_index, peak_day = equity, index, day
        else:
            dd = ONE - equity / peak
            if current is None:
                current = dict(peak_date=peak_day, first_underwater=day, trough_date=day,
                               max_drawdown=dd, underwater_sessions=0)
            current['underwater_sessions'] += 1
            if dd > current['max_drawdown']:
                current.update(max_drawdown=dd, trough_date=day)
    if current:
        current.update(status='open', recovery_date=None, sessions_to_recovery=None,
                       calendar_days=(sessions[-1] - peak_day).days)
        output.append(current)
    return output


def concentration(candidate, reference, sessions, count=5):
    sessions = dates(sessions)
    if len(candidate) != len(reference) or len(candidate) != len(sessions) or type(count) is not int or count < 0:
        raise ValueError("Concentration needs aligned returns and nonnegative count")
    excess = tuple(x - y for x, y in zip(candidate, reference))
    selected = sorted((i for i, value in enumerate(excess) if value > 0),
                      key=lambda i: (-excess[i], sessions[i]))[:count]
    removed = sum((excess[i] for i in selected), ZERO)
    positive = sum((max(x, ZERO) for x in excess), ZERO)
    return dict(mean_daily_excess=mean(excess),
                mean_excess_after_zeroing=(sum(excess, ZERO) - removed) / len(excess),
                removed_positive_excess_share=removed / positive if positive else None,
                zeroed_dates=[sessions[i].isoformat() for i in selected],
                convention='zero_best_positive_excess_sessions_not_trade_removal')


def attribution(run):
    """Daily dollar asset wealth changes; episodes persist through partial sales.

    Dividends enter P&L on entitlement, including unpaid receivables. A split
    enters through unchanged portfolio wealth, not a synthetic cash flow.
    """
    states = run['equity']
    sessions = dates([s['session'] for s in states])
    universe = tuple(run['manifest']['config']['universe'])
    flows, previous, fills, actions = defaultdict(Decimal), defaultdict(Decimal), defaultdict(list), defaultdict(list)
    for fill in run['fills']:
        fills[fill['execution_date']].append(fill)
    for action in run['corporate_actions']:
        if action['kind'] in ('dividend_entitlement', 'cash_delisting'):
            actions[action['session']].append(action)
    active, episodes, daily = {}, [], []
    previous_equity = Decimal(run['manifest']['config']['initial_cash'])
    for day, state in zip(sessions, states):
        for action in actions[day.isoformat()]:
            asset, amount = action['security_id'], Decimal(action['amount'])
            if asset not in universe:
                if amount:
                    raise ArithmeticError("Nonzero income outside universe")
                continue
            flows[asset] += amount
            if asset in active:
                active[asset]['pnl_usd'] += amount
        for fill in fills[day.isoformat()]:
            asset = fill['security_id']
            if asset not in universe:
                raise ArithmeticError("Fill outside universe")
            if asset not in active:
                if fill['side'] != 'buy':
                    raise ArithmeticError("Exit without a holding episode")
                active[asset] = dict(security_id=asset, entry_date=day, pnl_usd=ZERO)
            delta = Decimal(fill['notional']) * (ONE if fill['side'] == 'sell' else -ONE) - Decimal(fill['fees'])
            flows[asset] += delta
            active[asset]['pnl_usd'] += delta
            if Decimal(fill['position_quantity_after']) == ZERO:
                episode = active.pop(asset)
                episode.update(exit_date=day, mark_date=day, status='closed',
                               calendar_days=(day - episode['entry_date']).days)
                episodes.append(episode)
        marks = {p['security_id']: Decimal(p['market_value']) for p in state['positions']}
        current = {a: flows[a] + marks.get(a, ZERO) for a in universe}
        day_total = ZERO
        for asset in universe:
            delta = current[asset] - previous[asset]
            daily.append(dict(session=day, security_id=asset, pnl_usd=delta,
                              arithmetic_return_contribution=delta / previous_equity if previous_equity else None))
            day_total += delta
        equity = Decimal(state['equity'])
        if abs(day_total - (equity - previous_equity)) > max(Decimal('1e-18'), abs(equity) * Decimal('1e-24')):
            raise ArithmeticError(f"Daily attribution does not reconcile on {day}")
        previous, previous_equity = current, equity
    marks = {p['security_id']: Decimal(p['market_value']) for p in states[-1]['positions']}
    for asset, episode in active.items():
        episode['pnl_usd'] += marks.get(asset, ZERO)
        episode.update(exit_date=None, mark_date=sessions[-1], status='open',
                       calendar_days=(sessions[-1] - episode['entry_date']).days)
        episodes.append(episode)
    total = sum(previous.values(), ZERO)
    if abs(sum((e['pnl_usd'] for e in episodes), ZERO) - total) > max(Decimal('1e-18'), abs(total) * Decimal('1e-24')):
        raise ArithmeticError("Holding-episode P&L does not reconcile")
    positive = sum((max(v, ZERO) for v in previous.values()), ZERO)
    assets = [dict(security_id=a, pnl_usd=previous[a],
                   positive_pnl_share=max(previous[a], ZERO) / positive if positive else None)
              for a in universe]
    annual = defaultdict(Decimal)
    for row in daily:
        annual[row['session'].year, row['security_id']] += row['pnl_usd']
    return dict(daily=daily, assets=assets, episodes=episodes,
                annual=[dict(year=y, security_id=a, pnl_usd=v) for (y, a), v in sorted(annual.items())])
