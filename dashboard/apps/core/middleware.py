"""Request-scoped adapter construction with a safe failure mode."""

from __future__ import annotations

import logging

from adapters import get_adapter

log = logging.getLogger(__name__)


class DashboardAdapterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.adapter = None
        request.adapter_error = None
        try:
            request.adapter = get_adapter()
        except Exception as exc:  # a broken environment must not crash the frame
            request.adapter_error = str(exc)
            log.exception("could not construct the dashboard adapter")
        return self.get_response(request)
