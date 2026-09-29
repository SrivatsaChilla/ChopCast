"""End-to-end processing pipeline.

`process(raw) -> FeatureRow | None` is the single entry point used by
the dataset writer and by tests. It:

1. Parses the raw PIREP text into structured fields.
2. Maps the raw turbulence value to a severity label.
3. Strips leakage fields and normalises whitespace.
4. Buckets altitude and computes hour-of-day / day-of-year.
5. Builds the final `FeatureRow`.

Any parse failure short-circuits to `None`; structural failures are
logged at WARNING. Programming errors still raise.

See `docs/MODULE_DESIGN.md` §5.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from chopcast.config import (
    CleanerConfig,
    FeaturesConfig,
    LabelingConfig,
    ProcessingConfig,
)
from chopcast.errors import FeatureBuildError
from chopcast.labeling.mapper import map_to_severity
from chopcast.labeling.rules import LabelingRules, load_rules
from chopcast.logging import get_logger
from chopcast.parser.pirep import parse_pirep
from chopcast.processing.cleaner import clean_text
from chopcast.processing.features import FeatureRow, altitude_band

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Raw report shape (from the SQLite layer)
# ---------------------------------------------------------------------------
@runtime_checkable
class RawReport(Protocol):
    """The minimum the pipeline needs from a raw report.

    We use a Protocol rather than importing the storage dataclass so the
    pipeline doesn't depend on SQLite.
    """

    @property
    def hash(self) -> str: ...
    @property
    def obs_time(self) -> str | None: ...
    @property
    def raw_text(self) -> str | None: ...
    @property
    def report_type(self) -> str | None: ...
    @property
    def aircraft(self) -> str | None: ...
    @property
    def lat(self) -> float | None: ...
    @property
    def lon(self) -> float | None: ...
    @property
    def altitude(self) -> float | None: ...


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PipelineDeps:
    """Injected dependencies for the pipeline.

    `rules` is loaded once at startup; we don't re-read the YAML on
    every call. `config` carries the cleaner, features, and labeling
    knobs.
    """

    config: ProcessingConfig
    rules: LabelingRules


def _parse_obs_time(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string into a `datetime`. Returns None on failure."""
    if value is None:
        return None
    try:
        # Python's fromisoformat accepts 'Z' since 3.11; for older versions
        # we normalise.
        v = value.replace("Z", "+00:00")
        return datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def process(
    raw: RawReport | dict,
    deps: PipelineDeps,
    *,
    default_label: str = "None",
) -> FeatureRow | None:
    """Run the pipeline on one raw report. Returns `None` on parse failure.

    Accepts either a `RawReport` (Protocol) or a plain dict with the
    same keys. Dicts are wrapped in the `_RowLike` adapter that the
    feature store uses.

    Raises `FeatureBuildError` for programming errors (missing hash,
    missing obs_time). Other failures (parse failure, missing
    turbulence) are logged and yield `None`.
    """
    # Adapter: turn dicts into a RawReport-shaped object.
    if isinstance(raw, dict):
        raw = _RowAdapter(raw)
    if not raw.hash:
        raise FeatureBuildError("raw.hash is empty")
    obs_dt = _parse_obs_time(raw.obs_time)
    if obs_dt is None:
        log.warning("pipeline.missing_obs_time", hash=raw.hash[:8])
        return None
    if not raw.raw_text:
        log.warning("pipeline.missing_raw_text", hash=raw.hash[:8])
        return None

    try:
        parsed = parse_pirep(raw.raw_text)
    except ValueError:
        log.warning("pipeline.parse_failed", hash=raw.hash[:8])
        return None

    # Use the parsed turbulence if available; otherwise fall back to
    # whatever the raw row carried.
    turbulence = parsed.turbulence if parsed.turbulence is not None else None
    label = map_to_severity(turbulence, deps.rules)
    # If the labeler produced the configured default for unknown, but
    # we have explicit "default_label" from the labeling config, prefer
    # the default for rows that produced nothing.
    if turbulence is None:
        label = default_label

    # Clean the text. This is the only place leakage can occur.
    cleaned = clean_text(raw.raw_text, deps.config.cleaner)

    band = altitude_band(
        parsed.flight_level if parsed.flight_level is not None else None,
        deps.config.features.altitude_bands,
    )

    aircraft = parsed.aircraft_type or raw.aircraft
    report_type = raw.report_type or "PIREP"

    return FeatureRow(
        hash=raw.hash,
        obs_time=obs_dt,
        lat=raw.lat,
        lon=raw.lon,
        altitude_band=band,
        aircraft_type=aircraft,
        report_type=report_type or "PIREP",
        clean_text=cleaned,
        severity_label=label,
        hour_of_day=obs_dt.hour,
        day_of_year=obs_dt.timetuple().tm_yday,
    )


class _RowAdapter:
    """Adapter: dict -> RawReport (Protocol).

    Lives here to avoid an import cycle (the feature store uses the
    same shape, but we want `process()` callable directly with a dict
    in tests).
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def hash(self) -> str:
        return str(self._data.get("hash", ""))

    @property
    def obs_time(self) -> str | None:
        return self._data.get("obs_time")

    @property
    def raw_text(self) -> str | None:
        return self._data.get("raw_text")

    @property
    def report_type(self) -> str | None:
        return self._data.get("report_type")

    @property
    def aircraft(self) -> str | None:
        return self._data.get("aircraft")

    @property
    def lat(self) -> float | None:
        v = self._data.get("lat")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @property
    def lon(self) -> float | None:
        v = self._data.get("lon")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @property
    def altitude(self) -> float | None:
        v = self._data.get("altitude")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


def build_deps(
    config: ProcessingConfig,
    labeling: LabelingConfig,
    *,
    rules_path: Path | None = None,
    path_root: str | Path | None = None,
) -> PipelineDeps:
    """Build a `PipelineDeps` from a `ProcessingConfig` and labeling config.

    Loads the labeling rules from `rules_path` if given, else from
    `labeling.rules_path`. The path may contain an unresolved
    `${paths.root}` reference — pass `path_root` to substitute it.
    """
    from pathlib import Path

    rp = Path(rules_path) if rules_path else Path(labeling.rules_path)
    rp_str = str(rp)
    if "${paths.root}" in rp_str:
        if path_root is None:
            raise ValueError(
                f"labeling.rules_path contains an unresolved ref and no "
                f"path_root was supplied: {rp_str}"
            )
        rp_str = rp_str.replace("${paths.root}", str(path_root))
        rp = Path(rp_str)
    rules = load_rules(rp)
    return PipelineDeps(config=config, rules=rules)


__all__ = ["PipelineDeps", "RawReport", "build_deps", "process"]