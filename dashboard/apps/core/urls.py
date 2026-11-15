from __future__ import annotations

from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("healthz/", views.health, name="health"),
    path("system/", views.system, name="system"),
    path("issues/", views.issues, name="issues"),
    path("issues/raw/", views.issues_raw, name="issues_raw"),
]
