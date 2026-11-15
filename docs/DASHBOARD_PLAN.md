# ChopCast Dashboard — Build Plan

**Status:** Draft for approval. No `dashboard/` code has been written.
**Created:** 2026-11-14
**Scope:** a read-only Django dashboard that reports every pipeline stage, centred on the map layer.
**Evidence base:** `docs/ONBOARDING.md`, `docs/ISSUES.md` (82 existing items), and a read-only inspection of `chopcast/`, `configs/`, `data/raw/pireps.db`, `models/registry/`, and `runs/` at `main` @ `29fb780`.

---

## 1. Naming: there is no `maps/` module

The brief says "centred on the `maps/` module". The repository has **no `maps/` directory and no `maps` Python package**. The only map code is:

- `chopcast/map/folium_app.py` — one function, `generate_map(settings, registry, model_id, output_path)`.
- `chopcast/map/` has **no `__init__.py`** (ISS-057), so it is not an installable package.
- `chopcast map` in `chopcast/cli.py` is the only caller, and it currently fails with `NameError: Path` (ISS-016).
- The declared `chopcast-map` console script points at `chopcast.map.cli`, which does not exist (ISS-058).
- No generated `*.html` map file exists anywhere under the repo.

**Assumption for this plan:** "`maps/`" means the map layer implemented by `chopcast/map/folium_app.py`, and the Maps page is the centrepiece of the dashboard. The dashboard will not import that module (it has bugs, writes files, loads joblib artifacts, and needs network assets). It will reproduce the map's semantics by reading the same `trainable` data and rendering it itself. If you meant a different module or an external `maps/` directory, stop here and correct the assumption before implementation.

This is called out in the plan rather than silently guessed.

---

## 2. What the pipeline actually produces (snapshot)

These are the live values the dashboard must be able to display on day one. They also set the empty-state and warning expectations.

### 2.1 Raw data — `data/raw/pireps.db`

| Fact | Value |
|---|---|
| File | `data/raw/pireps.db` (ignored by git) |
| Reports | **3,525** |
| By `report_type` | AIREP **2,928**, PIREP **591**, Urgent PIREP **6** |
| `trainable` rows | **290** |
| `reports` columns | `hash, fetched_at, obs_time, report_type, raw_text, turbulence, turbulence_2, turbulence_type, turbulence_freq, aircraft, lat, lon, altitude, raw_json` |
| Missing vs target schema | no `source_url`, no `source_etag`, no `rejected` table, no `schema_migrations` table |
| Legacy `runs` columns | `id, ran_at, rows_seen, inserted, skipped, status` (**2 rows**, both `ok`) |
| Target `runs` columns | `id, started_at, finished_at, status, rows_seen, rows_inserted, rows_skipped, rows_rejected, error` |
| `trainable` definition | `SELECT * FROM reports WHERE report_type IN ('PIREP','Urgent PIREP') AND turbulence IS NOT NULL` (legacy view) |
| Target `trainable` definition | `SELECT hash, obs_time, raw_text, turbulence, turbulence_2, ... FROM pireps WHERE turbulence IS NOT NULL OR turbulence_2 IS NOT NULL` (migration 3) |
| `turbulence_2` | 14 non-null (`LGT` 1, `MOD` 7, `NEG` 6) |
| Parsed labels | 288 `None`, 1 `Light`, 1 `Moderate` (parser failure, ISS-008) |

### 2.2 Models and registry — `models/registry/`

| Fact | Value |
|---|---|
| Registry DB | `models/registry/registry.db` |
| Tables | `models`, `promotions`, **plus stray raw-data tables/views** (`reports`, `pireps`, `trainable`, `wx_altitude`, `schema_migrations`) — ISS-005 |
| Models | **2** rows |
| Model rows | id 1 `v1_test` (`model_kind=baseline`), id 2 `v1_transformer` (`model_kind=baseline` — mislabelled) |
| Promotions | **0**; `current("production")` returns `None` |
| Metrics | Both models identical: `accuracy 1.0`, `macro_f1 0.333`, `weighted_f1 1.0`, `n_samples 58`, only `None` has support |
| Artifacts | `baseline-v1_test/`, `baseline-v1_transformer/`; each has `pipeline.joblib`, `manifest.txt`, `metrics.json`, `lineage.json` |
| `artifact_path` | stored relative (`models\registry\...`), CWD-dependent — ISS-007 |
| Lineage | `created_at 2026-10-17T16:15:53Z`, `code_commit "unknown"`, `config_version "v1"`, counts 290/290/232/58 |

### 2.3 Splits, features, logs

| Fact | Value |
|---|---|
| Split manifests | `runs/split-v1_test.json`, `runs/split-v1_transformer.json` |
| Split contents | 232 `train_hashes`, 58 `test_hashes`, `version`, `seed 42`, `mode stratified`; **no timestamps, no run ID** |
| Feature dirs | `data/features/` and `data/processed/` exist but are **empty** |
| Logs dir | `logs/` exists but is **empty** |
| Root log | `collector.log` (158 bytes), two plain-text lines: `2026-08-30 21:00:28 ... TOTAL=1707`, `2026-10-03 19:42:49 ... TOTAL=3525`; local time ≈ UTC+3 |
| Map output | none; `generate_map()` defaults to `./turbulence_map.html` in the CWD |

### 2.4 What this means for the UI

- The dashboard must lead with **data-quality warnings**, not bury them: 285/290 rows fail to yield a parsed label (ISS-008), the two models are degenerate, and the registry has no production model.
- It must distinguish **legacy** vs **target** schema everywhere (badge on every data card).
- It must show **inferred** training/evaluation history, not pretend a run table exists.
- Empty states are the normal case for features, logs, and maps; they must still look intentional.

---

## 3. Constraints and design principles

### 3.1 Hard constraints from the brief

1. **Separate top-level project** at `dashboard/`; do not modify `chopcast/`.
2. **Read-only** against pipeline data:
   - SQLite opened with `file:...?mode=ro` (URI), `PRAGMA query_only=ON`.
   - Never run migrations on `data/raw/pireps.db` or `models/registry/registry.db`.
   - Never write pipeline artifacts, splits, registry rows, or logs.
   - Django's own database (only if admin is enabled) is a separate file under `dashboard/var/`.
3. **One adapter layer** for all pipeline access, configured by settings/env. If open decisions change (ISS-001…007), only the adapter and config change.
4. **No crashes on missing/empty data.** Every page has an empty state and a per-source error state.
5. **Python consistent with `pyproject.toml`** (`>=3.11`).
6. **All front-end libraries vendored**, no CDNs; works offline.
7. **Server-rendered Django templates + light JS**, no SPA framework.
8. **Pages:** Overview, Data, Labels, Training, Evaluation, Model registry, Maps, Logs/Jobs, System, Known Issues.
9. **Quality bar:** responsive UI, navigation, filtering, sorting, pagination; tests for adapter and key views (including empty/missing data); demo-data management command; `dashboard/README.md`.
10. **Do not resolve open decisions.** Display whichever variant exists and label it.
11. **New pipeline problems go to `docs/ISSUES.md`**, not fixed.

### 3.2 Principles used to resolve design choices

- **Evidence over inference.** Show stored values and file metadata; when a value is derived or inferred, label it `inferred` and say from what.
- **Provenance is part of the data.** Every card/table carries a small badge: `legacy`, `target`, `path A`, `path B`, `inferred`, `stale`, `missing`.
- **Fail soft, never silent.** A broken JSON file renders one row with an error badge; it does not 500 the page. A missing DB renders the page frame with a "source missing" panel and setup hint.
- **No execution of pipeline code.** The dashboard reads SQLite and files. It does not import `chopcast`, load joblib models, parse PIREPs, or call `generate_map()`. This avoids ISS-008/016/017/021/078 and keeps the read-only guarantee credible.
- **One request = one snapshot.** All sources are read within a request through the adapter; timestamps are captured once and shown in the header so cards cannot disagree about "now".
- **Progressive enhancement.** Filters and pagination are normal GET forms; HTMX is optional sugar. No JS is required to see data.
- **Boring, legible UI.** High information density, clear typographic hierarchy, restrained colour reserved for status/severity.

---

## 4. Architecture

### 4.1 Stack and versions

| Choice | Recommendation | Why |
|---|---|---|
| Python | **3.13** for local verification; support **3.11–3.13** | Core declares `>=3.11`; `py -0p` shows 3.13 installed at `%LOCALAPPDATA%\Programs\Python\Python313`. 3.14 is the shell default but Django 5.2 does not officially support it. |
| Django | **5.2 LTS** (5.2.19 at time of writing) | LTS with security support to 2028; supports Python 3.10–3.13, matching the core floor and the deploy script's 3.11. Do **not** use the locally installed Django 4.2.30 — it is past end of life. |
| DB for Django | none by default (signed-cookie sessions); optional SQLite at `dashboard/var/dashboard.sqlite3` only if admin is enabled | Avoids any migrations in the default install; keeps pipeline DBs untouched. |
| Templates | Django templates | Required. |
| CSS | hand-written CSS with custom properties; no framework | Small, offline, no build step. |
| JS | vanilla + HTMX (optional) + Leaflet + Chart.js | Vendored, pinned, minimal. |
| Tests | `pytest`, `pytest-django` | Matches core test tooling. |
| Packaging | `dashboard/pyproject.toml` (separate project) or `requirements.txt` | Keeps the dashboard out of the core package. Recommend a separate `pyproject.toml` with `requires-python = ">=3.11"` and pinned Django. |

