"""Tests for the TF-IDF + LogReg baseline trainer.

These tests require scikit-learn. They are skipped if sklearn is not
installed so the suite stays green on minimal installs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chopcast.config import (
    BaselineTrainConfig,
    LabelingConfig,
    SplitConfig,
    TextConfig,
    TfidfConfig,
)
from chopcast.models.baseline_sklearn import BaselineSklearn
from chopcast.models.protocol import Model
from chopcast.training.baseline import train_baseline
from chopcast.training.class_weights import compute_class_weights


def _has_sklearn() -> bool:
    try:
        import sklearn  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _has_sklearn(), reason="scikit-learn not installed"
)


# ---------------------------------------------------------------------------
# Train / predict / save / load
# ---------------------------------------------------------------------------
def _synthetic_corpus() -> tuple[list[str], list[str], list[str]]:
    hashes = [f"h{i}" for i in range(40)]
    texts = []
    labels = []
    for i in range(40):
        # 10 of each class.
        if i < 10:
            text = f"chop light ride over sfo oak {i} /ov sfo"
            label = "Light"
        elif i < 20:
            text = f"moderate chop ride over sfo oak {i} /ov oak"
            label = "Moderate"
        elif i < 30:
            text = f"severe turbulence ride over sfo oak {i} /ov sjc"
            label = "Severe"
        else:
            text = f"smooth ride over sfo oak {i} /ov sfo"
            label = "None"
        texts.append(text)
        labels.append(label)
    return hashes, texts, labels


def test_baseline_trains_and_predicts() -> None:
    hashes, texts, labels = _synthetic_corpus()
    model = BaselineSklearn.train(
        texts, labels,
        tfidf=TfidfConfig(),
        train=BaselineTrainConfig(),
        model_version="v1",
        feature_version="fv1",
    )
    assert isinstance(model, Model)
    assert model.model_kind == "baseline"
    preds = list(model.predict(texts))
    assert len(preds) == len(texts)
    assert set(preds) <= {"None", "Light", "Moderate", "Severe"}


def test_baseline_round_trip_save_load(tmp_path: Path) -> None:
    hashes, texts, labels = _synthetic_corpus()
    model = BaselineSklearn.train(
        texts, labels,
        tfidf=TfidfConfig(),
        train=BaselineTrainConfig(),
        model_version="v1",
        feature_version="fv1",
    )
    out = tmp_path / "model"
    model.save(out)
    loaded = BaselineSklearn.load(out)
    assert loaded.model_version == "v1"
    assert loaded.feature_version == "fv1"
    # Predictions match.
    preds_orig = list(model.predict(texts))
    preds_loaded = list(loaded.predict(texts))
    assert preds_orig == preds_loaded


def test_train_baseline_end_to_end() -> None:
    hashes, texts, labels = _synthetic_corpus()
    run = train_baseline(
        hashes, texts, labels,
        split_cfg=SplitConfig(mode="stratified", test_size=0.25, seed=42),
        text_cfg=TextConfig(),
        train_cfg=BaselineTrainConfig(),
        labeling_cfg=LabelingConfig(),
        feature_version="fv1",
        model_version="v1",
    )
    assert run.model.model_kind == "baseline"
    assert run.evaluation.model_version == "v1"
    assert run.evaluation.n_samples == len(run.X_test)
    assert 0.0 <= run.evaluation.macro <= 1.0
    # On a clearly separable synthetic corpus, accuracy should be > 0.7.
    assert run.evaluation.acc > 0.7


def test_baseline_empty_dataset_raises() -> None:
    with pytest.raises(ValueError):
        BaselineSklearn.train(
            [], [],
            tfidf=TfidfConfig(),
            train=BaselineTrainConfig(),
            model_version="v",
            feature_version="fv",
        )


def test_baseline_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        BaselineSklearn.train(
            ["a"], ["A", "B"],
            tfidf=TfidfConfig(),
            train=BaselineTrainConfig(),
            model_version="v",
            feature_version="fv",
        )


def test_baseline_predict_proba_shape() -> None:
    hashes, texts, labels = _synthetic_corpus()
    model = BaselineSklearn.train(
        texts, labels,
        tfidf=TfidfConfig(),
        train=BaselineTrainConfig(),
        model_version="v1",
        feature_version="fv1",
    )
    proba = model.predict_proba(["new text"])
    assert proba.shape == (1, len(model.classes()))


# ---------------------------------------------------------------------------
# Class weights
# ---------------------------------------------------------------------------
def test_compute_class_weights_balanced() -> None:
    y = ["A"] * 8 + ["B"] * 2
    w = compute_class_weights(y)
    # A is common -> low weight. B is rare -> high weight.
    assert w["B"] > w["A"]
    # Weights are inverse-frequency times n_total / n_classes.
    # A: 10 / (2 * 8) = 0.625; B: 10 / (2 * 2) = 2.5.
    assert w["A"] == pytest.approx(0.625)
    assert w["B"] == pytest.approx(2.5)


def test_compute_class_weights_empty() -> None:
    assert compute_class_weights([]) == {}