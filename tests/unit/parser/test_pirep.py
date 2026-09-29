"""Tests for chopcast.parser.pirep."""

from __future__ import annotations

import pytest

from chopcast.parser.pirep import PirepFields, parse_pirep


def test_full_pirep_parses_all_fields() -> None:
    raw = "UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP /RM SMOOTH RIDE"
    fields = parse_pirep(raw)
    assert isinstance(fields, PirepFields)
    assert fields.location == "SFO"
    assert fields.obs_time is not None and fields.obs_time.hour == 14 and fields.obs_time.minute == 25
    assert fields.flight_level == 35000
    assert fields.aircraft_type == "B738"
    assert fields.turbulence == "MOD CHOP"
    assert fields.remarks == "SMOOTH RIDE"
    assert fields.raw == raw


def test_glued_flight_level() -> None:
    fields = parse_pirep("UA /OV SFO /FL350 /TP B738")
    assert fields.flight_level == 35000


def test_space_flight_level() -> None:
    fields = parse_pirep("UA /OV SFO /FL 350 /TP B738")
    assert fields.flight_level == 35000


def test_flight_level_unknown_returns_none() -> None:
    fields = parse_pirep("UA /OV SFO /FLUNKN /TP B738")
    assert fields.flight_level is None


def test_flight_level_in_hundreds_below_600() -> None:
    # "FL 250" without "FL" prefix and digit < 600 is treated as FL.
    fields = parse_pirep("UA /OV SFO /TM 1500 /FL 250 /TP C172")
    assert fields.flight_level == 25000


def test_relative_location_not_split() -> None:
    # SFO030020 is one token; the parser must not break it.
    fields = parse_pirep("UA /OV SFO030020 /TM 1425")
    assert fields.location == "SFO030020"


def test_turbulence_only() -> None:
    fields = parse_pirep("UA /TB MOD")
    assert fields.turbulence == "MOD"


def test_missing_fields_become_none() -> None:
    fields = parse_pirep("UA /OV SFO /TP B738")
    assert fields.location == "SFO"
    assert fields.aircraft_type == "B738"
    assert fields.turbulence is None
    assert fields.flight_level is None
    assert fields.obs_time is None


def test_unparseable_raises_value_error() -> None:
    with pytest.raises(ValueError, match="no recognised slash fields"):
        parse_pirep("garbage with no slashes at all")


def test_temperature_with_sign() -> None:
    fields = parse_pirep("UA /TA -42")
    assert fields.temperature == -42


def test_icing_preserved() -> None:
    fields = parse_pirep("UA /IC MOD")
    assert fields.icing == "MOD"


def test_sky_conditions_preserved() -> None:
    fields = parse_pirep("UA /SK BKN040")
    assert fields.sky_conditions == "BKN040"


def test_remarks_can_contain_internal_spaces() -> None:
    fields = parse_pirep("UA /RM SMOOTH RIDE EXCEPT LAST 30 MIN")
    assert fields.remarks == "SMOOTH RIDE EXCEPT LAST 30 MIN"


def test_case_insensitive_keys() -> None:
    fields = parse_pirep("ua /ov sfo /tm 1425 /tb mod")
    assert fields.location == "sfo"
    assert fields.turbulence == "mod"