**Version caveat to approve:** Django 5.2 supports 3.11–3.13, not 3.14. The dashboard will therefore run under `py -3.13` locally. If you require it to run on the 3.14 shell default, the alternative is Django 6.0/6.1 with a dashboard floor of 3.12; that is a different support matrix and should be an explicit choice.

### 4.2 Directory layout

```
dashboard/
├── manage.py
├── pyproject.toml                  # dashboard-only project metadata + tool config
├── README.md
├── .env.example                    # CHOPCAST_DASHBOARD_* variables
├── config/
│   ├── __init__.py
│   ├── settings.py                 # env-driven; no pipeline imports
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── adapters/                       # the ONLY pipeline access layer
│   ├── __init__.py                 # get_adapter() singleton factory
│   ├── settings.py                 # AdapterSettings.from_env()
│   ├── types.py                    # DTOs, enums, SourceStatus, Result
│   ├── sqlite_ro.py                # read-only connection + introspection
│   ├── schema_probe.py             # legacy/target/registry capability detection
│   ├── reports.py                  # counts, time range, rows, detail, quality
│   ├── labels.py                   # value counts, rule preview, trainable variants
│   ├── training.py                 # artifact + registry + split joining
│   ├── evaluation.py               # metrics/report loading, comparisons
│   ├── registry.py                 # models, promotions, artifact existence
│   ├── maps.py                     # point queries, generated map file index
│   ├── logs.py                     # bounded tail + parse + filter
│   ├── system.py                   # config, paths, versions, sanity checks
│   ├── markdown.py                 # safe renderer for docs/ISSUES.md
│   └── cache.py                    # per-request / short-TTL cache
├── apps/
│   ├── core/                       # base, overview, system, issues, health
│   ├── pipeline/                   # data, labels, training, evaluation, registry, logs
│   └── geo/                        # maps + map data/file endpoints
├── templates/
│   ├── base.html
│   ├── partials/                   # nav, status banner, empty, error, table, pagination, badges
│   ├── core/
│   ├── pipeline/
│   └── geo/
├── static/
│   ├── css/app.css
│   ├── js/app.js
│   ├── vendor/
│   │   ├── leaflet/1.9.4/
│   │   ├── leaflet-markercluster/1.5.3/
│   │   ├── leaflet-heat/0.2.0/
│   │   ├── chartjs/4.4.x/
│   │   ├── htmx/2.0.x/
│   │   └── world/                  # Natural Earth 110m GeoJSON for offline base layer
│   └── THIRD_PARTY_LICENSES.md
├── management/commands/
│   └── demo_data.py                # writes ONLY under dashboard/var/demo
├── tests/
│   ├── adapters/
│   ├── views/
│   ├── fixtures/
│   └── conftest.py
└── var/                            # runtime-only; gitignored (Django DB, demo data)
```

### 4.3 Why a separate adapter package (not Django models)

- Pipeline data has **no stable schema** while ISS-001…007 are open. Django models would freeze the current shape and require migrations for every variant.
- The dashboard must read **legacy and target** shapes simultaneously; an ORM mapping would force one.
- A plain-Python adapter is testable without Django, enforces read-only in one place, and makes the future "swap to an API" change a single package replacement.
- No Django ORM model represents a pipeline table. Templates receive immutable DTOs.

### 4.4 Request flow

```
request
  -> view (apps/*)
       -> get_adapter()            # singleton built from AdapterSettings
            -> service method      # e.g. reports.summary()
                 -> sqlite_ro / file readers
                 -> DTO + SourceStatus
       -> template (server-rendered)
  -> response
```

Every service method returns a `Result[T]`:

```python
@dataclass(frozen=True)
class Result(Generic[T]):
    data: T | None
    status: SourceStatus          # ok | empty | missing | schema_mismatch | error | not_configured
    error: str | None = None
    provenance: str | None = None # "legacy", "target", "path A", ...
```

Views never catch `sqlite3.Error` directly; `sqlite_ro` translates it into a `SourceStatus` with a safe message (no stack trace, no absolute path leakage beyond configured roots).

## 5. The adapter layer

### 5.1 Public surface

```python
# adapters/__init__.py
def get_adapter() -> "Adapter": ...

@dataclass(frozen=True)
class Adapter:
    settings: AdapterSettings
    reports: ReportService
    labels: LabelService
    training: TrainingService
    evaluation: EvaluationService
    registry: RegistryService
    maps: MapService
    logs: LogService
    system: SystemService

    def capabilities(self) -> Capabilities: ...
    def health(self) -> list[SourceStatus]: ...
```

Services are plain classes constructed with `AdapterSettings` and a shared `ReadOnlyDatabase` helper. No service holds a long-lived SQLite connection; each query opens a short read-only connection and closes it (SQLite is fast at this size, and it avoids stale locks under OneDrive).

### 5.2 Configuration (`AdapterSettings`)

All values come from `CHOPCAST_DASHBOARD_*` environment variables, with safe defaults relative to the repository root. `dashboard/.env` is optional and loaded by `config/settings.py` with a tiny parser (only `CHOPCAST_DASHBOARD_*`, never overrides an existing environment variable, no shell expansion). The core `.env` is **not** read (ISS-036), and the dashboard deliberately does not pretend otherwise.

| Variable | Default | Purpose |
|---|---|---|
| `CHOPCAST_DASHBOARD_ROOT` | parent of `dashboard/` | Repository root for all relative defaults |
| `CHOPCAST_DASHBOARD_RAW_DB` | `<root>/data/raw/pireps.db` | Raw reports DB (read-only) |
| `CHOPCAST_DASHBOARD_REGISTRY_DB` | `<root>/models/registry/registry.db` | Registry DB (read-only) |
| `CHOPCAST_DASHBOARD_ARTIFACT_DIRS` | `<root>/models/registry;<root>/models/artifacts` | Where to look for model artifact directories (OS path separator) |
| `CHOPCAST_DASHBOARD_RUNS_DIR` | `<root>/runs` | Split manifests and run files |
| `CHOPCAST_DASHBOARD_FEATURES_DIR` | `<root>/data/features` | Feature datasets |
| `CHOPCAST_DASHBOARD_PROCESSED_DIR` | `<root>/data/processed` | Processed datasets |
| `CHOPCAST_DASHBOARD_LOGS_DIRS` | `<root>/logs;<root>` | Log search roots (root adds `collector.log`) |
| `CHOPCAST_DASHBOARD_MAP_DIRS` | `<root>/runs/maps;<root>/data/maps;<root>/maps;<root>` | Generated map HTML search roots |
| `CHOPCAST_DASHBOARD_CONFIG_DIR` | `<root>/configs` | YAML config files |
| `CHOPCAST_DASHBOARD_DOCS_DIR` | `<root>/docs` | `ISSUES.md` and docs |
| `CHOPCAST_DASHBOARD_PROFILE` | `None` | Optional profile label to display and overlay (`dev`/`prod`/`ci`) |
| `CHOPCAST_DASHBOARD_TIMEZONE` | `UTC` | Display timezone for timestamps |
| `CHOPCAST_DASHBOARD_PAGE_SIZE` | `50` | Default table page size |
| `CHOPCAST_DASHBOARD_MAX_PAGE_SIZE` | `200` | Hard cap |
| `CHOPCAST_DASHBOARD_MAP_MAX_POINTS` | `2000` | Max markers returned per map query |
| `CHOPCAST_DASHBOARD_LOG_TAIL_BYTES` | `262144` | Max bytes read from the end of a log file |
| `CHOPCAST_DASHBOARD_CACHE_SECONDS` | `10` | Short-TTL cache for expensive aggregates |
| `CHOPCAST_DASHBOARD_TILE_URL` | empty | Empty = offline vendored world layer; set to a tile URL for online basemaps |
| `CHOPCAST_DASHBOARD_ENABLE_ADMIN` | `0` | Optional Django admin (adds auth/contenttypes and a separate DB) |
| `CHOPCAST_DASHBOARD_ALLOW_DOWNLOADS` | `1` | Enable generated-map download endpoint |

`AdapterSettings` validates that every path is absolute after resolution, that no read-write flag exists, and that the raw DB / registry DB are not inside `dashboard/var/`. It never creates pipeline directories. It may create `dashboard/var/` (runtime only).

### 5.3 Read-only SQLite mechanics

```python
def connect_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 2000")
    return conn
```

Rules:

1. `mode=ro` always; never `mode=rw`, `mode=rwc`, or a plain path.
2. `PRAGMA query_only=ON` as a second line of defence.
3. No `executescript`, no DDL, no `VACUUM`, no `ATTACH` of writable files.
4. Every query has a `LIMIT` (default `page_size`, hard cap) and a column allowlist.
5. Identifiers are never interpolated from user input; sort columns come from a whitelist map.
6. WAL caveat: a read-only connection to a WAL database may need the `-shm` file. If SQLite raises `unable to open database file` and a `-wal` file exists, return `SourceStatus(state="error", detail="Database is in WAL mode and cannot be opened read-only while the writer holds it. Point the dashboard at a snapshot copy.")`. Do **not** silently copy or mutate the DB. A future optional `--snapshot` command can copy to `dashboard/var/` if approved.
7. Read-only guarantee is tested by hashing the DB file and sidecar files before/after a full page crawl.

### 5.4 Capability detection (`schema_probe.py`)

The adapter must not assume a schema. It probes once per request (cached briefly) and returns a profile:

