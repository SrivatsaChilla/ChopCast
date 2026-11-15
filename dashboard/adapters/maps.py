"""Map points and generated map files.

The dashboard re-implements the *visual contract* of ``chopcast/map/folium_app.py``
(same severity colours, circle markers, heat layer) without importing or calling
it. Only valid coordinates are plotted; invalid rows are counted, never dropped
silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.schema_probe import probe_raw_db
from adapters.settings import AdapterSettings
from adapters.sqlite_ro import ReadOnlyDatabase, SourceError, iso_mtime
from adapters.types import (
    MapFile,
    MapPoint,
    MapResult,
    Result,
    SourceState,
    SourceStatus,
)

HIDDEN_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
MAX_MAP_FILES = 500

SEVERITY_ORDER = ("None", "Light", "Moderate", "Severe", "Unlabelled")


@dataclass(frozen=True)
class MapFilters:
    label_layer: str = "combined"  # combined | primary | secondary | all
    label: str = ""  # raw stored value (optional)
    label_values: tuple[str, ...] = ()  # mapped class expanded to raw DB values
    report_type: str = ""
    date_from: str = ""
    date_to: str = ""
    alt_min: float | None = None
    alt_max: float | None = None
    q: str = ""
    include_invalid: bool = False
    bbox: tuple[float, float, float, float] | None = None  # min_lat, min_lon, max_lat, max_lon


def _status(
    key: str,
    label: str,
    state: SourceState,
    detail: str = "",
    path: str = "",
    provenance: str | None = None,
) -> SourceStatus:
    return SourceStatus(
        key=key, label=label, state=state, detail=detail, path=path, provenance=provenance
    )


def _like(value: str) -> str:
    return (
        "%"
        + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        + "%"
    )


COORD_VALID = (
    "lat IS NOT NULL AND lon IS NOT NULL "
    "AND lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180"
)


def _label_filter(clauses: list[str], params: list[Any], column: str, values: tuple[str, ...]) -> None:
    if not values:
        return
    placeholders = ", ".join("?" for _ in values)
    clauses.append(f"{column} IN ({placeholders})")
    params.extend(values)


class MapService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.db = ReadOnlyDatabase(settings.raw_db)
        self._profile = None

    def profile(self):
        if self._profile is None:
            self._profile = probe_raw_db(self.db)
        return self._profile

    # ------------------------------------------------------------------
    def status(self) -> SourceStatus:
        result = self.query(MapFilters(), limit=1)
        return result.status

    def file_status(self) -> SourceStatus:
        result = self.list_map_files()
        return result.status

    def source_table(self) -> tuple[str, tuple[str, ...], str]:
        """Return (table, columns, provenance)."""
        profile = self.profile()
        if "trainable" in profile.views:
            cols = profile.trainable_columns or profile.reports_columns
            provenance = (
                "live trainable view (primary-only predicate)"
                if profile.trainable_predicate == "primary_only"
                else "live trainable view"
            )
            return "trainable", cols, provenance
        return "reports", profile.reports_columns, "reports table + derived predicate"

    # ------------------------------------------------------------------
    def query(
        self,
        filters: MapFilters,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> Result[MapResult]:
        profile = self.profile()
        if not self.db.exists:
            return Result(None, self.status_missing())
        if "reports" not in profile.tables:
            return Result(
                None,
                _status(
                    "maps",
                    "Map points",
                    SourceState.SCHEMA_MISMATCH,
                    "reports table is missing",
                    str(self.settings.raw_db),
                ),
            )
        table, columns, provenance = self.source_table()
        limit = max(1, min(limit or self.settings.map_max_points, self.settings.map_max_points))
        where, params = self._where(filters, table, columns)
        try:
            total = int(
                self.db.scalar(f"SELECT COUNT(*) FROM {table}{where}", tuple(params), default=0)
            )
            invalid = int(
                self.db.scalar(
                    f"SELECT COUNT(*) FROM {table}{self._and(where, f'NOT ({COORD_VALID})')}",
                    tuple(params),
                    default=0,
                )
            )
            plottable = max(0, total - invalid)
            select = self._select(columns)
            rows = self.db.query(
                f"SELECT {select} FROM {table}{self._and(where, f'({COORD_VALID})')} "
                "ORDER BY obs_time IS NULL, obs_time DESC LIMIT ? OFFSET ?",
                tuple(params) + (limit, max(0, offset)),
            )
            counts: dict[str, int] = {}
            label_col = self._label_expression(filters.label_layer, columns)
            if label_col:
                count_rows = self.db.query(
                    f"SELECT {label_col} AS v, COUNT(*) AS n FROM {table}{where} "
                    f"GROUP BY {label_col}",
                    tuple(params),
                )
                for row in count_rows:
                    value = row["v"]
                    if value is None:
                        continue
                    # Stored raw values (MOD, LGT, ...) are mapped in the UI via labeling.yaml.
                    key = str(value)
                    counts[key] = counts.get(key, 0) + int(row["n"])
        except SourceError as exc:
            return Result(
                None,
                _status(
                    "maps",
                    "Map points",
                    SourceState.ERROR,
                    str(exc),
                    str(self.settings.raw_db),
                ),
            )
        points = tuple(self._point(row, filters.label_layer) for row in rows)
        warnings: list[str] = []
        if invalid:
            warnings.append(
                f"{invalid:,} matching row(s) have missing or out-of-range coordinates and are not plotted."
            )
        if plottable > limit:
            warnings.append(
                f"Showing the first {limit:,} of {plottable:,} plottable rows; narrow the filters."
            )
        return Result(
            MapResult(
                points=points,
                total_matching=total,
                returned=len(points),
                truncated=plottable > limit,
                invalid_coords=invalid,
                provenance=provenance,
                warnings=tuple(warnings),
                label_counts=counts,
                plottable=plottable,
            ),
            _status(
                "maps",
                "Map points",
                SourceState.OK if total else SourceState.EMPTY,
                f"{plottable:,} plottable / {total:,} matching · {provenance}",
                str(self.settings.raw_db),
                provenance,
            ),
        )

    def status_missing(self) -> SourceStatus:
        return _status(
            "maps",
            "Map points",
            SourceState.MISSING,
            "raw database not found",
            str(self.settings.raw_db),
        )

    # ------------------------------------------------------------------
    def _where(
        self, f: MapFilters, table: str, columns: tuple[str, ...]
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        has_primary = "turbulence" in columns
        has_secondary = "turbulence_2" in columns
        primary = "turbulence" if has_primary else "NULL"
        secondary = "turbulence_2" if has_secondary else "NULL"
        values = tuple(v for v in f.label_values if v)
        if f.label:
            values = (*values, f.label)
        if f.label_layer == "primary" and has_primary:
            clauses.append("turbulence IS NOT NULL")
            _label_filter(clauses, params, "turbulence", values)
        elif f.label_layer == "secondary" and has_secondary:
            clauses.append("turbulence_2 IS NOT NULL")
            _label_filter(clauses, params, "turbulence_2", values)
        elif f.label_layer == "combined":
            clauses.append(f"COALESCE({primary}, {secondary}) IS NOT NULL")
            _label_filter(clauses, params, f"COALESCE({primary}, {secondary})", values)
        elif values:
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"({primary} IN ({placeholders}) OR {secondary} IN ({placeholders}))")
            params.extend(values * 2)
        if f.report_type and "report_type" in columns:
            clauses.append("report_type = ?")
            params.append(f.report_type)
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
        if f.q:
            clauses.append("(raw_text LIKE ? ESCAPE '\\' OR hash LIKE ? ESCAPE '\\')")
            params.extend([_like(f.q), _like(f.q)])
        if f.bbox:
            min_lat, min_lon, max_lat, max_lon = f.bbox
            clauses.append("lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?")
            params.extend([min_lat, max_lat, min_lon, max_lon])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    @staticmethod
    def _and(where: str, clause: str) -> str:
        return f"{where} AND {clause}" if where else f" WHERE {clause}"

    def _select(self, columns: tuple[str, ...]) -> str:
        def col(name: str, alias: str | None = None) -> str:
            if name in columns:
                return name if alias is None else f"{name} AS {alias}"
            return f"NULL AS {alias or name}"

        return ", ".join(
            [
                col("hash"),
                col("obs_time"),
                col("altitude"),
                col("aircraft"),
                col("report_type"),
                col("turbulence"),
                col("turbulence_2"),
                col("lat"),
                col("lon"),
                col("raw_text"),
            ]
        )

    @staticmethod
    def _label_expression(layer: str, columns: tuple[str, ...]) -> str | None:
        primary = "turbulence" if "turbulence" in columns else "NULL"
        secondary = "turbulence_2" if "turbulence_2" in columns else "NULL"
        if layer == "primary":
            return primary
        if layer == "secondary":
            return secondary
        if layer == "combined":
            return f"COALESCE({primary}, {secondary})"
        return None

    @staticmethod
    def _point(row: dict[str, Any], layer: str) -> MapPoint:
        primary = row.get("turbulence")
        secondary = row.get("turbulence_2")
        combined = primary if primary is not None else secondary
        lat = float(row["lat"])
        lon = float(row["lon"])
        raw = row.get("raw_text") or ""
        return MapPoint(
            hash=str(row.get("hash") or ""),
            lat=lat,
            lon=lon,
            obs_time=row.get("obs_time"),
            altitude=float(row["altitude"]) if row.get("altitude") is not None else None,
            aircraft=row.get("aircraft"),
            report_type=row.get("report_type"),
            label_primary=str(primary) if primary is not None else None,
            label_secondary=str(secondary) if secondary is not None else None,
            label_combined=str(combined) if combined is not None else None,
            raw_text=str(raw)[:300],
            suspicious=(lat == 0.0 and lon == 0.0),
        )

    # ------------------------------------------------------------------
    def list_map_files(self) -> Result[list[MapFile]]:
        if not any(root.exists() for root in self.settings.map_dirs):
            return Result(
                [],
                _status(
                    "map_files",
                    "Generated maps",
                    SourceState.MISSING,
                    "no configured map directory exists",
                ),
            )
        found: dict[str, MapFile] = {}
        for root in self.settings.map_dirs:
            if not root.is_dir():
                continue
            try:
                if root.resolve() == self.settings.root.resolve():
                    candidates = root.glob("*.html")
                else:
                    candidates = self._walk_html(root)
                for path in candidates:
                    try:
                        resolved = path.resolve()
                    except OSError:
                        continue
                    if not resolved.is_file() or resolved.suffix.lower() != ".html":
                        continue
                    key = str(resolved)
                    if key in found:
                        continue
                    rel = self.settings.display_path(resolved).replace("\\", "/")
                    try:
                        stat = resolved.stat()
                        size = stat.st_size
                    except OSError:
                        size = 0
                    found[key] = MapFile(
                        name=resolved.name,
                        relative=rel,
                        path=str(resolved),
                        size=size,
                        mtime=iso_mtime(resolved),
                    )
                    if len(found) >= MAX_MAP_FILES:
                        break
            except OSError:
                continue
            if len(found) >= MAX_MAP_FILES:
                break
        items = sorted(found.values(), key=lambda f: (f.mtime or "", f.name), reverse=True)
        return Result(
            items,
            _status(
                "map_files",
                "Generated maps",
                SourceState.OK if items else SourceState.EMPTY,
                f"{len(items)} HTML file(s)" if items else "no generated map HTML found",
                provenance="filesystem",
            ),
        )

    def resolve_file(self, relpath: str) -> Path | None:
        """Resolve a map file path inside the configured roots, or None."""
        if not relpath:
            return None
        normalized = relpath.replace("\\", "/")
        if normalized.startswith("/") or "\x00" in normalized:
            return None
        parts = [part for part in normalized.split("/") if part]
        if any(part in {"..", "."} for part in parts):
            return None
        if not normalized.lower().endswith(".html"):
            return None
        bases = [self.settings.root, *self.settings.map_dirs]
        for base in bases:
            try:
                base_resolved = base.resolve()
            except OSError:
                continue
            candidate = (base / normalized).resolve()
            if not candidate.is_relative_to(base_resolved):
                continue
            if not candidate.is_file() or candidate.suffix.lower() != ".html":
                continue
            if candidate.is_relative_to(self.settings.root) or any(
                candidate.is_relative_to(root.resolve())
                for root in self.settings.map_dirs
                if root.exists()
            ):
                return candidate
        return None

    @staticmethod
    def _walk_html(root: Path):
        for path in root.rglob("*.html"):
            if any(part in HIDDEN_DIRS for part in path.parts):
                continue
            yield path
