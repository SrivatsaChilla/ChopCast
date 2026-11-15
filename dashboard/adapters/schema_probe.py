"""Schema and capability detection for the two pipeline databases."""

from __future__ import annotations

from adapters.sqlite_ro import ReadOnlyDatabase, SourceError
from adapters.types import RawDbProfile, RegistryProfile

LEGACY_RUNS_COLUMNS = {"id", "ran_at", "rows_seen", "inserted", "skipped", "status"}
TARGET_RUNS_COLUMNS = {
    "id",
    "started_at",
    "finished_at",
    "status",
    "rows_seen",
    "rows_inserted",
    "rows_skipped",
    "rows_rejected",
    "error",
}

TARGET_REPORTS_COLUMNS = {
    "hash",
    "fetched_at",
    "obs_time",
    "report_type",
    "raw_text",
    "turbulence",
    "aircraft",
    "lat",
    "lon",
    "altitude",
    "raw_json",
    "source_url",
    "source_etag",
}


def schema_diff(profile: RawDbProfile) -> dict[str, tuple[str, ...]]:
    """Exact column/table differences against the checked-in target schema."""
    reports = set(profile.reports_columns)
    runs = set(profile.runs_columns)
    return {
        "reports_missing": tuple(sorted(TARGET_REPORTS_COLUMNS - reports)),
        "reports_extra": tuple(sorted(reports - TARGET_REPORTS_COLUMNS)),
        "runs_missing": tuple(sorted(TARGET_RUNS_COLUMNS - runs)),
        "runs_extra": tuple(sorted(runs - TARGET_RUNS_COLUMNS)),
        "tables_missing": tuple(
            name for name in ("rejected", "schema_migrations") if name not in profile.tables
        ),
    }



def probe_raw_db(db: ReadOnlyDatabase) -> RawDbProfile:
    if not db.exists:
        return RawDbProfile(state="missing", notes=("database file not found",))
    try:
        tables = db.tables()
        views = db.views()
        reports_cols = db.columns("reports")
        runs_cols = db.columns("runs")
        trainable_cols = db.columns("trainable") if "trainable" in views else ()
        migrations: tuple[int, ...] = ()
        if "schema_migrations" in tables:
            try:
                rows = db.query("SELECT version FROM schema_migrations ORDER BY version")
                migrations = tuple(int(r["version"]) for r in rows)
            except (SourceError, TypeError, ValueError):
                migrations = ()
        trainable_sql = views.get("trainable", "")
        predicate = "unknown"
        if "OR" in trainable_sql.upper() and "TURBULENCE_2" in trainable_sql.upper():
            predicate = "either_layer"
        elif "TURBULENCE IS NOT NULL" in trainable_sql.upper():
            predicate = "primary_only"
        has_report_type = "report_type" in trainable_cols

        notes: list[str] = []
        if not reports_cols:
            notes.append("reports table is missing")
        if "trainable" not in views:
            notes.append("trainable view is missing")
        if "rejected" not in tables:
            notes.append("rejected table is missing (target schema)")
        if "source_url" not in reports_cols:
            notes.append("reports.source_url is missing (target schema)")
        if "source_etag" not in reports_cols:
            notes.append("reports.source_etag is missing (target schema)")
        if not migrations:
            notes.append("schema_migrations is missing or empty")
        if trainable_cols and not has_report_type:
            notes.append("trainable has no report_type column (migration-3 shape)")

        runs_shape = "unknown"
        if runs_cols:
            if TARGET_RUNS_COLUMNS.issubset(set(runs_cols)):
                runs_shape = "target"
            elif LEGACY_RUNS_COLUMNS.issubset(set(runs_cols)):
                runs_shape = "legacy"

        if not reports_cols:
            state = "unknown"
        elif runs_shape == "target" and "source_url" in reports_cols and "rejected" in tables:
            state = "target"
        elif runs_shape == "legacy" and "turbulence_2" in reports_cols and "source_url" not in reports_cols:
            state = "legacy"
        else:
            state = "mixed"

        return RawDbProfile(
            state=state,
            tables=tuple(sorted(tables)),
            views=views,
            reports_columns=reports_cols,
            runs_columns=runs_cols,
            trainable_columns=trainable_cols,
            schema_migrations=migrations,
            trainable_predicate=predicate,
            has_report_type_in_trainable=has_report_type,
            has_rejected="rejected" in tables,
            runs_shape=runs_shape,
            notes=tuple(notes),
        )
    except SourceError as exc:
        return RawDbProfile(state="error", notes=(str(exc),))
    except Exception as exc:  # defensive: a probe must never break a page
        return RawDbProfile(state="error", notes=(f"schema probe failed: {exc}",))


def probe_registry(db: ReadOnlyDatabase) -> RegistryProfile:
    if not db.exists:
        return RegistryProfile(state="missing", notes=("database file not found",))
    try:
        tables = db.tables()
        has_models = "models" in tables
        has_promotions = "promotions" in tables
        stray = tuple(
            sorted(
                t
                for t in tables
                if t in {"reports", "schema_migrations", "rejected", "runs"}
            )
        )
        notes: list[str] = []
        if not has_models:
            notes.append("models table is missing")
        if not has_promotions:
            notes.append("promotions table is missing")
        if stray:
            notes.append("registry contains raw-data tables (ISS-005)")
        state = "ok" if has_models and has_promotions else "schema_mismatch"
        return RegistryProfile(
            state=state,
            tables=tuple(sorted(tables)),
            has_models=has_models,
            has_promotions=has_promotions,
            stray_raw_tables=stray,
            notes=tuple(notes),
        )
    except SourceError as exc:
        return RegistryProfile(state="error", notes=(str(exc),))
    except Exception as exc:
        return RegistryProfile(state="error", notes=(f"schema probe failed: {exc}",))
