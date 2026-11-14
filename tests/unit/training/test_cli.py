"""Tests for the chopcast-train CLI."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from chopcast.config import Settings
from chopcast.storage.schema import SqliteReportStore
from chopcast.training.cli import cli


def _add(store: SqliteReportStore, h: str, report_type: str, raw_text: str, turbulence: str | None) -> None:
    store.insert_report(
        hash=h,
        fetched_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        obs_time="2026-11-01T12:00:00Z",
        report_type=report_type,
        raw_text=raw_text,
        turbulence=turbulence,
        aircraft="B738",
        lat=40.0,
        lon=-100.0,
        altitude=35000.0,
        raw_json={},
        source_url="test",
    )


@pytest.fixture
def db_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CHOPCAST_PATHS__ROOT", str(tmp_path))
    (tmp_path / "configs").mkdir()
    shutil.copy("configs/labeling.yaml", tmp_path / "configs")  # rules live under paths.root
    db = Settings.load().to_paths().raw_db_path
    db.parent.mkdir(parents=True)
    store = SqliteReportStore(db)
    _add(store, "a" * 64, "PIREP", "DEN UA /OV DEN/TM 1200/FL350/TP B738/TB MOD", "MOD")
    _add(store, "b" * 64, "PIREP", "DEN UA /OV DEN/TM 1200/FL350/TP B738/RM CLEAR", None)
    _add(store, "c" * 64, "AIREP", "ARP UAL1 4000N 10000W 1200 F350 MS50", None)
    store.close()
    return tmp_path


def _rows(out_dir: Path) -> list[dict]:
    (path,) = out_dir.glob("features_*.jsonl")
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_features_builds_from_pilot_reports_only(db_root: Path) -> None:
    result = CliRunner().invoke(cli, ["features"])
    assert result.exit_code == 0, result.output
    rows = _rows(Settings.load().to_paths().features_dir_path)
    assert {r["hash"][0] for r in rows} == {"a", "b"}


def test_features_labeled_only_skips_reports_without_turbulence(db_root: Path) -> None:
    result = CliRunner().invoke(cli, ["features", "--labeled-only"])
    assert result.exit_code == 0, result.output
    rows = _rows(Settings.load().to_paths().features_dir_path)
    assert [r["severity_label"] for r in rows] == ["Moderate"]
