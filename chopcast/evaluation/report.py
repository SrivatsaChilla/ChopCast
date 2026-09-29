"""Evaluation report data shape and Markdown renderer.

`EvaluationReport` is the canonical structured form. `to_markdown()`
renders it as a human-readable Markdown document. Both are pure
functions of the underlying metrics — no I/O, no randomness.

See `docs/MODULE_DESIGN.md` §9.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from chopcast.evaluation.metrics import (
    ClassMetrics,
    ConfusionMatrix,
    accuracy,
    macro_f1,
    weighted_f1,
)


@dataclass(frozen=True)
class EvaluationReport:
    """The result of evaluating a model on a labelled test set."""

    model_version: str
    feature_version: str
    labels: tuple[str, ...]
    per_class: tuple[ClassMetrics, ...]
    confusion: ConfusionMatrix
    acc: float
    macro: float
    weighted: float
    n_samples: int
    extras: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "labels": list(self.labels),
            "per_class": [
                {
                    "label": c.label,
                    "precision": c.precision,
                    "recall": c.recall,
                    "f1": c.f1,
                    "support": c.support,
                }
                for c in self.per_class
            ],
            "confusion": {
                "labels": list(self.confusion.labels),
                "matrix": [list(row) for row in self.confusion.matrix],
            },
            "accuracy": self.acc,
            "macro_f1": self.macro,
            "weighted_f1": self.weighted,
            "n_samples": self.n_samples,
            "extras": dict(self.extras),
        }


def evaluate(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    *,
    model_version: str,
    feature_version: str,
    labels: Sequence[str] | None = None,
) -> EvaluationReport:
    """Compute all metrics at once.

    `labels` defaults to the sorted unique union of `y_true` and
    `y_pred`, which is what we want for stratified evaluation.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"y_true and y_pred must have the same length, "
            f"got {len(y_true)} vs {len(y_pred)}"
        )
    if labels is None:
        labels = sorted({*y_true, *y_pred})
    if not labels:
        # No data, no labels: emit a degenerate report.
        labels = ("None",)
    cm = _compute_confusion(y_true, y_pred, labels)
    per_class = _class_metrics(cm)
    return EvaluationReport(
        model_version=model_version,
        feature_version=feature_version,
        labels=tuple(labels),
        per_class=tuple(per_class),
        confusion=cm,
        acc=accuracy(y_true, y_pred),
        macro=macro_f1(per_class),
        weighted=weighted_f1(per_class),
        n_samples=len(y_true),
    )


def _compute_confusion(
    y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str]
) -> ConfusionMatrix:
    from chopcast.evaluation.metrics import compute_confusion_matrix
    return compute_confusion_matrix(y_true, y_pred, labels)


def _class_metrics(cm: ConfusionMatrix) -> list[ClassMetrics]:
    from chopcast.evaluation.metrics import compute_class_metrics
    return compute_class_metrics(cm)


def to_markdown(report: EvaluationReport) -> str:
    """Render an `EvaluationReport` as Markdown."""
    lines: list[str] = []
    lines.append(f"# Evaluation report — {report.model_version}")
    lines.append("")
    lines.append(f"- **Feature version**: `{report.feature_version}`")
    lines.append(f"- **Samples**: {report.n_samples}")
    lines.append(f"- **Accuracy**: {report.acc:.4f}")
    lines.append(f"- **Macro-F1**: {report.macro:.4f}")
    lines.append(f"- **Weighted-F1**: {report.weighted:.4f}")
    lines.append("")
    lines.append("## Per-class metrics")
    lines.append("")
    lines.append("| Label | Precision | Recall | F1 | Support |")
    lines.append("|---|---|---|---|---|")
    for c in report.per_class:
        lines.append(
            f"| {c.label} | {c.precision:.4f} | {c.recall:.4f} | {c.f1:.4f} | {c.support} |"
        )
    lines.append("")
    lines.append("## Confusion matrix")
    lines.append("")
    header = "| true \\ pred | " + " | ".join(report.labels) + " |"
    sep = "|---|" + "|".join(["---"] * len(report.labels)) + "|"
    lines.append(header)
    lines.append(sep)
    for i, row in enumerate(report.confusion.matrix):
        lines.append(f"| {report.labels[i]} | " + " | ".join(str(v) for v in row) + " |")
    lines.append("")
    return "\n".join(lines)


__all__ = ["EvaluationReport", "evaluate", "to_markdown"]