# Turbulence From Text

PIREP severity classifier, geospatial map, and weather-fusion research project.

This repository is the starting point for a larger aviation ML pipeline: collect
pilot reports, learn to classify turbulence severity from their text, plot the
reports in space and altitude, then fuse in weather data to study which
atmospheric conditions are associated with rough air.

The current code covers **Phase 0** and **Phase 1**: schema discovery and data
collection from the NOAA/NWS Aviation Weather Center aircraft reports cache.

## Project Idea

Pilots report turbulence through short, jargon-heavy PIREPs such as:

```text
UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP occasional sharp jolts
```

Those reports contain two useful things at once:

- **Free text** that describes the flight conditions.
- **Structured turbulence fields** such as `/TB LGT`, `/TB MOD`, or `/TB SEV`.

That makes the project tractable. The structured turbulence field can provide a
label, while the remaining report text becomes the model input. The important
catch is label leakage: the `/TB` field must be removed before training, or the
model simply learns to read the answer.

## What We Are Building

### 1. Classify

Train an NLP model that maps cleaned PIREP text to a turbulence class:

- `None`
- `Light`
- `Moderate`
- `Severe`

The first model should be a strong baseline: TF-IDF plus Logistic Regression or
Linear SVM. A later version can fine-tune a small transformer such as
DistilBERT, especially because aviation text is terse and domain-specific.

### 2. Map

Plot reports and model predictions on an interactive geospatial map. Reports
should be filterable by severity, altitude or flight level, aircraft type, and
time.

The map is not just presentation. It is also a debugging tool. If reports cluster
in impossible locations, the `/OV` parsing or geocoding logic is probably wrong.

### 3. Explain

Fuse each PIREP with nearby weather observations and derived features:

- nearest METAR in space and time
- wind speed and direction
- pressure and temperature signals
- convective indicators
- possible upper-air or gridded wind/temperature products later

This is the most original part of the project. The question becomes: which
weather signatures most strongly co-occur with, or precede, moderate-to-severe
turbulence?

## Why This Project Is Interesting

This is not another generic sentiment classifier. It uses real operational
aviation data, deals with noisy domain language, has a geospatial component, and
connects naturally to aerospace and flight-safety work.

The end-to-end pipeline looks like real applied ML:

```text
collect -> parse -> label -> model -> map -> fuse weather -> explain
```

## Data Source

Primary source:

- NOAA/NWS Aviation Weather Center public data
- API/cache host: `https://aviationweather.gov`
- No API key required
- Custom `User-Agent` recommended

This repo currently uses the aircraft reports cache:

```text
https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz
```

**Important constraint:** the cache is a rolling **~90-minute** window, measured
live rather than assumed. There is no backfill endpoint, so every hour the
collector is not running is an hour of data that cannot be recovered. The dataset
accrues only while you are collecting, which makes this the bottleneck for the
whole project.

Measured accrual: **~32,000 reports/day**, of which **~1,500-2,400/day** are
labeled pilot reports.

## Repository Status

Implemented now:

- `explore.py` discovers the real AWC cache schema.
- `collector.py` polls the cache, deduplicates reports, and stores them in
  SQLite.
- `test_collector.py` validates collector behavior against synthetic data.

Not implemented yet:

- PIREP parser and label mapper.
- Leakage-safe text cleaner.
- Training dataset builder.
- Baseline classifier.
- Transformer classifier.
- Geospatial map.
- METAR/weather fusion layer.
- Analysis/reporting notebooks or app.

## Setup

Create a virtual environment and install the current dependencies:

```bash
python -m venv venv
venv\Scripts\activate
pip install pandas requests
```

On macOS/Linux:

```bash
python -m venv venv
source venv/bin/activate
pip install pandas requests
```

Set a custom identifier in both `explore.py` and `collector.py`:

```python
USER_AGENT = "pirep-turbulence-yourname"
```

AWC recommends identifiable automated traffic. Anonymous or generic clients may
be filtered.

## Phase 0: Understand The Data

Goal: inspect the live schema and read real reports before writing ML code.

Run:

```bash
python explore.py
```

This script:

- downloads the current aircraft reports cache
- prints all column names and non-null counts
- resolves likely fields such as raw text, turbulence, report type, altitude,
  aircraft type, latitude, longitude, and observation time
- shows PIREP/AIREP distribution
- estimates turbulence label yield
- prints sample reports
- saves `snapshot.csv`

After running it, copy the resolved column names into `COLUMNS` in
`collector.py`. Auto-resolution exists, but explicit columns make schema changes
fail loudly instead of quietly corrupting your dataset.

The most important activity in this phase is reading sample reports. The format
is compact, inconsistent, and full of aviation abbreviations. Assumptions made
without looking at the raw data will usually become parser bugs later.

## Phase 1: Collect Reports

Goal: start accruing a local historical dataset.

Run one pull first:

```bash
python collector.py --once
```

Then run the continuous collector:

```bash
python collector.py
```

Check progress and liveness at any time:

```bash
python collector.py --stats     # how much data, and what kind
python collector.py --health    # exit 0 if collecting, 1 if stalled
```

The collector stores data in `pireps.db`. Each row is stored twice:

- extracted typed columns for easy querying
- full `raw_json` so bad extraction choices can be fixed later without
  recollecting weeks of data

Deduplication uses a hash of `obs_time + lat + lon + raw_text`. The cache is a
rolling snapshot, so repeated polls re-serve the same reports; without dedup,
duplicates leak across the train/test split and inflate metrics. Latitude and
longitude are formatted to fixed precision before hashing, because a missing
value elsewhere in a pull can flip the column from `int64` to `float64` and make
`37` and `37.0` hash differently.

### Run it on a server, not your laptop

