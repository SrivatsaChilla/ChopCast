"""Text cleaning with structural leakage prevention.

This module is the only place in the codebase that knows how to
remove `/TB` from PIREP strings. The CI static check
(`tests/lint/test_no_tb_outside_cleaner.py`) enforces this rule.

Two leakage defenses are layered:

1. **Structural**: regex-based removal of every configured field tag
   (`/TB`, etc.) and its trailing value, so the cleaned text never
   carries the answer.
2. **Self-check**: every output is re-scanned for the configured
   field tags; if any survive, `LeakageError` is raised.

See `docs/MODULE_DESIGN.md` §5.1 and `docs/STANDARDS.md` §3.
"""

from __future__ import annotations

import re
from typing import Iterable

from chopcast.config import CleanerConfig
from chopcast.errors import LeakageError


# A recognised PIREP field tag is `/XX` where X is an uppercase letter
# or digit. We use this to know where one field ends and the next
# begins when stripping a tagged block.
_FIELD_TAG_RE = re.compile(r"\s*/([A-Z]{2,3})\b")


def _build_strip_patterns(fields: Iterable[str]) -> list[re.Pattern[str]]:
    """Compile one regex per field tag we need to strip.

    The pattern matches the leading tag (`/TB` or any other configured
    field) and greedily consumes everything up to (but not including)
    the next `/XX` field tag. So `/TB MOD CHOP` becomes empty.
    """
    patterns: list[re.Pattern[str]] = []
    for tag in fields:
        # Anchor on the tag, then eat non-/-prefixed text until the
        # next field tag or end of string.
        pat = re.compile(
            rf"(?:^|\s)/{re.escape(tag.lstrip('/'))}\b[^\S\r\n]*(?:(?!\s*/[A-Z]{{2,3}}\b).)*",
            re.IGNORECASE | re.DOTALL,
        )
        patterns.append(pat)
    return patterns


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_text(raw_text: str, config: CleanerConfig) -> str:
    """Strip configured PIREP fields, normalise, and self-check.

    Returns the cleaned text. Raises `LeakageError` if a configured
    field tag survives the strip. The function never silently lets a
    leakage path through.
    """
    if raw_text is None:
        raise ValueError("raw_text must not be None")
    text = raw_text

    # Step 1: drop each configured field block.
    for pat in _build_strip_patterns(config.strip_fields):
        text = pat.sub(" ", text)

    # Step 2: optional lowercase. We default to True because TF-IDF and
    # most transformer tokenisers are case-insensitive, and lowercasing
    # reduces vocabulary size.
    if config.lowercase:
        text = text.lower()

    # Step 3: collapse whitespace.
    if config.collapse_whitespace:
        text = _collapse_ws(text)

    # Step 4: structural self-check. If any leakage tag survived the
    # strip, raise. This is the behavioural layer of defense — it
    # catches bugs in the regex above.
    for tag in config.strip_fields:
        if re.search(rf"/{re.escape(tag.lstrip('/'))}\b", text, re.IGNORECASE):
            raise LeakageError(
                f"cleaned text still contains leakage tag {tag!r}: {text[:80]!r}"
            )

    return text


__all__ = ["clean_text"]