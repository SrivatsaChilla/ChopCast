"""The collection orchestrator.

Pulls data, validates, dedups, stores, records a run. Pure orchestration —
no HTTP, no SQL, no parsing of PIREP content. All dependencies are injected.

See docs/MODULE_DESIGN.md §2.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, runtime_checkable

import pandas as pd

from chopcast.collector.client import AwcClient
from chopcast.collector.hasher import report_hash as compute_hash
from chopcast.collector.validators import DefaultRowValidator, RowValidator, Verdict
from chopcast.config import CollectorConfig
from chopcast.errors import ChopcastError
from chopcast.logging import get_logger
from chopcast.storage.schema import ReportStore, RunResult

log = get_logger(__name__)


@runtime_checkable
class CollectionService(Protocol):
    """One cycle of: fetch -> validate -> dedup -> store -> record."""

    def run_once(self) -> RunResult: ...


# ---------------------------------------------------------------------------
# Column resolution
# ---------------------------------------------------------------------------
# The CSV from AWC has changed column names historically (Sept 2025 renames
# were the most recent). We resolve at runtime rather than hardcoding.
# Verified against a live AWC cache pull: the served columns are snake_case
# (`turbulence_intensity`, `report_type`, ...). The camelCase spellings are
# kept as fallbacks for the legacy/XML feed. Order matters -- first match wins.
#
# NB: matching is case-insensitive but NOT separator-insensitive, so
# "turbulenceIntensity" does not match "turbulence_intensity". Omitting the
# snake_case spelling leaves `turbulence` and `report_type` unresolved, which
# stores NULL for the label and the PIREP/AIREP filter on every row -- with no
# error anywhere. Do not remove these entries.
CANDIDATES: dict[str, list[str]] = {
    "raw_text": ["raw_text", "rawOb", "raw", "report", "rawReport"],
    "turbulence": ["turbulence_intensity", "turbulence", "tbInt1", "turbInt", "tb", "turbulenceIntensity"],
    "turbulence_2": ["turbulence_intensity.1"],
    "turbulence_type": ["turbulence_type", "turbulenceType"],
    "turbulence_freq": ["turbulence_freq", "turbulenceFreq"],
    "report_type": ["report_type", "reportType", "obsType", "type", "acReportType"],
    "aircraft": ["aircraft_ref", "acType", "aircraftType", "actype"],
    "lat": ["latitude", "lat"],
    "lon": ["longitude", "lon"],
    "altitude": ["altitude_ft_msl", "altFt", "fltLvl", "flightLevel", "alt"],
    "obs_time": ["observation_time", "obsTime", "receiptTime", "time"],
}


def resolve_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """Map logical field names to actual DataFrame columns.

    The match is case-insensitive. If a logical field has no candidate in
    `df.columns`, the value is `None` — the collector will then attempt to
    validate without that field.
    """
    lower = {c.lower(): c for c in df.columns}
    resolved: dict[str, str | None] = {}
    for key, candidates in CANDIDATES.items():
        resolved[key] = None
        for cand in candidates:
            actual = lower.get(cand.lower())
            if actual is not None:
                resolved[key] = actual
                break
    missing = [k for k, v in resolved.items() if v is None]
    if missing:
        log.warning("collector.columns.unresolved", missing=missing)
    return resolved



def _text_value(value: object) -> str | None:
    """Stringify a value, but keep missing values as None.

    `str(_clean_value(x))` turns a missing value into the literal string
    "None", which then satisfies `turbulence IS NOT NULL` and poisons every
    downstream filter. Absent stays absent.
    """
    cleaned = _clean_value(value)
    return None if cleaned is None else str(cleaned)

def _clean_value(value: Any) -> Any:
    """Replace NaN/None with Python None, leave everything else alone."""
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _to_float(value: Any) -> float | None:
    cleaned = _clean_value(value)
    if cleaned is None:
        return None
    try:
        f = float(cleaned)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _normalise_columns(df: pd.DataFrame, cols: dict[str, str | None]) -> pd.DataFrame:
    """Return a copy of `df` with logical column names where possible.

    Only renames columns whose logical field was resolved. Unmapped columns
    stay as-is, so callers can still see all source fields if they need to.
    """
    rename = {actual: logical for logical, actual in cols.items() if actual is not None}
    return df.rename(columns=rename)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@dataclass
class DefaultCollectionService:
    """The default collection orchestrator.

    Dependencies are injected at construction, which makes the service
    testable end-to-end with a mock client and a temp DB.
    """

    client: AwcClient
    store: ReportStore
    config: CollectorConfig
    validator: RowValidator | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def __post_init__(self) -> None:
        if self.validator is None:
            self.validator = DefaultRowValidator(self.config.validation)

    def run_once(self) -> RunResult:
        started_at = self.clock()
        run_id = self.store.begin_run(started_at)
        source_url = getattr(self.client, "_url", "<unknown>")
        log.info("collector.cycle.start", run_id=run_id)

        try:
            df = self.client.fetch_aircraft_reports()
        except ChopcastError as e:
            finished_at = self.clock()
            self.store.finish_run(
                run_id,
                finished_at=finished_at,
                status="http_error",
                rows_seen=0,
                rows_inserted=0,
                rows_skipped=0,
                rows_rejected=0,
                error=f"{type(e).__name__}: {e}",
            )
            log.error("collector.cycle.failed", run_id=run_id, error=str(e))
            raise

        if df is None:
            finished_at = self.clock()
            self.store.finish_run(
                run_id,
                finished_at=finished_at,
                status="no_data",
                rows_seen=0,
                rows_inserted=0,
                rows_skipped=0,
                rows_rejected=0,
            )
            log.info("collector.cycle.no_data", run_id=run_id)
            return RunResult(run_id=run_id, status="no_data")

        cols = resolve_columns(df)
        # Normalise the DataFrame to logical column names so the validator
        # and downstream code do not need to know about AWC's column history.
        norm = _normalise_columns(df, cols)
        inserted = 0
        skipped = 0
        rejected = 0
        for _, row in norm.iterrows():
            verdict = self.validator.validate(row) if self.validator else Verdict(ok=True)
            if not verdict.ok:
                self.store.insert_rejected(
                    fetched_at=started_at,
                    reason=verdict.reason or "rejected",
                    raw_row=row.to_dict(),
                    source_url=source_url,
                    detail=verdict.detail,
                )
                rejected += 1
                continue

            obs_time_val = _clean_value(row.get("obs_time"))
            raw_text_val = _clean_value(row.get("raw_text"))
            lat = _to_float(row.get("lat"))
            lon = _to_float(row.get("lon"))
            try:
                h = compute_hash(
                    str(obs_time_val) if obs_time_val is not None else None,
                    lat,
                    lon,
                    str(raw_text_val) if raw_text_val is not None else None,
                    lat_decimals=self.config.dedup.lat_decimals,
                    lon_decimals=self.config.dedup.lon_decimals,
                )
            except Exception:
                self.store.insert_rejected(
                    fetched_at=started_at,
                    reason="missing_hash_inputs",
                    raw_row=row.to_dict(),
                    source_url=source_url,
                    detail="obs_time or raw_text is missing",
                )
                rejected += 1
                continue

            was_inserted = self.store.insert_report(
                hash=h,
                fetched_at=started_at,
                obs_time=str(obs_time_val) if obs_time_val is not None else None,
                report_type=_text_value(row.get("report_type")),
                raw_text=str(raw_text_val) if raw_text_val is not None else None,
                turbulence=_text_value(row.get("turbulence")),
                turbulence_2=_text_value(row.get("turbulence_2")),
                turbulence_type=_text_value(row.get("turbulence_type")),
                turbulence_freq=_text_value(row.get("turbulence_freq")),
                aircraft=_text_value(row.get("aircraft")),
                lat=lat,
                lon=lon,
                altitude=_to_float(row.get("altitude")),
                raw_json={k: _clean_value(v) for k, v in row.to_dict().items()},
                source_url=source_url,
            )
            if was_inserted:
                inserted += 1
            else:
                skipped += 1

        finished_at = self.clock()
        self.store.finish_run(
            run_id,
            finished_at=finished_at,
            status="ok",
            rows_seen=len(df),
            rows_inserted=inserted,
            rows_skipped=skipped,
            rows_rejected=rejected,
        )
        result = RunResult(
            run_id=run_id,
            status="ok",
            rows_seen=len(df),
            rows_inserted=inserted,
            rows_skipped=skipped,
            rows_rejected=rejected,
        )
        log.info("collector.cycle.complete", **result.as_log_dict())
        return result


__all__ = [
    "CANDIDATES",
    "CollectionService",
    "DefaultCollectionService",
    "resolve_columns",
]
