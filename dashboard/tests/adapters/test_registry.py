from __future__ import annotations

from adapters.registry import RegistryService
from adapters.settings import AdapterSettings
from adapters.types import SourceState


def test_models_and_promotions(full_settings):
    service = RegistryService(full_settings)
    models = service.list_models()
    assert models.data is not None
    assert [model.id for model in models.data] == [3, 2, 1]
    assert models.status.state is SourceState.OK

    by_id = {model.id: model for model in models.data}
    assert by_id[1].artifact_exists is True
    assert by_id[1].promotions == ("production",)
    assert any("stored kind" in warning for warning in by_id[1].warnings)
    assert any("relative" in warning for warning in by_id[1].warnings)
    assert by_id[2].artifact_exists is True
    assert by_id[2].promotions == ()
    assert by_id[3].artifact_exists is False
    assert any("artifact directory not found" in warning for warning in by_id[3].warnings)
    assert any("metrics_json is not valid JSON" in warning for warning in by_id[3].warnings)

    promotions = service.promotions()
    assert [(p.model_id, p.tag) for p in promotions.data] == [(1, "production")]
    current = service.current()
    assert current.data is not None
    assert current.data.id == 1


def test_missing_model_and_registry(tmp_path):
    settings = AdapterSettings.from_env(tmp_path / "missing")
    service = RegistryService(settings)
    result = service.get(99)
    assert result.data is None
    assert result.status.state is SourceState.MISSING
    assert service.list_models().data is None
    assert service.promotions().data == []


def test_artifact_files_are_allowlisted(full_settings):
    service = RegistryService(full_settings)
    model = service.get(1).data
    assert model is not None
    files = service.artifact_files(model.artifact_resolved and service.resolve_artifact(model.artifact_path))
    assert {item.name for item in files} == {"pipeline.joblib", "manifest.txt", "metrics.json", "lineage.json"}
