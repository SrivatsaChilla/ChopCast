"""Load a model-ready dataset from the feature store.

The feature store writes newline-delimited `FeatureRow` records. This
module reads them back and nothing else: no cleaning, no labelling, no
text manipulation. Those belong upstream, and keeping them out of here
is what makes the leakage guarantee in ADR-0003 checkable — a trainer
that never sees `raw_text` cannot leak it.

See `docs/DATA_ENGINEERING.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from chopcast.errors import TrainingError
from chopcast.logging import get_logger

log = get_logger(__name__)

# The only fields a trainer is allowed to depend on. `raw_text` is
# absent by design.
REQUIRED_FIELDS = ("hash", "clean_text", "severity_label")


@dataclass(frozen=True)
class TrainingDataset:
    """Parallel arrays plus the ids needed to reproduce a split."""

    hashes: tuple[str, ...]
    texts: tuple[str, ...]
    labels: tuple[str, ...]
    feature_version: str
    source_path: Path

    def __len__(self) -> int:
        return len(self.hashes)

    def subset(self, keep: Sequence[str]) -> "TrainingDataset":
        """A new dataset containing only `keep`, in this dataset's order.

        Returns a new object; the original is untouched.
        """
        wanted = set(keep)
        idx = [i for i, h in enumerate(self.hashes) if h in wanted]
        return TrainingDataset(
            hashes=tuple(self.hashes[i] for i in idx),
            texts=tuple(self.texts[i] for i in idx),
            labels=tuple(self.labels[i] for i in idx),
            feature_version=self.feature_version,
            source_path=self.source_path,
        )


def _iter_rows(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise TrainingError(f"{path}: line {lineno} is not valid JSON: {e}") from e


def load_dataset(path: Path, *, feature_version: str = "") -> TrainingDataset:
    """Read a feature-store `.jsonl` into a `TrainingDataset`.

    Rows missing a required field, or carrying an empty label or empty
    text, are skipped and counted — an unlabelled row is not a training
    example, and an empty one teaches nothing.
    """
    if not path.exists():
        raise TrainingError(f"feature dataset not found: {path}")

    hashes: list[str] = []
    texts: list[str] = []
    labels: list[str] = []
    skipped = 0

    for row in _iter_rows(path):
        if any(f not in row for f in REQUIRED_FIELDS):
            skipped += 1
            continue
        text = (row.get("clean_text") or "").strip()
        label = (row.get("severity_label") or "").strip()
        if not text or not label:
            skipped += 1
            continue
        hashes.append(row["hash"])
        texts.append(text)
        labels.append(label)

    if not hashes:
        raise TrainingError(
            f"{path} yielded no usable rows "
            f"({skipped} skipped for missing text or label)"
        )

    version = feature_version or _version_from_filename(path)
    log.info(
        "training.dataset.loaded",
        path=str(path),
        rows=len(hashes),
        skipped=skipped,
        feature_version=version,
    )
    return TrainingDataset(
        hashes=tuple(hashes),
        texts=tuple(texts),
        labels=tuple(labels),
        feature_version=version,
        source_path=path,
    )


def _version_from_filename(path: Path) -> str:
    """Recover the dataset version the feature store encoded in the name.

    `features_<version>.jsonl` -> `<version>`; anything else -> "unknown",
    which is recorded rather than guessed.
    """
    stem = path.stem
    prefix = "features_"
    return stem[len(prefix):] if stem.startswith(prefix) else "unknown"


def latest_dataset(features_dir: Path) -> Path:
    """The most recently modified `features_*.jsonl` in `features_dir`."""
    if not features_dir.exists():
        raise TrainingError(f"features directory does not exist: {features_dir}")
    candidates = sorted(
        features_dir.glob("features_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise TrainingError(
            f"no features_*.jsonl in {features_dir} — run the feature build first"
        )
    return candidates[0]


__all__ = ["TrainingDataset", "load_dataset", "latest_dataset", "REQUIRED_FIELDS"]
