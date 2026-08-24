"""Tests for chopcast.collector.client.HttpAwcClient.

Uses `responses` to simulate AWC without any real network I/O.
"""

from __future__ import annotations

import gzip
from io import BytesIO

import pandas as pd
import pytest
import responses

from chopcast.collector.client import HttpAwcClient
from chopcast.errors import HttpError, RateLimited


def _gzipped_csv(text: str) -> bytes:
    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(text.encode("utf-8"))
    return buf.getvalue()


@responses.activate
def test_returns_dataframe_on_200() -> None:
    responses.add(
        responses.GET,
        "https://example.test/cache.csv.gz",
        body=_gzipped_csv("rawOb,obsTime,lat\nUA,2026-08-22T17:00:00Z,37.5\n"),
        status=200,
    )
    client = HttpAwcClient(
        url="https://example.test/cache.csv.gz",
        user_agent="test/1.0",
        max_retries=1,
        backoff_base_seconds=1,
    )
    df = client.fetch_aircraft_reports()
    assert df is not None
    assert len(df) == 1
    assert df.iloc[0]["rawOb"] == "UA"


@responses.activate
def test_returns_none_on_204() -> None:
    responses.add(
        responses.GET,
        "https://example.test/cache.csv.gz",
        status=204,
    )
    client = HttpAwcClient(
        url="https://example.test/cache.csv.gz",
        user_agent="test/1.0",
        max_retries=1,
    )
    assert client.fetch_aircraft_reports() is None


@responses.activate
def test_retries_on_429_then_succeeds() -> None:
    responses.add(
        responses.GET,
        "https://example.test/cache.csv.gz",
        status=429,
    )
    responses.add(
        responses.GET,
        "https://example.test/cache.csv.gz",
        body=_gzipped_csv("rawOb\nUA\n"),
        status=200,
    )
    client = HttpAwcClient(
        url="https://example.test/cache.csv.gz",
        user_agent="test/1.0",
        max_retries=3,
        backoff_base_seconds=1,
        max_backoff_seconds=2,
    )
    df = client.fetch_aircraft_reports()
    assert df is not None


@responses.activate
def test_raises_rate_limited_after_exhausting_retries() -> None:
    for _ in range(3):
        responses.add(
            responses.GET,
            "https://example.test/cache.csv.gz",
            status=429,
        )
    client = HttpAwcClient(
        url="https://example.test/cache.csv.gz",
        user_agent="test/1.0",
        max_retries=3,
        backoff_base_seconds=1,
        max_backoff_seconds=1,
    )
    with pytest.raises(RateLimited):
        client.fetch_aircraft_reports()


@responses.activate
def test_raises_http_error_after_server_errors() -> None:
    for _ in range(3):
        responses.add(
            responses.GET,
            "https://example.test/cache.csv.gz",
            status=503,
        )
    client = HttpAwcClient(
        url="https://example.test/cache.csv.gz",
        user_agent="test/1.0",
        max_retries=3,
        backoff_base_seconds=1,
        max_backoff_seconds=1,
    )
    with pytest.raises(HttpError) as e:
        client.fetch_aircraft_reports()
    assert e.value.status == 503
    assert e.value.url == "https://example.test/cache.csv.gz"
