"""Template context shared by every page."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from django.conf import settings
from django.urls import NoReverseMatch, reverse

log = logging.getLogger(__name__)

NAV = (
    ("overview", "Overview", "/"),
    ("data", "Data", "pipeline:data"),
    ("labels", "Labels", "pipeline:labels"),
    ("training", "Training", "pipeline:training"),
    ("evaluation", "Evaluation", "pipeline:evaluation"),
    ("registry", "Registry", "pipeline:registry"),
    ("maps", "Maps", "geo:maps"),
    ("logs", "Logs / Jobs", "pipeline:logs"),
    ("system", "System", "core:system"),
    ("issues", "Known Issues", "core:issues"),
)


def _nav_items(path: str) -> list[dict[str, str | bool]]:
    items: list[dict[str, str | bool]] = []
    for key, label, target in NAV:
        try:
            url = reverse(target)
        except NoReverseMatch:  # pragma: no cover - configuration guard
            continue
        active = path == url if url == "/" else path.startswith(url)
        items.append({"key": key, "label": label, "url": url, "active": active})
    return items


def dashboard(request):
    adapter = getattr(request, "adapter", None)
    health = []
    adapter_error = getattr(request, "adapter_error", None)
    if adapter is not None:
        try:
            health = adapter.health()
        except Exception as exc:  # never let a source break the chrome
            adapter_error = str(exc)
            log.exception("health check failed")
    statuses = {status.key: status for status in health}
    mtimes = [status.mtime for status in health if status.mtime]
    freshness = max(mtimes) if mtimes else datetime.now(timezone.utc).isoformat()
    return {
        "nav_items": _nav_items(request.path),
        "health": health,
        "health_statuses": statuses,
        "adapter": adapter,
        "adapter_error": adapter_error,
        "profile": adapter.settings.profile if adapter else None,
        "dashboard_version": settings.DASHBOARD_VERSION,
        "now_iso": datetime.now(timezone.utc).isoformat(),
        "freshness": freshness,
        "read_only": True,
    }
