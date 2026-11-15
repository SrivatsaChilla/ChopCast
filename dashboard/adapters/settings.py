"""Environment-driven configuration for the adapter layer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = Path(__file__).resolve().parents[1]


def _split_paths(raw: str, base: Path) -> tuple[Path, ...]:
    parts = [p.strip() for p in raw.split(os.pathsep) if p.strip()]
    return tuple((base / p).resolve() if not Path(p).is_absolute() else Path(p) for p in parts)


def _env_path(name: str, default: Path, base: Path) -> Path:
    raw = os.environ.get(name)
    if not raw:
        return default.resolve()
    p = Path(raw).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()


def _env_int(name: str, default: int, minimum: int = 0, maximum: int = 10_000_000) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AdapterSettings:
    root: Path
    raw_db: Path
    registry_db: Path
    artifact_dirs: tuple[Path, ...]
    runs_dir: Path
    features_dir: Path
    processed_dir: Path
    logs_dirs: tuple[Path, ...]
    map_dirs: tuple[Path, ...]
    config_dir: Path
    docs_dir: Path
    profile: str | None
    timezone: str
    page_size: int
    max_page_size: int
    map_max_points: int
    log_tail_bytes: int
    cache_seconds: int
    tile_url: str
    allow_downloads: bool

    @classmethod
    def from_env(cls, root: Path | None = None) -> "AdapterSettings":
        base = (root or _env_path("CHOPCAST_DASHBOARD_ROOT", REPO_ROOT, REPO_ROOT)).resolve()
        default_artifacts = f"{base / 'models' / 'registry'}{os.pathsep}{base / 'models' / 'artifacts'}"
        default_logs = f"{base / 'logs'}{os.pathsep}{base}"
        default_maps = os.pathsep.join(
            str(p)
            for p in (
                base / "runs" / "maps",
                base / "data" / "maps",
                base / "maps",
                base,
            )
        )
        page_size = _env_int("CHOPCAST_DASHBOARD_PAGE_SIZE", 50, 5, 200)
        max_page_size = _env_int("CHOPCAST_DASHBOARD_MAX_PAGE_SIZE", 200, page_size, 1000)
        return cls(
            root=base,
            raw_db=_env_path("CHOPCAST_DASHBOARD_RAW_DB", base / "data" / "raw" / "pireps.db", base),
            registry_db=_env_path(
                "CHOPCAST_DASHBOARD_REGISTRY_DB",
                base / "models" / "registry" / "registry.db",
                base,
            ),
            artifact_dirs=_split_paths(
                os.environ.get("CHOPCAST_DASHBOARD_ARTIFACT_DIRS", default_artifacts), base
            ),
            runs_dir=_env_path("CHOPCAST_DASHBOARD_RUNS_DIR", base / "runs", base),
            features_dir=_env_path(
                "CHOPCAST_DASHBOARD_FEATURES_DIR", base / "data" / "features", base
            ),
            processed_dir=_env_path(
                "CHOPCAST_DASHBOARD_PROCESSED_DIR", base / "data" / "processed", base
            ),
            logs_dirs=_split_paths(os.environ.get("CHOPCAST_DASHBOARD_LOGS_DIRS", default_logs), base),
            map_dirs=_split_paths(os.environ.get("CHOPCAST_DASHBOARD_MAP_DIRS", default_maps), base),
            config_dir=_env_path("CHOPCAST_DASHBOARD_CONFIG_DIR", base / "configs", base),
            docs_dir=_env_path("CHOPCAST_DASHBOARD_DOCS_DIR", base / "docs", base),
            profile=os.environ.get("CHOPCAST_DASHBOARD_PROFILE") or None,
            timezone=os.environ.get("CHOPCAST_DASHBOARD_TIMEZONE", "UTC"),
            page_size=page_size,
            max_page_size=max_page_size,
            map_max_points=_env_int("CHOPCAST_DASHBOARD_MAP_MAX_POINTS", 2000, 50, 50_000),
            log_tail_bytes=_env_int(
                "CHOPCAST_DASHBOARD_LOG_TAIL_BYTES", 262_144, 4096, 10_000_000
            ),
            cache_seconds=_env_int("CHOPCAST_DASHBOARD_CACHE_SECONDS", 10, 0, 3600),
            tile_url=os.environ.get("CHOPCAST_DASHBOARD_TILE_URL", "").strip(),
            allow_downloads=_env_bool("CHOPCAST_DASHBOARD_ALLOW_DOWNLOADS", True),
        )

    def is_within_root(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.root)
        except (OSError, ValueError):
            return False

    def display_path(self, path: str | Path | None) -> str:
        if path is None:
            return ""
        p = Path(path)
        try:
            return str(p.resolve().relative_to(self.root)) if p.is_absolute() else str(p)
        except (OSError, ValueError):
            return str(p)
