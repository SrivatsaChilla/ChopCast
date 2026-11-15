"""Environment, path, configuration, and sanity reporting.

Nothing here imports the ``chopcast`` package. Package versions come from
``importlib.metadata``; configuration is read as YAML and resolved for display
only. The dashboard never writes config.
"""

from __future__ import annotations

import os
import platform
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

from adapters.settings import AdapterSettings
from adapters.sqlite_ro import iso_mtime
from adapters.types import (
    ConfigFileView,
    PackageInfo,
    PathInfo,
    SanityCheck,
    SystemSnapshot,
)

SECRET_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "PASSWD", "API_KEY", "PRIVATE")
ENV_PREFIX = "CHOPCAST_DASHBOARD_"
PACKAGES = (
    ("chopcast", True),
    ("Django", True),
    ("PyYAML", True),
    ("Markdown", True),
    ("pandas", False),
    ("numpy", False),
    ("pydantic", False),
    ("scikit-learn", False),
    ("folium", False),
    ("requests", False),
    ("joblib", False),
)
INTERPOLATION = re.compile(r"\$\{([^}]+)\}")


class SystemService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self._snapshot: SystemSnapshot | None = None

    # ------------------------------------------------------------------
    def snapshot(self) -> SystemSnapshot:
        if self._snapshot is None:
            checks = tuple(self.checks())
            self._snapshot = SystemSnapshot(
                python_version=platform.python_version(),
                python_executable=sys.executable,
                django_version=self._version("Django") or "not installed",
                platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
                cwd=os.getcwd(),
                timezone=self.settings.timezone,
                settings=self._env_settings(),
                paths=tuple(self._paths()),
                configs=tuple(self._configs()),
                packages=tuple(self._packages()),
                checks=checks,
            )
        return self._snapshot

    # ------------------------------------------------------------------
    def _version(self, name: str) -> str | None:
        try:
            return metadata.version(name)
        except (metadata.PackageNotFoundError, ValueError):
            return None

    def _packages(self) -> list[PackageInfo]:
        return [
            PackageInfo(name=name, version=self._version(name), required=required)
            for name, required in PACKAGES
        ]

    def _env_settings(self) -> dict[str, Any]:
        """Adapter configuration with provenance, never the whole environment."""
        out: dict[str, Any] = {}
        known_defaults = {
            "ROOT": self.settings.root,
            "RAW_DB": self.settings.raw_db,
            "REGISTRY_DB": self.settings.registry_db,
            "ARTIFACT_DIRS": self.settings.artifact_dirs,
            "RUNS_DIR": self.settings.runs_dir,
            "FEATURES_DIR": self.settings.features_dir,
            "PROCESSED_DIR": self.settings.processed_dir,
            "LOGS_DIRS": self.settings.logs_dirs,
            "MAP_DIRS": self.settings.map_dirs,
            "CONFIG_DIR": self.settings.config_dir,
            "DOCS_DIR": self.settings.docs_dir,
            "PROFILE": self.settings.profile,
            "TIMEZONE": self.settings.timezone,
            "PAGE_SIZE": self.settings.page_size,
            "MAX_PAGE_SIZE": self.settings.max_page_size,
            "MAP_MAX_POINTS": self.settings.map_max_points,
            "LOG_TAIL_BYTES": self.settings.log_tail_bytes,
            "CACHE_SECONDS": self.settings.cache_seconds,
            "TILE_URL": self.settings.tile_url,
            "ALLOW_DOWNLOADS": self.settings.allow_downloads,
        }
        for suffix, default in known_defaults.items():
            key = ENV_PREFIX + suffix
            source = "env" if key in os.environ else "default"
            value: Any = default
            if source == "env":
                value = os.environ[key]
            if isinstance(value, Path) or (
                isinstance(value, tuple) and value and isinstance(value[0], Path)
            ):
                value = [str(v) for v in value] if isinstance(value, tuple) else str(value)
            if any(marker in suffix for marker in SECRET_MARKERS):
                value = "***redacted***"
            out[key] = {"value": value, "source": source}
        for key in sorted(os.environ):
            if not key.startswith(ENV_PREFIX) or key.removeprefix(ENV_PREFIX) in known_defaults:
                continue
            value = os.environ[key]
            if any(marker in key.upper() for marker in SECRET_MARKERS):
                value = "***redacted***"
            out[key] = {"value": value, "source": "env"}
        return out

    def _paths(self) -> list[PathInfo]:
        entries: list[tuple[str, Path]] = [
            ("raw_db", self.settings.raw_db),
            ("registry_db", self.settings.registry_db),
            ("runs_dir", self.settings.runs_dir),
            ("features_dir", self.settings.features_dir),
            ("processed_dir", self.settings.processed_dir),
            ("config_dir", self.settings.config_dir),
            ("docs_dir", self.settings.docs_dir),
            ("dashboard_var", Path(__file__).resolve().parents[1] / "var"),
        ]
        entries.extend((f"artifact_dir[{i}]", p) for i, p in enumerate(self.settings.artifact_dirs))
        entries.extend((f"logs_dir[{i}]", p) for i, p in enumerate(self.settings.logs_dirs))
        entries.extend((f"map_dir[{i}]", p) for i, p in enumerate(self.settings.map_dirs))
        items: list[PathInfo] = []
        for key, path in entries:
            try:
                exists = path.exists()
                is_dir = path.is_dir()
                size = None
                if exists and path.is_file():
                    size = path.stat().st_size
                items.append(
                    PathInfo(
                        key=key,
                        path=str(path),
                        exists=exists,
                        is_dir=is_dir,
                        size=size,
                        mtime=iso_mtime(path) if exists else None,
                        readable=os.access(path, os.R_OK) if exists else False,
                    )
                )
            except OSError:
                items.append(
                    PathInfo(
                        key=key,
                        path=str(path),
                        exists=False,
                        is_dir=False,
                        size=None,
                        mtime=None,
                        readable=False,
                    )
                )
        return items

    # ------------------------------------------------------------------
    def config_files(self) -> list[ConfigFileView]:
        return self._configs()

    def _configs(self) -> list[ConfigFileView]:
        root = self.settings.config_dir
        if not root.is_dir():
            return []
        views: list[ConfigFileView] = []
        try:
            files = sorted(p for p in root.glob("*.yaml") if p.is_file())
        except OSError:
            return []
        for path in files:
            raw, error = self._read_yaml(path)
            resolved = None
            if path.name == "default.yaml" and raw is not None:
                resolved = self._resolve(raw)
                profile = self.settings.profile
                if profile:
                    overlay_path = root / f"{profile}.yaml"
                    overlay, overlay_error = self._read_yaml(overlay_path)
                    if overlay_error:
                        error = (error + "; " if error else "") + f"overlay: {overlay_error}"
                    if overlay:
                        resolved = self._resolve(_deep_merge(raw, overlay))
                        resolved["__profile_overlay__"] = overlay_path.name
            views.append(
                ConfigFileView(
                    name=path.name,
                    path=str(path),
                    exists=True,
                    raw=raw,
                    resolved=resolved,
                    error=error,
                    mtime=iso_mtime(path),
                )
            )
        return views

    @staticmethod
    def _read_yaml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
        try:
            if not path.is_file():
                return None, None
            if path.stat().st_size > 1_000_000:
                return None, "file is too large to display"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            return None, str(exc)
        if data is None:
            return {}, None
        if not isinstance(data, dict):
            return None, "top-level YAML value is not a mapping"
        return data, None

    def _resolve(self, data: dict[str, Any]) -> dict[str, Any]:
        merged = {"paths": {"root": str(self.settings.root)}}
        merged = _deep_merge(merged, data)
        for _ in range(5):
            changed = False
            for key, value in list(_flatten(merged)):
                if isinstance(value, str) and "${" in value:
                    new = INTERPOLATION.sub(lambda m: self._lookup(merged, m.group(1)), value)
                    if new != value:
                        _set(merged, key, new)
                        changed = True
            if not changed:
                break
        return merged

    @staticmethod
    def _lookup(data: dict[str, Any], dotted: str) -> str:
        node: Any = data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return "${" + dotted + "}"
            node = node[part]
        return str(node)

    # ------------------------------------------------------------------
    def checks(self) -> list[SanityCheck]:
        from adapters.registry import RegistryService
        from adapters.reports import ReportService

        reports = ReportService(self.settings)
        registry = RegistryService(self.settings)
        checks: list[SanityCheck] = []

        raw_status = reports.status()
        checks.append(
            SanityCheck(
                key="raw_db",
                title="Raw database",
                state=_check_state(raw_status.state.value),
                detail=raw_status.detail or raw_status.path,
                issues=("ISS-002", "ISS-011") if raw_status.provenance == "legacy" else (),
            )
        )
        profile = reports.profile()
        checks.append(
            SanityCheck(
                key="schema",
                title="Schema profile",
                state="ok" if profile.state in {"legacy", "target"} else "warning",
                detail=f"{profile.state} · migrations {profile.schema_migrations or 'none'} · "
                f"trainable predicate {profile.trainable_predicate}",
                issues=tuple(
                    i
                    for i in (
                        "ISS-002" if profile.state == "legacy" else "",
                        "ISS-010" if not profile.has_report_type_in_trainable else "",
                        "ISS-012" if "trainable" in profile.views else "",
                    )
                    if i
                ),
            )
        )
        reg_status = registry.status()
        checks.append(
            SanityCheck(
                key="registry",
                title="Model registry",
                state=_check_state(reg_status.state.value),
                detail=reg_status.detail or reg_status.path,
                issues=("ISS-005",) if registry.profile().stray_raw_tables else (),
            )
        )
        current = registry.current("production")
        checks.append(
            SanityCheck(
                key="production",
                title="Production model",
                state="warning" if current.data is None else "ok",
                detail=(
                    "No model is promoted to production"
                    if current.data is None
                    else f"{current.data.model_version} (id {current.data.id})"
                ),
                issues=("ISS-049",) if current.data is None else (),
            )
        )
        models = registry.list_models()
        relative = [m.model_version for m in (models.data or []) if m.artifact_path and not Path(m.artifact_path).is_absolute()]
        missing = [m.model_version for m in (models.data or []) if not m.artifact_exists]
        checks.append(
            SanityCheck(
                key="artifacts",
                title="Model artifacts",
                state="warning" if relative or missing else "ok",
                detail=(
                    f"{len(models.data or [])} model(s); "
                    f"relative paths: {', '.join(relative) or 'none'}; "
                    f"missing: {', '.join(missing) or 'none'}"
                ),
                issues=tuple(i for i in (
                    "ISS-007" if relative else "",
                ) if i),
            )
        )
        feature_files = [
            p for p in self.settings.features_dir.glob("*") if p.is_file()
        ] if self.settings.features_dir.is_dir() else []
        checks.append(
            SanityCheck(
                key="features",
                title="Feature datasets",
                state="ok" if feature_files else "info",
                detail=f"{len(feature_files)} file(s) in {self.settings.features_dir}",
                issues=("ISS-038",) if not feature_files else (),
            )
        )
        log_dirs = [p for p in self.settings.logs_dirs if p.is_dir()]
        checks.append(
            SanityCheck(
                key="logs",
                title="Log destinations",
                state="warning" if len(log_dirs) > 1 else "ok",
                detail="; ".join(str(p) for p in log_dirs) or "no log directory exists",
                issues=("ISS-086",) if len(log_dirs) > 1 else (),
            )
        )
        map_dirs = [p for p in self.settings.map_dirs if p.is_dir()]
        checks.append(
            SanityCheck(
                key="maps",
                title="Generated map output",
                state="info" if not map_dirs else "ok",
                detail="no configured map output directory exists" if not map_dirs else "; ".join(str(p) for p in map_dirs),
                issues=("ISS-083", "ISS-084"),
            )
        )
        checks.append(
            SanityCheck(
                key="python",
                title="Python and Django",
                state="ok" if sys.version_info >= (3, 11) else "error",
                detail=f"Python {platform.python_version()}, Django {self._version('Django') or 'not installed'}",
                issues=("ISS-006",) if sys.version_info < (3, 11) else (),
            )
        )
        root_text = str(self.settings.root).lower()
        checks.append(
            SanityCheck(
                key="sync_folder",
                title="Sync-folder root",
                state="warning" if "onedrive" in root_text else "ok",
                detail=str(self.settings.root),
                issues=("ISS-044",) if "onedrive" in root_text else (),
            )
        )
        config_warning = any(
            str(cfg.raw.get("paths", {}).get("root")) == "."
            for cfg in self._configs()
            if cfg.raw and isinstance(cfg.raw.get("paths"), dict)
        )
        checks.append(
            SanityCheck(
                key="cwd",
                title="CWD-dependent configuration",
                state="warning" if config_warning else "ok",
                detail="configs/default.yaml resolves paths.root as '.' (CWD-dependent)"
                if config_warning
                else "no relative config root detected",
                issues=("ISS-037",) if config_warning else (),
            )
        )
        return checks


def _check_state(state: str) -> str:
    if state == "ok":
        return "ok"
    if state == "empty":
        return "info"
    if state in {"missing", "not_configured"}:
        return "error" if state == "missing" else "info"
    return "warning"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _flatten(data: Any, prefix: str = ""):
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _flatten(value, f"{prefix}.{key}" if prefix else str(key))
    else:
        yield prefix, data


def _set(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
