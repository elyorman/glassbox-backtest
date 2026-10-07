"""Causal daily price features shared by strategies and later model/scanner work."""

from decimal import Decimal

from quant_core.data.adjustments import adjusted_quantity

ZERO = Decimal("0")
ONE = Decimal("1")
PRICE_POLICY = "known_splits_ex_date_close_dividend_reinvestment_v1"


def signal_prices(bars, splits=(), dividends=()):
    """Dimensionless total-return index; reinvest at ex-date close for signals only.

    The portfolio separately receives dividend cash under its payment convention.
    This function does not supply adjusted execution prices or credit portfolio cash.
    """
    bars = tuple(bars)
    if not bars:
        return ()
    if len({b.security_id for b in bars}) != 1 or any(a.session >= b.session for a, b in zip(bars, bars[1:])):
        raise ValueError("Signal history requires one security and increasing unique sessions")
    asset, as_of = bars[-1].security_id, bars[-1].session
    distributions = {}
    for dividend in dividends:
        if dividend.security_id == asset and dividend.session <= as_of:
            distributions[dividend.session] = distributions.get(dividend.session, ZERO) + dividend.amount
    prices = [ONE]
    for previous, current in zip(bars, bars[1:]):
        value = prices[-1] * (current.close + distributions.get(current.session, ZERO))
        prices.append(adjusted_quantity(value, asset, previous.session, current.session, splits) / previous.close)
    return tuple(prices)


def trailing_mean(prices, window):
    _window(window)
    return sum(prices[-window:], ZERO) / window if len(prices) >= window else None


def trailing_return(prices, lookback, skip=0):
    _window(lookback)
    if type(skip) is not int or not 0 <= skip < lookback:
        raise ValueError("Return skip must be an integer in [0, lookback)")
    return prices[-1 - skip] / prices[-1 - lookback] - ONE if len(prices) > lookback else None


def nearness_to_high(prices, window):
    _window(window)
    return prices[-1] / max(prices[-window:]) if len(prices) >= window else None


def realized_volatility(prices, window):
    """Population standard deviation of exactly `window` simple signal returns."""
    _window(window)
    if len(prices) < window + 1:
        return None
    selected = prices[-window-1:]
    if any(p <= 0 or not p.is_finite() for p in selected):
        raise ValueError("Volatility prices must be positive finite Decimals")
    returns = tuple(b/a - ONE for a, b in zip(selected, selected[1:]))
    mean = sum(returns, ZERO) / window
    return (sum(((r-mean)**2 for r in returns), ZERO) / window).sqrt()


def _window(window):
    if type(window) is not int or window <= 0:
        raise ValueError("Feature window must be a positive integer")
