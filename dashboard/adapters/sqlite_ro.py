"""Read-only SQLite access.

Every pipeline database is opened with ``mode=ro`` and ``PRAGMA query_only``.
There is deliberately no read-write helper in this module.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from adapters.types import FileInfo, human_bytes


class SourceError(RuntimeError):
    """A safe, user-facing source error (never includes a traceback)."""


def iso_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def file_info(path: Path, key: str | None = None) -> FileInfo:
    try:
        stat = path.stat()
        return FileInfo(
            name=key or path.name,
            path=str(path),
            size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            exists=True,
            is_dir=path.is_dir(),
        )
    except OSError:
        return FileInfo(name=key or path.name, path=str(path), size=0, mtime=None, exists=False)


class ReadOnlyDatabase:
    """A short-lived, read-only connection factory."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    @property
    def mtime(self) -> str | None:
        return iso_mtime(self.path)

    @property
    def sidecars(self) -> tuple[Path, ...]:
        return tuple(Path(str(self.path) + suffix) for suffix in ("-wal", "-shm"))

    def _uri(self) -> str:
        # SQLite accepts file:C:/path on Windows and file:/posix/path elsewhere.
        encoded = quote(str(self.path.resolve()).replace("\\", "/"), safe="/:")
        return f"file:{encoded}?mode=ro"

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if not self.exists:
            raise SourceError(f"database not found: {self.path}")
        try:
            conn = sqlite3.connect(self._uri(), uri=True, timeout=2.0)
        except sqlite3.Error as exc:
            raise self._translate(exc) from None
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA busy_timeout = 2000")
            yield conn
        except sqlite3.Error as exc:
            raise self._translate(exc) from None
        finally:
            conn.close()

    def _translate(self, exc: sqlite3.Error) -> SourceError:
        message = str(exc)
        if "unable to open database file" in message and any(
            p.exists() for p in self.sidecars
        ):
            return SourceError(
                "The database is in WAL mode and cannot be opened read-only while a "
                "writer holds it. Point the dashboard at a snapshot copy."
            )
        return SourceError(f"could not read {self.path.name}: {message}")

    # ------------------------------------------------------------------
    def tables(self) -> frozenset[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        return frozenset(str(r["name"]) for r in rows)

    def views(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'view' ORDER BY name"
            ).fetchall()
        return {str(r["name"]): str(r["sql"] or "") for r in rows}

    def columns(self, table: str) -> tuple[str, ...]:
        quoted = table.replace('"', '""')
        try:
            with self.connect() as conn:
                rows = conn.execute(f'PRAGMA table_info("{quoted}")').fetchall()
        except SourceError:
            raise
        except sqlite3.Error:
            return ()
        return tuple(str(r["name"]) for r in rows)

    def table_exists(self, name: str) -> bool:
        try:
            return name in self.tables()
        except SourceError:
            return False

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: tuple[Any, ...] = (), default: Any = None) -> Any:
        row = self.one(sql, params)
        if not row:
            return default
        return next(iter(row.values()), default)

    def status_detail(self) -> str:
        sidecars = [p.name for p in self.sidecars if p.exists()]
        detail = f"{human_bytes(self.size)}"
        if sidecars:
            detail += f" | sidecars: {', '.join(sidecars)}"
        return detail
