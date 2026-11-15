"""Temporary smoke test: render every dashboard page against the live data, read-only."""
from __future__ import annotations

import os
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
paths = [
    "/",
    "/healthz/",
    "/system/",
    "/issues/",
    "/issues/raw/",
    "/data/",
    "/data/reports/",
    "/data/reports/?page=2&page_size=25&sort=obs_time&dir=asc",
    "/labels/",
    "/training/",
    "/evaluation/",
    "/evaluation/compare/",
    "/registry/",
    "/maps/",
    "/maps/data/",
    "/maps/files/",
    "/logs/",
    "/logs/?file=collector.log",
    "/nope/",
]
failures = 0
for path in paths:
    response = client.get(path)
    ok = response.status_code < 500
    print(f"{response.status_code} {len(response.content):>8} {path} {'OK' if ok else 'FAIL'}")
    if not ok:
        failures += 1
print("FAILURES", failures)
sys.exit(1 if failures else 0)
