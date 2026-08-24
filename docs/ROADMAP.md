# Roadmap

> Milestones M0–M7. Each milestone is independently shippable. We commit to M0–M1 first; later milestones are revised as learning happens.

---

## Milestone 0 — Foundation

### Objective
Make the project buildable, lintable, testable, and configurable. Replace the prototype 3-file layout with the production package structure. Preserve any data already collected.

### Deliverables
- `pyproject.toml` with pinned dependencies, dev dependencies, and tool config (ruff, mypy, pytest).
- `chopcast/` package skeleton mirroring [MODULE_DESIGN.md](MODULE_DESIGN.md).
- `configs/default.yaml`, `configs/dev.yaml`, `configs/prod.yaml`.
- `.env.example` documenting every required environment variable.
- `.gitignore` covering `pireps.db*`, `__pycache__/`, `.venv/`, `data/raw/`, `data/processed/`, `models/registry/*`, `*.log`.
- CI workflow (GitHub Actions) that runs lint, type-check, and tests on every push.
- Migration script `scripts/migrate_legacy_db.py` that ingests the existing `pireps.db` (if any) into the new schema without data loss.

### Required modules
- `chopcast.config` — typed settings, loaded from YAML + `.env`.
- `chopcast.logging` — structured logger factory.
- `chopcast.paths` — repo-relative path resolution.

### Tests
- `test_config.py`: defaults load; overrides merge; missing required keys fail loudly.
- `test_paths.py`: paths resolve from repo root regardless of CWD.
- `test_migrate_legacy_db.py`: round-trips a synthetic legacy DB.

### Definition of Done
- [ ] `pip install -e .[dev]` succeeds from a clean checkout.
- [ ] `ruff check`, `mypy chopcast`, `pytest` all pass on CI.
- [ ] `python -m chopcast.collector --help` works.
- [ ] No Python file imports from outside the `chopcast.*` namespace.
- [ ] Legacy DB migration is idempotent: running it twice produces no extra rows.

---

## Milestone 1 — Data engineering

### Objective
Move from "we have a collector script" to "we have a versioned, deduplicated, queryable data lake for PIREPs."

### Deliverables
- `chopcast.collector` package replacing `collector.py`.
- SQLite schema with migration framework (Alembic or hand-rolled).
- Deduplication on a content-addressed hash.
- Validation layer that quarantines bad rows instead of dropping them.
- DVC (or equivalent) tracking for raw Parquet exports.
- Scheduled task manifest (Windows Task Scheduler XML, Linux systemd unit).

### Required modules
- `chopcast.collector.client` — AWC HTTP client with retry/backoff/rate-limit.
- `chopcast.collector.service` — orchestrator: fetch → validate → dedup → store → manifest.
- `chopcast.storage.schema` — SQLAlchemy (or sqlite3 + dataclasses) models.
- `chopcast.storage.migrations` — versioned DDL.
- `chopcast.storage.rejected` — quarantine table and inspection CLI.
- `chopcast.observability.metrics` — counters for `rows_seen`, `rows_inserted`, `rows_skipped`, `http_429_count`, etc.

### Tests
- `test_collector_client.py`: mocked HTTP, exercises 200/204/429/5xx/retry.
- `test_dedup.py`: identical rows produce one insert; near-duplicates (lat shifted by 0.0001) do not collide.
- `test_validation.py`: invalid lat, missing obs_time, bad ISO format → quarantined.
- `test_schema_migrations.py`: forward and backward migration of a populated DB.
- Integration: `test_collector_e2e.py` with `responses` library simulating AWC.

### Definition of Done
- [ ] Collector runs continuously for 72 hours without manual intervention.
- [ ] `pireps.db` survives backup-and-restore via `sqlite3 .backup`.
- [ ] `chopcast-collector status` shows accrual rate, dedup rate, and last successful poll.
- [ ] Rejected rows are inspectable via CLI: `chopcast-collector rejected --reason invalid_lat`.
- [ ] No code path writes to `reports` without going through the validation layer.

---

## Milestone 2 — NLP pipeline

### Objective
Turn raw PIREPs into clean, labeled, model-ready feature rows. This is where label leakage is structurally prevented.

### Deliverables
- PIREP parser covering `/OV`, `/TM`, `/FL`, `/TP`, `/TB`, `/SK`, `/WX`, `/TA`, `/IC`, `/RM`.
- Label mapper with versioned rules (`LGT-MOD` → `Moderate`, etc.).
- Leakage-safe cleaner with explicit denial of `/TB` reaching the model.
- Feature builder producing the canonical `FeatureRow` schema.
- Golden corpus: at least 100 hand-labeled PIREPs with expected parse output committed as a test fixture.

