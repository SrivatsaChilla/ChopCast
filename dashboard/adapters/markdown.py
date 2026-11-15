"""Safe Markdown rendering for ``docs/ISSUES.md``.

Python-Markdown is used for syntax, then the HTML is re-parsed with a strict
tag/attribute allowlist. Raw HTML in the source is escaped, not executed, and
links are restricted to http(s), mailto, and relative targets.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import markdown

from adapters.settings import AdapterSettings
from adapters.sqlite_ro import iso_mtime
from adapters.types import IssueCounts, IssuesDocument, Result, SourceState, SourceStatus

ALLOWED_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "hr",
    "a",
    "em",
    "strong",
    "b",
    "i",
    "code",
    "pre",
    "blockquote",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "del",
    "sup",
    "sub",
    "span",
    "div",
}
VOID_TAGS = {"br", "hr"}
ALLOWED_ATTRS = {"href", "title", "id", "class", "colspan", "rowspan", "scope", "align"}
SAFE_ID = re.compile(r"[^A-Za-z0-9_-]+")
SAFE_CLASS = re.compile(r"[^A-Za-z0-9 _-]+")
HEADING = re.compile(r"^(#{2,3})\s+(.*\S)\s*$")
ISS_ID = re.compile(r"^(ISS-\d{3})", re.IGNORECASE)
EXPLICIT_ID = re.compile(r"\s*\{#([A-Za-z0-9_-]+)\}\s*$")
COUNTS = re.compile(r"\*\*Counts:\*\*\s*(.+)")
COUNT_PAIR = re.compile(r"([A-Za-z]+)\s+(\d+)")


def _status(
    key: str,
    label: str,
    state: SourceState,
    detail: str = "",
    path: str = "",
    mtime: str | None = None,
    provenance: str | None = None,
) -> SourceStatus:
    return SourceStatus(
        key=key, label=label, state=state, detail=detail, path=path, mtime=mtime, provenance=provenance
    )


def slugify(value: str) -> str:
    text = re.sub(r"[`*_]", "", value).strip().lower()
    text = SAFE_ID.sub("-", text).strip("-")
    return text or "section"


def extract_counts(text: str) -> IssueCounts:
    match = COUNTS.search(text)
    if not match:
        return IssueCounts()
    line = match.group(1)
    by_severity: dict[str, int] = {}
    total = 0
    for name, number in COUNT_PAIR.findall(line):
        key = name.capitalize()
        value = int(number)
        if key.lower() == "total":
            total = value
        else:
            by_severity[key] = value
    if not total:
        total = sum(by_severity.values())
    return IssueCounts(total=total, by_severity=by_severity)


class _Sanitizer(HTMLParser):
    """Allowlist-based HTML sanitiser with link-scheme enforcement."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._link_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            self.parts.append(html.escape(f"<{tag}>", quote=False))
            return
        clean = self._attrs(tag, attrs)
        self.parts.append(f"<{tag}{clean}>")
        if tag == "a":
            self._link_depth += 1

    def handle_startendtag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            self.parts.append(html.escape(f"<{tag}/>", quote=False))
            return
        clean = self._attrs(tag, attrs)
        self.parts.append(f"<{tag}{clean}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            self.parts.append(html.escape(f"</{tag}>", quote=False))
            return
        self.parts.append(f"</{tag}>")
        if tag == "a" and self._link_depth:
            self._link_depth -= 1

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.parts.append(html.escape(f"<!--{data}-->", quote=False))

    def handle_decl(self, decl: str) -> None:
        self.parts.append(html.escape(f"<!{decl}>", quote=False))

    def handle_pi(self, data: str) -> None:
        self.parts.append(html.escape(f"<?{data}>", quote=False))

    def unknown_decl(self, data: str) -> None:
        self.parts.append(html.escape(f"<![{data}]>", quote=False))

    def _attrs(self, tag: str, attrs) -> str:
        out: list[str] = []
        for raw_name, value in attrs:
            name = (raw_name or "").lower()
            if name not in ALLOWED_ATTRS or value is None:
                continue
            if name == "href":
                if not _safe_href(value):
                    continue
                out.append(f'href="{html.escape(value, quote=True)}"')
                if _is_external(value):
                    out.append('rel="noopener noreferrer"')
            elif name == "id":
                clean = SAFE_ID.sub("-", value)
                if clean:
                    out.append(f'id="{html.escape(clean, quote=True)}"')
            elif name == "class":
                clean = SAFE_CLASS.sub("", value)
                if clean:
                    out.append(f'class="{html.escape(clean, quote=True)}"')
            elif name in {"colspan", "rowspan"}:
                if value.isdigit():
                    out.append(f'{name}="{value}"')
            elif name == "scope" and value.lower() in {"col", "row"}:
                out.append(f'scope="{value.lower()}"')
            elif name == "align" and value.lower() in {"left", "right", "center"}:
                out.append(f'align="{value.lower()}"')
            else:
                out.append(f'{name}="{html.escape(value, quote=True)}"')
        return (" " + " ".join(out)) if out else ""


def _safe_href(value: str) -> bool:
    candidate = value.strip()
    if not candidate or candidate.startswith("#"):
        return True
    if candidate.startswith("//"):
        return False
    scheme = urlsplit(candidate).scheme.lower()
    if not scheme:
        return True
    return scheme in {"http", "https", "mailto"}


def _is_external(value: str) -> bool:
    scheme = urlsplit(value.strip()).scheme.lower()
    return scheme in {"http", "https"}


def sanitize(fragment: str) -> str:
    parser = _Sanitizer()
    parser.feed(fragment)
    parser.close()
    return "".join(parser.parts)


class _MarkdownRenderer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.toc: list[tuple[str, str, int]] = []
        self._used: set[str] = set()

    def render(self) -> tuple[str, tuple[tuple[str, str, int], ...]]:
        prepared = self._prepare()
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "attr_list", "sane_lists"],
            output_format="html5",
        )
        rendered = md.convert(prepared)
        return sanitize(rendered), tuple(self.toc)

    def _prepare(self) -> str:
        out: list[str] = []
        in_fence = False
        for line in self.text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                out.append(line)
                continue
            match = None if in_fence else HEADING.match(line)
            if not match:
                out.append(line)
                continue
            level = len(match.group(1))
            label = EXPLICIT_ID.sub("", match.group(2)).strip()
            explicit = EXPLICIT_ID.search(match.group(2))
            if explicit:
                anchor = explicit.group(1)
            else:
                iss = ISS_ID.match(label)
                anchor = iss.group(1).lower() if iss else slugify(label)
            anchor = self._unique(anchor)
            self.toc.append((anchor, re.sub(r"[`*_]", "", label), level))
            out.append(f"{match.group(1)} {label} {{#{anchor}}}")
        return "\n".join(out)

    def _unique(self, anchor: str) -> str:
        candidate = anchor
        index = 2
        while candidate in self._used:
            candidate = f"{anchor}-{index}"
            index += 1
        self._used.add(candidate)
        return candidate


