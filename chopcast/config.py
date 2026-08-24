"""Typed settings loaded from YAML profiles and the environment.

The configuration pipeline:
    1. `configs/default.yaml`  (the baseline)
    2. `configs/<profile>.yaml` overlay (selected by `CHOPCAST_PROFILE`)
    3. `.env` overlay
    4. `os.environ` overlay (double-underscore for nesting)

Later sources win. `Settings.load()` returns a frozen, validated object.
A bad value raises `ConfigError` at startup, not at first use.

See docs/CONFIGURATION.md and docs/MODULE_DESIGN.md §1.1.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from chopcast.errors import ConfigError
from chopcast.paths import Paths


# ---------------------------------------------------------------------------
# Subsections
# ---------------------------------------------------------------------------
class PathsConfig(BaseModel):
    """All paths. Variables like `${paths.root}` are resolved at load time."""

    model_config = ConfigDict(extra="forbid")

    root: str = "."
    raw_db: str = "${paths.root}/data/raw/pireps.db"
    raw_dir: str = "${paths.root}/data/raw"
    processed_dir: str = "${paths.root}/data/processed"
    features_dir: str = "${paths.root}/data/features"
    models_dir: str = "${paths.root}/models/registry"
    registry_db: str = "${paths.root}/models/registry/registry.db"
    runs_dir: str = "${paths.root}/runs"
    logs_dir: str = "${paths.root}/logs"
    backups_dir: str = "${paths.root}/backups"


class CollectorValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat_range: tuple[float, float] = (-90.0, 90.0)
    lon_range: tuple[float, float] = (-180.0, 180.0)
    require_raw_text: bool = True
    require_obs_time: bool = False


class CollectorDedupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat_decimals: int = 4
    lon_decimals: int = 4


class CollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str = "https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz"
    user_agent: str = "chopcast/0.1 (+contact@example.com)"
    poll_seconds: int = 600
    request_timeout_seconds: int = 60
    max_retries: int = 5
    max_backoff_seconds: int = 300
    backoff_base_seconds: int = 5
    validation: CollectorValidationConfig = Field(default_factory=CollectorValidationConfig)
    dedup: CollectorDedupConfig = Field(default_factory=CollectorDedupConfig)

    @field_validator("poll_seconds", "request_timeout_seconds", "max_retries")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    @field_validator("user_agent")
    @classmethod
    def _non_empty_user_agent(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_agent must not be empty (AWC filters anonymous clients)")
        return v


class DatabaseBackupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    schedule: str = "03:00"
    retention_days: int = 30
    destination: str = "${paths.backups_dir}"


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journal_mode: Literal["WAL", "TRUNCATE", "DELETE", "MEMORY", "OFF"] = "WAL"
    foreign_keys: bool = True
    busy_timeout_ms: int = 5000
    backup: DatabaseBackupConfig = Field(default_factory=DatabaseBackupConfig)


class CleanerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strip_fields: tuple[str, ...] = ("/TB",)
    drop_tb_block: bool = True
    lowercase: bool = True
    collapse_whitespace: bool = True
    preserve_remarks_tb_mentions: bool = True


class FeaturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    altitude_bands: tuple[tuple[int, int], ...] = (
        (0, 20000),
        (20000, 30000),
        (30000, 40000),
        (40000, 60000),
    )
    aircraft_unknown_token: str = "<UNK>"
    use_hour_of_day: bool = True
    use_day_of_year: bool = True


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser_version: str = "v1"
    labeler_version: str = "v1"
    cleaner_version: str = "v1"
    feature_builder_version: str = "v1"
    cleaner: CleanerConfig = Field(default_factory=CleanerConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)


class LabelingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules_path: str = "${paths.root}/configs/labeling.yaml"
    default_label: str = "None"


class TfidfConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ngram_range: tuple[int, int] = (1, 2)
    min_df: int = 5
    max_df: float = 0.95
    sublinear_tf: bool = True


class TransformerTextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = "distilbert-base-uncased"
    max_length: int = 128
    truncation: Literal["head", "tail", "head_tail"] = "head_tail"


class TextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_words_path: str = "${paths.root}/configs/stop_words.txt"
    tfidf: TfidfConfig = Field(default_factory=TfidfConfig)
    transformer: TransformerTextConfig = Field(default_factory=TransformerTextConfig)


class SplitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["stratified", "time", "spatiotemporal"] = "stratified"
    test_size: float = 0.2
    seed: int = 42


class BaselineTrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["logreg", "linear_svc"] = "logreg"
    class_weight: str | None = "balanced"
    max_iter: int = 1000
    C: float = 1.0


class TransformerTrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    epochs: int = 3
    batch_size: int = 16
    learning_rate: float = 5.0e-5
    warmup_steps: int = 100
    fp16: bool = False


class ImbalanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["class_weight", "smote", "none"] = "class_weight"


class RegressionGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    macro_f1_tolerance: float = 0.005
    per_class_f1_tolerance: float = 0.01


class TrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_split: SplitConfig = Field(default_factory=SplitConfig)
    baseline: BaselineTrainConfig = Field(default_factory=BaselineTrainConfig)
    transformer: TransformerTrainConfig = Field(default_factory=TransformerTrainConfig)
    imbalance: ImbalanceConfig = Field(default_factory=ImbalanceConfig)
    regression_gate: RegressionGateConfig = Field(default_factory=RegressionGateConfig)


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classes: tuple[str, ...] = ("None", "Light", "Moderate", "Severe")
    slice_columns: tuple[str, ...] = ("altitude_band", "report_type", "aircraft_type")


class MetarConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str = "https://aviationweather.gov/api/data/metar"
    max_distance_km: float = 50.0
    max_time_delta_minutes: float = 60.0


class WeatherCacheConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "${paths.root}/data/weather/metar.parquet"
    retention_days: int = 30


class WeatherConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str = "metar"
    metar: MetarConfig = Field(default_factory=MetarConfig)
    cache: WeatherCacheConfig = Field(default_factory=WeatherCacheConfig)


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    request_body_log: bool = False
    include_disclaimer_header: bool = True


class PrometheusConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    path: str = "/metrics"


class DriftConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    method: Literal["psi", "ks"] = "psi"
    threshold: float = 0.2
    window_size: int = 1000


class MonitoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    drift: DriftConfig = Field(default_factory=DriftConfig)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "console"] = "json"
    destination: Literal["stdout", "file", "both"] = "stdout"
    file_path: str = "${paths.logs_dir}/chopcast.log"
    rotate_max_bytes: int = 10_485_760
    rotate_backup_count: int = 5


# ---------------------------------------------------------------------------
# Root Settings
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """The full ChopCast configuration.

    Use `Settings.load(profile)` to construct one. The constructor is
    intentionally not exposed because layer resolution is non-trivial.
    """

    model_config = SettingsConfigDict(
        env_prefix="CHOPCAST_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
        # We apply env ourselves in `Settings.load()` to keep path-ref
        # resolution deterministic. Disabling the env source here means a
        # bare `Settings()` constructor will not read the environment.
        env_file=None,
    )

    paths: PathsConfig = Field(default_factory=PathsConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    labeling: LabelingConfig = Field(default_factory=LabelingConfig)
    text: TextConfig = Field(default_factory=TextConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # ----- loading ---------------------------------------------------------
    @classmethod
    def load(cls, profile: str | None = None) -> "Settings":
        """Build a Settings from configs + environment.

        Order of resolution:
            1. `configs/default.yaml`
            2. `configs/<profile>.yaml` (selected by profile arg or env)
            3. `CHOPCAST_*` environment variables
            4. `${paths.root}` references are expanded after step 3 so that
               an env override of `paths.root` flows into all path strings.

        Args:
            profile: profile name (e.g. "dev", "prod", "ci"). If None, uses
                the `CHOPCAST_PROFILE` env var; if that is also unset, uses
                "default".
        """
        if profile is None:
            profile = os.environ.get("CHOPCAST_PROFILE", "default")

        # 1. Defaults
        merged = _load_yaml_file("configs/default.yaml")

        # 2. Profile overlay
        if profile and profile != "default":
            profile_path = f"configs/{profile}.yaml"
            if Path(profile_path).is_file():
                overlay = _load_yaml_file(profile_path)
                merged = _deep_merge(merged, overlay)
            else:
                raise ConfigError(
                    f"Profile '{profile}' selected but {profile_path} does not exist"
                )

        # 3. Environment overlay (manual so path resolution stays in our control).
        env_overlay = _env_overlay(prefix="CHOPCAST_")
        merged = _deep_merge(merged, env_overlay)

        # 4. Resolve ${paths.root} references now that the env overlay has
        #    had a chance to override paths.root.
        merged = _resolve_path_refs_dict(merged)

        # 5. Construct the validated Settings object. Pydantic-settings will
        #    ALSO read the environment here, but since we already applied it
        #    the values are stable. We disable the env source for this call
        #    by leaving the dict's values intact and constructing directly.
        try:
            settings = cls.model_validate(merged)  # type: ignore[attr-defined]
        except Exception as e:
            raise ConfigError(f"Invalid configuration: {e}") from e

        return settings

    # ----- helpers ---------------------------------------------------------
    def to_paths(self) -> Paths:
        return Paths.from_settings(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_yaml_file(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"Configuration file not found: {path}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML parse error in {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a mapping, got {type(data).__name__}")
    return data


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge overlay onto base. Lists and scalars are replaced."""
    out: dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_VAR_PATTERN = __import__("re").compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _resolve_path_refs_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Expand `${paths.foo}` references in any string field of `data`.

    Walks the dict recursively. The `paths` sub-dict is expanded first
    (so path-on-path references work), then the result is used to expand
    references in every other section.

    Two passes total. References that cannot be resolved are left
    untouched; the surrounding Pydantic model will reject them at
    validation time.
    """
    paths = data.get("paths", {}) or {}

    def expand(value: str, *, against: dict[str, Any]) -> str:
        def repl(m: Any) -> str:
            section, key = m.group(1), m.group(2)
            if section == "paths" and key in against:
                return str(against[key])
            return m.group(0)
        return _VAR_PATTERN.sub(repl, value)

    # First pass: expand self-references inside `paths`.
    out_paths: dict[str, Any] = {}
    for key, value in paths.items():
        if isinstance(value, str):
            out_paths[key] = expand(value, against=paths)
        else:
            out_paths[key] = value
    # Second pass: a path may reference another path whose value was itself
    # a reference (e.g., `backups_dir` references `root`).
    for key, value in list(out_paths.items()):
        if isinstance(value, str):
            out_paths[key] = expand(value, against=out_paths)

    out = dict(data)
    out["paths"] = out_paths

    # Now expand `${paths.*}` references in every other section.
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return expand(node, against=out_paths)
        return node

    for section, value in list(out.items()):
        if section == "paths":
            continue
        out[section] = walk(value)

    return out


def _env_overlay(*, prefix: str) -> dict[str, Any]:
    """Read `CHOPCAST_*` env vars and return a nested dict overlay.

    `CHOPCAST_PATHS__ROOT=C:/foo` becomes `{"paths": {"root": "C:/foo"}}`.
    The `__` delimiter indicates one level of nesting. Values are strings;
    the surrounding Pydantic models coerce them to their declared types.

    Only top-level settings keys that already exist in the merged YAML
    dict are included; we do not invent new fields. This is checked at the
    merge step (`_deep_merge` only adds keys the overlay already has).
    """
    out: dict[str, Any] = {}
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        body = env_key[len(prefix):]
        if "__" in body:
            section, _, key = body.partition("__")
        else:
            section, key = "", body
        if not section or not key:
            continue
        section_dict = out.setdefault(section.lower(), {})
        section_dict[key.lower()] = env_value
    return out


__all__ = [
    "ApiConfig",
    "BaselineTrainConfig",
    "CleanerConfig",
    "CollectorConfig",
    "CollectorDedupConfig",
    "CollectorValidationConfig",
    "DatabaseBackupConfig",
    "DatabaseConfig",
    "DriftConfig",
    "EvaluationConfig",
    "FeaturesConfig",
    "ImbalanceConfig",
    "LabelingConfig",
    "LoggingConfig",
    "MetarConfig",
    "MonitoringConfig",
    "PathsConfig",
    "ProcessingConfig",
    "PrometheusConfig",
    "RegressionGateConfig",
    "Settings",
    "SplitConfig",
    "TextConfig",
    "TfidfConfig",
    "TransformerTextConfig",
    "TransformerTrainConfig",
    "TrainingConfig",
    "WeatherCacheConfig",
    "WeatherConfig",
]
