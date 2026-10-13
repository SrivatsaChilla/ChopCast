"""Evaluation orchestrator for ChopCast.

This module provides tools to compare different model versions using a
consistent test set. It ensures that model improvements are measured
fairly by using the same data and metric definitions.

See docs/ML_ARCHITECTURE.md §8.
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any

from chopcast.config import Settings
from chopcast.logging import get_logger
from chopcast.registry.store import ModelRegistry, ModelRecord
from chopcast.training.split import Split, load_split
from chopcast.models.protocol import Model
from chopcast.models.baseline_sklearn import BaselineSklearn
from chopcast.evaluation.report import EvaluationReport, evaluate

log = get_logger(__name__)


def load_model_artifact(record: ModelRecord) -> Model:
    """Load a model object from its registered artifact path."""
    path = Path(record.artifact_path)
    if record.model_kind == "baseline":
        return BaselineSklearn.load(path)
    # Transformer loading would go here
    raise NotImplementedError(f"loading for {record.model_kind} not implemented")


def compare_models(
    settings: Settings,
    registry: ModelRegistry,
    id_a: int,
    id_b: int,
) -> str:
    """Compare two models on a common test set and return a markdown report.

    The common test set is retrieved from the split manifest associated with
    the models.
    """
    # 1. Load records and models
    rec_a = registry.get(id_a)
    rec_b = registry.get(id_b)
    if not rec_a or not rec_b:
        raise KeyError("one or both model IDs not found in registry")

    model_a = load_model_artifact(rec_a)
    model_b = load_model_artifact(rec_b)

    # 2. Retrieve the test set
    paths = settings.to_paths()
    # Use the split manifest from the first model as the reference
    split_path = paths.runs_dir / f"split-{rec_a.model_version}.json"
    if not split_path.exists():
        raise FileNotFoundError(f"split manifest not found at {split_path}")

    split = load_split(split_path)

    # 3. Load the actual test data from the DB
    conn = sqlite3.connect(paths.raw_db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join(["?"] * len(split.test_hashes))
    cursor = conn.execute(
        f"SELECT * FROM trainable WHERE hash IN ({placeholders})",
        split.test_hashes
    )
    rows = cursor.fetchall()
    conn.close()

    from chopcast.processing.pipeline import process, build_deps
    deps = build_deps(settings.processing, settings.labeling, str(paths.root_path))

    X_test = []
    y_test = []
    for row in rows:
        feat = process(row, deps)
        if feat:
            X_test.append(feat.clean_text)
            y_test.append(feat.severity_label)

    if not X_test:
        raise ValueError("no test data available for these models")

    # 4. Generate Predictions
    pred_a = model_a.predict(X_test)
    pred_b = model_b.predict(X_test)

    # 5. Compute formal EvaluationReports
    rep_a = evaluate(
        y_true=y_test,
        y_pred=pred_a,
        model_version=rec_a.model_version,
        feature_version=rec_a.feature_version,
        labels=model_a.classes(),
    )
    rep_b = evaluate(
        y_true=y_test,
        y_pred=pred_b,
        model_version=rec_b.model_version,
        feature_version=rec_b.feature_version,
        labels=model_b.classes(),
    )

    # 6. Build Markdown Report (Industrial Style)
    report = [
        f"# Model Comparison Report",
        f"Comparison between `{rec_a.model_version}` and `{rec_b.model_version}`",
        f"Test Set Size: {len(X_test)} reports\n",
        "| Metric | {0} | {1} | Delta |".format(rec_a.model_version, rec_b.model_version),
        "|---|---|---|---|",
        "| **Macro-F1** | {0:.4f} | {1:.4f} | {2:+.4f} |".format(
            rep_a.macro, rep_b.macro, rep_b.macro - rep_a.macro
        ),
        "| **Weighted-F1** | {0:.4f} | {1:.4f} | {2:+.4f} |".format(
            rep_a.weighted, rep_b.weighted, rep_b.weighted - rep_a.weighted
        ),
    ]

    for label in rep_a.labels:
        # Find matching class metric for this label
        m_a = next((c for c in rep_a.per_class if c.label == label), None)
        m_b = next((c for c in rep_b.per_class if c.label == label), None)
        if m_a and m_b:
            report.append(
                "| {0} F1 | {1:.4f} | {2:.4f} | {3:+.4f} |".format(
                    label, m_a.f1, m_b.f1, m_b.f1 - m_a.f1
                )
            )

    return "\n".join(report)

__all__ = ["compare_models"]
