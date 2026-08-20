#!/usr/bin/env python3
"""
Validates collector logic against synthetic data shaped like the REAL AWC
cache schema (verified live 2026-08-20). No network required.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

import collector

# Real AWC values, taken from a live snapshot.
TB_VALUES = [None, "LGT", "MOD", "NEG", "LGT-MOD"]
RAW = ("{icao} UA /OV {icao}180025/TM 01{i:02d}/FL130/TP PC12"
       "/TB {tb} CHOP 130-100/RM ride report {i}")


def make_batch(start=0, n=5):
    """Mimics the real aircraft-reports cache columns."""
    return pd.DataFrame([{
        "receipt_time": f"2026-08-20T01:{i%60:02d}:00Z",
        "observation_time": f"2026-08-20T01:{i%60:02d}:00Z",
        "report_type": "PIREP" if i % 3 else "AIREP",
        "aircraft_ref": ["B738", "C172", "A320"][i % 3],
        "latitude": 37.5 + i * 0.1,
        "longitude": -122.0 - i * 0.1,
        "altitude_ft_msl": 35000 - i * 1000,
        "turbulence_intensity": TB_VALUES[i % 5],
        "turbulence_intensity.1": "MOD" if i % 7 == 0 else None,
        "turbulence_type": "CHOP",
        "turbulence_freq": "OCNL" if i % 2 else None,
        "raw_text": RAW.format(icao="KMLI", i=i, tb=TB_VALUES[i % 5] or "NEG"),
    } for i in range(start, start + n)])


def check(label, cond):
    assert cond, f"FAIL: {label}"
    print(f"  PASS: {label}")


def run():
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    conn = collector.init_db(tmp)

    print("\n[1] column resolution against real schema")
    cols = collector.resolve_columns(make_batch(0, 5))
    for k, v in cols.items():
        print(f"      {k:<16} -> {v}")
    check("raw_text -> raw_text", cols["raw_text"] == "raw_text")
    check("turbulence -> turbulence_intensity", cols["turbulence"] == "turbulence_intensity")
    check("report_type -> report_type", cols["report_type"] == "report_type")
    check("no unresolved fields", all(v is not None for v in cols.values()))

    print("\n[2] insert and dedup")
    b1 = make_batch(0, 5)
    ins, skip = collector.store(conn, b1)
    check(f"initial insert 5/0 (got {ins}/{skip})", (ins, skip) == (5, 0))
    ins, skip = collector.store(conn, b1)
    check(f"repeat pull fully dedups (got {ins}/{skip})", (ins, skip) == (0, 5))
    ins, skip = collector.store(conn, make_batch(3, 5))
    check(f"partial overlap 3 new / 2 dup (got {ins}/{skip})", (ins, skip) == (3, 2))

    print("\n[3] REGRESSION: dtype drift must not fork the dedup hash")
    same = {"observation_time": "2026-08-20T01:00:00Z", "raw_text": "UA /OV DEN /TB MOD",
            "report_type": "PIREP"}
    a = pd.DataFrame([{**same, "latitude": 37, "longitude": -122}])
    b = pd.DataFrame([{**same, "latitude": 37, "longitude": -122},
                      {**same, "latitude": None, "longitude": -122,
                       "raw_text": "other", "observation_time": "T2"}])
    ha = collector.row_hash(a.iloc[0], collector.resolve_columns(a))
    hb = collector.row_hash(b.iloc[0], collector.resolve_columns(b))
    print(f"      int64 hash={ha[:16]}  float64 hash={hb[:16]}")
    check("int64/float64 lat produce the same hash", ha == hb)

    print("\n[4] REGRESSION: NULLs must be SQL NULL, not the string 'None'")
    n_str = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE turbulence = 'None'").fetchone()[0]
    check(f"no literal 'None' strings stored (found {n_str})", n_str == 0)
    n_null = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE turbulence IS NULL").fetchone()[0]
    check(f"unlabeled rows are queryable as NULL (found {n_null})", n_null > 0)

    print("\n[5] field extraction")
    row = conn.execute(
        "SELECT raw_text, turbulence, lat, altitude, report_type, turbulence_type "
        "FROM reports WHERE turbulence='MOD' LIMIT 1").fetchone()
    check("turbulence extracted", row and row[1] == "MOD")
    check("lat stored numerically", isinstance(row[2], float))
    check("turbulence_type carried for label mapping", row[5] == "CHOP")
    lyr2 = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE turbulence_2 IS NOT NULL").fetchone()[0]
    check(f"second turbulence layer captured ({lyr2} rows)", lyr2 > 0)

    print("\n[6] raw_json completeness")
    parsed = json.loads(conn.execute("SELECT raw_json FROM reports LIMIT 1").fetchone()[0])
    check(f"raw_json preserves all {len(parsed)} source fields",
          {"aircraft_ref", "altitude_ft_msl", "turbulence_freq"} <= parsed.keys())

    print("\n[7] sparse rows must not crash")
    ins, _ = collector.store(conn, pd.DataFrame(
        [{"raw_text": "UA /OV SFO /TB LGT", "turbulence_intensity": "LGT"}]))
    check("sparse row accepted", ins == 1)

    total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    check(f"final row count 9 (got {total})", total == 9)

    print("\n" + "=" * 52)
    print("ALL TESTS PASSED")
    print("=" * 52)


if __name__ == "__main__":
    run()
