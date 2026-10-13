"""Class-imbalance helpers.

For M3 we rely on scikit-learn's built-in `class_weight="balanced"`
option on LogReg/LinearSVC. The single helper here is `compute_class_weights`
which returns a `{label: weight}` dict using the same formula as
sklearn (`n_samples / (n_classes * n_per_class)`), for cases where
a future model kind wants raw weights instead of the magic string.

See `docs/MODULE_DESIGN.md` §8.3.
"""

from __future__ import annotations

from typing import Mapping, Sequence


def compute_class_weights(y: Sequence[str]) -> dict[str, float]:
    """Compute inverse-frequency class weights.

    `weight[c] = n_total / (n_classes * count[c])`.

    A class with zero samples gets weight 0.0 (caller is expected
    to drop such classes before training).
    """
    if not y:
        return {}
    counts: dict[str, int] = {}
    for label in y:
        counts[label] = counts.get(label, 0) + 1
    n_total = len(y)
    n_classes = len(counts)
    weights = {
        label: (n_total / (n_classes * count) if count > 0 else 0.0)
        for label, count in counts.items()
    }
    return weights

def to_sklearn_dict(weights: Mapping[str, float]) -> dict[str, float]:
    """Plain dict for scikit-learn's `class_weight=` argument."""
    return dict(weights)


__all__ = ["compute_class_weights", "to_sklearn_dict"]