With a ~90-minute window, a laptop that sleeps loses data every time you close
the lid. **See [deploy/RUNBOOK.md](deploy/RUNBOOK.md)** for a step-by-step AWS EC2
deployment: systemd service, boot persistence, health checks, and nightly S3
backups. Roughly $6-8/month, often $0 on intro credits.

Because a stalled collector and a quiet feed look identical from outside, check
`--health` every few days. It exits non-zero if no successful pull has landed
within the threshold.

## Phase 2: Parse And Label

Goal: turn raw reports into a clean labeled dataset.

Expected output:

```text
raw_text_clean, severity_label, lat, lon, flight_level, aircraft_type, obs_time
```

### Working sets: use the views, not the raw table

The database ships three views so you never hand-filter report types:

| View | Rows | Use it for |
| --- | --- | --- |
| `pireps` | pilot reports only | anything text-related |
| `trainable` | pilot reports carrying a turbulence label | the Phase 3 dataset |
| `wx_altitude` | AIREP temperature and wind at flight level | Phase 5 weather fusion |

```sql
SELECT raw_text, turbulence FROM trainable;
```

**Why AIREPs are kept even though they have no prose.** They are ~93% of rows and
useless to a text model, so deleting them is tempting. But they supply **99.8% of all
temperature and wind observations**, recorded at a median 37,000 ft — that is the
weather-at-altitude source that replaces surface METAR in Phase 5, and surface METAR
cannot describe turbulence at FL340. Deleting them would also be irreversible: the AWC
cache is a ~90-minute window with no backfill. Filter at query time; never delete.

Key tasks:

- Parse or verify `/TB`, `/OV`, `/FL`, `/TP`, and `/TM`.
- Map turbulence values into the four-class scheme.
- Handle combinations such as `LGT-MOD` by taking the maximum severity.
- Handle negatives such as `NEG` or missing turbulence.
- Decide whether to exclude AIREPs, which often lack useful prose.
- Strip `/TB ...` from the model input to prevent label leakage.

Suggested label mapping:

| Raw turbulence signal | Label |
| --- | --- |
| `NEG`, missing, none observed | `None` |
| `LGT`, `LGT CHOP` | `Light` |
| `MOD`, `LGT-MOD`, `OCNL MOD` | `Moderate` |
| `SEV`, `MOD-SEV`, `EXTRM` | `Severe` |

The exact mapping should be documented once real values from `snapshot.csv` and
`pireps.db` are inspected.

## Phase 3: Train The Classifier

Goal: predict severity from cleaned report text, with optional structured
features.

### Baseline First

Build this before any neural model:

- TF-IDF features from cleaned text
- Logistic Regression or Linear SVM
- stratified train/test split
- class weights or training-only resampling
- per-class precision, recall, and F1

Do not optimize for accuracy alone. With imbalanced classes, a model can look
good by mostly predicting the majority class.

### Upgrade

After the baseline:

- fine-tune DistilBERT or another small transformer
- compare directly against the baseline
- optionally fuse structured features such as flight level and aircraft type

If the transformer does not beat the baseline, that is still a valid result.
Small, noisy datasets often reward simpler models.

## Phase 4: Build The Map

Goal: make the reports and predictions visible.

Candidate tools:

- `folium` for a quick interactive map
- `geopandas` and `contextily` for static/publication-style maps
- a small web app later if the project grows

Useful map controls:

- severity color
- time range
- altitude or flight-level band
- aircraft type
- actual label vs predicted label
- confidence or probability

## Phase 5: Weather Fusion

Goal: connect reported turbulence to atmospheric conditions.

Start simple:

- For each PIREP, find the nearest METAR station in space and time.
- Extract basic weather features.
- Validate several matches manually.
- Compare turbulence severity against weather features.

Then improve:

- add AIRMET/SIGMET turbulence products
- explore gridded wind and temperature aloft data
- derive wind shear or instability features
- test whether weather features improve the classifier

METAR is surface-level, so it may be weak for en-route turbulence at FL300+.
That limitation should be documented instead of hidden.

## Suggested Order Of Attack

1. Run `explore.py` and inspect the schema.
2. Start `collector.py` as early as possible.
3. Build the parser and label mapper on `snapshot.csv`.
4. Create a leakage-safe training dataframe from `pireps.db`.
5. Train the TF-IDF baseline.
6. Add the map.
7. Try the transformer only after the baseline is working.
8. Add weather fusion once enough reports have accumulated.

Expected calendar time: 4-6 weeks, mostly gated by data collection.

Expected active work: about 3 weeks for a junior developer with guidance.

## Backups

Back up the SQLite database regularly:

```bash
sqlite3 pireps.db ".backup 'pireps_backup.db'"
```

Losing weeks of collected data is the easiest way to slow the project down.

## Tests

Run:

```bash
python test_collector.py
```

The tests use synthetic data and do not need network access. They validate:

- column resolution
- repeat-pull deduplication
- partial-overlap deduplication
- field extraction
- `raw_json` completeness
- sparse/missing-column handling

## Open Questions

- What exact turbulence values appear in the live data?
- Should AIREPs be excluded entirely or kept for non-text analysis?
- How many labeled PIREPs arrive per day?
- How rare are `Severe` and `Moderate-Severe` reports?
- Is `/OV` already decoded to lat/lon reliably enough, or do we need navaid
  lookup support?
- Should the final deliverable be a notebook, a map app, a paper-style report,
  or all three?

## Mentoring Notes

For a junior developer, the highest-value habits in this project are:

- inspect real data before designing abstractions
- build the simple baseline first
- prevent label leakage deliberately
- measure per-class metrics, not just accuracy
- keep raw data so mistakes can be reprocessed
- validate geospatial and weather matches by hand before trusting automation

