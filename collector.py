#!/usr/bin/env python3
"""
Phase 1: PIREP collection pipeline.

Polls the AWC aircraft-reports cache, deduplicates, and accumulates into
SQLite. The AWC database only serves the previous 15 days, so this must run
continuously for weeks to build a training set.

Design notes:
  - Stores the FULL raw row as JSON alongside extracted fields. If a column
    guess is wrong you re-parse from the DB instead of re-collecting.
  - Dedup key is a hash of (time + location + raw text). pirepId was removed
    from AWC output in Sept 2025, so it cannot be used.
  - Handles 204 (no data, not an error) and 429 (backoff) per AWC docs.

Run:
    python collector.py --once        # single pull, for testing
    python collector.py               # continuous loop
    python collector.py --stats       # summarize what you have so far
"""

import argparse
import gzip
import hashlib
import io
import json
import logging
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# --------------------------------------------------------------------------
# CONFIG -- update COLUMNS after running explore.py
# --------------------------------------------------------------------------
CSV_URL = "https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz"
USER_AGENT = "pirep-turbulence-research"  # <- your identifier
DB_PATH = Path("pireps.db")
POLL_SECONDS = 600          # 10 min. Cache refreshes every 60s; be polite.
REQUEST_TIMEOUT = 60
MAX_RETRIES = 5

# Fill these in from explore.py output. None = auto-resolve from candidates.
COLUMNS = {
    "raw_text": None,
    "turbulence": None,
    "report_type": None,
    "aircraft": None,
    "lat": None,
    "lon": None,
    "altitude": None,
    "obs_time": None,
}

