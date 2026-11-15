# ChopCast — Issue Register

**Created:** 2026-11-14
**Basis:** the read-only onboarding review at `main` @ `29fb780` (see `docs/ONBOARDING.md`). Live artifacts inspected read-only: `data/raw/pireps.db`, `models/registry/registry.db`, `models/registry/baseline-v1_test/*`.
**Scope:** every problem, inconsistency, risk, and open question found — headline decisions plus the smaller drifts. Nothing here is fixed. Every item is **Open**.

> Naming: "legacy DB" = the current `data/raw/pireps.db`; "target schema" = `chopcast/storage/schema.py::SCHEMA` + `MIGRATIONS`; "onboarding doc" = `docs/ONBOARDING.md`.
---

## Summary

| ID | Title | Category | Severity | Status |
|---|---|---|---|---|
| ISS-001 | Canonical training path: DB orchestrator vs JSONL trainer | Decision needed | Critical | Open |
| ISS-002 | Raw DB strategy: migrate in place vs new store from legacy source | Decision needed | Critical | Open |
| ISS-003 | `turbulence` / `turbulence_2`: one combined label vs separate targets | Decision needed | High | Open |
| ISS-004 | Console scripts vs `chopcast` subcommands | Decision needed | High | Open |
| ISS-005 | Registry DB carries the raw-data schema | Decision needed | High | Open |
| ISS-006 | Minimum supported Python version | Decision needed | Medium | Open |
| ISS-007 | Model artifact location and relative `artifact_path` | Decision needed | High | Open |
| ISS-008 | Parser tokenizer fails on the real AWC text format | Bug | Critical | Open |
| ISS-009 | `process()` discards the DB turbulence columns | Bug | High | Open |
| ISS-010 | Migration-3 `trainable` has no `report_type`, but training filters on it | Bug | High | Open |
| ISS-011 | `apply_migrations()` cannot upgrade the legacy DB | Bug | Critical | Open |
| ISS-012 | Migration-3 `CREATE VIEW IF NOT EXISTS` cannot replace legacy views | Bug | High | Open |
| ISS-013 | Legacy DB lacks `rejected`, `runs` (new shape), `source_url`, `source_etag` | Bug | High | Open |
| ISS-014 | `run_training()` transformer branch treats a `TransformerRun` as a model | Bug | High | Open |
| ISS-015 | `chopcast-train run` uses nonexistent `cfg.split` | Bug | High | Open |
| ISS-016 | `chopcast map` raises `NameError: Path` | Bug | High | Open |
| ISS-017 | `generate_map()` reads nonexistent `severity_label` | Bug | High | Open |
| ISS-018 | `generate_map()` centroid, falsy coordinates, `raw_text`, `zip` hazards | Bug | Medium | Open |
| ISS-019 | `compare_models()` divides a `str` by a `Path` | Bug | High | Open |
| ISS-020 | `compare_models()` passes `sqlite3.Row` to `process()` | Bug | High | Open |
| ISS-021 | `weather/cache.py` is a syntax error and uses a missing `Paths` property | Bug | High | Open |
| ISS-022 | `weather/providers/metar.py` literal escapes + unpackaged subpackage | Bug | High | Open |
| ISS-023 | `WeatherFeatures` has no `to_dict()`, but training calls it | Bug | High | Open |
| ISS-024 | Weather matcher is always given an empty observation list | Bug | High | Open |
| ISS-025 | Parser stamps today's date onto `HHMM` times | Bug | High | Open |
| ISS-026 | `_parse_location()` placeholder and index handling | Bug | Medium | Open |
| ISS-027 | `/RM` values containing slashes are truncated by the tokenizer | Bug | Medium | Open |
| ISS-028 | Legacy migration drops `turbulence_2`/`_type`/`_freq` | Bug | High | Open |
| ISS-029 | Duplicate model registration raises an uncaught `IntegrityError` | Bug | Low | Open |
| ISS-030 | `BaselineSklearn.predict_proba()` is inconsistent and re-vectorises | Bug | Medium | Open |
| ISS-031 | Parser raises `ValueError`, docs promise `ParseError` | Bug | Low | Open |
| ISS-032 | `cleaner.preserve_remarks_tb_mentions` is configured but unused | Bug | Medium | Open |
| ISS-033 | Frozen `PipelineDeps` mutated via `object.__setattr__` | Bug | Medium | Open |
| ISS-034 | `build_deps()` has no way to inject a weather matcher | Bug | Medium | Open |
| ISS-035 | No label-distribution / data-quality guard before training | Bug | High | Open |
| ISS-036 | `.env` is documented everywhere and read nowhere | Inconsistency | High | Open |
| ISS-037 | `Settings.load()` resolves `configs/` relative to CWD | Inconsistency | High | Open |
| ISS-038 | Split manifests are written to different places per path | Inconsistency | Medium | Open |
| ISS-039 | Default `user_agent` is the placeholder `contact@example.com` | Inconsistency | Medium | Open |
| ISS-040 | `requirements.txt` does not reflect `pyproject.toml` | Inconsistency | Medium | Open |
| ISS-041 | `database.foreign_keys` / `busy_timeout_ms` are never applied | Inconsistency | Low | Open |
| ISS-042 | Env overlay supports only one nesting level | Inconsistency | Low | Open |
| ISS-043 | Macro-F1 is diluted by classes with zero support | Inconsistency | Medium | Open |
| ISS-044 | ADR-0006 sync-folder warning is not implemented | Inconsistency | Medium | Open |
| ISS-045 | `lineage.json` omits hashes and hardcodes commit/config version | Inconsistency | Low | Open |
| ISS-046 | Two independent model-comparison implementations | Inconsistency | Low | Open |
| ISS-047 | Registry/artifact metadata is muddled (both models `baseline`, no promotions) | Tech debt | High | Open |
| ISS-048 | Config sections with no implementation (`api`, `monitoring`, imbalance, regression gate) | Tech debt | Medium | Open |
| ISS-049 | Optional dependencies for features that do not exist | Tech debt | Low | Open |
| ISS-050 | Dead code and duplicate logger assignment | Tech debt | Low | Open |
| ISS-051 | Untracked root scripts (`test_pipeline.py`, `trace_pipeline.py`, …) | Tech debt | Medium | Open |
| ISS-052 | No `CHANGELOG.md` | Tech debt | Low | Open |
| ISS-053 | Committed notebook of unknown provenance | Tech debt | Low | Open |
| ISS-054 | `.gitignore` has a BOM, duplicates, and ignores `models/manifest.json` | Tech debt | Low | Open |
| ISS-055 | Coverage config omits `chopcast/__main__.py`, which does not exist | Tech debt | Low | Open |
| ISS-056 | `chopcast/logging.py` is untracked — clean clone cannot import | Packaging | Critical | Open |
| ISS-057 | `map/`, `weather/`, `weather/providers/` have no `__init__.py` | Packaging | High | Open |
| ISS-058 | Four console scripts point at missing modules (`parse`, `eval`, `registry`, `map`) | Packaging | High | Open |
| ISS-059 | No CI workflow | Packaging | High | Open |
| ISS-060 | No Dockerfile / compose despite M7 and docs | Packaging | Medium | Open |
| ISS-061 | No DVC despite ADR-0002 / README | Packaging | Medium | Open |
| ISS-062 | No pre-commit configuration despite ADR-0002 | Packaging | Low | Open |
| ISS-063 | M0 "definition of done" is unchecked; installability unverified | Packaging | Medium | Open |
| ISS-064 | README still describes the pre-M0 three-file prototype | Docs | High | Open |
| ISS-065 | `CLAUDE.md` is stale and contradicts the package | Docs | High | Open |
| ISS-066 | Architecture docs reference modules that do not exist | Docs | High | Open |
| ISS-067 | `TESTING.md` describes a test suite that is not there | Docs | High | Open |
| ISS-068 | README command table advertises broken/missing commands | Docs | Medium | Open |
| ISS-069 | Wrong repository URL in deploy docs and unit files | Docs | Low | Open |
| ISS-070 | ADRs cite files/tests that were never created | Docs | Low | Open |
| ISS-071 | No tests for map, CLIs, orchestrators, or weather | Missing tests | High | Open |
| ISS-072 | No golden corpus / parser conformance test | Missing tests | High | Open |
| ISS-073 | No import-boundary lint test | Missing tests | Medium | Open |
| ISS-074 | No call-graph leakage regression test | Missing tests | Medium | Open |
| ISS-075 | No metric-regression gate implementation | Missing tests | Medium | Open |
| ISS-076 | 80% coverage gate is aspirational and unverified | Missing tests | Medium | Open |

| ISS-077 | Operational data lives under OneDrive sync | Security | High | Open |
| ISS-078 | Joblib artifacts are loaded by path with no integrity check | Security | Medium | Open |
| ISS-079 | `raw_json` stores every source column; no retention/PII review | Security | Low | Open |
| ISS-080 | Collector iterates rows with `DataFrame.iterrows()` | Performance | Low | Open |
| ISS-081 | Evaluation uses one `IN (...)` clause sized by the test split | Performance | Medium | Open |
| ISS-082 | Map loads the whole view and builds a `pandas.Series` per row | Performance | Low | Open |
| ISS-083 | No configured map output location or map-run metadata | Tech debt | Medium | Open |
| ISS-084 | Generated folium maps depend on CDN assets and online tiles | Inconsistency | Medium | Open |
| ISS-085 | No training/evaluation run history; only successes are inferable | Tech debt | High | Open |
| ISS-086 | Collector logs go to two paths/formats and carry no run id | Inconsistency | Low | Open |
| ISS-087 | Evaluation metrics are duplicated three ways with no schema/version | Inconsistency | Low | Open |

**Counts:** Critical 5 · High 35 · Medium 27 · Low 20 · **Total 87**.

---

## Decision needed

### ISS-001 — Canonical training path: DB orchestrator vs JSONL trainer

- **Category:** Decision needed
- **Severity:** Critical
- **Evidence:** Three competing paths exist.
  - `chopcast train run` → `chopcast/cli.py::train_run` → `chopcast/training/orchestrator.py::run_training` (reads `trainable` directly, writes the artifact, lineage, metrics, and registry row).
  - `chopcast-train run` → `chopcast/training/cli.py::run` → `train_baseline()` / `train_transformer()` (reads a JSONL feature file, writes `report.md`/`report.json`, registers a model, but no lineage).
  - Untracked root scripts `test_pipeline.py`, `test_transformer.py`, `trace_pipeline.py` wire a third variant.
  - Only path 1 has actually produced the artifacts in `models/registry/` (both models dated 2026-10-17).
