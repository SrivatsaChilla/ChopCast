"""Migrate a legacy `pireps.db` (from the original `collector.py`) into the
new schema.

The legacy schema is:
    reports(hash, fetched_at, obs_time, report_type, raw_text, turbulence,
            aircraft, lat, lon, altitude, raw_json)

The new schema adds `source_url` and `source_etag`. Both are required
(NOT NULL). We fill them with `('<legacy>')` and NULL respectively so the
old rows are unambiguously marked.

The migration is idempotent. It uses `INSERT OR IGNORE`, so re-running
against an already-migrated database inserts zero new rows.

Usage:
    python -m scripts.migrate_legacy_db <legacy_path>
    chopcast-collector migrate-legacy <legacy_path>
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chopcast.errors import ChopcastError
from chopcast.paths import Paths


LEGACY_REQUIRED_COLUMNS = (
    "hash",
    "fetched_at",
    "obs_time",
    "report_type",
    "raw_text",
    "turbulence",
    "aircraft",
    "lat",
    "lon",
    "altitude",
    "raw_json",
)


class LegacySchemaError(ChopcastError):
    """The legacy DB does not have the expected columns."""


def _verify_legacy(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(reports)").fetchall()
    cols = {r[1] for r in rows}
    missing = [c for c in LEGACY_REQUIRED_COLUMNS if c not in cols]
    if missing:
        raise LegacySchemaError(
            f"legacy pireps.db is missing expected columns: {missing}. "
            f"Found: {sorted(cols)}"
        )


def migrate(legacy_path: Path, paths: Paths) -> tuple[int, int]:
    """Migrate rows from `legacy_path` into the new store at `paths.raw_db_path`.

    Returns (inserted, skipped). The new store is opened (and created if
    needed) by this function; the caller does not need to open it.
    """
    if not legacy_path.is_file():
        raise LegacySchemaError(f"legacy db not found: {legacy_path}")

    # Open the legacy read-only; the new store is created on first connect.
    legacy_conn = sqlite3.connect(f"file:{legacy_path}?mode=ro", uri=True)
    legacy_conn.row_factory = sqlite3.Row
    try:
        _verify_legacy(legacy_conn)
        legacy_rows = legacy_conn.execute("SELECT * FROM reports").fetchall()
    finally:
        legacy_conn.close()

    paths.ensure_dirs()
    new_path = paths.raw_db_path
    new_conn = sqlite3.connect(new_path)
    new_conn.row_factory = sqlite3.Row
    inserted = 0
    skipped = 0
    try:
        for r in legacy_rows:
            raw_json = _decode_raw_json(r["raw_json"])
            cur = new_conn.execute(
                "INSERT OR IGNORE INTO reports "
                "(hash, fetched_at, obs_time, report_type, raw_text, turbulence, "
                " aircraft, lat, lon, altitude, raw_json, source_url, source_etag) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    json.dumps(raw_json, default=str),
                    "<legacy-migration>",
                    None,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        new_conn.commit()
    finally:
        new_conn.close()

    return inserted, skipped


def _decode_raw_json(raw: Any) -> dict[str, Any]:
    """Parse the legacy `raw_json` field. It may be NULL, a JSON string, or
    already a dict (in case the column was added by hand).
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"_legacy_raw": str(raw)}
    return parsed if isinstance(parsed, dict) else {"_legacy_raw": parsed}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI entry point (`python -m scripts.migrate_legacy_db`)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    from chopcast.config import Settings

    if len(sys.argv) != 2:
        print("usage: python -m scripts.migrate_legacy_db <legacy_path>", file=sys.stderr)
        sys.exit(2)
    legacy = Path(sys.argv[1])
    try:
        settings = Settings.load()
        ins, skp = migrate(legacy, settings.to_paths())
    except ChopcastError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"inserted={ins} skipped={skp}")
