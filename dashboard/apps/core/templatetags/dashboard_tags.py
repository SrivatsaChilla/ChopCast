"""Small presentation helpers for templates."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from django import template

register = template.Library()

SEVERITY_CSS = {
    "none": "sev-none",
    "light": "sev-light",
    "moderate": "sev-moderate",
    "severe": "sev-severe",
    "unlabelled": "sev-unknown",
}


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs: Any) -> str:
    """Return the current URL with query parameters replaced or removed (None)."""
    request = context.get("request")
    params = request.GET.copy() if request else {}
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    encoded = urlencode([(k, v) for k, v in params.items()])
    return f"?{encoded}" if encoded else "?"


@register.simple_tag(takes_context=True)
def sort_link(context, field: str) -> str:
    request = context.get("request")
    params = request.GET.copy() if request else {}
    current = params.get("sort", "")
    direction = params.get("dir", "desc")
    if current == field:
        params["dir"] = "asc" if direction != "asc" else "desc"
    else:
        params["dir"] = "desc"
    params["sort"] = field
    params.pop("page", None)
    encoded = urlencode(list(params.items()))
    return f"?{encoded}"


@register.simple_tag(takes_context=True)
def sort_arrow(context, field: str) -> str:
    request = context.get("request")
    if not request:
        return ""
    if request.GET.get("sort", "") != field:
        return "↕"
    return "↑" if request.GET.get("dir", "desc") == "asc" else "↓"


@register.filter
def severity_class(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in SEVERITY_CSS:
        return SEVERITY_CSS[text]
    upper = text.upper()
    if "SEV" in upper:
        return SEVERITY_CSS["severe"]
    if "MOD" in upper or "CHOP" in upper:
        return SEVERITY_CSS["moderate"]
    if "LGT" in upper or "LIGHT" in upper:
        return SEVERITY_CSS["light"]
    if "NEG" in upper or "NONE" in upper or "NIL" in upper:
        return SEVERITY_CSS["none"]
    return SEVERITY_CSS["unlabelled"]


@register.filter
def human_bytes(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number < 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} TB"


@register.filter
def json_pretty(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


@register.filter
def metric(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


@register.filter
def pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


@register.filter
def percent_of(value: Any, total: Any) -> str:
    try:
        denominator = float(total)
        if denominator <= 0:
            return "—"
        return f"{float(value) / denominator * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


@register.filter
def display(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


@register.filter
def get_item(mapping: Any, key: Any) -> Any:
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def short(value: Any, length: int = 12) -> str:
    text = str(value or "")
    return text[:length] + ("…" if len(text) > length else "")


@register.filter
def state_class(value: Any) -> str:
    text = str(value or "").lower()
    return f"state-{text}" if text else "state-empty"


@register.filter
def check_class(value: Any) -> str:
    return {
        "ok": "state-ok",
        "info": "state-info",
        "warning": "state-warning",
        "error": "state-error",
    }.get(str(value or "").lower(), "state-empty")


@register.filter
def level_class(value: Any) -> str:
    text = str(value or "").upper()
    return {
        "DEBUG": "lvl-debug",
        "INFO": "lvl-info",
        "WARNING": "lvl-warning",
        "WARN": "lvl-warning",
        "ERROR": "lvl-error",
        "CRITICAL": "lvl-error",
    }.get(text, "")


@register.filter
def yesno_icon(value: Any) -> str:
    return "✓" if value else "✗"


@register.filter
def dict_values(mapping: Any) -> list[Any]:
    return list(mapping.values()) if isinstance(mapping, dict) else []


@register.filter
def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
