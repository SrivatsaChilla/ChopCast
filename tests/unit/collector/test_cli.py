"""Smoke tests for the top-level `chopcast` CLI."""

from __future__ import annotations

from click.testing import CliRunner

from chopcast.cli import root


def test_config_validate_succeeds() -> None:
    runner = CliRunner()
    result = runner.invoke(root, ["config", "validate"])
    assert result.exit_code == 0, result.output
    assert "valid" in result.output


def test_config_show_prints_yaml() -> None:
    runner = CliRunner()
    result = runner.invoke(root, ["config", "show"])
    assert result.exit_code == 0, result.output
    assert "collector:" in result.output


def test_config_show_section_filters() -> None:
    runner = CliRunner()
    result = runner.invoke(root, ["config", "show", "--section", "logging"])
    assert result.exit_code == 0, result.output
    assert "logging:" in result.output
    # Other sections should not be present.
    assert "collector:" not in result.output


def test_config_show_unknown_section_fails() -> None:
    runner = CliRunner()
    result = runner.invoke(root, ["config", "show", "--section", "bogus"])
    assert result.exit_code != 0
    assert "unknown section" in result.output


def test_paths_prints_resolved_paths() -> None:
    runner = CliRunner()
    result = runner.invoke(root, ["paths"])
    assert result.exit_code == 0, result.output
    assert "raw_db" in result.output
    assert "logs_dir" in result.output
