"""Tests for chopcast.paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from chopcast.paths import Paths


@pytest.fixture
def sample_paths(tmp_path: Path) -> Paths:
    """A `Paths` rooted at `tmp_path` with all subdirs already resolved."""
    return Paths(
        root=str(tmp_path),
        raw_db=str(tmp_path / "data/raw/pireps.db"),
        raw_dir=str(tmp_path / "data/raw"),
        processed_dir=str(tmp_path / "data/processed"),
        features_dir=str(tmp_path / "data/features"),
        models_dir=str(tmp_path / "models/registry"),
        registry_db=str(tmp_path / "models/registry/registry.db"),
        runs_dir=str(tmp_path / "runs"),
        logs_dir=str(tmp_path / "logs"),
        backups_dir=str(tmp_path / "backups"),
    )


def test_paths_resolve_absolute(sample_paths: Paths) -> None:
    p = sample_paths.raw_db_path
    assert p.is_absolute()
    # Use Path comparison rather than string endswith; Windows normalises
    # slashes when converting Path -> str.
    assert p.parts[-3:] == ("data", "raw", "pireps.db")


def test_paths_are_frozen(sample_paths: Paths) -> None:
    with pytest.raises(Exception):  # pydantic FrozenInstanceError
        sample_paths.root = "/tmp"  # type: ignore[misc]


def test_ensure_dirs_is_idempotent(sample_paths: Paths) -> None:
    sample_paths.ensure_dirs()
    sample_paths.ensure_dirs()  # second call must not raise
    assert sample_paths.raw_dir_path.is_dir()
    assert sample_paths.logs_dir_path.is_dir()
