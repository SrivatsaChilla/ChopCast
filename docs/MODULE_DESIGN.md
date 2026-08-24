# Module Design

> Authoritative for the `chopcast/` package layout. Each module is documented with responsibility, public interface, inputs, outputs, dependencies, and error handling. SOLID principles and dependency inversion are applied throughout.

---

## 0. Package layout

```
chopcast/
├── __init__.py
├── config.py             # typed settings
├── logging.py            # structured logger factory
├── paths.py              # repo-relative path resolution
├── errors.py             # domain exception hierarchy
├── collector/
│   ├── __init__.py
│   ├── client.py         # HTTP client (AWC)
│   ├── service.py        # orchestrator
│   ├── validators.py     # row-level validation
│   ├── hasher.py         # content hash
│   └── cli.py            # `chopcast-collector` entry point
├── parser/
│   ├── __init__.py
│   ├── pirep.py          # parse "/"-delimited PIREP string
│   ├── navaid.py         # /OV navaid lookup
│   └── golden.py         # golden corpus loader
├── labeling/
│   ├── __init__.py
│   ├── rules.py          # load rules from YAML
│   ├── combinations.py   # handle "LGT-MOD" etc.
│   └── mapper.py         # raw turbulence -> severity
├── processing/
│   ├── __init__.py
│   ├── cleaner.py        # strip /TB, normalize
│   ├── features.py       # build feature row
│   ├── pipeline.py       # orchestrate parse -> label -> clean -> featurize
│   └── weather.py        # weather feature join (M6)
├── weather/
│   ├── __init__.py
│   ├── providers/
│   │   ├── __init__.py
│   │   └── metar.py
│   ├── matcher.py        # spatial-temporal join
│   └── cache.py          # local Parquet cache
├── models/
│   ├── __init__.py
│   ├── protocol.py       # Model Protocol
│   ├── baseline_sklearn.py
│   └── transformer_distilbert.py
├── training/
│   ├── __init__.py
│   ├── split.py
│   ├── baseline.py
│   ├── transformer.py
│   ├── class_weights.py
│   └── cli.py            # `chopcast-train` entry point
├── evaluation/
│   ├── __init__.py
│   ├── metrics.py
│   ├── report.py
│   ├── slices.py
│   └── compare.py
├── registry/
│   ├── __init__.py
│   ├── store.py          # SQL-backed registry
│   └── cli.py
├── inference/
│   ├── __init__.py
│   ├── loader.py
│   └── predict.py
├── api/
│   ├── __init__.py
│   ├── app.py
│   ├── schemas.py
│   └── middleware.py
├── map/
│   ├── __init__.py
│   ├── folium_app.py
│   ├── filters.py
│   ├── density.py
│   └── validation.py
├── monitoring/
│   ├── __init__.py
│   ├── metrics.py
│   └── drift.py
└── data/
    ├── __init__.py
    ├── feature_store.py
    └── version.py
```

The dependency rule: a module may import from any module at the same level or lower. It may *not* import from a higher level. This is enforced by `tests/lint/test_imports.py`.

```
api       -> inference -> models    -> protocol
                           |
                           v
                       training    -> data
                           |          |
                           v          v
                       evaluation <- processing -> labeling -> parser
                                                |
                                                v
                                            weather  -> collector -> config
```

---

## 1. Cross-cutting modules

### 1.1 `chopcast.config`

**Responsibility.** Load and validate configuration from YAML files and `.env`. Produce typed `Settings` objects.

**Public interface.**
```python
class Settings(BaseModel):
    collector: CollectorConfig
    database: DatabaseConfig
    processing: ProcessingConfig
    training: TrainingConfig
    api: ApiConfig
    paths: PathsConfig
    @classmethod
    def load(cls, profile: str = "default") -> "Settings": ...
```

**Inputs.** `configs/default.yaml`, `configs/{profile}.yaml` overlay, `.env` overlay. Layered in that order; later wins.