```python
@dataclass(frozen=True)
class RawDbProfile:
    state: str                 # legacy | target | mixed | unknown | missing
    tables: frozenset[str]
    columns: dict[str, tuple[str, ...]]   # reports, runs, trainable, ...
    views: dict[str, str]      # name -> SQL text (from sqlite_master)
    schema_migration_versions: tuple[int, ...]
    trainable_predicate: str | None       # "primary_only" | "either_layer" | "unknown"
    has_report_type_in_trainable: bool
    has_rejected: bool
    runs_shape: str            # "legacy" | "target" | "unknown"
    notes: tuple[str, ...]     # human-readable findings
```

Detection rules (evidence-based, no guessing):

- `legacy`: `reports` has `turbulence_2` and lacks `source_url`; `runs` has `ran_at`; no `schema_migrations`.
- `target`: `reports` has `source_url` + `source_etag`; `rejected` exists; `runs` has `started_at`.
- `mixed`: anything else; list the exact missing/extra columns.
- `trainable_predicate` is read from `sqlite_master.sql`:
  - contains `turbulence IS NOT NULL OR turbulence_2 IS NOT NULL` → `either_layer`;
  - contains `turbulence IS NOT NULL` without `OR turbulence_2` → `primary_only`;
  - else `unknown`.
- `has_report_type_in_trainable` from `PRAGMA table_info(trainable)`.
- Registry profile: `models`/`promotions` present, plus a warning if `reports`/`pireps`/`trainable` are also present (ISS-005).

The System page and every data card show the profile. If the target schema is later adopted (ISS-002), only the probe and queries change.

### 5.5 DTOs (selected)

```python
@dataclass(frozen=True)
class ReportSummary:
    total: int
    by_type: dict[str, int]
    trainable_rows: int
    labelled_primary: int
    labelled_secondary: int
    first_obs_time: str | None
    last_obs_time: str | None
    first_fetched_at: str | None
    last_fetched_at: str | None
    with_coords: int
    without_coords: int
    invalid_coords: int
    duplicate_hashes: int

@dataclass(frozen=True)
class TrainingRun:
    key: str                    # stable synthetic id, e.g. "registry:1"
    model_id: int | None
    model_version: str
    model_kind_stored: str | None
    model_kind_manifest: str | None
    feature_version: str | None
    registered_at: str | None
    artifact_path: str | None
    artifact_exists: bool
    artifact_files: tuple[FileInfo, ...]
    lineage: dict | None
    metrics: dict | None
    split: dict | None
    source_path: str            # "db-orchestrator" | "jsonl-trainer" | "artifact-only" | "unknown"
    warnings: tuple[str, ...]   # e.g. "kind mismatch", "metrics duplicated", "no split"

@dataclass(frozen=True)
class MapPoint:
    hash: str
    obs_time: str | None
    lat: float
    lon: float
    altitude: float | None
    aircraft: str | None
    report_type: str | None
    label_primary: str | None
    label_secondary: str | None
    label_combined: str | None
    raw_text_excerpt: str
    suspicious: bool
```

All timestamps stay as ISO strings from the source; formatting happens in templates. This avoids timezone reinterpretation and keeps provenance exact.

### 5.6 Caching

- Per-request memoisation only by default (a dict on the adapter instance created per request).
- Optional short-TTL cache (10 s) for `reports.summary()`, `labels.distribution()`, `system.snapshot()` to keep navigation snappy; keyed by source mtimes.
- No persistent cache, no writes.
- A "Refresh" button bypasses the cache via `?refresh=1`.

### 5.7 Error model

| State | Meaning | UI |
|---|---|---|
| `ok` | Source read successfully, has data | normal |
| `empty` | Read successfully, zero rows | empty-state card with next-step hint |
| `missing` | File/dir does not exist | "Not found" panel with configured path and env var |
| `schema_mismatch` | Present but expected columns/views absent | warning panel listing missing items + ISS links |
| `not_configured` | Optional source not set | neutral "not configured" note |
| `error` | Read/parse failed | error panel with safe message + `docs/ISSUES.md` link; rest of page still renders |

No view raises on a source failure. A page-level `try/except` in a small middleware catches unexpected adapter bugs and renders `500.html` with a support block, but tests assert that missing/empty/malformed sources never reach it.

## 6. Pipeline stage inventory

### 6.1 End-to-end map

```
AWC CSV
  -> [1] collect            -> data/raw/pireps.db (reports/rejected/runs)
  -> [2] migrate legacy     -> target DB (not yet run; ISS-002/011)
  -> [3] parse + label      -> in-memory PirepFields/FeatureRow (no store)
  -> [4] build features     -> data/features/*.jsonl (no CLI; empty today)
  -> [5] train              -> models/registry/<kind>-<version>/ + runs/split-*.json + registry row
  -> [6] evaluate           -> metrics.json/report.json/report.md (inside artifact)
  -> [7] register/promote   -> registry.db (models/promotions)
  -> [8] generate map       -> standalone folium HTML in CWD (no configured location)
  -> [9] log/observe        -> stdout / logs/*.log / legacy collector.log
  -> [10] configure/paths   -> in-memory Settings/Paths (no artifact)
```

The dashboard reports stages 1–10. It can only **read**; it never triggers a stage.

### 6.2 Inventory table

| # | Stage | Entry point(s) | Inputs | Outputs | Storage | Status / run info | Counts | Timestamps | Errors / logs |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Config & paths | `chopcast config show|validate`, `chopcast paths`; `Settings.load()` | `configs/default.yaml`, profile YAML, `CHOPCAST_*` env (not `.env`) | In-memory `Settings`, `Paths` | none | none | none | none | `ConfigError`; no log |
| 1 | Collection | `chopcast-collector once|run|status|rejected` | AWC `aircraftreports.cache.csv.gz` | `reports` rows, `rejected` rows, `runs` rows | `data/raw/pireps.db` | `runs` table (legacy shape live); CLI output; root `collector.log` | 3,525 reports; 2,928 AIREP / 591 PIREP / 6 Urgent; 2 runs | `fetched_at`, `obs_time`, legacy `ran_at`; log lines 2026-08-30, 2026-10-03 | `runs.status/error` (target only), `rejected.reason/detail`, stderr |
| 2 | Legacy migration | `scripts/migrate_legacy_db.py`, `chopcast-collector migrate-legacy` | Legacy DB | Target DB + `schema_migrations` | destination DB (defaults to source — ISS-002) | none (stdout only) | source/target row counts (script output) | file mtime | traceback; known `duplicate column name: turbulence_2` (ISS-011) |
| 3 | Parse + label | `parse_pirep`, `clean_text`, `label_severity`, `process` | `raw_text`, `report_type`, `obs_time`, `lat/lon/alt`, label columns | `PirepFields`, `FeatureRow` | none (in-memory) | only `training.processed_count` log | 285/290 parse to `turbulence=None`; labels 288 None / 1 Light / 1 Moderate | none | `ValueError` (ISS-031); no parser audit log |
| 4 | Feature build | `data/feature_store.py::build_dataset` (no CLI) | `reports` rows | JSONL `features_<version>.jsonl` (docstring says Parquet — ISS-061) | `data/features/`, `data/processed/` (empty) | stdout/log only | written/rejected in log | file mtime; version string | exception; no run record |
| 5 | Training (A) | `chopcast train run --version` → `run_training` | `trainable` (filters `report_type`) | artifact dir, split manifest, registry row | `models/registry/<kind>-<version>/`, `runs/` | registry row + files; no run table | 290 raw / 290 usable / 232 train / 58 test | lineage `created_at`, `registered_at`, file mtimes | CLI stderr; partial artifact possible |
| 5 | Training (B) | `chopcast-train run --features` | JSONL feature file | artifact dir with `report.md/json`, `split.json`, registry row | `models/registry/<version>_<feature_version>/` | registry row + files | from feature file | file mtimes | fails at `cfg.split` (ISS-015); transformer path broken (ISS-014) |
| 5 | Training (C) | untracked root scripts | mixed | mixed | repo root | none | unknown | unknown | not collected by pytest (ISS-051) |
| 6 | Evaluation | `evaluate`, `chopcast eval compare`, `chopcast-train compare` | test split + model artifact | `metrics.json`, `report.json`, `report.md`, stdout diff | inside artifact dirs | inferred from files/registry | 58 samples; per-class support; confusion matrix | file mtime / `registered_at` | compare bugs (ISS-019/020); no eval run table |
| 7 | Registry | `SqliteModelRegistry` | registration call | `models`, `promotions` (+ stray raw schema) | `models/registry/registry.db` | rows; `current(tag)` | 2 models, 0 promotions | `registered_at`, `promoted_at` | duplicate `IntegrityError` (ISS-029) |
| 8 | Map | `chopcast map`, `generate_map`, declared `chopcast-map` (missing) | `trainable`; optional model id | standalone HTML (folium) | CWD default `turbulence_map.html`; no configured dir | none | markers/heat points (not recorded) | file mtime | `NameError: Path` (ISS-016), `KeyError severity_label` (ISS-017), centroid/NULL bugs (ISS-018) |
| 9 | Logs / jobs | `chopcast.logging.configure` | event records | stdout / rotating file | `logs/` (empty), root `collector.log` | no job table; run IDs not guaranteed | lines/levels/errors | log timestamps | parse failures, rotation |
| 10 | System | `chopcast config`, `chopcast paths` | YAML + env + installed packages | stdout | none | none | versions, file sizes | file mtimes | `ConfigError` |

