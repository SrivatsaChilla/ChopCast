"""End-to-end baseline training: load features → split → train → evaluate.

The single public function is `train_baseline(features, cfg, ...)`.
It returns a `BaselineRun` that bundles the model, the evaluation
report, and the split manifest. The caller (the CLI or a notebook)
is responsible for persisting these to disk.

See `docs/MODULE_DESIGN.md` §8.2.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from chopcast.config import (
    BaselineTrainConfig,
    LabelingConfig,
    SplitConfig,
    TextConfig,
)
from chopcast.evaluation.report import EvaluationReport, evaluate
from chopcast.logging import get_logger
from chopcast.models.baseline_sklearn import BaselineSklearn
from chopcast.training.split import Split, make_split

log = get_logger(__name__)


@dataclass(frozen=True)
class BaselineRun:
    """The output of `train_baseline`."""

    model: BaselineSklearn
    split: Split
    evaluation: EvaluationReport
    X_train: list[str]
    X_test: list[str]

def _materialise(
    hashes: Sequence[str], X_text: Sequence[str], y: Sequence[str], wanted: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Pick the rows whose hash is in `wanted`, preserving order."""
    by_hash = {h: (t, l) for h, t, l in zip(hashes, X_text, y)}
    xs: list[str] = []
    ys: list[str] = []
    for h in wanted:
        if h not in by_hash:
            raise KeyError(f"hash {h!r} not present in feature store")
        t, l = by_hash[h]
        xs.append(t)
        ys.append(l)
    return xs, ys


def train_baseline(
    hashes: Sequence[str],
    X_text: Sequence[str],
    y: Sequence[str],
    *,
    split_cfg: SplitConfig,
    text_cfg: TextConfig,
    train_cfg: BaselineTrainConfig,
    labeling_cfg: LabelingConfig,
    feature_version: str,
    model_version: str,
) -> BaselineRun:
    """Train a baseline model end-to-end.

    `hashes`, `X_text`, and `y` are parallel sequences. We split them
    by hash so the split is reproducible, then train on the train
    side and evaluate on the test side.
    """
    if not hashes:
        raise ValueError("cannot train on empty dataset")
    if len({len(hashes), len(X_text), len(y)}) != 1:
        raise ValueError("hashes, X_text, y must have the same length")

    split = make_split(hashes, y, config=split_cfg)

    X_train, y_train = _materialise(hashes, X_text, y, split.train_hashes)
    X_test, y_test = _materialise(hashes, X_text, y, split.test_hashes)

    model = BaselineSklearn.train(
        X_train,
        y_train,
        tfidf=text_cfg.tfidf,
        train=train_cfg,
        model_version=model_version,
        feature_version=feature_version,
    )

    y_pred = list(model.predict(X_test))
    report = evaluate(
        y_test,
        y_pred,
        model_version=model_version,
        feature_version=feature_version,
        labels=sorted(set(y_train) | set(y_test)),
    )
    log.info(
        "baseline.run_complete",
        model_version=model_version,
        feature_version=feature_version,
        macro_f1=report.macro,
        weighted_f1=report.weighted,
        accuracy=report.acc,
    )
    return BaselineRun(
        model=model,
        split=split,
        evaluation=report,
        X_train=X_train,
        X_test=X_test,
    )


__all__ = ["BaselineRun", "train_baseline"]