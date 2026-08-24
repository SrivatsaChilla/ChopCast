"""Navaid lookup.

A "navaid" is a published navigational aid with a known (lat, lon):
VORs, VORTACs, NDBs, and airports. The CSV comes from a public
FAA-style dataset; for now this module exposes a protocol so the
parser can depend on it without binding to a specific file format.

For M1 we ship an empty in-memory database. M2 will add the real CSV
loader once we've decided which dataset to vendor.

See `docs/MODULE_DESIGN.md` §3.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class NavaidEntry:
    """One navaid record."""

    code: str
    name: str
    lat: float
    lon: float


@runtime_checkable
class NavaidDatabase(Protocol):
    """Lookup interface used by the parser."""

    def lookup(self, code: str) -> tuple[float, float] | None:
        """Return (lat, lon) for the navaid or `None` if unknown."""


class InMemoryNavaidDatabase:
    """The default implementation. Backed by a plain dict."""

    def __init__(self, entries: list[NavaidEntry] | None = None) -> None:
        self._entries: dict[str, NavaidEntry] = {}
        if entries:
            for e in entries:
                self._entries[e.code.upper()] = e

    @classmethod
    def from_csv(cls, path: Path) -> "InMemoryNavaidDatabase":
        """Load from a CSV with columns `code,name,lat,lon`. Empty by default."""
        # Implementation deferred to M2 once a dataset is chosen.
        return cls()

    def lookup(self, code: str) -> tuple[float, float] | None:
        entry = self._entries.get(code.upper())
        if entry is None:
            return None
        return (entry.lat, entry.lon)

    def __len__(self) -> int:
        return len(self._entries)


__all__ = ["InMemoryNavaidDatabase", "NavaidDatabase", "NavaidEntry"]