- **Why it matters:** the paths differ in input source, split handling, artifact layout, and lineage. Fixing a bug in one does not fix the others; "train the model" has three meanings. This blocks every training-related fix.
- **Options:**
  1. **DB-first (path 1) is canonical.** Fewer moving parts; keeps the current registry flow; no dataset artifact. Weak reproducibility: the training set is whatever is in SQLite when you run.
  2. **JSONL-first (path 2) is canonical.** Add a `chopcast features build` command, make path 1 a thin wrapper, and require a versioned feature file. Matches `docs/DATA_ENGINEERING.md` and the existence of `chopcast/data/feature_store.py`. More work: feature-build CLI, dataset version in lineage, split derived from the file.
  3. **Keep both roles split** (exploration vs release). Cheapest now; the duplication is already drifting (`run_training` writes lineage, `chopcast-train` does not).
  - **Recommendation: option 2**, staged. It is the only option consistent with ADR-0002/ADR-0004 (versioned, content-addressed datasets) and it makes metrics reproducible; option 1 can be a `--from-db` convenience mode during the transition. Choose option 1 only if the immediate goal is a demo and reproducibility is explicitly out of scope.
- **Proposed fix:** document the chosen path in an ADR; delete or alias the other; make both CLIs call one library entry point.
- **Dependencies:** ISS-008, ISS-009, ISS-014, ISS-015, ISS-038, ISS-047.
- **Status:** Open

### ISS-002 — Raw DB strategy: migrate in place vs new store from legacy source

- **Category:** Decision needed
- **Severity:** Critical
- **Evidence:** `scripts/migrate_legacy_db.py::migrate` defaults its destination to `paths.raw_db_path` — the same file it reads. It also opens the legacy DB read-only but then applies the new `MIGRATIONS` to the destination, which fails on legacy content (`duplicate column name: turbulence_2`, verified on a temp copy). The legacy DB has 3,525 rows (290 labelled) and no `schema_migrations`.
- **Why it matters:** the collector CLI (`chopcast-collector once|status`) opens `SqliteReportStore(paths.raw_db_path)` directly, so today the only DB with data is the one the code cannot open. Until this is decided, nothing can run against real data.
- **Options:**
  1. **New store at a non-synced root, legacy stays read-only as the migration source.** Fix `migrate()` to write to a distinct target, carry the extra turbulence columns, and verify counts. One-time copy of 3,525 rows. Matches ADR-0006. Cost: the migration script needs real work and a test.
  2. **Upgrade in place** with legacy-aware, idempotent migrations (`ADD COLUMN` only when absent; `DROP/CREATE VIEW`). No data move, but preserves the OneDrive/WAL risk and forces the migration chain to encode historical shapes forever.
  3. **Start empty and abandon the legacy rows.** Cheapest schema-wise, but discards 290 labels and 2,928 AIREPs that cannot be re-collected (~90-minute cache).
  - **Recommendation: option 1.** It is the only one that both keeps the data and gives a schema that matches `SCHEMA`. Option 3 is defensible only if the 290 labels are considered low quality — which ISS-008 suggests, but they are still the only labels that exist.
- **Proposed fix:** separate source/target explicitly in `migrate()`, add a `--target` argument, make migrations legacy-tolerant or guarantee a fresh target, add a round-trip test.
- **Dependencies:** ISS-011, ISS-012, ISS-013, ISS-028, ISS-077.
- **Status:** Open

### ISS-003 — `turbulence` / `turbulence_2`: one combined label vs separate targets

- **Category:** Decision needed
- **Severity:** High
- **Evidence:** Three different behaviours coexist.
  - Migration-3 `trainable`: `WHERE turbulence IS NOT NULL OR turbulence_2 IS NOT NULL` (`storage/migrations.py:90-95`).
  - The live legacy `trainable`: `WHERE ... AND turbulence IS NOT NULL` only.
  - `process()` uses neither column; it reads only `parsed.turbulence` from the text (`processing/pipeline.py:140`).
  - Live data: `turbulence_2` has 14 non-null values (`LGT` 1, `MOD` 7, `NEG` 6) out of 3,525.
- **Why it matters:** the label definition is the target variable. Right now the view says "either layer", the pipeline says "text only", and the legacy view says "first layer only". Any metric depends on which one you meant.
- **Options:**
  1. **Primary from `turbulence`, fall back to `turbulence_2` when the primary is NULL.** Uses the 14 extra rows; preserves the two-block semantics; needs a `label_source` column to audit. Cost: mixes two observations into one target.
  2. **Separate models/targets per layer.** Cleanest semantically. Not viable at 14 rows; would need years of collection.
  3. **Ignore `turbulence_2`** (keep the legacy view semantics). Simplest and consistent with the only data that exists; requires changing the v3 view and the docs.
  - **Recommendation: option 1**, with `label_source ∈ {primary, secondary}` recorded on `FeatureRow` and in the split manifest. It costs one column and makes option 2 possible later. If the team wants minimum change now, option 3 plus a doc correction is acceptable.
- **Proposed fix:** decide, then make the view, `process()`, and the docs agree; add a test for a secondary-only row.
- **Dependencies:** ISS-002, ISS-009, ISS-010, ISS-028.
- **Status:** Open

### ISS-004 — Console scripts vs `chopcast` subcommands

- **Category:** Decision needed
- **Severity:** High
- **Evidence:** `pyproject.toml:66-73` declares seven entry points. `chopcast/cli.py` re-implements `map`, `train run`, and `eval compare` as subcommands. `chopcast evaluation.cli`, `registry.cli`, `map.cli`, and `parser.cli` do not exist as files. README advertises the standalone commands (`README.md:91-104`); `deploy/` only uses `chopcast-collector` and `chopcast config`.
- **Why it matters:** users get `ModuleNotFoundError` for four advertised commands, while the working implementations are hidden under `chopcast`. It also splits documentation and tests.
- **Options:**
  1. **Keep the standalone scripts and write the missing `cli.py` modules.** Matches README and conventional packaging; four new thin modules plus tests.
  2. **Drop the extra scripts; keep `chopcast` + `chopcast-collector`.** Smallest surface; README and `deploy/` need edits; scripts become breaking changes.
  3. **Standalone scripts as one-line aliases** that call `chopcast <group>` (`def main(): root(...)`). Keeps both interfaces without duplication; still needs the four module files.
  - **Recommendation: option 3.** It preserves the documented commands, keeps a single implementation, and is cheap to test.
- **Proposed fix:** add the four thin modules (or remove the entry points), update README, add a CLI smoke test.
- **Dependencies:** ISS-016, ISS-019, ISS-058, ISS-068.
- **Status:** Open

### ISS-005 — Registry DB carries the raw-data schema

- **Category:** Decision needed
- **Severity:** High
- **Evidence:** `chopcast/registry/store.py:113` calls `apply_migrations(self._conn, MIGRATIONS)` in `SqliteModelRegistry.__init__`, then creates `REGISTRY_SCHEMA`. Read-only inspection of `models/registry/registry.db` shows `reports` (0 rows), views `pireps`/`trainable`/`wx_altitude`, and `schema_migrations` v1–v3 alongside `models`/`promotions`.
- **Why it matters:** two databases pretend to be the same kind of store; a careless query can write raw rows into the registry; backups and migrations grow unrelated tables; a registry schema change can be blocked by data-store migrations. It also makes the registry file larger and harder to reason about.
- **Options:**
  1. **Stop applying `MIGRATIONS` in the registry**; keep `REGISTRY_SCHEMA` (plus a dedicated registry migration list). Clean separation. Cost: a one-time cleanup of existing registry DBs (drop stray tables/views) and a migration story for the registry itself.
  2. **Keep it and document it.** Cheapest, but the coupling remains and will surprise the next contributor.
  3. **Merge into one DB with schemas/table prefixes.** Bigger refactor; contradicts ADR-0002's separate lifecycles.
  - **Recommendation: option 1.** The separation is already the stated design; the code just violates it.
- **Proposed fix:** remove the `MIGRATIONS` import/call from `SqliteModelRegistry`; add `REGISTRY_MIGRATIONS`; write a cleanup step for existing files.
- **Dependencies:** ISS-002, ISS-047.
- **Status:** Open

### ISS-006 — Minimum supported Python version

- **Category:** Decision needed
- **Severity:** Medium
- **Evidence:** `pyproject.toml:10` declares `requires-python = ">=3.11"`, `mypy python_version = "3.11"`, `ruff target-version = "py311"`. Local bytecode is `cpython-314` (`tests/**/__pycache__/*.cpython-314*`). `chopcast/processing/pipeline.py:_parse_obs_time` relies on `datetime.fromisoformat` accepting `Z` (3.11+). `deploy/bootstrap.sh` installs `python3.11` explicitly. No CI matrix exists to prove either end.
- **Why it matters:** "supported" is undefined. Code may work on 3.14 locally and break on the documented 3.11 deployment (or vice versa), and the docs claim 3.11 while nothing tests it.
- **Options:**
  1. **Keep floor 3.11, add an upper bound (`<3.14`) and a CI matrix 3.11/3.12.** Predictable; slightly conservative.
  2. **Floor 3.11, no upper bound.** Maximum flexibility; you inherit breakage from future interpreters silently.
  3. **Target 3.13/3.14 only.** Simple locally; breaks `bootstrap.sh` and the documented install.
  - **Recommendation: option 1** for now. It matches the deployed 3.11 and the local 3.14 without promising untested versions. Revisit once a CI matrix exists.
- **Proposed fix:** write the decision into `pyproject.toml`/`docs/CONFIGURATION.md`, add the CI matrix, align `bootstrap.sh`.
- **Dependencies:** ISS-059.
- **Status:** Open

### ISS-007 — Model artifact location and relative `artifact_path`

- **Category:** Decision needed
- **Severity:** High
- **Evidence:** `PathsConfig.models_dir` defaults to `models/registry`, so `run_training()` writes artifacts to `models/registry/<kind>-<version>/` next to `registry.db` (`training/orchestrator.py:157`). The registry stores `str(artifact_path)` verbatim; live rows contain `models\registry\baseline-v1_test` — relative, CWD-dependent. The evaluation and map loaders do `Path(record.artifact_path)` (`evaluation/orchestrator.py:30`, `map/folium_app.py:69`).
- **Why it matters:** loading a registered model depends on the process CWD; moving the repo breaks every artifact; artifacts and the registry share a directory, so cleanup of one risks the other. Any layout change requires migrating both the directories and the DB rows.
- **Options:**
  1. **Artifacts in `models/artifacts/<kind>-<version>/`, registry DB alone in `models/registry/`, absolute paths stored.** Clean separation; requires moving two directories, rewriting two rows, and updating loaders. Compatible with a future artifact store.
  2. **Keep the current location but store absolute paths.** Minimal move; still commingled.
  3. **Store a relative artifact ID and resolve it through `Paths`** (`paths.models_dir / artifact_id`). Portable across machines; every loader must accept `Paths` instead of `Path`, so more call-site churn.
  - **Recommendation: option 1 for layout + store the relative ID as a second column** (`artifact_id`) while keeping an absolute `artifact_path` for compatibility. Migration impact is bounded: two rows, two directories, three loaders (`BaselineSklearn.load`, map, eval). Do it together with ISS-047.
