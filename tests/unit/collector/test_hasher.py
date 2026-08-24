"""Tests for chopcast.collector.hasher."""

from __future__ import annotations

import pytest

from chopcast.collector.hasher import report_hash
from chopcast.errors import ValidationError


def test_deterministic() -> None:
    a = report_hash("2026-08-22T17:00:00Z", 37.5, -122.0, "UA /OV SFO /TB MOD")
    b = report_hash("2026-08-22T17:00:00Z", 37.5, -122.0, "UA /OV SFO /TB MOD")
    assert a == b
    assert len(a) == 64


def test_case_and_whitespace_normalisation() -> None:
    a = report_hash("2026-08-22T17:00:00Z", 37.5, -122.0, "UA /OV SFO /TB MOD")
    b = report_hash("2026-08-22T17:00:00Z", 37.5, -122.0, "  ua  /ov  sfo  /tb  mod  ")
    assert a == b


def test_lat_lon_rounded_to_decimals() -> None:
    # At 5-decimal precision, two values that are 0.00001 apart should
    # produce different hashes.
    a = report_hash("2026-08-22T17:00:00Z", 37.50000, -122.00000, "UA", lat_decimals=5)
    b = report_hash("2026-08-22T17:00:00Z", 37.50001, -122.00000, "UA", lat_decimals=5)
    assert a != b


def test_lat_lon_at_default_precision_collide() -> None:
    # Two values within 4-decimal rounding should produce the same hash.
    a = report_hash("2026-08-22T17:00:00Z", 37.50000, -122.00000, "UA")
    b = report_hash("2026-08-22T17:00:00Z", 37.50004, -122.00000, "UA")
    assert a == b


def test_missing_obs_time_raises() -> None:
    with pytest.raises(ValidationError) as e:
        report_hash("", 37.5, -122.0, "UA")
    assert e.value.field == "obs_time"


def test_missing_raw_text_raises() -> None:
    with pytest.raises(ValidationError) as e:
        report_hash("2026-08-22T17:00:00Z", 37.5, -122.0, "")
    assert e.value.field == "raw_text"


def test_none_lat_lon_handled() -> None:
    h = report_hash("2026-08-22T17:00:00Z", None, None, "UA /OV SFO")
    assert isinstance(h, str) and len(h) == 64


def test_custom_decimal_precision() -> None:
    a = report_hash("2026-08-22T17:00:00Z", 37.500001, -122.0, "UA", lat_decimals=6)
    b = report_hash("2026-08-22T17:00:00Z", 37.500002, -122.0, "UA", lat_decimals=6)
    assert a != b
