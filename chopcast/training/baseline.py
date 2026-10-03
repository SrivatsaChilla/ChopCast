"""Baseline training run: split -> fit -> evaluate.

This module owns the sequence, not the algorithm. The estimator lives
in `chopcast.models.baseline_sklearn`, the metrics in
`chopcast.evaluation`, the split in `chopcast.training.split`. Keeping
orchestration thin is what lets the transformer trainer reuse the same
split and produce a comparable report.

The trainer never sees `raw_text` — only the cleaned text the feature
pipeline produced. That is the structural half of the leakage
guarantee in ADR-0003.

See `docs/ROADMAP.md` Milestone 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from chopcast.config import (
    BaselineTrainConfig,
    LabelingConfig,
    SplitConfig,
    TextConfig,
)
from chopcast.errors import TrainingError
from chopcast.evaluation.report import EvaluationReport, evaluate
from chopcast.logging import get_logger
from chopcast.models.baseline_sklearn import BaselineSklearn
from chopcast.training.class_weights import describe_imbalance
from chopcast.training.split import Split, make_split

log = get_logger(__name__)


@dataclass(frozen=True)
class BaselineRun:
    """Everything one baseline training run produced.

    Frozen so it can be passed between modules — reporting, registry,
    comparison — without any of them mutating a shared result.
    """

    model: BaselineSklearn
    split: Split
    evaluation: EvaluationReport
    X_train: list[str]
    X_test: list[str]


def _partition(
    hashes: Sequence[str],
    texts: Sequence[str],
    labels: Sequence[str],
    split: Split,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Materialise the split into parallel text/label lists."""
    text_of = dict(zip(hashes, texts))
    label_of = dict(zip(hashes, labels))
    X_train = [text_of[h] for h in split.train_hashes]
    y_train = [label_of[h] for h in split.train_hashes]
    X_test = [text_of[h] for h in split.test_hashes]
    y_test = [label_of[h] for h in split.test_hashes]
    return X_train, y_train, X_test, y_test


def train_baseline(
    hashes: Sequence[str],
    texts: Sequence[str],
    labels: Sequence[str],
    *,
    split_cfg: SplitConfig,
    text_cfg: TextConfig,
    train_cfg: BaselineTrainConfig,
    labeling_cfg: LabelingConfig,
    feature_version: str,
    model_version: str,
) -> BaselineRun:
    """Split, fit a TF-IDF baseline, and evaluate on the held-out rows."""
    if not (len(hashes) == len(texts) == len(labels)):
        raise TrainingError(
            "hashes, texts and labels must be the same length, got "
            f"{len(hashes)}, {len(texts)}, {len(labels)}"
        )
    if not hashes:
        raise TrainingError("cannot train on an empty dataset")

    split = make_split(hashes, labels, config=split_cfg)
    X_train, y_train, X_test, y_test = _partition(hashes, texts, labels, split)

    if not X_train:
        raise TrainingError("split produced an empty training set")
    if not X_test:
        raise TrainingError(
            "split produced an empty test set; there is nothing to evaluate on"
        )

    missing = set(labels) - set(y_train)
    if missing:
        raise TrainingError(
            f"these classes are absent from the training set: {sorted(missing)}"
        )

    imbalance = describe_imbalance(y_train)
    log.info(
        "training.baseline.start",
        n_train=len(X_train),
        n_test=len(X_test),
        imbalance_ratio=round(imbalance["imbalance_ratio"], 2),
        split_version=split.version,
    )

    model = BaselineSklearn.train(
        list(X_train),
        list(y_train),
        tfidf=text_cfg.tfidf,
        train=train_cfg,
        model_version=model_version,
        feature_version=feature_version,
    )

    predictions = [str(p) for p in model.predict(list(X_test))]
    report = evaluate(
        list(y_test),
        predictions,
        model_version=model_version,
        feature_version=feature_version,
    )

    log.info(
        "training.baseline.complete",
        model_version=model_version,
        macro_f1=round(report.macro, 4),
        accuracy=round(report.acc, 4),
        majority_floor=round(imbalance["majority_baseline_accuracy"], 4),
    )
    return BaselineRun(
        model=model,
        split=split,
        evaluation=report,
        X_train=list(X_train),
        X_test=list(X_test),
    )


__all__ = ["BaselineRun", "train_baseline"]