### 6.3 Per-stage notes the UI must express

**0 — Config.** The dashboard reads YAML itself and recomputes `${paths.root}` interpolation. It shows raw values and resolved values side by side, and labels them "resolved by dashboard, not by `Settings.load()`". It redacts anything matching `token|secret|password|key|user_agent` (the User-Agent is not secret but is shown in full only on request). It does not import `chopcast.config` (CWD coupling, ISS-037).

**1 — Collection.** The live `runs` table is the legacy shape. The dashboard shows a **legacy runs** badge and maps columns: `ran_at → started_at`, `inserted → rows_inserted`, `skipped → rows_skipped`, `rejected → n/a (no column)`. It shows two run rows and the two `collector.log` totals, clearly labelled "legacy log, no run id". A target-schema DB would show the full shape automatically.

**2 — Migration.** There is no migration run record. The page infers state from: presence of `schema_migrations`, its versions, the `reports` column set, the `runs` shape, and the `trainable` SQL. It shows three badges: `legacy`, `target`, `mixed/unknown`, plus a checklist of the exact gaps (ISS-013). It must not claim a migration succeeded or failed; it says "no run record; inferred from schema".

**3 — Parse + label.** No parser audit exists. The Labels page therefore shows:
- authoritative **column** value counts for `turbulence`, `turbulence_2`, `turbulence_type`, `turbulence_freq`;
- a **rule preview**: apply `configs/labeling.yaml` v1 in the adapter (same case-insensitive, longest-match, `max` strategy) to the column values, clearly labelled "dashboard preview of labeling.yaml; not the pipeline's persisted output";
- the `trainable` count under **both** known view predicates, labelled `legacy predicate` and `migration-3 predicate`;
- a prominent warning that 285/290 parsed labels are `None` (ISS-008) and that persisted parse audit data is unavailable.

**4 — Feature build.** Directories exist but are empty. The page lists any `*.jsonl` / `*.parquet` files with size, mtime, line count (streamed, capped), and a schema preview from the first record. If empty: "No feature datasets found. `build_dataset()` has no CLI entry point (ISS-058) and the directories are empty."

**5 — Training.** There is no training-run table. The adapter joins three evidence sources:
1. registry `models` rows (authoritative for registered models);
2. artifact directories under configured roots (files, manifest, lineage, metrics, split);
3. `runs/split-*.json` manifests (hashes, seed, mode, version).

Each `TrainingRun` gets a `source_path` label:
- `db-orchestrator` if the artifact has `lineage.json` + `metrics.json` and a split in `runs/`;
- `jsonl-trainer` if the artifact has `report.md`/`report.json` + `split.json` and no lineage;
- `artifact-only` if files exist without a registry row;
- `unknown` otherwise.

Warnings shown per run: stored kind vs manifest kind mismatch (ISS-047), relative artifact path (ISS-007), missing split, metrics duplicated in registry and file, `code_commit=unknown` (ISS-045), missing artifact files. The page must say **"history inferred from files; failures are not recorded"**.

**6 — Evaluation.** The dashboard only displays persisted metrics; it does not recompute predictions (that would require loading joblib and running the pipeline, violating the no-execution rule). It renders:
- metric cards (`accuracy`, `macro_f1`, `weighted_f1`, `n_samples`);
- per-class precision/recall/F1/support table with a warning when support is 0 (ISS-043);
- confusion matrix as an accessible HTML table with a colour scale;
- a compare view for any two models, diffing stored metrics field by field and flagging incomparable metrics (different feature/label versions).

**7 — Registry.** Shows all models, stored kind, manifest kind, feature version, registration time, promotion tags, artifact path, and per-file existence. A model with a missing artifact is still listed, with a red `artifact missing` badge. `current("production") == None` gets a dedicated "no production model" banner, not an error.

**8 — Map.** No generated map HTML exists. The Maps page renders its own Leaflet view from `trainable` (see §9). The "Generated files" tab indexes configured map roots and shows an empty state explaining that `chopcast map` is currently broken (ISS-016/017) and that no output directory is configured (ISS-083). It never invokes `generate_map()`.

**9 — Logs/Jobs.** There is no jobs table. The page shows:
- collector runs from `runs` (legacy mapping) as the only real job history;
- training/evaluation "runs" inferred from registry + artifacts, marked inferred;
- log tail from `logs/**/*.log` and root `collector.log`, streamed from the end (max `LOG_TAIL_BYTES`), parsed as JSON lines when possible, otherwise as plain text;
- level filters, text search, and a per-file "download" link (read-only).

**10 — System.** Shows resolved adapter settings, raw config files, path existence/size/mtime, Python/Django/package versions, and a sanity checklist with severity and ISS links (missing DB, empty features, legacy schema, no promotions, relative artifact paths, `.env` not read, OneDrive root, Python 3.14 vs Django 5.2). It is the page that explains *why* other pages look the way they do.

## 7. Data source catalogue

| Source | Read method | Freshness | Provenance label | Empty behaviour |
|---|---|---|---|---|
| `data/raw/pireps.db` → `reports` | `mode=ro`, `PRAGMA query_only` | `MAX(fetched_at)`, `MAX(obs_time)` | `legacy` / `target` from probe | "No raw reports" + collector hint |
| `reports` columns `turbulence`, `turbulence_2` | same | row counts | `DB column` | zero counts shown as 0, not blank |
| `trainable` view | `sqlite_master.sql` + `SELECT COUNT(*)` | view SQL hash | `legacy predicate` / `migration-3 predicate` | explain predicate mismatch |
| `runs` table | same, shape-aware | last `ran_at` / `started_at` | `legacy runs` / `target runs` | "No collection runs recorded" |
| `rejected` table | same (if present) | last `fetched_at` | target only | "No rejected rows (table absent in legacy DB)" |
| `models/registry/registry.db` → `models` | `mode=ro` | `MAX(registered_at)` | `registry` | "No models registered" |
| `promotions` | same | `MAX(promoted_at)` | `registry` | "No promotions; no production model" |
| Artifact dirs | filesystem, read-only | `mtime` | `artifact` | per-model "artifact missing" |
| `manifest.txt` | line parser `k=v` | mtime | `artifact manifest` | warning "manifest missing" |
| `metrics.json` / `report.json` | JSON parse, size cap | mtime | `persisted metrics` | "No metrics file" |
| `lineage.json` | JSON parse | mtime | `lineage` | "No lineage file" |
| `split-*.json` / `split.json` | JSON parse, hash lists counted only | mtime | `split manifest` | "No split manifest" |
| `data/features/*.jsonl` | streamed line count, first-line schema | mtime | `feature dataset` | "No feature datasets" |
| `logs/**/*.log`, `collector.log` | tail from end, max bytes | mtime | `log` | "No logs found" |
| `configs/*.yaml` | PyYAML safe_load | mtime | `config` | "Config missing" |
| `docs/ISSUES.md` | text read + safe renderer | mtime | `docs` | "Issue register not found" |
| `pyproject.toml` | `tomllib` | mtime | `packaging` | "No pyproject found" |
| Installed packages | `importlib.metadata` | process start | `environment` | always available |

**Never read:** `.env`, `pipeline.joblib` contents (existence and size only), `raw_json` in bulk (only for a single report detail, with a size cap), or any file outside configured roots.

### 7.1 Database query policy

- Aggregates use single queries with `COUNT`, `MIN`, `MAX`, `GROUP BY`.
- Table views use `SELECT` with explicit columns, `ORDER BY` whitelist, `LIMIT/OFFSET`.
- Text search uses `LIKE` on `raw_text`/`hash` with escaped `%`/`_`; no FTS assumption.
- The report detail page fetches one row by `hash` (parameterised) and pretty-prints `raw_json` with a 20 KB cap.
- Invalid coordinates are counted with `lat IS NULL OR lon IS NULL OR lat NOT BETWEEN -90 AND 90 OR lon NOT BETWEEN -180 AND 180` (NULL-safe).
- No `SELECT *` on wide tables in list views; only the detail query may use it.

### 7.2 File safety

- All file paths are resolved with `Path.resolve()` and must be `is_relative_to()` one of the configured roots; otherwise 404.
- Symlinks are resolved before the check.
- Only allowlisted extensions are served (`.html` for generated maps; `.log`, `.json`, `.jsonl`, `.yaml`, `.md`, `.toml` for downloads).
- Downloads use `Content-Disposition: attachment`; inline map view uses a strict CSP (`sandbox allow-scripts`) in a separate endpoint.
- File contents are never executed or templated.

---

## 8. Pages, apps, and URLs

### 8.1 Django apps

| App | Responsibility | Templates |
|---|---|---|
| `apps.core` | base layout, navigation, overview, system, issues, health, error pages | `core/` |
| `apps.pipeline` | data, labels, training, evaluation, registry, logs/jobs | `pipeline/` |
| `apps.geo` | maps page, map data JSON, generated map file index/view/download | `geo/` |

`config/urls.py` includes each app under a namespace. No API framework, no DRF.

### 8.2 URL map

