"""Stratified train/test split with deterministic manifest.

The split is deterministic for a given `(seed, version)`: re-running
with the same inputs produces the same manifest. The manifest is
saved alongside the dataset so a future training run can recover
the exact train/test split used for evaluation.

We support two split modes:
- `stratified` — sklearn-like stratified split.
- `time` — chronological split (oldest goes to train).

`time` is what we want once we have enough longitudinal data; for
M3 we use `stratified`.

See `docs/MODULE_DESIGN.md` §8.1.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from chopcast.config import SplitConfig
from chopcast.errors import ValidationError


@dataclass(frozen=True)
class Split:
    """A stratified train/test split."""

    train_hashes: tuple[str, ...]
    test_hashes: tuple[str, ...]
    train_labels: tuple[str, ...]
    test_labels: tuple[str, ...]
    version: str
    seed: int
    config_version: str
    mode: str

    @property
    def n_train(self) -> int:
        return len(self.train_hashes)

    @property
    def n_test(self) -> int:
        return len(self.test_hashes)


def _stratified_split(
    hashes: Sequence[str],
    labels: Sequence[str],
    *,
    test_size: float,
    seed: int,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (train_h, test_h, train_y, test_y) preserving class proportions.

    Implementation: for each class, shuffle its indices with the given
    seed and put `round(test_size * n_class)` items in the test set.
    """
    if not 0.0 < test_size < 1.0:
        raise ValidationError(f"test_size must be in (0, 1), got {test_size}")
    import random

    by_class: dict[str, list[int]] = {}
    for i, label in enumerate(labels):
        by_class.setdefault(label, []).append(i)
    if not by_class:
        return [], [], [], []
    rng = random.Random(seed)
    train_idx: list[int] = []
    test_idx: list[int] = []
    for indices in by_class.values():
        rng.shuffle(indices)
        n_test = max(1, round(len(indices) * test_size)) if len(indices) >= 2 else 0
        test_idx.extend(indices[:n_test])
        train_idx.extend(indices[n_test:])
    rng.shuffle(train_idx)
    rng.shuffle(test_idx)
    return (
        [hashes[i] for i in train_idx],
        [hashes[i] for i in test_idx],
        [labels[i] for i in train_idx],
        [labels[i] for i in test_idx],
    )


def _time_split(
    hashes: Sequence[str],
    labels: Sequence[str],
    *,
    test_size: float,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Chronological split. Caller pre-sorts by `obs_time` and passes
    the already-sorted sequences."""
    if not 0.0 < test_size < 1.0:
        raise ValidationError(f"test_size must be in (0, 1), got {test_size}")
    n_test = max(1, round(len(hashes) * test_size))
    n_train = len(hashes) - n_test
    return (
        list(hashes[:n_train]),
        list(hashes[n_train:]),
        list(labels[:n_train]),
        list(labels[n_train:]),
    )


def make_split(
    hashes: Sequence[str],
    labels: Sequence[str],
    *,
    config: SplitConfig,
    version: str = "v1",
) -> Split:
    """Build a split. `hashes` and `labels` are parallel sequences."""
    if len(hashes) != len(labels):
        raise ValidationError(
            f"hashes and labels must have the same length, got {len(hashes)} vs {len(labels)}"
        )
    if not hashes:
        return Split(
            train_hashes=(),
            test_hashes=(),
            train_labels=(),
            test_labels=(),
            version=version,
            seed=config.seed,
            config_version=version,
            mode=config.mode,
        )
    if config.mode == "stratified":
        th, eh, ty, ey = _stratified_split(
            hashes, labels, test_size=config.test_size, seed=config.seed
        )
    elif config.mode == "time":
        th, eh, ty, ey = _time_split(hashes, labels, test_size=config.test_size)
    else:
        raise ValidationError(f"unknown split mode: {config.mode!r}")
    return Split(
        train_hashes=tuple(th),
        test_hashes=tuple(eh),
        train_labels=tuple(ty),
        test_labels=tuple(ey),
        version=version,
        seed=config.seed,
        config_version=version,
        mode=config.mode,
    )


def save_split(split: Split, path: Path) -> None:
    """Write a split manifest as JSON. We use JSON so it's diff-friendly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(split)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_split(path: Path) -> Split:
    """Load a split manifest. Returns a `Split`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Split(
        train_hashes=tuple(payload["train_hashes"]),
        test_hashes=tuple(payload["test_hashes"]),
        train_labels=tuple(payload["train_labels"]),
        test_labels=tuple(payload["test_labels"]),
        version=payload["version"],
        seed=payload["seed"],
        config_version=payload["config_version"],
        mode=payload["mode"],
    )


__all__ = ["Split", "load_split", "make_split", "save_split"]