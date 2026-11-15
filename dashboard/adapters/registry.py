"""Read-only model registry access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.schema_probe import probe_registry
from adapters.settings import AdapterSettings
from adapters.sqlite_ro import ReadOnlyDatabase, SourceError, iso_mtime
from adapters.types import (
    ArtifactFile,
    ModelRecord,
    PromotionRecord,
    Result,
    SourceState,
    SourceStatus,
)

COMMON_ARTIFACT_FILES = ("pipeline.joblib", "manifest.txt", "metrics.json", "lineage.json", "report.json", "report.md", "split.json")


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


def _safe_json(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if raw is None:
        return None, None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        return None, str(exc)
    return (value if isinstance(value, dict) else {"value": value}), None


class RegistryService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.db = ReadOnlyDatabase(settings.registry_db)
        self._profile = None

    def profile(self):
        if self._profile is None:
            self._profile = probe_registry(self.db)
        return self._profile

    def status(self) -> SourceStatus:
        profile = self.profile()
        if not self.db.exists:
            return _status("registry", "Model registry", SourceState.MISSING, "file not found", str(self.settings.registry_db))
        if profile.state == "error":
            return _status("registry", "Model registry", SourceState.ERROR, "; ".join(profile.notes), str(self.settings.registry_db), self.db.mtime)
        if not profile.has_models:
            return _status("registry", "Model registry", SourceState.SCHEMA_MISMATCH, "models table missing", str(self.settings.registry_db), self.db.mtime)
        try:
            count = int(self.db.scalar("SELECT COUNT(*) FROM models", default=0))
        except SourceError as exc:
            return _status("registry", "Model registry", SourceState.ERROR, str(exc), str(self.settings.registry_db), self.db.mtime)
        return _status(
            "registry",
            "Model registry",
            SourceState.OK if count else SourceState.EMPTY,
            f"{count} model(s)" + (" · raw tables present" if profile.stray_raw_tables else ""),
            str(self.settings.registry_db),
            self.db.mtime,
            "registry",
        )

    # ------------------------------------------------------------------
    def list_models(self) -> Result[list[ModelRecord]]:
        profile = self.profile()
        if not self.db.exists or not profile.has_models:
            return Result(None, self.status())
        try:
            rows = self.db.query("SELECT * FROM models ORDER BY id DESC")
            promotions: dict[int, list[str]] = {}
            if profile.has_promotions:
                for prow in self.db.query("SELECT model_id, tag FROM promotions ORDER BY id"):
                    promotions.setdefault(int(prow["model_id"]), []).append(str(prow["tag"]))
        except SourceError as exc:
            return Result(None, _status("registry", "Model registry", SourceState.ERROR, str(exc)))
        models = [self._to_record(r, tuple(promotions.get(int(r["id"]), ()))) for r in rows]
        state = SourceState.OK if models else SourceState.EMPTY
        return Result(
            models,
            _status("registry", "Model registry", state, f"{len(models)} model(s)", str(self.settings.registry_db), self.db.mtime, "registry"),
        )

    def get(self, model_id: int) -> Result[ModelRecord]:
        profile = self.profile()
        if not self.db.exists or not profile.has_models:
            return Result(None, self.status())
        try:
            rows = self.db.query("SELECT * FROM models WHERE id = ?", (int(model_id),))
            tags: tuple[str, ...] = ()
            if profile.has_promotions:
                tags = tuple(
                    str(r["tag"])
                    for r in self.db.query(
                        "SELECT tag FROM promotions WHERE model_id = ? ORDER BY id", (int(model_id),)
                    )
                )
        except SourceError as exc:
            return Result(None, _status("registry", "Model registry", SourceState.ERROR, str(exc)))
        if not rows:
            return Result(None, _status("registry", "Model registry", SourceState.MISSING, f"no model with id={model_id}"))
        return Result(self._to_record(rows[0], tags), _status("registry", "Model registry", SourceState.OK, f"model {model_id}", provenance="registry"))

    def promotions(self) -> Result[list[PromotionRecord]]:
        profile = self.profile()
        if not self.db.exists or not profile.has_promotions:
            return Result([], _status("promotions", "Promotions", SourceState.EMPTY, "promotions table missing"))
        try:
            rows = self.db.query("SELECT id, model_id, promoted_at, tag, replaced_id FROM promotions ORDER BY id DESC")
        except SourceError as exc:
            return Result(None, _status("promotions", "Promotions", SourceState.ERROR, str(exc)))
        items = tuple(
            PromotionRecord(
                id=int(r["id"]),
                model_id=int(r["model_id"]),
                promoted_at=str(r["promoted_at"]),
                tag=str(r["tag"]),
                replaced_id=int(r["replaced_id"]) if r["replaced_id"] is not None else None,
            )
            for r in rows
        )
        return Result(
            list(items),
            _status("promotions", "Promotions", SourceState.OK if items else SourceState.EMPTY, f"{len(items)} promotion(s)"),
        )

    def current(self, tag: str = "production") -> Result[ModelRecord | None]:
        profile = self.profile()
        if not self.db.exists or not profile.has_promotions:
            return Result(None, _status("current", "Current model", SourceState.EMPTY, "no promotions table"))
        try:
            row = self.db.one(
                "SELECT m.* FROM models m JOIN promotions p ON p.model_id = m.id WHERE p.tag = ?",
                (tag,),
            )
        except SourceError as exc:
            return Result(None, _status("current", "Current model", SourceState.ERROR, str(exc)))
        if row is None:
            return Result(None, _status("current", "Current model", SourceState.EMPTY, f"no model promoted to {tag}"))
        return Result(self._to_record(row), _status("current", "Current model", SourceState.OK, tag, provenance="registry"))

    # ------------------------------------------------------------------
    def _to_record(self, row: dict[str, Any], tags: tuple[str, ...] = ()) -> ModelRecord:
        metrics, metrics_error = _safe_json(row.get("metrics_json"))
        raw_path = str(row.get("artifact_path") or "")
        resolved = self.resolve_artifact(raw_path)
        warnings: list[str] = []
        if metrics_error:
            warnings.append(f"metrics_json is not valid JSON: {metrics_error}")
        if raw_path and not Path(raw_path).is_absolute():
            warnings.append("artifact_path is relative and CWD-dependent (ISS-007)")
        if resolved is None:
            warnings.append("artifact directory not found")
        manifest_kind = self._manifest_kind(resolved)
        stored_kind = str(row.get("model_kind") or "")
        if manifest_kind and stored_kind and manifest_kind != stored_kind:
            warnings.append(
                f"stored kind '{stored_kind}' differs from manifest kind '{manifest_kind}' (ISS-047)"
            )
        return ModelRecord(
            id=int(row["id"]),
            model_version=str(row.get("model_version") or ""),
            model_kind=stored_kind,
            feature_version=str(row.get("feature_version") or ""),
            registered_at=str(row.get("registered_at") or ""),
            metrics=metrics,
            artifact_path=raw_path,
            notes=row.get("notes"),
            artifact_exists=resolved is not None,
            artifact_resolved=str(resolved) if resolved else None,
            promotions=tags,
            warnings=tuple(warnings),
        )

    def resolve_artifact(self, raw_path: str) -> Path | None:
        if not raw_path:
            return None
        normalized = raw_path.replace("\\", "/")
        candidate = Path(normalized)
        candidates: list[Path] = []
        if candidate.is_absolute():
            candidates.append(candidate)
        else:
            candidates.append(self.settings.root / candidate)
            candidates.append(self.settings.root / "models" / "registry" / candidate.name)
        for root in self.settings.artifact_dirs:
            candidates.append(root / candidate.name)
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            if path.is_dir():
                return path.resolve()
        return None

    def _manifest_kind(self, path: Path | None) -> str | None:
        if path is None:
            return None
        manifest = path / "manifest.txt"
        try:
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if line.startswith("model_kind="):
                    return line.split("=", 1)[1].strip() or None
        except OSError:
            return None
        return None

    def artifact_files(self, path: Path | None) -> tuple[ArtifactFile, ...]:
        if path is None or not path.is_dir():
            return ()
        files: list[ArtifactFile] = []
        for name in COMMON_ARTIFACT_FILES:
            p = path / name
            if p.is_file():
                try:
                    stat = p.stat()
                    files.append(
                        ArtifactFile(
                            name=name,
                            path=str(p),
                            size=stat.st_size,
                            mtime=iso_mtime(p),
                            exists=True,
                        )
                    )
                except OSError:
                    continue
        return tuple(files)
