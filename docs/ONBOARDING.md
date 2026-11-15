# ChopCast — Onboarding Notes

**Prepared:** 2026-11-14
**Repository state:** `main` @ `29fb780` ("training updates and finetuning setup"), working tree dirty (see §5.1)
**Method:** read-only review — source, configs, docs, tests, and both live SQLite databases. No project files were modified except this document. Commands that could mutate state were not run; the two exceptions were (a) read-only SQLite connections (`mode=ro`) and (b) opening a *temp copy* of `data/raw/pireps.db` to test migrations.
**How to read this:** everything below is grounded in a file path and, where useful, a symbol. Where the docs and the code disagree, that is called out explicitly rather than resolved silently.

---

## 1. What ChopCast is

ChopCast turns pilot reports (PIREPs) into labelled turbulence data, trains a text classifier to predict turbulence severity, plots the results geographically, and (eventually) fuses reports with weather observations.

The domain loop, from `README.md`:

1. **Collect** aircraft reports from the AWC gzipped CSV cache (`README.md:106-113`). The cache is a rolling window of roughly **90 minutes** and there is no backfill endpoint, so collection must run continuously.
2. **Strip `/TB` from the model input** to prevent label leakage (`README.md:41-47`, `docs/adr/0003-leakage-prevention.md`).
3. **Classify** into four classes — `None` / `Light` / `Moderate` / `Severe`.
4. **Map** reports and predictions.
5. **Fuse** with weather (METAR), currently aspirational.

The central design constraint: a PIREP contains both the answer and the input.

```
UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP occasional sharp jolts
```

`/TB MOD` is the label; the rest is the feature text. `chopcast/processing/cleaner.py` is the **only** module allowed to remove `/TB` (`clean_text`), enforced by `tests/lint/test_no_tb_outside_cleaner.py` and by a runtime self-check that raises `LeakageError`.

Note on scale today: the live DB has **3,525** reports, of which **290** are labelled PIREPs (see §5.2). This is a small, early-stage dataset.

---

## 2. Architecture in a nutshell

The intended shape (and mostly the implemented shape) is a one-way pipeline with SQLite at the centre:

```
AWC CSV.gz
   │  chopcast/collector/client.py     (requests, retries, gzip, pandas)
   ▼
resolve_columns → DefaultRowValidator → report_hash
   │  chopcast/collector/service.py
   ▼
reports table  ──►  views: pireps / trainable / wx_altitude
   │  chopcast/storage/{schema,migrations}.py
   ▼
process()  ──► parse_pirep ──► map_to_severity ──► clean_text ──► FeatureRow
   │  chopcast/processing/pipeline.py
   ▼
stratified split  ──►  BaselineSklearn  |  TransformerDistilBERT
   │  chopcast/training/{split,baseline,transformer_trainer}.py
   ▼
evaluate()  ──►  artifact dir (joblib + manifest + metrics.json + lineage.json)
   │  chopcast/evaluation/report.py, chopcast/models/*.py
   ▼
model registry SQLite (models + promotions)
   │  chopcast/registry/store.py
   ▼
map (folium) / evaluation compare / (future) API
```

Key architectural decisions and where they live:

| Decision | Where |
|---|---|
| Package layout, no flat scripts | `docs/adr/0001-redesign-rationale.md`, `docs/adr/0002-repository-layout.md` |
| Leakage prevention in the cleaner only | `docs/adr/0003-leakage-prevention.md`, `chopcast/processing/cleaner.py` |
| Content-hash dedup on `(obs_time, lat, lon, normalized text)` | `docs/adr/0004-dedup-strategy.md`, `chopcast/collector/hasher.py` (`report_hash`) |
| One `Model` protocol for baseline and transformer | `docs/adr/0005-model-abstraction.md`, `chopcast/models/protocol.py` |
| Data must not live under a cloud-sync folder | `docs/adr/0006-no-onedrive.md` |
| Two turbulence layers, `turbulence` and `turbulence_2` | `chopcast/storage/migrations.py` (migration 2) |
| AIREPs are filtered, never deleted | `chopcast/storage/migrations.py` (migration 3 comments), `README.md:132-151` |

Configuration is layered YAML + environment, resolved into a frozen Pydantic object and a `Paths` helper:

- `chopcast/config.py` — `Settings.load()`: `configs/default.yaml` → `configs/<profile>.yaml` → `CHOPCAST_*` env vars → `${paths.root}` expansion.
- `chopcast/paths.py` — `Paths` / `Paths.from_settings()`; the only sanctioned way to construct filesystem paths.
- `configs/default.yaml` — the baseline; `configs/{dev,prod,ci}.yaml` are overlays; `configs/labeling.yaml` holds the severity rules.

Persistence is two independent SQLite databases:

