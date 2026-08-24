"""Tests for chopcast.collector.validators."""

from __future__ import annotations

import pandas as pd

from chopcast.collector.validators import DefaultRowValidator
from chopcast.config import CollectorValidationConfig


def _row(**kwargs: object) -> pd.Series:
    return pd.Series(kwargs)


def _validator(
    *,
    require_raw_text: bool = True,
    require_obs_time: bool = False,
) -> DefaultRowValidator:
    return DefaultRowValidator(
        CollectorValidationConfig(
            require_raw_text=require_raw_text,
            require_obs_time=require_obs_time,
        )
    )


def test_valid_row_passes() -> None:
    v = _validator()
    assert v.validate(_row(raw_text="UA /OV SFO", lat=37.5, lon=-122.0)).ok


def test_missing_raw_text_rejected() -> None:
    v = _validator()
    result = v.validate(_row(raw_text=None, lat=37.5))
    assert not result.ok
    assert result.reason == "missing_raw_text"


def test_empty_raw_text_rejected() -> None:
    v = _validator()
    result = v.validate(_row(raw_text="   ", lat=37.5))
    assert not result.ok
    assert result.reason == "missing_raw_text"


def test_lat_out_of_range_rejected() -> None:
    v = _validator()
    result = v.validate(_row(raw_text="UA", lat=999.0))
    assert not result.ok
    assert result.reason == "invalid_lat"


def test_lon_out_of_range_rejected() -> None:
    v = _validator()
    result = v.validate(_row(raw_text="UA", lat=37.0, lon=-999.0))
    assert not result.ok
    assert result.reason == "invalid_lon"


def test_unparseable_lat_rejected() -> None:
    v = _validator()
    result = v.validate(_row(raw_text="UA", lat="not a number"))
    assert not result.ok
    assert result.reason == "invalid_lat"


def test_none_lat_passes() -> None:
    v = _validator()
    assert v.validate(_row(raw_text="UA", lat=None)).ok


def test_require_obs_time_when_configured() -> None:
    v = _validator(require_obs_time=True)
    assert not v.validate(_row(raw_text="UA", obs_time=None)).ok
    assert v.validate(_row(raw_text="UA", obs_time="2026-08-22T17:00:00Z")).ok
