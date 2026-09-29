"""Raw storage layer: SQLite schema, migrations, and the `ReportStore` protocol.

The schema is the source of truth for what a "raw report" looks like. Adding
a field does not require a code change (it goes into `raw_json`); changing
the schema of an existing column does.

See docs/DATA_ENGINEERING.md §2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from chopcast.logging import get_logger
from chopcast.storage.migrations import MIGRATIONS, apply_migrations

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# DDL — must match docs/DATA_ENGINEERING.md §2.1 exactly.
# ---------------------------------------------------------------------------
SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_reports_obs_time    ON reports(obs_time);
CREATE INDEX IF NOT EXISTS idx_reports_turbulence  ON reports(turbulence);
CREATE INDEX IF NOT EXISTS idx_reports_type        ON reports(report_type);
CREATE INDEX IF NOT EXISTS idx_reports_fetched_at  ON reports(fetched_at);

CREATE TABLE IF NOT EXISTS rejected (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at    TEXT NOT NULL,
    reason        TEXT NOT NULL,
    raw_row       TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    detail        TEXT
);

CREATE INDEX IF NOT EXISTS idx_rejected_reason ON rejected(reason);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,
    rows_seen     INTEGER,
    rows_inserted INTEGER,
    rows_skipped  INTEGER,
    rows_rejected INTEGER,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
"""


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RunResult:
    """Outcome of a single collection cycle."""

    run_id: int
    status: str
    rows_seen: int = 0
    rows_inserted: int = 0
    rows_skipped: int = 0
    rows_rejected: int = 0

    def as_log_dict(self) -> dict[str, int | str]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "rows_seen": self.rows_seen,
            "rows_inserted": self.rows_inserted,
            "rows_skipped": self.rows_skipped,
            "rows_rejected": self.rows_rejected,
        }


@dataclass(frozen=True)
class RunRecord:
    """A row from the `runs` table."""

    id: int
    started_at: str
    finished_at: str | None
    status: str
    rows_seen: int | None
    rows_inserted: int | None
    rows_skipped: int | None
    rows_rejected: int | None
    error: str | None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class ReportStore(Protocol):
    """The interface the collector uses to talk to the raw store.

    A protocol (not an ABC) so tests can substitute a fake without subclassing.
    """

    def insert_report(
        self,
        *,
        hash: str,
        fetched_at: datetime,
        obs_time: str | None,
        report_type: str | None,
        raw_text: str | None,
        turbulence: str | None,
        aircraft: str | None,
        turbulence_2: str | None = None,
        turbulence_type: str | None = None,
        turbulence_freq: str | None = None,
        lat: float | None,
        lon: float | None,
        altitude: float | None,
        raw_json: dict[str, Any],
        source_url: str,
        source_etag: str | None = None,
    ) -> bool:
        """Insert one report. Returns True if inserted, False if duplicate.

        The dedup is on the primary key (`hash`). The implementation must
        use `INSERT OR IGNORE` so two collection cycles cannot double-insert.
        """
        ...

    def insert_rejected(
        self,
        *,
        fetched_at: datetime,
        reason: str,
        raw_row: dict[str, Any],
        source_url: str,
        detail: str | None = None,
    ) -> None:
        ...

    def begin_run(self, started_at: datetime) -> int:
        """Append a new `runs` row with status='in_progress'. Return the id."""
        ...

    def finish_run(
        self,
        run_id: int,
        *,
        finished_at: datetime,
        status: str,
        rows_seen: int,
        rows_inserted: int,
        rows_skipped: int,
        rows_rejected: int,
        error: str | None = None,
    ) -> None:
        ...

    def last_runs(self, limit: int = 10) -> list[RunRecord]: ...

    def count(self) -> int: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------
