"""Domain exception hierarchy for ChopCast.

Library code raises these. The CLI catches them at the boundary and translates
to user-friendly messages. Tests assert on exception types, not messages.

See docs/MODULE_DESIGN.md §1.3 and docs/STANDARDS.md §7.
"""

from __future__ import annotations

from typing import Any


class ChopcastError(Exception):
    """Base class for all ChopCast exceptions."""


class ConfigError(ChopcastError):
    """Configuration is missing, invalid, or inconsistent."""


class CollectionError(ChopcastError):
    """Base class for data-collection failures."""


class HttpError(CollectionError):
    """An HTTP request failed after retries were exhausted."""

    def __init__(self, message: str, *, status: int, url: str) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class RateLimited(CollectionError):
    """AWC returned 429 and the configured backoff was insufficient."""


class ParseError(ChopcastError):
    """A PIREP string could not be parsed."""

    def __init__(self, message: str, *, raw_text: str, field: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.field = field


class ValidationError(ChopcastError):
    """A row or field failed validation."""

    def __init__(self, message: str, *, field: str, value: Any) -> None:
        super().__init__(message)
        self.field = field
        self.value = value


class LabelingError(ChopcastError):
    """A labeling rule or label mapping failed."""


class FeatureBuildError(ChopcastError):
    """A feature row could not be constructed."""


class ModelNotFound(ChopcastError):
    """A requested model id is not in the registry."""


class LeakageError(ChopcastError):
    """Label leakage was detected (e.g., /TB appeared in a cleaned string)."""


class TrainingError(ChopcastError):
    """Raised when a training run cannot proceed.

    Covers an empty or unreadable dataset, a split that would leave a
    class entirely absent from training, and a model artifact that
    cannot be written.
    """


__all__ = [
    "ChopcastError",
    "ConfigError",
    "CollectionError",
    "FeatureBuildError",
    "HttpError",
    "LabelingError",
    "LeakageError",
    "TrainingError",
    "ModelNotFound",
    "ParseError",
    "RateLimited",
    "ValidationError",
]
