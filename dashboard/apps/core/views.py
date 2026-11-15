"""Overview, health, system, issues, and error views."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from adapters.types import SourceState

log = logging.getLogger(__name__)


def _safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        log.exception("adapter call failed")
        return default


def overview(request: HttpRequest) -> HttpResponse:
    adapter = getattr(request, "adapter", None)
    if adapter is None:
        return render(
            request,
            "core/overview.html",
            {"page_title": "Overview", "adapter_error": getattr(request, "adapter_error", "adapter unavailable")},
        )

    summary_result = _safe(adapter.reports.summary)
    labels_result = _safe(adapter.labels.distribution)
    models_result = _safe(adapter.registry.list_models)
    current_result = _safe(adapter.registry.current)
    training_result = _safe(adapter.training.list_runs)
    runs_result = _safe(lambda: adapter.reports.run_history(limit=10))
    logs_result = _safe(adapter.logs.files)
    maps_result = _safe(adapter.maps.list_map_files)
    splits_result = _safe(adapter.training.split_manifests)
    evaluations_result = _safe(adapter.evaluation.list_evaluations)
    configs = _safe(adapter.system.config_files, []) or []
    feature_files = _safe(adapter.training.feature_files, []) or []
    profile = _safe(adapter.reports.profile)

    summary = summary_result.data if summary_result else None
    labels = labels_result.data if labels_result else None
    models = models_result.data if models_result else None
    current = current_result.data if current_result else None
    runs = runs_result.data if runs_result else None
    log_files = logs_result.data if logs_result else None
    map_files = maps_result.data if maps_result else None
    evaluations = evaluations_result.data if evaluations_result else None

    latest_run = runs[0] if runs else None
    degraded = _degenerate(evaluations)
    recent_errors = _recent_errors(adapter, log_files or [], runs or [])

    stages = [
        _stage(
            "collect",
            "Collect",
            state="ok" if latest_run else "empty",
            evidence=latest_run.started_at if latest_run else "no run record",
            counts=f"{summary.total:,} reports" if summary else "unknown",
            finding=(
                f"last run {latest_run.status} · {latest_run.rows_seen or 0:,} seen"
                if latest_run
                else "runs table exists but has no rows"
            ),
            url_name="pipeline:logs",
            issues=("ISS-086",),
        ),
        _stage(
            "migrate",
            "Migrate",
            state="warning" if profile and profile.state == "legacy" else "ok" if profile else "missing",
            evidence=f"migrations {profile.schema_migrations or 'none'}" if profile else "unknown",
            counts=profile.state if profile else "unknown",
            finding=(
                "legacy schema in use; migration path cannot upgrade it"
                if profile and profile.state == "legacy"
                else "schema profile detected"
            ),
            url_name="core:system",
            issues=("ISS-002", "ISS-011", "ISS-012"),
        ),
        _stage(
            "labels",
            "Parse / Label",
            state="warning" if labels and labels.warnings else "ok" if labels and labels.labelled else "empty",
            evidence=f"{labels.labelled:,} labelled" if labels else "no label data",
            counts=(
                f"{labels.labelled:,} / {labels.total:,} rows"
                if labels
                else "—"
            ),
            finding=(
                f"{labels.unlabelled:,} unlabelled · rules {labels.rules_version or 'unknown'}"
                if labels
                else "no reports table"
            ),
            url_name="pipeline:labels",
            issues=("ISS-008", "ISS-009", "ISS-035"),
        ),
        _stage(
            "features",
            "Features",
            state="ok" if feature_files else "empty",
            evidence=f"{len(feature_files)} file(s)" if feature_files else "no feature files",
            counts=f"{len(feature_files)}",
            finding="feature datasets are present" if feature_files else "data/features and data/processed are empty",
            url_name="pipeline:training",
            issues=("ISS-038",),
        ),
        _stage(
            "train",
            "Train",
            state="warning" if training_result and training_result.data else "empty",
            evidence=_first_timestamp(training_result.data if training_result else None),
            counts=f"{len(training_result.data or [])} inferred run(s)" if training_result else "—",
            finding=(
                "training history is inferred from registry rows and artifacts"
                if training_result and training_result.data
                else "no registry rows and no artifact directories"
            ),
            url_name="pipeline:training",
            issues=("ISS-001", "ISS-085"),
        ),
        _stage(
            "evaluate",
            "Evaluate",
            state="warning" if degraded else "ok" if evaluations else "empty",
            evidence=f"{len([e for e in evaluations or [] if e.metrics])} with metrics" if evaluations is not None else "—",
            counts=f"{len(evaluations or [])} model(s)" if evaluations is not None else "—",
            finding="metrics are degenerate (macro-F1 near chance)" if degraded else "persisted metrics available",
            url_name="pipeline:evaluation",
            issues=("ISS-043", "ISS-087"),
        ),
        _stage(
            "register",
            "Register",
            state="ok" if models else "empty",
            evidence=_first_timestamp(models, key="registered_at"),
            counts=f"{len(models or [])} model(s)" if models is not None else "—",
            finding=(
                f"production: {current.model_version}" if current else "no production model promoted"
            ),
            url_name="pipeline:registry",
            issues=("ISS-005", "ISS-007"),
        ),
        _stage(
            "map",
            "Map",
            state="ok" if map_files else "empty",
            evidence=f"{len(map_files or [])} generated file(s)" if map_files is not None else "—",
            counts=(
                f"{summary.trainable_rows:,} trainable row(s)"
                if summary
                else "—"
            ),
            finding=(
                "the dashboard renders its own map; generated HTML is not required"
            ),
            url_name="geo:maps",
            issues=("ISS-016", "ISS-017", "ISS-083", "ISS-084"),
        ),
        _stage(
            "logs",
            "Logs",
            state="ok" if log_files else "empty",
            evidence=_first_timestamp(log_files, key="mtime"),
            counts=f"{len(log_files or [])} log file(s)" if log_files is not None else "—",
            finding="two log destinations are possible" if log_files and len({lf.root for lf in log_files}) > 1 else "single log destination",
            url_name="pipeline:logs",
            issues=("ISS-086",),
        ),
        _stage(
            "config",
            "Config",
            state="ok" if configs else "empty",
            evidence=f"{len(configs)} YAML file(s)",
            counts=f"{len(configs)}",
            finding="configs are read as files; the core .env is not read",
            url_name="core:system",
            issues=("ISS-036", "ISS-037"),
        ),
    ]

    quality = _quality_items(summary, labels, models, current, profile, degraded, evaluations)

    return render(
        request,
        "core/overview.html",
        {
            "page_title": "Overview",
            "summary": summary,
            "summary_status": summary_result.status if summary_result else None,
            "labels": labels,
            "models": models,
            "current": current,
            "runs": runs,
            "log_files": log_files,
            "map_files": map_files,
            "stages": stages,
            "quality": quality,
            "recent_errors": recent_errors,
            "feature_count": len(feature_files),
            "split_count": len(splits_result.data or []) if splits_result else 0,
            "capabilities": _safe(adapter.capabilities),
        },
    )


def health(request: HttpRequest) -> JsonResponse:
    adapter = getattr(request, "adapter", None)
    if adapter is None:
        return JsonResponse(
            {"ok": False, "error": getattr(request, "adapter_error", "adapter unavailable")},
            status=503,
        )
    statuses = list(adapter.health())
    for extra in (_safe(adapter.evaluation.status), _safe(adapter.issues.status)):
        if extra is not None:
            statuses.append(extra)
    capabilities = _safe(adapter.capabilities)
    return JsonResponse(
        {
            "ok": not any(s.state in {SourceState.ERROR, SourceState.MISSING} for s in statuses),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": [s.as_dict() for s in statuses],
            "capabilities": asdict(capabilities) if capabilities else None,
        }
    )


def system(request: HttpRequest) -> HttpResponse:
    adapter = getattr(request, "adapter", None)
    snapshot = _safe(adapter.system.snapshot) if adapter else None
    diagnostics = _diagnostics(request, adapter, snapshot)
    return render(
        request,
        "core/system.html",
        {
            "page_title": "System",
            "snapshot": snapshot,
            "diagnostics": diagnostics,
            "adapter_error": getattr(request, "adapter_error", None) if adapter is None else None,
        },
    )


def issues(request: HttpRequest) -> HttpResponse:
    adapter = getattr(request, "adapter", None)
    result = _safe(adapter.issues.render) if adapter else None
    document = result.data if result else None
    return render(
        request,
        "core/issues.html",
        {
            "page_title": "Known Issues",
            "document": document,
            "status": result.status if result else None,
            "issues_path": adapter.issues.path if adapter else "",
            "adapter_error": getattr(request, "adapter_error", None) if adapter is None else None,
        },
    )


def issues_raw(request: HttpRequest) -> HttpResponse:
    adapter = getattr(request, "adapter", None)
    text = _safe(adapter.issues.raw_text) if adapter else None
    if not text:
        return render(
            request,
            "errors/404.html",
            {"page_title": "Issue register not found", "message": "docs/ISSUES.md could not be read."},
            status=404,
        )
    response = HttpResponse(text, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ISSUES.md"'
    response["Cache-Control"] = "no-store"
    return response


def not_found(request: HttpRequest, exception=None) -> HttpResponse:
    return render(
        request,
        "errors/404.html",
        {"page_title": "Not found", "message": "That page or record does not exist."},
        status=404,
    )


def server_error(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "errors/500.html",
        {"page_title": "Dashboard error"},
        status=500,
    )


# ----------------------------------------------------------------------
def _stage(key, name, *, state, evidence, counts, finding, url_name, issues) -> dict:
    from django.urls import reverse

    try:
        url = reverse(url_name)
    except Exception:
        url = "#"
    return {
        "key": key,
        "name": name,
        "state": state,
        "evidence": evidence,
        "counts": counts,
        "finding": finding,
        "url": url,
        "issues": issues,
    }


def _first_timestamp(items, key: str = "started_at") -> str:
    if not items:
        return "no record"
    for item in items:
        value = getattr(item, key, None)
        if value:
            return str(value)
    return "no timestamp"


def _degenerate(evaluations) -> bool:
    if not evaluations:
        return False
    for record in evaluations:
        metrics = record.metrics or {}
        macro = metrics.get("macro_f1")
        samples = metrics.get("n_samples")
        try:
            if macro is not None and float(macro) <= 0.34 and samples:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _quality_items(summary, labels, models, current, profile, degraded, evaluations) -> list[dict]:
    items: list[dict] = []
    if profile and profile.state == "legacy":
        items.append(
            {
                "state": "warning",
                "text": "The raw database uses the legacy schema; migrations cannot upgrade it in place.",
                "url_name": "core:system",
                "anchor": "iss-002",
                "issues": ("ISS-002", "ISS-011"),
            }
        )
    if labels and labels.warnings:
        items.append(
            {
                "state": "warning",
                "text": labels.warnings[0],
                "url_name": "pipeline:labels",
                "issues": ("ISS-009", "ISS-003"),
            }
        )
    if labels and labels.total and labels.unlabelled / max(1, labels.total) > 0.9:
        items.append(
            {
                "state": "warning",
                "text": f"{labels.unlabelled:,} of {labels.total:,} reports have no stored label.",
                "url_name": "pipeline:labels",
                "issues": ("ISS-008",),
            }
        )
    if degraded:
        items.append(
            {
                "state": "warning",
                "text": "Persisted metrics are degenerate: macro-F1 is at chance and most classes have zero support.",
                "url_name": "pipeline:evaluation",
                "issues": ("ISS-043",),
            }
        )
    if models and current is None:
        items.append(
            {
                "state": "info",
                "text": "Registry has models but no production promotion.",
                "url_name": "pipeline:registry",
                "issues": ("ISS-005",),
            }
        )
    if summary and summary.without_coords:
        items.append(
            {
                "state": "info",
                "text": f"{summary.without_coords:,} reports have no coordinates and cannot appear on the map.",
                "url_name": "geo:maps",
                "issues": ("ISS-018",),
            }
        )
    return items


def _recent_errors(adapter, log_files, runs) -> list[dict]:
    errors: list[dict] = []
    for log_file in log_files[:10]:
        result = _safe(lambda lf=log_file: adapter.logs.tail(lf.path, level="ERROR", limit=10))
        for entry in (result.data if result else []) or []:
            errors.append(
                {
                    "kind": "log",
                    "when": entry.timestamp,
                    "source": log_file.name,
                    "text": entry.raw[:400],
                    "level": entry.level or "ERROR",
                }
            )
    for run in runs:
        if str(run.status).lower() not in {"ok", "success", "succeeded"}:
            errors.append(
                {
                    "kind": "run",
                    "when": run.started_at,
                    "source": f"run #{run.id}",
                    "text": run.error or f"status {run.status}",
                    "level": "ERROR",
                }
            )
    errors.sort(key=lambda item: item.get("when") or "", reverse=True)
    return errors[:10]


def _diagnostics(request, adapter, snapshot) -> str:
    lines = [
        "ChopCast dashboard diagnostics",
        f"generated: {datetime.now(timezone.utc).isoformat()}",
        f"dashboard: {settings.DASHBOARD_VERSION}",
        f"read-only: yes",
        "",
    ]
    if adapter is None:
        lines.append(f"adapter error: {getattr(request, 'adapter_error', 'unknown')}")
        return "\n".join(lines)
    lines.append(f"profile: {adapter.settings.profile or '(none)'}")
    if snapshot:
        lines.extend(
            [
                f"python: {snapshot.python_version}",
                f"django: {snapshot.django_version}",
                f"platform: {snapshot.platform}",
                f"timezone: {snapshot.timezone}",
                "",
                "paths:",
            ]
        )
        for path in snapshot.paths:
            lines.append(
                f"  {path.key}: {'present' if path.exists else 'missing'} · "
                f"{'dir' if path.is_dir else 'file'} · {adapter.settings.display_path(path.path)}"
            )
        lines.append("")
        lines.append("checks:")
        for check in snapshot.checks:
            lines.append(f"  [{check.state}] {check.title}: {check.detail}")
            if check.issues:
                lines.append(f"      issues: {', '.join(check.issues)}")
    return "\n".join(lines)
