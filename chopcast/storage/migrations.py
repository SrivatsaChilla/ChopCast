"""Versioned SQLite migrations.

Forward-only by default. Reverse migrations require explicit justification
and a test.

See docs/DATA_ENGINEERING.md §2.3.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True)
class Migration:
    """One versioned schema change."""

    version: int
    name: str
    sql: str


# ---------------------------------------------------------------------------
# Migration list. Append new entries; never reorder or edit existing ones.
# A new migration must have a higher version than any current migration.
# ---------------------------------------------------------------------------
MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="initial_schema",
        sql=(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                applied_at  TEXT NOT NULL
            );
            """
        ),
    ),
    Migration(
        version=2,
        name="add_turbulence_layers",
        sql=(
            """
            -- Migrations may run against a bare connection (before the
            -- base SCHEMA is applied), so this migration is self-contained:
            -- it ensures the table exists, then evolves it.
            CREATE TABLE IF NOT EXISTS reports (
                hash          TEXT PRIMARY KEY,
                fetched_at    TEXT NOT NULL,
                obs_time      TEXT,
                report_type   TEXT,
                raw_text      TEXT,
                turbulence    TEXT,
                aircraft      TEXT,
                lat           REAL,
                lon           REAL,
                altitude      REAL,
                raw_json      TEXT NOT NULL,
                source_url    TEXT NOT NULL,
                source_etag   TEXT,
                CONSTRAINT lat_range CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
                CONSTRAINT lon_range CHECK (lon IS NULL OR lon BETWEEN -180 AND 180)
            );
            ALTER TABLE reports ADD COLUMN turbulence_2 TEXT;
            ALTER TABLE reports ADD COLUMN turbulence_type TEXT;
            ALTER TABLE reports ADD COLUMN turbulence_freq TEXT;
            """
        ),
    ),
    Migration(
        version=3,
        name="working_set_views",
        sql=(
            """
            -- AIREPs are ~93% of rows and carry no prose, so they are noise
            -- for the text model. They are NOT deleted: they hold 99.8% of
            -- the temp/wind observations at flight level. Filter, never drop.
            -- 'AIREP' does not match '%PIREP%'; 'Urgent PIREP' does.
            CREATE VIEW IF NOT EXISTS pireps AS
                SELECT * FROM reports WHERE report_type LIKE '%PIREP%';

            -- The supervised working set. /TB is deliberately still present
            -- in raw_text: removing it is chopcast.processing.cleaner's job
            -- and its alone (ADR-0003).
            CREATE VIEW IF NOT EXISTS trainable AS
                SELECT hash, obs_time, raw_text,
                       turbulence, turbulence_2, turbulence_type, turbulence_freq,
                       aircraft, lat, lon, altitude
                FROM pireps
                WHERE turbulence IS NOT NULL OR turbulence_2 IS NOT NULL;

            -- AIREPs as atmospheric observations. temp/wind are not typed
            -- columns, so they are read back out of raw_json.
            CREATE VIEW IF NOT EXISTS wx_altitude AS
                SELECT hash, obs_time, lat, lon, altitude,
                       CAST(json_extract(raw_json,'$.temp_c')           AS REAL) AS temp_c,
                       CAST(json_extract(raw_json,'$.wind_dir_degrees') AS REAL) AS wind_dir_degrees,
                       CAST(json_extract(raw_json,'$.wind_speed_kt')    AS REAL) AS wind_speed_kt
                FROM reports
                WHERE report_type = 'AIREP';
            """
        ),
    ),
)


def apply_migrations(conn: sqlite3.Connection, migrations: Sequence[Migration]) -> list[int]:
    """Apply any unapplied migrations.

    Returns the list of versions that were applied in this call. The
    `schema_migrations` table is created on demand (the first migration
    does this for us).

    Note: SQLite + autocommit mode (`isolation_level=None`) means we drive
    transactions explicitly. `executescript` ignores the outer transaction,
    so we keep the migration to a single statement when possible, and
    fall back to manual rollback for multi-statement migrations.
    """
    # Ensure the bookkeeping table exists before we try to read it.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY,"
        " name TEXT NOT NULL,"
        " applied_at TEXT NOT NULL"
        ")"
    )
    applied_rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    applied = {int(r[0]) for r in applied_rows}

    newly_applied: list[int] = []
    now = datetime.now(timezone.utc).isoformat()
    for m in migrations:
        if m.version in applied:
            continue
        try:
            # `executescript` will issue its own COMMIT before running.
            # That's acceptable here because migrations are DDL and SQLite
            # is atomic per-statement for DDL anyway.
            conn.executescript(m.sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
                (m.version, m.name, now),
            )
        except Exception:
            # Best-effort cleanup. We cannot rely on ROLLBACK because the
            # failure may have happened inside a `executescript` that
            # already committed its own internal statements.
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        newly_applied.append(m.version)
    return newly_applied


__all__ = ["Migration", "MIGRATIONS", "apply_migrations"]
