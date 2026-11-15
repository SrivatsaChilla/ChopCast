"""Training-run reconstruction from registry rows, artifacts, and split files.

There is no training-run table in the pipeline (ISS-085). A run is therefore a
join of evidence, and every run is labelled with the evidence path that
produced it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from adapters.registry import COMMON_ARTIFACT_FILES, RegistryService
from adapters.settings import AdapterSettings
from adapters.sqlite_ro import iso_mtime
from adapters.types import (
    ArtifactFile,
    Result,
    SourceState,
    SourceStatus,
    SplitInfo,
    TrainingRun,
)


def _status(
    key: str,
    label: str,
    state: SourceState,
    detail: str = "",
    path: str = "",
    mtime: str | None = None,
    provenance: str | None = None,
) -> SourceStatus:
    return SourceStatus(
        key=key, label=label, state=state, detail=detail, path=path, mtime=mtime, provenance=provenance
    )


class TrainingService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.registry = RegistryService(settings)

    # ------------------------------------------------------------------
    def artifact_status(self) -> SourceStatus:
        dirs = self.artifact_dirs_found()
        if not any(root.exists() for root in self.settings.artifact_dirs):
            return _status("artifacts", "Model artifacts", SourceState.MISSING, "no artifact directory exists")
        if not dirs:
            return _status("artifacts", "Model artifacts", SourceState.EMPTY, "no artifact directories")
        return _status("artifacts", "Model artifacts", SourceState.OK, f"{len(dirs)} artifact director(ies)")

    def feature_status(self) -> SourceStatus:
        files = self.feature_files()
        if not any(root.is_dir() for root in (self.settings.features_dir, self.settings.processed_dir)):
            return _status("features", "Feature datasets", SourceState.MISSING, "feature directories not found")
        if not files:
            return _status("features", "Feature datasets", SourceState.EMPTY, "directories exist but are empty")
        return _status("features", "Feature datasets", SourceState.OK, f"{len(files)} dataset file(s)")

    def feature_files(self) -> list[Path]:
        files: list[Path] = []
        for root in (self.settings.features_dir, self.settings.processed_dir):
            if root.is_dir():
                files.extend(
                    p
                    for p in sorted(root.iterdir())
                    if p.is_file() and p.suffix in {".jsonl", ".parquet", ".csv"}
                )
        return files

    def artifact_dirs_found(self) -> list[Path]:
        found: list[Path] = []
        seen: set[str] = set()
        for root in self.settings.artifact_dirs:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not child.is_dir():
                    continue
                if not any((child / name).is_file() for name in COMMON_ARTIFACT_FILES):
                    continue
                key = str(child.resolve())
                if key not in seen:
                    seen.add(key)
                    found.append(child.resolve())
        return found

    # ------------------------------------------------------------------
    def list_runs(self) -> Result[list[TrainingRun]]:
        models_result = self.registry.list_models()
        if models_result.data is None:
            return Result(None, models_result.status)
        artifact_dirs = self.artifact_dirs_found()
        used: set[str] = set()
        runs: list[TrainingRun] = []
        for model in models_result.data:
            path = Path(model.artifact_resolved) if model.artifact_resolved else None
            if path:
                used.add(str(path))
            runs.append(self._from_model(model, path))
        for path in artifact_dirs:
            if str(path) in used:
                continue
            runs.append(self._from_artifact(path))
        runs.sort(key=lambda r: (r.registered_at or "", r.model_id or 0), reverse=True)
        state = SourceState.OK if runs else SourceState.EMPTY
        return Result(
            runs,
            _status("training", "Training runs", state, f"{len(runs)} inferred run(s)", provenance="inferred"),
        )

    def get_run(self, key: str) -> Result[TrainingRun]:
        result = self.list_runs()
        if result.data is None:
            return Result(None, result.status)
        for run in result.data:
            if run.key == key:
                return Result(run, _status("training", "Training run", SourceState.OK, run.model_version, provenance=run.source_path))
        return Result(None, _status("training", "Training run", SourceState.MISSING, f"no run with key {key}"))

    def _from_model(self, model, path: Path | None) -> TrainingRun:
        files = self.registry.artifact_files(path)
        manifest = self._manifest(path)
        lineage = self._json_file(path / "lineage.json") if path else None
        metrics = self._json_file(path / "metrics.json") if path else None
        if metrics is None and path:
            metrics = self._json_file(path / "report.json")
        split = self._find_split(model.model_version, path)
        warnings: list[str] = list(model.warnings)
        if path and (path / "lineage.json").is_file():
            source = "db-orchestrator"
        elif path and ((path / "report.json").is_file() or (path / "report.md").is_file()):
            source = "jsonl-trainer"
        elif path:
            source = "artifact-only"
        else:
            source = "registry-only"
        if path and not lineage:
            warnings.append("no lineage.json (path B or older run)")
        if lineage and str(lineage.get("code_commit", "")).lower() in {"", "unknown"}:
            warnings.append("lineage code_commit is 'unknown' (ISS-045)")
        if path and not split:
            warnings.append("no split manifest found (ISS-038)")
        if path and metrics is not None and model.metrics is not None:
            warnings.append("metrics are duplicated in the registry and the artifact (ISS-087)")
        if manifest.get("feature_version") and model.feature_version and manifest["feature_version"] != model.feature_version:
            warnings.append("feature_version differs between registry and manifest")
        if manifest.get("model_kind") and model.model_kind and manifest["model_kind"] != model.model_kind:
            warnings.append(
                f"manifest kind '{manifest['model_kind']}' differs from stored kind '{model.model_kind}' (ISS-047)"
            )
        return TrainingRun(
            key=f"registry:{model.id}",
            model_id=model.id,
            model_version=model.model_version,
            model_kind_stored=model.model_kind,
            model_kind_manifest=manifest.get("model_kind"),
            feature_version=model.feature_version or manifest.get("feature_version"),
            registered_at=model.registered_at,
            artifact_path=model.artifact_path,
            artifact_resolved=model.artifact_resolved,
            artifact_exists=model.artifact_exists,
            lineage=lineage,
            metrics=metrics if metrics is not None else model.metrics,
            split=split,
            source_path=source,
            warnings=tuple(dict.fromkeys(warnings)),
            files=files,
        )

    def _from_artifact(self, path: Path) -> TrainingRun:
        manifest = self._manifest(path)
        lineage = self._json_file(path / "lineage.json")
        metrics = self._json_file(path / "metrics.json") or self._json_file(path / "report.json")
        version = str(manifest.get("model_version") or lineage.get("version") if lineage else path.name)
        split = self._find_split(version, path)
        source = "db-orchestrator" if (path / "lineage.json").is_file() else (
            "jsonl-trainer" if (path / "report.json").is_file() else "artifact-only"
        )
        warnings = ["artifact has no registry row (orphan)"]
        if not split:
            warnings.append("no split manifest found (ISS-038)")
        return TrainingRun(
            key=f"artifact:{path.name}",
            model_version=version,
            model_kind_manifest=manifest.get("model_kind"),
            feature_version=manifest.get("feature_version"),
            registered_at=lineage.get("created_at") if lineage else None,
            artifact_path=str(path),
            artifact_resolved=str(path),
            artifact_exists=True,
            lineage=lineage,
            metrics=metrics,
            split=split,
            source_path=source,
            warnings=tuple(warnings),
            files=self.registry.artifact_files(path),
        )

    # ------------------------------------------------------------------
    def manifest(self, path: Path | None) -> dict[str, str]:
        return self._manifest(path)

    def split_manifests(self) -> Result[list[SplitInfo]]:
        if not self.settings.runs_dir.is_dir():
            return Result([], _status("splits", "Split manifests", SourceState.MISSING, "runs directory not found"))
        candidates: list[Path] = []
        try:
            candidates = sorted(self.settings.runs_dir.glob("split-*.json"))
        except OSError:
            candidates = []
        items = [self._load_split(p) for p in candidates]
        return Result(
            items,
            _status(
                "splits",
                "Split manifests",
                SourceState.OK if items else SourceState.EMPTY,
                f"{len(items)} manifest(s)",
            ),
        )

    def _find_split(self, version: str, artifact: Path | None) -> SplitInfo | None:
        candidates: list[Path] = []
        if artifact:
            candidates.append(artifact / "split.json")
        if version:
            candidates.append(self.settings.runs_dir / f"split-{version}.json")
        for path in candidates:
            if path.is_file():
                return self._load_split(path)
        return None

    def _load_split(self, path: Path) -> SplitInfo:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            train = data.get("train_hashes") or []
            test = data.get("test_hashes") or []
            return SplitInfo(
                name=path.name,
                path=str(path),
                version=data.get("version"),
                seed=data.get("seed"),
                mode=data.get("mode"),
                train_count=len(train) if isinstance(train, list) else 0,
                test_count=len(test) if isinstance(test, list) else 0,
                mtime=iso_mtime(path),
            )
        except (OSError, ValueError, TypeError) as exc:
            return SplitInfo(
                name=path.name,
                path=str(path),
                version=None,
                seed=None,
                mode=None,
                train_count=0,
                test_count=0,
                mtime=iso_mtime(path),
                error=str(exc),
            )

    # ------------------------------------------------------------------
    @staticmethod
    def _manifest(path: Path | None) -> dict[str, str]:
        if path is None:
            return {}
        try:
            lines = (path / "manifest.txt").read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        out: dict[str, str] = {}
        for line in lines:
            if "=" in line:
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip()
        return out

    @staticmethod
    def _json_file(path: Path) -> dict[str, Any] | None:
        try:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"value": data}
        except (OSError, ValueError, TypeError):
            return None