**Outputs.** A frozen `Settings` instance.

**Dependencies.** `pydantic`, `pyyaml`. No other Chopcast modules.

**Error handling.** Missing required keys raise `ConfigError` (defined in `chopcast.errors`) at startup, not at first use. The collector refuses to start with a half-configured environment.

### 1.2 `chopcast.logging`

**Responsibility.** Produce structured JSON loggers.

**Public interface.**
```python
def get_logger(name: str) -> structlog.stdlib.BoundLogger: ...
```

**Inputs.** `name`. The `LOG_LEVEL` env var. `LOG_FORMAT` (`json` | `console`).

**Outputs.** A bound logger.

**Dependencies.** `structlog`.

**Error handling.** Logging is best-effort; it never raises.

### 1.3 `chopcast.errors`

**Responsibility.** Define the project's exception hierarchy.

```python
class ChopcastError(Exception): ...
class ConfigError(ChopcastError): ...
class CollectionError(ChopcastError): ...
class HttpError(CollectionError):
    status: int
    url: str
class RateLimited(CollectionError): ...
class ParseError(ChopcastError):
    raw_text: str
    field: str
class ValidationError(ChopcastError):
    field: str
    value: Any
class LabelingError(ChopcastError): ...
class FeatureBuildError(ChopcastError): ...
class ModelNotFound(ChopcastError): ...
class LeakageError(ChopcastError): ...
```

**Rule:** library code raises these; the CLI catches them at the boundary and translates to user-friendly messages. Tests assert on exception types, not messages.

### 1.4 `chopcast.paths`

**Responsibility.** Resolve all paths from a single root.

**Public interface.**
```python
class Paths(BaseModel):
    root: Path
    raw_db: Path
    raw_dir: Path
    processed_dir: Path
    features_dir: Path
    models_dir: Path
    runs_dir: Path
    logs_dir: Path
    @classmethod
    def from_settings(cls, settings: Settings) -> "Paths": ...
```

This is the only place paths are constructed. Modules that need a path take a `Paths` object; they never call `Path("data/foo")`.

---

## 2. `chopcast.collector`

### 2.1 `collector.client`

**Responsibility.** Speak HTTP to AWC. Handle retries, rate limits, and timeouts. Return a parsed DataFrame or `None` for 204.

**Public interface.**
```python
class AwcClient(Protocol):
    def fetch_aircraft_reports(self) -> pd.DataFrame | None: ...

class HttpAwcClient:
    def __init__(self, url: str, user_agent: str, timeout: int, max_retries: int): ...
    def fetch_aircraft_reports(self) -> pd.DataFrame | None: ...
```

**Inputs.** Constructor: URL, user agent, timeout, max retries. Method: nothing (the URL is set at construction).

**Outputs.** A `DataFrame` of raw reports, or `None` on 204.

**Dependencies.** `requests`, `pandas`, `chopcast.config`, `chopcast.logging`, `chopcast.errors`.

**Error handling.**
- `204` → return `None`. This is a normal response, not an error.
- `429` → exponential backoff (5s, 10s, 20s, 40s, 80s, capped at 300s).
- `5xx` → same backoff.
- Network error → same backoff.
- After `max_retries`, raise `HttpError` with status and URL.

The client is testable by injecting a `MockAwcClient` that implements the protocol.

### 2.2 `collector.validators`

**Responsibility.** Validate one raw row. Produce a verdict and a reason.

**Public interface.**
```python
@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str | None
    detail: str | None

class RowValidator(Protocol):
    def validate(self, row: pd.Series) -> Verdict: ...

class DefaultRowValidator:
    def __init__(self, lat_range: tuple[float, float], lon_range: tuple[float, float]): ...
    def validate(self, row: pd.Series) -> Verdict: ...
```

**Inputs.** One row.

**Outputs.** A `Verdict`.

