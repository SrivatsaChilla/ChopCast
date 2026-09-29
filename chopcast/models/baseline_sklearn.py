"""TF-IDF + Logistic Regression baseline model.

Default model kind for M3. Uses scikit-learn's `Pipeline` so the
TF-IDF vectoriser and the classifier are serialised together.

Saving uses `joblib` to preserve the full pipeline. Loading rebuilds
the wrapper.

See `docs/MODULE_DESIGN.md` §7.2.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from chopcast.config import BaselineTrainConfig, TfidfConfig
from chopcast.logging import get_logger
from chopcast.models.protocol import Model

log = get_logger(__name__)


class BaselineSklearn:
    """A TF-IDF + LogReg/SVM pipeline satisfying the `Model` protocol."""

    def __init__(
        self,
        pipeline: object,
        classes: list[str],
        *,
        model_version: str,
        feature_version: str,
    ) -> None:
        self._pipeline = pipeline
        self._classes = list(classes)
        self.model_version = model_version
        self.model_kind = "baseline"
        self.feature_version = feature_version

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    @classmethod
    def train(
        cls,
        X: list[str],
        y: list[str],
        tfidf: TfidfConfig,
        train: BaselineTrainConfig,
        *,
        model_version: str,
        feature_version: str,
    ) -> "BaselineSklearn":
        """Train on `(X, y)`. Both are parallel lists."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.svm import LinearSVC

        if not X:
            raise ValueError("cannot train on empty X")
        if len(X) != len(y):
            raise ValueError(f"X and y must have the same length, got {len(X)} vs {len(y)}")

        vectoriser = TfidfVectorizer(
            ngram_range=tfidf.ngram_range,
            min_df=tfidf.min_df,
            max_df=tfidf.max_df,
            sublinear_tf=tfidf.sublinear_tf,
        )

        if train.kind == "logreg":
            # `class_weight="balanced"` is the default; users can pass
            # None to opt out via config.
            clf = LogisticRegression(
                max_iter=train.max_iter,
                C=train.C,
                class_weight=train.class_weight,
            )
        elif train.kind == "linear_svc":
            # LinearSVC doesn't expose predict_proba; we wrap it with
            # CalibratedClassifierCV so the Model protocol still works.
            from sklearn.calibration import CalibratedClassifierCV

            base = LinearSVC(
                max_iter=train.max_iter,
                C=train.C,
                class_weight=train.class_weight,
            )
            clf = CalibratedClassifierCV(base)
        else:
            raise ValueError(f"unknown baseline kind: {train.kind!r}")

        pipeline = Pipeline([("tfidf", vectoriser), ("clf", clf)])
        pipeline.fit(X, y)
        classes = list(pipeline.classes_)
        log.info(
            "baseline.trained",
            n_train=len(X),
            classes=classes,
            kind=train.kind,
        )
        return cls(
            pipeline,
            classes,
            model_version=model_version,
            feature_version=feature_version,
        )

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def predict(self, X: list[str]) -> np.ndarray:
        return self._pipeline.predict(X)

    def predict_proba(self, X: list[str]) -> np.ndarray:
        clf = self._pipeline.named_steps["clf"]
        if not hasattr(clf, "predict_proba"):
            raise RuntimeError(
                f"classifier {type(clf).__name__} does not support predict_proba"
            )
        return clf.predict_proba(self._pipeline[:-1].transform(X))

    def classes(self) -> list[str]:
        return list(self._classes)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        import joblib

        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._pipeline, path / "pipeline.joblib")
        (path / "manifest.txt").write_text(
            f"model_version={self.model_version}\n"
            f"model_kind={self.model_kind}\n"
            f"feature_version={self.feature_version}\n"
            f"classes={','.join(self._classes)}\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "BaselineSklearn":
        import joblib

        manifest_lines = (path / "manifest.txt").read_text(encoding="utf-8").splitlines()
        manifest = {}
        for line in manifest_lines:
            if "=" in line:
                k, _, v = line.partition("=")
                manifest[k.strip()] = v.strip()
        pipeline = joblib.load(path / "pipeline.joblib")
        classes = manifest.get("classes", "").split(",") if manifest.get("classes") else []
        return cls(
            pipeline,
            classes,
            model_version=manifest.get("model_version", "unknown"),
            feature_version=manifest.get("feature_version", "unknown"),
        )


__all__ = ["BaselineSklearn"]