### Required modules
- `chopcast.parser.pirep` — regex/state-machine parser.
- `chopcast.parser.navaid` — `/OV` lookup for known navaids.
- `chopcast.labeling.rules` — `LGT|MOD|SEV|...` → severity, versioned in config.
- `chopcast.labeling.combinations` — handler for `LGT-MOD`, `OCNL MOD-CHOP`, etc.
- `chopcast.processing.cleaner` — strips `/TB`, normalizes whitespace, lowercases configurable.
- `chopcast.processing.features` — `build_features(report) -> FeatureRow`.
- `chopcast.processing.pipeline` — orchestrates parse → label → clean → featurize.

### Tests
- `test_parser_golden.py`: 100+ golden inputs with expected structured output.
- `test_labeling.py`: every documented mapping rule, plus edge cases (`NEG`, empty, `CHOP` only).
- `test_cleaner.py`: `/TB` is removed; `/TB` is removed even with trailing whitespace and weird casing; `RM CHOP` (which mentions turbulence as a remark) is preserved (the parser must distinguish `/TB` from `RM`).
- `test_pipeline.py`: round-trip from raw row to feature row produces a deterministic hash.

### Definition of Done
- [ ] Golden corpus is ≥ 100 hand-labeled PIREPs with 0 mismatches against the parser.
- [ ] `chopcast-parse --raw "UA /OV SFO /TB MOD CHOP /FL350"` produces structured output.
- [ ] Static check: no module other than `chopcast.processing.cleaner` contains the string `/TB` (regex-based lint rule).
- [ ] Labeling rules live in YAML, not in code.

---

## Milestone 3 — ML baseline

### Objective
Ship a TF-IDF + Logistic Regression baseline that beats the "majority class" floor. Establish the evaluation harness that every future model must pass.

### Deliverables
- TF-IDF + LogReg / Linear SVM training script.
- Stratified train/test split with split manifest committed alongside.
- Evaluation report: per-class precision, recall, F1, macro-F1, weighted-F1, confusion matrix, per-class support.
- Class-imbalance handling: class weights or SMOTE, whichever is documented as chosen.
- Experiment tracking wired to a local backend (MLflow or simple JSON manifests).
- Model registry with promoted/baseline tag.

### Required modules
- `chopcast.training.split` — split logic with manifest.
- `chopcast.training.baseline` — TF-IDF + LogReg/SVM.
- `chopcast.training.class_weights` — imbalance handler.
- `chopcast.evaluation.metrics` — per-class and aggregate metrics.
- `chopcast.evaluation.report` — markdown report renderer.
- `chopcast.registry.store` — append-only registry of model versions.

### Tests
- `test_split.py`: stratification preserves class proportions; manifest is deterministic.
- `test_baseline.py`: trains on synthetic data, hits a minimum F1, writes a registry entry.
- `test_metrics.py`: known input → known output (per-class + macro).
- `test_evaluation_regression.py`: when run on a committed fixture, evaluation output matches committed expected values to 4 decimals.

### Definition of Done
- [ ] Baseline trains end-to-end on the full feature store in < 10 minutes on a laptop.
- [ ] Macro-F1 on the held-out test set is documented and committed.
- [ ] Evaluation report is rendered as Markdown and stored next to the model artifact.
- [ ] Inference API can load the registered baseline by name and return predictions.
- [ ] Re-running the trainer with the same feature store version and same config produces a byte-identical model artifact.

---

## Milestone 4 — Transformer models

### Objective
Add a DistilBERT-based classifier behind the same `Model` protocol. The downstream system does not need to know which model is loaded.

### Deliverables
- `chopcast.models.transformer` — DistilBERT fine-tuning.
- Tokenization pipeline that handles PIREP-specific truncation.
- GPU-optional training (works on CPU for small datasets; uses GPU when available).
- Comparison report: baseline vs. transformer on the same split.
- Model card for each promoted transformer version.

### Required modules
- `chopcast.models.protocol` — `Model` Protocol with `predict`, `predict_proba`, `feature_version`.
- `chopcast.models.baseline_sklearn` — implementation of the protocol.
- `chopcast.models.transformer_distilbert` — implementation of the protocol.
- `chopcast.training.transformer_trainer` — HuggingFace `Trainer` wrapper.
- `chopcast.evaluation.compare` — A/B report between two model versions.

### Tests
- `test_protocol.py`: a stub model satisfying the protocol can be substituted in any test.
- `test_transformer.py`: trains for 1 step on synthetic data, saves, reloads, predicts.
- `test_compare.py`: produces a valid comparison report from two registry entries.

### Definition of Done
- [ ] Transformer model implements the same `Model` protocol as the baseline.
- [ ] Switching the inference API from baseline to transformer requires only a config change.
- [ ] Comparison report is rendered next to both model versions.
- [ ] If the transformer does not beat the baseline, the result is documented (negative result is acceptable).
- [ ] All tests in M3 still pass without modification.

