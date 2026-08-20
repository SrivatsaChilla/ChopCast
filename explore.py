#!/usr/bin/env python3
"""
Phase 0: schema discovery for the AWC aircraft reports cache.

Answers the four questions you need before writing the collector:
  1. What columns actually exist?
  2. CSV vs XML -- does CSV carry raw text + aircraft type?
  3. Are AIREPs mixed in with PIREPs?
  4. What fraction of reports carry a usable turbulence label?

Run:  python explore.py
Saves a local snapshot so you can work offline afterwards.
"""

from __future__ import annotations

import gzip
import io
import sys
from pathlib import Path

import pandas as pd
import requests

CSV_URL = "https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz"
USER_AGENT = "pirep-turbulence-research"  # <- put your own identifier here
SNAPSHOT = Path("snapshot.csv")

# Candidate column names. AWC has renamed fields before (Sept 2025), so we
# search rather than assume. Discovery output will tell you the real ones.
CANDIDATES = {
    "raw_text": ["raw_text", "rawOb", "raw", "report", "rawReport"],
    "turbulence": ["turbulence_intensity", "turbulenceIntensity", "tbInt1", "turbulence"],
    "report_type": ["report_type", "reportType", "obsType", "acReportType"],
    "aircraft": ["aircraft_ref", "acType", "aircraftType"],
    "lat": ["latitude", "lat"],
    "lon": ["longitude", "lon"],
    "altitude": ["altitude_ft_msl", "altFt", "flightLevel", "fltLvl"],
    "obs_time": ["observation_time", "obsTime", "receiptTime", "time"],
}


def fetch_csv(url: str) -> pd.DataFrame:
    print(f"Fetching {url}")
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    print(f"  {len(resp.content):,} bytes compressed")
    with gzip.open(io.BytesIO(resp.content), "rt", errors="replace") as fh:
        # AWC cache CSVs sometimes carry preamble lines before the header row.
        df = pd.read_csv(fh, low_memory=False, on_bad_lines="skip")
    print(f"  {len(df):,} rows x {len(df.columns)} columns\n")
    return df


def resolve(df: pd.DataFrame, names: list[str]) -> str | None:
    """Case-insensitive lookup of the first candidate present."""
    lower = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def report_schema(df: pd.DataFrame) -> dict:
    print("=" * 70)
    print("COLUMNS")
    print("=" * 70)
    for col in df.columns:
        nn = df[col].notna().sum()
        pct = 100 * nn / len(df) if len(df) else 0
        print(f"  {col:<28} {nn:>7,} non-null ({pct:5.1f}%)  {df[col].dtype}")

    print("\n" + "=" * 70)
    print("RESOLVED FIELDS  (copy these into collector.py CONFIG)")
    print("=" * 70)
    resolved = {}
    for key, cands in CANDIDATES.items():
        found = resolve(df, cands)
        resolved[key] = found
        mark = "OK " if found else "!! "
        print(f"  {mark}{key:<14} -> {found or 'NOT FOUND - inspect columns above'}")
    return resolved


def report_types(df: pd.DataFrame, col: str | None) -> None:
    print("\n" + "=" * 70)
    print("REPORT TYPES  (PIREP vs AIREP)")
    print("=" * 70)
    if not col:
        print("  No report-type column resolved. Check the column list above.")
        return
    counts = df[col].value_counts(dropna=False)
    for val, n in counts.items():
        print(f"  {str(val):<20} {n:>7,}  ({100*n/len(df):5.1f}%)")
    print("\n  AIREPs are automated and carry no descriptive prose.")
    print("  If they are a large share, filter them in the collector.")


def turbulence_yield(df: pd.DataFrame, tb_col: str | None, text_col: str | None) -> None:
    print("\n" + "=" * 70)
    print("TURBULENCE LABEL YIELD  (this sets your project timeline)")
    print("=" * 70)
    if not tb_col:
        print("  No turbulence column resolved -- inspect the column list.")
        return

    labeled = df[tb_col].notna().sum()
    rate = labeled / len(df) if len(df) else 0
    print(f"  Rows with a turbulence value: {labeled:,} / {len(df):,}  ({100*rate:.1f}%)")

    print("\n  Distinct values (your label-mapping problem):")
    for val, n in df[tb_col].value_counts(dropna=True).head(25).items():
        print(f"    {str(val):<24} {n:>6,}")

    # Rows usable for NLP need BOTH a label and non-empty prose.
    if text_col:
        usable = df[df[tb_col].notna() & df[text_col].notna() & (
            df[text_col].astype(str).str.strip().str.len() > 20)]
        print(f"\n  Usable for NLP (label + prose >20 chars): {len(usable):,} "
              f"({100*len(usable)/len(df):.1f}%)")
        print("\n  --- TIMELINE MATH ---")
        print(f"  This snapshot holds {len(usable):,} usable reports.")
        print("  The cache is a rolling window, so run this twice ~24h apart")
        print("  and diff to get your true reports/day accrual rate.")


def show_samples(df: pd.DataFrame, text_col: str | None, tb_col: str | None) -> None:
    print("\n" + "=" * 70)
    print("SAMPLE REPORTS  (read these -- do not skip)")
    print("=" * 70)
    if not text_col:
        print("  No raw-text column resolved.")
        return
    subset = df[df[text_col].notna()]
    if tb_col:
        subset = subset[subset[tb_col].notna()]
    for i, (_, row) in enumerate(subset.head(8).iterrows(), 1):
        label = row[tb_col] if tb_col else "?"
        print(f"\n  [{i}] label={label}")
        print(f"      {str(row[text_col])[:220]}")


def main() -> int:
    try:
        df = fetch_csv(CSV_URL)
    except requests.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    resolved = report_schema(df)
    report_types(df, resolved["report_type"])
    turbulence_yield(df, resolved["turbulence"], resolved["raw_text"])
    show_samples(df, resolved["raw_text"], resolved["turbulence"])

    df.to_csv(SNAPSHOT, index=False)
    print(f"\n\nSnapshot saved -> {SNAPSHOT.resolve()}")
    print("You can now build the parser offline against this file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