- **Raw store** — `data/raw/pireps.db`, schema in `chopcast/storage/schema.py` (`SCHEMA`), evolution in `chopcast/storage/migrations.py` (`MIGRATIONS`, `apply_migrations`). Interface: `ReportStore` protocol, implementation `SqliteReportStore`.
- **Model registry** — `models/registry/registry.db`, schema in `chopcast/registry/store.py` (`REGISTRY_SCHEMA`). Append-only `promotions` table; artifacts live beside it (`baseline-v1_test/…`).

---

## 3. Module map

| Package / file | Responsibility | State |
|---|---|---|
| `chopcast/__init__.py` | Version only (`__version__ = "0.1.0"`) | Fine |
| `chopcast/config.py` | Pydantic settings for every section; `Settings.load()` | Works from repo root; does **not** read `.env` (§5.4) |
| `chopcast/paths.py` | `Paths` object, `ensure_dirs()` | Works |
| `chopcast/errors.py` | `ChopcastError`, `ConfigError`, `ValidationError`, `FeatureBuildError`, `LeakageError`, … | Works |
| `chopcast/logging.py` | structlog config, `get_logger`, `configure` | **Untracked in git** (§5.1) |
| `chopcast/cli.py` | Root `chopcast` CLI: `config show/validate`, `paths`, `map`, `train run`, `eval compare` | Partly broken (§5.5) |
| `chopcast/collector/client.py` | AWC fetch: gzip CSV → DataFrame, retries/backoff | Not executed in this review |
| `chopcast/collector/service.py` | `DefaultCollectionService.run_once()`; column resolution, validation, hashing, insert, run bookkeeping | Logic is coherent; depends on store compatibility |
| `chopcast/collector/validators.py` | `DefaultRowValidator` → `Verdict(ok, reason, detail)`; lat/lon/raw_text checks | Works |
| `chopcast/collector/hasher.py` | `report_hash()` = SHA-256 over `obs_time | lat4 | lon4 | normalized text` | Works |
| `chopcast/collector/cli.py` | `chopcast-collector once/run/status/rejected/migrate-legacy` | `once`/`status` open the raw DB directly (§5.2) |
| `chopcast/storage/schema.py` | `SCHEMA`, `ReportStore`, `SqliteReportStore`, `RunResult`, `RunRecord` | Schema is the target, not what's on disk |
| `chopcast/storage/migrations.py` | `Migration`, `MIGRATIONS` (v1 schema_migrations, v2 turbulence layers, v3 views), `apply_migrations` | Fails on the existing legacy DB (§5.2) |
| `chopcast/parser/pirep.py` | `parse_pirep()` → `PirepFields`; slash-field tokenizer; `/OV` navaid helper | **Fails on the real AWC text format** (§5.3) |
| `chopcast/parser/navaid.py`, `golden.py` | Navaid lookup helpers, golden-corpus helper | Small; not on the training path |
| `chopcast/labeling/rules.py` | `LabelingRules`, `load_rules()` from `configs/labeling.yaml` | Requires a `Path`, not `str` |
| `chopcast/labeling/mapper.py` | `map_to_severity()`; substring matching, combination strategy | Works |
| `chopcast/labeling/combinations.py` | `combine()` for multi-match values (`max`/`min`/`first`) | Works |
| `chopcast/processing/cleaner.py` | `clean_text()` — removes `/TB` blocks, lowercases, collapses whitespace, self-check | Works; leakage defence is real |
| `chopcast/processing/pipeline.py` | `process()`, `RawReport` protocol, `_RowAdapter`, `build_deps()`, `PipelineDeps` | Central seam; several issues (§5.6) |
| `chopcast/processing/features.py` | `FeatureRow` (frozen dataclass), `altitude_band()` | Works |
| `chopcast/data/feature_store.py` | `build_dataset()` / `stream_features()` → JSONL (`features_<version>.jsonl`) | Works standalone; not wired into `chopcast-train` |
| `chopcast/data/version.py` | Dataset version derivation | Works |
| `chopcast/models/protocol.py` | `Model` protocol (`predict`, `predict_proba`, `classes`, version fields) | Works |
| `chopcast/models/baseline_sklearn.py` | `BaselineSklearn.train/load/save` (TF-IDF + LogReg or LinearSVC), joblib persistence | `predict_proba` is inconsistent for LinearSVC (§5.7) |
| `chopcast/models/transformer_distilbert.py` | DistilBERT wrapper satisfying `Model` | Not exercised here |
| `chopcast/training/orchestrator.py` | `run_training()`: DB → process → split → fit → evaluate → save → register | Only path that writes real artifacts; bugs in §5.6 |
| `chopcast/training/baseline.py` | `train_baseline()` → `BaselineRun` (model + split + evaluation) | Used only by `chopcast-train` |
| `chopcast/training/transformer_trainer.py` | `train_transformer()` → `TransformerRun` | Works as a library; orchestrator misuses it |
| `chopcast/training/split.py` | `make_split()` (stratified/time), `save_split`/`load_split` | Works |
| `chopcast/training/class_weights.py` | Class-weight helpers | Small utility |
| `chopcast/training/cli.py` | `chopcast-train run/list/promote/compare` | `run` is broken (`cfg.split`) (§5.6) |
| `chopcast/evaluation/{metrics,report,compare}.py` | Metric primitives, `EvaluationReport` + `to_markdown`, model-vs-model diff | Pure functions; work |
| `chopcast/evaluation/orchestrator.py` | `compare_models()` on a shared split manifest | Broken (`str / Path`, `Row` vs dict) |
| `chopcast/registry/store.py` | `SqliteModelRegistry`, `ModelRegistry` protocol | Works, but pollutes the registry DB (§5.8) |
| `chopcast/map/folium_app.py` | `generate_map()`: folium map of reports/predictions | Broken on live data (§5.5); **no `__init__.py`** |
| `chopcast/weather/{features,matcher,cache}.py` | Weather features, METAR nearest-match, Parquet cache | Inert / partly unimportable (§5.9) |
| `chopcast/weather/providers/metar.py` | METAR provider | **No `__init__.py`** in `weather/` or `providers/` |
| `scripts/migrate_legacy_db.py` | Legacy → new schema migration | Cannot target the legacy DB it is meant to migrate (§5.2) |
| `tests/` | 30 test modules (unit, integration, lint) | Partial coverage; see §6 |
| `deploy/` | systemd units, bootstrap/backup scripts, AWS runbook | Not verified |

