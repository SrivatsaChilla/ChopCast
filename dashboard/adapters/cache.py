"""Optional short-TTL cache for expensive read-only aggregates.

There is no persistent cache and no write path. Keys include source mtimes so a
changed database or file invalidates the entry even within the TTL. The default
adapter uses per-request memoisation only; this is available for future use and
for tests.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def fingerprint(paths: tuple[Path, ...] | list[Path]) -> tuple[tuple[str, int, int], ...]:
    entries: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
            entries.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            entries.append((str(path), 0, 0))
    return tuple(entries)


class TTLCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: str, ttl_seconds: int, factory: Callable[[], T]) -> T:
        if ttl_seconds <= 0:
            return factory()
        now = time.monotonic()
        with self._lock:
            entry = self._values.get(key)
            if entry and entry[0] > now:
                return entry[1]
        value = factory()
        with self._lock:
            self._values[key] = (now + ttl_seconds, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
