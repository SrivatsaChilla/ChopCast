from __future__ import annotations

from adapters.settings import AdapterSettings
from adapters.training import TrainingService
from adapters.types import SourceState


def test_runs_are_reconstructed_with_provenance(full_settings):
    service = TrainingService(full_settings)
    result = service.list_runs()
    assert result.data is not None
    runs = {run.key: run for run in result.data}
    assert set(runs) == {"registry:1", "registry:2", "registry:3"}

    baseline = runs["registry:1"]
    assert baseline.source_path == "db-orchestrator"
    assert baseline.split is not None
    assert baseline.split.train_count == 4
    assert baseline.split.test_count == 2
    assert any("code_commit" in warning for warning in baseline.warnings)
    assert any("duplicated" in warning for warning in baseline.warnings)

    transformer = runs["registry:2"]
    assert transformer.source_path == "jsonl-trainer"
    assert transformer.split is not None
    assert transformer.split.train_count == 3
    assert transformer.model_kind_manifest == "transformer"

    missing = runs["registry:3"]
    assert missing.source_path == "registry-only"
    assert missing.artifact_exists is False
    assert any("no split manifest" in warning for warning in missing.warnings)


def test_orphan_artifact_is_detected(full_settings):
    service = TrainingService(full_settings)
    orphan = service.settings.artifact_dirs[0] / "orphan-demo"
    orphan.mkdir(parents=True)
    (orphan / "manifest.txt").write_text("model_version=orphan\n", encoding="utf-8")
    runs = service.list_runs().data
    assert runs is not None
    assert "artifact:orphan-demo" in {run.key for run in runs}
    orphan_run = next(run for run in runs if run.key == "artifact:orphan-demo")
    assert any("no registry row" in warning for warning in orphan_run.warnings)


def test_get_run_and_splits(full_settings):
    service = TrainingService(full_settings)
    found = service.get_run("registry:1")
    assert found.data is not None
    assert found.data.model_version == "demo-baseline"
    missing = service.get_run("nope")
    assert missing.data is None
    assert missing.status.state is SourceState.MISSING

    splits = service.split_manifests()
    assert splits.data is not None
    assert len(splits.data) == 1
    assert splits.data[0].name == "split-demo-baseline.json"


def test_statuses_and_missing_sources(tmp_path):
    service = TrainingService(AdapterSettings.from_env(tmp_path / "missing"))
    assert service.artifact_status().state is SourceState.MISSING
    assert service.feature_status().state is SourceState.MISSING
    assert service.feature_files() == []
    assert service.list_runs().data is None
    assert service.split_manifests().data == []
