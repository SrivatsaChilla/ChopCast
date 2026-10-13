"""Geospatial visualization for ChopCast.

This module generates interactive maps of turbulence reports, allowing researchers
to visually audit model predictions and identify geospatial patterns.

See docs/ROADMAP.md Milestone 5.
"""

from __future__ import annotations

import folium
from folium.plugins import HeatMap
import pandas as pd
from pathlib import Path
from typing import Any

from chopcast.config import Settings
from chopcast.registry.store import SqliteModelRegistry
from chopcast.models.protocol import Model
from chopcast.collector.validators import DefaultRowValidator


log = get_logger(__name__) if 'get_logger' in globals() else None

# Severity color mapping (standardized across the project)
SEVERITY_COLORS = {
    "None": "blue",
    "Light": "green",
    "Moderate": "orange",
    "Severe": "red",
}

def generate_map(
    settings: Settings,
    registry: SqliteModelRegistry,
    model_id: int | None = None,
    output_path: Path = Path("turbulence_map.html"),
) -> Path:
    """Generate a Folium map of reports colored by severity.

    If model_id is provided, it uses model predictions; otherwise, it uses
    the ground truth labels from the 'trainable' view.
    """
    paths = settings.to_paths()

    # 1. Load Data
    import sqlite3
    conn = sqlite3.connect(paths.raw_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM trainable")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise ValueError("no data available in 'trainable' view to map")

    # 2. Setup Validation and Model
    validator = DefaultRowValidator(settings.collector.validation)

    labels = []
    if model_id is None:
        labels = [row["severity_label"] for row in rows]
    else:
        record = registry.get(model_id)
        if not record:
            raise KeyError(f"model {model_id} not found in registry")

        from chopcast.models.baseline_sklearn import BaselineSklearn
        model = BaselineSklearn.load(Path(record.artifact_path))

        from chopcast.processing.pipeline import process, build_deps
        deps = build_deps(settings.processing, settings.labeling, str(paths.root_path))

        texts = []
        valid_rows = []
        for row in rows:
            feat = process(row, deps)
            if feat:
                texts.append(feat.clean_text)
                valid_rows.append(row)

        predictions = model.predict(texts)
        labels = predictions
        rows = valid_rows

    # 3. Build Map
    avg_lat = sum(r["lat"] for r in rows if r["lat"]) / len(rows)
    avg_lon = sum(r["lon"] for r in rows if r["lon"]) / len(rows)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=4, control_scale=True)

    # Create layers for toggleable views
    reports_layer = folium.FeatureGroup(name="Individual Reports")
    heatmap_layer = folium.FeatureGroup(name="Turbulence HeatMap")

    heat_data = []

    # 4. Add Markers and collect heat data
    for row, label in zip(rows, labels):
        if not row["lat"] or not row["lon"]:
            continue

        # Validate coordinates
        row_series = pd.Series(dict(row))
        verdict = validator.validate(row_series)
        is_suspicious = not verdict.ok and verdict.reason in ("invalid_lat", "invalid_lon")

        color = SEVERITY_COLORS.get(label, "gray")

        # Construct enhanced popup
        if model_id:
            severity_html = f"<b>Actual:</b> {row['severity_label']} | <b>Predicted:</b> {label}<br>"
        else:
            severity_html = f"<b>Severity:</b> {label}<br>"

        warning_html = f"<i style='color:red;'><b>Warning:</b> Suspicious Coordinates ({verdict.detail})</i><br>" if is_suspicious else ""

        popup_text = (
            f"{warning_html}{severity_html}"
            f"<b>Time:</b> {row['obs_time']}<br>"
            f"<b>Alt:</b> {row['altitude']}<br>"
            f"<b>Aircraft:</b> {row['aircraft']}<br>"
            f"<b>Text:</b> {row['raw_text'][:100]}..."
        )

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5 if not is_suspicious else 8,
            popup=folium.Popup(popup_text, max_width=300),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7 if not is_suspicious else 0.3,
        ).add_to(reports_layer)

        if not is_suspicious:
            heat_data.append([row["lat"], row["lon"]])

    # 5. Add HeatMap
    if heat_data:
        HeatMap(data=heat_data).add_to(heatmap_layer)

    reports_layer.add_to(m)
    heatmap_layer.add_to(m)
    folium.LayerControl().add_to(m)

    m.save(str(output_path))
    return output_path

__all__ = ["generate_map"]
