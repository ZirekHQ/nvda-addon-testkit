"""One polling loop shared by every waiting assertion."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

INTERVAL = 0.1


@dataclass(frozen=True)
class Outcome:
    found: bool
    elapsed: float


def wait_until(check: Callable[[], bool], *, within: float, scale: float) -> Outcome:
    start = time.monotonic()
    deadline = start + within * scale
    while True:
        if check():
            return Outcome(True, time.monotonic() - start)
        if time.monotonic() >= deadline:
            return Outcome(False, time.monotonic() - start)
        time.sleep(INTERVAL)
