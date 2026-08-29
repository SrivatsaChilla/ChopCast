# ChopCast

A research-grade system that turns operational pilot reports (PIREPs) into structured, geospatial, weather-aware intelligence about turbulence. It collects raw reports continuously, learns to classify turbulence severity from report text, plots the resulting observations on a map, and fuses them with atmospheric data to surface the weather signatures that drive rough air.

> **Status:** Pre-M0. The original 3-file prototype is in `explore.py`, `collector.py`, and `test_collector.py`. The production architecture described below is the target; the M0 milestone migrates the prototype into the new package layout. See [ADR-0001](docs/adr/0001-redesign-rationale.md).

> **Disclaimer:** Experimental. Not for flight decisions. Predictions from this system are research artifacts, not aviation guidance.

## Quickstart

```bash
# Setup
python -m venv .venv
source .venv/bin/activate          # or: .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Configure (do not skip — AWC requires a User-Agent)
cp .env.example .env
# edit .env to set CHOPCAST_COLLECTOR__USER_AGENT

# Validate
chopcast config validate

# Run a single collection cycle
chopcast-collector once

# Or run continuously
chopcast-collector run

# Check progress
chopcast-collector status

# Run tests
pytest
```

> **Important:** if this repo lives under a cloud-sync folder (OneDrive, Dropbox, iCloud, Google Drive), set `CHOPCAST_PATHS__ROOT` in `.env` to a non-synced location. SQLite + sync clients interact badly. See [ADR-0006](docs/adr/0006-no-onedrive.md).

## Project idea

Pilots file PIREPs that include a structured `/TB` turbulence field plus free-text description. The plan:

1. **Collect** PIREPs continuously (the AWC cache is a **~90-minute** rolling window, measured live; we accumulate over time).
2. **Strip `/TB` from the model input** to prevent label leakage — the single most important failure mode of PIREP classifier projects. See [ADR-0003](docs/adr/0003-leakage-prevention.md).
3. **Train** a 4-class severity classifier (`None` / `Light` / `Moderate` / `Severe`). Start with a TF-IDF + LogReg baseline; upgrade to a DistilBERT classifier behind the same `Model` protocol.
4. **Map** the reports and predictions on an interactive map.
5. **Fuse** each PIREP with nearby weather observations and see which features improve classification.

A PIREP looks like:

```
UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP occasional sharp jolts
```

That single line contains both the label (`/TB MOD`) and the model input (everything else). Removing `/TB` and using the rest to *predict* turbulence is the project's central challenge.

## Documentation

The architectural blueprint lives in [`docs/`](docs/). Read in this order:

1. [Architecture](docs/ARCHITECTURE.md) — system overview, Mermaid diagrams, design principles, glossary.
2. [Roadmap](docs/ROADMAP.md) — eight milestones (M0 foundation → M7 deployment) with deliverables and definition of done.
3. [Data engineering](docs/DATA_ENGINEERING.md) — schema, dedup, dataset versioning, leakage prevention.
4. [ML architecture](docs/ML_ARCHITECTURE.md) — the `Model` protocol, training, evaluation, model registry.
5. [Module design](docs/MODULE_DESIGN.md) — package layout, module contracts, dependency rules.
6. [Testing](docs/TESTING.md) — unit, golden, integration, regression, and lint tests.
7. [Configuration](docs/CONFIGURATION.md) — config schema, profile overlays, `.env`, secrets.
8. [Contributing](docs/CONTRIBUTING.md) — workflow, branches, commits, reviews.
9. [Standards](docs/STANDARDS.md) — coding style, type system, naming, anti-patterns.
10. [ADRs](docs/adr/) — accepted architectural decisions and the reasoning behind them.

The original 386-line requirements document is preserved at [`REQUIREMENTS.md`](REQUIREMENTS.md) for reference. The new architecture supersedes it; the FR/NFR numbers it introduces are tracked in [ROADMAP.md](docs/ROADMAP.md).

## Repository layout

```
chopcast/         source code (created in M0)
configs/          YAML configuration
data/             datasets (gitignored, DVC-tracked)
models/           model registry (gitignored)
tests/            unit, integration, golden, regression, lint
docs/             this tree
notebooks/        exploratory analysis
scripts/          operational scripts
pyproject.toml    package definition
.env.example      template for local secrets
```

See [ADR-0002](docs/adr/0002-repository-layout.md).

## Commands

| Command | Purpose |
|---|---|
| `chopcast-collector once` | Single collection cycle. |
| `chopcast-collector run` | Continuous collection loop. |
| `chopcast-collector status` | Show last run, accrual rate, dedup rate. |
| `chopcast-collector rejected` | Inspect quarantined rows. |
| `chopcast-parse "UA /OV SFO /TB MOD CHOP /FL350"` | Parse a single PIREP. |
| `chopcast-train run` | Train a model. |
| `chopcast-eval compare <a> <b>` | Compare two model versions. |
| `chopcast-registry promote <id>` | Promote a model to production. |
| `chopcast-map` | Generate the static map. |
| `chopcast config show` | Print the effective config. |

## Data source

- **AWC aircraft reports cache:** `https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz`
- No API key required; AWC requires a custom User-Agent.
- The cache is a rolling window of roughly **90 minutes** (measured: `observation_time`
  spanning 00:08–01:37Z in one pull). There is no backfill endpoint, so the collector
  must run continuously — any hour it is down is an hour of reports that cannot be recovered.
- See [DATA_ENGINEERING.md](docs/DATA_ENGINEERING.md) §6 for the schema and the rationale for storing raw data immutably.

### Working sets

Query the views, not the `reports` table directly:

| View | Contents | Use it for |
| --- | --- | --- |
| `pireps` | `PIREP` + `Urgent PIREP` only | anything text-related |
| `trainable` | pilot reports labeled in either turbulence layer | the supervised dataset |
| `wx_altitude` | AIREP temperature and wind at flight level | Phase 5 weather fusion |

```sql
SELECT raw_text, turbulence FROM trainable;
```

`trainable` still contains `/TB` in `raw_text` by design — removing it belongs to
`chopcast.processing.cleaner` and nothing else (ADR-0003).

### Why AIREPs are kept

AIREPs are roughly 93% of collected rows and carry no prose, so deleting them looks
obvious. Measured against live data, it is not:

| | kept | if AIREPs were deleted |
| --- | --- | --- |
| wind readings | 2,411 | **1** |
| temperature readings | 2,427 | **15** |

They hold ~99.8% of all temperature and wind observations, recorded at a median
37,000 ft against 14,500 ft for pilot reports. Deletion is also irreversible: with a
~90-minute cache window and no backfill, those observations cannot be re-collected.
**Filter at query time; never delete.**

One limitation to record: AIREPs **cannot** be co-located with PIREPs for weather
fusion. 99.6% sit outside the continental US on oceanic tracks, the median distance
from a labeled PIREP to the nearest AIREP is ~1,478 km, and only 2 of 328 labeled
reports find a match even at 400 km / 90 min / 10,000 ft. Phase 5 needs gridded
RAP/HRRR fields. The AIREPs remain useful as a standalone oceanic dataset.

## License

TBD. Treat as "all rights reserved" until decided.
