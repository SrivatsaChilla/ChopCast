from __future__ import annotations

from django.urls import path

from apps.geo import views

app_name = "geo"

urlpatterns = [
    path("maps/", views.maps, name="maps"),
    path("maps/data/", views.map_data, name="map_data"),
    path("maps/files/", views.map_files, name="map_files"),
    path("maps/files/<path:relpath>", views.map_file, name="map_file"),
]
