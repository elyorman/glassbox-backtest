"""Causal transformations into current share units; source observations stay raw."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from quant_core.data import Dividend, Split, number


def split_factor(asset, observed_on, as_of, splits):
    """Scalar convenience; repeating exact ratios cannot be represented finitely."""
    return _legacy_factor(asset, observed_on, as_of, splits)


def adjusted_quantity(value, asset, observed_on, as_of, splits):
    """Convert an amount through known actions, avoiding a rounded scalar factor."""
    if not any(s.new_shares is not None and s.security_id == asset and observed_on < s.session <= as_of
               for s in splits):
        return value * _legacy_factor(asset, observed_on, as_of, splits)
    for split in sorted(splits, key=lambda s: s.session):
        if split.security_id == asset and observed_on < split.session <= as_of:
            value = split.adjust_quantity(value)
    return value


def adjusted_price(value, asset, observed_on, as_of, splits):
    """Convert a historical price using each action's original counts."""
    for split in sorted(splits, key=lambda s: s.session):
        if split.security_id == asset and observed_on < split.session <= as_of:
            value = split.adjust_price(value)
    return value


def _legacy_factor(asset, observed_on, as_of, splits):
    factor = Decimal("1")
    for split in splits:
        if split.security_id == asset and observed_on < split.session <= as_of:
            factor *= split.ratio
    return factor


def normalized_history(bars, splits):
    """Past observations expressed in the last bar's share units, known splits only."""
    bars = tuple(bars)
    if not bars:
        return ()
    result = []
    for bar in bars:
        asset, day, end = bar.security_id, bar.session, bars[-1].session
        if any(s.new_shares is not None and s.security_id == asset and day < s.session <= end for s in splits):
            prices = {name: adjusted_price(getattr(bar, name), asset, day, end, splits)
                      for name in ("open", "high", "low", "close")}
            volume = adjusted_quantity(bar.volume, asset, day, end, splits)
        else:
            # Preserve legacy multi-action arithmetic and historic results.
            factor = _legacy_factor(asset, day, end, splits)
            prices = {name: getattr(bar, name) / factor for name in ("open", "high", "low", "close")}
            volume = bar.volume * factor
        result.append(replace(bar, **prices, volume=volume))
    return tuple(result)


PRECISION_LIMIT = Decimal("0.05")  # Coarser rounding cannot verify even small stock dividends; reported, not trusted.


@dataclass(frozen=True)
class AdjustmentDisagreement:
    previous_session: date
    session: date
    implied_factor: Decimal  # Provider: A(previous) / A(current).
    expected_factor: Decimal  # Declared splits and cash dividends in (previous, current].
    reason: str  # "factor_mismatch" or "insufficient_precision".


def provider_adjustment_disagreements(observations, actions, tolerance="0.001", dividend_basis="previous_close"):
    """Compare a provider's back-adjusted closes with declared splits and cash dividends.

    `observations` are ascending (session, raw_close, provider_adjusted_close) for one
    security. A back-adjusted series is raw * A(t), so A(previous) / A(current) equals
    the product of the price factors of actions in (previous, current]. Splits give
    old/new shares. A cash dividend's factor depends on the provider's convention:
    "previous_close" is (previous close - amount) / previous close, as EODHD documents;
    "ex_date_close" is ex-date close / (ex-date close + amount), which reproduces
    Tiingo's adjClose to about 1e-11.

    The provider's rounding is half a unit of the finest decimal printed anywhere in the
    series (providers drop trailing zeros), allowed on top of `tolerance`. A pair whose
    rounding allowance exceeds PRECISION_LIMIT is reported as insufficient precision.
    """
    tolerance = number(tolerance)
    if tolerance < 0:
        raise ValueError("Adjustment tolerance cannot be negative")
    if dividend_basis not in ("previous_close", "ex_date_close"):
        raise ValueError("Unsupported dividend basis")
    rows = tuple((day, number(raw), number(adjusted)) for day, raw, adjusted in observations)
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("Adjustment observations require ascending unique sessions")
    if any(raw <= 0 or adjusted <= 0 for _, raw, adjusted in rows):
        raise ValueError("Adjustment observations require positive raw and adjusted closes")
    finest = min((adjusted.as_tuple().exponent for _, _, adjusted in rows), default=0)
    half_unit = Decimal(1).scaleb(finest) / 2 if finest < 0 else Decimal(0)
    price_actions = sorted((a for a in actions if isinstance(a, (Split, Dividend))),
                           key=lambda a: (a.session, isinstance(a, Dividend)))
    found = []
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        for (day0, raw0, adjusted0), (day1, raw1, adjusted1) in zip(rows, rows[1:]):
            reference, dividends = raw0, Decimal(1)
            for action in price_actions:
                if day0 < action.session <= day1:
                    if isinstance(action, Split):
                        reference = action.adjust_price(reference)
                    elif dividend_basis == "previous_close":
                        reference = reference - action.amount
                    else:
                        dividends *= raw1 / (raw1 + action.amount)
            expected = reference / raw0 * dividends
            implied = (adjusted0 / raw0) / (adjusted1 / raw1)
            allowance = half_unit / adjusted0 + half_unit / adjusted1
            if allowance > PRECISION_LIMIT:
                found.append(AdjustmentDisagreement(day0, day1, implied, expected, "insufficient_precision"))
            elif expected <= 0 or abs(implied / expected - 1) > tolerance + allowance:
                found.append(AdjustmentDisagreement(day0, day1, implied, expected, "factor_mismatch"))
    return tuple(found)
