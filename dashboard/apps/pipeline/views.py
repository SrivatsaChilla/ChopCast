"""Data, labels, training, evaluation, registry, and log pages."""

from __future__ import annotations

import logging
from pathlib import Path

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from adapters.evaluation import class_rows, confusion, numeric_metrics
from adapters.reports import SORT_COLUMNS, ReportFilters
from adapters.schema_probe import schema_diff
from adapters.types import SourceState
from apps.core.params import (
    get_date,
    get_float,
    get_hash,
    get_int,
    get_str,
    page_number,
    page_size,
)

log = logging.getLogger(__name__)

SORT_FIELDS = set(SORT_COLUMNS) | {"hash"}


def _safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        log.exception("adapter call failed")
        return default


def _adapter(request):
    return getattr(request, "adapter", None)


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------
def data(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    if adapter is None:
        return render(request, "pipeline/data.html", {"page_title": "Data"})
    summary_result = _safe(adapter.reports.summary)
    quality_result = _safe(adapter.reports.quality)
    variants_result = _safe(adapter.labels.trainable_variants)
    recent_result = _safe(lambda: adapter.reports.recent(10))
    runs_result = _safe(lambda: adapter.reports.run_history(10))
    rejected_result = _safe(lambda: adapter.reports.rejected(10))
    profile = _safe(adapter.reports.profile)
    labels_result = _safe(adapter.labels.distribution)
    return render(
        request,
        "pipeline/data.html",
        {
            "page_title": "Data",
            "summary": summary_result.data if summary_result else None,
            "summary_status": summary_result.status if summary_result else None,
            "quality": quality_result.data if quality_result else None,
            "variants": variants_result.data if variants_result else None,
            "recent": recent_result.data if recent_result else None,
            "recent_status": recent_result.status if recent_result else None,
            "runs": runs_result.data if runs_result else None,
            "rejected": rejected_result.data if rejected_result else None,
            "profile": profile,
            "diff": schema_diff(profile) if profile else None,
            "labels": labels_result.data if labels_result else None,
            "source": {
                "path": str(adapter.settings.raw_db),
                "display": adapter.settings.display_path(adapter.settings.raw_db),
                "size": adapter.reports.db.size,
                "mtime": adapter.reports.db.mtime,
                "exists": adapter.reports.db.exists,
            },
        },
    )


def reports(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    params = request.GET
    filters = ReportFilters(
        q=get_str(params, "q", max_len=200),
        report_type=get_str(params, "report_type", allowed=_report_types(adapter)),
        label_layer=get_str(params, "label_layer", "any", allowed={"any", "primary", "secondary", "combined"}),
        label=get_str(params, "label", allowed=_label_values(adapter)),
        date_from=get_date(params, "date_from"),
        date_to=get_date(params, "date_to"),
        alt_min=get_float(params, "alt_min", minimum=-2_000, maximum=100_000),
        alt_max=get_float(params, "alt_max", minimum=-2_000, maximum=100_000),
        has_coords=get_str(params, "has_coords", allowed={"", "yes", "no"}),
        sort=get_str(params, "sort", "obs_time", allowed=SORT_FIELDS),
        direction=get_str(params, "dir", "desc", allowed={"asc", "desc"}),
    )
    if adapter is None:
        return render(request, "pipeline/reports.html", {"page_title": "Reports", "filters": filters})
    default = adapter.settings.page_size
    size = page_size(params, default, adapter.settings.max_page_size)
    result = _safe(lambda: adapter.reports.list_reports(filters, page=page_number(params), page_size=size))
    context = {
        "page_title": "Reports",
        "filters": filters,
        "result": result,
        "page_obj": result.data if result else None,
        "rows": result.data.items if result and result.data else (),
        "status": result.status if result else None,
        "report_types": sorted(_report_types(adapter)),
        "label_values": sorted(_label_values(adapter)),
        "page_sizes": (25, 50, 100, 200),
        "total_all": _safe(lambda: adapter.reports.summary().data.total, 0),
    }
    if request.headers.get("HX-Request"):
        return render(request, "pipeline/_reports_table.html", context)
    return render(request, "pipeline/reports.html", context)


def report_detail(request: HttpRequest, report_hash: str) -> HttpResponse:
    adapter = _adapter(request)
    safe_hash = get_hash(report_hash)
    result = _safe(lambda: adapter.reports.get_report(safe_hash)) if adapter and safe_hash else None
    if result is None or result.data is None:
        return render(
            request,
            "errors/404.html",
            {
                "page_title": "Report not found",
                "message": f"No report with hash {report_hash}.",
            },
            status=404,
        )
    return render(
        request,
        "pipeline/report_detail.html",
        {
            "page_title": f"Report {report_hash[:12]}",
            "detail": result.data,
            "status": result.status,
        },
    )


# ----------------------------------------------------------------------
# Labels
# ----------------------------------------------------------------------
def labels(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    if adapter is None:
        return render(request, "pipeline/labels.html", {"page_title": "Labels"})
    distribution_result = _safe(adapter.labels.distribution)
    variants_result = _safe(adapter.labels.trainable_variants)
    rules = _safe(adapter.labels.rules)
    raw_rows = _safe(lambda: adapter.labels.raw_value_preview(200), []) or []
    for row in raw_rows:
        try:
            row["mapped"], row["rule"] = rules.map(row.get("value"))
        except Exception:
            row["mapped"], row["rule"] = "None", "unmapped"
    evaluations = _safe(adapter.evaluation.list_evaluations)
    zero_support: list[str] = []
    for record in (evaluations.data if evaluations else []) or []:
        for item in class_rows(record.metrics):
            if item.support == 0:
                zero_support.append(f"{record.model_version}: {item.label}")
    distribution = distribution_result.data if distribution_result else None
    chart = _label_chart(distribution)
    return render(
        request,
        "pipeline/labels.html",
        {
            "page_title": "Labels",
            "distribution": distribution,
            "status": distribution_result.status if distribution_result else None,
            "variants": variants_result.data if variants_result else None,
            "variants_status": variants_result.status if variants_result else None,
            "rules": rules,
            "raw_rows": raw_rows,
            "rules_path": adapter.settings.config_dir / "labeling.yaml",
            "chart": chart,
            "zero_support": zero_support,
            "evaluation_count": len(evaluations.data) if evaluations and evaluations.data else 0,
        },
    )


# ----------------------------------------------------------------------
# Training
# ----------------------------------------------------------------------
def training(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    if adapter is None:
        return render(request, "pipeline/training.html", {"page_title": "Training"})
    runs_result = _safe(adapter.training.list_runs)
    splits_result = _safe(adapter.training.split_manifests)
    return render(
        request,
        "pipeline/training.html",
        {
            "page_title": "Training",
            "runs": runs_result.data if runs_result else None,
            "status": runs_result.status if runs_result else None,
            "splits": splits_result.data if splits_result else None,
            "splits_status": splits_result.status if splits_result else None,
            "feature_status": _safe(adapter.training.feature_status),
            "artifact_status": _safe(adapter.training.artifact_status),
        },
    )


def training_detail(request: HttpRequest, key: str) -> HttpResponse:
    adapter = _adapter(request)
    result = _safe(lambda: adapter.training.get_run(key)) if adapter else None
    if result is None or result.data is None:
        return render(
            request,
            "errors/404.html",
            {"page_title": "Training run not found", "message": f"No training run with key {key}."},
            status=404,
        )
    run = result.data
    path = Path(run.artifact_resolved) if run.artifact_resolved else None
    manifest = _safe(lambda: adapter.training.manifest(path), {}) if adapter else {}
    files = _safe(lambda: adapter.registry.artifact_files(path), ()) if adapter else ()
    return render(
        request,
        "pipeline/training_detail.html",
        {
            "page_title": f"Training {run.model_version or run.key}",
            "run": run,
            "status": result.status,
            "manifest": manifest,
            "files": files,
            "classes": class_rows(run.metrics),
            "matrix": confusion(run.metrics),
            "matrix_rows": _matrix_rows(confusion(run.metrics)),
            "numbers": numeric_metrics(run.metrics),
            "split": run.split,
            "artifact_path": path,
        },
    )


# ----------------------------------------------------------------------
# Evaluation
# ----------------------------------------------------------------------
def evaluation(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    if adapter is None:
        return render(request, "pipeline/evaluation.html", {"page_title": "Evaluation"})
    result = _safe(adapter.evaluation.list_evaluations)
    rows = []
    for record in (result.data if result else []) or []:
        rows.append(
            {
                "record": record,
                "numbers": numeric_metrics(record.metrics),
                "classes": class_rows(record.metrics),
            }
        )
    return render(
        request,
        "pipeline/evaluation.html",
        {
            "page_title": "Evaluation",
            "rows": rows,
            "status": result.status if result else None,
            "models": [r["record"] for r in rows],
        },
    )


def evaluation_detail(request: HttpRequest, model_id: int) -> HttpResponse:
    adapter = _adapter(request)
    result = _safe(lambda: adapter.evaluation.get(model_id)) if adapter else None
    if result is None or result.data is None:
        return render(
            request,
            "errors/404.html",
            {"page_title": "Evaluation not found", "message": f"No model with id {model_id}."},
            status=404,
        )
    record = result.data
    previous = _safe(lambda: adapter.evaluation.previous(record)) if adapter else None
    comparison = (
        _safe(lambda: adapter.evaluation.compare(previous.model_id, record.model_id))
        if previous and adapter
        else None
    )
    return render(
        request,
        "pipeline/evaluation_detail.html",
        {
            "page_title": f"Evaluation {record.model_version}",
            "record": record,
            "status": result.status,
            "numbers": numeric_metrics(record.metrics),
            "classes": class_rows(record.metrics),
            "matrix": confusion(record.metrics),
            "matrix_rows": _matrix_rows(confusion(record.metrics)),
            "previous": previous,
            "comparison": comparison.data if comparison else None,
        },
    )


def evaluation_compare(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    if adapter is None:
        return render(request, "pipeline/evaluation_compare.html", {"page_title": "Compare"})
    records_result = _safe(adapter.evaluation.list_evaluations)
    records = records_result.data if records_result else []
    all_ids = [r.model_id for r in (records or []) if r.metrics]
    default_a = all_ids[0] if all_ids else None
    default_b = all_ids[1] if len(all_ids) > 1 else None
    a = get_int(request.GET, "a", default_a or 0, minimum=0, maximum=10_000_000) or None
    b = get_int(request.GET, "b", default_b or 0, minimum=0, maximum=10_000_000) or None
    comparison = None
    if a is not None and b is not None:
        comparison = _safe(lambda: adapter.evaluation.compare(a, b))
    return render(
        request,
        "pipeline/evaluation_compare.html",
        {
            "page_title": "Compare evaluations",
            "records": records or [],
            "a": a,
            "b": b,
            "comparison": comparison.data if comparison else None,
            "comparison_status": comparison.status if comparison else None,
        },
    )


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------
def registry(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    if adapter is None:
        return render(request, "pipeline/registry.html", {"page_title": "Registry"})
    models_result = _safe(adapter.registry.list_models)
    promotions_result = _safe(adapter.registry.promotions)
    current_result = _safe(adapter.registry.current)
    profile = _safe(adapter.registry.profile)
    models = models_result.data if models_result else None
    rows = []
    for model in models or []:
        path = Path(model.artifact_resolved) if model.artifact_resolved else None
        rows.append(
            {
                "model": model,
                "files": _safe(lambda p=path: adapter.registry.artifact_files(p), ()),
            }
        )
    return render(
        request,
        "pipeline/registry.html",
        {
            "page_title": "Registry",
            "models": models,
            "rows": rows,
            "status": models_result.status if models_result else None,
            "promotions": promotions_result.data if promotions_result else None,
            "current": current_result.data if current_result else None,
            "profile": profile,
            "registry_path": str(adapter.settings.registry_db),
        },
    )


def registry_detail(request: HttpRequest, model_id: int) -> HttpResponse:
    adapter = _adapter(request)
    result = _safe(lambda: adapter.registry.get(model_id)) if adapter else None
    if result is None or result.data is None:
        return render(
            request,
            "errors/404.html",
            {"page_title": "Model not found", "message": f"No model with id {model_id}."},
            status=404,
        )
    model = result.data
    path = Path(model.artifact_resolved) if model.artifact_resolved else None
    promotions_result = _safe(adapter.registry.promotions) if adapter else None
    promotions = promotions_result.data if promotions_result else None
    return render(
        request,
        "pipeline/registry_detail.html",
        {
            "page_title": f"Model {model.model_version}",
            "model": model,
            "status": result.status,
            "files": _safe(lambda: adapter.registry.artifact_files(path), ()) if adapter else (),
            "manifest": _safe(lambda: adapter.training.manifest(path), {}) if adapter else {},
            "promotions": promotions,
            "model_promotions": [p for p in (promotions or []) if p.model_id == model_id],
            "evaluation": _safe(lambda: adapter.evaluation.get(model_id)) if adapter else None,
        },
    )


# ----------------------------------------------------------------------
# Logs / jobs
# ----------------------------------------------------------------------
def logs(request: HttpRequest) -> HttpResponse:
    adapter = _adapter(request)
    if adapter is None:
        return render(request, "pipeline/logs.html", {"page_title": "Logs / Jobs"})
    files_result = _safe(adapter.logs.files)
    files = files_result.data if files_result else []
    display = [adapter.settings.display_path(f.path) for f in (files or [])]
    selected = get_str(request.GET, "file", display[0] if display else "", max_len=500)
    level = get_str(request.GET, "level", "", allowed={"", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
    query = get_str(request.GET, "q", max_len=200)
    tail_result = (
        _safe(lambda: adapter.logs.tail(selected, level=level, q=query, limit=500))
        if selected
        else None
    )
    runs_result = _safe(lambda: adapter.reports.run_history(20))
    rejected_result = _safe(lambda: adapter.reports.rejected(20))
    training_result = _safe(lambda: adapter.training.list_runs())
    return render(
        request,
        "pipeline/logs.html",
        {
            "page_title": "Logs / Jobs",
            "files": files,
            "files_status": files_result.status if files_result else None,
            "selected": selected,
            "display_files": list(zip(files or [], display)),
            "tail": tail_result.data if tail_result else None,
            "tail_status": tail_result.status if tail_result else None,
            "level": level,
            "levels": ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
            "query": query,
            "runs": runs_result.data if runs_result else None,
            "rejected": rejected_result.data if rejected_result else None,
            "training_runs": training_result.data if training_result else None,
        },
    )


# ----------------------------------------------------------------------
def _report_types(adapter) -> set[str]:
    if adapter is None:
        return set()
    summary = _safe(adapter.reports.summary)
    if summary and summary.data:
        return {key for key in summary.data.by_type if key and key != "(null)"}
    return set()


def _label_values(adapter) -> set[str]:
    if adapter is None:
        return set()
    distribution = _safe(adapter.labels.distribution)
    if not distribution or not distribution.data:
        return set()
    values = {item.value for item in distribution.data.primary}
    values |= {item.value for item in distribution.data.secondary}
    return values


def _matrix_rows(matrix) -> list[dict]:
    if not matrix:
        return []
    return [
        {
            "label": matrix.labels[index] if index < len(matrix.labels) else str(index),
            "cells": [
                {
                    "label": matrix.labels[col] if col < len(matrix.labels) else str(col),
                    "value": value,
                    "actual": row[index] if index < len(row) else 0,
                }
                for col, value in enumerate(row)
            ],
        }
        for index, row in enumerate(matrix.matrix)
    ]


def _label_chart(distribution) -> dict:
    if not distribution:
        return {"labels": [], "primary": [], "combined": []}
    labels = ["None", "Light", "Moderate", "Severe"]
    primary: dict[str, int] = {label: 0 for label in labels}
    for item in distribution.primary:
        primary[item.mapped] = primary.get(item.mapped, 0) + item.count
    combined = distribution.combined or {}
    return {
        "labels": labels,
        "primary": [primary.get(label, 0) for label in labels],
        "combined": [int(combined.get(label, 0)) for label in labels],
    }
