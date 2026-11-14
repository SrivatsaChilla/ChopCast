"""Train/test splitting with a reproducible, serialisable `Split`.

A split you cannot reproduce is a split you cannot defend: every
reported metric depends on which rows landed in test, so the assignment
has to be derivable from (hashes, labels, config) alone and storable
alongside the model.

Two modes matter here. `stratified` preserves class proportions, which
is what the imbalance in turbulence severity demands. `time` holds out
the most recent rows, which is the honest evaluation for a model that
will be asked about the future — and usually scores worse, because it
cannot borrow context from reports either side of the ones it predicts.

Rare classes are a live problem in this dataset: Severe turbulence is
genuinely scarce, and a class with one member cannot appear in both
splits. The last member of a class is never split off into test, so a
class is never lost from training entirely.

See `docs/ROADMAP.md` Milestone 3.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Sequence

from chopcast.config import SplitConfig
from chopcast.errors import TrainingError
from chopcast.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Split:
    """One reproducible train/test assignment."""

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

    def to_dict(self) -> dict:
        return {
            "train_hashes": list(self.train_hashes),
            "test_hashes": list(self.test_hashes),
            "train_labels": list(self.train_labels),
            "test_labels": list(self.test_labels),
            "version": self.version,
            "seed": self.seed,
            "config_version": self.config_version,
            "mode": self.mode,
        }


def _config_version(config: SplitConfig) -> str:
    """A stable id for the config that produced a split.

    Changing any knob changes this, so a stored split can be checked
    against the config a later run claims to have used.
    """
    payload = json.dumps(
        {"mode": config.mode, "test_size": config.test_size, "seed": config.seed},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _split_version(train: Sequence[str], test: Sequence[str], config_version: str) -> str:
    payload = json.dumps(
        {"train": sorted(train), "test": sorted(test), "config": config_version},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _assemble(
    train: Sequence[str],
    test: Sequence[str],
    label_of: dict[str, str],
    config: SplitConfig,
) -> Split:
    cfg_version = _config_version(config)
    return Split(
        train_hashes=tuple(train),
        test_hashes=tuple(test),
        train_labels=tuple(label_of[h] for h in train),
        test_labels=tuple(label_of[h] for h in test),
        version=_split_version(train, test, cfg_version),
        seed=config.seed,
        config_version=cfg_version,
        mode=config.mode,
    )


def _stratified(
    hashes: Sequence[str], labels: Sequence[str], config: SplitConfig
) -> tuple[list[str], list[str]]:
    by_label: dict[str, list[str]] = defaultdict(list)
    for h, y in zip(hashes, labels):
        by_label[y].append(h)

    rng = Random(config.seed)
    train: list[str] = []
    test: list[str] = []

    for label in sorted(by_label):
        members = list(by_label[label])
        rng.shuffle(members)
        # Never split off the last member of a class: a class the model
        # has never seen is worse than a class the test set lacks.
        n_test = int(round(len(members) * config.test_size))
        n_test = min(n_test, len(members) - 1)
        n_test = max(n_test, 0)
        test.extend(members[:n_test])
        train.extend(members[n_test:])

    return train, test


def _time_ordered(
    hashes: Sequence[str], config: SplitConfig
) -> tuple[list[str], list[str]]:
    """Hold out the tail. `hashes` is assumed already in time order."""
    n_test = int(round(len(hashes) * config.test_size))
    n_test = min(n_test, len(hashes))
    cut = len(hashes) - n_test
    return list(hashes[:cut]), list(hashes[cut:])


def make_split(
    hashes: Sequence[str],
    labels: Sequence[str],
    *,
    config: SplitConfig,
) -> Split:
    """Assign every hash to train or test according to `config`.

    An empty dataset yields an empty split rather than an error: callers
    that genuinely cannot train raise on their own terms, with a message
    about training rather than about splitting.
    """
    if len(hashes) != len(labels):
        raise TrainingError(
            f"hashes and labels must be the same length, got {len(hashes)} vs {len(labels)}"
        )
    if not 0.0 < config.test_size < 1.0:
        raise TrainingError(
            f"test_size must be strictly between 0 and 1, got {config.test_size}"
        )

    label_of = dict(zip(hashes, labels))
    if not hashes:
        return _assemble([], [], label_of, config)

    if config.mode == "stratified":
        train, test = _stratified(hashes, labels, config)
    elif config.mode == "time":
        train, test = _time_ordered(hashes, config)
    elif config.mode == "spatiotemporal":
        # Not implemented: fail loudly rather than quietly fall back to
        # stratified and report metrics from a different split than asked for.
        raise TrainingError(
            "split mode 'spatiotemporal' is not implemented; use 'stratified' or 'time'"
        )
    else:
        raise TrainingError(f"unknown split mode: {config.mode!r}")

    split = _assemble(train, test, label_of, config)
    log.info(
        "training.split.complete",
        mode=config.mode,
        n_train=split.n_train,
        n_test=split.n_test,
        version=split.version,
    )
    return split


def save_split(split: Split, path: Path) -> None:
    """Write a split as JSON next to the model it produced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(split.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def load_split(path: Path) -> Split:
    """Read a split written by `save_split`."""
    path = Path(path)
    if not path.exists():
        raise TrainingError(f"split file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise TrainingError(f"{path} is not valid JSON: {e}") from e

    try:
        return Split(
            train_hashes=tuple(data["train_hashes"]),
            test_hashes=tuple(data["test_hashes"]),
            train_labels=tuple(data["train_labels"]),
            test_labels=tuple(data["test_labels"]),
            version=data["version"],
            seed=int(data["seed"]),
            config_version=data["config_version"],
            mode=data["mode"],
        )
    except KeyError as e:
        raise TrainingError(f"{path} is missing field {e}") from e


__all__ = ["Split", "make_split", "save_split", "load_split"]
