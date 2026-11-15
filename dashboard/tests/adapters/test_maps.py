from __future__ import annotations

from pathlib import Path

from adapters.maps import MapFilters, MapService
from adapters.settings import AdapterSettings
from adapters.types import SourceState


def test_default_query_uses_trainable_view(full_settings):
    service = MapService(full_settings)
    result = service.query(MapFilters())
    assert result.data is not None
    data = result.data
    assert data.total_matching == 3
    assert data.invalid_coords == 1
    assert data.plottable == 2
    assert data.returned == 2
    assert data.provenance == "live trainable view (primary-only predicate)"
    assert data.truncated is False
    assert {point.hash for point in data.points} == {"0" * 63 + "1", "0" * 63 + "2"}
    assert data.label_counts == {"LGT": 1, "MOD": 1, "SEV": 1}
    assert data.warnings


def test_all_layer_and_label_filter(full_settings):
    service = MapService(full_settings)
    all_rows = service.query(MapFilters(label_layer="all"))
    assert all_rows.data is not None
    assert all_rows.data.total_matching == 6
    assert all_rows.data.invalid_coords == 2
    assert all_rows.data.plottable == 4

    light = service.query(MapFilters(label_layer="all", label_values=("LGT",)))
    assert light.data is not None
    assert light.data.total_matching == 1

    primary = service.query(MapFilters(label_layer="primary", label_values=("LGT",)))
    assert primary.data is not None
    assert primary.data.total_matching == 1

    combined = service.query(MapFilters(label_layer="combined"))
    assert combined.data is not None
    assert combined.data.total_matching == 3


def test_bbox_type_and_limit(full_settings):
    service = MapService(full_settings)
    bbox = service.query(MapFilters(bbox=(55.5, -12.0, 57.5, -10.5)))
    assert bbox.data is not None
    assert bbox.data.total_matching == 2

    by_type = service.query(MapFilters(report_type="Urgent PIREP"))
    assert by_type.data is not None
    assert by_type.data.total_matching == 1

    limited = service.query(MapFilters(), limit=1)
    assert limited.data is not None
    assert limited.data.returned == 1
    assert limited.data.truncated is True
    assert any("Showing the first" in warning for warning in limited.data.warnings)


def test_map_files_and_safe_paths(full_settings):
    service = MapService(full_settings)
    files = service.list_map_files()
    assert files.data is not None
    assert [item.name for item in files.data] == ["demo.html"]

    resolved = service.resolve_file("demo.html")
    assert resolved is not None
    assert resolved.name == "demo.html"

    assert service.resolve_file("../pireps.db") is None
    assert service.resolve_file("..\\pireps.db") is None
    assert service.resolve_file("/etc/passwd") is None
    assert service.resolve_file("C:\\Windows\\win.ini") is None
    assert service.resolve_file("") is None

    absolute_inside = str(resolved)
    assert service.resolve_file(absolute_inside) == resolved


def test_missing_database_and_files(tmp_path):
    settings = AdapterSettings.from_env(tmp_path / "missing")
    service = MapService(settings)
    result = service.query(MapFilters())
    assert result.data is None
    assert result.status.state is SourceState.MISSING
    files = service.list_map_files()
    assert files.data == []
    assert files.status.state is SourceState.MISSING
    assert service.file_status().state is SourceState.MISSING


def test_empty_database(tmp_path):
    from tests.fixtures import build

    root = tmp_path / "empty"
    build.empty_db(root / "data" / "raw" / "pireps.db")
    result = MapService(AdapterSettings.from_env(root)).query(MapFilters())
    assert result.data is not None
    assert result.data.total_matching == 0
    assert result.data.plottable == 0
    assert result.status.state is SourceState.EMPTY
