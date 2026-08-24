"""Static lint: no module other than `chopcast.processing.cleaner` may
contain the string `/TB` in executable code (case-insensitive). This
prevents any code path outside the controlled cleaner from stripping
or reading `/TB` without going through the linted path.

We use Python's `tokenize` module to drop comments and string
literals before scanning, so descriptive references like "strips
///T from text" are allowed — only actual runtime usage of the
string is forbidden.

We allowlist `chopcast/config.py` for the config-default value and
`chopcast/errors.py` for error messages; both reference `/TB` as a
literal string but do not act on it.

See `docs/STANDARDS.md` §3 and `docs/MODULE_DESIGN.md` §5.1.
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "chopcast"
ALLOWED = {
    (PACKAGE / "processing" / "cleaner.py").resolve(),
    (PACKAGE / "config.py").resolve(),  # CleanerConfig.strip_fields default
    (PACKAGE / "errors.py").resolve(),  # LeakageError message
}


def _strip_strings_and_comments(source: str) -> str:
    """Return the source with all string literals and comments replaced
    by spaces, leaving only executable code.

    Uses Python's tokenizer so we correctly handle multi-line
    docstrings, escapes, f-strings, and triple-quoted strings.
    """
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    out = list(source)
    for tok in tokens:
        if tok.type in (
            tokenize.STRING,
            tokenize.COMMENT,
        ):
            start, end = tok.start, tok.end
            line_start = sum(source[: tok.start[1] + 1].count("\n") for _ in [0])  # noqa: F841
            # Replace the token's span with spaces, preserving newlines
            # so the regex sees the same line structure.
            flat_start = tok.start[1] if False else _pos_to_index(source, tok.start)
            flat_end = _pos_to_index(source, tok.end)
            replaced = re.sub(r"\S", " ", source[flat_start:flat_end])
            out[flat_start:flat_end] = replaced
    return "".join(out)


def _pos_to_index(source: str, pos: tuple[int, int]) -> int:
    line, col = pos
    lines = source.splitlines(keepends=True)
    return sum(len(l) for l in lines[:line]) + col


def _all_python_files() -> list[Path]:
    return [p for p in PACKAGE.rglob("*.py") if p.is_file()]


def _code_contains_tb(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        code = _strip_strings_and_comments(text)
    except (tokenize.TokenizeError, IndentationError):
        # If the file isn't valid Python we still scan the raw source.
        code = text
    return bool(re.search(r"/TB\b", code, re.IGNORECASE))


@pytest.mark.parametrize("path", _all_python_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_tb_outside_cleaner(path: Path) -> None:
    """`/TB` may only appear in code inside the cleaner (or in the
    string-literal config-default and error message allowlist)."""
    if path.resolve() in ALLOWED:
        pytest.skip("this file is on the allowlist")
    assert not _code_contains_tb(path), (
        f"{path.relative_to(ROOT)} uses '/TB' in code — only "
        "chopcast/processing/cleaner.py is permitted to. Route the "
        "stripping through clean_text() instead."
    )


def test_cleaner_does_contain_tb() -> None:
    """Belt-and-braces: make sure we don't accidentally delete the
    canonical owner. If this fails, update ALLOWED above."""
    owner = PACKAGE / "processing" / "cleaner.py"
    assert owner.exists()
    text = owner.read_text(encoding="utf-8", errors="replace")
    code = _strip_strings_and_comments(text)
    assert re.search(r"/TB\b", code, re.IGNORECASE)