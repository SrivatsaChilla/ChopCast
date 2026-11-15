from __future__ import annotations

from django.urls import path

from apps.pipeline import views

app_name = "pipeline"

urlpatterns = [
    path("data/", views.data, name="data"),
    path("data/reports/", views.reports, name="reports"),
    path("data/reports/<str:report_hash>/", views.report_detail, name="report_detail"),
    path("labels/", views.labels, name="labels"),
    path("training/", views.training, name="training"),
    path("training/<str:key>/", views.training_detail, name="training_detail"),
    path("evaluation/", views.evaluation, name="evaluation"),
    path("evaluation/compare/", views.evaluation_compare, name="evaluation_compare"),
    path("evaluation/<int:model_id>/", views.evaluation_detail, name="evaluation_detail"),
    path("registry/", views.registry, name="registry"),
    path("registry/<int:model_id>/", views.registry_detail, name="registry_detail"),
    path("logs/", views.logs, name="logs"),
]
