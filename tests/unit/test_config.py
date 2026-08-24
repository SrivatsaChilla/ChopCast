"""Tests for chopcast.config.Settings."""

from __future__ import annotations

import pytest

from chopcast.config import Settings
from chopcast.errors import ConfigError


def test_default_loads() -> None:
    s = Settings.load()
    assert s.collector.poll_seconds == 600
    assert s.collector.user_agent.startswith("chopcast/")
    assert s.evaluation.classes == ("None", "Light", "Moderate", "Severe")


def test_load_with_unknown_profile_raises() -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        Settings.load(profile="nonexistent-profile")


def test_env_overrides_take_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHOPCAST_COLLECTOR__POLL_SECONDS", "30")
    s = Settings.load()
    assert s.collector.poll_seconds == 30


def test_user_agent_cannot_be_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHOPCAST_COLLECTOR__USER_AGENT", "   ")
    with pytest.raises(Exception):  # pydantic ValidationError
        Settings.load()


def test_poll_seconds_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHOPCAST_COLLECTOR__POLL_SECONDS", "0")
    with pytest.raises(Exception):
        Settings.load()


def test_path_refs_are_resolved() -> None:
    s = Settings.load()
    # ${paths.root} should have been expanded away.
    assert "${paths.root}" not in s.paths.raw_db
    assert s.paths.raw_db.startswith(s.paths.root)
