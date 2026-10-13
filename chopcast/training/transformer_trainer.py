"""End-to-end transformer training: split → fine-tune → evaluate.

This module is the transformer twin of `training.baseline`. Its public
function `train_transformer` returns a `TransformerRun` that bundles
the trained model, the split manifest, and the evaluation report.

Heavy imports (`torch`, `transformers`) are deferred to
`TransformerDistilbert.train`. The module itself imports cleanly even
when those packages are missing, so the type-check / import time stays
unaffected.

See `docs/MODULE_DESIGN.md` §8.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from chopcast.config import (
    LabelingConfig,
    SplitConfig,
    TransformerTextConfig,
    TransformerTrainConfig,
)
from chopcast.evaluation.report import EvaluationReport, evaluate
from chopcast.logging import get_logger
from chopcast.models.protocol import Model
from chopcast.models.transformer_distilbert import TransformerDistilbert
from chopcast.training.split import Split, make_split

log = get_logger(__name__)


@dataclass(frozen=True)
class TransformerRun:
    """The output of `train_transformer`."""

    model: TransformerDistilbert
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


def train_transformer(
    hashes: Sequence[str],
    X_text: Sequence[str],
    y: Sequence[str],
    *,
    split_cfg: SplitConfig,
    text_cfg: TransformerTextConfig,
    train_cfg: TransformerTrainConfig,
    labeling_cfg: LabelingConfig,
    feature_version: str,
    model_version: str,
    output_dir: str | None = None,
) -> TransformerRun:
    """Fine-tune a transformer model end-to-end.

    The wiring is identical to `train_baseline`:
        1. Split by hash (so the transformer and the baseline see the
           same train/test partition — this is what enables the
           comparison report downstream).
        2. Fine-tune on the train side.
        3. Evaluate on the test side.

    Args:
        output_dir: If supplied, the trained model is persisted to this
            directory. The path is also written into the transformer
            manifest.
    """
    from pathlib import Path

    if not hashes:
        raise ValueError("cannot train on empty dataset")
    if len({len(hashes), len(X_text), len(y)}) != 1:
        raise ValueError("hashes, X_text, y must have the same length")

    split = make_split(hashes, y, config=split_cfg)

    X_train, y_train = _materialise(hashes, X_text, y, split.train_hashes)
    X_test, y_test = _materialise(hashes, X_text, y, split.test_hashes)

    out_path: Path | None = Path(output_dir) if output_dir else None

    model = TransformerDistilbert.train(
        X_train,
        y_train,
        text_cfg=text_cfg,
        train_cfg=train_cfg,
        model_version=model_version,
        feature_version=feature_version,
        output_dir=out_path,
    )
    assert isinstance(model, Model)

    y_pred = list(model.predict(X_test))
    report = evaluate(
        y_test,
        y_pred,
        model_version=model_version,
        feature_version=feature_version,
        labels=sorted(set(y_train) | set(y_test)),
    )
    log.info(
        "transformer.run_complete",
        model_version=model_version,
        feature_version=feature_version,
        macro_f1=report.macro,
        weighted_f1=report.weighted,
        accuracy=report.acc,
    )
    return TransformerRun(
        model=model,
        split=split,
        evaluation=report,
        X_train=X_train,
        X_test=X_test,
    )


__all__ = ["TransformerRun", "train_transformer"]
