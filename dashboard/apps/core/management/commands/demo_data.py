"""Generate an isolated, varied demo dataset for the dashboard.

The command never touches real pipeline data. It refuses an output directory
that resolves under ``data/``, ``models/``, ``runs/``, ``logs/``, ``configs/``,
or ``chopcast/`` and writes only below the requested directory (by default
``dashboard/var/demo``).
"""

from __future__ import annotations

import json
import random
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

DASHBOARD_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = DASHBOARD_ROOT.parent
FORBIDDEN_ROOTS = tuple(
    REPO_ROOT / name for name in ("data", "models", "runs", "logs", "configs", "chopcast")
)

REPORT_LABELS = (
    None,
    "NEG",
    "LGT",
    "MOD",
    "SEV",
    "LGT CHOP",
    "CHOP",
    "MOD-SEV",
    "UNRECOGNISED-TURB",
)
SECONDARY_LABELS = (None, None, None, "MOD", "LGT", "SEV", None, None, None, None)
REPORT_TYPES = ("AIREP", "AIREP", "PIREP", "Urgent PIREP", "AIREP", "PIREP")


def _now() -> datetime:
    return datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _within(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().is_relative_to(parent.resolve())
    except (OSError, ValueError):
        return False


def _assert_safe_output(output: Path) -> Path:
    resolved = output.expanduser().resolve()
    if resolved == REPO_ROOT or _within(REPO_ROOT, resolved):
        raise CommandError(
            "refusing to write the demo dataset at or above the repository root "
            f"({resolved})"
        )
    if resolved == DASHBOARD_ROOT:
        raise CommandError(
            "refusing to write the demo dataset directly into dashboard/; point at a "
            "dedicated directory such as dashboard/var/demo"
        )
    for forbidden in FORBIDDEN_ROOTS:
        if _within(resolved, forbidden):
            raise CommandError(
                f"refusing to write under the real pipeline directory {forbidden} ({resolved})"
            )
    return resolved


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


REPORT_COLUMNS = (
    "hash",
    "fetched_at",
    "obs_time",
    "report_type",
    "raw_text",
    "turbulence",
    "turbulence_2",
    "turbulence_type",
    "turbulence_freq",
    "aircraft",
    "lat",
    "lon",
    "altitude",
    "raw_json",
)
TARGET_EXTRA_COLUMNS = ("source_url", "source_etag")

TRAINABLE_SELECT = (
    "hash, fetched_at, obs_time, report_type, raw_text, turbulence, turbulence_2, "
    "turbulence_type, turbulence_freq, aircraft, lat, lon, altitude, raw_json"
)
TRAINABLE_WHERE = "report_type IN ('PIREP', 'Urgent PIREP') AND turbulence IS NOT NULL"


def _reports(seed: int, count: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    base = _now() - timedelta(days=10)
    rows: list[dict[str, Any]] = []
    for index in range(count):
        label = REPORT_LABELS[index % len(REPORT_LABELS)]
        secondary = SECONDARY_LABELS[index % len(SECONDARY_LABELS)]
        report_type = REPORT_TYPES[index % len(REPORT_TYPES)]
        obs = base + timedelta(hours=index * 3)
        fetched = obs + timedelta(minutes=7)
        lat: float | None = round(45.0 + rng.random() * 15.0, 4)
        lon: float | None = round(-40.0 + rng.random() * 40.0, 4)
        if index % 17 == 0:
            lat, lon = 101.0, 200.0  # deliberately invalid: dropped from the map
        if index % 19 == 0:
            lat, lon = None, None  # no coordinates at all
        raw_text: str | None = (
            f"UA /OV {lat or '----'}{lon or '----'} /TM {obs:%H%M} /FL350 /TP B738 /TB {label or 'NEG'}"
        )
        if index % 23 == 0:
            raw_text = None
        rows.append(
            {
                "hash": sha256(f"{seed}:{index}".encode()).hexdigest(),
                "fetched_at": _iso(fetched),
                "obs_time": _iso(obs),
                "report_type": report_type,
                "raw_text": raw_text,
                "turbulence": label,
                "turbulence_2": secondary,
                "turbulence_type": None if label is None else ("CHOP" if "CHOP" in label else "CAT"),
                "turbulence_freq": None if label is None else rng.choice(["OCNL", "FRQ", "INTMT"]),
                "aircraft": f"N{700 + index % 200}AB",
                "lat": lat,
                "lon": lon,
                "altitude": float(30000 + (index % 12) * 1000),
                "raw_json": json.dumps({"demo": True, "index": index}),
                "source_url": f"https://example.invalid/reports/{index}",
                "source_etag": f'"etag-{index}"',
            }
        )
    return rows


def _create_target_db(path: Path, rows: list[dict[str, Any]], *, legacy: bool) -> None:
    if path.exists():
        path.unlink()
    connection = _connect(path)
    columns = list(REPORT_COLUMNS if legacy else REPORT_COLUMNS + TARGET_EXTRA_COLUMNS)
    extra_ddl = (
        ""
        if legacy
        else ",\n                source_url TEXT,\n                source_etag TEXT"
    )
    try:
        connection.executescript(
            f"""
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
                raw_json TEXT{extra_ddl}
            );
            """
        )
        present = [column for column in columns if column in _table_columns(connection, "reports")]
        placeholders = ", ".join("?" for _ in present)
        connection.executemany(
            f"INSERT INTO reports ({', '.join(present)}) VALUES ({placeholders})",
            [tuple(row[column] for column in present) for row in rows],
        )
        if legacy:
            connection.executescript(
                """
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
                INSERT INTO runs (ran_at, rows_seen, inserted, skipped, status) VALUES
                    ('2026-01-14T08:00:00+00:00', 55, 53, 2, 'ok'),
                    ('2026-01-15T08:00:00+00:00', 60, 58, 2, 'ok');
                """
            )
        else:
            connection.executescript(
                f"""
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
                    SELECT {TRAINABLE_SELECT} FROM reports WHERE {TRAINABLE_WHERE};
                INSERT INTO runs
                    (started_at, finished_at, status, rows_seen, rows_inserted, rows_skipped, rows_rejected, error)
                VALUES
                    ('2026-01-14T08:00:00+00:00', '2026-01-14T08:02:00+00:00', 'ok', 55, 50, 3, 2, NULL),
                    ('2026-01-15T08:00:00+00:00', '2026-01-15T08:02:00+00:00', 'ok', 60, 58, 1, 1, NULL),
                    ('2026-01-15T12:00:00+00:00', '2026-01-15T12:00:40+00:00', 'error', 12, 9, 1, 2, 'demo: upstream timeout');
                INSERT INTO rejected (fetched_at, reason, detail) VALUES
                    ('2026-01-15T08:00:00+00:00', 'missing_coordinates', 'demo row without lat/lon'),
                    ('2026-01-15T12:00:00+00:00', 'parse_error', 'demo malformed report');
                """
            )
        connection.commit()
    finally:
        connection.close()


def _table_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(row["name"] for row in connection.execute(f"PRAGMA table_info({table})"))


def _create_registry_db(path: Path, models: list[dict[str, Any]], promotions: list[tuple]) -> None:
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
            """
        )
        connection.executemany(
            "INSERT INTO models (id, model_version, model_kind, feature_version, registered_at, "
            "metrics_json, artifact_path, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    model["id"],
                    model["model_version"],
                    model["model_kind"],
                    model["feature_version"],
                    model["registered_at"],
                    model["metrics_json"],
                    model["artifact_path"],
                    model["notes"],
                )
                for model in models
            ],
        )
        connection.executemany(
            "INSERT INTO promotions (id, model_id, promoted_at, tag, replaced_id) "
            "VALUES (?, ?, ?, ?, ?)",
            promotions,
        )
        connection.commit()
    finally:
        connection.close()


def _metrics(kind: str, accuracy: float, macro_f1: float, samples: int, matrix: list[list[int]]) -> dict[str, Any]:
    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "n_samples": samples,
        "per_class": [
            {"label": "None", "precision": 0.91, "recall": 0.88, "f1": 0.89, "support": 20},
            {"label": "Light", "precision": 0.74, "recall": 0.69, "f1": 0.71, "support": 16},
            {"label": "Moderate", "precision": 0.62, "recall": 0.58, "f1": 0.60, "support": 12},
            {"label": "Severe", "precision": 0.50, "recall": 0.45, "f1": 0.47, "support": 10},
        ],
        "confusion": {
            "labels": ["None", "Light", "Moderate", "Severe"],
            "matrix": matrix,
        },
        "model_kind": kind,
    }


def _split_payload(version: str, seed: int, train: int, test: int) -> dict[str, Any]:
    return {
        "version": version,
        "seed": seed,
        "mode": "hash",
        "train_hashes": [f"train-{i:04d}" for i in range(train)],
        "test_hashes": [f"test-{i:04d}" for i in range(test)],
    }


def _write_artifacts(output: Path, seed: int) -> None:
    registry_dir = output / "registry"
    baseline = registry_dir / "baseline-demo"
    transformer = registry_dir / "transformer-demo"

    baseline.mkdir(parents=True, exist_ok=True)
    (baseline / "pipeline.joblib").write_bytes(b"")
    (baseline / "manifest.txt").write_text(
        "\n".join(
            (
                "model_version=demo-baseline",
                "model_kind=transformer",
                "feature_version=features_v1",
                "labeling_version=v1",
                "",
            )
        ),
        encoding="utf-8",
    )
    _write_json(
        baseline / "metrics.json",
        _metrics("baseline", 0.81, 0.48, 48, [[18, 2, 0, 0], [4, 9, 2, 0], [1, 3, 6, 1], [0, 1, 2, 2]]),
    )
    _write_json(
        baseline / "lineage.json",
        {
            "version": "demo-baseline",
            "code_commit": "unknown",
            "created_at": "2026-01-13T09:00:00+00:00",
            "feature_version": "features_v1",
        },
    )
    _write_json(
        output / "runs" / "split-demo-baseline.json",
        _split_payload("demo-baseline", seed, 48, 12),
    )

    transformer.mkdir(parents=True, exist_ok=True)
    (transformer / "manifest.txt").write_text(
        "\n".join(
            (
                "model_version=demo-transformer",
                "model_kind=transformer",
                "feature_version=features_v1",
                "labeling_version=v1",
                "",
            )
        ),
        encoding="utf-8",
    )
    (transformer / "report.md").write_text(
        "# Demo transformer training report\n\n"
        "This file exists so the dashboard can show the target artifact layout.\n",
        encoding="utf-8",
    )
    _write_json(
        transformer / "report.json",
        _metrics("transformer", 0.90, 0.63, 58, [[20, 1, 0, 0], [2, 14, 3, 0], [0, 2, 9, 1], [0, 0, 1, 6]]),
    )
    _write_json(
        transformer / "split.json",
        _split_payload("demo-transformer", seed + 1, 46, 12),
    )


def _write_support_files(output: Path) -> None:
    _write_json(
        output / "runs" / "split-demo-transformer.json",
        _split_payload("demo-transformer", 43, 46, 12),
    )
    maps = output / "runs" / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    (maps / "demo-map.html").write_text(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>Demo generated map</title></head><body>"
        "<h1>Demo generated map</h1><p>Static placeholder for the file browser. "
        "No CDN, no scripts.</p></body></html>\n",
        encoding="utf-8",
    )

    features = output / "features"
    features.mkdir(parents=True, exist_ok=True)
    with (features / "features_v1_demo.jsonl").open("w", encoding="utf-8") as handle:
        for index in range(4):
            handle.write(
                json.dumps(
                    {
                        "hash": sha256(f"feature:{index}".encode()).hexdigest(),
                        "feature_version": "features_v1",
                        "label": REPORT_LABELS[index],
                        "vector": [index, index * 0.5, -index],
                    }
                )
                + "\n"
            )

    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "collector.log").open("w", encoding="utf-8") as handle:
        for index in range(12):
            level = "ERROR" if index == 9 else ("WARNING" if index == 5 else "INFO")
            handle.write(
                json.dumps(
                    {
                        "timestamp": _iso(_now() + timedelta(minutes=index)),
                        "level": level,
                        "event": "fetch" if index % 3 else "parse",
                        "message": f"demo line {index}",
                        "report_index": index,
                    }
                )
                + "\n"
            )
        handle.write("2026-01-15 12:30:00,000 INFO plain demo line without JSON\n")
    (logs / "collector.log.1").write_text(
        "2026-01-14 08:00:00,000 INFO rotated demo line\n", encoding="utf-8"
    )

    configs = output / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    source_rules = REPO_ROOT / "configs" / "labeling.yaml"
    if source_rules.is_file():
        shutil.copyfile(source_rules, configs / "labeling.yaml")
    else:
        (configs / "labeling.yaml").write_text(
            "version: v1\nnone: [NEG, NIL]\nlight: [LGT, LIGHT]\n"
            "moderate: [MOD]\nsevere: [SEV, SEVERE]\n",
            encoding="utf-8",
        )


def _env_lines(output: Path) -> list[str]:
    artifact_dirs = f"{output / 'registry'}"
    values = {
        "CHOPCAST_DASHBOARD_ROOT": str(output),
        "CHOPCAST_DASHBOARD_RAW_DB": str(output / "raw" / "pireps.db"),
        "CHOPCAST_DASHBOARD_REGISTRY_DB": str(output / "registry" / "registry.db"),
        "CHOPCAST_DASHBOARD_ARTIFACT_DIRS": artifact_dirs,
        "CHOPCAST_DASHBOARD_RUNS_DIR": str(output / "runs"),
        "CHOPCAST_DASHBOARD_FEATURES_DIR": str(output / "features"),
        "CHOPCAST_DASHBOARD_PROCESSED_DIR": str(output / "processed"),
        "CHOPCAST_DASHBOARD_LOGS_DIRS": str(output / "logs"),
        "CHOPCAST_DASHBOARD_MAP_DIRS": str(output / "runs" / "maps"),
        "CHOPCAST_DASHBOARD_CONFIG_DIR": str(output / "configs"),
        "CHOPCAST_DASHBOARD_DOCS_DIR": str(REPO_ROOT / "docs"),
        "CHOPCAST_DASHBOARD_TIMEZONE": "UTC",
    }
    lines = [
        "# Generated by `python manage.py demo_data`. Never edit the real .env.",
        "# Copy next to manage.py as .env, or source it before starting the server.",
        "# bash:        set -a; . ./demo.env; set +a",
        "# PowerShell:  Get-Content demo.env | ForEach-Object {",
        "#                if ($_ -match \"^([A-Z0-9_]+)=(.*)$\") {",
        "#                  Set-Item -Path \"Env:$($matches[1])\" -Value $matches[2].Trim(\"'\")",
        "#                }",
        "#              }",
    ]
    lines.extend(f"{key}='{value}'" for key, value in values.items())
    return lines


class Command(BaseCommand):
    help = "Write a varied demo dataset under dashboard/var/demo without touching pipeline data."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            default=str(DASHBOARD_ROOT / "var" / "demo"),
            help="Output directory (default: dashboard/var/demo).",
        )
        parser.add_argument("--force", action="store_true", help="Replace a non-empty output directory.")
        parser.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42).")
        parser.add_argument(
            "--reports", type=int, default=60, help="Number of demo reports (default: 60)."
        )
        parser.add_argument("--quiet", action="store_true", help="Only print errors.")

    def handle(self, *args, **options) -> None:
        output = _assert_safe_output(Path(options["output"]))
        seed = int(options["seed"])
        reports = max(1, min(int(options["reports"]), 5000))

        if output.exists() and any(output.iterdir()):
            if not options["force"]:
                raise CommandError(
                    f"{output} already exists and is not empty; pass --force to replace it"
                )
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)

        rows = _reports(seed, reports)
        _create_target_db(output / "raw" / "pireps.db", rows, legacy=False)
        _create_target_db(output / "raw" / "legacy_pireps.db", rows, legacy=True)

        registered = "2026-01-13T09:00:00+00:00"
        models = [
            {
                "id": 1,
                "model_version": "demo-baseline",
                "model_kind": "baseline",
                "feature_version": "features_v1",
                "registered_at": registered,
                "metrics_json": json.dumps(_metrics("baseline", 0.81, 0.48, 48, [[18, 2, 0, 0], [4, 9, 2, 0], [1, 3, 6, 1], [0, 1, 2, 2]])),
                "artifact_path": "registry/baseline-demo",
                "notes": "manifest kind intentionally differs from the stored kind (ISS-047 demo)",
            },
            {
                "id": 2,
                "model_version": "demo-transformer",
                "model_kind": "transformer",
                "feature_version": "features_v1",
                "registered_at": "2026-01-14T10:00:00+00:00",
                "metrics_json": json.dumps(_metrics("transformer", 0.90, 0.63, 58, [[20, 1, 0, 0], [2, 14, 3, 0], [0, 2, 9, 1], [0, 0, 1, 6]])),
                "artifact_path": "registry/transformer-demo",
                "notes": None,
            },
            {
                "id": 3,
                "model_version": "demo-missing",
                "model_kind": "transformer",
                "feature_version": "features_v1",
                "registered_at": "2026-01-15T11:00:00+00:00",
                "metrics_json": "{this is not valid json",
                "artifact_path": "registry/missing-demo",
                "notes": "artifact directory intentionally absent",
            },
        ]
        _create_registry_db(
            output / "registry" / "registry.db",
            models,
            [(1, 1, "2026-01-15T12:00:00+00:00", "production", None)],
        )
        _write_artifacts(output, seed)
        _write_support_files(output)
        (output / "demo.env").write_text("\n".join(_env_lines(output)) + "\n", encoding="utf-8")

        trainable = sum(
            1
            for row in rows
            if row["report_type"] in {"PIREP", "Urgent PIREP"} and row["turbulence"] is not None
        )
        if not options["quiet"]:
            self.stdout.write(self.style.SUCCESS(f"demo dataset written to {output}"))
            self.stdout.write(
                f"  reports={len(rows)} trainable={trainable} models={len(models)} promotions=1"
            )
            self.stdout.write("  load it with:")
            self.stdout.write(
                f"    PowerShell:  $env:CHOPCAST_DASHBOARD_ROOT='{output}'  (or copy demo.env to dashboard/.env)"
            )
            self.stdout.write(f"    bash:        export CHOPCAST_DASHBOARD_ROOT='{output}'")
