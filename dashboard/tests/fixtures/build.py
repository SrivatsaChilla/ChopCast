"""Fixture builders for adapter and view tests.

Everything is created under a temporary pipeline root; no test touches the real
checkout.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_TIME = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def sample_reports() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    records = [
        ("AIREP", None, None, 55.0, -10.0, 35000.0, "alpha one"),
        ("PIREP", "LGT", None, 56.0, -11.0, 34000.0, "bravo two"),
        ("PIREP", "MOD", "SEV", 57.0, -12.0, 33000.0, None),
        ("Urgent PIREP", "SEV", None, 999.0, 200.0, 32000.0, "delta four"),
        ("PIREP", None, None, None, None, 31000.0, "echo five"),
        ("AIREP", "NEG", None, 0.0, 0.0, 30000.0, "foxtrot six"),
    ]
    for index, (rtype, primary, secondary, lat, lon, altitude, text) in enumerate(records):
        fetched = BASE_TIME + timedelta(hours=index)
        rows.append(
            {
                "hash": f"{index:064d}",
                "fetched_at": fetched.isoformat(),
                "obs_time": (fetched - timedelta(minutes=5)).isoformat(),
                "report_type": rtype,
                "raw_text": text,
                "turbulence": primary,
                "turbulence_2": secondary,
                "turbulence_type": None if primary is None else "CAT",
                "turbulence_freq": None if primary is None else "OCNL",
                "aircraft": f"N10{index}AB",
                "lat": lat,
                "lon": lon,
                "altitude": altitude,
                "raw_json": json.dumps({"index": index}),
                "source_url": f"https://example.invalid/{index}",
                "source_etag": f'"etag-{index}"',
            }
        )
    return rows


def target_db(path: Path, rows: list[dict[str, Any]] | None = None) -> Path:
    if path.exists():
        path.unlink()
    rows = sample_reports() if rows is None else rows
    connection = _connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE reports (
                hash TEXT PRIMARY KEY,
                fetched_at TEXT,
                obs_time TEXT,
                report_type TEXT,
                raw_text TEXT,
                turbulence TEXT,
                turbulence_2 TEXT,
                turbulence_type TEXT,
                turbulence_freq TEXT,
                aircraft TEXT,
                lat REAL,
                lon REAL,
                altitude REAL,
                raw_json TEXT,
                source_url TEXT,
                source_etag TEXT
            );
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                rows_seen INTEGER,
                rows_inserted INTEGER,
                rows_skipped INTEGER,
                rows_rejected INTEGER,
                error TEXT
            );
            CREATE TABLE rejected (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT,
                reason TEXT,
                detail TEXT
            );
            CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY);
            INSERT INTO schema_migrations (version) VALUES (1), (2), (3);
            CREATE VIEW trainable AS
                SELECT hash, fetched_at, obs_time, report_type, raw_text, turbulence,
                       turbulence_2, turbulence_type, turbulence_freq, aircraft, lat, lon,
                       altitude, raw_json
                FROM reports
                WHERE report_type IN ('PIREP', 'Urgent PIREP') AND turbulence IS NOT NULL;
            INSERT INTO runs VALUES
                (1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:01:00+00:00', 'ok', 6, 6, 0, 0, NULL),
                (2, '2026-01-02T00:00:00+00:00', '2026-01-02T00:01:00+00:00', 'error', 6, 5, 0, 1, 'boom');
            INSERT INTO rejected VALUES
                (1, '2026-01-02T00:00:00+00:00', 'parse_error', 'bad row');
            """
        )
        placeholders = ", ".join("?" for _ in rows[0]) if rows else ""
        if rows:
            connection.executemany(
                f"INSERT INTO reports VALUES ({placeholders})",
                [tuple(row.values()) for row in rows],
            )
        connection.commit()
    finally:
        connection.close()
    return path