- **Proposed fix:** decide layout; add a registry migration; update `PathsConfig`, writers, and loaders in one change.
- **Dependencies:** ISS-047, ISS-005.
- **Status:** Open

---

## Bug

### ISS-008 — Parser tokenizer fails on the real AWC text format

- **Category:** Bug
- **Severity:** Critical
- **Evidence:** `chopcast/parser/pirep.py::_tokenize` splits on whitespace-before-slash (`re.split(r"\s+/", tail)`). A real row from `data/raw/pireps.db`:
  `"MLI UA /OV MLI270020/TM 1756/FL170/TP CRJ2/TB CONS MOD "` →
  `['MLI', '/UA', '/OV', 'MLI270020/TM 1756/FL170/TP CRJ2/TB CONS MOD']`; `location` swallows the rest, `turbulence`/`flight_level`/`aircraft_type`/`obs_time` are all `None`.
  Across all 290 rows in `trainable`: **285 parse to `turbulence = None`**; resulting labels are 288 `None`, 1 `Light`, 1 `Moderate`.
  The spaced README example (`UA /OV SFO /TM 1425 ...`) parses correctly, which is why tests pass (`tests/unit/parser/test_pirep.py`).
- **Why it matters:** the label is silently discarded and replaced by `default_label="None"` in `process()`. Every downstream metric is measured against a near-constant label. This is the root cause of ISS-043/ISS-047's degenerate artifact.
- **Proposed fix:** tokenise on every `/XX` field key regardless of preceding whitespace (regex over known keys), keep `/RM` as a remainder field, and add a fixture from a real AWC row.
- **Dependencies:** ISS-009, ISS-025, ISS-026, ISS-027, ISS-035, ISS-072.
- **Status:** Open

### ISS-009 — `process()` discards the DB turbulence columns

- **Category:** Bug
- **Severity:** High
- **Evidence:** `chopcast/processing/pipeline.py:138-146`:
  `turbulence = parsed.turbulence if parsed.turbulence is not None else None` — the comment above says "otherwise fall back to whatever the raw row carried", but no fallback exists. `RawReport` (`pipeline.py:47-70`) does not even expose `turbulence`/`turbulence_2`; `_RowAdapter` (`:184-245`) does not read them.
- **Why it matters:** even after ISS-008 is fixed, rows whose label exists only in the column (e.g. collector-populated `turbulence_intensity` with a sparse `/TB`) will be labelled `None`. It also makes the view's `WHERE turbulence IS NOT NULL` filter meaningless for labelling.
- **Proposed fix:** extend `RawReport`/`_RowAdapter` with `turbulence`/`turbulence_2`, prefer the parsed value, fall back to columns, record `label_source`.
- **Dependencies:** ISS-003, ISS-008.
- **Status:** Open

### ISS-010 — Migration-3 `trainable` has no `report_type`, but training filters on it

- **Category:** Bug
- **Severity:** High
- **Evidence:** `chopcast/storage/migrations.py:90-95` projects `hash, obs_time, raw_text, turbulence, turbulence_2, turbulence_type, turbulence_freq, aircraft, lat, lon, altitude` — **no `report_type`**. `training/orchestrator.py:62` runs `SELECT * FROM trainable WHERE report_type = 'PIREP' OR report_type = 'Urgent PIREP'`. The live legacy view happens to be `SELECT *`, so it works today; a fresh DB built by the migrations would raise `no such column: report_type`.
- **Why it matters:** the code only works against the legacy view. Once ISS-002 is resolved with a fresh store, training breaks immediately — a latent failure hidden by the existing DB.
- **Proposed fix:** add `report_type` to the projection (or drop the redundant filter, since `trainable` is already PIREP-only).
- **Dependencies:** ISS-002, ISS-012.
- **Status:** Open

### ISS-011 — `apply_migrations()` cannot upgrade the legacy DB

- **Category:** Bug
- **Severity:** Critical
- **Evidence:** `chopcast/storage/migrations.py:69-71` unconditionally runs `ALTER TABLE reports ADD COLUMN turbulence_2/...`. The legacy DB already has those columns. Running `apply_migrations()` on a temp copy of `data/raw/pireps.db` raised `sqlite3.OperationalError: duplicate column name: turbulence_2`. `SqliteReportStore.__init__` (`storage/schema.py:215`) calls this before `SCHEMA`, so `chopcast-collector once`/`status` fail on the only DB with data.
- **Why it matters:** total blocker for collection and for any run against real data.
- **Proposed fix:** make migrations version-gated per column (`PRAGMA table_info` guard) or target a guaranteed-fresh DB (ISS-002). Add a test that runs the chain against a legacy fixture.
- **Dependencies:** ISS-002, ISS-013, ISS-028.
- **Status:** Open

### ISS-012 — Migration-3 `CREATE VIEW IF NOT EXISTS` cannot replace legacy views

- **Category:** Bug
- **Severity:** High
- **Evidence:** `migrations.py:84,90,99` all use `CREATE VIEW IF NOT EXISTS`. The legacy DB already has a different `trainable` (and no `pireps`/`wx_altitude`). Applying the migrations leaves the legacy definition in place while recording v3 as applied. `schema_migrations` is absent from the legacy DB, so the code believes v1–v3 are new.
- **Why it matters:** the DB reports "migrated" while still having the old view semantics (no `turbulence_2`-only rows, `SELECT *`). Silent divergence.
- **Proposed fix:** version the views explicitly (`DROP VIEW IF EXISTS` then `CREATE VIEW`) in a new migration, and never edit shipped migrations.
- **Dependencies:** ISS-002, ISS-010.
- **Status:** Open

### ISS-013 — Legacy DB lacks `rejected`, `runs` (new shape), `source_url`, `source_etag`

- **Category:** Bug
- **Severity:** High
- **Evidence:** Legacy `reports` columns: `hash, fetched_at, obs_time, report_type, raw_text, turbulence, turbulence_2, turbulence_type, turbulence_freq, aircraft, lat, lon, altitude, raw_json` — no `source_url`/`source_etag` (both `NOT NULL` in `SCHEMA`). Legacy `runs`: `(id, ran_at, rows_seen, inserted, skipped, status)` vs `SCHEMA`'s `(started_at, finished_at, status, rows_seen, rows_inserted, rows_skipped, rows_rejected, error)`. There is no `rejected` table.
- **Why it matters:** `SqliteReportStore.insert_report` writes `source_url`; `finish_run` updates `started_at`/`rows_inserted`; `chopcast-collector rejected` queries `rejected`. All three fail on the legacy DB even if ISS-011 were fixed. `last_runs()` reads columns that do not exist.
- **Proposed fix:** handle as part of the ISS-002 migration (create target schema correctly, map old `runs` rows, create `rejected`), with a test on a legacy fixture.
- **Dependencies:** ISS-002, ISS-011.
- **Status:** Open

### ISS-014 — `run_training()` transformer branch treats a `TransformerRun` as a model

- **Category:** Bug
- **Severity:** High
- **Evidence:** `training/orchestrator.py:119-133` sets `model = train_transformer(...)`; `train_transformer` returns `TransformerRun` (`training/transformer_trainer.py:36,74,130`). Lines `145` (`model.predict`), `151` (`model.classes`), `158` (`model.save`) then fail. The `X_test` built earlier is also unused for the transformer.
- **Why it matters:** the documented `--kind transformer` path cannot complete; the failure occurs after expensive training.
- **Proposed fix:** use `run.model` / `run.split` / `run.evaluation` like `training/cli.py` does, or return the model and keep split/evaluation in the caller.
- **Dependencies:** ISS-001.
- **Status:** Open

### ISS-015 — `chopcast-train run` uses nonexistent `cfg.split`

- **Category:** Bug
- **Severity:** High
- **Evidence:** `training/cli.py:105` and `:119`: `split_cfg=cfg.split`. `Settings` (`chopcast/config.py:305-334`) has `training.default_split`; no `split` attribute. `cfg = settings` at `:90`.
- **Why it matters:** the standalone trainer fails before touching data. Combined with ISS-014, neither transformer entry point works.
- **Proposed fix:** `split_cfg=settings.training.default_split`.
- **Dependencies:** ISS-001.
- **Status:** Open

### ISS-016 — `chopcast map` raises `NameError: Path`

- **Category:** Bug
- **Severity:** High
- **Evidence:** `chopcast/cli.py:44` calls `Path(output)`; `Path` is never imported in `cli.py` (imports at `:11-19` cover `sys`, `Any`, `NoReturn`, `click`, `yaml`, `Settings`, errors, logging).
- **Why it matters:** the root `map` subcommand cannot run at all.
- **Proposed fix:** import `Path` from `pathlib`.
- **Dependencies:** ISS-004.
- **Status:** Open

### ISS-017 — `generate_map()` reads nonexistent `severity_label`

- **Category:** Bug
- **Severity:** High
- **Evidence:** `map/folium_app.py:62` `labels = [row["severity_label"] for row in rows]`; `:111` reads it again in the popup. Live `trainable` columns have no `severity_label` (verified with `PRAGMA table_info(trainable)`); the label is derived by `process()`.
- **Why it matters:** the default (ground-truth) map always fails with `KeyError`; the prediction mode only works if you avoid line 62, which requires a model id.
- **Proposed fix:** run `process()` for rows (as the `model_id` branch already does) or project a derived label into the query.
- **Dependencies:** ISS-003, ISS-009.
- **Status:** Open

### ISS-018 — `generate_map()` centroid, falsy coordinates, `raw_text`, `zip` hazards

- **Category:** Bug
- **Severity:** Medium
- **Evidence:** `folium_app.py:87-88`: `sum(r["lat"] for r in rows if r["lat"]) / len(rows)` — missing rows are excluded from the numerator but counted in the denominator; `0.0` is treated as missing. `:122` `row["raw_text"][:100]` raises `TypeError` when `raw_text` is NULL. `:98` `zip(rows, labels)` silently truncates if lengths diverge (they can, when `process()` drops rows). `:23` `log = get_logger(__name__) if 'get_logger' in globals() else None` is dead defensive code (`get_logger` is never imported).
- **Why it matters:** wrong map centre, crashes on NULL text, and silently missed markers.
- **Proposed fix:** compute the centroid over valid coordinates only and guard the empty case; coalesce text; assert equal lengths.
- **Dependencies:** ISS-017.
- **Status:** Open

### ISS-019 — `compare_models()` divides a `str` by a `Path`

- **Category:** Bug
- **Severity:** High
- **Evidence:** `evaluation/orchestrator.py:60`: `paths.runs_dir / f"split-{rec_a.model_version}.json"`. `Paths.runs_dir` is a `str` (`paths.py:41`); only `runs_dir_path` is a `Path`.
- **Why it matters:** `chopcast eval compare` fails immediately.
- **Proposed fix:** use `paths.runs_dir_path`.
- **Dependencies:** ISS-004, ISS-038.
- **Status:** Open