| URL name | Path | View | Purpose |
|---|---|---|---|
| `core:overview` | `/` | OverviewView | Pipeline health, stage cards, key counts, recent errors |
| `core:health` | `/healthz/` | health | JSON source statuses (for humans and smoke tests) |
| `core:system` | `/system/` | SystemView | Config, paths, versions, sanity checks |
| `core:issues` | `/issues/` | IssuesView | Rendered `docs/ISSUES.md` |
| `core:issues_raw` | `/issues/raw/` | raw text download | Source of truth, read-only |
| `pipeline:data` | `/data/` | DataView | Raw counts, time range, sources, quality |
| `pipeline:reports` | `/data/reports/` | ReportListView | Paginated, filterable report table |
| `pipeline:report_detail` | `/data/reports/<hash>/` | ReportDetailView | One report, raw JSON, parse hints |
| `pipeline:labels` | `/labels/` | LabelsView | `turbulence`/`turbulence_2` distributions, trainable variants |
| `pipeline:training` | `/training/` | TrainingListView | All inferred training runs |
| `pipeline:training_detail` | `/training/<key>/` | TrainingDetailView | Lineage, split, metrics, artifact files |
| `pipeline:evaluation` | `/evaluation/` | EvaluationView | Persisted metrics for all models |
| `pipeline:evaluation_detail` | `/evaluation/<int:model_id>/` | EvaluationDetailView | Per-class table, confusion matrix |
| `pipeline:evaluation_compare` | `/evaluation/compare/` | EvaluationCompareView | Two-model diff (`?a=&b=`) |
| `pipeline:registry` | `/registry/` | RegistryView | Models, versions, promotions, artifact existence |
| `pipeline:registry_detail` | `/registry/<int:model_id>/` | RegistryDetailView | One model record + files |
| `pipeline:logs` | `/logs/` | LogsView | Job/run history + log tail |
| `geo:maps` | `/maps/` | MapsView | Interactive map + filters + generated files tab |
| `geo:map_data` | `/maps/data/` | map_data | JSON FeatureCollection for the current filters |
| `geo:map_files` | `/maps/files/` | MapFilesView | Index of generated map HTML |
| `geo:map_file` | `/maps/files/<path:relpath>` | map_file | Inline view (`?download=1` for attachment) |

Query parameters are shared across list pages: `page`, `page_size`, `sort`, `dir`, `q`, plus page-specific filters. Invalid values fall back to defaults, never 400.

### 8.3 Page-by-page specification

#### Overview — `/`

**Purpose:** one screen that answers "is the pipeline healthy, and what is broken?"

**Sections:**
1. **Global status strip** — raw DB, registry DB, artifacts, features, logs, maps: six chips with `ok/empty/missing/error` and last-modified time.
2. **Stage timeline** — ten stage cards (Collect → Migrate → Parse/Label → Features → Train → Evaluate → Register → Map → Logs → Config). Each card: stage name, last evidence timestamp, counts, status, one-line finding, link to detail. Stages with no run record say "no run record".
3. **Key counts** — reports 3,525; trainable 290; labelled 290 primary / 14 secondary; models 2; production model none; feature files 0; map files 0; log files 1.
4. **Data-quality banner** — 285/290 parse to `None`; models degenerate (`macro_f1 0.333`); no promotions; legacy schema. Each links to the relevant page and ISS.
5. **Recent errors** — last N error-level log lines and `runs.status != ok`; empty state "no errors recorded (no error log exists)".
6. **Quick links** — Data, Labels, Training, Maps, Issues.

**Empty state:** if the raw DB is missing, the page still renders the frame, shows a setup checklist (env vars), and every card shows `missing` rather than zero.

#### Data — `/data/`

**Sections:**
- Summary cards: total reports, by type (AIREP/PIREP/Urgent/other), trainable rows under both predicates, reports with coordinates, invalid coordinates, duplicate hashes (if detectable), distinct `fetched_at` days.
- Time range: first/last `obs_time`, first/last `fetched_at`, collection cadence (runs per day) if runs exist.
- Source table: configured raw DB path, size, mtime, schema profile, `schema_migrations` versions, view definitions (collapsible SQL).
- Quality table: null counts per column, empty `raw_text`, out-of-range lat/lon, missing `obs_time`, label coverage.
- Recent reports preview (10 rows) + link to the full table.
- Legacy vs target panel: exact column diff, missing tables, ISS links.

**Filters (report table):** report type, label (primary/secondary/combined), date range, altitude range, has coordinates, text search, hash prefix. **Sort:** obs_time, fetched_at, report_type, turbulence, altitude, aircraft. **Pagination:** 25/50/100, capped at 200.

**Empty state:** "The raw database is empty or missing. Run `chopcast-collector once` after resolving ISS-011." If the DB exists but `reports` is empty, show the schema and zero counts.

#### Report detail — `/data/reports/<hash>/`

Fields: hash, fetched_at, obs_time, report_type, raw_text (wrapped, copy button), turbulence, turbulence_2, type, freq, aircraft, lat/lon/altitude with map link, raw_json pretty-printed. A "parse preview" shows what the documentation says the parser would extract, but labels it **"not executed; parser is not imported"** — actually, do not show a fake parse. Instead show the known parser limitation (ISS-008) and link to the parser source. If `raw_json` is malformed, show the error and the raw text.

#### Labels — `/labels/`

**Sections:**
- Distribution cards for `turbulence` (primary) and `turbulence_2` (secondary): counts + bar charts.
- Combined preview: primary else secondary, with a `label_source` breakdown.
- Rule preview: apply `configs/labeling.yaml` to the raw values; show mapping version/strategy and the exact rule that matched (expandable).
- Trainable counts under both predicates, side by side, with the predicate SQL shown.
- Data-quality warning: parse failure rate (from training lineage if present; otherwise "no persisted parse audit"), zero-support classes, and the degenerate-model warning.
- Table of distinct raw values with counts and mapped labels; sortable, paginated.

**Empty state:** "No label columns found in this database." If columns exist but are all NULL: explain that `trainable` will be empty.

#### Training — `/training/` and `/training/<key>/`

**List columns:** model version, stored kind, manifest kind, feature version, registered at, source path, artifact exists, metrics (accuracy/macro/weighted/F1), warnings, links.

**Detail:**
- Identity: registry id, version, kinds, feature version, source path, registered at.
- Lineage: full JSON tree (collapsible), with missing fields highlighted (`code_commit=unknown`, no hashes).
- Split: manifest counts (train/test), seed, mode, version, hash list length only; a warning if no manifest.
- Metrics: cards + per-class table + confusion matrix.
- Artifacts: file table (name, size, mtime, exists), `manifest.txt` parsed, `pipeline.joblib` shown as "not loaded (ISS-078)".
- Warnings: kind mismatch, relative path, duplicate metrics, no lineage, no split, artifact missing.
- Cross-links: registry detail, evaluation detail, split file.

**Empty state:** "No training runs found. No registry rows and no artifact directories." If registry rows exist but artifacts are missing, list the rows with red badges.

#### Evaluation — `/evaluation/`, `/evaluation/<id>/`, `/evaluation/compare/`

- Index: one row per model with accuracy, macro/weighted F1, samples, support warning, link.
- Detail: metric cards, per-class table (support 0 highlighted), confusion matrix, metric provenance (`metrics.json` vs `report.json` vs registry `metrics_json`), and a diff against the previous model.
- Compare: select two models; show side-by-side values, deltas, and a compatibility banner if feature versions differ. Do not claim statistical significance.
- If no metrics: "No persisted evaluation found. Evaluation is not run by the dashboard."

#### Registry — `/registry/` and `/registry/<id>/`

- Table: id, version, stored kind, feature version, registered at, promotion tag, artifact path (relative badge), artifact exists, file count, metric summary.
- Detail: record fields, metrics JSON (collapsible), promotions history, artifact file list with existence, manifest parsed, warnings.
- Banner: "No production model" when `current('production')` is empty; "Registry contains raw-data tables (ISS-005)".
- Empty state: "No registry database found" with the configured path.

#### Logs/Jobs — `/logs/`

- Job history: collector `runs` (legacy/target mapped), inferred training/evaluation runs, with status, started, duration (if both timestamps), counts, error excerpt.
- Log files: list with path, size, mtime; selected file tail (last `LOG_TAIL_BYTES`), level filter, search, line numbers; JSON lines rendered as a compact table (timestamp, level, event, key fields), plain lines as monospace.
- Empty state: "No logs found. `logs/` is empty and the only log is the legacy root `collector.log` (2 lines)."

#### System — `/system/`

- Environment: Python version/executable, Django version, OS, cwd, timezone.
- Adapter settings: every variable with value, source (`env`/`default`), resolved path; secret-like values redacted.
- Paths: existence, type, size, mtime, permissions (readable/writable, but dashboard only reads).
- Config: each YAML file, resolved values, profile overlay applied, raw vs resolved toggle.
- Packages: `chopcast` (if installed/importable — do not import it; use `importlib.metadata.version`), Django, pandas, pydantic, folium, scikit-learn, etc.; "not installed" is fine.
- Sanity checklist with severity and ISS links: DB state, schema profile, artifact paths, production model, feature/log/map dirs, `.env` ignored, CWD-dependent config, OneDrive root, Python/Django support, registry pollution.
- "Copy diagnostics" button (client-side) producing a text block safe to paste into an issue.

#### Known Issues — `/issues/`

- Renders `docs/ISSUES.md` with a safe, dependency-free Markdown subset: headings, tables, lists, bold/italic, inline code, fenced code, links, blockquotes, horizontal rules.
- Table of contents generated from `##`/`###` headings; anchors stable.
- Summary counts at top (parsed from the `**Counts:**` line if present).
- Filters: severity, category, status, text search (client-side, no server round trip).
- Every issue gets an anchor `#iss-001`; deep links from other pages use it.
- Raw HTML in the Markdown is escaped, not rendered. Links are restricted to `http(s)`, `mailto`, and relative paths; `javascript:` is rejected.
- Empty/missing file: "Issue register not found at `<path>`" with the configured docs dir.

