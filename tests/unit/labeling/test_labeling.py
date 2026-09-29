"""Tests for chopcast.labeling.mapper and chopcast.labeling.combinations."""

from __future__ import annotations

from pathlib import Path

import pytest

from chopcast.errors import LabelingError
from chopcast.labeling.combinations import combine
from chopcast.labeling.mapper import map_to_severity
from chopcast.labeling.rules import load_rules


@pytest.fixture
def rules() -> object:
    return load_rules(Path("configs/labeling.yaml"))


def test_none_patterns(rules: object) -> None:
    assert map_to_severity("NEG", rules) == "None"
    assert map_to_severity("SMOOTH", rules) == "None"
    assert map_to_severity("TB NIL", rules) == "None"


def test_light_patterns(rules: object) -> None:
    assert map_to_severity("LGT", rules) == "Light"
    assert map_to_severity("LGT CHOP", rules) == "Light"
    assert map_to_severity("LIGHT", rules) == "Light"


def test_moderate_patterns(rules: object) -> None:
    assert map_to_severity("MOD", rules) == "Moderate"
    assert map_to_severity("MOD CHOP", rules) == "Moderate"
    assert map_to_severity("OCNL MOD", rules) == "Moderate"


def test_severe_patterns(rules: object) -> None:
    assert map_to_severity("SEV", rules) == "Severe"
    assert map_to_severity("EXTRM", rules) == "Severe"
    assert map_to_severity("SEVERE", rules) == "Severe"


def test_combination_max(rules: object) -> None:
    # "LGT-MOD" matches both Light and Moderate; max wins -> Moderate.
    assert map_to_severity("LGT-MOD", rules) == "Moderate"


def test_combination_max_picks_severe(rules: object) -> None:
    assert map_to_severity("MOD-SEV", rules) == "Severe"


def test_empty_returns_none(rules: object) -> None:
    assert map_to_severity(None, rules) == "None"
    assert map_to_severity("", rules) == "None"


def test_chop_only_label(rules: object) -> None:
    # Default config: chop_only_label=light
    assert map_to_severity("CHOP", rules) == "Light"


def test_unknown_returns_none_by_default(rules: object) -> None:
    assert map_to_severity("???WHAT???", rules) == "None"


def test_case_insensitive(rules: object) -> None:
    assert map_to_severity("lgt", rules) == "Light"
    assert map_to_severity("sev", rules) == "Severe"


def test_combine_max() -> None:
    assert combine(["Light", "Moderate"], "max") == "Moderate"
    assert combine(["Moderate", "Severe"], "max") == "Severe"


def test_combine_min() -> None:
    assert combine(["Light", "Moderate"], "min") == "Light"
    assert combine(["Moderate", "Severe"], "min") == "Moderate"


def test_combine_first() -> None:
    assert combine(["Moderate", "Light"], "first") == "Moderate"


def test_combine_empty() -> None:
    assert combine([], "max") == "None"


def test_load_rules_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LabelingError):
        load_rules(tmp_path / "missing.yaml")


def test_load_rules_invalid_combination_strategy(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: v1\ncombination_strategy: nonsense\nnone:\n  - NEG\n")
    with pytest.raises(LabelingError, match="combination_strategy"):
        load_rules(bad)