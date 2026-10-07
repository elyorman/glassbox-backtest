"""Causal, raw-price/raw-share dollar-volume ranks; no vendor dependencies."""
from dataclasses import dataclass
from decimal import Decimal

from quant_core.data import Bar, session


@dataclass(frozen=True)
class DollarVolumePercentile:
    score: Decimal | None
    reason: str | None
    observations: tuple[Bar, ...]
    lower_count: int = 0
    equal_count: int = 0


def dollar_volume_percentile(bars, completed_calendar, window_sessions):
    """Compare current raw close × shares to W−1 exact preceding sessions.

    The calendar ends at the completed signal session. Future bars are ignored;
    invalid ordering/identities are rejected and coverage/volume failures remain
    explicit. Observations retain the exact raw bars used by this feature.
    """
    if type(window_sessions) is not int or window_sessions < 2:
        raise ValueError("Volume window requires at least two integer sessions")
    calendar = tuple(completed_calendar)
    for day in calendar:
        session(day)
    if calendar != tuple(sorted(set(calendar))):
        raise ValueError("Completed calendar must be unique and increasing")
    if not calendar:
        return DollarVolumePercentile(None, "insufficient_history", ())
    history = tuple(b for b in bars if b.session <= calendar[-1])
    if any(not isinstance(b, Bar) for b in history):
        raise ValueError("Volume feature requires raw bars")
    if len({b.security_id for b in history}) > 1:
        raise ValueError("Volume feature requires one security")
    if tuple(b.session for b in history) != tuple(sorted(set(b.session for b in history))):
        raise ValueError("Volume bars must be unique and increasing")
    observations = history[-window_sessions:]
    if len(calendar) < window_sessions or len(observations) < window_sessions:
        return DollarVolumePercentile(None, "insufficient_history", observations)
    if tuple(b.session for b in observations) != calendar[-window_sessions:]:
        return DollarVolumePercentile(None, "missing_history_session", observations)
    if any(b.volume <= 0 for b in observations):
        return DollarVolumePercentile(None, "nonpositive_volume", observations)
    values = tuple(b.close * b.volume for b in observations)
    lower = sum(v < values[-1] for v in values[:-1])
    equal = sum(v == values[-1] for v in values[:-1])
    score = (Decimal(lower) + Decimal(".5") * equal) / (window_sessions - 1)
    return DollarVolumePercentile(score, None, observations, lower, equal)
