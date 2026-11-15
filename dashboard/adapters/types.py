"""Immutable data-transfer objects shared by the adapter and the views."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class SourceState(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    MISSING = "missing"
    SCHEMA_MISMATCH = "schema_mismatch"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"

    @property
    def is_ok(self) -> bool:
        return self is SourceState.OK

    @property
    def is_problem(self) -> bool:
        return self in {SourceState.MISSING, SourceState.SCHEMA_MISMATCH, SourceState.ERROR}


@dataclass(frozen=True)
class SourceStatus:
    key: str
    label: str
    state: SourceState
    detail: str = ""
    path: str = ""
    mtime: str | None = None
    provenance: str | None = None

    @property
    def css(self) -> str:
        return f"state-{self.state.value}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "state": self.state.value,
            "detail": self.detail,
            "path": self.path,
            "mtime": self.mtime,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class Result(Generic[T]):
    data: T | None
    status: SourceStatus
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status.state is SourceState.OK

    @property
    def has_data(self) -> bool:
        return self.data is not None


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)

    @property
    def start(self) -> int:
        return (self.page - 1) * self.page_size + 1 if self.total else 0

    @property
    def end(self) -> int:
        return min(self.page * self.page_size, self.total)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


@dataclass(frozen=True)
class FileInfo:
    name: str
    path: str
    size: int
    mtime: str | None
    exists: bool = True
    is_dir: bool = False

    @property
    def size_human(self) -> str:
        return human_bytes(self.size)


def human_bytes(n: int | None) -> str:
    if n is None:
        return "—"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


@dataclass(frozen=True)
class ReportRow:
    hash: str
    fetched_at: str | None
    obs_time: str | None
    report_type: str | None
    raw_text: str | None
    turbulence: str | None
    turbulence_2: str | None
    aircraft: str | None
    lat: float | None
    lon: float | None
    altitude: float | None


@dataclass(frozen=True)
class ReportSummary:
    total: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    trainable_rows: int = 0
    primary_labelled: int = 0
    secondary_labelled: int = 0
    first_obs_time: str | None = None
    last_obs_time: str | None = None
    first_fetched_at: str | None = None
    last_fetched_at: str | None = None
    with_coords: int = 0
    without_coords: int = 0
    invalid_coords: int = 0
    distinct_hashes: int = 0


@dataclass(frozen=True)
class ReportDetail:
    row: ReportRow
    raw_json: str | None
    raw_json_error: str | None = None


@dataclass(frozen=True)
class RunRecord:
    id: int
    started_at: str | None
    finished_at: str | None
    status: str
    rows_seen: int | None
    rows_inserted: int | None
    rows_skipped: int | None
    rows_rejected: int | None
    error: str | None
    shape: str = "legacy"


@dataclass(frozen=True)
class RejectedRecord:
    id: int
    fetched_at: str | None
    reason: str
    detail: str | None


@dataclass(frozen=True)
class LabelCount:
    value: str
    count: int
    mapped: str = "None"
    rule: str = ""


@dataclass(frozen=True)
class LabelDistribution:
    total: int = 0
    primary: tuple[LabelCount, ...] = ()
    secondary: tuple[LabelCount, ...] = ()
    types: tuple[LabelCount, ...] = ()
    freqs: tuple[LabelCount, ...] = ()
    combined: dict[str, int] = field(default_factory=dict)
    labelled: int = 0
    unlabelled: int = 0
    rules_version: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrainableVariant:
    key: str
    label: str
    predicate: str
    count: int
    description: str


@dataclass(frozen=True)
class SplitInfo:
    name: str
    path: str
    version: str | None
    seed: int | None
    mode: str | None
    train_count: int
    test_count: int
    mtime: str | None
    error: str | None = None


@dataclass(frozen=True)
class ArtifactFile:
    name: str
    path: str
    size: int
    mtime: str | None
    exists: bool = True


@dataclass(frozen=True)
class TrainingRun:
    key: str
    model_id: int | None = None
    model_version: str = ""
    model_kind_stored: str | None = None
    model_kind_manifest: str | None = None
    feature_version: str | None = None
    registered_at: str | None = None
    artifact_path: str | None = None
    artifact_resolved: str | None = None
    artifact_exists: bool = False
    lineage: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    split: SplitInfo | None = None
    source_path: str = "unknown"
    warnings: tuple[str, ...] = ()
    files: tuple[ArtifactFile, ...] = ()


@dataclass(frozen=True)
class ModelRecord:
    id: int
    model_version: str
    model_kind: str
    feature_version: str
    registered_at: str
    metrics: dict[str, Any] | None
    artifact_path: str
    notes: str | None
    artifact_exists: bool
    artifact_resolved: str | None
    promotions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromotionRecord:
    id: int
    model_id: int
    promoted_at: str
    tag: str
    replaced_id: int | None


@dataclass(frozen=True)
class EvaluationRecord:
    model_id: int
    model_version: str
    model_kind: str
    feature_version: str
    registered_at: str
    metrics: dict[str, Any] | None
    source: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompareField:
    name: str
    a: Any
    b: Any
    delta: float | None = None


@dataclass(frozen=True)
class CompareResult:
    a: EvaluationRecord
    b: EvaluationRecord
    fields: tuple[CompareField, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MapPoint:
    hash: str
    lat: float
    lon: float
    obs_time: str | None
    altitude: float | None
    aircraft: str | None
    report_type: str | None
    label_primary: str | None
    label_secondary: str | None
    label_combined: str | None
    raw_text: str
    suspicious: bool = False


@dataclass(frozen=True)
class MapResult:
    points: tuple[MapPoint, ...]
    total_matching: int
    returned: int
    truncated: bool
    invalid_coords: int
    provenance: str
    warnings: tuple[str, ...] = ()
    label_counts: dict[str, int] = field(default_factory=dict)
    plottable: int = 0


@dataclass(frozen=True)
class MapFile:
    name: str
    relative: str
    path: str
    size: int
    mtime: str | None


@dataclass(frozen=True)
class LogFile:
    name: str
    path: str
    size: int
    mtime: str | None
    root: str


@dataclass(frozen=True)
class LogEntry:
    line_no: int
    timestamp: str | None
    level: str
    event: str
    fields: dict[str, Any]
    raw: str
    is_json: bool


@dataclass(frozen=True)
class PathInfo:
    key: str
    path: str
    exists: bool
    is_dir: bool
    size: int | None
    mtime: str | None
    readable: bool


@dataclass(frozen=True)
class ConfigFileView:
    name: str
    path: str
    exists: bool
    raw: dict[str, Any] | None
    resolved: dict[str, Any] | None
    error: str | None
    mtime: str | None


@dataclass(frozen=True)
class PackageInfo:
    name: str
    version: str | None
    required: bool = False


@dataclass(frozen=True)
class SanityCheck:
    key: str
    title: str
    state: str
    detail: str
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class SystemSnapshot:
    python_version: str
    python_executable: str
    django_version: str
    platform: str
    cwd: str
    timezone: str
    settings: dict[str, Any]
    paths: tuple[PathInfo, ...]
    configs: tuple[ConfigFileView, ...]
    packages: tuple[PackageInfo, ...]
    checks: tuple[SanityCheck, ...]


@dataclass(frozen=True)
class RawDbProfile:
    state: str
    tables: tuple[str, ...] = ()
    views: dict[str, str] = field(default_factory=dict)
    reports_columns: tuple[str, ...] = ()
    runs_columns: tuple[str, ...] = ()
    trainable_columns: tuple[str, ...] = ()
    schema_migrations: tuple[int, ...] = ()
    trainable_predicate: str = "unknown"
    has_report_type_in_trainable: bool = False
    has_rejected: bool = False
    runs_shape: str = "unknown"
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegistryProfile:
    state: str
    tables: tuple[str, ...] = ()
    has_models: bool = False
    has_promotions: bool = False
    stray_raw_tables: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Capabilities:
    raw: RawDbProfile
    registry: RegistryProfile


@dataclass(frozen=True)
class IssueCounts:
    total: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class IssuesDocument:
    html: str
    toc: tuple[tuple[str, str, int], ...] = ()
    counts: IssueCounts = field(default_factory=IssueCounts)
    source_path: str = ""
    mtime: str | None = None
