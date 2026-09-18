"""Opt-in, low-overhead timing primitives for startup and discovery work."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import time
from typing import ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class TimingSummary:
    name: str
    count: int
    total_ns: int
    minimum_ns: int
    median_ns: int
    maximum_ns: int


class PerformanceRecorder:
    """Collect monotonic durations only while explicitly activated."""

    def __init__(self, *, clock: Callable[[], int] = time.perf_counter_ns) -> None:
        self._clock = clock
        self.started_ns = clock()
        self._samples: dict[str, list[int]] = defaultdict(list)

    def record(self, name: str, duration_ns: int) -> None:
        if duration_ns < 0:
            raise ValueError("performance durations cannot be negative")
        self._samples[name].append(int(duration_ns))

    def milestone(self, name: str) -> None:
        self.record(name, self._clock() - self.started_ns)

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        started = self._clock()
        try:
            yield
        finally:
            self.record(name, self._clock() - started)

    @contextmanager
    def activate(self) -> Iterator["PerformanceRecorder"]:
        token = _ACTIVE_RECORDER.set(self)
        try:
            yield self
        finally:
            _ACTIVE_RECORDER.reset(token)

    def samples(self, name: str) -> tuple[int, ...]:
        return tuple(self._samples.get(name, ()))

    def summaries(self) -> tuple[TimingSummary, ...]:
        result = []
        for name, values in sorted(self._samples.items()):
            ordered = sorted(values)
            middle = len(ordered) // 2
            median = (
                ordered[middle]
                if len(ordered) % 2
                else (ordered[middle - 1] + ordered[middle]) // 2
            )
            result.append(TimingSummary(
                name=name,
                count=len(values),
                total_ns=sum(values),
                minimum_ns=min(values),
                median_ns=median,
                maximum_ns=max(values),
            ))
        return tuple(result)


_ACTIVE_RECORDER: ContextVar[PerformanceRecorder | None] = ContextVar(
    "mouse_control_performance_recorder", default=None
)


@contextmanager
def measure(name: str) -> Iterator[None]:
    """Measure one phase when a recorder is active; otherwise only yield."""
    recorder = _ACTIVE_RECORDER.get()
    if recorder is None:
        yield
        return
    with recorder.phase(name):
        yield


def milestone(name: str) -> None:
    recorder = _ACTIVE_RECORDER.get()
    if recorder is not None:
        recorder.milestone(name)


def timed(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Instrument a cold-path function without changing its public signature."""
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with measure(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate
