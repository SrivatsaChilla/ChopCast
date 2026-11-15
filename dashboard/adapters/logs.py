"""Bounded, escaped log reading.

Logs are untrusted text and possibly huge. Only the tail of a file is read, and
nothing here writes, rotates, or truncates a log. Two destinations exist today
(ISS-086); the file index shows both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.settings import AdapterSettings
from adapters.sqlite_ro import iso_mtime
from adapters.types import LogEntry, LogFile, Result, SourceState, SourceStatus

HIDDEN_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "static",
}
MAX_LOG_FILES = 300
TIMESTAMP_KEYS = ("timestamp", "ts", "time", "asctime", "@timestamp", "created")
LEVEL_KEYS = ("level", "severity", "lvl", "log.level", "levelname")
EVENT_KEYS = ("event", "msg", "message", "event_name", "name")
LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "WARN": 30, "ERROR": 40, "CRITICAL": 50}


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


def parse_line(line: str, line_no: int) -> LogEntry:
    stripped = line.rstrip("\r\n")
    if not stripped.strip():
        return LogEntry(line_no=line_no, timestamp=None, level="", event="", fields={}, raw="", is_json=False)
    try:
        data = json.loads(stripped)
    except (TypeError, ValueError):
        return _plain(stripped, line_no)
    if not isinstance(data, dict):
        return LogEntry(
            line_no=line_no,
            timestamp=None,
            level="",
            event="",
            fields={"value": data},
            raw=stripped,
            is_json=True,
        )
    timestamp = next((str(data[k]) for k in TIMESTAMP_KEYS if data.get(k) is not None), None)
    level = next((str(data[k]).upper() for k in LEVEL_KEYS if data.get(k) is not None), "")
    event = next((str(data[k]) for k in EVENT_KEYS if data.get(k) is not None), "")
    consumed = set(TIMESTAMP_KEYS) | set(LEVEL_KEYS) | set(EVENT_KEYS)
    fields = {str(k): v for k, v in data.items() if k not in consumed}
    return LogEntry(
        line_no=line_no,
        timestamp=timestamp,
        level=level,
        event=event,
        fields=fields,
        raw=stripped,
        is_json=True,
    )


def _plain(stripped: str, line_no: int) -> LogEntry:
    timestamp = None
    level = ""
    remainder = stripped
    # A conservative look at "2026-10-17 12:00:00,123 INFO message".
    for token in stripped.split(maxsplit=3):
        if not timestamp and len(token) >= 10 and token[4:5] == "-" and token[7:8] == "-":
            timestamp = token
            remainder = stripped.replace(token, "", 1).strip()
            continue
        upper = token.strip("[]:").upper()
        if not level and upper in LEVEL_ORDER:
            level = upper
            remainder = remainder.replace(token, "", 1).strip()
    return LogEntry(
        line_no=line_no,
        timestamp=timestamp,
        level=level,
        event="",
        fields={},
        raw=stripped,
        is_json=False,
    )


class LogService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------
    def status(self) -> SourceStatus:
        result = self.files()
        if result.status.state is SourceState.OK:
            return _status(
                "logs",
                "Logs",
                SourceState.OK,
                f"{len(result.data or [])} log file(s)",
                provenance="filesystem",
            )
        return result.status

    def files(self) -> Result[list[LogFile]]:
        if not any(root.is_dir() for root in self.settings.logs_dirs):
            return Result(
                [],
                _status("logs", "Logs", SourceState.MISSING, "no configured log directory exists"),
            )
        found: dict[str, LogFile] = {}
        for root in self.settings.logs_dirs:
            if not root.is_dir():
                continue
            try:
                is_repo_root = root.resolve() == self.settings.root.resolve()
                candidates = self._root_logs(root) if is_repo_root else self._walk_logs(root)
                for path in candidates:
                    try:
                        resolved = path.resolve()
                    except OSError:
                        continue
                    if not resolved.is_file():
                        continue
                    if resolved.suffix.lower() not in {".log", ".jsonl", ".txt"} and ".log." not in resolved.name:
                        continue
                    key = str(resolved)
                    if key in found:
                        continue
                    try:
                        stat = resolved.stat()
                        size = stat.st_size
                    except OSError:
                        size = 0
                    found[key] = LogFile(
                        name=resolved.name,
                        path=key,
                        size=size,
                        mtime=iso_mtime(resolved),
                        root=str(root),
                    )
                    if len(found) >= MAX_LOG_FILES:
                        break
            except OSError:
                continue
            if len(found) >= MAX_LOG_FILES:
                break
        items = sorted(found.values(), key=lambda f: (f.mtime or "", f.name), reverse=True)
        return Result(
            items,
            _status(
                "logs",
                "Logs",
                SourceState.OK if items else SourceState.EMPTY,
                f"{len(items)} log file(s)" if items else "log directories exist but contain no log files",
                provenance="filesystem",
            ),
        )

    def resolve_file(self, key: str) -> Path | None:
        if not key:
            return None
        raw = Path(key)
        if raw.is_absolute():
            try:
                candidate = raw.resolve()
            except OSError:
                return None
            if candidate.is_file() and any(
                candidate.is_relative_to(root.resolve())
                for root in self.settings.logs_dirs
                if root.exists()
            ):
                return candidate
            return None
        normalized = key.replace("\\", "/")
        if normalized.startswith("/") or "\x00" in normalized or ".." in normalized.split("/"):
            return None
        for root in self.settings.logs_dirs:
            try:
                base = root.resolve()
                candidate = (base / normalized).resolve()
            except OSError:
                continue
            if candidate.is_relative_to(base) and candidate.is_file():
                return candidate
        # Accept a repo-root-relative path when the root itself is a log root.
        try:
            candidate = (self.settings.root / normalized).resolve()
        except OSError:
            return None
        if candidate.is_file() and any(
            candidate.is_relative_to(root.resolve()) for root in self.settings.logs_dirs if root.exists()
        ):
            return candidate
        return None

    # ------------------------------------------------------------------
    def tail(
        self,
        key: str,
        *,
        level: str = "",
        q: str = "",
        limit: int = 500,
    ) -> Result[list[LogEntry]]:
        path = self.resolve_file(key)
        if path is None:
            return Result(None, _status("log_file", "Log file", SourceState.MISSING, f"cannot resolve {key}"))
        limit = max(1, min(limit, 5000))
        try:
            text, truncated_head = self._read_tail(path)
        except OSError as exc:
            return Result(None, _status("log_file", "Log file", SourceState.ERROR, str(exc), str(path)))
        lines = text.splitlines()
        if truncated_head and lines:
            lines = lines[1:]
        entries: list[LogEntry] = []
        needle = q.lower()
        min_level = LEVEL_ORDER.get(level.upper()) if level else None
        for index, line in enumerate(lines, start=1):
            entry = parse_line(line, index)
            if level:
                if min_level is not None and LEVEL_ORDER.get(entry.level.upper(), 0) < min_level:
                    continue
                if min_level is None and entry.level.upper() != level.upper():
                    continue
            if needle and needle not in line.lower():
                continue
            entries.append(entry)
        total = len(entries)
        entries = entries[-limit:]
        return Result(
            entries,
            _status(
                "log_file",
                "Log file",
                SourceState.OK if entries else SourceState.EMPTY,
                f"{len(entries)} of {total} matching line(s) · tail ≤ {self.settings.log_tail_bytes:,} bytes",
                str(path),
                iso_mtime(path),
                provenance="tail",
            ),
        )

    def _read_tail(self, path: Path) -> tuple[str, bool]:
        cap = self.settings.log_tail_bytes
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > cap:
                handle.seek(size - cap)
                raw = handle.read(cap)
                return raw.decode("utf-8", errors="replace"), True
            return handle.read().decode("utf-8", errors="replace"), False

    @staticmethod
    def _root_logs(root: Path):
        """Repo root holds code and requirements files, so match log names only."""
        for pattern in ("*.log", "*.log.*", "*.jsonl"):
            yield from root.glob(pattern)

    @staticmethod
    def _walk_logs(root: Path):
        for path in root.rglob("*"):
            if any(part in HIDDEN_DIRS for part in path.parts):
                continue
            if path.is_file():
                yield path
