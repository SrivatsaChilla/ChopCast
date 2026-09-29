"""Working-set views: `pireps`, `trainable`, `wx_altitude`.

AIREPs are ~93% of collected rows and carry no prose, so they are noise for
the text model. They are never deleted: they hold ~99.8% of the temperature
and wind observations at flight level, and the AWC cache is a ~90-minute
rolling window with no backfill, so a deleted row is gone permanently.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from chopcast.storage.schema import SqliteReportStore

DB_NAME = "views.db"


def _insert(
    store: SqliteReportStore,
    *,
    hash: str,
    report_type: str,
    turbulence: str | None = None,
    turbulence_2: str | None = None,
    temp_c: float | None = None,
    wind_speed_kt: float | None = None,
) -> None:
    store.insert_report(
        hash=hash,
        fetched_at=datetime.now(timezone.utc),
        obs_time="2026-08-24T01:00:00Z",
        report_type=report_type,
        raw_text=f"UA /OV DEN /FL350 /TB {turbulence or 'NEG'}",
        turbulence=turbulence,
        turbulence_2=turbulence_2,
        turbulence_type="CHOP",
        turbulence_freq="OCNL",
        aircraft="B738",
        lat=39.9,
        lon=-104.7,
        altitude=35000.0,
        raw_json={"temp_c": temp_c, "wind_speed_kt": wind_speed_kt},
        source_url="https://example.invalid/cache.csv.gz",
    )


@pytest.fixture()
def con(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A populated store, plus a read connection that is always closed."""
    store = SqliteReportStore(tmp_path / DB_NAME)
    _insert(store, hash="a1", report_type="PIREP", turbulence="MOD")
    _insert(store, hash="a2", report_type="Urgent PIREP", turbulence="SEV")
    _insert(store, hash="a3", report_type="PIREP")                      # unlabeled
    _insert(store, hash="a4", report_type="PIREP", turbulence_2="LGT")  # 2nd layer only
    _insert(store, hash="a5", report_type="AIREP", temp_c=-52.9, wind_speed_kt=61.0)
    _insert(store, hash="a6", report_type="AIREP", turbulence="LGT")
    store.close()

    conn = sqlite3.connect(tmp_path / DB_NAME)
    try:
        yield conn
    finally:
        conn.close()


def test_views_exist(con: sqlite3.Connection) -> None:
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='view'")}
    assert {"pireps", "trainable", "wx_altitude"} <= names


def test_pireps_excludes_airep_and_keeps_urgent(con: sqlite3.Connection) -> None:
    kinds = {r[0] for r in con.execute("SELECT DISTINCT report_type FROM pireps")}
    assert kinds == {"PIREP", "Urgent PIREP"}


def test_trainable_requires_a_label_in_either_layer(con: sqlite3.Connection) -> None:
    hashes = {r[0] for r in con.execute("SELECT hash FROM trainable")}
    assert hashes == {"a1", "a2", "a4"}, "the second turbulence layer must count as labeled"
    assert "a3" not in hashes, "an unlabeled pilot report must be excluded"
    assert "a6" not in hashes, "a labeled AIREP is still not a pilot report"


def test_wx_altitude_reads_weather_out_of_raw_json(con: sqlite3.Connection) -> None:
    rows = con.execute(
        "SELECT hash, temp_c, wind_speed_kt FROM wx_altitude WHERE temp_c IS NOT NULL"
    ).fetchall()
    assert rows == [("a5", -52.9, 61.0)]


def test_nothing_is_deleted(con: sqlite3.Connection) -> None:
    assert con.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 6


def test_null_labels_are_sql_null_not_the_string_none(con: sqlite3.Connection) -> None:
    assert con.execute("SELECT COUNT(*) FROM reports WHERE turbulence = 'None'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM reports WHERE turbulence IS NULL").fetchone()[0] == 3
