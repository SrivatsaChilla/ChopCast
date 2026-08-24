"""Tests for chopcast.storage.schema.SqliteReportStore."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from chopcast.storage.schema import SqliteReportStore


def test_creates_schema_on_open(tmp_db: Path) -> None:
    """Opening a store at a new path creates the schema and indexes."""
    s = SqliteReportStore(tmp_db, journal_mode="TRUNCATE")
    try:
        # The `reports` and `runs` tables should exist.
        conn = sqlite3.connect(s._path)  # noqa: SLF001  # internal but read-only
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        assert "reports" in tables
        assert "runs" in tables
        assert "rejected" in tables
        assert "schema_migrations" in tables
    finally:
        s.close()


def test_insert_and_count(store: SqliteReportStore, utc_now: datetime) -> None:
    assert store.count() == 0
    inserted = store.insert_report(
        hash="abc",
        fetched_at=utc_now,
        obs_time="2026-08-22T17:00:00Z",
        report_type="PIREP",
        raw_text="UA /OV SFO",
        turbulence="MOD",
        aircraft="B738",
        lat=37.5,
        lon=-122.0,
        altitude=35000.0,
        raw_json={"rawOb": "UA /OV SFO"},
        source_url="https://example.test/",
    )
    assert inserted is True
    assert store.count() == 1


def test_duplicate_hash_is_ignored(store: SqliteReportStore, utc_now: datetime) -> None:
    kwargs = dict(
        hash="dup",
        fetched_at=utc_now,
        obs_time="2026-08-22T17:00:00Z",
        report_type=None,
        raw_text="UA /OV SFO",
        turbulence=None,
        aircraft=None,
        lat=None,
        lon=None,
        altitude=None,
        raw_json={},
        source_url="https://example.test/",
    )
    assert store.insert_report(**kwargs) is True
    assert store.insert_report(**kwargs) is False
    assert store.count() == 1


def test_lat_out_of_range_rejected_by_sqlite_constraint(tmp_db: Path, utc_now: datetime) -> None:
    s = SqliteReportStore(tmp_db, journal_mode="TRUNCATE")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            s.insert_report(
                hash="bad",
                fetched_at=utc_now,
                obs_time=None,
                report_type=None,
                raw_text="UA",
                turbulence=None,
                aircraft=None,
                lat=999.0,
                lon=-122.0,
                altitude=None,
                raw_json={},
                source_url="x",
            )
    finally:
        s.close()


def test_rejected_table_is_written(store: SqliteReportStore, utc_now: datetime) -> None:
    store.insert_rejected(
        fetched_at=utc_now,
        reason="invalid_lat",
        raw_row={"rawOb": "UA"},
        source_url="https://example.test/",
        detail="lat=999.0 not in [-90, 90]",
    )
    conn = sqlite3.connect(store._path)  # noqa: SLF001 — internal but read-only here
    try:
        rows = conn.execute("SELECT reason, detail FROM rejected").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "invalid_lat"
    finally:
        conn.close()


def test_runs_table_records_cycle(store: SqliteReportStore, utc_now: datetime) -> None:
    run_id = store.begin_run(utc_now)
    store.finish_run(
        run_id,
        finished_at=utc_now,
        status="ok",
        rows_seen=10,
        rows_inserted=8,
        rows_skipped=2,
        rows_rejected=0,
    )
    last = store.last_runs(1)
    assert len(last) == 1
    assert last[0].status == "ok"
    assert last[0].rows_inserted == 8
