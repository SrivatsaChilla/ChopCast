"""Tests for chopcast.evaluation.metrics and report."""

from __future__ import annotations

import pytest

from chopcast.evaluation.metrics import (
    accuracy,
    compute_class_metrics,
    compute_confusion_matrix,
    macro_f1,
    weighted_f1,
)
from chopcast.evaluation.report import evaluate, to_markdown


# ---------------------------------------------------------------------------
# Confusions
# ---------------------------------------------------------------------------
def test_perfect_predictions() -> None:
    cm = compute_confusion_matrix(["A", "B", "C"], ["A", "B", "C"], ["A", "B", "C"])
    assert cm.labels == ("A", "B", "C")
    assert cm.matrix == ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    per = compute_class_metrics(cm)
    assert all(p.precision == 1.0 and p.recall == 1.0 and p.f1 == 1.0 for p in per)


def test_class_metrics_known_values() -> None:
    """Hand-crafted 2-class case with known F1."""
    y_true = ["A", "A", "B", "B"]
    y_pred = ["A", "B", "B", "B"]
    cm = compute_confusion_matrix(y_true, y_pred, ["A", "B"])
    # tp_A=1, fp_A=0, fn_A=1 -> P=1.0, R=0.5, F1=2/3
    # tp_B=2, fp_B=1, fn_B=0 -> P=2/3, R=1.0, F1=0.8
    per = compute_class_metrics(cm)
    by_label = {p.label: p for p in per}
    assert by_label["A"].precision == pytest.approx(1.0)
    assert by_label["A"].recall == pytest.approx(0.5)
    assert by_label["A"].f1 == pytest.approx(2 / 3)
    assert by_label["B"].precision == pytest.approx(2 / 3)
    assert by_label["B"].recall == pytest.approx(1.0)
    assert by_label["B"].f1 == pytest.approx(0.8)


def test_macro_and_weighted_f1() -> None:
    y_true = ["A", "A", "B", "B"]
    y_pred = ["A", "B", "B", "B"]
    cm = compute_confusion_matrix(y_true, y_pred, ["A", "B"])
    per = compute_class_metrics(cm)
    assert macro_f1(per) == pytest.approx((2 / 3 + 0.8) / 2)
    assert weighted_f1(per) == pytest.approx((2 / 3 * 2 + 0.8 * 2) / 4)


def test_accuracy() -> None:
    assert accuracy(["A", "B", "C"], ["A", "B", "A"]) == pytest.approx(2 / 3)
    assert accuracy([], []) == 0.0


def test_empty_class_metrics() -> None:
    per = compute_class_metrics(compute_confusion_matrix([], [], ["A"]))
    assert len(per) == 1
    assert per[0].precision == 0.0
    assert per[0].recall == 0.0


# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------
def test_evaluate_emits_report() -> None:
    report = evaluate(
        ["A", "A", "B", "B", "C", "C"],
        ["A", "B", "B", "B", "C", "A"],
        model_version="v1",
        feature_version="fv1",
    )
    assert report.model_version == "v1"
    assert report.feature_version == "fv1"
    assert report.n_samples == 6
    assert 0.0 <= report.acc <= 1.0
    assert 0.0 <= report.macro <= 1.0
    assert 0.0 <= report.weighted <= 1.0
    assert report.labels == ("A", "B", "C")


def test_evaluate_with_explicit_labels() -> None:
    # Even when a class doesn't appear in the data, it should be in
    # the report (with zero support).
    report = evaluate(
        ["A", "B"],
        ["A", "B"],
        model_version="v1",
        feature_version="fv1",
        labels=["A", "B", "C"],
    )
    assert "C" in report.labels
    c = next(p for p in report.per_class if p.label == "C")
    assert c.support == 0
    assert c.precision == 0.0
    assert c.recall == 0.0


def test_evaluate_length_mismatch() -> None:
    with pytest.raises(ValueError, match="same length"):
        evaluate(["A", "B"], ["A"], model_version="v", feature_version="fv")


# ---------------------------------------------------------------------------
# to_markdown
# ---------------------------------------------------------------------------
def test_to_markdown_contains_sections() -> None:
    report = evaluate(
        ["A", "B", "C", "A"],
        ["A", "B", "C", "B"],
        model_version="v1",
        feature_version="fv1",
    )
    md = to_markdown(report)
    assert "# Evaluation report" in md
    assert "Macro-F1" in md
    assert "Per-class metrics" in md
    assert "Confusion matrix" in md


def test_to_dict_is_serialisable() -> None:
    import json

    report = evaluate(["A", "B"], ["A", "B"], model_version="v", feature_version="fv")
    blob = json.dumps(report.to_dict())
    assert "model_version" in blob