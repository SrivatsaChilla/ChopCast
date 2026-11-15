from __future__ import annotations

import os

import pytest

from adapters import clear_settings_cache
from adapters.settings import AdapterSettings
from tests.fixtures import build


@pytest.fixture(autouse=True)
def isolate_dashboard_env(monkeypatch):
    """Keep the developer's real CHOPCAST_DASHBOARD_* environment out of tests."""

    for key in list(os.environ):
        if key.startswith("CHOPCAST_DASHBOARD_"):
            monkeypatch.delenv(key, raising=False)
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def pipeline_root(tmp_path):
    root = tmp_path / "pipeline"
    build.target_db(root / "data" / "raw" / "pireps.db")
    return root


@pytest.fixture
def settings(pipeline_root):
    return AdapterSettings.from_env(pipeline_root)


@pytest.fixture
def full_root(tmp_path):
    return build.full_pipeline(tmp_path / "pipeline")


@pytest.fixture
def full_settings(full_root):
    return AdapterSettings.from_env(full_root)


@pytest.fixture
def empty_root(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    return root
