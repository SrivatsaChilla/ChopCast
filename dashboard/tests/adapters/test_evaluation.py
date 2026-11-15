from __future__ import annotations

from adapters.evaluation import EvaluationService, class_rows, confusion
from adapters.settings import AdapterSettings
from adapters.types import SourceState


def test_metrics_sources(full_settings):
    service = EvaluationService(full_settings)
    records = service.list_evaluations()
    assert records.data is not None
    by_id = {record.model_id: record for record in records.data}
    assert by_id[1].source == "metrics.json"
    assert by_id[1].metrics is not None
    assert by_id[1].metrics["accuracy"] == 0.8
    assert by_id[2].source == "report.json"
    assert by_id[2].metrics is not None
    assert by_id[2].metrics["accuracy"] == 0.9
    assert by_id[3].metrics is None
    assert by_id[3].source == "none"
    assert records.status.state is SourceState.OK


def test_class_rows_and_confusion(full_settings):
    record = EvaluationService(full_settings).get(1).data
    assert record is not None
    rows = class_rows(record.metrics)
    assert {row.label for row in rows} == {"None", "Light"}
    assert rows[0].support == 2

    matrix = confusion(record.metrics)
    assert matrix is not None
    assert matrix.labels == ("None", "Light")
    assert matrix.matrix == ((2, 0), (1, 1))


def test_compare_flags_kind_mismatch(full_settings):
    service = EvaluationService(full_settings)
    result = service.compare(1, 2)
    assert result.data is not None
    assert result.data.a.model_id == 1
    assert result.data.b.model_id == 2
    assert any("Model kinds differ" in warning for warning in result.data.warnings)
    accuracy = next(field for field in result.data.fields if field.name == "accuracy")
    assert round(accuracy.delta or 0, 6) == 0.1


def test_missing_registry(tmp_path):
    service = EvaluationService(AdapterSettings.from_env(tmp_path / "missing"))
    result = service.list_evaluations()
    assert result.data is None
    assert result.status.state is SourceState.MISSING
    assert service.get(1).data is None
