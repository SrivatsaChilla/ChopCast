"""Per-class and aggregate metrics.

We compute everything from raw counts so the output is exactly
reproducible from a confusion matrix. We do NOT use sklearn's
metrics directly because their output is a numpy array — we want
plain Python types so the report is easy to serialise and compare.

See `docs/MODULE_DESIGN.md` §9.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ClassMetrics:
    """Per-class metrics."""

    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class ConfusionMatrix:
    """Confusion matrix as a labelled square.

    `labels[i]` is the row/column header for index `i`. `matrix[i][j]`
    is the count of true-class-`i` predicted-as-class-`j`.
    """

    labels: tuple[str, ...]
    matrix: tuple[tuple[int, ...], ...]


def _safe_div(num: float, den: float) -> float:
    return num / den if den > 0 else 0.0


def compute_confusion_matrix(
    y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str]
) -> ConfusionMatrix:
    """Build a labelled confusion matrix.

    `labels` defines the class ordering; rows/columns not present in
    the data are still part of the matrix (filled with zeros).
    """
    label_to_idx = {label: i for i, label in enumerate(labels)}
    n = len(labels)
    grid: list[list[int]] = [[0] * n for _ in range(n)]
    for t, p in zip(y_true, y_pred):
        ti = label_to_idx.get(t)
        pi = label_to_idx.get(p)
        if ti is None or pi is None:
            # Unknown label; we count it under a synthetic bucket but
            # only if it was emitted by the predictor. The cleanest
            # move is to log and skip — we never expect this in tests.
            continue
        grid[ti][pi] += 1
    return ConfusionMatrix(
        labels=tuple(labels),
        matrix=tuple(tuple(row) for row in grid),
    )


def compute_class_metrics(cm: ConfusionMatrix) -> list[ClassMetrics]:
    """Compute per-class precision/recall/F1/support from a confusion matrix."""
    out: list[ClassMetrics] = []
    n = len(cm.labels)
    for i, label in enumerate(cm.labels):
        tp = cm.matrix[i][i]
        fp = sum(cm.matrix[r][i] for r in range(n) if r != i)
        fn = sum(cm.matrix[i][c] for c in range(n) if c != i)
        support = sum(cm.matrix[i])
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        out.append(ClassMetrics(label=label, precision=precision, recall=recall, f1=f1, support=support))
    return out


def macro_f1(per_class: Sequence[ClassMetrics]) -> float:
    if not per_class:
        return 0.0
    return sum(c.f1 for c in per_class) / len(per_class)


def weighted_f1(per_class: Sequence[ClassMetrics]) -> float:
    total = sum(c.support for c in per_class)
    if total == 0:
        return 0.0
    return sum(c.f1 * c.support for c in per_class) / total


def accuracy(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    if not y_true:
        return 0.0
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


__all__ = [
    "ClassMetrics",
    "ConfusionMatrix",
    "accuracy",
    "compute_class_metrics",
    "compute_confusion_matrix",
    "macro_f1",
    "weighted_f1",
]