**Dependencies.** `pandas`, `chopcast.errors`.

**Error handling.** Validators never raise. They return a `Verdict(ok=False, ...)`. The caller decides what to do with rejected rows.

### 2.3 `collector.hasher`

**Responsibility.** Compute the content hash of a row.

**Public interface.**
```python
def report_hash(obs_time: str, lat: float | None, lon: float | None, raw_text: str) -> str: ...
```

**Inputs.** The four fields. `lat` and `lon` may be `None`.

**Outputs.** A 64-character hex string.

**Dependencies.** `hashlib`, `chopcast.errors`.

**Error handling.** Raises `ValidationError` if `obs_time` cannot be parsed as ISO 8601 or if `raw_text` is empty.

### 2.4 `collector.service`

**Responsibility.** Orchestrate one collection cycle. Pure orchestration — no HTTP, no SQL, no parsing.

**Public interface.**
```python
class CollectionService(Protocol):
    def run_once(self) -> RunResult: ...

class DefaultCollectionService:
    def __init__(
        self,
        client: AwcClient,
        validator: RowValidator,
        hasher: Callable[..., str],
        store: ReportStore,
        metrics: MetricsSink,
    ): ...
    def run_once(self) -> RunResult: ...
```

**Inputs.** Its dependencies, injected at construction.

**Outputs.** A `RunResult` with `rows_seen`, `rows_inserted`, `rows_skipped`, `rows_rejected`, `status`.

**Dependencies.** All injected. This module is the seam where the system becomes testable end-to-end with mocks.

**Error handling.** Exceptions from any dependency are caught, recorded in `runs.status`, and re-raised only if `RERAISE_ON_CYCLE_FAILURE` is set. The collector does not crash on a single bad cycle; the scheduler is responsible for restarting it.

### 2.5 `collector.cli`

**Responsibility.** Expose the collector as a CLI.

**Commands.**
- `chopcast-collector run` — continuous loop.
- `chopcast-collector once` — single cycle.
- `chopcast-collector status` — show last run, accrual rate.
- `chopcast-collector rejected --reason X` — inspect quarantined rows.
- `chopcast-collector migrate-legacy <path>` — ingest old `pireps.db`.

**Inputs.** CLI args.

**Outputs.** Console output, log files, side effects on the database.

**Dependencies.** All other collector modules + `chopcast.config`, `chopcast.logging`.

**Error handling.** CLI catches `ChopcastError` and prints a one-line message with the error type and a hint. Stack traces only on `--verbose`.

---

## 3. `chopcast.parser`

### 3.1 `parser.pirep`

**Responsibility.** Parse a PIREP string into structured fields.

**Public interface.**
```python
@dataclass(frozen=True)
class PirepFields:
    location: str | None
    location_parsed: tuple[float, float] | None
    obs_time: datetime | None
    flight_level: int | None
    aircraft_type: str | None
    turbulence: str | None
    sky_conditions: str | None
    weather: str | None
    temperature: int | None
    icing: str | None
    remarks: str | None
    raw: str

def parse_pirep(raw: str) -> PirepFields: ...
```

**Inputs.** The raw PIREP text (the `UA ...` string).

**Outputs.** A `PirepFields` dataclass. Missing fields are `None`.

**Dependencies.** `re`, `datetime`, `chopcast.parser.navaid`, `chopcast.errors`.

**Error handling.** Returns a `PirepFields` with whatever could be parsed. If nothing could be parsed, raises `ParseError`. The collector catches `ParseError` and quarantines the row.

### 3.2 `parser.navaid`

**Responsibility.** Resolve a `/OV` value (e.g., `SFO`, `BLM`) to lat/lon when possible.

**Public interface.**
```python
class NavaidDatabase(Protocol):
    def lookup(self, code: str) -> tuple[float, float] | None: ...

class FileNavaidDatabase:
    def __init__(self, csv_path: Path): ...
    def lookup(self, code: str) -> tuple[float, float] | None: ...
```

