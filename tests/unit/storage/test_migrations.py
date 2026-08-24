"""Tests for chopcast.storage.migrations."""

from __future__ import annotations

import sqlite3

import pytest

from chopcast.storage.migrations import MIGRATIONS, Migration, apply_migrations


def test_apply_creates_schema_migrations_table() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        apply_migrations(conn, MIGRATIONS)
        rows = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version").fetchall()
        assert len(rows) == len(MIGRATIONS)
        assert rows[0][0] == 1
    finally:
        conn.close()


def test_apply_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        first = apply_migrations(conn, MIGRATIONS)
        second = apply_migrations(conn, MIGRATIONS)
        assert first == [m.version for m in MIGRATIONS]
        assert second == []
    finally:
        conn.close()


def test_apply_partial_set() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        # Apply only the first migration, then both.
        first = MIGRATIONS[:1]
        new1 = apply_migrations(conn, first)
        new2 = apply_migrations(conn, MIGRATIONS)
        assert new1 == [1]
        assert new2 == []
    finally:
        conn.close()


def test_failed_migration_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        bad = MIGRATIONS + (
            Migration(version=999, name="bad", sql="CREATE TABLE broken ("),
        )
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations(conn, bad)
        # The first migration should still be applied; the failing one not.
        rows = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        assert rows[0] == 1
    finally:
        conn.close()
