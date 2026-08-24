"""Shared pytest fixtures.

The fixtures here are intentionally minimal. Per-module fixtures live in
`tests/unit/<module>/conftest.py` or at the top of the test file.

See docs/TESTING.md §3.2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytest

from chopcast.config import Settings
from chopcast.paths import Paths
from chopcast.storage.schema import SqliteReportStore


@pytest.fixture
def tmp_db(tmp_path: Path) -> Iterator[Path]:
    """An empty SQLite path. The DB is not opened; the test does that."""
    yield tmp_path / "test.db"


@pytest.fixture
def store(tmp_db: Path) -> Iterator[SqliteReportStore]:
    """A `SqliteReportStore` rooted at a temp file. Auto-closed."""
    s = SqliteReportStore(tmp_db, journal_mode="TRUNCATE")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def settings() -> Settings:
    """A `Settings` with all defaults. Loaded from configs/default.yaml."""
    return Settings.load()


@pytest.fixture
def paths(settings: Settings) -> Paths:
    return settings.to_paths()


@pytest.fixture
def utc_now() -> datetime:
    return datetime(2026, 8, 22, 17, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def synthetic_batch() -> pd.DataFrame:
    """Five rows that mimic AWC's cache shape. Used by collector tests."""
    rows = []
    for i in range(5):
        rows.append(
            {
                "rawOb": f"UA /OV SFO{i:03d} /TM 1425 /FL350 /TP B738 /TB MOD CHOP report {i}",
                "obsTime": f"2026-08-22T1{i % 10}:25:00Z",
                "reportType": "PIREP" if i % 3 else "AIREP",
                "acType": ["B738", "C172", "A320"][i % 3],
                "lat": 37.5 + i * 0.1,
                "lon": -122.0 - i * 0.1,
                "fltLvl": 35000 - i * 1000,
                "turbulence": [None, "LGT", "MOD", "SEV", "LGT-MOD"][i % 5],
            }
        )
    return pd.DataFrame(rows)
