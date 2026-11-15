"""Safe parsing of untrusted query-string values.

Invalid values fall back to defaults; no query parameter can produce a 400 or a
500. Identifiers from the whitelist only reach SQL.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Mapping

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HASH = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def get_str(
    params: Mapping[str, Any],
    key: str,
    default: str = "",
    *,
    allowed: set[str] | None = None,
    max_len: int = 200,
) -> str:
    raw = params.get(key)
    if raw is None:
        return default
    value = str(raw).strip()[:max_len]
    if allowed is not None and value and value not in allowed:
        return default
    return value


def get_int(
    params: Mapping[str, Any],
    key: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int = 10_000,
) -> int:
    raw = params.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def get_float(
    params: Mapping[str, Any],
    key: str,
    default: float | None = None,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    raw = params.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(str(raw))
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_bool(params: Mapping[str, Any], key: str, default: bool = False) -> bool:
    raw = params.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def get_date(params: Mapping[str, Any], key: str) -> str:
    value = get_str(params, key, max_len=10)
    if not DATE.match(value):
        return ""
    try:
        date.fromisoformat(value)
    except ValueError:
        return ""
    return value


def get_hash(value: str) -> str | None:
    value = (value or "").strip()
    return value if HASH.match(value) else None


def page_number(params: Mapping[str, Any]) -> int:
    return get_int(params, "page", 1, minimum=1, maximum=1_000_000)


def page_size(params: Mapping[str, Any], default: int, maximum: int) -> int:
    value = get_int(params, "page_size", default, minimum=5, maximum=maximum)
    allowed = {5, 10, 25, 50, 100, 200}
    return value if value in allowed else default


def bbox(params: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    raw = params.get("bbox")
    if not raw:
        return None
    parts = str(raw).split(",")
    if len(parts) != 4:
        return None
    try:
        min_lat, min_lon, max_lat, max_lon = (float(p) for p in parts)
    except ValueError:
        return None
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        return None
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        return None
    if min_lat > max_lat or min_lon > max_lon:
        return None
    return (min_lat, min_lon, max_lat, max_lon)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
