"""Training orchestrator for ChopCast.

This module coordinates the full lifecycle from raw SQLite reports to a
registered ML model. It ensures that data is processed safely (no leakage)
and that lineage is preserved via the model registry.

See docs/ML_ARCHITECTURE.md §3 and §7.
"""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chopcast.config import Settings
from chopcast.logging import get_logger
from chopcast.processing.pipeline import process, build_deps, PipelineDeps
from chopcast.training.split import make_split, Split, save_split, load_split
from chopcast.models.baseline_sklearn import BaselineSklearn
from chopcast.evaluation.report import evaluate, EvaluationReport
from chopcast.registry.store import SqliteModelRegistry
from chopcast.weather.matcher import WeatherMatcher

log = get_logger(__name__)


def run_training(
    settings: Settings,
    model_version: str,
    use_weather: bool = False,
) -> str:
    """Run the end-to-end training pipeline.

    Returns the registered model ID.
    """
    paths = settings.to_paths()

    # 1. Setup Pipeline Dependencies
    weather_matcher = None
    if use_weather and settings.weather.enabled:
        weather_matcher = WeatherMatcher(settings)

    deps = build_deps(
        config=settings.processing,
        labeling=settings.labeling,
        path_root=str(paths.root_path),
    )
    if weather_matcher:
        object.__setattr__(deps, 'weather_matcher', weather_matcher)

    # 2. Load and Process Data
    log.info("training.loading_data", db=str(paths.raw_db_path))
    conn = sqlite3.connect(paths.raw_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM trainable")
    all_rows = cursor.fetchall()
    conn.close()

    if not all_rows:
        raise ValueError("no data found in 'trainable' view")

    # process raw rows -> FeatureRows (ADR-0003 compliance)
    processed_features = []
    for row in all_rows:
        # Convert sqlite3.Row to a dict to satisfy the RawReport protocol adapter
        # because Row doesn't implement __getattr__ for column names.
        row_dict = dict(row)
        feat = process(row_dict, deps)
        if feat and feat.clean_text and len(feat.clean_text.strip()) > 0:
            processed_features.append(feat)

    log.info(
        "training.processed_count",
        raw=len(all_rows),
        usable=len(processed_features)
    )

    if not processed_features:
        raise ValueError("no reports with residual text available for training")

    # 3. Stratified Split
    hashes = [f.hash for f in processed_features]
    labels = [f.severity_label for f in processed_features]

    split = make_split(
        hashes=hashes,
        labels=labels,
        config=settings.training.default_split,
        version=f"split-{model_version}",
    )

    train_set = [f for f in processed_features if f.hash in split.train_hashes]
    test_set = [f for f in processed_features if f.hash in split.test_hashes]

    # 4. Feature Preparation
    if use_weather:
        X_train = [(f.clean_text, f.weather.to_dict() if f.weather else {}) for f in train_set]
        y_train = [f.severity_label for f in train_set]
        X_test = [(f.clean_text, f.weather.to_dict() if f.weather else {}) for f in test_set]
        y_test = [f.severity_label for f in test_set]
        kind = "baseline-weather"
    else:
        X_train = [f.clean_text for f in train_set]
        y_train = [f.severity_label for f in train_set]
        X_test = [f.clean_text for f in test_set]
        y_test = [f.severity_label for f in test_set]
        kind = "baseline"
    # 5. Train Model
    log.info("training.fitting_model", kind=kind)
    model = BaselineSklearn.train(
        X=X_train,
        y=y_train,
        tfidf=settings.text.tfidf,
        train=settings.training.baseline,
        model_version=model_version,
        feature_version=settings.processing.feature_builder_version,
    )

    # 5. Evaluate (using formal EvaluationReport)
    y_pred = model.predict(X_test)
    report = evaluate(
        y_true=y_test,
        y_pred=y_pred,
        model_version=model_version,
        feature_version=settings.processing.feature_builder_version,
        labels=model.classes(),
    )

    log.info("training.evaluated", macro_f1=report.macro)

    # 6. Persistence & Lineage
    artifact_dir = paths.models_dir / f"{kind}-{model_version}"
    model.save(artifact_dir)

    # Save Split Manifest
    split_path = paths.runs_dir / f"split-{model_version}.json"
    save_split(split, split_path)

    # Lineage File
    lineage = {
        "artifact": f"{kind}-{model_version}",
        "version": model_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": "unknown",
        "config_version": "v1",
        "inputs": {
            "raw_hashes_count": len(all_rows),
            "usable_hashes_count": len(processed_features),
            "train_count": len(X_train),
            "test_count": len(X_test),
            "weather_enabled": use_weather,
        }
    }
    (artifact_dir / "lineage.json").write_text(json.dumps(lineage, indent=2), encoding="utf-8")

    # Metrics File
    (artifact_dir / "metrics.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    # Register in DB
    registry = SqliteModelRegistry(paths.registry_db_path)
    try:
        model_id = registry.register(
            model_version=model_version,
            model_kind=kind,
            feature_version=settings.processing.feature_builder_version,
            metrics=report.to_dict(),
            artifact_path=artifact_dir,
            notes=f"Macro-F1: {report.macro:.3f} (weather={use_weather})",
        )
    finally:
        registry.close()

    return str(model_id)

__all__ = ["run_training"]