**Inputs.** A navaid code.

**Outputs.** `(lat, lon)` or `None`.

**Dependencies.** `csv` (stdlib).

**Error handling.** Returns `None` for unknown codes; never raises.

### 3.3 `parser.golden`

**Responsibility.** Load the golden corpus (hand-labeled PIREPs) used by `test_parser_golden.py`.

**Public interface.**
```python
def load_golden() -> list[GoldenCase]: ...

@dataclass(frozen=True)
class GoldenCase:
    raw: str
    expected: PirepFields
    source: str       # "AWC 2026-01" etc., for provenance
```

**Dependencies.** `pathlib`, `chopcast.config` (for the corpus path).

---

## 4. `chopcast.labeling`

### 4.1 `labeling.rules`

**Responsibility.** Load label-mapping rules from `configs/labeling.yaml`.

**Public interface.**
```python
@dataclass(frozen=True)
class LabelingRules:
    version: str
    none_patterns: list[re.Pattern]
    light_patterns: list[re.Pattern]
    moderate_patterns: list[re.Pattern]
    severe_patterns: list[re.Pattern]
    combination_strategy: str     # "max" | "min" | "first"
    chop_only_label: str          # "light" | "none"

def load_rules(path: Path) -> LabelingRules: ...
```

**Inputs.** YAML path.

**Outputs.** A `LabelingRules` instance.

**Dependencies.** `pyyaml`, `re`, `chopcast.errors`.

**Error handling.** Bad rules raise `LabelingError` at load time, not at first use.

### 4.2 `labeling.mapper`

**Responsibility.** Map a raw turbulence value to a severity class.

**Public interface.**
```python
def map_to_severity(raw: str | None, rules: LabelingRules) -> str: ...
```

**Inputs.** Raw turbulence value, rules.

**Outputs.** One of `"None"`, `"Light"`, `"Moderate"`, `"Severe"`.

**Dependencies.** `chopcast.labeling.rules`, `chopcast.labeling.combinations`.

**Error handling.** Returns `"None"` for missing or unrecognized values. Logs at WARNING when an unrecognized value is seen, so we can extend the rules over time.

---

## 5. `chopcast.processing`

### 5.1 `processing.cleaner`

**Responsibility.** Strip `/TB` and other leakage fields, normalize whitespace.

**Public interface.**
```python
def clean_text(raw_text: str, config: CleanerConfig) -> str: ...

@dataclass(frozen=True)
class CleanerConfig:
    version: str
    strip_fields: tuple[str, ...]      # ("/TB",)
    drop_tb_block: bool                # drop the value after /TB until next /
    lowercase: bool
    collapse_whitespace: bool
    preserve_remarks_tb_mentions: bool # if True, "RM CHOP" survives
```

**Inputs.** The raw PIREP text, plus a `CleanerConfig`.

**Outputs.** Cleaned text.

**Dependencies.** `re`, `chopcast.errors`.

**Error handling.** Raises `LeakageError` if a `/TB` value is detected in the output. The function runs a self-check at the end of every call.

**This module is the only place in the codebase allowed to know how to remove `/TB`.** The static check in CI enforces this.

### 5.2 `processing.features`

**Responsibility.** Build a `FeatureRow` from a processed report.

**Public interface.**
```python
@dataclass(frozen=True)
class FeatureRow:
    hash: str
    obs_time: datetime
    lat: float | None
    lon: float | None
    altitude_band: str | None
    aircraft_type: str | None
    report_type: str
    clean_text: str
    severity_label: str
    hour_of_day: int
    day_of_year: int

def build_features(
    report: ProcessedReport,
    config: FeatureConfig,
) -> FeatureRow: ...
```

**Inputs.** A `ProcessedReport`, a `FeatureConfig`.

**Outputs.** A `FeatureRow`.

