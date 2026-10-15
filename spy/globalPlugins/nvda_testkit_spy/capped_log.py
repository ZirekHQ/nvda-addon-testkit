# coding: utf-8
"""A thread-safe, size-capped, append-only log with stable absolute indices."""

from __future__ import annotations

import threading
from typing import Any

DEFAULT_CAPACITY = 10000


class CappedLog:
    """Keeps the newest `capacity` entries; indices keep counting past evictions.

    `index()` is the position the next append will take, so a host that stored
    an index before an eviction still gets everything newer than it.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._capacity = capacity
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = []
        self._dropped = 0

    def append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(entry)
            overflow = len(self._items) - self._capacity
            if overflow > 0:
                del self._items[:overflow]
                self._dropped += overflow

    def index(self) -> int:
        with self._lock:
            return self._dropped + len(self._items)

    def since(self, index: int) -> list[dict[str, Any]]:
        with self._lock:
            start = max(0, index - self._dropped)
            return [dict(entry) for entry in self._items[start:]]

    def mark_last(self, **fields: Any) -> bool:
        with self._lock:
            if not self._items:
                return False
            self._items[-1].update(fields)
            return True

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._dropped = 0
