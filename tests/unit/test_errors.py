"""Tests for chopcast.errors."""

from __future__ import annotations

import pytest

from chopcast.errors import (
    ChopcastError,
    ConfigError,
    FeatureBuildError,
    HttpError,
    LabelingError,
    LeakageError,
    ModelNotFound,
    ParseError,
    RateLimited,
    ValidationError,
)


def test_all_subclasses_inherit_from_base() -> None:
    for cls in (
        ConfigError,
        HttpError,
        RateLimited,
        ParseError,
        ValidationError,
        LabelingError,
        FeatureBuildError,
        ModelNotFound,
        LeakageError,
    ):
        assert issubclass(cls, ChopcastError)


def test_http_error_carries_status_and_url() -> None:
    e = HttpError("boom", status=500, url="https://example/")
    assert e.status == 500
    assert e.url == "https://example/"
    assert "boom" in str(e)


def test_validation_error_carries_field_and_value() -> None:
    e = ValidationError("bad lat", field="lat", value=999.0)
    assert e.field == "lat"
    assert e.value == 999.0


def test_parse_error_carries_raw_text_and_field() -> None:
    e = ParseError("missing /TM", raw_text="UA /OV SFO", field="obs_time")
    assert e.raw_text == "UA /OV SFO"
    assert e.field == "obs_time"


def test_chopcast_error_is_an_exception() -> None:
    with pytest.raises(ChopcastError):
        raise LeakageError("caught as base")
