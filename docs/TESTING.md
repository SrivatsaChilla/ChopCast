# Testing Strategy

> Authoritative for `tests/`. Test kinds, locations, naming, fixtures, and what must be covered at each milestone.

---

## 1. Principles

1. **Test the contracts, not the implementations.** Tests should not break when we refactor a module internally. They should break when a contract is broken.
2. **Tests are deterministic.** No real network, no real time, no random seeds unless seeded.
3. **Tests are fast.** The unit-test suite completes in under 30 seconds on a laptop. Slow tests are integration tests, marked as such, and not run on every save.
4. **Coverage is a signal, not a goal.** A line of code that is never executed is suspicious, but 100% coverage is not the objective. We require 100% coverage on `processing.cleaner` and `labeling.mapper` because leakage and mislabeling are catastrophic.
5. **Tests live next to the thing they test** when they're truly internal (e.g., a smoke test for a class), but the canonical test tree is `tests/` mirroring the package layout.

---

## 2. Test kinds and locations

```
tests/
├── unit/
│   ├── test_config.py
│   ├── test_paths.py
│   ├── collector/
│   │   ├── test_client.py
│   │   ├── test_validators.py
│   │   ├── test_hasher.py
│   │   └── test_service.py
│   ├── parser/
│   │   ├── test_pirep.py
│   │   ├── test_navaid.py
│   │   └── test_golden.py
│   ├── labeling/
│   │   ├── test_rules.py
│   │   ├── test_combinations.py
│   │   └── test_mapper.py
│   ├── processing/
│   │   ├── test_cleaner.py
│   │   ├── test_features.py
│   │   └── test_pipeline.py
│   ├── weather/
│   │   ├── test_matcher.py
│   │   └── test_cache.py
│   ├── training/
│   │   ├── test_split.py
│   │   ├── test_baseline.py
│   │   └── test_transformer.py
│   ├── evaluation/
│   │   ├── test_metrics.py
│   │   ├── test_slices.py
│   │   └── test_compare.py
│   ├── models/
│   │   └── test_protocol.py
│   ├── inference/
│   │   └── test_predictor.py
│   ├── api/
│   │   └── test_app.py
│   └── monitoring/
│       └── test_drift.py
├── integration/
│   ├── collector/
│   │   ├── test_collector_e2e.py        # mocked AWC, real DB
│   │   └── test_migration.py
│   ├── processing/
│   │   └── test_raw_to_features.py      # real SQLite, real pipeline
│   ├── training/
│   │   └── test_train_register_promote.py
│   └── api/
│       └── test_predict_e2e.py
├── golden/
│   ├── corpus.jsonl                     # hand-labeled PIREPs
│   └── README.md
├── regression/
│   └── evaluation/
│       ├── test_baseline_regression.py
│       └── fixtures/
│           ├── feature_store_v1.parquet
│           ├── split_v1.json
│           └── expected_metrics.json
├── lint/
│   ├── test_imports.py                  # dependency direction
│   ├── test_no_tb_leakage.py            # structural anti-leakage
│   └── test_no_hardcoded_secrets.py
└── conftest.py                          # shared fixtures
```

---

## 3. Unit tests

Unit tests cover one module in isolation. They use mocks for everything outside the module. The goal is to exercise every branch and every error path.

### 3.1 Naming

- File: `test_<module>.py`.
- Function: `test_<thing>_<condition>_<expected>`.
- Class: `Test<Module>` grouping related tests.

Example:
```python
def test_hasher_with_missing_lat_returns_stable_hash() -> None:
    h1 = report_hash("2026-08-22T17:00:00Z", None, -122.0, "UA /OV SFO")
    h2 = report_hash("2026-08-22T17:00:00Z", None, -122.0, "UA /OV SFO")
    assert h1 == h2
```

### 3.2 Fixtures

`tests/conftest.py` provides:

| Fixture | Scope | Purpose |
|---|---|---|
| `tmp_db` | function | Empty SQLite at a temp path. |
| `seeded_db` | function | `tmp_db` with 100 synthetic reports. |
| `settings` | function | A `Settings` with all defaults. |
| `mock_clock` | function | Returns a fixed `datetime`. |
| `mock_awc_client` | function | Returns canned DataFrames. |
| `golden_corpus` | session | The hand-labeled PIREP corpus. |

### 3.3 Coverage