class MarkdownService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings

    @property
    def path(self) -> Path:
        return self.settings.docs_dir / "ISSUES.md"

    def status(self) -> SourceStatus:
        if not self.path.is_file():
            return _status(
                "issues",
                "Issue register",
                SourceState.MISSING,
                "ISSUES.md not found",
                str(self.path),
            )
        return _status(
            "issues",
            "Issue register",
            SourceState.OK,
            str(self.path),
            str(self.path),
            iso_mtime(self.path),
        )

    def render(self) -> Result[IssuesDocument]:
        status = self.status()
        if not self.path.is_file():
            return Result(None, status)
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return Result(
                None,
                _status(
                    "issues",
                    "Issue register",
                    SourceState.ERROR,
                    str(exc),
                    str(self.path),
                ),
            )
        renderer = _MarkdownRenderer(text)
        html_text, toc = renderer.render()
        return Result(
            IssuesDocument(
                html=html_text,
                toc=toc,
                counts=extract_counts(text),
                source_path=str(self.path),
                mtime=iso_mtime(self.path),
            ),
            _status(
                "issues",
                "Issue register",
                SourceState.OK if text.strip() else SourceState.EMPTY,
                f"{len(text.splitlines()):,} lines",
                str(self.path),
                iso_mtime(self.path),
                provenance="docs/ISSUES.md",
            ),
        )

    def raw_text(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
