#!/usr/bin/env python3
"""Validates collector logic against synthetic data (no network)."""
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

import collector


def make_batch(n_start=0, n=5):
    """Mimics plausible AWC cache structure."""
    return pd.DataFrame([{
        "receiptTime": f"2026-08-09T1{i%10}:30:00Z",
        "obsTime": f"2026-08-09T1{i%10}:25:00Z",
        "reportType": "PIREP" if i % 3 else "AIREP",
        "acType": ["B738", "C172", "A320"][i % 3],
        "lat": 37.5 + i * 0.1,
        "lon": -122.0 - i * 0.1,
        "fltLvl": 35000 - i * 1000,
        "turbulence": [None, "LGT", "MOD", "SEV", "LGT-MOD"][i % 5],
        "rawOb": f"UA /OV SFO{i:03d} /TM 1425 /FL350 /TP B738 "
                 f"/TB MOD CHOP occasional sharp jolts report {i}",
    } for i in range(n_start, n_start + n)])


def run():
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    conn = collector.init_db(tmp)
    ok = True

    # --- column resolution ---
    b1 = make_batch(0, 5)
    cols = collector.resolve_columns(b1)
    print("Resolved columns:")
    for k, v in cols.items():
        print(f"  {k:<12} -> {v}")
    assert cols["raw_text"] == "rawOb", "raw_text resolution failed"
    assert cols["turbulence"] == "turbulence", "turbulence resolution failed"
    assert cols["report_type"] == "reportType", "report_type resolution failed"
    print("  PASS: column auto-resolution\n")

    # --- first insert ---
    ins, skip = collector.store(conn, b1)
    print(f"Batch 1: inserted={ins} skipped={skip}")
    assert ins == 5 and skip == 0, f"expected 5/0, got {ins}/{skip}"
    print("  PASS: initial insert\n")

    # --- identical batch must fully dedup (the rolling-snapshot case) ---
    ins, skip = collector.store(conn, b1)
    print(f"Batch 1 again: inserted={ins} skipped={skip}")
    assert ins == 0 and skip == 5, f"DEDUP BROKEN: got {ins}/{skip}"
    print("  PASS: dedup on repeat pull\n")

    # --- overlapping batch: i=3..7 vs i=0..4 -> 3 new, 2 dupes ---
    b2 = make_batch(3, 5)
    ins, skip = collector.store(conn, b2)
    print(f"Batch 2 (overlap): inserted={ins} skipped={skip}")
    assert ins == 3 and skip == 2, f"expected 3/2, got {ins}/{skip}"
    print("  PASS: partial overlap\n")

    # --- verify stored fields ---
    row = conn.execute(
        "SELECT raw_text, turbulence, lat, altitude, report_type "
        "FROM reports WHERE turbulence='MOD' LIMIT 1").fetchone()
    print(f"Sample stored row: {row}")
    assert row and row[1] == "MOD", "field extraction failed"
    assert isinstance(row[2], float), "lat not stored numerically"
    print("  PASS: field extraction\n")

    # --- raw_json preserves everything (insurance against bad column guesses) ---
    import json
    raw = conn.execute("SELECT raw_json FROM reports LIMIT 1").fetchone()[0]
    parsed = json.loads(raw)
    assert "acType" in parsed and "fltLvl" in parsed, "raw_json incomplete"
    print(f"  PASS: raw_json preserves all {len(parsed)} source fields\n")

    # --- nulls / missing columns must not crash ---
    sparse = pd.DataFrame([{"rawOb": "UA /OV SFO /TB LGT", "turbulence": "LGT"}])
    ins, skip = collector.store(conn, sparse)
    print(f"Sparse batch (missing lat/lon/type): inserted={ins}")
    assert ins == 1, "sparse row rejected"
    print("  PASS: handles missing columns\n")

    total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    print(f"Final row count: {total}")
    assert total == 9, f"expected 9, got {total}"

    print("\n" + "=" * 50)
    print("ALL TESTS PASSED" if ok else "FAILURES")
    print("=" * 50)
    print("\n--- stats output preview ---")
    collector.show_stats(conn)


if __name__ == "__main__":
    run()
