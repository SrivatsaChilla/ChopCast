"""Content-addressed hashing for PIREPs.

The dedup key is `sha256(obs_time | "|" | lat_rounded | "|" | lon_rounded | "|" | normalized_raw_text)`.

See ADR-0004 and docs/DATA_ENGINEERING.md §3.
"""

from __future__ import annotations

import hashlib
from typing import Final

from chopcast.errors import ValidationError


_PIPE: Final = " | "


def _round(value: float | int | None, decimals: int) -> str:
    if value is None:
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    # NaN handling
    if f != f:
        return ""
    return f"{f:.{decimals}f}"


def _normalize_text(text: str) -> str:
    """Lowercase and collapse internal whitespace. Preserve content otherwise.

    We do not rewrite semantically (e.g., we do not touch `/TB` or `/OV`).
    The purpose of normalization is to make the hash stable across
    trivial casing/whitespace differences.
    """
    return " ".join(text.lower().split())


def report_hash(
    obs_time: str | None,
    lat: float | int | None,
    lon: float | int | None,
    raw_text: str | None,
    *,
    lat_decimals: int = 4,
    lon_decimals: int = 4,
) -> str:
    """Compute the SHA-256 content hash of a PIREP.

    Args:
        obs_time: ISO 8601 UTC observation time. May not be empty.
        lat: Latitude in decimal degrees, or None if unknown.
        lon: Longitude in decimal degrees, or None if unknown.
        raw_text: The raw "/"-delimited PIREP string. May not be empty.
        lat_decimals: Precision to round latitude to (default 4, ~11 m).
        lon_decimals: Precision to round longitude to (default 4, ~11 m).

    Returns:
        A 64-character hex SHA-256 digest.

    Raises:
        ValidationError: If `obs_time` or `raw_text` is missing.
    """
    if not obs_time or not obs_time.strip():
        raise ValidationError("obs_time is required for hashing", field="obs_time", value=obs_time)
    if not raw_text or not raw_text.strip():
        raise ValidationError("raw_text is required for hashing", field="raw_text", value=raw_text)

    parts = (
        obs_time.strip(),
        _round(lat, lat_decimals),
        _round(lon, lon_decimals),
        _normalize_text(raw_text),
    )
    payload = _PIPE.join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = ["report_hash"]
