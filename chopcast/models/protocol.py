"""The model Protocol.

Every model in ChopCast implements this interface. The Protocol is
`runtime_checkable` so tests can substitute a stub without subclassing.

The `feature_version` attribute ties a model to the dataset version
that trained it. Loading a model with a mismatched feature version
should raise (we enforce this in the registry).

See `docs/ML_ARCHITECTURE.md` §2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Model(Protocol):
    """The contract every trained model must satisfy.

    Attributes:
        model_version: A short string identifying this model instance
            (e.g. "v3"). Combined with the registry row id it uniquely
            names a model.
        model_kind: One of "baseline", "transformer", "stub".
        feature_version: The dataset version string this model was
            trained on. Used to refuse to load with a mismatched
            dataset.

    Methods:
        predict: Hard predictions. Returns a 1-D array of class labels.
        predict_proba: Class probabilities, shape (n, k).
        classes: The list of class labels in the order used by
            `predict_proba` columns.
    """

    model_version: str
    model_kind: str
    feature_version: str

    def predict(self, X: list[str]) -> np.ndarray: ...
    def predict_proba(self, X: list[str]) -> np.ndarray: ...
    def classes(self) -> list[str]: ...

    def save(self, path: Path) -> None: ...


class StubModel:
    """A trivial model used by tests.

    Predicts the majority class seen during training for every input.
    Satisfies the `Model` Protocol.
    """

    def __init__(self, classes: list[str], majority: str, *, feature_version: str = "stub") -> None:
        self._classes = list(classes)
        self._majority = majority
        self.model_version = "stub-1"
        self.model_kind = "stub"
        self.feature_version = feature_version

    def predict(self, X: list[str]) -> np.ndarray:
        import numpy as np
        return np.array([self._majority] * len(X), dtype=object)

    def predict_proba(self, X: list[str]) -> np.ndarray:
        import numpy as np
        rows = []
        for _ in X:
            row = [1.0 if c == self._majority else 0.0 for c in self._classes]
            rows.append(row)
        return np.array(rows, dtype=float)

    def classes(self) -> list[str]:
        return list(self._classes)

    def save(self, path: Path) -> None:
        # Stub has no parameters to save.
        path.mkdir(parents=True, exist_ok=True)
        (path / "STUB.txt").write_text("stub model\n")


__all__ = ["Model", "StubModel"]