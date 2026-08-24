# Data Engineering

> How raw PIREPs become versioned, deduplicated, queryable datasets. Authoritative for `chopcast.collector` and `chopcast.storage`.

---

## 1. Storage layers

There are three storage layers, each with a distinct shape and lifecycle.

| Layer | Format | Lifecycle | Mutability |
|---|---|---|---|
| **Raw** | SQLite `reports` table | Permanent | Append-only |
| **Processed** | Parquet, versioned by DVC | Long-term | Immutable per version |
| **Features** | Parquet, versioned | Per training run | Immutable per version |

Raw is the source of truth. If a downstream artifact is wrong, we re-derive it from raw; we never rewrite raw.

---

## 2. SQLite schema (raw layer)

The raw layer is SQLite. It is chosen because (a) we already have it, (b) the working set fits on one machine, (c) ACID guarantees are simple, and (d) `sqlite3 .backup` is a one-line operational tool.

### 2.1 Tables

```sql
-- schema_migrations
CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);

-- reports (raw, append-only)
CREATE TABLE reports (
    hash          TEXT PRIMARY KEY,        -- sha256(obs_time|lat|lon|raw_text)
    fetched_at    TEXT NOT NULL,           -- ISO 8601 UTC, our clock
    obs_time      TEXT,                    -- ISO 8601 UTC, from source
    report_type   TEXT,                    -- PIREP | AIREP | NULL
    raw_text      TEXT,                    -- source "/"-delimited string
    turbulence    TEXT,                    -- raw /TB value
    aircraft      TEXT,
    lat           REAL,                    -- -90..90, NULL if missing
    lon           REAL,                    -- -180..180, NULL if missing
    altitude      REAL,                    -- feet MSL or flight level
    raw_json      TEXT NOT NULL,           -- full source row, JSON-encoded
    source_url    TEXT NOT NULL,           -- which URL this came from
    source_etag   TEXT,                    -- for cache validation
    CONSTRAINT lat_range CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
    CONSTRAINT lon_range CHECK (lon IS NULL OR lon BETWEEN -180 AND 180)
);

CREATE INDEX idx_reports_obs_time  ON reports(obs_time);
CREATE INDEX idx_reports_turbulence ON reports(turbulence);
CREATE INDEX idx_reports_type      ON reports(report_type);
CREATE INDEX idx_reports_fetched_at ON reports(fetched_at);

-- rejected (quarantine)
CREATE TABLE rejected (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at    TEXT NOT NULL,
    reason        TEXT NOT NULL,           -- invalid_lat | bad_obs_time | ...
    raw_row       TEXT NOT NULL,           -- full source row
    source_url    TEXT NOT NULL,
    detail        TEXT                     -- parser error message
);

CREATE INDEX idx_rejected_reason ON rejected(reason);

-- runs (collection observability)
CREATE TABLE runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,           -- ok | no_data | http_error | exception
    rows_seen     INTEGER,
    rows_inserted INTEGER,
    rows_skipped  INTEGER,
    rows_rejected INTEGER,
    error         TEXT
);

CREATE INDEX idx_runs_started_at ON runs(started_at);
```

### 2.2 Why these constraints

- **`hash` is the primary key**, not a synthetic `id`. A report *is* its content; identity is intrinsic.
- **`raw_json` is mandatory**. A wrong column guess should be fixable in code, not by re-collecting weeks of data.
- **`fetched_at` and `obs_time` are separate**. The first is when we pulled it; the second is when the pilot observed it. They are often hours apart.
- **`source_url` and `source_etag` are kept** for cache validation and to reproduce a pull later.
- **`rejected` is a table, not a log line**. Quarantined rows must be inspectable and re-triable, not lost.
- **`runs` records every collection attempt**, including failures. A blank wall in the timeline is a bug, not a quiet day.

### 2.3 Migrations

Schema changes are versioned. The `schema_migrations` table records which migrations have been applied. Migrations are forward-only by default; reverse migrations require explicit justification and a test.

