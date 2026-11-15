"""Temporary: assert the live dashboard reports the known counts."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("CHOPCAST_DASHBOARD_DEBUG", "1")

import django

django.setup()

from django.test import Client

client = Client(raise_request_exception=False)

# Adapter-level checks are the source of truth.
from adapters import get_adapter

adapter = get_adapter()
summary = adapter.reports.summary().data
print("reports", summary.total, "trainable", summary.trainable_rows, "with_coords", summary.with_coords, "invalid", summary.invalid_coords, "without", summary.without_coords)
print("by_type", summary.by_type)
labels = adapter.labels.distribution().data
print("labels total", labels.total, "labelled", labels.labelled, "unlabelled", labels.unlabelled)
models = adapter.registry.list_models().data
print("models", [(m.id, m.model_version, m.model_kind) for m in models])
promotions = adapter.registry.promotions().data
print("promotions", promotions)
for record in adapter.evaluation.list_evaluations().data:
    print("eval", record.model_version, record.source, record.metrics.get("accuracy"), record.metrics.get("macro_f1"), record.metrics.get("n_samples"))
print("map files", adapter.maps.list_map_files().data)
print("logs", [(f.name, f.size) for f in adapter.logs.files().data])
maps = adapter.maps.query(__import__("adapters.maps", fromlist=["MapFilters"]).MapFilters()).data
print("map points", maps.total_matching, maps.plottable, maps.invalid_coords, maps.returned, maps.provenance)
print("trainable variants", [(v.label, v.count) for v in adapter.labels.trainable_variants().data])

checks = {
    "summary.total": (summary.total, 3525),
    "summary.trainable": (summary.trainable_rows, 290),
    "models": (len(models), 2),
    "promotions": (len(promotions), 0),
    "map plottable": (maps.plottable, 3525 - maps.invalid_coords),
}
for key, (got, want) in checks.items():
    print(key, got, "==", want, got == want)
