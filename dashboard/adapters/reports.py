"""Read-only access to the raw report store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from adapters.schema_probe import probe_raw_db
from adapters.settings import AdapterSettings
from adapters.sqlite_ro import ReadOnlyDatabase, SourceError, iso_mtime
from adapters.types import (
    Page,
    RejectedRecord,
    ReportDetail,
    ReportRow,
    ReportSummary,
    Result,
    RunRecord,
    SourceState,
    SourceStatus,
)

SORT_COLUMNS = {
    "obs_time": "obs_time",
    "fetched_at": "fetched_at",
    "report_type": "report_type",
    "turbulence": "turbulence",
    "turbulence_2": "turbulence_2",
    "altitude": "altitude",
    "aircraft": "aircraft",
    "hash": "hash",
}


@dataclass(frozen=True)
class ReportFilters:
    q: str = ""
    report_type: str = ""
    label_layer: str = "any"
    label: str = ""
    date_from: str = ""
    date_to: str = ""
    alt_min: float | None = None
    alt_max: float | None = None
    has_coords: str = ""
    sort: str = "obs_time"
    direction: str = "desc"


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


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


class ReportService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.db = ReadOnlyDatabase(settings.raw_db)
        self._profile = None

    # ------------------------------------------------------------------
    def profile(self):
        if self._profile is None:
            self._profile = probe_raw_db(self.db)
        return self._profile

    def status(self) -> SourceStatus:
        profile = self.profile()
        if not self.db.exists:
            return _status(
                "raw_db", "Raw database", SourceState.MISSING, "file not found", str(self.settings.raw_db)
            )
        if profile.state == "error":
            return _status(
                "raw_db",
                "Raw database",
                SourceState.ERROR,
                "; ".join(profile.notes) or "unreadable",
                str(self.settings.raw_db),
                self.db.mtime,
            )
        if "reports" not in profile.tables:
            return _status(
                "raw_db",
                "Raw database",
                SourceState.SCHEMA_MISMATCH,
                "reports table is missing",
                str(self.settings.raw_db),
                self.db.mtime,
            )
        try:
            total = int(self.db.scalar("SELECT COUNT(*) FROM reports", default=0))
        except SourceError as exc:
            return _status("raw_db", "Raw database", SourceState.ERROR, str(exc), str(self.settings.raw_db), self.db.mtime)
        if total == 0:
            return _status("raw_db", "Raw database", SourceState.EMPTY, "0 reports", str(self.settings.raw_db), self.db.mtime)
        return _status(
            "raw_db",
            "Raw database",
            SourceState.OK,
            f"{total:,} reports · {profile.state}",
            str(self.settings.raw_db),
            self.db.mtime,
            profile.state,
        )

    # ------------------------------------------------------------------
    def summary(self) -> Result[ReportSummary]:
        profile = self.profile()
        if not self.db.exists:
            return Result(None, self.status())
        if "reports" not in profile.tables:
            return Result(None, self.status())
        try:
            total = int(self.db.scalar("SELECT COUNT(*) FROM reports", default=0))
            by_type: dict[str, int] = {}
            if "report_type" in profile.reports_columns:
                for row in self.db.query(
                    "SELECT COALESCE(report_type, '(null)') AS k, COUNT(*) AS n "
                    "FROM reports GROUP BY report_type ORDER BY n DESC"
                ):
                    by_type[str(row["k"])] = int(row["n"])
            trainable = 0
            if "trainable" in profile.views:
                trainable = int(self.db.scalar("SELECT COUNT(*) FROM trainable", default=0))
            primary = int(
                self.db.scalar("SELECT COUNT(*) FROM reports WHERE turbulence IS NOT NULL", default=0)
            )
            secondary = int(
                self.db.scalar("SELECT COUNT(*) FROM reports WHERE turbulence_2 IS NOT NULL", default=0)
            )
            bounds = self.db.one(
                "SELECT MIN(obs_time) AS min_obs, MAX(obs_time) AS max_obs, "
                "MIN(fetched_at) AS min_fetched, MAX(fetched_at) AS max_fetched FROM reports"
            ) or {}
            with_coords = int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM reports WHERE lat IS NOT NULL AND lon IS NOT NULL "
                    "AND lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180",
                    default=0,
                )
            )
            without_coords = int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM reports WHERE lat IS NULL OR lon IS NULL",
                    default=0,
                )
            )
            invalid = int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM reports WHERE (lat IS NOT NULL AND (lat < -90 OR lat > 90)) "
                    "OR (lon IS NOT NULL AND (lon < -180 OR lon > 180))",
                    default=0,
                )
            )
            distinct = int(self.db.scalar("SELECT COUNT(DISTINCT hash) FROM reports", default=0))
        except SourceError as exc:
            return Result(None, _status("raw_db", "Raw database", SourceState.ERROR, str(exc), str(self.settings.raw_db)))
        data = ReportSummary(
            total=total,
            by_type=by_type,
            trainable_rows=trainable,
            primary_labelled=primary,
            secondary_labelled=secondary,
            first_obs_time=_str_or_none(bounds.get("min_obs")),
            last_obs_time=_str_or_none(bounds.get("max_obs")),
            first_fetched_at=_str_or_none(bounds.get("min_fetched")),
            last_fetched_at=_str_or_none(bounds.get("max_fetched")),
            with_coords=with_coords,
            without_coords=without_coords,
            invalid_coords=invalid,
            distinct_hashes=distinct,
        )
        state = SourceState.OK if total else SourceState.EMPTY
        return Result(
            data,
            _status(
                "raw_db",
                "Raw database",
                state,
                f"{total:,} reports",
                str(self.settings.raw_db),
                self.db.mtime,
                profile.state,
            ),
        )

    # ------------------------------------------------------------------
    def run_history(self, limit: int = 20) -> Result[list[RunRecord]]:
        profile = self.profile()
        if not self.db.exists:
            return Result(None, self.status())
        if "runs" not in profile.tables:
            return Result(
                [],
                _status("runs", "Collection runs", SourceState.EMPTY, "runs table is missing"),
            )
        cols = set(profile.runs_columns)
        shape = profile.runs_shape
        aliases = {
            "id": ("id", "id"),
            "started_at": ("started_at", "ran_at"),
            "finished_at": ("finished_at", "finished_at"),
            "status": ("status", "status"),
            "rows_seen": ("rows_seen", "rows_seen"),
            "rows_inserted": ("rows_inserted", "inserted"),
            "rows_skipped": ("rows_skipped", "skipped"),
            "rows_rejected": ("rows_rejected", "rows_rejected"),
            "error": ("error", "error"),
        }
        parts: list[str] = []
        for target, (target_col, legacy_col) in aliases.items():
            if target_col in cols:
                parts.append(target_col)
            elif legacy_col in cols:
                parts.append(f"{legacy_col} AS {target}")
            else:
                parts.append(f"NULL AS {target}")
        select = ", ".join(parts)
        try:
            rows = self.db.query(f"SELECT {select} FROM runs ORDER BY id DESC LIMIT ?", (int(limit),))
        except SourceError as exc:
            return Result(None, _status("runs", "Collection runs", SourceState.ERROR, str(exc)))
        items = tuple(
            RunRecord(
                id=int(r["id"]),
                started_at=_str_or_none(r.get("started_at")),
                finished_at=_str_or_none(r.get("finished_at")),
                status=str(r.get("status") or "unknown"),
                rows_seen=_int_or_none(r.get("rows_seen")),
                rows_inserted=_int_or_none(r.get("rows_inserted")),
                rows_skipped=_int_or_none(r.get("rows_skipped")),
                rows_rejected=_int_or_none(r.get("rows_rejected")),
                error=_str_or_none(r.get("error")),
                shape=shape,
            )
            for r in rows
        )
        return Result(
            list(items),
            _status(
                "runs",
                "Collection runs",
                SourceState.OK if items else SourceState.EMPTY,
                f"{len(items)} run(s) · {shape}",
                str(self.settings.raw_db),
                self.db.mtime,
                f"{shape} runs",
            ),
        )

    def rejected(self, limit: int = 20) -> Result[list[RejectedRecord]]:
        profile = self.profile()
        if not self.db.exists:
            return Result(None, self.status())
        if "rejected" not in profile.tables:
            return Result(
                [],
                _status(
                    "rejected",
                    "Rejected rows",
                    SourceState.EMPTY,
                    "rejected table is absent in the legacy database",
                ),
            )
        try:
            rows = self.db.query(
                "SELECT id, fetched_at, reason, detail FROM rejected ORDER BY id DESC LIMIT ?",
                (int(limit),),
            )
        except SourceError as exc:
            return Result(None, _status("rejected", "Rejected rows", SourceState.ERROR, str(exc)))
        items = tuple(
            RejectedRecord(
                id=int(r["id"]),
                fetched_at=_str_or_none(r.get("fetched_at")),
                reason=str(r.get("reason") or "unknown"),
                detail=_str_or_none(r.get("detail")),
            )
            for r in rows
        )
        return Result(
            list(items),
            _status(
                "rejected",
                "Rejected rows",
                SourceState.OK if items else SourceState.EMPTY,
                f"{len(items)} row(s)",
            ),
        )

    # ------------------------------------------------------------------
    def list_reports(
        self,
        filters: ReportFilters,
        *,
        page: int = 1,
        page_size: int | None = None,
    ) -> Result[Page[ReportRow]]:
        profile = self.profile()
        page_size = page_size or self.settings.page_size
        page_size = max(1, min(page_size, self.settings.max_page_size))
        if not self.db.exists or "reports" not in profile.tables:
            return Result(None, self.status())
        where, params = self._where(filters, profile.reports_columns)
        sort = SORT_COLUMNS.get(filters.sort, "obs_time")
        direction = "DESC" if filters.direction.lower() != "asc" else "ASC"
        order = f"{sort} IS NULL, {sort} {direction}"
        try:
            total = int(self.db.scalar(f"SELECT COUNT(*) FROM reports{where}", tuple(params), default=0))
            page = max(1, min(page, max(1, (total + page_size - 1) // page_size)))
            rows = self.db.query(
                "SELECT hash, fetched_at, obs_time, report_type, raw_text, turbulence, "
                "turbulence_2, aircraft, lat, lon, altitude FROM reports"
                f"{where} ORDER BY {order} LIMIT ? OFFSET ?",
                tuple(params) + (page_size, (page - 1) * page_size),
            )
        except SourceError as exc:
            return Result(None, _status("reports", "Reports", SourceState.ERROR, str(exc)))
        items = tuple(_row(r) for r in rows)
        return Result(
            Page(items=items, total=total, page=page, page_size=page_size),
            _status(
                "reports",
                "Reports",
                SourceState.OK if total else SourceState.EMPTY,
                f"{total:,} matching reports",
                str(self.settings.raw_db),
                self.db.mtime,
                profile.state,
            ),
        )

    def recent(self, limit: int = 10) -> Result[list[ReportRow]]:
        result = self.list_reports(
            ReportFilters(sort="obs_time", direction="desc"), page=1, page_size=limit
        )
        if result.data is None:
            return Result(None, result.status)
        return Result(list(result.data.items), result.status)

    def get_report(self, report_hash: str) -> Result[ReportDetail]:
        profile = self.profile()
        if not self.db.exists or "reports" not in profile.tables:
            return Result(None, self.status())
        try:
            rows = self.db.query("SELECT * FROM reports WHERE hash = ?", (report_hash,))
        except SourceError as exc:
            return Result(None, _status("report", "Report", SourceState.ERROR, str(exc)))
        if not rows:
            return Result(
                None,
                _status("report", "Report", SourceState.MISSING, f"no report with hash {report_hash}"),
            )
        raw = rows[0]
        raw_json = None
        raw_json_error = None
        if raw.get("raw_json"):
            try:
                raw_json = json.dumps(json.loads(raw["raw_json"]), indent=2, ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                raw_json_error = str(exc)
                raw_json = str(raw["raw_json"])
        return Result(
            ReportDetail(row=_row(raw), raw_json=raw_json, raw_json_error=raw_json_error),
            _status("report", "Report", SourceState.OK, report_hash[:12], provenance=profile.state),
        )

    # ------------------------------------------------------------------
    def quality(self) -> Result[dict[str, Any]]:
        profile = self.profile()
        if not self.db.exists or "reports" not in profile.tables:
            return Result(None, self.status())
        fields = {
            "hash": "hash",
            "fetched_at": "fetched_at",
            "obs_time": "obs_time",
            "report_type": "report_type",
            "raw_text": "raw_text",
            "turbulence": "turbulence",
            "turbulence_2": "turbulence_2",
            "aircraft": "aircraft",
            "lat": "lat",
            "lon": "lon",
            "altitude": "altitude",
        }
        nulls: dict[str, int] = {}
        try:
            for key, col in fields.items():
                if col in profile.reports_columns:
                    nulls[key] = int(
                        self.db.scalar(f"SELECT COUNT(*) FROM reports WHERE {col} IS NULL", default=0)
                    )
            blank_text = int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM reports WHERE raw_text IS NULL OR TRIM(raw_text) = ''",
                    default=0,
                )
            )
            distinct_aircraft = int(
                self.db.scalar("SELECT COUNT(DISTINCT aircraft) FROM reports WHERE aircraft IS NOT NULL", default=0)
            )
            distinct_days = int(
                self.db.scalar("SELECT COUNT(DISTINCT substr(fetched_at,1,10)) FROM reports", default=0)
            )
        except SourceError as exc:
            return Result(None, _status("quality", "Data quality", SourceState.ERROR, str(exc)))
        return Result(
            {
                "total": int(self.db.scalar("SELECT COUNT(*) FROM reports", default=0)),
                "nulls": nulls,
                "blank_text": blank_text,
                "distinct_aircraft": distinct_aircraft,
                "distinct_fetch_days": distinct_days,
            },
            _status("quality", "Data quality", SourceState.OK, "column null counts"),
        )

    # ------------------------------------------------------------------
    def _where(self, f: ReportFilters, columns: tuple[str, ...]) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if f.q:
            clauses.append("(hash LIKE ? ESCAPE '\\' OR raw_text LIKE ? ESCAPE '\\')")
            params.extend([_like(f.q), _like(f.q)])
        if f.report_type and "report_type" in columns:
            clauses.append("report_type = ?")
            params.append(f.report_type)
        if f.label_layer == "primary":
            clauses.append("turbulence IS NOT NULL")
            if f.label:
                clauses.append("turbulence = ?")
                params.append(f.label)
        elif f.label_layer == "secondary":
            clauses.append("turbulence_2 IS NOT NULL")
            if f.label:
                clauses.append("turbulence_2 = ?")
                params.append(f.label)
        elif f.label_layer == "combined":
            clauses.append("COALESCE(turbulence, turbulence_2) IS NOT NULL")
            if f.label:
                clauses.append("COALESCE(turbulence, turbulence_2) = ?")
                params.append(f.label)
        elif f.label:
            clauses.append("(turbulence = ? OR turbulence_2 = ?)")
            params.extend([f.label, f.label])
        if f.date_from:
            clauses.append("substr(obs_time,1,10) >= ?")
            params.append(f.date_from)
        if f.date_to:
            clauses.append("substr(obs_time,1,10) <= ?")
            params.append(f.date_to)
        if f.alt_min is not None:
            clauses.append("altitude >= ?")
            params.append(f.alt_min)
        if f.alt_max is not None:
            clauses.append("altitude <= ?")
            params.append(f.alt_max)
        if f.has_coords == "yes":
            clauses.append(
                "lat IS NOT NULL AND lon IS NOT NULL AND lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180"
            )
        elif f.has_coords == "no":
            clauses.append(
                "(lat IS NULL OR lon IS NULL OR lat < -90 OR lat > 90 OR lon < -180 OR lon > 180)"
            )
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _row(r: dict[str, Any]) -> ReportRow:
    return ReportRow(
        hash=str(r.get("hash") or ""),
        fetched_at=_str_or_none(r.get("fetched_at")),
        obs_time=_str_or_none(r.get("obs_time")),
        report_type=_str_or_none(r.get("report_type")),
        raw_text=_str_or_none(r.get("raw_text")),
        turbulence=_str_or_none(r.get("turbulence")),
        turbulence_2=_str_or_none(r.get("turbulence_2")),
        aircraft=_str_or_none(r.get("aircraft")),
        lat=_float_or_none(r.get("lat")),
        lon=_float_or_none(r.get("lon")),
        altitude=_float_or_none(r.get("altitude")),
    )


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
