"""Tests for chopcast.collector.service.DefaultCollectionService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import pandas as pd
import pytest

from chopcast.collector.client import AwcClient
from chopcast.collector.service import DefaultCollectionService, resolve_columns
from chopcast.config import CollectorConfig
from chopcast.storage.schema import SqliteReportStore


class _MockClient:
    """Implements the AwcClient protocol for tests."""

    def __init__(self, df: pd.DataFrame | None) -> None:
        self._df = df
        self.calls = 0

    def fetch_aircraft_reports(self) -> pd.DataFrame | None:
        self.calls += 1
        return self._df


def _service(
    store: SqliteReportStore,
    df: pd.DataFrame | None,
    *,
    clock: Iterator[datetime] | None = None,
) -> DefaultCollectionService:
    return DefaultCollectionService(
        client=_MockClient(df),
        store=store,
        config=CollectorConfig(),
        clock=lambda: next(clock) if clock else datetime.now(timezone.utc),
    )


def test_resolve_columns_finds_known_names() -> None:
    df = pd.DataFrame(columns=["rawOb", "turbulence", "reportType", "acType", "lat", "lon", "fltLvl", "obsTime"])
    cols = resolve_columns(df)
    assert cols == {
        "raw_text": "rawOb",
        "turbulence": "turbulence",
        "turbulence_2": None,
        "turbulence_type": None,
        "turbulence_freq": None,
        "report_type": "reportType",
        "aircraft": "acType",
        "lat": "lat",
        "lon": "lon",
        "altitude": "fltLvl",
        "obs_time": "obsTime",
    }


def test_resolve_columns_handles_renames() -> None:
    df = pd.DataFrame(columns=["raw_text", "tb", "type", "actype", "latitude", "longitude", "flightLevel", "time"])
    cols = resolve_columns(df)
    assert cols["raw_text"] == "raw_text"
    assert cols["turbulence"] == "tb"
    assert cols["report_type"] == "type"


def test_resolve_columns_missing_returns_none() -> None:
    df = pd.DataFrame(columns=["rawOb"])
    cols = resolve_columns(df)
    assert cols["raw_text"] == "rawOb"
    assert cols["turbulence"] is None
    assert cols["lat"] is None


def test_first_cycle_inserts_all_rows(store: SqliteReportStore, synthetic_batch: pd.DataFrame) -> None:
    service = _service(store, synthetic_batch)
    result = service.run_once()
    assert result.status == "ok"
    assert result.rows_seen == 5
    assert result.rows_inserted == 5
    assert result.rows_skipped == 0
    assert result.rows_rejected == 0
    assert store.count() == 5


def test_second_identical_cycle_is_fully_deduped(store: SqliteReportStore, synthetic_batch: pd.DataFrame) -> None:
    service = _service(store, synthetic_batch)
    service.run_once()
    result = service.run_once()
    assert result.rows_inserted == 0
    assert result.rows_skipped == 5
    assert store.count() == 5


def test_partial_overlap(store: SqliteReportStore, synthetic_batch: pd.DataFrame) -> None:
    service = _service(store, synthetic_batch)
    service.run_once()
    # Second fetch: 2 rows already in the DB (first 2 of synthetic_batch) plus
    # 3 brand-new rows. Expected: 3 inserted, 2 skipped, store count = 8.
    new_rows = pd.DataFrame(
        [
            {
                "rawOb": "UA /OV OAK000 /TM 1500 /FL350 /TP B738 /TB MOD new report 6",
                "obsTime": "2026-08-22T17:26:00Z",
                "reportType": "PIREP",
                "acType": "B738",
                "lat": 37.6,
                "lon": -122.2,
                "fltLvl": 34000,
                "turbulence": "MOD",
            },
            {
                "rawOb": "UA /OV OAK001 /TM 1500 /FL350 /TP B738 /TB MOD new report 7",
                "obsTime": "2026-08-22T17:27:00Z",
                "reportType": "PIREP",
                "acType": "B738",
                "lat": 37.7,
                "lon": -122.3,
                "fltLvl": 33000,
                "turbulence": "MOD",
            },
            {
                "rawOb": "UA /OV OAK002 /TM 1500 /FL350 /TP B738 /TB MOD new report 8",
                "obsTime": "2026-08-22T17:28:00Z",
                "reportType": "PIREP",
                "acType": "B738",
                "lat": 37.8,
                "lon": -122.4,
                "fltLvl": 32000,
                "turbulence": "LGT",
            },
        ]
    )
    overlap = pd.concat(
        [synthetic_batch.iloc[:2].reset_index(drop=True), new_rows], ignore_index=True
    )
    service2 = _service(store, overlap)
    result = service2.run_once()
    assert result.rows_inserted == 3
    assert result.rows_skipped == 2
    assert result.rows_rejected == 0
    assert store.count() == 8


def test_no_data_cycle(store: SqliteReportStore) -> None:
    service = _service(store, None)
    result = service.run_once()
    assert result.status == "no_data"
    assert result.rows_seen == 0
    assert store.count() == 0


def test_invalid_lat_quarantined(store: SqliteReportStore) -> None:
    bad = pd.DataFrame([{"rawOb": "UA /OV SFO", "obsTime": "2026-08-22T17:00:00Z", "lat": 999.0, "lon": -122.0}])
    service = _service(store, bad)
    result = service.run_once()
    assert result.rows_rejected == 1
    assert result.rows_inserted == 0
    assert store.count() == 0


def test_sparse_row_is_accepted(store: SqliteReportStore) -> None:
    sparse = pd.DataFrame([{"rawOb": "UA /OV SFO", "obsTime": "2026-08-22T17:00:00Z"}])
    service = _service(store, sparse)
    result = service.run_once()
    assert result.rows_inserted == 1
    assert result.rows_rejected == 0
    assert store.count() == 1


def test_run_is_recorded_in_runs_table(store: SqliteReportStore, synthetic_batch: pd.DataFrame) -> None:
    service = _service(store, synthetic_batch)
    service.run_once()
    runs = store.last_runs(1)
    assert len(runs) == 1
    assert runs[0].status == "ok"
    assert runs[0].rows_inserted == 5
