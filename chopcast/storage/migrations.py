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
    # Future migrations go here. Example:
    # Migration(version=2, name="add_source_etag", sql="ALTER TABLE ..."),
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