**Dependencies.** `chopcast.processing.cleaner`, `chopcast.labeling.mapper`.

**Error handling.** Raises `FeatureBuildError` on missing required fields. The caller decides whether to drop the row or quarantine it.

### 5.3 `processing.pipeline`

**Responsibility.** End-to-end: parse → label → clean → featurize.

**Public interface.**
```python
def process(raw: RawReport, config: ProcessingConfig) -> FeatureRow | None: ...
```

**Inputs.** A raw report, a `ProcessingConfig`.

**Outputs.** A `FeatureRow` or `None` (if the row was rejected).

**Dependencies.** All processing modules.

**Error handling.** Returns `None` for parse failures (with a log entry). Raises only for programming errors.

### 5.4 `processing.weather`

**Responsibility.** Add weather columns to a `FeatureRow`.

**Public interface.**
```python
def enrich_with_weather(
    row: FeatureRow,
    matcher: WeatherMatcher,
    extractor: WeatherFeatureExtractor,
) -> FeatureRow: ...
```

**Dependencies.** `chopcast.weather.matcher`, `chopcast.weather.providers`.

---

## 6. `chopcast.weather`

### 6.1 `weather.providers.metar`

**Responsibility.** Fetch METAR observations.

**Public interface.**
```python
class MetarProvider(Protocol):
    def fetch(self, lat: float, lon: float, t: datetime, max_distance_km: float) -> list[MetarObservation]: ...
```

**Dependencies.** `requests`, `chopcast.config`.

### 6.2 `weather.cache`

**Responsibility.** Local Parquet cache of METAR observations to avoid re-fetching.

**Public interface.**
```python
class MetarCache(Protocol):
    def get_or_fetch(self, station: str, t_start: datetime, t_end: datetime) -> pd.DataFrame: ...
```

### 6.3 `weather.matcher`

**Responsibility.** Spatial-temporal join between reports and METAR.

**Public interface.**
```python
@dataclass(frozen=True)
class MatchResult:
    matched: bool
    station: str | None
    distance_km: float | None
    time_delta_minutes: float | None
    observation: MetarObservation | None

def match_nearest(
    report: FeatureRow,
    candidates: list[MetarObservation],
    max_distance_km: float,
    max_time_delta_minutes: float,
) -> MatchResult: ...
```

**Dependencies.** `numpy`.

---

## 7. `chopcast.models`

### 7.1 `models.protocol`

See [ML_ARCHITECTURE.md](ML_ARCHITECTURE.md) §2.

### 7.2 `models.baseline_sklearn`

**Public interface.**
```python
class BaselineSklearn:
    feature_version: str
    model_version: str
    model_kind: str = "baseline"

    @classmethod
    def train(cls, X: list[str], y: list[str], config: BaselineConfig) -> "BaselineSklearn": ...

    def predict(self, X: list[str]) -> np.ndarray: ...
    def predict_proba(self, X: list[str]) -> np.ndarray: ...
    def classes(self) -> list[str]: ...

    def save(self, path: Path) -> None: ...
    @classmethod
    def load(cls, path: Path) -> "BaselineSklearn": ...
```

**Dependencies.** `scikit-learn`, `joblib`, `numpy`.

### 7.3 `models.transformer_distilbert`

Same interface. Implementation uses HuggingFace `transformers` and `torch`. The interface is identical so the API cannot tell which kind it loaded.

---

## 8. `chopcast.training`

### 8.1 `training.split`

**Public interface.**
```python
@dataclass(frozen=True)
class Split:
    train_hashes: list[str]
    test_hashes: list[str]
    version: str
    seed: int
    config_version: str

def make_split(
    feature_store: FeatureStore,
    config: SplitConfig,
) -> Split: ...

def save_split(split: Split, path: Path) -> None: ...
def load_split(path: Path) -> Split: ...
```

**Dependencies.** `numpy`, `chopcast.data.feature_store`.

