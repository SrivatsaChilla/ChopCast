"""Tests for the transformer trainer.

The end-to-end fine-tuning path requires torch + transformers and is
skipped when those are missing. Validation errors are testable without
either, so we keep them at module scope.
"""

from __future__ import annotations

import pytest

from chopcast.config import (
    LabelingConfig,
    SplitConfig,
    TransformerTextConfig,
    TransformerTrainConfig,
)
from chopcast.training.transformer_trainer import TransformerRun, train_transformer


# ---------------------------------------------------------------------------
# Validation paths — runnable without torch / transformers
# ---------------------------------------------------------------------------
def test_train_transformer_rejects_empty_dataset() -> None:
    with pytest.raises(ValueError, match="empty dataset"):
        train_transformer(
            [], [], [],
            split_cfg=SplitConfig(),
            text_cfg=TransformerTextConfig(),
            train_cfg=TransformerTrainConfig(),
            labeling_cfg=LabelingConfig(),
            feature_version="fv1",
            model_version="v1",
        )


def test_train_transformer_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="same length"):
        train_transformer(
            ["h1", "h2"], ["a"], ["A"],
            split_cfg=SplitConfig(),
            text_cfg=TransformerTextConfig(),
            train_cfg=TransformerTrainConfig(),
            labeling_cfg=LabelingConfig(),
            feature_version="fv1",
            model_version="v1",
        )


def test_transformer_run_dataclass_is_frozen() -> None:
    """The TransformerRun dataclass is frozen so it can be safely reused
    as a return value across modules without mutation surprises.
    """
    import dataclasses
    from chopcast.evaluation.report import EvaluationReport
    from chopcast.evaluation.metrics import ConfusionMatrix
    from chopcast.training.split import Split

    report = EvaluationReport(
        model_version="v1",
        feature_version="fv1",
        labels=("A",),
        per_class=(),
        confusion=ConfusionMatrix(labels=("A",), matrix=((0,))),
        acc=0.0,
        macro=0.0,
        weighted=0.0,
        n_samples=0,
    )
    split = Split(
        train_hashes=(),
        test_hashes=(),
        train_labels=(),
        test_labels=(),
        version="v1",
        seed=0,
        config_version="v1",
        mode="stratified",
    )
    run = TransformerRun(
        model=object(),  # type: ignore[arg-type]
        split=split,
        evaluation=report,
        X_train=[],
        X_test=[],
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        run.X_train = ["x"]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# End-to-end — gated on torch / transformers
# ---------------------------------------------------------------------------
def _has_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _has_transformers() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _synthetic_corpus() -> tuple[list[str], list[str], list[str]]:
    hashes = [f"h{i}" for i in range(40)]
    texts: list[str] = []
    labels: list[str] = []
    for i in range(40):
        if i < 10:
            texts.append(f"chop light ride over sfo oak {i}")
            labels.append("Light")
        elif i < 20:
            texts.append(f"moderate chop ride over sfo oak {i}")
            labels.append("Moderate")
        elif i < 30:
            texts.append(f"severe turbulence ride over sfo oak {i}")
            labels.append("Severe")
        else:
            texts.append(f"smooth ride over sfo oak {i}")
            labels.append("None")
    return hashes, texts, labels


@pytest.mark.skipif(
    not (_has_torch() and _has_transformers()),
    reason="torch/transformers not installed",
)
def test_train_transformer_end_to_end(tmp_path) -> None:
    hashes, texts, labels = _synthetic_corpus()
    run = train_transformer(
        hashes, texts, labels,
        split_cfg=SplitConfig(mode="stratified", test_size=0.25, seed=42),
        text_cfg=TransformerTextConfig(),
        train_cfg=TransformerTrainConfig(),
        labeling_cfg=LabelingConfig(),
        feature_version="fv1",
        model_version="v1",
        output_dir=str(tmp_path / "model"),
    )
    assert run.model.model_kind == "transformer"
    assert run.evaluation.model_version == "v1"
    assert run.evaluation.n_samples == len(run.X_test)
    assert 0.0 <= run.evaluation.macro <= 1.0
    # Manifest written.
    assert (tmp_path / "model" / "chopcast_manifest.txt").exists()


@pytest.mark.skipif(
    not (_has_torch() and _has_transformers()),
    reason="torch/transformers not installed",
)
def test_train_transformer_uses_same_split_as_baseline() -> None:
    """If we train a baseline and a transformer on the same split_cfg, the
    resulting test partitions should be identical. This is what enables
    the comparison report to compare apples-to-apples.
    """
    from chopcast.training.split import make_split

    hashes, texts, labels = _synthetic_corpus()
    cfg = SplitConfig(mode="stratified", test_size=0.25, seed=42)
    run = train_transformer(
        hashes, texts, labels,
        split_cfg=cfg,
        text_cfg=TransformerTextConfig(),
        train_cfg=TransformerTrainConfig(),
        labeling_cfg=LabelingConfig(),
        feature_version="fv1",
        model_version="v1",
    )
    expected = make_split(hashes, labels, config=cfg)
    assert run.split.test_hashes == expected.test_hashes
