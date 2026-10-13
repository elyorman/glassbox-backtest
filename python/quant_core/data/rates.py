"""Provider-neutral annual cash rates for idle-cash interest and cash comparisons."""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from quant_core.data import number, session

MAX_RATE_AGE_DAYS = 10


@dataclass(frozen=True)
class CashRateSeries:
    """Annual simple rates as fractions (0.05 is 5%), one per observation date."""
    source: str
    series: str
    retrieved_at: datetime
    observations: tuple[tuple[date, Decimal], ...]

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in (self.source, self.series)):
            raise ValueError("Cash rates require a source and a series name")
        if not isinstance(self.retrieved_at, datetime) or self.retrieved_at.utcoffset() is None:
            raise ValueError("Cash rate retrieved_at must be timezone-aware")
        try:
            observations = tuple((day, number(rate)) for day, rate in self.observations)
        except (TypeError, ValueError):
            raise ValueError("Cash rate observations must be (date, rate) pairs") from None
        for day, _ in observations:
            session(day)
        if not observations or any(a[0] >= b[0] for a, b in zip(observations, observations[1:])):
            raise ValueError("Cash rate observations must be nonempty with ascending unique dates")
        if any(not -1 < rate <= 1 for _, rate in observations):
            raise ValueError("Cash rates must be annual fractions above -1 and at most 1")
        object.__setattr__(self, "observations", observations)

    def rate_before(self, day: date) -> Decimal:
        """Latest rate observed strictly before `day`; missing or stale data is refused."""
        index = bisect_left(self.observations, day, key=lambda observation: observation[0])
        if index == 0:
            raise ValueError(f"No {self.series} observation before {day}")
        observed, rate = self.observations[index - 1]
        if (day - observed).days > MAX_RATE_AGE_DAYS:
            raise ValueError(f"{self.series} is stale for {day}: the latest observation, {observed}, "
                             f"is more than {MAX_RATE_AGE_DAYS} days earlier")
        return rate

    def accrual(self, amount: Decimal, previous: date, day: date) -> Decimal:
        """Simple ACT/365 interest on `amount` held at the close of `previous`, for the calendar days until `day`."""
        if day <= previous:
            raise ValueError("Accrual requires a later session")
        return amount * self.rate_before(previous) * (day - previous).days / 365

    def growth(self, sessions) -> Decimal:
        """Growth of 1 unit of idle cash held over consecutive `sessions`, credited as the engine credits it."""
        sessions = tuple(sessions)
        if not sessions:
            raise ValueError("Cash growth needs at least one session")
        growth = Decimal(1)
        with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):  # The engine's context, whoever calls.
            for previous, day in zip(sessions, sessions[1:]):
                growth += self.accrual(growth, previous, day)
        return growth
