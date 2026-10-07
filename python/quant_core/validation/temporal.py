"""Unique-session chronology and timestamp-based label purging for later ML."""

from dataclasses import dataclass
from datetime import date

from quant_core.data import identity, session


@dataclass(frozen=True)
class Period:
    name: str
    start: date
    end: date

    def __post_init__(self):
        identity(self.name)
        session(self.start)
        session(self.end)
        if self.start > self.end:
            raise ValueError("Period start must precede end")


@dataclass(frozen=True)
class LabelInterval:
    security_id: str
    signal: date
    entry: date
    end: date

    def __post_init__(self):
        identity(self.security_id)
        for day in (self.signal, self.entry, self.end):
            session(day)
        if not self.signal < self.entry <= self.end:
            raise ValueError("Labels require signal < entry <= outcome end")


def past_training_samples(samples, fit_session, evaluation_start):
    """Close-fit may use completed same-day labels; evaluation overlap is purged."""
    session(fit_session)
    session(evaluation_start)
    if fit_session >= evaluation_start:
        raise ValueError("Fit must occur before evaluation")
    samples = tuple(samples)
    if any(not isinstance(s, LabelInterval) for s in samples):
        raise ValueError("Training samples require LabelInterval")
    if len({(s.security_id, s.signal) for s in samples}) != len(samples):
        raise ValueError("Duplicate symbol/signal label")
    return tuple(s for s in samples if s.signal <= fit_session and s.end <= fit_session
                 and s.entry < evaluation_start and s.end < evaluation_start)


def period_sessions(calendar, period):
    return tuple(day for day in calendar if period.start <= day <= period.end)