```python
# chopcast/storage/migrations.py
MIGRATIONS = [
    (1, "initial_schema", "CREATE TABLE ..."),
    (2, "add_source_etag", "ALTER TABLE reports ADD COLUMN source_etag TEXT"),
    # ...
]
```

The migration runner applies any unapplied migration in a single transaction per migration. A migration that fails partway leaves the database unchanged. Migrations are tested by `test_schema_migrations.py`, which spins up a populated DB, applies a forward migration, asserts the new shape, and (if a reverse exists) rolls back.

---

## 3. Deduplication policy

### 3.1 Hash definition

```
hash = sha256(obs_time | "|" | lat_rounded | "|" | lon_rounded | "|" | normalized_raw_text)
```

Where:
- `obs_time` is ISO 8601 UTC.
- `lat_rounded` and `lon_rounded` are rounded to 4 decimal places (~11 m). This is coarser than GPS but finer than realistic position noise in a PIREP, and prevents two equivalent reports from differing by a rounding artifact.
- `normalized_raw_text` is lowercased, with leading and trailing whitespace stripped and internal whitespace collapsed to single spaces. We do *not* rewrite the raw text semantically — only enough to make the hash stable.

### 3.2 Why not `pirepId`?

AWC removed `pirepId` in September 2025. We cannot rely on a stable external id. See [ADR-0004](adr/0004-dedup-strategy.md).

### 3.3 Near-duplicate handling

Reports that differ only by:
- punctuation in `raw_text` (e.g., trailing period),
- casing of `/TB MOD` vs. `/tb mod`,

…will not collide. The cleaner stage normalizes them, so they will collide *as processed records*. This is acceptable: dedup at the raw stage is intentionally conservative. The cleaning stage produces a second hash on which a tighter dedup is performed for the training set.

### 3.4 Dedup is at the SQL level

We use `INSERT OR IGNORE INTO reports` with `hash` as the primary key. There is no read-then-write path. This makes the operation atomic and concurrency-safe.

---

## 4. Data lineage

Every derived artifact records its inputs.

| Artifact | Records |
|---|---|
| Parquet processed dataset | Source raw hashes, cleaning config version, code commit |
| Parquet feature store | Source processed hashes, feature builder config version, code commit |
| Registered model | Feature store version, training config version, code commit |
| Evaluation report | Model version, test split version, code commit |

A model is reproducible if and only if the chain `commit → config → feature store version → raw hashes` is intact. We do not store raw rows in the lineage records; we store *hashes*. If the raw rows are gone, the model cannot be reproduced, and that fact must be visible.

A `lineage.json` is emitted by every pipeline run:

```json
{
  "artifact": "features",
  "version": "v3",
  "created_at": "2026-08-22T17:00:00+00:00",
  "code_commit": "abc123",
  "config_version": "cfg-7",
  "inputs": {
    "raw_hashes_count": 50231,
    "raw_hashes_sha256": "def456...",
    "processed_version": "v2"
  }
}
```

---

## 5. Dataset versioning

Processed and feature datasets are versioned explicitly.

- **Convention:** `vN` where `N` is a monotonically increasing integer.
- **Storage:** `data/processed/vN/*.parquet` and `data/features/vN/*.parquet`. Never overwrite; always create a new directory.
- **Pointer file:** `data/processed/latest -> vN` (a symlink) so other code can refer to "the current one" without hardcoding. CI verifies that `latest` points to a valid version.
- **Promotion:** Only a version that has been evaluated and promoted becomes `latest`. Promotion is a manual CLI: `chopcast-data promote processed v3`.
- **Retention:** The last 10 versions are kept on disk; older versions are moved to cold storage (object storage) but are not deleted.

### 5.1 Why Parquet

Parquet is columnar, compressed, and readable by pandas, polars, DuckDB, and Spark. It plays well with DVC for content-addressed versioning. CSV is rejected for derived datasets because of typing ambiguity and parsing cost.

---

## 6. Raw → Processed → Feature

### 6.1 Raw

The raw layer is whatever AWC sent us. It is opaque to downstream code — every consumer treats it as a bag of fields plus a JSON blob. Adding fields to the source does not require changing the schema; it changes only `raw_json`.

