"""Storage layer for ChopCast.

The raw store is SQLite. The schema is defined here. Migrations are
versioned. The store is append-only: the only way to remove a row is a
versioned migration.

See docs/DATA_ENGINEERING.md §2.
"""

from chopcast.storage.schema import (
    ReportStore,
    RunRecord,
    RunResult,
    SqliteReportStore,
)

__all__ = ["ReportStore", "RunRecord", "RunResult", "SqliteReportStore"]