## 9. Maps: the centrepiece

### 9.1 What the existing map module does

`chopcast/map/folium_app.py::generate_map`:

- opens `data/raw/pireps.db` (read-write, not read-only);
- selects every row from `trainable` (290 today);
- with no `model_id`, reads `row["severity_label"]` — a column that does not exist → `KeyError` on every call (ISS-017);
- with a `model_id`, loads a joblib artifact, runs `process()` per row, predicts labels;
- computes a centroid with a bug (missing coordinates counted in the denominator; `0.0` treated as missing — ISS-018);
- builds a folium map with per-report `CircleMarker`s + a `HeatMap` layer + `LayerControl`;
- uses severity colours `None=blue, Light=green, Moderate=orange, Severe=red`;
- writes a standalone HTML file, default `turbulence_map.html` in the CWD;
- returns the path. There is no run record, no filter support, no output directory, and no offline asset story (folium's default template loads Leaflet JS/CSS from a CDN and tiles from OpenStreetMap).

`chopcast map` calls it but fails before that at `Path(output)` (`NameError`, ISS-016). The declared `chopcast-map` CLI does not exist (ISS-058).

### 9.2 Decision: re-render, do not invoke

The dashboard will **not** call `generate_map()` or import `chopcast.map`:

1. It writes a file, violating read-only.
2. Its default path crashes, and its prediction path executes a joblib artifact (ISS-078).
3. Its output is a standalone document, not embeddable data.
4. It has no filters.

Instead, `apps.geo` reads the same `trainable` rows through the adapter and renders a Leaflet map directly. The visual contract is preserved: same severity colours, circle markers, heat layer, layer control, popups with time/altitude/aircraft/text.

**This means no change to `chopcast/map/` is required for the dashboard.** Optional improvements are listed in §14 and require separate approval.

### 9.3 Map page layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ Maps                                                        [Refresh]│
│ Data: legacy trainable · 290 rows · 290 with coordinates             │
├──────────────────────────────────────────────────────────────────────┤
│ [Filters: date range | altitude | label layer | report type | text ] │
│ [ Apply ] [ Reset ]                         Showing 290 / 290 points │
├──────────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────┐  ┌────────────────┐  │
│  │                                            │  │ Legend         │  │
│  │              Leaflet map                   │  │ ● None   (288) │  │
│  │   markers + optional heat layer            │  │ ● Light    (1) │  │
│  │                                            │  │ ● Moderate (1) │  │
│  │                                            │  │ ● Severe   (0) │  │
│  └────────────────────────────────────────────┘  │ Layers         │  │
│                                                  │ [x] Markers    │  │
│                                                  │ [ ] Heatmap    │  │
│                                                  │ [ ] Clusters   │  │
│                                                  └────────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│ Points table (paginated)                    [Download filtered CSV]  │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.4 Label layers

The layer selector is explicit about provenance:

| Layer | Source | Meaning |
|---|---|---|
| `Primary (turbulence)` | DB column | The legacy `trainable` predicate |
| `Secondary (turbulence_2)` | DB column | The second observation layer; 14 rows |
| `Combined (primary else secondary)` | derived | The migration-3 predicate's semantics |
| `Unlabelled` | derived | Rows with neither column set (only if the query includes them) |

The default is `Combined`, because it matches the target view's intent, but the page shows a badge `derived` and a note: "The pipeline's canonical label layer is an open decision (ISS-003). This view does not choose one; it shows each layer." Colours come from the same mapping as `folium_app.py`; unknown labels are grey.

### 9.5 Filters

- **Time:** `obs_time` from/to (date inputs, inclusive); presets 24h / 7d / 30d / all.
- **Altitude:** min/max feet; presets surface–10k, 10k–20k, 20k–30k, 30k–40k, 40k+.
- **Label layer:** as above; optional specific class filter (None/Light/Moderate/Severe).
- **Report type:** PIREP / Urgent PIREP (the live `trainable` is already restricted; show the filter anyway). If the active view has no `report_type` column (migration-3 shape, ISS-010), disable the control with an inline note instead of failing the query.
- **Coordinates:** include/exclude invalid; only valid points are plotted, invalid count shown.
- **Text:** substring search on `raw_text` (escaped LIKE).
- **Map viewport:** optional "filter to current view" using Leaflet bounds (client sends bbox; server validates and applies).

All filters are server-side query parameters, so the URL is shareable and the page works without JS. The map's JS fetches `/maps/data/` with the same parameters.

### 9.6 Data endpoint — `/maps/data/`

Response (JSON, no HTML):

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [lon, lat]},
      "properties": {
        "hash": "…",
        "obs_time": "2026-08-30T16:30:00.000Z",
        "altitude": 17000,
        "aircraft": "CRJ2",
        "report_type": "PIREP",
        "label_primary": null,
        "label_secondary": null,
        "label_combined": "None",
        "label_layer": "combined",
        "suspicious": false,
        "raw_text": "…"
      }
    }
  ],
  "meta": {
    "total_matching": 290,
    "returned": 290,
    "truncated": false,
    "max_points": 2000,
    "filters": {"..." : "..."},
    "provenance": "legacy trainable view",
    "generated_at": "2026-11-14T…Z"
  }
}
```

- Only valid coordinates are returned; invalid rows are counted in `meta`.
- `raw_text` is truncated to 300 chars server-side (no full text in the map payload).
- `truncated` is true when `total_matching > max_points`; the page shows a warning and a link to the filtered table.
- `Cache-Control: no-store`.

### 9.7 Generated map files tab

Because `generate_map()` writes standalone HTML and no directory is configured, the tab is a **file index**, not a generator:

- Search roots from `CHOPCAST_DASHBOARD_MAP_DIRS` (default: `runs/maps`, `data/maps`, `maps`, repo root), non-recursive at the root to avoid scanning the whole repo; recursive under the first three.
- List `*.html` with relative path, size, mtime; empty state explains ISS-016/017/083.
- **View:** `/maps/files/<relpath>` streams the file with `Content-Type: text/html; charset=utf-8`, `Content-Security-Policy: sandbox allow-scripts`, `X-Content-Type-Options: nosniff`, and no caching. It is a static artifact; the dashboard does not modify it.
- **Download:** same URL with `?download=1`, `Content-Disposition: attachment`.
- Path traversal, absolute paths, `..`, symlinks outside roots, and non-`.html` files → 404.
- A note on the page: generated folium maps may require internet for their JS/tiles (ISS-084); the live map above does not.

### 9.8 Why the live map works offline

Leaflet, MarkerCluster, and Leaflet.heat are vendored. The base layer defaults to a **vendored Natural Earth 110m world outline** rendered as a GeoJSON layer, so no tile server is contacted. If `CHOPCAST_DASHBOARD_TILE_URL` is set, a tile layer is added (with attribution) and the page shows an "online tiles" badge. This keeps the app fully offline by default while allowing a nicer basemap later.

### 9.9 Performance

- Server-side `LIMIT` (default 2,000; configurable) and a `truncated` flag.
- Marker clustering enabled when > 500 points.
- Heatmap uses only valid coordinates and a capped sample (e.g., 5,000) if the dataset grows.
- The point table is paginated independently; it does not re-render all rows in the browser.
- No per-row `pandas.Series` construction (unlike ISS-082).

---

## 10. UI/UX specification

### 10.1 Layout

- **Desktop:** fixed left sidebar (240 px) with product name, environment/profile badge, nav groups (`Overview`, `Data`, `Labels`, `Training`, `Evaluation`, `Registry`, `Maps`, `Logs`, `System`, `Issues`), and a footer with data-freshness time. Main content max-width 1,440 px, 24 px gutters.
- **Tablet:** collapsible sidebar (hamburger), same content.
- **Mobile:** top bar + slide-over nav; cards stack; tables become horizontally scrollable with sticky first column; map height 60vh.
- **Header:** page title, breadcrumb, global status chips (raw/registry/artifacts), "Refresh" button, keyboard shortcut hint (`/` focuses search).
- **Footer:** "Read-only · data as of HH:MM:SS UTC · ChopCast <version>" and a link to `/issues/`.

### 10.2 Visual system

- CSS custom properties: `--bg`, `--surface`, `--text`, `--muted`, `--border`, `--accent`, `--ok`, `--warn`, `--error`, `--info`.
- Light theme by default; `prefers-color-scheme: dark` support via the same variables. No theme switcher in v1.
- Type: system UI stack (`-apple-system, Segoe UI, Roboto, ...`), 14 px base, 1.5 line-height; monospace for hashes/SQL/JSON.
- Spacing scale 4/8/12/16/24/32; 8 px radius; subtle borders, no heavy shadows.
- Severity colours match `SEVERITY_COLORS`: None `#2f6fed` (blue), Light `#1f9d55` (green), Moderate `#d97706` (orange), Severe `#dc2626` (red). Always paired with a text label, never colour alone.
- Status badges: `ok`, `empty`, `missing`, `warning`, `error`, `inferred`, `legacy`, `target`, `derived`.

### 10.3 Components