def legacy_db(path: Path, rows: list[dict[str, Any]] | None = None) -> Path:
    if path.exists():
        path.unlink()
    rows = sample_reports() if rows is None else rows
    connection = _connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE reports (
                hash TEXT PRIMARY KEY,
                fetched_at TEXT,
                obs_time TEXT,
                report_type TEXT,
                raw_text TEXT,
                turbulence TEXT,
                turbulence_2 TEXT,
                turbulence_type TEXT,
                turbulence_freq TEXT,
                aircraft TEXT,
                lat REAL,
                lon REAL,
                altitude REAL,
                raw_json TEXT
            );
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at TEXT,
                rows_seen INTEGER,
                inserted INTEGER,
                skipped INTEGER,
                status TEXT
            );
            CREATE VIEW trainable AS
                SELECT hash, obs_time, turbulence, turbulence_2, aircraft, lat, lon, altitude
                FROM reports WHERE turbulence IS NOT NULL;
            INSERT INTO runs VALUES
                (1, '2026-01-01T00:00:00+00:00', 6, 6, 0, 'ok');
            """
        )
        columns = (
            "hash, fetched_at, obs_time, report_type, raw_text, turbulence, turbulence_2, "
            "turbulence_type, turbulence_freq, aircraft, lat, lon, altitude, raw_json"
        )
        placeholders = ", ".join("?" for _ in range(14))
        connection.executemany(
            f"INSERT INTO reports ({columns}) VALUES ({placeholders})",
            [
                (
                    row["hash"],
                    row["fetched_at"],
                    row["obs_time"],
                    row["report_type"],
                    row["raw_text"],
                    row["turbulence"],
                    row["turbulence_2"],
                    row["turbulence_type"],
                    row["turbulence_freq"],
                    row["aircraft"],
                    row["lat"],
                    row["lon"],
                    row["altitude"],
                    row["raw_json"],
                )
                for row in rows
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def empty_db(path: Path) -> Path:
    return target_db(path, rows=[])


def models_db(path: Path) -> Path:
    if path.exists():
        path.unlink()
    connection = _connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE models (
                id INTEGER PRIMARY KEY,
                model_version TEXT,
                model_kind TEXT,
                feature_version TEXT,
                registered_at TEXT,
                metrics_json TEXT,
                artifact_path TEXT,
                notes TEXT
            );
            CREATE TABLE promotions (
                id INTEGER PRIMARY KEY,
                model_id INTEGER,
                promoted_at TEXT,
                tag TEXT,
                replaced_id INTEGER
            );
            INSERT INTO models VALUES
                (1, 'demo-baseline', 'baseline', 'features_v1', '2026-01-01T00:00:00+00:00',
                 '{"accuracy": 0.8, "macro_f1": 0.5, "n_samples": 6}',
                 'models/registry/demo-baseline', 'stored baseline'),
                (2, 'demo-transformer', 'transformer', 'features_v1', '2026-01-02T00:00:00+00:00',
                 '{"accuracy": 0.9, "macro_f1": 0.7, "n_samples": 6}',
                 'models/registry/demo-transformer', NULL),
                (3, 'demo-broken', 'transformer', 'features_v1', '2026-01-03T00:00:00+00:00',
                 '{not json', 'models/registry/demo-missing', 'artifact absent');
            INSERT INTO promotions VALUES
                (1, 1, '2026-01-04T00:00:00+00:00', 'production', NULL);
            """
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _metric_payload(kind: str, accuracy: float, macro_f1: float) -> dict[str, Any]:
    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "n_samples": 6,
        "model_kind": kind,
        "per_class": {
            "None": {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2},
            "Light": {"precision": 0.6, "recall": 0.4, "f1": 0.48, "support": 2},
        },
        "confusion": {
            "labels": ["None", "Light"],
            "matrix": [[2, 0], [1, 1]],
        },
    }


