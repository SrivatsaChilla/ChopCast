"""Interactive map, GeoJSON data endpoint, and generated-file browser."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse

from adapters.maps import MapFilters
from adapters.types import Page
from apps.core.params import (
    bbox,
    get_bool,
    get_date,
    get_float,
    get_str,
    page_number,
    page_size,
)

log = logging.getLogger(__name__)

SEVERITY_COLORS = {
    "None": "#2f6fed",
    "Light": "#1f9d55",
    "Moderate": "#d97706",
    "Severe": "#dc2626",
    "Unlabelled": "#6b7280",
}
LABEL_CLASSES = ("None", "Light", "Moderate", "Severe")


def _safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        log.exception("adapter call failed")
        return default


def _filters(request: HttpRequest, adapter) -> tuple[MapFilters, str]:
    params = request.GET
    layer = get_str(params, "label_layer", "combined", allowed={"combined", "primary", "secondary", "all"})
    label_class = get_str(params, "label", "", allowed={"", *LABEL_CLASSES})
    raw_values = _class_values(adapter, layer, label_class)
    report_types = _report_types(adapter)
    filters = MapFilters(
        label_layer=layer,
        label_values=raw_values,
        report_type=get_str(params, "report_type", allowed=report_types),
        date_from=get_date(params, "date_from"),
        date_to=get_date(params, "date_to"),
        alt_min=get_float(params, "alt_min", minimum=-2_000, maximum=100_000),
        alt_max=get_float(params, "alt_max", minimum=-2_000, maximum=100_000),
        q=get_str(params, "q", max_len=200),
        include_invalid=get_bool(params, "include_invalid"),
        bbox=bbox(params),
    )
    return filters, label_class


def maps(request: HttpRequest) -> HttpResponse:
    adapter = getattr(request, "adapter", None)
    if adapter is None:
        return render(request, "geo/maps.html", {"page_title": "Maps"})
    filters, label_class = _filters(request, adapter)
    size = page_size(request.GET, adapter.settings.page_size, adapter.settings.max_page_size)
    page = page_number(request.GET)
    result = _safe(
        lambda: adapter.maps.query(
            filters,
            limit=size,
            offset=(page - 1) * size,
        )
    )
    data = result.data if result else None
    rules = _safe(adapter.labels.rules)
    counts = _class_counts(data.label_counts if data else {}, rules)
    files_result = _safe(adapter.maps.list_map_files)
    files = files_result.data if files_result else []
    query = request.GET.copy()
    query.pop("page", None)
    query.pop("page_size", None)
    data_url = reverse("geo:map_data") + "?" + urlencode(query)
    page_obj = (
        Page(items=data.points, total=data.plottable, page=page, page_size=size)
        if data
        else None
    )
    label_map = {}
    for raw in (data.label_counts if data else {}):
        try:
            label_map[raw] = rules.map(raw)[0]
        except Exception:
            label_map[raw] = "Unlabelled"
    map_config = {
        "data_url": data_url,
        "world_url": static("vendor/world/ne_110m_land.geojson"),
        "tile_url": adapter.settings.tile_url,
        "colors": SEVERITY_COLORS,
        "raw_labels": label_map,
        "max_points": adapter.settings.map_max_points,
    }
    return render(
        request,
        "geo/maps.html",
        {
            "page_title": "Maps",
            "filters": filters,
            "label_class": label_class,
            "class_counts": counts,
            "colors": SEVERITY_COLORS,
            "classes": LABEL_CLASSES,
            "result": result,
            "map_status": result.status if result else None,
            "page_obj": page_obj,
            "data": data,
            "data_url": data_url,
            "map_config": map_config,
            "map_max_points": adapter.settings.map_max_points,
            "tile_url": adapter.settings.tile_url,
            "map_files": files,
            "map_files_status": files_result.status if files_result else None,
            "report_types": sorted(_report_types(adapter)),
            "provenance": data.provenance if data else "",
        },
    )


def map_data(request: HttpRequest) -> JsonResponse:
    adapter = getattr(request, "adapter", None)
    if adapter is None:
        return JsonResponse({"error": "adapter unavailable"}, status=503)
    filters, _ = _filters(request, adapter)
    result = _safe(
        lambda: adapter.maps.query(filters, limit=adapter.settings.map_max_points)
    )
    if result is None or result.data is None:
        return JsonResponse(
            {
                "type": "FeatureCollection",
                "features": [],
                "meta": {
                    "error": result.status.detail if result else "map query failed",
                    "provenance": result.status.provenance if result else None,
                },
            },
            status=503,
        )
    data = result.data
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [point.lon, point.lat]},
            "properties": {
                "hash": point.hash,
                "obs_time": point.obs_time,
                "altitude": point.altitude,
                "aircraft": point.aircraft,
                "report_type": point.report_type,
                "label_primary": point.label_primary,
                "label_secondary": point.label_secondary,
                "label_combined": point.label_combined,
                "label_layer": filters.label_layer,
                "suspicious": point.suspicious,
                "raw_text": point.raw_text,
            },
        }
        for point in data.points
    ]
    meta = {
        "total_matching": data.total_matching,
        "returned": data.returned,
        "truncated": data.truncated,
        "max_points": adapter.settings.map_max_points,
        "plottable": data.plottable,
        "invalid_coords": data.invalid_coords,
        "provenance": data.provenance,
        "filters": {
            "label_layer": filters.label_layer,
            "label_values": list(filters.label_values),
            "report_type": filters.report_type,
            "date_from": filters.date_from,
            "date_to": filters.date_to,
            "alt_min": filters.alt_min,
            "alt_max": filters.alt_max,
            "q": filters.q,
            "bbox": list(filters.bbox) if filters.bbox else None,
        },
        "warnings": list(data.warnings),
    }
    response = JsonResponse({"type": "FeatureCollection", "features": features, "meta": meta})
    response["Cache-Control"] = "no-store"
    return response


def map_files(request: HttpRequest) -> HttpResponse:
    adapter = getattr(request, "adapter", None)
    result = _safe(adapter.maps.list_map_files) if adapter else None
    return render(
        request,
        "geo/map_files.html",
        {
            "page_title": "Generated map files",
            "files": result.data if result else None,
            "status": result.status if result else None,
            "allow_downloads": adapter.settings.allow_downloads if adapter else False,
        },
    )


def map_file(request: HttpRequest, relpath: str) -> HttpResponse:
    adapter = getattr(request, "adapter", None)
    path = _safe(lambda: adapter.maps.resolve_file(relpath)) if adapter else None
    if path is None:
        raise Http404("map file not found")
    download = get_bool(request.GET, "download")
    if download and not adapter.settings.allow_downloads:
        return HttpResponse("Downloads are disabled.", status=403, content_type="text/plain")
    response = FileResponse(path.open("rb"), content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = "sandbox allow-scripts"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    if download:
        response["Content-Disposition"] = f'attachment; filename="{path.name}"'
    return response


# ----------------------------------------------------------------------
def _class_values(adapter, layer: str, label_class: str) -> tuple[str, ...]:
    if not label_class or adapter is None:
        return ()
    distribution = _safe(adapter.labels.distribution)
    if not distribution or not distribution.data:
        return ()
    values: set[str] = set()
    if layer in {"primary", "combined", "all"}:
        values |= {item.value for item in distribution.data.primary if item.mapped == label_class}
    if layer in {"secondary", "combined", "all"}:
        values |= {item.value for item in distribution.data.secondary if item.mapped == label_class}
    return tuple(sorted(values))


def _report_types(adapter) -> set[str]:
    if adapter is None:
        return set()
    summary = _safe(adapter.reports.summary)
    if summary and summary.data:
        return {key for key in summary.data.by_type if key and key != "(null)"}
    return set()


def _class_counts(raw_counts: dict[str, int], rules) -> dict[str, int]:
    counts = {label: 0 for label in (*LABEL_CLASSES, "Unlabelled")}
    for raw, count in raw_counts.items():
        try:
            mapped, _ = rules.map(raw)
        except Exception:
            mapped = "Unlabelled"
        counts[mapped] = counts.get(mapped, 0) + int(count)
    return counts
