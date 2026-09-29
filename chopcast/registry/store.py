"""SQL-backed model registry.

Schema lives in `REGISTRY_SCHEMA`. Two tables:
- `models` — one row per trained model.
- `promotions` — append-only log of model promotions (baseline -> champion).

The registry is intentionally append-only for promotions. We never
delete models; we just stop pointing at them.

See `docs/MODULE_DESIGN.md` §10.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from chopcast.logging import get_logger
from chopcast.storage.migrations import MIGRATIONS, apply_migrations

log = get_logger(__name__)


REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version   TEXT NOT NULL,
    model_kind      TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    registered_at   TEXT NOT NULL,
    metrics_json    TEXT NOT NULL,
    artifact_path   TEXT NOT NULL,
    notes           TEXT,
    UNIQUE(model_kind, model_version)
);

CREATE TABLE IF NOT EXISTS promotions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id        INTEGER NOT NULL,
    promoted_at     TEXT NOT NULL,
    tag             TEXT NOT NULL,
    replaced_id     INTEGER,
    FOREIGN KEY(model_id) REFERENCES models(id),
    FOREIGN KEY(replaced_id) REFERENCES models(id),
    UNIQUE(tag)
);
"""


@dataclass(frozen=True)
class ModelRecord:
    """A row from the `models` table."""

    id: int
    model_version: str
    model_kind: str
    feature_version: str
    registered_at: str
    metrics: dict[str, Any]
    artifact_path: str
    notes: str | None


@dataclass(frozen=True)
class PromotionRecord:
    """A row from the `promotions` table."""

    id: int
    model_id: int
    promoted_at: str
    tag: str
    replaced_id: int | None


@runtime_checkable
class ModelRegistry(Protocol):
    """The interface the inference layer uses."""

    def register(
        self,
        *,
        model_version: str,
        model_kind: str,
        feature_version: str,
        metrics: dict[str, Any],
        artifact_path: Path,
        notes: str | None = None,
    ) -> int: ...

    def promote(self, model_id: int, *, tag: str) -> None: ...

    def current(self, tag: str = "production") -> ModelRecord | None: ...

    def get(self, model_id: int) -> ModelRecord | None: ...

    def list(self, *, model_kind: str | None = None) -> list[ModelRecord]: ...

    def close(self) -> None: ...


class SqliteModelRegistry:
    """The default registry implementation."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        apply_migrations(self._conn, MIGRATIONS)
        self._conn.executescript(REGISTRY_SCHEMA)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def register(
        self,
        *,
        model_version: str,
        model_kind: str,
        feature_version: str,
        metrics: dict[str, Any],
        artifact_path: Path,
        notes: str | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        try:
            cur = self._conn.execute(
                "INSERT INTO models "
                "(model_version, model_kind, feature_version, registered_at, "
                " metrics_json, artifact_path, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    model_version,
                    model_kind,
                    feature_version,
                    now,
                    json.dumps(metrics, default=str),
                    str(artifact_path),
                    notes,
                ),
            )
        except sqlite3.IntegrityError as e:
            log.warning("registry.duplicate_model", version=model_version, kind=model_kind)
            raise
        return int(cur.lastrowid)

    def promote(self, model_id: int, *, tag: str) -> None:
        # Reject unknown models first.
        row = self._conn.execute("SELECT id FROM models WHERE id = ?", (model_id,)).fetchone()
        if row is None:
            raise KeyError(f"no model with id={model_id}")
        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT id FROM promotions WHERE tag = ?", (tag,)
        ).fetchone()
        replaced_id = int(existing["id"]) if existing else None
        # INSERT OR REPLACE keeps a single row per tag.
        self._conn.execute(
            "INSERT OR REPLACE INTO promotions (id, model_id, promoted_at, tag, replaced_id) "
            "VALUES ("
            " COALESCE((SELECT id FROM promotions WHERE tag = ?), NULL),"
            " ?, ?, ?, ?"
            ")",
            (tag, model_id, now, tag, replaced_id),
        )
        log.info(
            "registry.promoted",
            model_id=model_id,
            tag=tag,
            replaced_id=replaced_id,
        )

    def current(self, tag: str = "production") -> ModelRecord | None:
        row = self._conn.execute(
            "SELECT m.* FROM models m JOIN promotions p ON p.model_id = m.id "
            "WHERE p.tag = ?",
            (tag,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def get(self, model_id: int) -> ModelRecord | None:
        row = self._conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def list(self, *, model_kind: str | None = None) -> list[ModelRecord]:
        if model_kind is None:
            rows = self._conn.execute("SELECT * FROM models ORDER BY id DESC").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM models WHERE model_kind = ? ORDER BY id DESC",
                (model_kind,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ModelRecord:
        metrics = json.loads(row["metrics_json"]) if row["metrics_json"] else {}
        return ModelRecord(
            id=int(row["id"]),
            model_version=str(row["model_version"]),
            model_kind=str(row["model_kind"]),
            feature_version=str(row["feature_version"]),
            registered_at=str(row["registered_at"]),
            metrics=metrics,
            artifact_path=str(row["artifact_path"]),
            notes=row["notes"],
        )


__all__ = [
    "ModelRecord",
    "ModelRegistry",
    "PromotionRecord",
    "REGISTRY_SCHEMA",
    "SqliteModelRegistry",
]