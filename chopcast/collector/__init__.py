"""Collector subpackage.

The collector is the only component that talks to AWC. It fetches raw
reports, validates them, dedups by content hash, and stores them in
the `ReportStore`. The collector does not parse, label, or model.

See docs/MODULE_DESIGN.md §2 and docs/ROADMAP.md M1.
"""

from chopcast.collector.hasher import report_hash
from chopcast.collector.service import CollectionService, DefaultCollectionService
from chopcast.collector.validators import DefaultRowValidator, RowValidator, Verdict

__all__ = [
    "CollectionService",
    "DefaultCollectionService",
    "DefaultRowValidator",
    "RowValidator",
    "Verdict",
    "report_hash",
]
