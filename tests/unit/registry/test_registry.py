"""Tests for chopcast.registry.store."""

from __future__ import annotations

from pathlib import Path

import pytest

from chopcast.registry.store import SqliteModelRegistry


@pytest.fixture
def reg(tmp_path: Path) -> SqliteModelRegistry:
    return SqliteModelRegistry(tmp_path / "registry.db")


def test_register_returns_id(reg: SqliteModelRegistry) -> None:
    mid = reg.register(
        model_version="v1",
        model_kind="baseline",
        feature_version="fv1",
        metrics={"acc": 0.9},
        artifact_path=Path("/tmp/artefact"),
    )
    assert isinstance(mid, int)
    assert mid >= 1


def test_get_returns_record(reg: SqliteModelRegistry) -> None:
    mid = reg.register(
        model_version="v1",
        model_kind="baseline",
        feature_version="fv1",
        metrics={"acc": 0.9},
        artifact_path=Path("/tmp/artefact"),
        notes="first model",
    )
    rec = reg.get(mid)
    assert rec is not None
    assert rec.model_version == "v1"
    assert rec.model_kind == "baseline"
    assert rec.metrics == {"acc": 0.9}
    assert rec.notes == "first model"


def test_promote_sets_current(reg: SqliteModelRegistry) -> None:
    mid = reg.register(
        model_version="v1",
        model_kind="baseline",
        feature_version="fv1",
        metrics={},
        artifact_path=Path("/tmp"),
    )
    reg.promote(mid, tag="production")
    cur = reg.current("production")
    assert cur is not None
    assert cur.id == mid


def test_promote_replaces_previous(reg: SqliteModelRegistry) -> None:
    m1 = reg.register(
        model_version="v1",
        model_kind="baseline",
        feature_version="fv1",
        metrics={},
        artifact_path=Path("/tmp"),
    )
    m2 = reg.register(
        model_version="v2",
        model_kind="baseline",
        feature_version="fv1",
        metrics={},
        artifact_path=Path("/tmp"),
    )
    reg.promote(m1, tag="production")
    reg.promote(m2, tag="production")
    assert reg.current("production").id == m2


def test_current_returns_none_when_unset(reg: SqliteModelRegistry) -> None:
    assert reg.current("production") is None


def test_promote_unknown_model_raises(reg: SqliteModelRegistry) -> None:
    with pytest.raises(KeyError):
        reg.promote(999, tag="production")


def test_list_filters_by_kind(reg: SqliteModelRegistry) -> None:
    reg.register(
        model_version="v1",
        model_kind="baseline",
        feature_version="fv1",
        metrics={},
        artifact_path=Path("/tmp"),
    )
    reg.register(
        model_version="v2",
        model_kind="transformer",
        feature_version="fv1",
        metrics={},
        artifact_path=Path("/tmp"),
    )
    only_baseline = reg.list(model_kind="baseline")
    assert len(only_baseline) == 1
    assert only_baseline[0].model_kind == "baseline"


def test_unique_per_kind_version(reg: SqliteModelRegistry) -> None:
    reg.register(
        model_version="v1",
        model_kind="baseline",
        feature_version="fv1",
        metrics={},
        artifact_path=Path("/tmp"),
    )
    with pytest.raises(Exception):
        reg.register(
            model_version="v1",
            model_kind="baseline",
            feature_version="fv1",
            metrics={},
            artifact_path=Path("/tmp"),
        )


def test_registry_survives_reopen(tmp_path: Path) -> None:
    p = tmp_path / "r.db"
    r1 = SqliteModelRegistry(p)
    r1.register(
        model_version="v1",
        model_kind="baseline",
        feature_version="fv1",
        metrics={"x": 1},
        artifact_path=Path("/tmp"),
    )
    r1.close()
    r2 = SqliteModelRegistry(p)
    try:
        rows = r2.list()
        assert len(rows) == 1
        assert rows[0].metrics == {"x": 1}
    finally:
        r2.close()