### ISS-020 — `compare_models()` passes `sqlite3.Row` to `process()`

- **Category:** Bug
- **Severity:** High
- **Evidence:** `evaluation/orchestrator.py:83` calls `process(row, deps)` where `row` is a `sqlite3.Row` (`:67-74`). `process()` only adapts `dict` (`pipeline.py:120`); `_RowAdapter` is not applied. `sqlite3.Row` has no `.hash` attribute → `AttributeError`.
- **Why it matters:** comparison fails even after ISS-019.
- **Proposed fix:** `process(dict(row), deps)` or make `process()` accept mapping-like objects.
- **Dependencies:** ISS-019.
- **Status:** Open

### ISS-021 — `weather/cache.py` is a syntax error and uses a missing `Paths` property

- **Category:** Bug
- **Severity:** High
- **Evidence:** `weather/cache.py:12-13,19-20,28-29,40-41` contain literal `\"\"\"` (backslash + quotes) instead of docstring delimiters → `SyntaxError` on import. `:16` uses `settings.to_paths().weather_cache_path`; `Paths` defines no such property (`paths.py:34-43`, accessors `:53-91`), so it would fail even after the syntax fix.
- **Why it matters:** any import of `chopcast.weather.cache` (including a test collection sweep) fails; the feature is dead code.
- **Proposed fix:** correct the docstrings; source the cache path from `settings.weather.cache.path` or add a `Paths` accessor.
- **Dependencies:** ISS-022, ISS-057.
- **Status:** Open

### ISS-022 — `weather/providers/metar.py` literal escapes + unpackaged subpackage

- **Category:** Bug
- **Severity:** High
- **Evidence:** `weather/providers/metar.py` contains the same literal `\"\"\"` pattern (observed in review). `chopcast/weather/providers/` has no `__init__.py` and `chopcast/weather/` has none either, so `[tool.setuptools.packages.find]` (`pyproject.toml:79-84`) will not ship them.
- **Why it matters:** the METAR provider cannot be imported from an installed package, and fails from source too.
- **Proposed fix:** fix the quotes, add the two `__init__.py` files, add an import smoke test.
- **Dependencies:** ISS-057.
- **Status:** Open

### ISS-023 — `WeatherFeatures` has no `to_dict()`, but training calls it

- **Category:** Bug
- **Severity:** High
- **Evidence:** `training/orchestrator.py:104-107` builds `f.weather.to_dict()`. `weather/features.py` defines only the five fields and no methods (`:5-16`). `FeatureRow.to_dict()` (`processing/features.py:43-66`) flattens weather manually instead of delegating.
- **Why it matters:** `run_training(use_weather=True)` crashes at feature preparation; the weather experiment cannot run.
- **Proposed fix:** add `to_dict()` to `WeatherFeatures` (or drop the call and flatten consistently).
- **Dependencies:** ISS-024, ISS-048.
- **Status:** Open

### ISS-024 — Weather matcher is always given an empty observation list

- **Category:** Bug
- **Severity:** High
- **Evidence:** `pipeline.py:161-166` calls `deps.weather_matcher.find_nearest(raw.lat, raw.lon, raw.obs_time, [])` with a literal `[]`. `WeatherMatcher.find_nearest` (`weather/matcher.py:40-57`) iterates observations and returns `None` when the list is empty.
- **Why it matters:** even with weather enabled, every `FeatureRow.weather` is `None`; the weather branch is structurally inert.
- **Proposed fix:** pass observations (cache/window) into `process()`, or move matching out of the per-row pipeline into an enrichment step.
- **Dependencies:** ISS-021, ISS-022, ISS-023, ISS-034.
- **Status:** Open

### ISS-025 — Parser stamps today's date onto `HHMM` times

- **Category:** Bug
- **Severity:** High
- **Evidence:** `parser/pirep.py:169-171` builds `datetime(today.year, today.month, today.day, hh, mm, ss, ...)` using `datetime.now(timezone.utc)`. PIREPs only carry `HHMM`; the observation date comes from the source row (`obs_time` column, e.g. `2026-08-30T16:30:00.000Z`).
- **Why it matters:** `PirepFields.obs_time` is wrong for every historical row. If used for temporal splits or weather matching it silently compares different dates; currently `process()` ignores it and uses the column, so the bug is latent but exported in `parse_pirep` output and any future caller.
- **Proposed fix:** return a time-of-day or accept a reference date; resolve the date from the raw row.
- **Dependencies:** ISS-008.
- **Status:** Open

### ISS-026 — `_parse_location()` placeholder and index handling

- **Category:** Bug
- **Severity:** Medium
- **Evidence:** `parser/pirep.py:205-224`. It splits on whitespace, then uses `tokens[1]`/`tokens[2]` as lat/lon for `"SFO 037020"` style, but `lat = float(tokens[1][:3])` takes the first three characters of a radial, and `lon` defaults to `0.0`. Real `/OV` values (`MLI270020`) have no whitespace, so the function returns `None`. The docstring says navaid lookup is "the navaid module's job", but nothing calls `parser/navaid.py` from the pipeline.
- **Why it matters:** `location_parsed` is effectively always `None`; any future geocoding silently degrades, and `0.0` would place reports on the Greenwich meridian.
- **Proposed fix:** implement or delegate to `navaid.py`; return `None` instead of a fabricated longitude.
- **Dependencies:** ISS-008.
- **Status:** Open

### ISS-027 — `/RM` values containing slashes are truncated by the tokenizer

- **Category:** Bug
- **Severity:** Medium
- **Evidence:** `_tokenize` splits on every `\s+/`, and `_slice_field` stops at the first token beginning with `/` + letter (`pirep.py:141-155`). A remark like `/RM TURB BLO /FL350` splits the remark. The module docstring claims remarks "may contain spaces and slashes" (`:70`), and ADR-0003 relies on remarks being model input.
- **Why it matters:** remark text (often the most informative part for turbulence) is truncated or re-parsed as fields; also affects `/TB` extraction when a remark follows.
- **Proposed fix:** treat `/RM` as "rest of string" and parse fields in a defined order.
- **Dependencies:** ISS-008.
- **Status:** Open

### ISS-028 — Legacy migration drops `turbulence_2`/`_type`/`_freq`

- **Category:** Bug
- **Severity:** High
- **Evidence:** `scripts/migrate_legacy_db.py:97-117` inserts only the 11 legacy columns plus `source_url`/`source_etag`. `LEGACY_REQUIRED_COLUMNS` (`:32-44`) does not include the three extra turbulence columns, so legacy rows are migrated with `turbulence_2 = NULL` even though the source has 14 values.
- **Why it matters:** the migration loses the very data ISS-003 is trying to use, irreversibly.
- **Proposed fix:** copy all present columns; extend `LEGACY_REQUIRED_COLUMNS` with optional extras.
- **Dependencies:** ISS-002, ISS-003.
- **Status:** Open

### ISS-029 — Duplicate model registration raises an uncaught `IntegrityError`

- **Category:** Bug
- **Severity:** Low
- **Evidence:** `registry/store.py:146-149` logs `registry.duplicate_model` and re-raises. `training/orchestrator.py:187` does not catch it, so a retrain with the same version aborts after the artifact has already been written (and possibly overwritten).
- **Why it matters:** partial state on retry; confusing UX.
- **Proposed fix:** either upsert by `(kind, version)` or fail before saving the artifact.
- **Dependencies:** ISS-047.
- **Status:** Open

### ISS-030 — `BaselineSklearn.predict_proba()` is inconsistent and re-vectorises

- **Category:** Bug
- **Severity:** Medium
- **Evidence:** `models/baseline_sklearn.py:119-125` takes `clf = self._pipeline.named_steps["clf"]` and calls `clf.predict_proba(self._pipeline[:-1].transform(X))`. For `LogReg` this bypasses `Pipeline.predict_proba`; for `LinearSVC` the pipeline step is `CalibratedClassifierCV` (`:93`) and the manual transform is not guaranteed to match the fitted pipeline. No test exercises `predict_proba`.
- **Why it matters:** probabilities are the contract in `Model` (ADR-0005) and will feed the API; the current implementation is untested and version-fragile.
- **Proposed fix:** `return self._pipeline.predict_proba(X)` and let the pipeline own the transform; add a test for both `kind` values.
- **Dependencies:** ISS-071.
- **Status:** Open

### ISS-031 — Parser raises `ValueError`, docs promise `ParseError`

