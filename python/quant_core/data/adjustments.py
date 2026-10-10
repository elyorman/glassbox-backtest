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


@dataclass(frozen=True)
class AdjustmentDisagreement:
    session: date
    implied_factor: Decimal  # Provider: A(previous) / A(current).
    expected_factor: Decimal  # Declared splits and cash dividends in (previous, current].


def provider_adjustment_disagreements(observations, actions, tolerance="0.01"):
    """Compare a provider's back-adjusted closes with declared splits and cash dividends.

    `observations` are ascending (session, raw_close, provider_adjusted_close) for one
    security. A back-adjusted series is raw * A(t), so A(previous) / A(current) equals
    the product of the price factors of actions in (previous, current]. Declared actions
    give that product as the action-adjusted previous close divided by the previous
    close (split: old/new shares; cash dividend: (reference - amount) / reference).
    The provider's last-digit rounding is allowed on top of `tolerance`.
    """
    tolerance = number(tolerance)
    if tolerance < 0:
        raise ValueError("Adjustment tolerance cannot be negative")
    rows = tuple(observations)
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("Adjustment observations require ascending unique sessions")
    if any(raw <= 0 or adjusted <= 0 for _, raw, adjusted in rows):
        raise ValueError("Adjustment observations require positive raw and adjusted closes")
    price_actions = sorted((a for a in actions if isinstance(a, (Split, Dividend))),
                           key=lambda a: (a.session, isinstance(a, Dividend)))
    found = []
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        for (day0, raw0, adjusted0), (day1, raw1, adjusted1) in zip(rows, rows[1:]):
            reference = raw0
            for action in price_actions:
                if day0 < action.session <= day1:
                    reference = (action.adjust_price(reference) if isinstance(action, Split)
                                 else reference - action.amount)
            expected = reference / raw0
            implied = (adjusted0 / raw0) / (adjusted1 / raw1)
            allowance = _half_unit(adjusted0) / adjusted0 + _half_unit(adjusted1) / adjusted1
            if expected <= 0 or abs(implied / expected - 1) > tolerance + allowance:
                found.append(AdjustmentDisagreement(day1, implied, expected))
    return tuple(found)


def _half_unit(value):
    """Half of the last printed digit; integers are treated as exact."""
    exponent = value.as_tuple().exponent
    return Decimal(0) if exponent >= 0 else Decimal(1).scaleb(exponent) / 2
