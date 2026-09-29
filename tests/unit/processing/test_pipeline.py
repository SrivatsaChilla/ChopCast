"""Tests for chopcast.processing.pipeline and feature_store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chopcast.config import LabelingConfig, ProcessingConfig
from chopcast.data.feature_store import (
    DatasetResult,
    FeatureStoreConfig,
    build_dataset,
    stream_features,
)
from chopcast.data.version import derive_version
from chopcast.processing.features import FeatureRow, altitude_band
from chopcast.processing.pipeline import build_deps, process


# ---------------------------------------------------------------------------
# altitude_band
# ---------------------------------------------------------------------------
def test_altitude_band_picks_first_matching_range() -> None:
    bands = ((0, 20000), (20000, 30000), (30000, 40000), (40000, 60000))
    assert altitude_band(15000, bands) == "00000-20000"
    assert altitude_band(25000, bands) == "20000-30000"
    assert altitude_band(35000, bands) == "30000-40000"
    assert altitude_band(45000, bands) == "40000-60000"


def test_altitude_band_none_for_missing() -> None:
    assert altitude_band(None, ((0, 10000),)) is None


def test_altitude_band_none_for_out_of_range() -> None:
    assert altitude_band(70000, ((0, 60000),)) is None


# ---------------------------------------------------------------------------
# derive_version
# ---------------------------------------------------------------------------
def test_derive_version_is_deterministic() -> None:
    cfg = ProcessingConfig()
    v1 = derive_version(cfg)
    v2 = derive_version(cfg)
    assert v1.content_hash == v2.content_hash


def test_derive_version_changes_with_salt() -> None:
    cfg = ProcessingConfig()
    assert derive_version(cfg, salt="x") != derive_version(cfg, salt="y")


def test_derive_version_changes_with_config_change() -> None:
    v1 = derive_version(ProcessingConfig())
    cfg2 = ProcessingConfig()
    # Force a config change: bump cleaner version.
    object.__setattr__(cfg2, "cleaner_version", "v2-test")
    v2 = derive_version(cfg2)
    assert v1.content_hash != v2.content_hash


# ---------------------------------------------------------------------------
# build_dataset / process end-to-end
# ---------------------------------------------------------------------------
@pytest.fixture
def deps() -> object:
    return build_deps(ProcessingConfig(), LabelingConfig(), path_root=".")


def _row(**overrides) -> dict:
    base = {
        "hash": "a" * 64,
        "obs_time": "2026-08-22T17:00:00Z",
        "raw_text": "UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP /RM SMOOTH",
        "report_type": "PIREP",
        "aircraft": "B738",
        "lat": 37.5,
        "lon": -122.0,
        "altitude": 35000,
    }
    base.update(overrides)
    return base


def test_process_emits_feature_row(deps: object) -> None:
    feature = process(_row(), deps)
    assert isinstance(feature, FeatureRow)
    assert feature.severity_label == "Moderate"
    assert feature.altitude_band == "30000-40000"
    assert "/TB" not in feature.clean_text
    assert "MOD CHOP" not in feature.clean_text
    assert feature.hour_of_day == 17


def test_process_returns_none_on_missing_obs_time(deps: object) -> None:
    assert process(_row(obs_time=None), deps) is None


def test_process_returns_none_on_missing_raw_text(deps: object) -> None:
    assert process(_row(raw_text=None), deps) is None


def test_process_returns_none_on_unparseable(deps: object) -> None:
    assert process(_row(raw_text="no slashes here"), deps) is None


def test_process_severity_severe(deps: object) -> None:
    feature = process(_row(raw_text="UA /OV SFO /TB SEV"), deps)
    assert feature is not None
    assert feature.severity_label == "Severe"


def test_process_severity_none(deps: object) -> None:
    feature = process(_row(raw_text="UA /OV SFO /TB NEG"), deps)
    assert feature is not None
    assert feature.severity_label == "None"


def test_stream_features(deps: object) -> None:
    rows = [_row(hash=("a" * 64)), _row(hash=("b" * 64), raw_text="UA /TB LGT"), _row(hash=("c" * 64), raw_text="garbage")]
    out = list(stream_features(rows, deps))
    assert len(out) == 2
    assert all(isinstance(f, FeatureRow) for f in out)


def test_build_dataset_writes_versioned_jsonl(tmp_path: Path) -> None:
    cfg = FeatureStoreConfig(
        processing=ProcessingConfig(),
        labeling=LabelingConfig(),
        output_dir=tmp_path,
        path_root=".",
    )
    rows = [
        _row(hash="a" * 64),
        _row(hash="b" * 64, raw_text="UA /OV OAK /TB LGT"),
        _row(hash="c" * 64, raw_text="UA /OV SJC /TB NEG"),
        _row(hash="d" * 64, obs_time=None),  # rejected
    ]
    result = build_dataset(rows, cfg)
    assert isinstance(result, DatasetResult)
    assert result.rows_written == 3
    assert result.rows_rejected == 1
    assert result.output_path.exists()
    lines = result.output_path.read_text().splitlines()
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)
        assert "severity_label" in record
        assert "/TB" not in record["clean_text"]