Docs live in `docs/`: `ARCHITECTURE.md`, `ROADMAP.md`, `MODULE_DESIGN.md`, `DATA_ENGINEERING.md`, `ML_ARCHITECTURE.md`, `CONFIGURATION.md`, `TESTING.md`, `STANDARDS.md`, `CONTRIBUTING.md`, `adr/0001-0006`. They are design-first and, in several places, ahead of the code (§5.10).

---

## 4. End-to-end data flow (what actually happens)

**Collection** (`chopcast/collector/service.py`, `DefaultCollectionService.run_once`)

1. `client.fetch_aircraft_reports()` returns a `pandas.DataFrame` (or `None` for "no data").
2. `resolve_columns()` maps AWC's evolving headers to logical names via `CANDIDATES`; unmatched fields log `collector.columns.unresolved`.
3. `DefaultRowValidator.validate()` rejects bad coordinates / empty text; rejects go to `rejected`.
4. `report_hash()` computes the content hash; `INSERT` with primary-key-conflict handling in `SqliteReportStore.insert_report`.
5. `begin_run` / `finish_run` record the cycle in `runs`.

**Views** (`chopcast/storage/migrations.py`, migration 3 — the *intended* definitions)

- `pireps` — `report_type LIKE '%PIREP%'` (excludes AIREP).
- `trainable` — labelled PIREPs, `/TB` deliberately still present in `raw_text`.
- `wx_altitude` — AIREP temperature/wind extracted from `raw_json` via `json_extract`.

**Processing** (`chopcast/processing/pipeline.py`, `process`)

1. `parse_pirep(raw_text)` → `PirepFields`.
2. `map_to_severity(parsed.turbulence, rules)` → `None` / `Light` / `Moderate` / `Severe` (default `None`).
3. `clean_text(raw_text, config.cleaner)` → leakage-free text (the only call site of the cleaner).
4. `altitude_band()`, hour-of-day, day-of-year, aircraft, report type → `FeatureRow`.

**Training** (`chopcast/training/orchestrator.py`, `run_training`)

1. `SELECT * FROM trainable WHERE report_type = 'PIREP' OR report_type = 'Urgent PIREP'`.
2. `process()` each row (dict adapter), drop empties.
3. `make_split(hashes, labels, settings.training.default_split)`; materialise train/test by hash membership.
4. Fit `BaselineSklearn` (default) or `train_transformer`.
5. `evaluate()` → `EvaluationReport` (`accuracy`, `macro_f1`, `weighted_f1`, per-class, confusion).
6. Save artifact to `models/registry/<kind>-<version>/`, split manifest to `runs/`, `lineage.json`, `metrics.json`, then `registry.register(...)`.

**Evaluation / mapping**

- `compare_models()` loads two registry entries, reads the split manifest, reloads the test rows, and diffs reports.
- `generate_map()` reads `trainable`, optionally predicts with a registered baseline, and writes a folium HTML file.

---

## 5. Current state: what works, what doesn't

### 5.1 Git state is dirty and the clean checkout is not importable

`git status` at `29fb780`:

