from __future__ import annotations

import pytest

from adapters.sqlite_ro import ReadOnlyDatabase, SourceError


def test_connection_is_query_only(settings):
    db = ReadOnlyDatabase(settings.raw_db)
    with db.connect() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(SourceError):
            connection.execute("DELETE FROM reports")


def test_missing_database_raises_safe_error(tmp_path):
    db = ReadOnlyDatabase(tmp_path / "absent.db")
    assert db.exists is False
    with pytest.raises(SourceError, match="database not found"):
        db.connect()


def test_scalar_and_one_defaults(settings):
    db = ReadOnlyDatabase(settings.raw_db)
    assert db.scalar("SELECT COUNT(*) FROM reports") == 6
    assert db.scalar("SELECT COUNT(*) FROM reports WHERE 0") == 0
    assert db.one("SELECT hash FROM reports WHERE 0") is None
    assert db.scalar("SELECT COUNT(*) FROM reports WHERE 0", default=-1) == 0