def artifacts(registry_dir: Path) -> None:
    baseline = registry_dir / "demo-baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    (baseline / "pipeline.joblib").write_bytes(b"")
    (baseline / "manifest.txt").write_text(
        "model_version=demo-baseline\nmodel_kind=transformer\nfeature_version=features_v1\n",
        encoding="utf-8",
    )
    (baseline / "metrics.json").write_text(
        json.dumps(_metric_payload("baseline", 0.8, 0.5)), encoding="utf-8"
    )
    (baseline / "lineage.json").write_text(
        json.dumps(
            {
                "version": "demo-baseline",
                "code_commit": "unknown",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    transformer = registry_dir / "demo-transformer"
    transformer.mkdir(parents=True, exist_ok=True)
    (transformer / "manifest.txt").write_text(
        "model_version=demo-transformer\nmodel_kind=transformer\nfeature_version=features_v1\n",
        encoding="utf-8",
    )
    (transformer / "report.md").write_text("# Demo report\n", encoding="utf-8")
    (transformer / "report.json").write_text(
        json.dumps(_metric_payload("transformer", 0.9, 0.7)), encoding="utf-8"
    )
    (transformer / "split.json").write_text(
        json.dumps(
            {
                "version": "demo-transformer",
                "seed": 42,
                "mode": "hash",
                "train_hashes": ["a", "b", "c"],
                "test_hashes": ["d"],
            }
        ),
        encoding="utf-8",
    )


def write_runs(root: Path) -> None:
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "split-demo-baseline.json").write_text(
        json.dumps(
            {
                "version": "demo-baseline",
                "seed": 42,
                "mode": "hash",
                "train_hashes": ["a", "b", "c", "d"],
                "test_hashes": ["e", "f"],
            }
        ),
        encoding="utf-8",
    )
    maps = runs / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    (maps / "demo.html").write_text(
        "<!doctype html><html><body>demo map</body></html>", encoding="utf-8"
    )
    (maps / "not-a-map.txt").write_text("ignored", encoding="utf-8")


def write_features(root: Path) -> None:
    features = root / "data" / "features"
    features.mkdir(parents=True, exist_ok=True)
    (features / "features_v1_demo.jsonl").write_text(
        '{"hash": "a", "label": "Light"}\n', encoding="utf-8"
    )


def write_logs(root: Path) -> None:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"timestamp": "2026-01-01T00:00:00Z", "level": "INFO", "event": "fetch"}),
        json.dumps({"timestamp": "2026-01-01T00:00:01Z", "level": "ERROR", "event": "parse", "detail": "bad"}),
        "2026-01-01 00:00:02,000 WARNING plain fallback",
    ]
    (logs / "collector.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (logs / "collector.log.1").write_text("rotated line\n", encoding="utf-8")
    (root / "requirements.txt").write_text("django\n", encoding="utf-8")
    (root / "collector.log").write_text("2026-01-01 00:00:00,000 INFO root log\n", encoding="utf-8")


def write_configs(root: Path) -> None:
    configs = root / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    (configs / "labeling.yaml").write_text(
        "\n".join(
            (
                "version: v1",
                "none: [NEG, NIL]",
                "light: [LGT, LIGHT, CHOP]",
                "moderate: [MOD]",
                "severe: [SEV, SEVERE]",
                "combination_strategy: max",
                "chop_only_label: light",
                "unknown_strategy: none",
                "",
            )
        ),
        encoding="utf-8",
    )


def write_docs(root: Path) -> None:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "ISSUES.md").write_text(
        "# Known issues\n\n"
        "## Critical\n\n"
        "### ISS-001: Example critical issue\n\n"
        "Body with `code` and a [link](https://example.invalid).\n\n"
        "## High\n\n"
        "### ISS-002: Example high issue\n\n"
        "More text.\n",
        encoding="utf-8",
    )


def full_pipeline(root: Path) -> Path:
    target_db(root / "data" / "raw" / "pireps.db")
    legacy_db(root / "data" / "raw" / "legacy_pireps.db")
    registry = root / "models" / "registry"
    models_db(registry / "registry.db")
    artifacts(registry)
    write_runs(root)
    write_features(root)
    write_logs(root)
    write_configs(root)
    write_docs(root)
    return root
