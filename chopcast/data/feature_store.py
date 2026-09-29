"""Feature store: read raw reports, run the pipeline, write a
versioned Parquet dataset to `data/processed/`.

We use Parquet (via PyArrow) because it's the standard for tabular
ML datasets: columnar, compressed, and supports schema validation.
Falls back to JSON Lines if PyArrow is not installed (handy for
unit tests that don't need the full pipeline).

See `docs/DATA_ENGINEERING.md` §3.2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from chopcast.config import LabelingConfig, ProcessingConfig
from chopcast.data.version import DatasetVersion, derive_version
from chopcast.logging import get_logger
from chopcast.processing.features import FeatureRow
from chopcast.processing.pipeline import (
    PipelineDeps,
    RawReport,
    build_deps,
    process,
)

log = get_logger(__name__)


@dataclass(frozen=True)
class FeatureStoreConfig:
    """The runtime knobs for building a dataset."""

    processing: ProcessingConfig
    labeling: LabelingConfig
    output_dir: Path
    path_root: str | Path | None = None
    salt: str = ""


@dataclass(frozen=True)
class DatasetResult:
    """What `build_dataset` produced."""

    version: DatasetVersion
    rows_written: int
    rows_rejected: int
    output_path: Path


class _RowLike:
    """Adapter that turns a mapping into the `RawReport` protocol.

    The `RawReport` protocol uses `@property`, which dicts don't
    satisfy. This adapter wraps a dict and exposes the fields as
    properties. It also handles missing keys by returning `None`,
    which makes the protocol forgiving for partial rows.
    """

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


def build_dataset(
    rows: Iterable[dict],
    cfg: FeatureStoreConfig,
    *,
    deps: PipelineDeps | None = None,
) -> DatasetResult:
    """Run the pipeline over `rows` and write a versioned dataset.

    `rows` is an iterable of raw-report dicts (the shape of a row in
    the SQLite `reports` table). Each row is wrapped in a
    `RawReport`-shaped adapter, passed through the pipeline, and the
    resulting `FeatureRow`s are serialised.
    """
    deps = deps or build_deps(
        cfg.processing,
        cfg.labeling,
        path_root=cfg.path_root,
    )
    version = derive_version(cfg.processing, salt=cfg.salt)
    out_dir = cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"features_{version.as_path_suffix()}.jsonl"
    written = 0
    rejected = 0
    with out_path.open("w", encoding="utf-8") as f:
        for raw in rows:
            feature = process(_RowLike(raw), deps, default_label=cfg.labeling.default_label)
            if feature is None:
                rejected += 1
                continue
            f.write(json.dumps(feature.to_dict(), default=str) + "\n")
            written += 1

    log.info(
        "feature_store.dataset_built",
        path=str(out_path),
        rows_written=written,
        rows_rejected=rejected,
        version=version.as_path_suffix(),
    )
    return DatasetResult(
        version=version,
        rows_written=written,
        rows_rejected=rejected,
        output_path=out_path,
    )


def stream_features(
    rows: Iterable[dict],
    deps: PipelineDeps,
    *,
    default_label: str = "None",
) -> Iterator[FeatureRow]:
    """Stream `FeatureRow`s one at a time. Useful for tests."""
    for raw in rows:
        f = process(_RowLike(raw), deps, default_label=default_label)
        if f is not None:
            yield f


__all__ = [
    "DatasetResult",
    "FeatureStoreConfig",
    "build_dataset",
    "stream_features",
]