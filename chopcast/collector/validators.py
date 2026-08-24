"""Row-level validation.

Validators never raise; they return a `Verdict`. The collector decides
what to do with rejected rows (quarantine, log, drop).

See docs/MODULE_DESIGN.md §2.2.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from chopcast.config import CollectorValidationConfig


@dataclass(frozen=True)
class Verdict:
    """The result of validating one row.

    Attributes:
        ok: True if the row passes all checks; False otherwise.
        reason: A short, snake_case identifier of the failing rule, or None
            if `ok` is True. Examples: `invalid_lat`, `missing_raw_text`.
        detail: A human-readable explanation, or None.
    """

    ok: bool
    reason: str | None = None
    detail: str | None = None


class RowValidator:
    """Protocol for one-row validators."""

    def validate(self, row: pd.Series) -> Verdict:  # pragma: no cover - protocol
        ...


class DefaultRowValidator:
    """The default validator. Checks coordinates, raw text, and obs_time.

    Configuration is taken from `CollectorValidationConfig`. The validator
    returns a `Verdict(ok=False, reason="...")` on the first failure and
    does not enumerate all problems at once.
    """

    def __init__(self, config: CollectorValidationConfig) -> None:
        self._config = config

    def validate(self, row: pd.Series) -> Verdict:
        if self._config.require_raw_text:
            raw = row.get("raw_text")
            if raw is None or (isinstance(raw, float) and pd.isna(raw)) or not str(raw).strip():
                return Verdict(ok=False, reason="missing_raw_text", detail="raw_text is empty")

        if self._config.require_obs_time:
            obs = row.get("obs_time")
            if obs is None or (isinstance(obs, float) and pd.isna(obs)) or not str(obs).strip():
                return Verdict(ok=False, reason="missing_obs_time", detail="obs_time is empty")

        lat = row.get("lat")
        if lat is not None and not (isinstance(lat, float) and pd.isna(lat)):
            try:
                lat_f = float(lat)
            except (TypeError, ValueError):
                return Verdict(ok=False, reason="invalid_lat", detail=f"lat={lat!r}")
            lo, hi = self._config.lat_range
            if not (lo <= lat_f <= hi):
                return Verdict(
                    ok=False,
                    reason="invalid_lat",
                    detail=f"lat={lat_f} not in [{lo}, {hi}]",
                )

        lon = row.get("lon")
        if lon is not None and not (isinstance(lon, float) and pd.isna(lon)):
            try:
                lon_f = float(lon)
            except (TypeError, ValueError):
                return Verdict(ok=False, reason="invalid_lon", detail=f"lon={lon!r}")
            lo, hi = self._config.lon_range
            if not (lo <= lon_f <= hi):
                return Verdict(
                    ok=False,
                    reason="invalid_lon",
                    detail=f"lon={lon_f} not in [{lo}, {hi}]",
                )

        return Verdict(ok=True)


__all__ = ["DefaultRowValidator", "RowValidator", "Verdict"]
