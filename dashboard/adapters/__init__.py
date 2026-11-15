"""The only layer that reads pipeline data.

Nothing outside ``dashboard/adapters`` may open a pipeline database, read a
pipeline artifact, or parse a pipeline log. Services are plain Python so they
can be tested without Django and swapped if the open architecture decisions
in ``docs/ISSUES.md`` change.
"""

from __future__ import annotations

from functools import lru_cache

from adapters.evaluation import EvaluationService
from adapters.labels import LabelService
from adapters.logs import LogService
from adapters.maps import MapService
from adapters.markdown import MarkdownService
from adapters.registry import RegistryService
from adapters.reports import ReportService
from adapters.settings import AdapterSettings
from adapters.system import SystemService
from adapters.training import TrainingService
from adapters.types import Capabilities, SourceStatus


class Adapter:
    """Facade over every read-only pipeline source."""

    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.reports = ReportService(settings)
        self.labels = LabelService(settings)
        self.training = TrainingService(settings)
        self.evaluation = EvaluationService(settings)
        self.registry = RegistryService(settings)
        self.maps = MapService(settings)
        self.logs = LogService(settings)
        self.system = SystemService(settings)
        self.issues = MarkdownService(settings)
        self._cache: dict[str, object] = {}

    def cached(self, key: str, factory):
        if key not in self._cache:
            self._cache[key] = factory()
        return self._cache[key]

    def capabilities(self) -> Capabilities:
        return self.cached("capabilities", self._build_capabilities)

    def _build_capabilities(self) -> Capabilities:
        raw = self.reports.profile()
        reg = self.registry.profile()
        return Capabilities(raw=raw, registry=reg)

    def health(self) -> list[SourceStatus]:
        return self.cached("health", self._build_health)

    def _build_health(self) -> list[SourceStatus]:
        return [
            self.reports.status(),
            self.registry.status(),
            self.training.artifact_status(),
            self.training.feature_status(),
            self.logs.status(),
            self.maps.file_status(),
        ]


@lru_cache(maxsize=1)
def _cached_settings() -> AdapterSettings:
    return AdapterSettings.from_env()


def get_adapter() -> Adapter:
    """Build a fresh adapter for one request (services hold no connections)."""

    return Adapter(_cached_settings())


def clear_settings_cache() -> None:
    """Test hook: forget the cached environment-derived settings."""

    _cached_settings.cache_clear()