- `partials/status_badge.html`
- `partials/metric_card.html` (label, value, sublabel, trend/quality flag)
- `partials/data_table.html` (columns, rows, sort links, empty slot)
- `partials/pagination.html` (page numbers, prev/next, page-size select; preserves query string)
- `partials/empty_state.html` (icon, title, explanation, action/link)
- `partials/error_state.html` (source, safe message, "what to check", ISS link)
- `partials/filter_bar.html` (GET form, reset link)
- `partials/json_viewer.html` (collapsible `<details>`, escaped)
- `partials/sql_block.html` (monospace, copy)
- `partials/tabs.html` (server-rendered links, active state)
- `partials/breadcrumbs.html`

### 10.4 Tables

- Server-side sorting via `?sort=field&dir=asc|desc`; clicking a header toggles; arrow indicator; whitelist only.
- Pagination via `?page=N&page_size=M`; page size 25/50/100; hard cap 200.
- Sticky header on scroll; zebra rows optional; numeric columns right-aligned; hashes monospace with copy button; long text truncated with a title tooltip and a detail link.
- Empty table renders `empty_state` inside the table body, not a blank grid.
- "Showing X–Y of Z" above the table; filter chips below the header with individual remove links.

### 10.5 Charts

- Chart.js only where it adds value: label distribution bars, collection runs per day, metric comparison bars.
- Charts are rendered from server-provided JSON in a `<script type="application/json">` block; data is escaped.
- If Chart.js fails to load (should not happen offline), a `<noscript>`/fallback table remains.
- Confusion matrix is an HTML table, not a canvas, for accessibility.

### 10.6 HTMX usage

- Optional: filter form submits via `hx-get` and swaps the results partial; pagination links use `hx-get` with `hx-push-url`.
- Without JS, the same URLs return full pages.
- No HTMX for the map (Leaflet owns its DOM).
- All endpoints degrade to normal HTML.

### 10.7 Accessibility

- Landmarks (`header`, `nav`, `main`, `footer`), skip link, visible focus rings.
- Form labels and `aria-describedby` for hints/errors.
- Tables have `<caption>` and `scope="col"`.
- Status is text + colour; charts have data tables.
- Map has a text alternative: the points table below it and an `aria-label` on the container.
- Keyboard: `/` focuses search, `Esc` clears, map controls are Leaflet defaults.

## 11. Security and read-only guarantees

### 11.1 Read-only enforcement (defence in depth)

1. **Construction:** only `mode=ro` connections exist in `adapters/sqlite_ro.py`; a grep test asserts no other module calls `sqlite3.connect`.
2. **Session:** `PRAGMA query_only=ON` on every connection.
3. **No DDL/DML:** no `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`, `ALTER`, `VACUUM`, `ATTACH`, `PRAGMA journal_mode` anywhere in `dashboard/`.
4. **No migrations:** `manage.py migrate` is never required for the default install; the optional admin DB is a different file and a different app.
5. **No artifact writes:** the dashboard never writes under `data/`, `models/`, `runs/`, `logs/`, or `configs/`. `demo_data` writes only under `dashboard/var/demo/`.
6. **Verification test:** compute SHA-256 + size + mtime of `pireps.db`, `registry.db`, and every artifact file before/after crawling all pages; assert unchanged. Also assert no `-wal`/`-shm` files were created.
7. **Filesystem:** path allowlists, `resolve()` + `is_relative_to`, no symlink escapes.
8. **Templates:** autoescape on; Markdown renderer escapes raw HTML; no `|safe` except the renderer's sanitized output.
9. **No model execution:** `pipeline.joblib` is listed by name/size only. No `joblib.load`, no `pickle`, no `subprocess` of pipeline commands.
10. **No network by default:** vendored assets; optional tile URL is the only outbound dependency and is off by default.

### 11.2 Other hardening

- `DEBUG=False` by default; `ALLOWED_HOSTS` from env (`localhost`, `127.0.0.1` by default).
- `SECRET_KEY` from env, generated ephemeral if absent (sessions are signed cookies; a restart invalidates them, acceptable).
- CSRF middleware on; no POST endpoints in v1.
- Security headers: `X-Content-Type-Options`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY` (except the map-file view, which uses CSP sandbox), `Content-Security-Policy` allowing only `'self'` + `data:` images + the optional tile host.
- No directory listing, no static file serving outside `STATIC_ROOT`, no debug tracebacks in responses.
- Logs page output is escaped; JSON log values are rendered as text.
- Downloads are attachment-only except the explicit inline map view.
- Rate limiting is out of scope for a local read-only tool; if exposed, put it behind a reverse proxy with auth (documented).

### 11.3 Privacy

- The dashboard displays PIREP free text, which may contain callsigns/aircraft IDs (ISS-079). It is a local tool; no telemetry, no external calls, no analytics.
- The "Copy diagnostics" block excludes raw report text and absolute user paths by default.
- `raw_json` is shown only on a single report detail page, with a size cap, and is never included in map payloads or list pages.

---

## 12. Testing plan

### 12.1 Test layers

| Layer | What it proves | Examples |
|---|---|---|
| Unit — adapter primitives | read-only connection, schema probe, query builders, safe paths | `mode=ro` rejects writes; legacy vs target detection; `..` rejected |
| Unit — services | counts, labels, training join, metrics parsing, log tail | 3,525/290/2 fixtures; malformed JSON → error result; tail cap |
| Unit — Markdown | safe rendering of `ISSUES.md` | tables, code, links; `<script>` escaped; `javascript:` rejected |
| View — happy path | every URL renders with a demo adapter | 200, expected headings, nav active |
| View — empty/missing | no 500s when sources are absent/empty | missing DB, empty registry, no logs, no maps |
| View — malformed | one bad artifact does not break the page | invalid `metrics.json`, NULL `raw_text`, bad `obs_time` |
| Endpoint — map JSON | filters, limits, provenance, no invalid coordinates | bbox, altitude, label layer, truncation |
| Endpoint — files | path traversal and content type | `../../etc/passwd` → 404; `.html` inline; `.json` attachment |
| Invariant — read-only | pipeline files unchanged after crawl | SHA-256 before/after; no WAL/SHM |
| Template — no CDN | offline guarantee | grep rendered HTML for `https://` outside allowlisted docs links |
| Management command | demo data is isolated | refuses to write under real pipeline roots |

### 12.2 Fixtures

Generated in `tests/fixtures/` at test time (no binary files committed):

- `legacy_pireps.db`: exact live column set, legacy `runs`, legacy `trainable` view, 20 reports with mixed labels, 2 invalid coordinates, 1 NULL `raw_text`.
- `target_pireps.db`: `SCHEMA` + migrations 1–3, `rejected`, target `runs`, `report_type` in `trainable`.
- `empty_pireps.db`: schema only.
- `registry.db`: `models` (2 rows, one kind mismatch, one missing artifact), `promotions` (1 row), stray `reports` table.
- Artifact tree: `baseline-v1/` with all files; `baseline-v2/` missing `metrics.json`; `transformer-v1/` with `report.json` layout.
- Logs: JSON lines, console lines, a rotated file, a file larger than the tail cap.

### 12.3 Commands

```
py -3.13 -m venv dashboard/.venv
dashboard/.venv/Scripts/python -m pip install -e dashboard[dev]
dashboard/.venv/Scripts/python dashboard/manage.py check
dashboard/.venv/Scripts/python -m pytest dashboard/tests -q
```

