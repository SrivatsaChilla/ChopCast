"""Class-imbalance handling.

Turbulence severity is heavily skewed: Light and None dominate, Severe
is scarce. Left alone, a classifier maximises accuracy by predicting
the majority class and never predicting the class that matters most.

ADR note: we default to class weights rather than resampling. Weights
change the loss without inventing or discarding observations, which
keeps the training set honest about how little Severe data exists.
SMOTE is available behind config but synthesises text-space neighbours
that have no physical meaning for a PIREP.

See `docs/ROADMAP.md` Milestone 3.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from chopcast.config import ImbalanceConfig
from chopcast.errors import TrainingError
from chopcast.logging import get_logger

log = get_logger(__name__)


def compute_class_weights(labels: Sequence[str]) -> Mapping[str, float]:
    """Balanced weights: `n_samples / (n_classes * count)`.

    This is scikit-learn's "balanced" formula, computed explicitly so
    the values can be logged, asserted on, and stored in the registry
    rather than hidden inside an estimator.
    """
    if not labels:
        # An empty label set has no classes to weight. Returning {} lets a
        # caller pass the result straight to an estimator without a guard;
        # the empty-dataset error belongs to the trainer, not here.
        return {}

    counts = Counter(labels)
    n_samples = len(labels)
    n_classes = len(counts)
    return {
        label: n_samples / (n_classes * count)
        for label, count in sorted(counts.items())
    }


def describe_imbalance(labels: Sequence[str]) -> dict[str, float]:
    """Summary numbers worth recording next to a model.

    `imbalance_ratio` is the majority/minority count ratio — the single
    figure that explains why accuracy is the wrong headline metric.
    """
    if not labels:
        raise TrainingError("cannot describe an empty label set")

    counts = Counter(labels)
    majority = max(counts.values())
    minority = min(counts.values())
    return {
        "n_samples": float(len(labels)),
        "n_classes": float(len(counts)),
        "majority_count": float(majority),
        "minority_count": float(minority),
        "imbalance_ratio": majority / minority,
        "majority_baseline_accuracy": majority / len(labels),
    }


def resolve_class_weight(cfg: ImbalanceConfig) -> str | None:
    """Translate the configured strategy into sklearn's `class_weight`.

    Returns the value to hand an estimator: `"balanced"`, or `None` to
    leave the loss untouched.
    """
    if cfg.strategy == "class_weight":
        return "balanced"
    if cfg.strategy == "none":
        return None
    if cfg.strategy == "smote":
        # Deliberately not silently downgraded: a caller asking for SMOTE
        # should find out here, not discover later that it never ran.
        raise TrainingError(
            "imbalance strategy 'smote' is not implemented for the text baseline; "
            "use 'class_weight' or 'none'"
        )
    raise TrainingError(f"unknown imbalance strategy: {cfg.strategy!r}")


__all__ = ["compute_class_weights", "describe_imbalance", "resolve_class_weight"]