### 6.2 Processed

The processed layer is the result of:
1. `parser.pirep.parse()` — extracts structured fields from the raw text.
2. `labeling.map_to_severity()` — maps the raw turbulence value to a severity class.
3. `processing.cleaner.clean_text()` — strips `/TB`, normalizes whitespace.

The processed schema is:

| Column | Type | Notes |
|---|---|---|
| `hash` | str | Inherited from raw. |
| `obs_time` | datetime | UTC, parsed. |
| `lat`, `lon` | float | Inherited. |
| `altitude` | float | Feet MSL or flight level, normalized. |
| `aircraft` | str | From `/TP`. |
| `report_type` | str | `PIREP`, `AIREP`, or NULL. |
| `severity_label` | enum | `None`, `Light`, `Moderate`, `Severe`. |
| `clean_text` | str | No `/TB`, no leading/trailing whitespace. |
| `parser_version` | str | For repro. |
| `labeler_version` | str | For repro. |
| `cleaner_version` | str | For repro. |

### 6.3 Features

The feature layer is what models train on. It is produced by `processing.pipeline.build_features(row)` and contains:

| Group | Columns |
|---|---|
| **Identifiers** | `hash`, `obs_time`, `lat`, `lon` |
| **Label** | `severity_label` (target) |
| **Text** | `clean_text` (or `input_ids` + `attention_mask` for transformer) |
| **Context** | `altitude_band`, `aircraft_type`, `report_type`, `hour_of_day`, `day_of_year` |
| **Weather** (M6) | `wind_speed`, `wind_dir`, `temperature`, `pressure`, `weather_status` |

Feature columns are versioned in `feature_schema.yaml` next to the feature store. A change to the schema bumps the major version of the feature store.

---

## 7. Leakage prevention

Label leakage is the single most important failure mode. The architecture prevents it in three independent ways.

### 7.1 Structural

The `chopcast.processing.cleaner` module is the **only** function that takes raw text and returns clean text. There is no `clean_text` or `text` property on the raw row. Trainers do not have access to the raw text; they receive `FeatureRow` objects, which carry only `clean_text`.

### 7.2 Static

A lint rule (`scripts/check_no_tb_leakage.py`) scans the repository and fails if the literal `/TB` appears outside:
- `chopcast/processing/cleaner.py`
- `chopcast/parser/pirep.py` (where it is *parsed*, not passed through)
- test fixtures that intentionally contain it

This is run in CI on every commit. A regression in this rule is treated as a critical defect.

### 7.3 Test

A test injects a known-leaky input and asserts that the cleaned output does not contain the turbulence value. A test also walks the training call graph and asserts that no function reachable from `train()` accepts a `Report` (raw) object; it must accept a `FeatureRow` (clean).

---

## 8. Backup and disaster recovery

| Concern | Policy |
|---|---|
| Daily backup | `scripts/backup.ps1` runs at 03:00 local, calls `sqlite3 .backup`. |
| Retention | 30 days of daily backups, 12 monthly snapshots. |
| Off-host | Backups are copied to a separate machine or object storage; never only on the collector host. |
| Restore drill | A restore is performed into a sandbox DB quarterly. The drill is logged. |
| WAL safety | `journal_mode=WAL` is set on every connection. The collector does not run inside a cloud-sync folder (see [ADR-0006](adr/0006-no-onedrive.md)). |

Losing weeks of collected data is the most common way to slow this project down. Backups are not optional.

---

## 9. Privacy and safety

PIREPs are public operational data, but they are not "free for any use." Specifically:

- We do not publish the dataset with raw pilot identifiers. The raw schema above contains no `pirepId` because AWC stopped providing one, but if a future source reintroduces it, we drop it at ingestion.
- Predictions from the model are explicitly **not** aviation guidance. The API returns a banner response header: `X-Chopcast-Disclaimer: experimental; not for flight decisions`.
- We log requests at the API level but do not log request bodies that include raw text, in case the text contains identifying information.
