"""Pure computations over raw movements: FIFO dwell, retention, schedule regularity."""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev


@dataclass(frozen=True)
class Movement:
    id: str
    at: datetime
    amount: int
    counterparty: str


@dataclass(frozen=True)
class FifoResult:
    segments: list[tuple[float, int]]  # (dwell minutes, matched amount)
    retained: int
    inflow: int

    @property
    def retention_ratio(self) -> float | None:
        return self.retained / self.inflow if self.inflow else None

    @property
    def median_dwell_minutes(self) -> float | None:
        if not self.segments:
            return None
        ordered = sorted(self.segments)
        half = sum(a for _, a in ordered) / 2
        running = 0
        for dwell, amount in ordered:
            running += amount
            if running >= half:
                return dwell
        return ordered[-1][0]

    @property
    def max_dwell_minutes(self) -> float | None:
        return max((d for d, _ in self.segments), default=None)


def fifo_dwell(inbound: Sequence[Movement], outbound: Sequence[Movement]) -> FifoResult:
    """Match outflows to the oldest funds first. Outflows with no funds to match are ignored."""
    events = sorted(
        [(m.at, 0, m.amount) for m in inbound] + [(m.at, 1, m.amount) for m in outbound]
    )  # an inflow sorts before an outflow at the same instant
    queue: deque[tuple[datetime, int]] = deque()
    segments: list[tuple[float, int]] = []
    for at, kind, amount in events:
        if kind == 0:
            queue.append((at, amount))
            continue
        remaining = amount
        while remaining > 0 and queue:
            arrival, available = queue.popleft()
            take = min(remaining, available)
            segments.append(((at - arrival).total_seconds() / 60, take))
            remaining -= take
            if take < available:
                queue.appendleft((arrival, available - take))
    return FifoResult(segments, sum(a for _, a in queue), sum(m.amount for m in inbound))


def is_regular_schedule(outbound: Sequence[Movement]) -> bool:
    """At least 3 outflows at (nearly) the same clock time, or at an almost constant interval."""
    if len(outbound) < 3:
        return False
    times = sorted(m.at for m in outbound)
    minutes = [t.hour * 60 + t.minute for t in times]
    if max(minutes) - min(minutes) <= 30:
        return True
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)]
    avg = mean(gaps)
    return avg > 0 and pstdev(gaps) / avg <= 0.05