class SqliteReportStore:
    """The default `ReportStore`, backed by a single SQLite file.

    The connection is opened with `journal_mode=WAL` and a `busy_timeout` so
    concurrent readers do not block writers. The same connection is reused
    for the lifetime of the process; the collector calls `close()` on
    shutdown.
    """

    def __init__(self, path: Path, *, journal_mode: str = "WAL", busy_timeout_ms: int = 5000) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # PRAGMA values are not bindable; the value is a validated Literal
        # so the f-string is safe.
        self._conn.execute(f"PRAGMA journal_mode = {journal_mode}")
        self._conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        self._conn.execute("PRAGMA foreign_keys = ON")
        # Initialise schema, including any unapplied migrations.
        apply_migrations(self._conn, MIGRATIONS)
        self._conn.executescript(SCHEMA)

    # ----- helpers --------------------------------------------------------
    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _serialise(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, float) and value != value:  # NaN
            return None
        return value

    # ----- ReportStore ---------------------------------------------------
    def insert_report(
        self,
        *,
        hash: str,
        fetched_at: datetime,
        obs_time: str | None,
        report_type: str | None,
        raw_text: str | None,
        turbulence: str | None,
        aircraft: str | None,
        turbulence_2: str | None = None,
        turbulence_type: str | None = None,
        turbulence_freq: str | None = None,
        lat: float | None,
        lon: float | None,
        altitude: float | None,
        raw_json: dict[str, Any],
        source_url: str,
        source_etag: str | None = None,
    ) -> bool:
        # NB: We do NOT use `INSERT OR IGNORE` here. SQLite treats CHECK
        # constraint failures as ignorable under `OR IGNORE`, which would
        # silently drop data that the schema rejected. We catch
        # IntegrityError and inspect the message: if the violation is a
        # primary-key conflict, treat as a duplicate (return False);
        # otherwise re-raise so the caller can quarantine the row.
        try:
            cur = self._conn.execute(
                "INSERT INTO reports "
                "(hash, fetched_at, obs_time, report_type, raw_text, turbulence, "
                " turbulence_2, turbulence_type, turbulence_freq, "
                " aircraft, lat, lon, altitude, raw_json, source_url, source_etag) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    hash,
                    fetched_at.isoformat(),
                    self._serialise(obs_time),
                    self._serialise(report_type),
                    self._serialise(raw_text),
                    self._serialise(turbulence),
                    self._serialise(turbulence_2),
                    self._serialise(turbulence_type),
                    self._serialise(turbulence_freq),
                    self._serialise(aircraft),
                    self._serialise(lat),
                    self._serialise(lon),
                    self._serialise(altitude),
                    json.dumps(raw_json, default=str),
                    source_url,
                    source_etag,
                ),
            )
        except sqlite3.IntegrityError as e:
            msg = str(e).lower()
            if "unique" in msg or "primary key" in msg:
                return False
            # Some other constraint (CHECK, NOT NULL, FK). Re-raise.
            log.warning("storage.insert.constraint_violation", error=str(e), hash=hash[:8])
            raise
        return cur.rowcount > 0

    def insert_rejected(
        self,
        *,
        fetched_at: datetime,
        reason: str,
        raw_row: dict[str, Any],
        source_url: str,
        detail: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO rejected (fetched_at, reason, raw_row, source_url, detail) "
            "VALUES (?,?,?,?,?)",
            (
                fetched_at.isoformat(),
                reason,
                json.dumps(raw_row, default=str),
                source_url,
                detail,
            ),
        )

    def begin_run(self, started_at: datetime) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'in_progress')",
            (started_at.isoformat(),),
        )
        return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        finished_at: datetime,
        status: str,
        rows_seen: int,
        rows_inserted: int,
        rows_skipped: int,
        rows_rejected: int,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE runs SET finished_at=?, status=?, rows_seen=?, rows_inserted=?, "
            "rows_skipped=?, rows_rejected=?, error=? WHERE id=?",
            (
                finished_at.isoformat(),
                status,
                rows_seen,
                rows_inserted,
                rows_skipped,
                rows_rejected,
                error,
                run_id,
            ),
        )

    def last_runs(self, limit: int = 10) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM reports").fetchone()
        return int(row[0])

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_run(r: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=int(r["id"]),
            started_at=str(r["started_at"]),
            finished_at=r["finished_at"],
            status=str(r["status"]),
            rows_seen=r["rows_seen"],
            rows_inserted=r["rows_inserted"],
            rows_skipped=r["rows_skipped"],
            rows_rejected=r["rows_rejected"],
            error=r["error"],
        )


__all__ = [
    "ReportStore",
    "RunRecord",
    "RunResult",
    "SCHEMA",
    "SqliteReportStore",
]