Coverage target for `dashboard/adapters` and `dashboard/apps`: **>= 85%** (separate from the core's aspirational 80% gate, ISS-076). CI wiring is out of scope here (ISS-059), but the commands are CI-ready.

### 12.4 Manual verification against real data

1. Record SHA-256 of `data/raw/pireps.db`, `models/registry/registry.db`, and all files under `models/registry/baseline-*`.
2. Crawl every page with a scripted `Client` and the real adapter.
3. Assert the hashes are unchanged and no new files appeared.
4. Record the rendered counts in the PR/notes: 3,525 / 290 / 2 / 0 / 0.
5. Run the demo command and crawl again with the demo env.

---

## 13. Demo data command

`python manage.py demo_data`

**Purpose:** give the dashboard a realistic dataset when real data is unavailable or when testing empty/error states, without touching pipeline artifacts.

**Writes only under `dashboard/var/demo/`** (override with `--output`), which is gitignored:

```
dashboard/var/demo/
├── raw/pireps.db              # target-ish schema, 60 reports
├── raw/legacy_pireps.db       # legacy schema for profile detection
├── registry/registry.db       # 2 models, 1 promotion, one kind mismatch
├── registry/baseline-demo/    # pipeline.joblib (empty placeholder), manifest, metrics, lineage
├── registry/transformer-demo/ # report.json/report.md/split.json layout
├── runs/split-demo.json
├── runs/maps/demo-map.html    # tiny static HTML for the file browser
├── features/features_v1_demo.jsonl
├── logs/collector.log         # JSON lines + a rotated file
└── demo.env                   # ready-to-source CHOPCAST_DASHBOARD_* values
```

**Safety:**

- Refuses `--output` if it resolves under `data/`, `models/`, `runs/`, `logs/`, `configs/`, or `chopcast/`.
- Refuses to overwrite a non-empty directory unless `--force`.
- Prints PowerShell and bash export lines; never edits `.env` or the real config.
- The demo DB is deliberately varied: all four labels, NULL labels, invalid coordinates, a NULL `raw_text`, legacy and target runs, a model with a missing artifact, a malformed metric row.

**Flags:** `--output`, `--force`, `--seed` (default 42), `--reports` (default 60), `--quiet`.

---

## 14. Changes to `chopcast/map/` (none now; optional later)

**Required for this dashboard: none.** The dashboard reads `trainable` directly and does not import or call the map module.

If you later want the map layer itself fixed, these are the changes I would propose as a **separate, approved task** (they map to existing issues):

| Change | Issue | Why |
|---|---|---|
| Add `chopcast/map/__init__.py` | ISS-057 | Make it an installable package |
| Import `Path` in `chopcast/cli.py` | ISS-016 | `chopcast map` currently dies before mapping |
| Replace `severity_label` read with `process()`/column label | ISS-017 | Default map always raises `KeyError` |
| Fix centroid denominator/falsy coordinates/NULL text/zip | ISS-018 | Wrong centre, crashes, silent truncation |
| Add `chopcast/map/cli.py` | ISS-058 | Declared `chopcast-map` entry point |
| Extract `build_map_payload(rows, labels, ...) -> dict` (pure, no file I/O) | new | Lets dashboard and folium share filtering/label logic; testable |
| Add `Paths.maps_dir` + `paths.maps_dir` config, default `runs/maps` | ISS-083 | Gives generated maps a discoverable home |
| Vendor Leaflet assets / `tiles=None` option | ISS-084 | Generated HTML should work offline |

Until approved, the dashboard's own map is the only map that works, and the Generated Files tab will usually be empty.

---

## 15. Build phases and acceptance criteria

### Phase 0 — Foundation (no pages yet)

- `dashboard/` scaffold, `pyproject.toml`, `config/settings.py`, URL root, base template/nav, CSS tokens, `README` skeleton.
- `AdapterSettings`, `sqlite_ro`, `types`, `schema_probe`, `get_adapter()`, `/healthz/`.
- Vendor assets downloaded and pinned; `THIRD_PARTY_LICENSES.md`.
- Test harness + first adapter tests (legacy/target/missing).
- **Accept:** `manage.py check` clean; `pytest` green; `/healthz/` reports sources; read-only invariant test passes; no CDN URLs.

### Phase 1 — Overview, System, Issues

- Overview stage cards and key counts; System page; safe Markdown renderer for `ISSUES.md`.
- **Accept:** real data shows 3,525 / 290 / 2 / 0; missing DB renders empty states; Issues page anchors and filters work; raw HTML escaped.

### Phase 2 — Data, Labels, Logs

- Data summary, report table/detail, label distributions + rule preview, log tail/job history.
- **Accept:** filters/sort/pagination work without JS; legacy/target badges correct; 285/290 warning visible; NULL/malformed rows do not crash.

### Phase 3 — Registry, Training, Evaluation

- Registry list/detail, inferred training runs, evaluation metrics/confusion, compare.
- **Accept:** 2 models shown with kind mismatch and relative-path warnings; missing artifact handled; compare works with identical metrics; no model execution.

### Phase 4 — Maps

- Live Leaflet map with filters, layer switch, clustering/heatmap, points table; generated-file index/view/download; offline world layer.
- **Accept:** 290 points; layer counts match DB; truncation flag; path traversal blocked; no external requests with default settings.

### Phase 5 — Polish and documentation

- Responsive pass, accessibility pass, empty-state copy, keyboard shortcuts, loading/disabled states.
- `dashboard/README.md`: setup, env vars, run, test, demo, read-only guarantees, troubleshooting, ISS links.
- **Accept:** all pages usable at 360 px / 768 px / 1440 px; axe-style manual check; README commands verified from a clean shell.

### Phase 6 — Verification

- Real-data crawl + hash check; demo crawl; test suite; record results in `dashboard/README.md` or a short `docs/DASHBOARD_VERIFICATION.md` (new file, optional).
- **Accept:** no pipeline file changed; no new WAL/SHM; all tests pass; counts documented.

---

## 16. Open decisions and how the dashboard stays neutral

| Decision | Dashboard behaviour | Where it would change |
|---|---|---|
| ISS-001 canonical training path | Shows both layouts, labels `db-orchestrator` vs `jsonl-trainer`; joins on version, not assumed path | `training.py` source detection |
| ISS-002 raw DB strategy | Detects legacy/target/mixed; shows exact gaps; never migrates | `schema_probe.py`, `reports.py` queries |
| ISS-003 label layer | Shows primary/secondary/combined; default combined labelled `derived`; no canonical claim | `labels.py`, map layer selector |
| ISS-004 CLI shape | Shows commands that exist and marks missing ones; does not run any | `system.py` command inventory |
| ISS-005 registry schema | Shows stray raw tables as a warning; reads only `models`/`promotions` | `registry.py` |
| ISS-006 Python floor | Displays Python/Django versions and support warning; dashboard declares `>=3.11`, runs on 3.13 | `system.py` |
| ISS-007 artifact location | Searches multiple roots; shows absolute/relative and existence; does not rewrite | `AdapterSettings.artifact_dirs` |
| ISS-008 parser bug | Prominent data-quality warning; no parse audit fabrication | `labels.py`, Overview banner |
| ISS-011/013 migration blockers | Read-only dashboard still works; collection/training pages explain why runs fail | Data/System panels |
| ISS-036 `.env` ignored | Dashboard has its own `.env.example`; System page states the core `.env` is not read | `system.py` |
| ISS-077 OneDrive | Read-only access; System page warns; WAL error guidance | `sqlite_ro.py`, `system.py` |

No decision is resolved by the dashboard. If a decision lands, the adapter and config change; templates and URLs stay.

---

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Real DB is in WAL mode and read-only open fails | Clear error state with snapshot guidance; optional snapshot command later (approval needed) |
| OneDrive locks/sync during reads | Short connections, busy timeout, read-only; no writes; System warning |
| Legacy schema changes under us | Capability probe + explicit `schema_mismatch`; no hard-coded column assumptions in templates |
| Degenerate data makes the dashboard look "broken" | The dashboard reports it honestly, with ISS links and explanations; no green-washing |
| Training history is incomplete | Inferred runs labelled; failures explicitly "not recorded" |
| Map query grows | Server limit + truncation + clustering; no full-view load |
| Markdown renderer XSS | Escape raw HTML; allowlist links; unit tests |
| Vendored assets are large / licensing | Pin versions, include licenses, only the needed builds; no source maps |
| Django 5.2 not supporting 3.14 | Use `py -3.13`; documented in README and System page; alternative Django 6.x is an explicit approval item |
| Scope creep into fixing the pipeline | Hard rule: new findings go to `docs/ISSUES.md`; no `chopcast/` edits |

---

## 18. New issues found during this study (to append to `docs/ISSUES.md`)

These are genuinely new relative to the existing 82:

- **ISS-083** — No configured map output location or map-run metadata.
- **ISS-084** — Generated folium maps are not offline-capable (CDN JS/CSS + online tiles by default).
- **ISS-085** — No training/evaluation run history table; history must be inferred from registry rows and artifact files.
- **ISS-086** — Two collector log destinations/formats (`logs/collector.log` vs root `collector.log`) with no run ID.
- **ISS-087** — Evaluation metrics are duplicated in `metrics_json`, `metrics.json`, and `report.json` with no schema/version field.

They will be appended in the existing format, with the summary table and counts updated.

---

## 19. Out of scope (explicit)

- Fixing any pipeline bug or resolving any open decision.
- Triggering collection, migration, training, evaluation, or map generation from the UI.
- Loading or serving model predictions from joblib artifacts.
- Authentication/authorization beyond optional Django admin.
- Multi-user deployment, background jobs, WebSockets, or live updates.
- Editing `docs/ISSUES.md` from the UI.
- A REST API for third parties (the map JSON endpoint is internal).
- Changing `chopcast/`, `configs/`, `data/`, `models/`, `runs/`, or `logs/`.

---

## 20. Approval checklist

Please confirm or correct:

1. **`maps/` assumption** — "`maps/`" means `chopcast/map/folium_app.py`; no such directory exists.
2. **Stack** — Django 5.2 LTS, Python 3.13 locally (`py -3.13`), support 3.11–3.13; no Django 4.2.
3. **No `chopcast/map/` changes** — the dashboard re-renders the map from `trainable`; the module is untouched.
4. **Read-only scope** — SQLite `mode=ro`, no migrations, no artifact writes; demo data only under `dashboard/var/demo/`.
5. **Adapter contract** — `CHOPCAST_DASHBOARD_*` env vars as listed; one adapter package; capability detection for legacy/target.
6. **Pages/URLs** — the map in §8.2.
7. **Map defaults** — offline vendored world layer; optional tile URL; 2,000-point cap; layer selector labelled primary/secondary/combined.
8. **New issues** — append ISS-083…087 to `docs/ISSUES.md`.

After approval I will start at Phase 0 and stop at the end of each phase for review if you prefer, or proceed through Phase 6 continuously.

---

## 21. Appendix: why not simpler alternatives

- **Streamlit/Gradio:** fast, but violates the Django requirement, gives poor table/filter control, and encourages running pipeline code.
- **Django admin over mirrored models:** would require copying pipeline data into a dashboard DB, doubling storage and creating a stale mirror; admin is also poor at read-only detail pages.
- **Importing `chopcast` for metrics/parsing:** would couple the dashboard to CWD, broken modules, and pydantic config, and would tempt execution; direct reads are safer.
- **Calling `generate_map()` and embedding its HTML:** writes files, fails today, and cannot be filtered; re-rendering is the only read-only option.
- **A single giant `views.py`:** faster to start, but the adapter boundary is the whole point of the brief; separate services keep the swap cheap.
- **Postgres/ORM:** unnecessary for read-only SQLite at this scale; adds a service and a migration story.