### 8.2 `training.baseline` and `training.transformer`

Both expose:

```python
def train(
    X: list[str],
    y: list[str],
    config: TrainConfig,
    feature_version: str,
) -> Model: ...
```

**Dependencies.** `chopcast.models.protocol`, `chopcast.models.baseline_sklearn` (or transformer).

### 8.3 `training.cli`

The `chopcast-train` CLI: `run`, `sweep`, `compare`. Thin wrappers.

---

## 9. `chopcast.evaluation`

### 9.1 `evaluation.metrics`

```python
@dataclass(frozen=True)
class Metrics:
    accuracy: float
    macro_f1: float
    weighted_f1: float
    per_class: dict[str, PerClassMetrics]
    confusion_matrix: np.ndarray
    support: dict[str, int]

def compute(y_true: list[str], y_pred: list[str], classes: list[str]) -> Metrics: ...
```

### 9.2 `evaluation.slices`

```python
def slice_metrics(
    y_true: list[str],
    y_pred: list[str],
    feature_store: FeatureStore,
    test_hashes: list[str],
    slice_columns: list[str],
) -> list[SliceMetrics]: ...
```

### 9.3 `evaluation.report`

Renders a `Metrics` object to Markdown. Pure function. No I/O. Testable.

### 9.4 `evaluation.compare`

Renders an A/B comparison between two model registry entries.

---

## 10. `chopcast.registry`

**Public interface.**
```python
class Registry:
    def register(self, model: Model, config: dict, metrics: Metrics, code_commit: str) -> str: ...
    def load(self, model_id: str) -> Model: ...
    def load_production(self, kind: str) -> Model: ...
    def promote(self, model_id: str) -> None: ...
    def list_versions(self, kind: str) -> list[ModelEntry]: ...
```

**Backed by.** SQLite database at `models/registry/registry.db`. Same DB as the raw store? **No.** Separate file, separate lifecycle. See [ADR-0001](adr/0001-redesign-rationale.md).

---

## 11. `chopcast.inference`

**Public interface.**
```python
class Predictor:
    def __init__(self, registry: Registry, model_id: str | None = None): ...
    def predict(self, raw_text: str, context: dict | None = None) -> Prediction: ...

@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    class_probabilities: dict[str, float]
    model_id: str
    model_kind: str
    feature_version: str
```

This is the public surface of the model system. The API calls this. Nothing else does.

---

## 12. `chopcast.api`

**Public interface.** FastAPI app with endpoints:

| Endpoint | Method | Body | Response |
|---|---|---|---|
| `/health` | GET | — | `{"status": "ok"}` |
| `/ready` | GET | — | `{"ready": true}` if registry.load_production succeeds |
| `/predict` | POST | `{"raw_text": str, "context": dict}` | `Prediction` |
| `/metrics` | GET | — | Prometheus exposition |
| `/model/info` | GET | — | `{"model_id": ..., "kind": ..., "feature_version": ...}` |

The API does not know about AWC, SQLite, or the registry's storage details. It depends on `inference.Predictor`. Mocking the predictor in tests is one line.

---

## 13. `chopcast.map`

**Public interface.**
```python
def render_map(
    feature_store: FeatureStore,
    predictions: list[Prediction] | None,
    config: MapConfig,
    output_path: Path,
) -> None: ...
```

Renders an HTML file. The function is pure: input features + config + optional predictions → file. No HTTP, no network.

---

## 14. `chopcast.monitoring`

### 14.1 `monitoring.metrics`

Prometheus counters and histograms. Imported by the API and the collector.

### 14.2 `monitoring.drift`

```python
class DriftDetector:
    def __init__(self, baseline: dict[str, float], threshold: float): ...
    def check(self, current: dict[str, float]) -> DriftResult: ...
```

The baseline is the class distribution from the training set. The detector compares it to a recent window of predictions. PSI (population stability index) is the default metric.
