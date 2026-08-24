# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A turbulence-from-text research pipeline. Pilots file PIREPs (pilot reports) that include a structured `/TB` turbulence field plus free-text description. The plan is: collect PIREPs over time → strip `/TB` from text to avoid label leakage → train a 4-class severity classifier (`None`/`Light`/`Moderate`/`Severe`) → map them → fuse with weather.

Full vision lives in `README.md` and `REQUIREMENTS.md`. Phases 0 and 1 are implemented; phases 2–5 are not.

## Layout

- `explore.py` — Phase 0. One-shot schema discovery against the live AWC cache. Prints columns, resolves likely field names, shows PIREP/AIREP split and turbulence label yield, saves `snapshot.csv` for offline work.
- `collector.py` — Phase 1. Polls the same cache every 10 min, dedups, writes to SQLite (`pireps.db`). Stores both extracted typed columns and the full row as `raw_json` (insurance against bad column guesses).
- `test_collector.py` — Synthetic-data unit tests for `collector.py` (no network).
- `README.md` — Project narrative, setup, phase-by-phase plan.
- `REQUIREMENTS.md` — Numbered FR/NFR spec, data model, evaluation rules.

There are only three Python files; everything else is docs.

## Commands

Setup (Windows shown; README has macOS/Linux variant):
```bash
python -m venv venv
venv\Scripts\activate
pip install pandas requests
```

Run schema discovery (needs network, writes `snapshot.csv`):
```bash
python explore.py
```

Single test pull, to verify the collector works before leaving it running:
```bash
python collector.py --once
```

Continuous collection (run somewhere stable — the AWC cache is a 15-day rolling window, so gaps mean lost data):
```bash
python collector.py
```

Check progress:
```bash
python collector.py --stats
```

Run the synthetic-data tests:
```bash
python test_collector.py
```

Back up the SQLite database (do this regularly — losing the DB is the most common project-killer):
```bash
sqlite3 pireps.db ".backup 'pireps_backup.db'"
```

## Key design decisions (so you don't undo them by accident)

- **Dedup key** in `collector.row_hash` is `sha256(obs_time | lat | lon | raw_text)`. AWC's `pirepId` was removed in Sept 2025, so we can't use it. The cache re-serves the same reports on every poll, and duplicate PIREPs across train/test splits inflate metrics.
- **`raw_json` is mandatory**, not optional. If a column guess is wrong (AWC has renamed fields before), re-parse from the DB instead of re-collecting weeks of data.
- **HTTP 204 is not an error** — AWC returns it when the cache has nothing new. 429 backs off exponentially up to 5 min.
- **No `pirepId` in dedup** (removed upstream).
- **Label leakage is the central ML risk.** The `/TB` field must be stripped from any text fed to a model, or the classifier learns to read the answer. See `REQUIREMENTS.md` §7.4 and FR-019.
- **Class imbalance is expected.** Severe is rare. Build the TF-IDF + LogReg/SVM baseline before any transformer; report per-class precision/recall/F1, not accuracy.

## Configuration touchpoints

Two values to set before the collector is useful:

- `USER_AGENT` in both `explore.py` and `collector.py` — replace `"pirep-turbulence-research"` with something identifying. AWC filters anonymous clients.
- `COLUMNS` dict in `collector.py` — initially `None` (auto-resolved). After running `explore.py`, pin the resolved names explicitly so a future AWC schema change fails loudly instead of silently corrupting the dataset.

The two scripts share `CANDIDATES` lists. If AWC renames a field again, update both.

## Open questions worth knowing about (from REQUIREMENTS.md §14)

- Exact turbulence value vocabulary (run `--stats` after a day of collection and inspect).
- Whether to exclude AIREPs entirely (they're automated, often lack prose).
- AIREP vs PIREP share in the actual data — `explore.py` reports this.
- Reports-per-day accrual rate (run `--stats` ~24h apart and diff).
- Whether `/OV` is reliably decoded to lat/lon or whether navaid lookup is needed.
- Split strategy: random vs time-based vs location-grouped (the last prevents spatial leakage).

## Project-specific pitfalls

- **Don't run the collector in a directory that syncs to cloud storage with conflict resolution** (e.g. OneDrive) without testing — SQLite + sync clients can corrupt the WAL. The repo lives under OneDrive; if you see `database is locked` errors, move `pireps.db` to a non-synced path and symlink, or pause sync.
- **Long sleeps on Windows**: the collector polls every 600s; keep the machine awake or run in a scheduled task, not a laptop lid-closed session.
- **Phase 1 must start early** — it's the bottleneck for every later phase.