```
 D chopcast/chopcast/logging.py      # deleted at a nested (wrong) path
 M chopcast/training/orchestrator.py
 M chopcast/weather/features.py
 M chopcast/weather/matcher.py
?? chopcast/logging.py               # the real module is untracked
?? test_pipeline.py
?? test_pipeline.py`
?? test_transformer.py
?? trace_pipeline.py
```

Every module does `from chopcast.logging import get_logger`, but `chopcast/logging.py` is **not committed**. A fresh clone of `main` therefore fails at import time. The tracked-but-deleted path `chopcast/chopcast/logging.py` indicates a bad `git add` earlier.

### 5.2 The live database does not match the current schema or migrations

`data/raw/pireps.db` (read-only inspection):

- `reports`: **3,525** rows — `AIREP` 2,928, `PIREP` 591, `Urgent PIREP` 6.
- `trainable`: **290** rows.
- Turbulence column: `LGT` 141, `LGT-MOD` 27, `MOD` 48, `NEG` 88, `MOD-SEV` 1, `SEV` 1, `NULL` 3,219.
- Time span: `2026-08-30T16:30Z` – `2026-10-03T16:42Z`; two `runs` rows, both `ok`.
- `PRAGMA user_version = 0`; **no `schema_migrations` table**.

Its shape is the legacy one:

- `reports` has **no** `source_url` / `source_etag` (both `NOT NULL` in `SCHEMA`).
- `runs` has `(id, ran_at, rows_seen, inserted, skipped, status)` instead of `(started_at, finished_at, status, rows_seen, rows_inserted, rows_skipped, rows_rejected, error)`.
- `trainable` is `SELECT * FROM reports WHERE report_type IN ('PIREP','Urgent PIREP') AND turbulence IS NOT NULL` — not the migration-3 view (which projects specific columns and includes `turbulence_2`).

Consequences, verified:

- Running `apply_migrations()` against a **copy** of this DB raises
  `sqlite3.OperationalError: duplicate column name: turbulence_2` — migration 2 blindly `ALTER TABLE ... ADD COLUMN`s columns the legacy DB already has.
- `SqliteReportStore.__init__` calls `apply_migrations()` then `SCHEMA`, so `chopcast-collector once` / `status` — which construct `SqliteReportStore(paths.raw_db_path)` (`chopcast/collector/cli.py:55`, `:149`) — will fail on the existing DB the same way.
- `scripts/migrate_legacy_db.py` defaults its destination to `paths.raw_db_path`, i.e. the same file it is migrating; even with a different destination, `CREATE VIEW IF NOT EXISTS trainable` leaves the legacy view in place, and the insert does not carry `turbulence_2`/`_type`/`_freq`.

Because `SqliteModelRegistry.__init__` also calls `apply_migrations(self._conn, MIGRATIONS)` (`chopcast/registry/store.py:113`), `models/registry/registry.db` contains an empty `reports` table plus the `pireps` / `trainable` / `wx_altitude` views and `schema_migrations` v1–v3. The registry DB should not carry the raw-data schema.

### 5.3 The parser does not handle the real AWC text format — and that explains the model

`parse_pirep()` (`chopcast/parser/pirep.py`) tokenises on **whitespace followed by `/`**. That works for the canonical example:

```
"UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP ..."  → /TB = "MOD CHOP ..."
```

The actual AWC cache omits spaces before later fields:

```
"MLI UA /OV MLI270020/TM 1756/FL170/TP CRJ2/TB CONS MOD "
```

Measured behaviour on that row:

```
tokens: ['MLI', '/UA', '/OV', 'MLI270020/TM 1756/FL170/TP CRJ2/TB CONS MOD']
location: 'MLI270020/TM 1756/FL170/TP CRJ2/TB CONS MOD'
turbulence: None
flight_level: None   aircraft_type: None   obs_time: None
```

Across all 290 rows in `trainable`:

- **285 / 290** parse to `turbulence = None`.
- Resulting labels: **288 `None`, 1 `Light`, 1 `Moderate`** and no `Severe`.

So the labeler is not the problem; the parser silently discards the label. `process()` then applies `default_label = "None"`. This is the most important finding in this review: the pipeline trains on almost entirely `None` labels, which is exactly what the stored artifacts show (§5.11).

Secondary parser issues: `_parse_location()` is a placeholder that returns `None` for real navaid/relative-position strings; the module docstring says it raises `ParseError`, but the code raises `ValueError` (`pirep.py:233-256`); `_parse_time()` stamps the **current** date onto `HHMM`, which is wrong for historical rows.

### 5.4 Configuration: `.env` is documented but never read

- `chopcast/config.py:1-12` and `configs/default.yaml:3` say `.env` overrides apply, and `README.md:18-19` and `.env.example` tell users to `cp .env.example .env` and edit it.
- `Settings.model_config` sets `env_file=None` (`config.py:320`) and `Settings.load()` only reads `configs/*.yaml` + `os.environ` (`config.py:337-387`). No `.env` parsing anywhere.
- `Settings.load()` resolves `configs/default.yaml` **relative to the current working directory**, not the repo root. Running any console script from another directory raises `ConfigError: Configuration file not found`.
- ADR-0006 claims a startup check warns when `paths.root` is under OneDrive/Dropbox/iCloud/Google Drive; no such check exists in `chopcast/config.py` (grep finds nothing).

### 5.5 CLI surface: advertised commands are missing or broken

`pyproject.toml:66-73` declares seven entry points. Three target modules that **do not exist**:

| Entry point | Target | Exists? |
|---|---|---|
| `chopcast-eval` | `chopcast.evaluation.cli:main` | No |
| `chopcast-registry` | `chopcast.registry.cli:main` | No |
| `chopcast-map` | `chopcast.map.cli:main` | No |

The `chopcast` root CLI re-implements `map`, `train run`, and `eval compare` (`chopcast/cli.py`), but:

- `map_reports()` uses `Path(output)` at `cli.py:44` without importing `Path` → `NameError`.
- `generate_map()` reads `row["severity_label"]` (`folium_app.py:62`, `:111`), a column that does not exist in `trainable` → `KeyError`.
- `generate_map()` computes `avg_lat/avg_lon` as `sum(... if r["lat"]) / len(rows)` (`folium_app.py:87-88`): rows with missing coordinates are excluded from the numerator but still counted in the denominator, and `0.0` is treated as missing.
- `compare_models()` does `paths.runs_dir / f"split-..."` (`evaluation/orchestrator.py:60`) where `paths.runs_dir` is a `str` → `TypeError`. It also passes `sqlite3.Row` directly to `process()` (`:83`), which only adapts `dict` (`pipeline.py:120`) → `AttributeError`.

Also: `chopcast/map/`, `chopcast/weather/`, and `chopcast/weather/providers/` have **no `__init__.py`**. `[tool.setuptools.packages.find]` (`pyproject.toml:79-84`) will not package them, so an editable/regular install cannot import `chopcast.map.folium_app` or `chopcast.weather.*`.

### 5.6 Three training paths, none fully consistent

1. `chopcast train run` → `chopcast/training/orchestrator.run_training()`.
2. `chopcast-train run` → `chopcast/training/cli.py` → `train_baseline()` / `train_transformer()`.
3. Root scripts `test_pipeline.py`, `test_transformer.py`, `trace_pipeline.py` (untracked) do their own wiring.

Specific defects:

- `chopcast/training/cli.py:105` and `:119` pass `split_cfg=cfg.split`. `Settings` has **no** `split` attribute; it is `settings.training.default_split` → `AttributeError` before training starts.
- `run_training()` assigns `model = train_transformer(...)`, which returns a `TransformerRun` dataclass (`transformer_trainer.py:36,74,130`), then calls `model.predict(X_test)` / `model.save(...)` (`orchestrator.py:145,151,158`) → `AttributeError`.
- `run_training()` mutates the frozen `PipelineDeps` via `object.__setattr__` (`orchestrator.py:53`).
- `process()` never uses the DB `turbulence` column, despite the comment “fall back to whatever the raw row carried” (`pipeline.py:138-140`). The label comes only from `/TB` in the text — which §5.3 shows is usually missing.
- `build_deps()` has no `weather_matcher` parameter (`pipeline.py:248-274`), so weather is injected only by the frozen-dataclass hack.
- `FeatureRow.report_type` is `str`, but the fallback `report_type or "PIREP"` assumes non-`None`.
- `process()`'s docstring says missing `obs_time` raises `FeatureBuildError`; the code logs and returns `None` (`pipeline.py:124-127`).
- `pipeline.py` imports `chopcast.weather.matcher` (`:37`) — the layering rules in `docs/MODULE_DESIGN.md` say processing should not depend on weather/collector. `folium_app.py` imports `DefaultRowValidator` from the collector, another cross-layer import.

### 5.7 Baseline `predict_proba` is inconsistent for LinearSVC

`BaselineSklearn.train` wraps `LinearSVC` in `CalibratedClassifierCV` (`baseline_sklearn.py:83-93`), but `predict_proba()` calls `self._pipeline.named_steps["clf"].predict_proba(self._pipeline[:-1].transform(X))` (`:119-125`). For LogReg the pipeline step already owns the vectoriser, but the code re-vectorises manually; for the calibrated SVC it is not the same object the pipeline would use. Either way the path is not exercised by tests, and the `hasattr` guard only catches the uncalibrated case.

### 5.8 Registry / model artifacts on disk

`models/registry/registry.db` (read-only):

| id | model_version | model_kind | feature_version | artifact | notes |
|---|---|---|---|---|---|
| 1 | `v1_test` | `baseline` | `v1` | `models\registry\baseline-v1_test` | Macro-F1 0.333 |
| 2 | `v1_transformer` | `baseline` (**sic**) | `v1` | `models\registry\baseline-v1_transformer` | Macro-F1 0.333 |

- `promotions` is empty (nothing is “production”).
- Model 2 is registered as `kind=baseline`, and its artifact dir is `baseline-v1_transformer` — the transformer branch was labelled as a baseline by `run_training()`'s `kind` variable.
- `baseline-v1_test/metrics.json`: labels `Light, Moderate, None`; only `None` has support (58); `accuracy = 1.0`, `macro_f1 = 0.333`, `weighted_f1 = 1.0`. `lineage.json`: 290 raw / 290 usable / 232 train / 58 test.
- `artifact_path` is stored relative (`models\registry\...`), so loading depends on CWD.
- Artifacts are written to `models/registry/<kind>-<version>/`, while the registry is at `models/registry/registry.db` — artifacts and the registry DB are commingled.

This is the observable symptom of §5.3: a “perfect” accuracy on a single-class test set with a near-zero macro-F1.

### 5.9 Weather fusion is inert

- `process()` calls `deps.weather_matcher.find_nearest(lat, lon, obs_time, [])` (`pipeline.py:161-166`) — always an empty observation list, so the matcher always returns `None`.
- `run_training(use_weather=True)` builds `X_train` as `(text, weather.to_dict())` tuples (`orchestrator.py:104-107`), but `WeatherFeatures` (`weather/features.py`) has **no `to_dict()`** → `AttributeError`; `BaselineSklearn` also only accepts `list[str]`.
- `WeatherMatcher.find_nearest` expects observation dicts with `time`, `lat`, `lon` (`weather/matcher.py:40-48`); no provider populates that shape on the training path.
- `chopcast/weather/cache.py` contains literal `\"\"\"` sequences (`:12-13`, `:19-20`, `:28-29`, `:40-41`) — a syntax error — and uses `settings.to_paths().weather_cache_path`, which `Paths` does not define (`paths.py:34-43`).
- `chopcast/weather/providers/metar.py` has the same literal-escape problem (per earlier review) and is not packaged (`__init__.py` missing).

### 5.10 Documentation drift (selected, high-impact)

- `README.md:5` says “Pre-M0 … original 3-file prototype is in `explore.py`, `collector.py`, `test_collector.py`”. Those files do not exist, and `chopcast/` is a full package. `CLAUDE.md` repeats the same stale description.
- `README.md:91-104` lists `chopcast-parse`, `chopcast-eval`, `chopcast-registry`, `chopcast-map` as working commands; the latter three have no module, and `chopcast-parse` exists (`chopcast/parser/cli.py`) but is not covered here.
- `docs/TESTING.md` describes import-lint, secrets-lint, golden corpus, regression, weather, api, and monitoring tests that are not present (see §6).
- `docs/ROADMAP.md` has **all** M0–M7 “definition of done” boxes unchecked, including “`pip install -e .[dev]` succeeds from a clean checkout” and “`ruff check`, `mypy`, `pytest` all pass on CI”.
- ADR-0001/0003 reference `tests/lint/test_imports.py`, `tests/lint/test_no_tb_leakage.py`, and a call-graph test; the repo has `tests/lint/test_no_tb_outside_cleaner.py` only, and no call-graph test.
- `docs/RUNBOOK.md` uses the repo URL `https://github.com/SrivatsaChilla/ChopCast`; `pyproject.toml:76-77` uses `musiimenta-joachim/ChopCast`.
- `requirements.txt` is `pandas>=2.0`, `requests>=2.28` only, while `pyproject.toml` is the real dependency list; docs reference DVC, Docker, pre-commit, and CI workflows that are absent (no `.github/`, no `Dockerfile`, no `.pre-commit-config.yaml`, no `.dvc/`).

### 5.11 What is genuinely solid

- The **leakage defence** is real and testable: `clean_text()` strips configured tags and re-scans its own output, raising `LeakageError`; the lint test tokenises source and ignores strings/comments, which is a sensible design (`tests/lint/test_no_tb_outside_cleaner.py`).
- **Dedup** is deterministic and content-addressed (`hasher.py`), and `insert_report` deliberately distinguishes primary-key conflicts from CHECK/NOT NULL violations (`schema.py:252-291`).
- **Evaluation primitives** (`evaluation/metrics.py`, `report.py`) are pure and well-shaped; `EvaluationReport` is the right canonical object, and Markdown rendering already exists.
- **Configuration model** is comprehensive (every subsystem has a typed section) even though `.env` loading is missing.
- The **ADR set** is unusually good: each decision states the alternative and the cost. ADR-0003 and ADR-0004 in particular explain *why* the design is shaped this way.

---

## 6. Tests and quality gates

`pyproject.toml` is strict:

- `pytest`: `testpaths = ["tests"]`, `-ra --strict-markers --strict-config -m "not integration"` (integration tests are opt-in), warnings are **errors**.
- Coverage: `source = ["chopcast"]`, `fail_under = 80`.
- `mypy --strict` (`strict = true`, `disallow_any_generics`, pydantic plugin).
- `ruff` with `E,F,W,I,N,UP,B,A,C4,PT,RUF`, line length 100.

What exists under `tests/`:

- **Unit:** `test_config`, `test_errors`, `test_paths`; `unit/collector/{test_cli,test_client,test_hasher,test_service,test_validators}`; `unit/storage/{test_migrations,test_schema,test_views}`; `unit/parser/test_pirep`; `unit/processing/{test_cleaner,test_pipeline}`; `unit/labeling/test_labeling`; `unit/models/{test_protocol,test_transformer_distilbert}`; `unit/training/{test_baseline,test_split,test_transformer_trainer}`; `unit/evaluation/{test_compare,test_metrics}`; `unit/registry/test_registry`.
- **Integration:** `integration/collector/test_migration.py` (deselected by default).
- **Lint:** `lint/test_no_tb_outside_cleaner.py`.

Missing relative to `docs/TESTING.md`: import-boundary lint, secrets lint, golden-corpus tests, regression/“no metric regression” gate, weather tests, API tests, monitoring/drift tests. There is no CI workflow to run any of it.

I did **not** run `pytest`, `ruff`, or `mypy` (they write caches / are state-changing under the read-only brief). Expect failures: `chopcast/weather/cache.py` and `chopcast/weather/providers/metar.py` are syntax errors and sit inside the package; `map/` and `weather/` are not packaged; several tests import modules that use the untracked `logging.py`.

---

## 7. Risks and open questions

Ordered by how much they block useful work.

1. **Labels are effectively destroyed by the parser (§5.3).** 285/290 labelled rows become `None`. Until this is fixed, every metric is meaningless — the current artifact’s `accuracy = 1.0` is a single-class artifact, not a result. *This is the first thing to confirm with the owner.*
2. **The live DB cannot be opened by the current code (§5.2).** The collector CLI and any migration fail with `duplicate column name: turbulence_2`. There is no documented “start from a fresh DB” path, and the ADR-0006 mitigation (point `CHOPCAST_PATHS__ROOT` elsewhere) is not actually wired through `.env`.
3. **The repo is not installable/importable from a clean clone (§5.1, §5.5).** Untracked `chopcast/logging.py`, three missing `__init__.py`, and three entry points pointing at nonexistent modules. M0’s own definition of done is unchecked.
4. **Three training entry points disagree (§5.6).** `chopcast-train run` cannot start (`cfg.split`), the transformer branch of `run_training` treats a `TransformerRun` as a model, and `chopcast train run` duplicates the orchestrator. Which one is canonical is a product decision, not a code-reading one.
5. **Registry and artifact layout is muddled (§5.8).** Data-store migrations run against the registry DB; artifact paths are relative; both stored models are labelled `baseline`; nothing is promoted. Any “current production model” query returns `None`.
6. **Map and compare paths are broken at the CLI boundary (§5.5).** `Path` missing, `severity_label` missing, `str / Path`, `Row` vs `dict`.
7. **Weather is not merely disabled — it is unimplementable as written (§5.9).** Empty observation list, missing `to_dict`, missing `Paths.weather_cache_path`, syntax errors, unpackaged subpackage.
8. **Docs overstate the system (§5.10).** New contributors will follow `README.md`/`TESTING.md` and hit missing files. The ADRs are trustworthy; the README/CLAUDE/TESTING/RUNBOOK are not.
9. **Data location vs ADR-0006.** The repo is under OneDrive; the recommended non-synced root is only a commented line in `.env.example`, `.env` is not loaded, and no sync-folder warning exists.
10. **Unverified:** network behaviour of `AwcClient`; `deploy/*.sh` and systemd units; `docs/RUNBOOK.md` steps; transformer training (torch/transformers not installed here).

Questions I could not answer from the repository:

- Which training path is canonical — `chopcast train run` (DB → orchestrator) or `chopcast-train run` (JSONL → `train_baseline`)? They have different inputs, splits, and artifact layouts.
- Is `data/raw/pireps.db` meant to be migrated in place, or is the new store meant to start empty (with the legacy DB only as a source)? `scripts/migrate_legacy_db.py` assumes the latter but defaults to the former.
- Are the two turbulence layers (`turbulence`, `turbulence_2`) meant to be combined into one label, or kept as separate targets? `trainable` uses either; `process()` ignores both.
- Should `chopcast-eval`, `chopcast-map`, and `chopcast-registry` exist as separate console scripts (as `pyproject.toml` declares) or remain subcommands of `chopcast` (as `cli.py` implements)?
- Is the model-registry DB supposed to hold the raw-data schema? Right now it does, because `SqliteModelRegistry` applies `MIGRATIONS`.
- What is the intended minimum Python version? `pyproject.toml` says `>=3.11`; the local `__pycache__` files are `cpython-314`, and some code (e.g. `datetime.fromisoformat` with `Z`) relies on 3.11+ behaviour.
- Should artifacts live under `models/registry/` (current) or a separate `models/artifacts/` tree? Relative `artifact_path` values make this a migration decision, not just a layout preference.

---

## 8. How to run, test, and build (as documented, with caveats)

> Everything below is what the repo *says* to do. Given §5.1–§5.5, expect the first command to need fixes before it works.

**Install (from the repo root):**

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Caveats: `chopcast/logging.py` is untracked (a clean clone will not import); `chopcast/map` and `chopcast/weather` lack `__init__.py` and will not be packaged; `chopcast-eval`, `chopcast-registry`, `chopcast-map` point at missing modules. `requirements.txt` is not the dependency source — use `pyproject.toml`.

**Configure:**

```bash
cp .env.example .env    # .env is NOT read by Settings.load(); export the vars instead
export CHOPCAST_COLLECTOR__USER_AGENT="chopcast/0.1 (+you@example.com)"
export CHOPCAST_PROFILE=dev
```

Run from the repository root: `Settings.load()` resolves `configs/default.yaml` relative to CWD. There is no sync-folder guard.

**Collect:**

```bash
chopcast-collector once
chopcast-collector run          # continuous, poll_seconds = 600
chopcast-collector status
chopcast-collector rejected --reason invalid_lat
```

Against the existing `data/raw/pireps.db`, `once`/`status` construct `SqliteReportStore` and fail at `apply_migrations` (`duplicate column name: turbulence_2`). To get a clean run, point `CHOPCAST_PATHS__ROOT` at a directory **outside** the repo/OneDrive (per ADR-0006) so a fresh DB is created.

**Parse / inspect config:**

```bash
chopcast-parse "UA /OV SFO /TB MOD CHOP /FL350"
chopcast config show
chopcast config validate
chopcast paths
```

**Train / evaluate / map:**

```bash
chopcast train run --version v2                  # DB → run_training()
chopcast-train run --features data/processed/features_<ver>.jsonl --model-version v2
chopcast-train list
chopcast-train promote <id> --tag production
chopcast-train compare <a> <b>
chopcast eval compare <a> <b>
chopcast map --output turbulence_map.html
```

Known breakages: `chopcast-train run` (`cfg.split`); `chopcast train run` transformer branch; `chopcast map` (`Path` not imported, `severity_label` missing); `eval compare` (`str / Path`, `Row` vs `dict`).

**Build a feature dataset (library only):**

```python
from chopcast.data.feature_store import FeatureStoreConfig, build_dataset
# build_dataset(rows, FeatureStoreConfig(processing=..., labeling=..., output_dir=Path("data/processed")))
# writes features_<version>.jsonl
```

**Test / lint / type-check:**

```bash
pytest                       # integration tests are deselected by default
pytest -m integration
ruff check .
ruff format --check .
mypy chopcast
```

Coverage gate is 80% (`[tool.coverage.report] fail_under = 80`); warnings are errors.

**Package build:** no build script or CI exists. `python -m build` would use setuptools with `include = ["chopcast*", "scripts*"]`; see the missing `__init__.py` and untracked-module caveats above.

---

## Appendix — evidence collected

- `git status --porcelain`, `git log --oneline -5` at `29fb780`.
- `data/raw/pireps.db` opened read-only: object list, row counts, `report_type` and turbulence distributions, `runs` contents, `PRAGMA table_info` for `reports` / `trainable`, `trainable` view SQL, `PRAGMA user_version`.
- `apply_migrations()` run against a **temp copy** of `pireps.db` → `OperationalError: duplicate column name: turbulence_2`.
- `models/registry/registry.db` opened read-only: `models` rows, `promotions` (empty), `sqlite_master` (contains `reports` + the three views), `schema_migrations` v1–v3.
- `models/registry/baseline-v1_test/{metrics,lineage}.json` and `manifest.txt` read.
- Parser probe on a real row plus a README-style row: token lists and captured `/TB`, `/FL`, `/TP`, `/TM`.
- Label probe over all 290 `trainable` rows with `load_rules("configs/labeling.yaml")` + `parse_pirep` + `map_to_severity` → 288 `None`, 1 `Light`, 1 `Moderate`.
- Files read in full or in relevant part: `pyproject.toml`, `README.md`, `.env.example`, `configs/default.yaml`, `configs/labeling.yaml`, `chopcast/{__init__,config,paths,logging,cli}.py`, `chopcast/storage/{schema,migrations}.py`, `chopcast/collector/{cli,service,validators,hasher}.py`, `chopcast/parser/pirep.py`, `chopcast/labeling/{mapper,rules,combinations}.py`, `chopcast/processing/{cleaner,features,pipeline}.py`, `chopcast/data/feature_store.py`, `chopcast/models/{protocol,baseline_sklearn}.py`, `chopcast/training/{orchestrator,cli,split,baseline,transformer_trainer}.py`, `chopcast/evaluation/{report,orchestrator}.py`, `chopcast/registry/store.py`, `chopcast/map/folium_app.py`, `chopcast/weather/{features,matcher,cache}.py`, `scripts/migrate_legacy_db.py`, `tests/lint/test_no_tb_outside_cleaner.py`, `docs/adr/0001-0006`.