---

## Milestone 5 — Geospatial intelligence

### Objective
Make the data visible and the predictions auditable. The map is a debugging tool first and a presentation tool second.

### Deliverables
- Folium map with severity-colored markers, time slider, altitude filter, aircraft-type filter.
- Hexbin density map for spatiotemporal analysis.
- "Suspicious coordinates" detector: flags points in impossible locations (over poles, far from any flight route) for manual review.
- Side-by-side view: actual label vs. predicted label for any report.

### Required modules
- `chopcast.map.folium_app` — interactive map generator.
- `chopcast.map.filters` — query builders for the feature store.
- `chopcast.map.density` — hexbin / kernel density.
- `chopcast.map.validation` — sanity checks on coordinates and altitudes.

### Tests
- `test_map_filters.py`: filter combinations return the expected rows.
- `test_map_validation.py`: known-bad coordinates are flagged.
- Smoke test: map HTML renders without error on a small dataset.

### Definition of Done
- [ ] `chopcast-map` CLI generates a static HTML file from the registry's latest model + feature store.
- [ ] At least one manual session validates 50 random reports against their plotted location.
- [ ] Filters for severity, altitude band, aircraft type, and time range all work.
- [ ] Suspicious-coordinate flags are reviewable from the CLI.

---

## Milestone 6 — Weather fusion

### Objective
Connect each PIREP to a nearby METAR and extract weather features. Test whether those features improve the classifier.

### Deliverables
- METAR fetcher with caching.
- Spatial-temporal matcher: nearest station within distance and time bounds.
- Weather feature extractor: wind speed/direction, temperature, pressure, visibility.
- Enriched feature store with weather columns.
- A/B experiment: classifier with weather features vs. without.

### Required modules
- `chopcast.weather.providers.metar` — provider client.
- `chopcast.weather.matcher` — spatial-temporal join.
- `chopcast.weather.features` — extraction.
- `chopcast.weather.cache` — local Parquet cache of METAR observations.

### Tests
- `test_matcher.py`: known (lat, lon, time) finds the expected station within the configured bound.
- `test_matcher_bounds.py`: out-of-bound requests produce `weather_status="no_match"`, not exceptions.
- `test_features.py`: known METAR string produces expected features.
- Manual validation: a sample of 20 matches are spot-checked against the source METAR.

### Definition of Done
- [ ] Every report in the enriched store has a `weather_status` field (`matched`, `no_match`, `quarantined`).
- [ ] Distance and time-delta distributions are documented.
- [ ] Documented limitation: METAR is surface-level, so flight-level turbulence may not be well-explained.
- [ ] The A/B experiment produces a report comparing the two model versions.

---

## Milestone 7 — Deployment & monitoring

### Objective
Run the system unattended, observe its behavior, and recover from failure.

### Deliverables
- Inference API (FastAPI) with health check, readiness check, and `/predict` endpoint.
- Containerized deployment (Dockerfile + docker-compose for local).
- Prometheus metrics: requests/sec, latency p50/p95/p99, prediction-class distribution.
- Alerting rules: collector staleness, dedup-rate anomaly, model drift (predicted-class distribution shift).
- Backup automation: daily `sqlite3 .backup` to a separate volume, retained 30 days.
- Runbook for common failures.

### Required modules
- `chopcast.api.app` — FastAPI app.
- `chopcast.api.schemas` — Pydantic request/response models.
- `chopcast.monitoring.metrics` — Prometheus exporters.
- `chopcast.monitoring.drift` — class-distribution drift detector.
- `scripts/backup.sh` (or `.ps1`).

### Tests
- `test_api.py`: `/predict` round-trip; `/health`; `/ready`.
- `test_drift.py`: a synthetic distribution shift triggers the alarm.
- `test_backup.py`: backup can be restored to a clean DB.

### Definition of Done
- [ ] `docker compose up` brings the API, collector, and monitoring stack online.
- [ ] API survives a model reload (no downtime).
- [ ] Backup is automated and a restore drill has been performed.
- [ ] Runbook covers: collector crash, AWC rate limit, schema change, model regression, DB corruption.
- [ ] Drift detection is exercised against a synthetic shift and produces an alert.

---

## Sequencing notes

- M0 unblocks everyone. It must be done first.
- M1 unblocks M2 (you can't parse what you haven't stored).
- M2 unblocks M3 (you can't train on unparsed data).
- M3 and M4 are sequential only because the comparison report is more meaningful once a baseline exists.
- M5, M6, M7 are partially independent: M5 needs the registry, M6 needs M2's feature builder, M7 needs the API.
- The critical path is M0 → M1 → M2 → M3. Everything after that is parallelizable across team members.