`pyproject.toml` configures `pytest --cov=chopcast --cov-fail-under=80`. Modules below 80% fail CI. The following modules require 100%:

- `chopcast.processing.cleaner`
- `chopcast.labeling.mapper`
- `chopcast.collector.hasher`
- `chopcast.evaluation.metrics`
- `chopcast.inference.predictor`

These are the modules where a missed branch is a hidden bug, not a missing test.

### 3.4 Property-based tests

`labeling.mapper` and `parser.pirep` are tested with `hypothesis`. Examples:

```python
@given(raw_turb=st.text(min_size=0, max_size=50))
def test_mapper_never_crashes(raw_turb: str) -> None:
    label = map_to_severity(raw_turb, default_rules)
    assert label in {"None", "Light", "Moderate", "Severe"}

@given(raw=pirep_text_strategy())
def test_parser_returns_dataclass(raw: str) -> None:
    result = parse_pirep(raw)  # may raise ParseError
    assert result.raw == raw
```

This catches edge cases the golden corpus does not.

---

## 4. Golden corpus

The golden corpus is a committed, hand-labeled set of PIREPs.

### 4.1 Format

`tests/golden/corpus.jsonl`, one record per line:

```json
{
  "raw": "UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP occasional sharp jolts",
  "expected": {
    "location": "SFO",
    "location_parsed": [37.6189, -122.3750],
    "obs_time": "2026-08-22T14:25:00+00:00",
    "flight_level": 350,
    "aircraft_type": "B738",
    "turbulence": "MOD CHOP",
    "sky_conditions": null,
    "weather": null,
    "temperature": null,
    "icing": null,
    "remarks": "occasional sharp jolts"
  },
  "source": "AWC live 2026-08-22",
  "reviewer": "musiimenta-joachim"
}
```

### 4.2 Maintenance

- Adding a case: open a PR with the new line. The PR description says which bug the case would have caught.
- Removing a case: only allowed in a PR that also updates the parser, with justification. The git history keeps the removed case.
- Size: target 100 cases. Diminishing returns above 200.
- Reviewer: any contributor can add, but the case must include a `reviewer` field and the case must be cross-checked by a second person before merge.

### 4.3 Test

```python
def test_parser_matches_golden_corpus() -> None:
    for case in load_golden():
        actual = parse_pirep(case.raw)
        assert actual == case.expected, f"mismatch on {case.raw!r}"
```

A mismatch on any case fails the build.

---

## 5. Integration tests

Integration tests exercise multiple modules together. They live under `tests/integration/`.

### 5.1 Collector end-to-end

```python
def test_collector_cycle_inserts_deduped_rows(
    mock_awc_client: MockAwcClient,
    tmp_db: Path,
) -> None:
    # Two identical batches, then a third with one new row.
    batch = make_batch(0, 10)
    mock_awc_client.queue_response(batch)
    mock_awc_client.queue_response(batch)
    mock_awc_client.queue_response(batch.iloc[:1])

    service = DefaultCollectionService(
        client=mock_awc_client,
        validator=DefaultRowValidator(...),
        hasher=report_hash,
        store=SqliteReportStore(tmp_db),
        metrics=InMemoryMetrics(),
    )

    service.run_once()
    service.run_once()
    service.run_once()

    store = SqliteReportStore(tmp_db)
    assert store.count() == 11
```

### 5.2 Raw → features

```python
def test_raw_to_features_round_trip(tmp_db: Path) -> None:
    seed_db(tmp_db, n=50)
    store = SqliteReportStore(tmp_db)
    feature_store = build_feature_store(store, processing_config)
    feature_store.save(Paths(...).features_dir / "v1")
    reloaded = FeatureStore.load("v1")
    assert reloaded.count() == feature_store.count()
    assert reloaded.text_for(feature_store.hashes[:5]) == feature_store.text_for(feature_store.hashes[:5])
```

### 5.3 Train → register → promote

```python
def test_train_register_promote(registry_db: Path, feature_store: FeatureStore) -> None:
    split = make_split(feature_store, default_split_config)
    model = train_baseline(...)
    registry = Registry(registry_db)
    model_id = registry.register(model, config={...}, metrics=metrics, code_commit="abc")
    registry.promote(model_id)
    assert registry.load_production("baseline").model_version == model_id
```

Integration tests can be slow (multi-second). They are marked with `@pytest.mark.integration` and excluded from the default test run via `pytest -m "not integration"`.

