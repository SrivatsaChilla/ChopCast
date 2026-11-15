from __future__ import annotations

from adapters.reports import ReportFilters, ReportService
from adapters.settings import AdapterSettings
from adapters.types import SourceState
from tests.fixtures import build


def test_summary_counts(settings):
    service = ReportService(settings)
    result = service.summary()
    assert result.data is not None
    summary = result.data
    assert summary.total == 6
    assert summary.trainable_rows == 3
    assert summary.by_type == {"PIREP": 3, "AIREP": 2, "Urgent PIREP": 1}
    assert summary.primary_labelled == 4
    assert summary.secondary_labelled == 1
    assert summary.with_coords == 4
    assert summary.without_coords == 1
    assert summary.invalid_coords == 1
    assert summary.distinct_hashes == 6
    assert summary.first_obs_time is not None
    assert summary.last_obs_time is not None


def test_filters_and_sorting(settings):
    service = ReportService(settings)
    pireps = service.list_reports(ReportFilters(report_type="PIREP"))
    assert pireps.data is not None
    assert pireps.data.total == 3

    search = service.list_reports(ReportFilters(q="bravo"))
    assert search.data is not None
    assert search.data.total == 1
    assert search.data.items[0].aircraft == "N101AB"

    labelled = service.list_reports(ReportFilters(label_layer="combined", label="MOD"))
    assert labelled.data is not None
    assert labelled.data.total == 1

    coords = service.list_reports(ReportFilters(has_coords="yes"), page_size=50)
    assert coords.data is not None
    assert coords.data.total == 4

    missing = service.list_reports(ReportFilters(has_coords="no"))
    assert missing.data is not None
    assert missing.data.total == 2

    ascending = service.list_reports(ReportFilters(sort="altitude", direction="asc"), page_size=50)
    assert ascending.data is not None
    assert ascending.data.items[0].altitude == 30000.0
    assert ascending.data.items[-1].altitude == 35000.0


def test_pagination_clamps(settings):
    service = ReportService(settings)
    page = service.list_reports(ReportFilters(), page=2, page_size=2)
    assert page.data is not None
    assert page.data.page == 2
    assert page.data.total == 6
    assert len(page.data.items) == 2

    clamped = service.list_reports(ReportFilters(), page=99, page_size=2)
    assert clamped.data is not None
    assert clamped.data.page == 3


def test_detail_and_missing(settings):
    service = ReportService(settings)
    found = service.get_report("0000000000000000000000000000000000000000000000000000000000000001")
    assert found.data is not None
    assert found.data.row.report_type == "PIREP"
    assert found.data.raw_json is not None

    missing = service.get_report("f" * 64)
    assert missing.data is None
    assert missing.status.state is SourceState.MISSING


def test_run_history_and_rejected(settings):
    service = ReportService(settings)
    runs = service.run_history()
    assert [run.id for run in runs.data] == [2, 1]
    assert runs.data[0].shape == "target"
    assert runs.data[0].error == "boom"

    rejected = service.rejected()
    assert len(rejected.data) == 1
    assert rejected.data[0].reason == "parse_error"


def test_empty_database(tmp_path):
    root = tmp_path / "empty"
    build.empty_db(root / "data" / "raw" / "pireps.db")
    service = ReportService(AdapterSettings.from_env(root))
    summary = service.summary()
    assert summary.data is not None
    assert summary.data.total == 0
    assert summary.status.state is SourceState.EMPTY
    page = service.list_reports(ReportFilters())
    assert page.data is not None
    assert page.data.total == 0
    assert page.data.items == ()


def test_missing_database_never_crashes(tmp_path):
    service = ReportService(AdapterSettings.from_env(tmp_path / "nothing"))
    summary = service.summary()
    assert summary.data is None
    assert summary.status.state is SourceState.MISSING
    page = service.list_reports(ReportFilters())
    assert page.data is None
    assert page.status.state is SourceState.MISSING
