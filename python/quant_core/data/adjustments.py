"""Causal transformations into current share units; source observations stay raw."""

from dataclasses import replace
from decimal import Decimal


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