---

## 6. ML evaluation regression

`tests/regression/evaluation/test_baseline_regression.py` is the most important test in the system after the leakage test. It guards against silent breakage of the model.

### 6.1 Fixture

`tests/regression/evaluation/fixtures/` contains:
- `feature_store_v1.parquet` — a small, frozen feature store.
- `split_v1.json` — a frozen split.
- `expected_metrics.json` — the macro-F1, per-class metrics, and confusion matrix from a known training run.

The fixture is generated by the first successful training run and committed. It is regenerated only when we intentionally change the baseline.

### 6.2 Test

```python
def test_baseline_regression(frozen_metrics: Metrics) -> None:
    model = BaselineSklearn.train(...)
    actual = compute(y_test, model.predict(X_test), classes=model.classes())
    assert abs(actual.macro_f1 - frozen_metrics.macro_f1) < 0.005
    for cls, m in actual.per_class.items():
        assert abs(m.f1 - frozen_metrics.per_class[cls].f1) < 0.01
```

A 0.5 percentage-point drop in macro-F1 fails the build. A 1 percentage-point drop in any class's F1 also fails. The test is run on every PR.

### 6.3 Updating the fixture

When a deliberate change moves the metrics:
1. Open a PR titled "Update baseline regression fixture."
2. Include the new metrics and a justification.
3. The PR must be reviewed by someone who did not author the change.

The fixture is treated as code. Its history matters.

---

## 7. Lint tests

Three lint tests run as part of `pytest`. They are not optional.

### 7.1 `test_imports.py` — dependency direction

Walks the AST of every module in `chopcast/` and asserts that imports only flow from higher-level modules to lower-level modules as defined in [MODULE_DESIGN.md](MODULE_DESIGN.md) §0. A `parser` module importing from `api` fails.

### 7.2 `test_no_tb_leakage.py` — structural anti-leakage

Walks the source tree and fails if the literal substring `/TB` appears in any file other than:
- `chopcast/processing/cleaner.py`
- `chopcast/parser/pirep.py` (the `/TB` pattern is part of the parser grammar)
- `tests/parser/test_pirep.py`
- `tests/processing/test_cleaner.py`
- `tests/golden/corpus.jsonl`

This is run on every commit. A regression is treated as a critical defect.

### 7.3 `test_no_hardcoded_secrets.py`

Greps for likely-secret patterns (AWS keys, generic API key formats, anything matching `password=` or `secret=` followed by a string). Excludes `configs/`, `.env.example`, and `tests/`. The collector's `USER_AGENT` is fine; a literal `Authorization: Bearer ...` is not.

---

## 8. Test commands

```bash
# unit + lint (fast, default)
pytest

# with coverage
pytest --cov=chopcast --cov-report=html

# everything including integration
pytest -m ""

# a single module
pytest tests/unit/parser/test_pirep.py

# a single test
pytest tests/unit/parser/test_pirep.py::test_parser_matches_golden_corpus

# only regression
pytest tests/regression/

# only lint
pytest tests/lint/

# verbose
pytest -v

# stop on first failure
pytest -x
```

CI runs `pytest -m "not integration"` on every push, and `pytest` (all tests) on every PR. Integration tests are also run nightly.

---

## 9. Test data

| Dataset | Location | Generation | Refresh |
|---|---|---|---|
| Golden PIREP corpus | `tests/golden/corpus.jsonl` | Hand-labeled | On parser change |
| Synthetic batches | `tests/collector/_factories.py` | Programmatically | Per test |
| Frozen feature store | `tests/regression/evaluation/fixtures/` | From a committed run | On baseline change |
| Mock AWC responses | `tests/collector/_factories.py` | Programmatically | Per test |
| Real AWC snapshot | `data/raw/snapshot.csv` | From `explore.py` | Manual |

Synthetic data is preferred. Real data is used only in regression fixtures and in the local `data/` directory for analysis.

---

## 10. What is not tested

- The web framework (FastAPI) is not unit-tested; we test the `Predictor` it depends on. The API is smoke-tested in integration.
- The map renderer is smoke-tested by `assert file exists and contains "folium"`. Visual regression would be possible with Playwright but is out of scope until M5.
- Hardware acceleration (CUDA, MPS) is not tested in CI; the CI runner is CPU. GPU behavior is exercised manually before each transformer release.
