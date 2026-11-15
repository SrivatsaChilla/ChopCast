"""Root URL configuration for the dashboard."""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include("apps.pipeline.urls")),
    path("", include("apps.geo.urls")),
]

if settings.ENABLE_ADMIN:
    from django.contrib import admin

    urlpatterns.insert(0, path(settings.ADMIN_URL, admin.site.urls))

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"
