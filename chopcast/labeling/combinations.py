"""Combination handling for turbulence values.

PIREPs frequently combine severities (`LGT-MOD`, `OCNL MOD-CHOP`,
`MOD-SEV`). This module exposes the combinator: pick the higher (or
lower, or first) severity from a set of matched labels.

See `docs/MODULE_DESIGN.md` §4.2.
"""

from __future__ import annotations

from typing import Iterable, Literal

Severity = Literal["None", "Light", "Moderate", "Severe"]

_ORDER: dict[str, int] = {
    "None": 0,
    "Light": 1,
    "Moderate": 2,
    "Severe": 3,
}


def combine(labels: Iterable[str], strategy: Literal["max", "min", "first"]) -> str:
    """Combine multiple matched labels into one.

    `max` picks the highest severity, `min` the lowest, `first` the
    one that appeared first. Empty input returns "None".
    """
    seq = list(labels)
    if not seq:
        return "None"
    if strategy == "first":
        return seq[0]
    if strategy == "max":
        return max(seq, key=lambda l: _ORDER[l])
    if strategy == "min":
        return min(seq, key=lambda l: _ORDER[l])
    raise ValueError(f"unknown combination strategy: {strategy!r}")


__all__ = ["Severity", "combine"]