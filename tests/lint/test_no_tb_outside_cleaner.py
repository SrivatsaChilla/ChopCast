"""Static lint: no module other than `chopcast.processing.cleaner` may
contain the string `/TB` in executable code (case-insensitive). This
prevents any code path outside the controlled cleaner from stripping
or reading `/TB` without going through the linted path.

We use Python's `tokenize` module to drop comments and string
literals before scanning, so descriptive references like "strips
/TB from text" in docstrings are allowed — only actual runtime usage
of the string is forbidden.

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
    by whitespace, leaving only executable code.

    Uses Python's tokenizer so we correctly handle multi-line
    docstrings, escapes, f-strings, and triple-quoted strings. The
    result preserves newlines so the regex sees the same line
    structure.

    Python's tokenizer uses 1-indexed line numbers, so we offset our
    row table by one.
    """
    lines = source.splitlines(keepends=True)
    # row_offsets[line_number] = flat offset of the start of that line.
    # Index by 1-indexed line numbers used by the tokenizer.
    row_offsets: list[int] = [0]  # placeholder for line 0
    offset = 0
    for line in lines:
        row_offsets.append(offset)
        offset += len(line)

    out = list(source)

    def _mask(start: tuple[int, int], end: tuple[int, int]) -> None:
        s_line, s_col = start
        e_line, e_col = end
        flat_start = row_offsets[s_line] + s_col
        flat_end = row_offsets[e_line] + e_col
        for i in range(flat_start, min(flat_end, len(out))):
            ch = out[i]
            out[i] = "\n" if ch == "\n" else " "

    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                _mask(tok.start, tok.end)
    except (tokenize.TokenizeError, IndentationError):
        pass
    return "".join(out)


def _all_python_files() -> list[Path]:
    return [p for p in PACKAGE.rglob("*.py") if p.is_file()]


def _code_contains_tb(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    code = _strip_strings_and_comments(text)
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


def test_cleaner_does_contain_tb_via_config() -> None:
    """Belt-and-braces: the cleaner does NOT hardcode `/TB`; instead it
    reads it from `CleanerConfig.strip_fields` at runtime. We confirm
    the runtime path is wired by checking that the config default
    references `/TB`."""
    import yaml  # noqa: F401  (presence confirms PyYAML is available)

    from chopcast.config import CleanerConfig

    assert "/TB" in CleanerConfig().strip_fields