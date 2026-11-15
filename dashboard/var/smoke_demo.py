"""Temporary: load dashboard/var/demo/demo.env and exercise the demo dataset."""
from __future__ import annotations

import os
import sys
from pathlib import Path

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
envy = DASH / "var" / "demo" / "demo.env"
for line in envy.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    os.environ[key.strip()] = value
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("CHOPCAST_DASHBOARD_DEBUG", "1")

import django

django.setup()

from django.test import Client

from adapters import get_adapter
from adapters.maps import MapFilters

adapter = get_adapter()
summary = adapter.reports.summary().data
print("raw status", adapter.reports.status().state.value, adapter.reports.profile().state)
print("reports", summary.total, "trainable", summary.trainable_rows, "by_type", summary.by_type)
print("coords", summary.with_coords, "invalid", summary.invalid_coords, "without", summary.without_coords)
print("runs", [(r.id, r.status, r.shape) for r in adapter.reports.run_history().data])
print("rejected", len(adapter.reports.rejected().data))
labels = adapter.labels.distribution().data
print("labels", labels.total, labels.labelled, labels.unlabelled, labels.combined)
models = adapter.registry.list_models().data
print("models", [(m.id, m.model_version, m.model_kind, m.artifact_exists, len(m.warnings)) for m in models])
print("promotions", [(p.model_id, p.tag) for p in adapter.registry.promotions().data])
for record in adapter.evaluation.list_evaluations().data:
    print("eval", record.model_id, record.source, record.metrics.get("accuracy") if record.metrics else None, len(record.warnings))
print("training runs", [(r.key, r.source_path, r.model_kind_manifest, r.split.train_count if r.split else None) for r in adapter.training.list_runs().data])
print("map files", [(f.name, f.size) for f in adapter.maps.list_map_files().data])
print("logs", [(f.name, f.size) for f in adapter.logs.files().data])
maps = adapter.maps.query(MapFilters()).data
print("map", maps.total_matching, maps.plottable, maps.invalid_coords, maps.returned, maps.provenance)
print("variants", [(v.label, v.count) for v in adapter.labels.trainable_variants().data])

client = Client(raise_request_exception=False)
paths = [
    "/", "/healthz/", "/system/", "/issues/", "/issues/raw/", "/data/", "/data/reports/",
    "/data/reports/?page=2&page_size=25&sort=obs_time&dir=asc", "/labels/", "/training/",
    "/evaluation/", "/evaluation/compare/", "/registry/", "/maps/", "/maps/data/",
    "/maps/files/", "/logs/", "/logs/?file=collector.log", "/nope/",
]
failures = 0
for path in paths:
    response = client.get(path)
    ok = response.status_code < 500
    print(response.status_code, path, "OK" if ok else "FAIL")
    failures += 0 if ok else 1
print("FAILURES", failures)
sys.exit(1 if failures else 0)
