"""Repository-relative path resolution.

`Paths` is the only place paths are constructed. Modules that need a path take
a `Paths` object; they never call `Path("data/foo")` themselves.

See docs/MODULE_DESIGN.md §1.4.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    pass

# `Settings` is imported under TYPE_CHECKING; the reference below would
# re-introduce a circular import. Use a string forward reference instead.



class Paths(BaseModel):
    """All filesystem paths the application uses.

    The values come from the resolved `Settings`. The root path is stored as
    a string and converted to `Path` on access so that Pydantic's
    serialisation stays JSON-friendly.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    root: str = Field(description="Root directory. All other paths are relative to this.")
    raw_db: str
    raw_dir: str
    processed_dir: str
    features_dir: str
    models_dir: str
    registry_db: str
    runs_dir: str
    logs_dir: str
    backups_dir: str

    @field_validator("root")
    @classmethod
    def _no_trailing_slash(cls, v: str) -> str:
        if v.endswith("/") and v != "/":
            return v.rstrip("/")
        return v

    # ----- resolved Path accessors ------------------------------------------
    @property
    def root_path(self) -> Path:
        return Path(self.root).resolve()

    @property
    def raw_db_path(self) -> Path:
        return Path(self.raw_db).resolve()

    @property
    def raw_dir_path(self) -> Path:
        return Path(self.raw_dir).resolve()

    @property
    def processed_dir_path(self) -> Path:
        return Path(self.processed_dir).resolve()

    @property
    def features_dir_path(self) -> Path:
        return Path(self.features_dir).resolve()

    @property
    def models_dir_path(self) -> Path:
        return Path(self.models_dir).resolve()

    @property
    def registry_db_path(self) -> Path:
        return Path(self.registry_db).resolve()

    @property
    def runs_dir_path(self) -> Path:
        return Path(self.runs_dir).resolve()

    @property
    def logs_dir_path(self) -> Path:
        return Path(self.logs_dir).resolve()

    @property
    def backups_dir_path(self) -> Path:
        return Path(self.backups_dir).resolve()

    # ----- factory ----------------------------------------------------------
    @classmethod
    def from_settings(cls, settings: "Settings") -> "Paths":  # type: ignore[type-arg]
        """Build a `Paths` from a fully-resolved `Settings`."""
        return cls(
            root=settings.paths.root,
            raw_db=settings.paths.raw_db,
            raw_dir=settings.paths.raw_dir,
            processed_dir=settings.paths.processed_dir,
            features_dir=settings.paths.features_dir,
            models_dir=settings.paths.models_dir,
            registry_db=settings.paths.registry_db,
            runs_dir=settings.paths.runs_dir,
            logs_dir=settings.paths.logs_dir,
            backups_dir=settings.paths.backups_dir,
        )

    def ensure_dirs(self) -> None:
        """Create any missing directories. Idempotent."""
        for d in (
            self.raw_dir_path,
            self.processed_dir_path,
            self.features_dir_path,
            self.models_dir_path,
            self.runs_dir_path,
            self.logs_dir_path,
            self.backups_dir_path,
        ):
            d.mkdir(parents=True, exist_ok=True)


__all__ = ["Paths"]
