"""Feature row construction.

A `FeatureRow` is the canonical, model-ready representation of a
PIREP. It is immutable and hashable so it can be safely compared,
deduplicated, and serialized.

The row contains:
- The report hash (so we can join back to raw).
- The cleaned text (without /TB).
- The severity label (None/Light/Moderate/Severe).
- A handful of structural features (altitude band, hour-of-day,
  day-of-year, aircraft type token).
- The obs_time and lat/lon, so downstream code can do spatial-temporal
  splits without re-reading the raw layer.

See `docs/MODULE_DESIGN.md` §5.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FeatureRow:
    """One model-ready PIREP record."""

    hash: str
    obs_time: datetime
    lat: float | None
    lon: float | None
    altitude_band: str | None
    aircraft_type: str | None
    report_type: str
    clean_text: str
    severity_label: str
    hour_of_day: int
    day_of_year: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "hash": self.hash,
            "obs_time": self.obs_time.isoformat(),
            "lat": self.lat,
            "lon": self.lon,
            "altitude_band": self.altitude_band,
            "aircraft_type": self.aircraft_type,
            "report_type": self.report_type,
            "clean_text": self.clean_text,
            "severity_label": self.severity_label,
            "hour_of_day": self.hour_of_day,
            "day_of_year": self.day_of_year,
        }


def altitude_band(altitude_ft: int | None, bands: tuple[tuple[int, int], ...]) -> str | None:
    """Bucket an altitude (feet MSL) into a named band.

    `bands` is a sorted list of `(low, high)` ranges. The first range
    that contains `altitude_ft` wins. Returns `None` if the altitude
    is missing or doesn't fit any band.
    """
    if altitude_ft is None:
        return None
    for low, high in bands:
        if low <= altitude_ft < high:
            return f"{low:05d}-{high:05d}"
    return None


__all__ = ["FeatureRow", "altitude_band"]