CANDIDATES = {
    "raw_text": ["rawOb", "raw_text", "raw", "report", "rawReport"],
    "turbulence": ["turbulence", "tbInt1", "turbInt", "tb", "turbulenceIntensity"],
    "report_type": ["reportType", "obsType", "type", "acReportType"],
    "aircraft": ["acType", "aircraftType", "actype", "aircraft_ref"],
    "lat": ["lat", "latitude"],
    "lon": ["lon", "longitude"],
    "altitude": ["altFt", "fltLvl", "altitude_ft_msl", "flightLevel", "alt"],
    "obs_time": ["obsTime", "observation_time", "receiptTime", "time"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    handlers=[logging.FileHandler("collector.log"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("collector")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True
    log.info("Shutdown signal received; finishing current cycle.")


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    hash        TEXT PRIMARY KEY,
    fetched_at  TEXT NOT NULL,
    obs_time    TEXT,
    report_type TEXT,
    raw_text    TEXT,
    turbulence  TEXT,
    aircraft    TEXT,
    lat         REAL,
    lon         REAL,
    altitude    REAL,
    raw_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turb ON reports(turbulence);
CREATE INDEX IF NOT EXISTS idx_obs  ON reports(obs_time);
CREATE INDEX IF NOT EXISTS idx_type ON reports(report_type);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at     TEXT NOT NULL,
    rows_seen  INTEGER,
    inserted   INTEGER,
    skipped    INTEGER,
    status     TEXT
);
"""


def init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def resolve_columns(df: pd.DataFrame) -> dict:
    """Map logical field names to actual DataFrame columns."""
    lower = {c.lower(): c for c in df.columns}
    resolved = {}
    for key, override in COLUMNS.items():
        if override:
            resolved[key] = override
            continue
        found = None
        for cand in CANDIDATES.get(key, []):
            if cand.lower() in lower:
                found = lower[cand.lower()]
                break
        resolved[key] = found
    missing = [k for k, v in resolved.items() if v is None]
    if missing:
        log.warning("Unresolved columns: %s -- run explore.py and set COLUMNS", missing)
    return resolved


def row_hash(row: pd.Series, cols: dict) -> str:
    """
    Dedup key. The cache is a rolling snapshot, so every poll re-serves
    reports already stored. Without this you build a duplicate-laden dataset
    that leaks across your train/test split.
    """
    parts = []
    for key in ("obs_time", "lat", "lon", "raw_text"):
        col = cols.get(key)
        val = row.get(col) if col else None
        parts.append("" if pd.isna(val) else str(val).strip())
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _clean(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _num(val):
    val = _clean(val)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------
def fetch(url: str) -> pd.DataFrame | None:
    """Returns DataFrame, or None when there is no data (HTTP 204)."""
    delay = 5
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
            )

            if resp.status_code == 204:
                log.info("204 No Content -- valid request, nothing new.")
                return None

            if resp.status_code == 429:
                log.warning("429 rate limited; backing off %ss", delay)
                time.sleep(delay)
                delay = min(delay * 2, 300)
                continue

            if resp.status_code >= 500:
                log.warning("Server error %s; retry %d/%d in %ss",
                            resp.status_code, attempt, MAX_RETRIES, delay)
                time.sleep(delay)
                delay = min(delay * 2, 300)
                continue

            resp.raise_for_status()

            with gzip.open(io.BytesIO(resp.content), "rt", errors="replace") as fh:
                return pd.read_csv(fh, low_memory=False, on_bad_lines="skip")

        except requests.RequestException as e:
            log.warning("Request failed (%s); retry %d/%d in %ss",
                        type(e).__name__, attempt, MAX_RETRIES, delay)
            time.sleep(delay)
            delay = min(delay * 2, 300)

    log.error("Giving up after %d attempts.", MAX_RETRIES)
    return None


def store(conn: sqlite3.Connection, df: pd.DataFrame) -> tuple[int, int]:
    cols = resolve_columns(df)
    now = datetime.now(timezone.utc).isoformat()
    rows = []

    for _, row in df.iterrows():
        rows.append((
            row_hash(row, cols),
            now,
            str(_clean(row.get(cols["obs_time"]))) if cols["obs_time"] else None,
            str(_clean(row.get(cols["report_type"]))) if cols["report_type"] else None,
            str(_clean(row.get(cols["raw_text"]))) if cols["raw_text"] else None,
            str(_clean(row.get(cols["turbulence"]))) if cols["turbulence"] else None,
            str(_clean(row.get(cols["aircraft"]))) if cols["aircraft"] else None,
            _num(row.get(cols["lat"])) if cols["lat"] else None,
            _num(row.get(cols["lon"])) if cols["lon"] else None,
            _num(row.get(cols["altitude"])) if cols["altitude"] else None,
            json.dumps({k: _clean(v) for k, v in row.to_dict().items()}, default=str),
        ))

    before = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    conn.executemany(
        "INSERT OR IGNORE INTO reports "
        "(hash, fetched_at, obs_time, report_type, raw_text, turbulence, "
        " aircraft, lat, lon, altitude, raw_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]

    inserted = after - before
    return inserted, len(rows) - inserted


def run_once(conn: sqlite3.Connection) -> None:
    df = fetch(CSV_URL)
    ran_at = datetime.now(timezone.utc).isoformat()

    if df is None:
        conn.execute("INSERT INTO runs (ran_at, rows_seen, inserted, skipped, status) "
                     "VALUES (?,?,?,?,?)", (ran_at, 0, 0, 0, "no_data"))
        conn.commit()
        return

    inserted, skipped = store(conn, df)
    total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    conn.execute("INSERT INTO runs (ran_at, rows_seen, inserted, skipped, status) "
                 "VALUES (?,?,?,?,?)", (ran_at, len(df), inserted, skipped, "ok"))
    conn.commit()

    log.info("seen=%-6d new=%-5d dup=%-6d  TOTAL=%d", len(df), inserted, skipped, total)


def show_stats(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    print(f"\nTotal reports stored: {total:,}")
    if not total:
        print("Nothing collected yet.")
        return

    labeled = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE turbulence IS NOT NULL "
        "AND turbulence != 'None' AND turbulence != ''").fetchone()[0]
    print(f"With turbulence label: {labeled:,} ({100*labeled/total:.1f}%)")

    print("\nTurbulence value distribution:")
    for val, n in conn.execute(
        "SELECT turbulence, COUNT(*) c FROM reports "
        "WHERE turbulence IS NOT NULL AND turbulence NOT IN ('None','') "
        "GROUP BY turbulence ORDER BY c DESC LIMIT 20"):
        print(f"  {str(val):<24} {n:>7,}")

    print("\nReport types:")
    for val, n in conn.execute(
        "SELECT report_type, COUNT(*) c FROM reports GROUP BY report_type "
        "ORDER BY c DESC LIMIT 10"):
        print(f"  {str(val):<24} {n:>7,}")

    print("\nAccrual (last 10 runs):")
    for ran_at, seen, ins in conn.execute(
        "SELECT ran_at, rows_seen, inserted FROM runs ORDER BY id DESC LIMIT 10"):
        print(f"  {ran_at[:19]}  seen={seen:<6} new={ins}")

    first, last = conn.execute(
        "SELECT MIN(fetched_at), MAX(fetched_at) FROM reports").fetchone()
    print(f"\nCollecting since: {first[:19] if first else '-'}")
    print(f"Most recent pull: {last[:19] if last else '-'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single pull then exit")
    ap.add_argument("--stats", action="store_true", help="summarize stored data")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    conn = init_db(Path(args.db))

    if args.stats:
        show_stats(conn)
        return 0

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if args.once:
        run_once(conn)
        return 0

    log.info("Collector started. Polling every %ds. Ctrl-C to stop.", POLL_SECONDS)
    while not _shutdown:
        try:
            run_once(conn)
        except Exception as e:
            log.exception("Cycle failed: %s", e)
        for _ in range(POLL_SECONDS):
            if _shutdown:
                break
            time.sleep(1)

    conn.close()
    log.info("Stopped cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
