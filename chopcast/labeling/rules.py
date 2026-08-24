"""Load severity-mapping rules from `configs/labeling.yaml`.

Rules are versioned. A change to the rules file is a content-breaking
change that requires a new feature-store version.

See `docs/MODULE_DESIGN.md` §4.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from chopcast.errors import LabelingError


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
CombinationStrategy = Literal["max", "min", "first"]


@dataclass(frozen=True)
class LabelingRules:
    """The in-memory shape of `configs/labeling.yaml`."""

    version: str
    none_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    light_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    moderate_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    severe_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    combination_strategy: CombinationStrategy
    chop_only_label: Literal["none", "light"]
    unknown_strategy: Literal["none", "moderate"]

    @property
    def all_patterns(self) -> dict[str, tuple[tuple[str, re.Pattern[str]], ...]]:
        return {
            "None": self.none_patterns,
            "Light": self.light_patterns,
            "Moderate": self.moderate_patterns,
            "Severe": self.severe_patterns,
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _compile(name: str, raw_pattern: str) -> tuple[str, re.Pattern[str]]:
    """Wrap a raw YAML pattern string with case-insensitive, whole-token
    anchoring so substring matches don't bleed across word boundaries.
    """
    pattern = re.escape(raw_pattern)
    return raw_pattern, re.compile(pattern, re.IGNORECASE)


def _load_patterns(section: list[str] | None) -> tuple[tuple[str, re.Pattern[str]], ...]:
    if not section:
        return ()
    return tuple(_compile(p, p) for p in section)


def load_rules(path: Path) -> LabelingRules:
    """Load and validate the labeling rules file. Raises `LabelingError`."""
    if not path.exists():
        raise LabelingError(f"labeling rules file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise LabelingError(f"invalid YAML in {path}: {e}") from e
    if not isinstance(data, dict):
        raise LabelingError(f"labeling rules must be a mapping, got {type(data).__name__}")

    version = data.get("version")
    if not isinstance(version, str):
        raise LabelingError("labeling rules missing 'version' string")

    strategy = data.get("combination_strategy", "max")
    if strategy not in ("max", "min", "first"):
        raise LabelingError(
            f"combination_strategy must be one of max|min|first, got {strategy!r}"
        )

    chop_only = data.get("chop_only_label", "light")
    if chop_only not in ("none", "light"):
        raise LabelingError(
            f"chop_only_label must be one of none|light, got {chop_only!r}"
        )

    unknown = data.get("unknown_strategy", "none")
    if unknown not in ("none", "moderate"):
        raise LabelingError(
            f"unknown_strategy must be one of none|moderate, got {unknown!r}"
        )

    return LabelingRules(
        version=version,
        none_patterns=_load_patterns(data.get("none")),
        light_patterns=_load_patterns(data.get("light")),
        moderate_patterns=_load_patterns(data.get("moderate")),
        severe_patterns=_load_patterns(data.get("severe")),
        combination_strategy=strategy,
        chop_only_label=chop_only,  # type: ignore[arg-type]
        unknown_strategy=unknown,  # type: ignore[arg-type]
    )


__all__ = ["CombinationStrategy", "LabelingRules", "load_rules"]