from __future__ import annotations

from adapters.schema_probe import probe_raw_db, probe_registry, schema_diff
from adapters.sqlite_ro import ReadOnlyDatabase


def test_target_schema(settings):
    profile = probe_raw_db(ReadOnlyDatabase(settings.raw_db))
    assert profile.state == "target"
    assert profile.runs_shape == "target"
    assert profile.has_rejected is True
    assert profile.schema_migrations == (1, 2, 3)
    assert profile.trainable_predicate == "primary_only"
    assert profile.has_report_type_in_trainable is True
    assert profile.reports_columns


def test_legacy_schema(full_settings):
    profile = probe_raw_db(ReadOnlyDatabase(full_settings.raw_db.parent / "legacy_pireps.db"))
    assert profile.state == "legacy"
    assert profile.runs_shape == "legacy"
    assert profile.has_rejected is False
    assert profile.has_report_type_in_trainable is False
    diff = schema_diff(profile)
    assert set(diff["reports_missing"]) == {"source_url", "source_etag"}
    assert set(diff["tables_missing"]) == {"rejected", "schema_migrations"}
    assert "inserted" in diff["runs_extra"]


def test_missing_database(tmp_path):
    profile = probe_raw_db(ReadOnlyDatabase(tmp_path / "missing.db"))
    assert profile.state == "missing"
    assert "not found" in " ".join(profile.notes)


def test_registry_probe(full_settings):
    profile = probe_registry(ReadOnlyDatabase(full_settings.registry_db))
    assert profile.state == "ok"
    assert profile.has_models is True
    assert profile.has_promotions is True
    assert profile.stray_raw_tables == ()