- **Category:** Bug
- **Severity:** Low
- **Evidence:** module docstring `parser/pirep.py:12-13` and `parse_pirep` docstring `:233-234` say `ParseError`; code raises `ValueError` (`:237`, `:240`, `:256`) with an explicit comment "We do not import ParseError here". `pipeline.py:132-136` catches `ValueError`. `errors.py` defines `ParseError`? (no `ParseError` symbol observed in the error module's usage elsewhere).
- **Why it matters:** callers cannot distinguish "not a PIREP" from a programming error by type; docs lie.
- **Proposed fix:** add/raise `ParseError` and catch it explicitly (keeping `ValueError` for programmer errors).
- **Dependencies:** ISS-008.
- **Status:** Open

### ISS-032 — `cleaner.preserve_remarks_tb_mentions` is configured but unused

- **Category:** Bug
- **Severity:** Medium
- **Evidence:** `CleanerConfig.preserve_remarks_tb_mentions = True` (`config.py:118`, `configs/default.yaml:54`). `clean_text()` (`processing/cleaner.py:56-93`) reads only `strip_fields`, `lowercase`, `collapse_whitespace`; `drop_tb_block` is also unread. The regex strips every `/TB` block regardless of location, then raises if any tag survives.
- **Why it matters:** a documented knob changes nothing; a user enabling/disabling it gets identical output. Either the intent (keep `/TB` mentions inside `/RM`?) conflicts with ADR-0003's absolute rule, or the code is incomplete.
- **Proposed fix:** decide the semantics; implement or remove the flags and update the config docs.
- **Dependencies:** ADR-0003 review (ISS-070); no blocking code dependency.
- **Status:** Open

### ISS-033 — Frozen `PipelineDeps` mutated via `object.__setattr__`

- **Category:** Bug
- **Severity:** Medium
- **Evidence:** `training/orchestrator.py:53` `object.__setattr__(deps, 'weather_matcher', weather_matcher)` on a `@dataclass(frozen=True)` (`pipeline.py:76-87`). `build_deps()` has no parameter for it (`:248-274`).
- **Why it matters:** defeats immutability, hides the dependency from the type signature, and will break if `PipelineDeps` ever uses `__slots__` or pydantic.
- **Proposed fix:** add `weather_matcher` to `build_deps()` and construct once (see ISS-034).
- **Dependencies:** ISS-034.
- **Status:** Open

### ISS-034 — `build_deps()` has no way to inject a weather matcher

- **Category:** Bug
- **Severity:** Medium
- **Evidence:** `pipeline.py:248-274` accepts `config`, `labeling`, `rules_path`, `path_root` only; `PipelineDeps` has a `weather_matcher` field defaulting to `None` (`:87`). Every caller (`training/orchestrator.py`, `evaluation/orchestrator.py`, `feature_store.py`, `map/folium_app.py`) builds deps without it.
- **Why it matters:** weather enrichment cannot be turned on through the supported constructor; only the frozen-dataclass hack works.
- **Proposed fix:** add an optional `weather_matcher` parameter and pass it from callers.
- **Dependencies:** ISS-024, ISS-033.
- **Status:** Open

### ISS-035 — No label-distribution / data-quality guard before training

- **Category:** Bug
- **Severity:** High
- **Evidence:** `run_training()` logs `training.processed_count` (`orchestrator.py:79-83`) and proceeds. With the current data it trains on 288 `None` / 1 `Light` / 1 `Moderate` (`ISS-008` evidence) and registers a model with `accuracy = 1.0`, `macro_f1 = 0.333` (`models/registry/baseline-v1_test/metrics.json`). No assertion on class count, minimum per-class support, or label/parse failure rate exists anywhere.
- **Why it matters:** a broken parser produced a "successful" model and a registry entry. Without a gate, the next silent data regression will also ship.
- **Proposed fix:** fail or warn on: >X% parse-to-default labels, classes with <N samples, a single-class test set; record the distribution in `lineage.json`.
- **Dependencies:** ISS-008, ISS-072, ISS-075.
- **Status:** Open

---

## Inconsistency

### ISS-036 — `.env` is documented everywhere and read nowhere

- **Category:** Inconsistency
- **Severity:** High
- **Evidence:** `config.py:1-12` lists ".env overlay" in the resolution order; `configs/default.yaml:3` says `.env` can override; `README.md:17-19` tells users to `cp .env.example .env` and edit it; `.env.example` is the documented config surface; `deploy/bootstrap.sh` creates `.env` and warns about the User-Agent. `Settings.model_config` sets `env_file=None` (`config.py:320`) and `Settings.load()` (`:337-387`) reads only YAML + `os.environ`. No dotenv import exists in the repo.
- **Why it matters:** the documented setup silently does nothing. `bootstrap.sh` will start the collector with the placeholder User-Agent (`contact@example.com`), which AWC may throttle — the exact failure the docs warn about.
- **Proposed fix:** load `.env` explicitly (e.g. `dotenv_values` merged before env), or remove every `.env` reference and update the deploy script to export variables.
- **Dependencies:** ISS-039, ISS-044, ISS-063.
- **Status:** Open

### ISS-037 — `Settings.load()` resolves `configs/` relative to CWD

- **Category:** Inconsistency
- **Severity:** High
- **Evidence:** `config.py:357` `_load_yaml_file("configs/default.yaml")`; `:361` `f"configs/{profile}.yaml"`; `_load_yaml_file` raises `ConfigError` if missing (`:397-400`). `deploy/chopcast.service` comments that `WorkingDirectory` matters for `paths.root`, but the config lookup also depends on it.
- **Why it matters:** every console script fails from any directory other than the repo root with `Configuration file not found` — including an installed package run from `$HOME`. It also blocks packaging as a real CLI.
- **Proposed fix:** resolve the repo/config root from `__file__` or an explicit `CHOPCAST_CONFIG_DIR`, falling back to CWD.
- **Dependencies:** ISS-036, ISS-063.
- **Status:** Open

### ISS-038 — Split manifests are written to different places per path

- **Category:** Inconsistency
- **Severity:** Medium
- **Evidence:** `training/orchestrator.py:161-162` writes `runs/split-<version>.json`; `training/cli.py:137` writes `<artifact>/split.json`; `evaluation/orchestrator.py:60` expects `paths.runs_dir / f"split-{model_version}.json"`. `training/baseline.py:79` creates a split with default `version="v1"`.
- **Why it matters:** a model trained via `chopcast-train` cannot be compared via `chopcast eval compare`; the error will be "split manifest not found", not a clear contract violation.
- **Proposed fix:** one writer, one canonical location referenced from the registry row (path or dataset version).
- **Dependencies:** ISS-001, ISS-019.
- **Status:** Open

### ISS-039 — Default `user_agent` is the placeholder `contact@example.com`

- **Category:** Inconsistency
- **Severity:** Medium
- **Evidence:** `configs/default.yaml:19` and `config.py:69`: `"chopcast/0.1 (+contact@example.com)"`. `README.md:17-19` and `.env.example:9-13` say a real contact is required; `config.py:85-90` only rejects an empty string. `deploy/bootstrap.sh` falls back to the template when `CHOPCAST_CONTACT` is unset.
- **Why it matters:** a default that looks valid but violates the provider's policy; combined with ISS-036, deployments can silently run with it.
- **Proposed fix:** make the UA required (no default) or fail/warn loudly when it still contains `example.com`.
- **Dependencies:** ISS-036.
- **Status:** Open

### ISS-040 — `requirements.txt` does not reflect `pyproject.toml`

- **Category:** Inconsistency
- **Severity:** Medium
- **Evidence:** `requirements.txt` contains only `pandas>=2.0` and `requests>=2.28`. `pyproject.toml:19-64` lists pydantic, pydantic-settings, PyYAML, structlog, click, joblib, python-dateutil plus extras. `deploy/bootstrap.sh` installs `-e .` (correct), so `requirements.txt` is dead but misleading.
- **Why it matters:** anyone following `pip install -r requirements.txt` gets an unusable environment; dependency drift between two sources.
- **Proposed fix:** delete the file or generate it from the project metadata as a pinned lock for deployment.
- **Dependencies:** none.
- **Status:** Open

### ISS-041 — `database.foreign_keys` / `busy_timeout_ms` are never applied

- **Category:** Inconsistency
- **Severity:** Low
- **Evidence:** `DatabaseConfig` exposes `foreign_keys` and `busy_timeout_ms` (`config.py:105-107`); `SqliteReportStore.__init__` (`schema.py:204-216`) hardcodes `PRAGMA foreign_keys = ON` and takes `busy_timeout_ms` but the collector CLI never passes it (`collector/cli.py:55`, `:149`). Changing the config has no effect.
- **Why it matters:** a knob that lies; concurrency tuning is impossible via config.
- **Proposed fix:** pass both values from settings in `_build_service`/`status` and honour `foreign_keys`.
- **Dependencies:** ISS-013.
- **Status:** Open

### ISS-042 — Env overlay supports only one nesting level

- **Category:** Inconsistency
- **Severity:** Low
- **Evidence:** `config.py:479-503` `_env_overlay` splits on the **first** `__` only: `section, _, key = body.partition("__")`. `CHOPCAST_TRAINING__BASELINE__C` becomes `{"training": {"baseline__c": ...}}`, which pydantic rejects or ignores (`extra="ignore"` on `Settings`, but `extra="forbid"` on sections).
- **Why it matters:** deep overrides (`training.baseline.C`, `logging.file_path`) cannot be set by environment, despite the documented `__` convention.
- **Proposed fix:** recursive split on `__`, or document the one-level limitation.
- **Dependencies:** ISS-036.
- **Status:** Open

### ISS-043 — Macro-F1 is diluted by classes with zero support

- **Category:** Inconsistency
- **Severity:** Medium
- **Evidence:** `evaluation/report.py:84-99` passes `labels=model.classes()` (3 classes in the artifact) into `evaluate`, which computes `macro_f1(per_class)` including `support=0` classes scored 0.0. The stored `metrics.json` shows `macro_f1 = 0.333`, `weighted_f1 = 1.0`, `accuracy = 1.0` on 58 single-class samples.
- **Why it matters:** the headline metric looks catastrophic (0.333) while accuracy is perfect; both are true and neither is informative. Teams will misread progress, and the 0.005 regression gate would be dominated by absent classes.
- **Proposed fix:** report macro-F1 over classes present in the evaluation set (or report both), and always report per-class support; document the rule.
- **Dependencies:** ISS-035, ISS-075.
- **Status:** Open

### ISS-044 — ADR-0006 sync-folder warning is not implemented

- **Category:** Inconsistency
- **Severity:** Medium
- **Evidence:** ADR-0006 §Consequences says "a startup check … if `paths.root` resolves to a directory under a known sync folder … the collector warns at startup", implemented in `chopcast.config.Settings`. No such check exists (grep for OneDrive/Dropbox/iCloud in `chopcast/` finds nothing; `config.py` has no path inspection beyond validation).
- **Why it matters:** the repo *is* under OneDrive, and the only mitigation is a commented `.env` line that ISS-036 says is not read. Contributors get SQLite locking/corruption risk with no warning.
- **Proposed fix:** implement the check in `Settings.load()` (warn, do not block), or amend the ADR to say it is unimplemented.
- **Dependencies:** ISS-036, ISS-077.
- **Status:** Open

### ISS-045 — `lineage.json` omits hashes and hardcodes commit/config version

- **Category:** Inconsistency
- **Severity:** Low
- **Evidence:** `training/orchestrator.py:165-179`: `"code_commit": "unknown"`, `"config_version": "v1"`, and `inputs` contains only counts (`raw_hashes_count`, `usable_hashes_count`, `train_count`, `test_count`). ADR-0004 §Mitigations says "the hash is also stored in the `lineage.json` of every derived artifact", and `docs/DATA_ENGINEERING.md` describes content-addressed lineage.
- **Why it matters:** the artifact cannot be reproduced or audited; the claim in the ADR is false.
- **Proposed fix:** record `git rev-parse HEAD`, config hash, dataset version, split file hash, and (optionally) the hash list.
- **Dependencies:** ISS-001, ISS-007.
- **Status:** Open

### ISS-046 — Two independent model-comparison implementations

- **Category:** Inconsistency
- **Severity:** Low
- **Evidence:** `evaluation/compare.py::compare` (registry-record metrics diff) used by `chopcast-train compare`; `evaluation/orchestrator.py::compare_models` (reloads data, re-predicts) used by `chopcast eval compare`. They produce different reports from different inputs.
- **Why it matters:** "compare" means two things; test coverage and docs attach to different ones.
- **Proposed fix:** one comparison entry point with a `--recompute` flag, or clearly label one as "metadata diff".
- **Dependencies:** ISS-004, ISS-038.
- **Status:** Open

### ISS-084 — Generated folium maps depend on CDN assets and online tiles

- **Category:** Inconsistency
- **Severity:** Medium
- **Evidence:** `map/folium_app.py:89` calls `folium.Map(location=..., zoom_start=4, control_scale=True)` without `tiles=`; folium's default template loads Leaflet JS/CSS from a CDN and OpenStreetMap tiles from the network. The module docstring frames the output as an audit artefact for researchers, and the dashboard brief requires offline operation. No generated map exists to test against.
- **Why it matters:** a generated map opened without internet is a blank/broken page, and the default file silently makes third-party requests; the audit artefact is not self-contained. It also conflicts with the dashboard's offline guarantee if the file browser later serves these maps.
- **Proposed fix:** support `tiles=None` and inject vendored Leaflet assets (or document the online requirement explicitly), add an offline smoke test that opens the generated HTML with no network.
- **Dependencies:** ISS-083.
- **Status:** Open

### ISS-086 — Collector logs go to two paths/formats and carry no run id

- **Category:** Inconsistency
- **Severity:** Low
- **Evidence:** `collector/cli.py:46` configures the log at `<logs_dir>/collector.log`; `configs/default.yaml:135` declares `logging.file_path` as `${paths.logs_dir}/chopcast.log`; the only log with content is the root `collector.log` (158 bytes, two plain-text `TOTAL=` lines), while `logs/` is empty and structlog is configured for JSON or console output. `RunResult` carries a `run_id`, but the legacy root lines do not.
- **Why it matters:** an operator or the dashboard cannot reliably find "the" collector log, and cannot correlate lines to a `runs` row; the root file is a ghost from an older configuration.
- **Proposed fix:** pick one documented destination and format, bind `run_id` into every cycle log line, remove/rotate the legacy root file, add a test that the configured path is the one written.
- **Dependencies:** ISS-013, ISS-085.
- **Status:** Open

### ISS-087 — Evaluation metrics are duplicated three ways with no schema/version

- **Category:** Inconsistency
- **Severity:** Low
- **Evidence:** `training/orchestrator.py:182` writes `metrics.json` and `:191` stores the same `report.to_dict()` in `metrics_json`; `training/cli.py:142-145` writes `report.json` and `:154` stores the same dict in the registry. `EvaluationReport.to_dict()` has no `schema_version`, `run_id`, or checksum. The two live registry rows and artifact files happen to match, but nothing enforces it.
- **Why it matters:** the dashboard must guess which copy is canonical; the copies can drift (e.g., a failed registry write after the file write); consumers cannot reject an incompatible metric shape.
- **Proposed fix:** add `schema_version` + `run_id` to the report dict, designate one canonical file, store a checksum/pointer in the registry, and add a consistency test.
- **Dependencies:** ISS-001, ISS-045, ISS-085.
- **Status:** Open

---

## Tech debt

### ISS-047 — Registry/artifact metadata is muddled

- **Category:** Tech debt
- **Severity:** High
- **Evidence:** `models/registry/registry.db` rows: id 1 `v1_test` kind `baseline`; id 2 `v1_transformer` kind **`baseline`** with artifact `models\registry\baseline-v1_transformer`. `promotions` is empty. Both metrics files are identical (`macro_f1 0.333`, 58 samples). `run_training()` derives `kind` from the caller's `model_kind`, so the transformer run was registered as a baseline; the transformer branch also fails before saving (ISS-014), so id 2's artifact is a baseline pipeline. `artifact_path` is relative.
- **Why it matters:** the registry cannot be trusted to say what a model is or which one is current (`current("production")` returns `None`). Any inference or comparison keyed on `model_kind` will misroute.
- **Proposed fix:** derive `kind` from the trained object, validate artifacts on registration, add a promotion step to the training workflow (or a documented manual one), and rebuild the two existing rows/artifacts.
- **Dependencies:** ISS-007, ISS-014, ISS-029, ISS-035.
- **Status:** Open

### ISS-048 — Config sections with no implementation

- **Category:** Tech debt
- **Severity:** Medium
- **Evidence:** `configs/default.yaml` and `config.py` define `api` (258-265), `monitoring.prometheus`/`drift` (268-288), `training.imbalance.smote` (204-207), `training.regression_gate` (210-214), `evaluation.slice_columns` (231). No `api/`, `monitoring/`, or `inference/` packages exist; `smote` is never branched on; no regression gate is applied; no slicing is implemented. `weather.enabled` exists and is honoured, but the matcher is inert (ISS-024).
- **Why it matters:** the config surface promises features that do not exist; users tune knobs with no effect, and it inflates the apparent scope.
- **Proposed fix:** mark unimplemented sections as reserved in docs, or remove them until implemented.
- **Dependencies:** ISS-049, ISS-066.
- **Status:** Open

### ISS-049 — Optional dependencies for features that do not exist

- **Category:** Tech debt
- **Severity:** Low
- **Evidence:** `pyproject.toml:42-52` defines `serving` (fastapi/uvicorn) and `monitoring` (prometheus-client); nothing imports either. `map` extra pulls geopandas, but `folium_app.py` uses only folium/pandas. `dev` therefore installs unused heavy packages.
- **Why it matters:** slow installs, larger attack surface, and a misleading capability signal.
- **Proposed fix:** align extras with actual imports (or add the features).
- **Dependencies:** ISS-048.
- **Status:** Open

### ISS-050 — Dead code and duplicate logger assignment

- **Category:** Tech debt
- **Severity:** Low
- **Evidence:** `processing/pipeline.py:39` and `:41` assign `log = get_logger(__name__)` twice. `processing/cleaner.py:30-31` defines `_FIELD_TAG_RE` and never uses it. `map/folium_app.py:19` imports `Model` but never uses it; `:23` contains the `get_logger if 'get_logger' in globals()` hack. `scripts/migrate_legacy_db.py:146-147` defines unused `_now_iso`. `pipeline.py`'s docstring says missing `obs_time` raises `FeatureBuildError`, while the code returns `None` (`:115-117` vs `:124-127`).
- **Why it matters:** small, but each one misleads a reader or a linter; ruff should be catching some of these once it runs over the package (see ISS-076).
- **Proposed fix:** delete or wire up; correct the docstring.
- **Dependencies:** ISS-076.
- **Status:** Open

### ISS-051 — Untracked root scripts

- **Category:** Tech debt
- **Severity:** Medium
- **Evidence:** `git status` shows `?? test_pipeline.py`, `?? test_pipeline.py\`` (a stray backtick filename), `?? test_transformer.py`, `?? trace_pipeline.py`. They are outside `tests/`, not collected by pytest (`testpaths = ["tests"]`), and encode a third training wiring (ISS-001).
- **Why it matters:** they look like tests but never run; one has a malformed name that will break shell globbing and Windows tooling; they hold knowledge that will be lost or duplicated.
- **Proposed fix:** decide whether they are experiments (move to `notebooks/` or delete) or tests (move into `tests/` with fixtures); remove the stray backtick file.
- **Dependencies:** ISS-001.
- **Status:** Open

### ISS-052 — No `CHANGELOG.md`

- **Category:** Tech debt
- **Severity:** Low
- **Evidence:** repository root listing has no `CHANGELOG.md`; `docs/CONTRIBUTING.md` describes a release/versioning process (per the onboarding read).
- **Why it matters:** no record of schema/feature-version breaking changes, which matter here because hashes and dataset versions are content-breaking (ADR-0004).
- **Proposed fix:** add a changelog keyed to schema/feature versions, or drop the release claim from CONTRIBUTING.
- **Dependencies:** none.
- **Status:** Open

### ISS-053 — Committed notebook of unknown provenance

- **Category:** Tech debt
- **Severity:** Low
- **Evidence:** `ChopCast.ipynb` sits at the repo root and is tracked (absent from `git status`), while ADR-0002 says notebooks belong in `notebooks/` and are "not used to ship models". The notebook's contents were not reviewed during onboarding.
- **Why it matters:** unknown code/state in the repo; likely stale relative to `chopcast/`; may contain outputs or paths from a previous layout.
- **Proposed fix:** review, move to `notebooks/`, strip outputs, or delete.
- **Dependencies:** ISS-001.
- **Status:** Open

### ISS-054 — `.gitignore` has a BOM, duplicates, and ignores `models/manifest.json`

- **Category:** Tech debt
- **Severity:** Low
- **Evidence:** `.gitignore` begins with a UTF-8 BOM (`# Collected data`), repeats `.venv/`, `venv/`, `.DS_Store`, `.ipynb_checkpoints/`, `snapshot.csv`, `pireps.db`; and ignores `models/manifest.json`, while ADR-0002 says "Only the registry's `manifest.json` … is committed".
- **Why it matters:** the BOM can confuse tools; duplicates are noise; the manifest rule contradicts the ADR and would silently exclude the one file the ADR says to publish.
- **Proposed fix:** rewrite the file without BOM/duplicates; decide the manifest rule and align the ADR.
- **Dependencies:** ISS-007.
- **Status:** Open

### ISS-055 — Coverage config omits `chopcast/__main__.py`, which does not exist

- **Category:** Tech debt
- **Severity:** Low
- **Evidence:** `pyproject.toml:176` `omit = [..., "chopcast/__main__.py"]`; the package listing has no `__main__.py`.
- **Why it matters:** `python -m chopcast` (implied by the omission and by `README`-style usage) does not work; the config hides the gap.
- **Proposed fix:** add `__main__.py` delegating to `chopcast.cli:main`, or drop the omit entry.
- **Dependencies:** ISS-004.
- **Status:** Open

### ISS-083 — No configured map output location or map-run metadata

- **Category:** Tech debt
- **Severity:** Medium
- **Evidence:** `map/folium_app.py:37` defaults `output_path=Path("turbulence_map.html")`; `chopcast/cli.py:29` defaults `--output` to the same CWD-relative name; `Paths` (`paths.py:34-43`) has no map/output accessor and `configs/default.yaml` has no map section. No generated `*.html` exists in the repo. The function records nothing about the model id, filters, row counts, or generation time alongside the file.
- **Why it matters:** outputs land in whatever directory the caller happened to use, can overwrite each other silently, and cannot be discovered by an operator or the dashboard. There is no audit trail from a map back to the data/model that produced it.
- **Proposed fix:** add a configured `paths.maps_dir` (default `runs/maps`), write a sidecar manifest (model id, filters, counts, timestamps, data snapshot), and make the CLI default to it.
- **Dependencies:** ISS-007, ISS-017, ISS-058.
- **Status:** Open

### ISS-085 — No training/evaluation run history; only successes are inferable

- **Category:** Tech debt
- **Severity:** High
- **Evidence:** `REGISTRY_SCHEMA` has only `models`/`promotions` (`registry/store.py:28-51`). `run_training()` writes an artifact, split, lineage, and registry row but no run record (`training/orchestrator.py:156-197`); `chopcast-train` writes no lineage (`training/cli.py:131-156`). Split manifests contain `version`, `seed`, `mode`, and hashes but no timestamp or run id (`runs/split-v1_test.json`). The `runs` table is collection-only. Failures are never recorded anywhere; the two live successes have no status, duration, or config hash.
- **Why it matters:** the dashboard cannot report run history, failed attempts, durations, retries, or which config/dataset produced a model. A "Logs/Jobs" page would show collection cycles only, and training history would be an inference from file layout. Reproducibility and incident review are impossible.
- **Proposed fix:** add append-only `training_runs`/`evaluation_runs` tables (or a JSONL run log) with `run_id`, `started_at`, `finished_at`, `status`, `source_path`, `config_hash`, `dataset/split refs`, counts, and `error`; write on start, finish, and failure.
- **Dependencies:** ISS-001, ISS-007, ISS-038, ISS-045.
- **Status:** Open

---

## Packaging

### ISS-056 — `chopcast/logging.py` is untracked — clean clone cannot import

- **Category:** Packaging
- **Severity:** Critical
- **Evidence:** `git status`: `?? chopcast/logging.py` and `D chopcast/chopcast/logging.py`. Every module imports `from chopcast.logging import get_logger` (e.g. `storage/schema.py:19`, `processing/pipeline.py:33`, `registry/store.py:22`, `collector/service.py:22`). A fresh clone of `29fb780` has no `chopcast/logging.py`.
- **Why it matters:** nothing imports. This is the single highest-leverage packaging fix.
- **Proposed fix:** add the real file at `chopcast/logging.py`, remove the deleted nested path, commit.
- **Dependencies:** none.
- **Status:** Open

### ISS-057 — `map/`, `weather/`, `weather/providers/` have no `__init__.py`

- **Category:** Packaging
- **Severity:** High
- **Evidence:** file listing: `chopcast/map/folium_app.py` with no `chopcast/map/__init__.py`; `chopcast/weather/{cache,features,matcher}.py` with no `chopcast/weather/__init__.py`; `chopcast/weather/providers/metar.py` with no `__init__.py`. `[tool.setuptools.packages.find] include = ["chopcast*", "scripts*"]` (`pyproject.toml:79-84`) only finds packages with `__init__.py` (regular packages).
- **Why it matters:** `pip install .` will omit these modules; `chopcast-map` and any weather import fail post-install. Source-tree runs work by namespace-package accident, which hides the bug.
- **Proposed fix:** add the three `__init__.py` files (exporting the public symbols), add an install smoke test that imports every advertised entry point.
- **Dependencies:** ISS-022, ISS-058, ISS-063.
- **Status:** Open

### ISS-058 — Four console scripts point at missing modules

- **Category:** Packaging
- **Severity:** High
- **Evidence:** `pyproject.toml:66-73` declares `chopcast-parse` → `chopcast.parser.cli`, `chopcast-eval` → `chopcast.evaluation.cli`, `chopcast-registry` → `chopcast.registry.cli`, `chopcast-map` → `chopcast.map.cli`. None of those files exists (`chopcast/parser/` has `pirep.py`, `navaid.py`, `golden.py`, `__init__.py`; `evaluation/` and `registry/` have no `cli.py`; `map/` has only `folium_app.py`). Note: the onboarding doc's §5.10 line claiming `chopcast-parse` exists is incorrect — correct it when this issue is resolved.
- **Why it matters:** four of seven advertised commands fail with `ModuleNotFoundError`; `README.md` documents three of them.
- **Proposed fix:** implement thin CLIs or remove the entry points (decision ISS-004).
- **Dependencies:** ISS-004, ISS-016, ISS-019, ISS-068.
- **Status:** Open

### ISS-059 — No CI workflow

- **Category:** Packaging
- **Severity:** High
- **Evidence:** no `.github/` directory. `docs/ROADMAP.md` M0 requires "`ruff check`, `mypy chopcast`, `pytest` all pass on CI"; `docs/TESTING.md` describes CI behaviour; `pyproject.toml` defines strict ruff/mypy/pytest/coverage settings.
- **Why it matters:** every quality gate is voluntary. The current state (syntax errors in the package, untracked module, missing entry points) is exactly what CI would have caught.
- **Proposed fix:** add a workflow running install → ruff → mypy → pytest with coverage on a supported Python matrix.
- **Dependencies:** ISS-006, ISS-056, ISS-057, ISS-076.
- **Status:** Open

### ISS-060 — No Dockerfile / compose despite M7 and docs

- **Category:** Packaging
- **Severity:** Medium
- **Evidence:** no `Dockerfile` or `docker-compose*.yml` in the repo root or `deploy/`; `docs/ROADMAP.md` M7 requires "`docker compose up` brings the API, collector, and monitoring stack online"; README/ARCHITECTURE describe container deployment.
- **Why it matters:** the documented deployment story is not reproducible; `deploy/` is EC2-specific.
- **Proposed fix:** either add container definitions for collector (+ future API) or remove the container claims from docs until M7.
- **Dependencies:** ISS-059, ISS-066.
- **Status:** Open

### ISS-061 — No DVC despite ADR-0002 / README

- **Category:** Packaging
- **Severity:** Medium
- **Evidence:** no `.dvc/`, `dvc.yaml`, or `.dvc` files. ADR-0002 §Decision says "`data/` … (DVC-tracked, gitignored)" and "Parquet is DVC-tracked"; `README.md:79` says "datasets (gitignored, DVC-tracked)". The feature store writes JSONL, not Parquet (`data/feature_store.py:139`, and its docstring says Parquet).
- **Why it matters:** dataset versioning has no mechanism; the docstring/ADR claim a format that is not produced.
- **Proposed fix:** adopt DVC (or an equivalent) for `data/processed/`, or amend ADR-0002/README and the feature-store docstring to match JSONL.
- **Dependencies:** ISS-001, ISS-028.
- **Status:** Open

### ISS-062 — No pre-commit configuration despite ADR-0002

- **Category:** Packaging
- **Severity:** Low
- **Evidence:** no `.pre-commit-config.yaml`; ADR-0002 §Consequences cites a "`pre-commit` notebook-clean step" and a lint rule as mitigations.
- **Why it matters:** local checks are undocumented and absent; notebook output/formatting drift is unmanaged.
- **Proposed fix:** add pre-commit hooks (ruff, ruff-format, mypy optional, notebook cleaning) or drop the claim.
- **Dependencies:** ISS-059.
- **Status:** Open

### ISS-063 — M0 "definition of done" is unchecked; installability unverified

- **Category:** Packaging
- **Severity:** Medium
- **Evidence:** `docs/ROADMAP.md` M0 lists `pip install -e .[dev]` succeeds, `ruff`/`mypy`/`pytest` pass, `python -m chopcast.collector --help` works, no cross-namespace imports, idempotent legacy migration — **all unchecked** (`- [ ]`), as are M1–M7. `pyproject.toml` requires `>=3.11`; local runs are on 3.14.
- **Why it matters:** the project is treating M0 as done in practice while its own criteria say otherwise; there is no evidence install/lint/type/test ever passed.
- **Proposed fix:** run the checklist, record results, fix or re-scope; keep the boxes honest.
- **Dependencies:** ISS-056, ISS-057, ISS-058, ISS-059.
- **Status:** Open

---

## Docs

### ISS-064 — README still describes the pre-M0 three-file prototype

- **Category:** Docs
- **Severity:** High
- **Evidence:** `README.md:5`: "**Status:** Pre-M0. The original 3-file prototype is in `explore.py`, `collector.py`, and `test_collector.py`." None of those files exists; `chopcast/` is a full package with collector, storage, parser, models, and a registry.
- **Why it matters:** the first thing a new contributor reads is false about the repo's state and layout; it undermines trust in the rest of the docs.
- **Proposed fix:** replace with a current status (what works, what doesn't, link to `docs/ONBOARDING.md`/`docs/ISSUES.md`).
- **Dependencies:** ISS-065, ISS-068.
- **Status:** Open

### ISS-065 — `CLAUDE.md` is stale and contradicts the package

- **Category:** Docs
- **Severity:** High
- **Evidence:** `CLAUDE.md` describes only the three-file prototype and phases 0–1, matching the old README, not the current `chopcast/` tree.
- **Why it matters:** agent/assistant instructions are wrong, so automated help will reason about files that do not exist.
- **Proposed fix:** rewrite or replace with a pointer to `docs/ARCHITECTURE.md` + `docs/ONBOARDING.md`; keep only durable conventions.
- **Dependencies:** ISS-064.
- **Status:** Open

### ISS-066 — Architecture docs reference modules that do not exist

- **Category:** Docs
- **Severity:** High
- **Evidence:** `docs/ARCHITECTURE.md`, `MODULE_DESIGN.md`, `ML_ARCHITECTURE.md`, `TESTING.md`, and ADR-0005 reference `chopcast.inference` (`Predictor`), `chopcast.api`, `chopcast.monitoring`, `evaluation.slices`, `container.py`, `map.filters`/`map.density`/`map.validation`, `models.explain`, and `tests/lint/test_imports.py`. None exists in the package listing.
- **Why it matters:** the design docs are the project's stated source of truth, but a reader cannot tell planned from implemented. New work gets scoped against imaginary modules.
- **Proposed fix:** mark planned modules explicitly (e.g. "planned, M3+") or move them to a roadmap appendix; keep the module map in sync with the tree.
- **Dependencies:** ISS-048, ISS-064, ISS-067.
- **Status:** Open

### ISS-067 — `TESTING.md` describes a test suite that is not there

- **Category:** Docs
- **Severity:** High
- **Evidence:** `docs/TESTING.md` describes import-boundary lint, secrets lint, golden-corpus tests, regression tests, weather tests, API tests, monitoring/drift tests, and fixtures. Actual `tests/` has unit tests for config/errors/paths/collector/storage/parser/processing/labeling/models/training/evaluation/registry, one integration migration test, and one lint test. No `tests/golden`, `tests/regression`, `tests/weather`, `tests/api`, `tests/monitoring`.
- **Why it matters:** the documented safety net does not exist, which is how ISS-008 and ISS-011 survived. Contributors may assume coverage that isn't there.
- **Proposed fix:** reconcile the document with reality (and track the gap as ISS-071–ISS-076).
- **Dependencies:** ISS-071, ISS-072, ISS-073, ISS-074, ISS-075.
- **Status:** Open

### ISS-068 — README command table advertises broken/missing commands

- **Category:** Docs
- **Severity:** Medium
- **Evidence:** `README.md:91-104` lists `chopcast-parse`, `chopcast-train run`, `chopcast-eval compare`, `chopcast-registry promote`, `chopcast-map`, and a quickstart using `.env`. Four of the five scripts are missing (ISS-058), `chopcast-train run` fails (ISS-015), `.env` is ignored (ISS-036).
- **Why it matters:** the quickstart fails at step one; users will conclude the project is broken rather than unfinished.
- **Proposed fix:** regenerate the table from what actually runs; add a "known broken" note until ISS-004/015/036 are fixed.
- **Dependencies:** ISS-004, ISS-015, ISS-036, ISS-058.
- **Status:** Open

### ISS-069 — Wrong repository URL in deploy docs and unit files

- **Category:** Docs
- **Severity:** Low
- **Evidence:** `deploy/chopcast.service` Documentation URL and `deploy/bootstrap.sh` `REPO_URL` use `https://github.com/SrivatsaChilla/ChopCast`; `pyproject.toml:76-77` and ADR-0001's deciders use `musiimenta-joachim/ChopCast`. `deploy/RUNBOOK.md` repeats the former.
- **Why it matters:** bootstrap clones the wrong/unexpected remote; support links rot.
- **Proposed fix:** pick the canonical remote, update all four locations.
- **Dependencies:** none.
- **Status:** Open

### ISS-070 — ADRs cite files/tests that were never created

- **Category:** Docs
- **Severity:** Low
- **Evidence:** ADR-0001 cites `tests/lint/test_imports.py` and `tests/integration/collector/test_migration.py` (the latter exists, the former does not) plus `scripts/legacy/collector.py` (absent). ADR-0002 cites `make`/`scripts/check_layout.sh`, `models/README.md`, and a pre-commit step (none exist). ADR-0003 cites `tests/lint/test_no_tb_leakage.py` and a call-graph test (actual file: `tests/lint/test_no_tb_outside_cleaner.py`; no call-graph test). ADR-0006 cites `scripts/backup.ps1` and a `chopcast paths` size report (neither exists). ADR-0005 cites `tests/unit/models/test_protocol.py` (exists) and `chopcast.inference` (absent).
- **Why it matters:** ACs are unverifiable; reviewers cannot tell which safeguards are real.
- **Proposed fix:** annotate each ADR with an implementation-status line, or correct the references.
- **Dependencies:** ISS-066, ISS-073, ISS-074, ISS-054.
- **Status:** Open

---

## Missing tests

### ISS-071 — No tests for map, CLIs, orchestrators, or weather

- **Category:** Missing tests
- **Severity:** High
- **Evidence:** `tests/` has no `test_map*`, no root-CLI test, no `evaluation/test_orchestrator.py`, no `training/test_orchestrator.py`, no `weather/` tests. The files with the most bugs from this review (`map/folium_app.py`, `training/orchestrator.py`, `evaluation/orchestrator.py`, `weather/*`) are precisely the untested ones. `tests/unit/collector/test_cli.py` exists; the root `chopcast/cli.py` is untested.
- **Why it matters:** ISS-014/016/017/019/020/024 would all have been caught by a single smoke test each.
- **Proposed fix:** add CLI smoke tests (invoke `--help` and one happy path with a temp DB) and orchestrator tests with fake stores/models.
- **Dependencies:** ISS-008, ISS-030, ISS-059.
- **Status:** Open

### ISS-072 — No golden corpus / parser conformance test

- **Category:** Missing tests
- **Severity:** High
- **Evidence:** `docs/ROADMAP.md` M2 requires "Golden corpus ≥ 100 hand-labeled PIREPs with 0 mismatches"; `chopcast/parser/golden.py` exists (helper), but there is no `tests/golden/`, no fixture file, and `tests/unit/parser/test_pirep.py` uses synthetic spaced strings only.
- **Why it matters:** the parser's fatal format assumption (ISS-008) survived because the only inputs it was tested on are the ones it was written against. Real AWC rows were never captured as fixtures.
- **Proposed fix:** add a fixture set sampled from the live cache (at least one per format variant) with expected field values; include unspaced rows as a regression case.
- **Dependencies:** ISS-008.
- **Status:** Open

### ISS-073 — No import-boundary lint test

- **Category:** Missing tests
- **Severity:** Medium
- **Evidence:** ADR-0001/0003 and `docs/MODULE_DESIGN.md` state that `parser` cannot import `api`, trainers cannot import `collector`, etc., and that `tests/lint/test_imports.py` enforces it. That file does not exist. Current violations exist: `processing/pipeline.py:37` imports `weather.matcher`; `map/folium_app.py:20` imports `collector.validators`; `registry/store.py` imports `storage.migrations`.
- **Why it matters:** the dependency rule is unenforced and already violated; layering will continue to erode.
- **Proposed fix:** add an AST-based import lint test encoding the allowed edges; fix or allowlist violations.
- **Dependencies:** ISS-066, ISS-070.
- **Status:** Open

### ISS-074 — No call-graph leakage regression test

- **Category:** Missing tests
- **Severity:** Medium
- **Evidence:** ADR-0003 §Behavioral claims "a test walks the call graph of `train()` and asserts that no function reachable from it accepts a `RawReport`". No such test exists; `tests/lint/test_no_tb_outside_cleaner.py` is the only leakage-related test, and it scans literals, not types.
- **Why it matters:** the third defence layer claimed by the ADR is absent; only the structural cleaner + literal lint are real.
- **Proposed fix:** implement the type/call-graph check or amend ADR-0003 to the two real layers.
- **Dependencies:** ISS-073.
- **Status:** Open

### ISS-075 — No metric-regression gate implementation

- **Category:** Missing tests
- **Severity:** Medium
- **Evidence:** `RegressionGateConfig` (macro_f1_tolerance 0.005, per_class_f1_tolerance 0.01) exists in `config.py:210-214` and `configs/default.yaml:95-97`; nothing reads it. `registry.promote` accepts any model; no comparison against the current champion is enforced.
- **Why it matters:** a worse model can be promoted; the roadmap's "definition of done" for M3/M4 implies a gate.
- **Proposed fix:** implement a gate in `promote`/training, or remove the config section until designed.
- **Dependencies:** ISS-043, ISS-047, ISS-048.
- **Status:** Open

### ISS-076 — 80% coverage gate is aspirational and unverified

- **Category:** Missing tests
- **Severity:** Medium
- **Evidence:** `pyproject.toml:179-180` sets `fail_under = 80`. No CI, no coverage artifact, and several modules are unimportable (`weather/cache.py`, `weather/providers/metar.py`) or unpackaged (`map/`). Tests were not run during this review (read-only brief).
- **Why it matters:** the gate cannot pass as configured; whoever first runs coverage will get a red build with no baseline.
- **Proposed fix:** run coverage, record the baseline, exclude/deprecate dead modules, then ratchet the gate.
- **Dependencies:** ISS-021, ISS-022, ISS-059, ISS-071.
- **Status:** Open

---

## Security

### ISS-077 — Operational data lives under OneDrive sync

- **Category:** Security
- **Severity:** High
- **Evidence:** repo path `C:\Users\HP\OneDrive\Documents\workspace\...\ChopCast`; `data/raw/pireps.db` is there. ADR-0006 documents exactly this risk (SQLite + sync clients → lock/corruption/partial upload) and recommends `C:\Users\HP\AppData\Local\ChopCast`. The only mitigation is a commented `.env` line; `.env` is not read (ISS-036) and no warning exists (ISS-044). `paths.root` defaults to `"."` (`configs/default.yaml:6`).
- **Why it matters:** corruption or silent data loss for the only copy of an unbackfillable dataset; also uploads aviation operational data to a third-party cloud without an explicit decision.
- **Proposed fix:** set a non-synced `paths.root` for real runs, implement the ADR-0006 warning, and document backup. (Documentation only here; no config changes applied.)
- **Dependencies:** ISS-036, ISS-044.
- **Status:** Open

### ISS-078 — Joblib artifacts are loaded by path with no integrity check

- **Category:** Security
- **Severity:** Medium
- **Evidence:** `BaselineSklearn.load` (`baseline_sklearn.py:146-163`) calls `joblib.load(path / "pipeline.joblib")`; `evaluation/orchestrator.py:28-34` and `map/folium_app.py:68-69` load whatever `record.artifact_path` says. Joblib deserialisation can execute arbitrary code; the registry DB is writable by any process that can open it.
- **Why it matters:** a tampered artifact or registry row becomes code execution. Low likelihood in a single-user repo, but the registry is designed to feed an inference API.
- **Proposed fix:** restrict artifact roots to `paths.models_dir`, verify a checksum stored at registration, and document the trust boundary before any API exists.
- **Dependencies:** ISS-007, ISS-047.
- **Status:** Open

### ISS-079 — `raw_json` stores every source column; no retention/PII review

- **Category:** Security
- **Severity:** Low
- **Evidence:** `collector/service.py:252` writes `raw_json={k: _clean_value(v) for k, v in row.to_dict().items()}` — the entire source row. PIREPs can contain callsigns/aircraft IDs and free-text remarks. `docs/DATA_ENGINEERING.md` describes immutable raw storage but no retention or redaction policy. `database.backup.retention_days` exists, but no purge job exists.
- **Why it matters:** indefinite retention of free text with possible identifiers, no documented policy, and no deletion path.
- **Proposed fix:** document what is stored, the retention period, and whether identifiers are in scope; add a purge job or explicitly state "keep forever".
- **Dependencies:** ISS-002, ISS-077.
- **Status:** Open

---

## Performance

### ISS-080 — Collector iterates rows with `DataFrame.iterrows()`

- **Category:** Performance
- **Severity:** Low
- **Evidence:** `collector/service.py:201` `for _, row in norm.iterrows():` — per-row Python objects, `pd.isna` calls in several helpers, and one `INSERT` per row (`schema.py:258-283`).
- **Why it matters:** fine at ~1.8k rows/poll, but the cache can grow and the loop is the hot path; batching would also reduce SQLite write amplification.
- **Proposed fix:** `itertuples()`/vectorised validation and `executemany`/batched inserts, measured against a captured CSV.
- **Dependencies:** none.
- **Status:** Open

### ISS-081 — Evaluation uses one `IN (...)` clause sized by the test split

- **Category:** Performance
- **Severity:** Medium
- **Evidence:** `evaluation/orchestrator.py:69-73` builds `placeholders = ",".join(["?"] * len(split.test_hashes))` and executes a single `IN` query. SQLite's bound-variable limit is commonly 999 (higher in recent builds); a large test split will fail with "too many SQL variables".
- **Why it matters:** works at 58 test rows; fails silently as the dataset grows (likely exactly when comparisons start to matter).
- **Proposed fix:** chunk the hash list, or join against a temp table.
- **Dependencies:** ISS-019, ISS-020.
- **Status:** Open

### ISS-082 — Map loads the whole view and builds a `pandas.Series` per row

- **Category:** Performance
- **Severity:** Low
- **Evidence:** `map/folium_app.py:50-51` selects all of `trainable`; `:98-136` loops every row, constructs `pd.Series(dict(row))` per row (`:103`) to call `DefaultRowValidator`, and adds a `CircleMarker` per valid row. No filtering (severity/time/altitude) despite M5 requiring filters.
- **Why it matters:** the HTML grows linearly with the dataset and the per-row validator conversion is avoidable; the missing filters are also a functional gap.
- **Proposed fix:** query only needed columns with filters, validate vectorised, and cluster/aggregate markers.
- **Dependencies:** ISS-017, ISS-018.
- **Status:** Open

---

## How to use this register

- Items are independent unless `Dependencies` says otherwise; resolve dependencies first.
- Decision items (ISS-001…007) block clusters: 001 → training bugs; 002 → DB/migration bugs; 003 → label bugs; 004 → CLI/packaging; 005/007 → registry/artifact; 006 → CI.
- Suggested first cut: ISS-056 (make the repo importable), then ISS-008 + ISS-035 (make the data honest), then ISS-002/011 (make the DB usable), then the decisions in ID order.
