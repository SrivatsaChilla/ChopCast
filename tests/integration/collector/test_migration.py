"""Integration test for scripts/migrate_legacy_db.

Builds a synthetic legacy pireps.db with the old schema, migrates it, and
verifies the rows land in the new store with the expected fields. Then runs
the migration a second time to confirm idempotence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chopcast.paths import Paths
from chopcast.storage.schema import SqliteReportStore
from scripts.migrate_legacy_db import LegacySchemaError, migrate


@pytest.fixture
def paths_under_tmp(tmp_path: Path) -> Paths:
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


def _build_legacy_db(path: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE reports (
                hash TEXT PRIMARY KEY,
                fetched_at TEXT NOT NULL,
                obs_time TEXT,
                report_type TEXT,
                raw_text TEXT,
                turbulence TEXT,
                aircraft TEXT,
                lat REAL,
                lon REAL,
                altitude REAL,
                raw_json TEXT
            );
            """
        )
        for r in rows:
            conn.execute(
                "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r["hash"],
                    r["fetched_at"],
                    r["obs_time"],
                    r["report_type"],
                    r["raw_text"],
                    r["turbulence"],
                    r["aircraft"],
                    r["lat"],
                    r["lon"],
                    r["altitude"],
                    r["raw_json"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _sample_rows() -> list[dict]:
    return [
        {
            "hash": "h1",
            "fetched_at": "2026-08-22T17:00:00+00:00",
            "obs_time": "2026-08-22T16:55:00Z",
            "report_type": "PIREP",
            "raw_text": "UA /OV SFO /TM 1655 /FL350 /TP B738 /TB MOD",
            "turbulence": "MOD",
            "aircraft": "B738",
            "lat": 37.5,
            "lon": -122.0,
            "altitude": 35000.0,
            "raw_json": '{"rawOb": "UA /OV SFO /TM 1655 /FL350 /TP B738 /TB MOD"}',
        },
        {
            "hash": "h2",
            "fetched_at": "2026-08-22T17:00:01+00:00",
            "obs_time": "2026-08-22T16:55:30Z",
            "report_type": "AIREP",
            "raw_text": "UA /OV OAK /TM 1655 /FL200 /TP A320 /TB LGT",
            "turbulence": "LGT",
            "aircraft": "A320",
            "lat": 37.7,
            "lon": -122.2,
            "altitude": 20000.0,
            "raw_json": '{"rawOb": "UA /OV OAK /TM 1655 /FL200 /TP A320 /TB LGT"}',
        },
    ]


def test_migrate_round_trip(tmp_path: Path, paths_under_tmp: Paths) -> None:
    legacy = tmp_path / "legacy.db"
    _build_legacy_db(legacy, _sample_rows())

    inserted, skipped = migrate(legacy, paths_under_tmp)
    assert inserted == 2
    assert skipped == 0

    # Verify the rows are in the new store with the expected defaults.
    new_store = SqliteReportStore(paths_under_tmp.raw_db_path, journal_mode="TRUNCATE")
    try:
        assert new_store.count() == 2
        conn = sqlite3.connect(paths_under_tmp.raw_db_path)
        try:
            rows = conn.execute(
                "SELECT hash, source_url, source_etag FROM reports ORDER BY hash"
            ).fetchall()
        finally:
            conn.close()
        # The default source_url marker identifies migrated rows.
        assert all(r[1] == "<legacy-migration>" for r in rows)
        assert all(r[2] is None for r in rows)
    finally:
        new_store.close()


def test_migrate_is_idempotent(tmp_path: Path, paths_under_tmp: Paths) -> None:
    legacy = tmp_path / "legacy.db"
    _build_legacy_db(legacy, _sample_rows())

    migrate(legacy, paths_under_tmp)
    inserted, skipped = migrate(legacy, paths_under_tmp)
    assert inserted == 0
    assert skipped == 2


def test_migrate_rejects_non_legacy_schema(tmp_path: Path, paths_under_tmp: Paths) -> None:
    bogus = tmp_path / "bogus.db"
    conn = sqlite3.connect(bogus)
    try:
        conn.execute("CREATE TABLE reports (only_one_column TEXT)")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(LegacySchemaError):
        migrate(bogus, paths_under_tmp)
