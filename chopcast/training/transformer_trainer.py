"""Transformer training run — Milestone 4, not yet implemented.

This module exists so the committed test suite can be collected and so
`TransformerRun` has a real definition for the comparison report to type
against. The validation paths are genuine; the training path raises.

Why a stub rather than nothing: a test file that cannot be imported
aborts collection for the *whole* suite, which means nobody runs any of
it. A module that validates its inputs and then says plainly that it is
unbuilt keeps the suite usable and keeps the gap visible.

The split is deliberately computed with the same `make_split` the
baseline uses. Comparing a transformer against a baseline is only
meaningful on an identical test partition, and the committed test
`test_train_transformer_uses_same_split_as_baseline` pins that.

See `docs/ROADMAP.md` Milestone 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from chopcast.config import (
    LabelingConfig,
    SplitConfig,
    TransformerTextConfig,
    TransformerTrainConfig,
)
from chopcast.evaluation.report import EvaluationReport
from chopcast.logging import get_logger
from chopcast.training.split import Split

log = get_logger(__name__)


@dataclass(frozen=True)
class TransformerRun:
    """Everything one transformer training run produced.

    Mirrors `chopcast.training.baseline.BaselineRun` so the comparison
    report can treat the two interchangeably. Frozen, so a result can be
    passed between reporting, registry and comparison without any of
    them mutating it.
    """

    model: Any
    split: Split
    evaluation: EvaluationReport
    X_train: list[str]
    X_test: list[str]


def train_transformer(
    hashes: Sequence[str],
    texts: Sequence[str],
    labels: Sequence[str],
    *,
    split_cfg: SplitConfig,
    text_cfg: TransformerTextConfig,
    train_cfg: TransformerTrainConfig,
    labeling_cfg: LabelingConfig,
    feature_version: str,
    model_version: str,
    output_dir: str | None = None,
) -> TransformerRun:
    """Fine-tune a transformer classifier. **Not yet implemented.**

    Inputs are validated first, so a caller with a malformed dataset
    learns that rather than learning only that the model is missing.
    """
    if not (len(hashes) == len(texts) == len(labels)):
        raise ValueError(
            "hashes, texts and labels must be the same length, got "
            f"{len(hashes)}, {len(texts)}, {len(labels)}"
        )
    if not hashes:
        raise ValueError("cannot train on an empty dataset")

    raise NotImplementedError(
        "transformer training is Milestone 4 and is not implemented yet. "
        "Use chopcast.training.baseline.train_baseline for the TF-IDF baseline."
    )


__all__ = ["TransformerRun", "train_transformer"]
