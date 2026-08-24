"""Map a raw `/TB` value to one of four severity classes.

Matching is case-insensitive substring with the longest match winning.
If multiple severities match (e.g. a value that contains both `LGT`
and `MOD`), the configured combination strategy picks the winner.

See `docs/MODULE_DESIGN.md` §4.2.
"""

from __future__ import annotations

from chopcast.logging import get_logger
from chopcast.labeling.combinations import combine
from chopcast.labeling.rules import LabelingRules

log = get_logger(__name__)

Severity = str  # one of "None" | "Light" | "Moderate" | "Severe"


def _matches(value: str, patterns: tuple[tuple[str, object], ...]) -> bool:
    """Return True if any pattern matches the (already-uppercased) value.

    Patterns are precompiled with `re.escape` so substring matching is
    exact, not regex-grammar-aware.
    """
    upper = value.upper()
    for raw, pat in patterns:
        if pat.search(upper):
            return True
    return False


def _matched_severities(
    value: str | None,
    rules: LabelingRules,
) -> list[str]:
    """Return every severity whose pattern matches the value."""
    if value is None:
        return []
    hits: list[str] = []
    for sev, patterns in rules.all_patterns.items():
        if _matches(value, patterns):
            hits.append(sev)
    return hits


def map_to_severity(value: str | None, rules: LabelingRules) -> Severity:
    """Map a raw turbulence value (the `/TB` block) to a severity class.

    - Empty / None -> "None" (with WARNING so we can spot drift).
    - Special case: a "CHOP"-only remark is mapped per
      `rules.chop_only_label`.
    - No match -> `rules.unknown_strategy` ("None" by default).
    - Multiple matches -> `combine(..., rules.combination_strategy)`.
    """
    if value is None or not str(value).strip():
        return "None"

    raw = str(value).strip()
    upper = raw.upper()
    # "CHOP" alone (no severity prefix) goes to chop_only_label.
    if upper.strip() == "CHOP":
        return "Light" if rules.chop_only_label == "light" else "None"

    hits = _matched_severities(raw, rules)
    if not hits:
        log.warning(
            "labeling.unknown_turbulence",
            value=raw,
            strategy=rules.unknown_strategy,
        )
        return "Moderate" if rules.unknown_strategy == "moderate" else "None"

    if len(hits) == 1:
        return hits[0]
    return combine(hits, rules.combination_strategy)


__all__ = ["map_to_severity"]