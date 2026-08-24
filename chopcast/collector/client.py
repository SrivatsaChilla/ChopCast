"""HTTP client for the AWC aircraft reports cache.

Responsibilities:
- GET the gzipped CSV, with retries, timeouts, and exponential backoff.
- Decode the gzipped CSV into a pandas DataFrame.
- Treat 204 as "no data" (return None) and 429 as "rate limited" (back off).
- Never raise on transient errors; only raise after `max_retries` is exhausted.

See docs/MODULE_DESIGN.md §2.1.
"""

from __future__ import annotations

import gzip
import io
import time
from typing import Protocol, runtime_checkable

import pandas as pd
import requests

from chopcast.errors import HttpError, RateLimited
from chopcast.logging import get_logger

log = get_logger(__name__)


@runtime_checkable
class AwcClient(Protocol):
    """Anything that can fetch the AWC aircraft reports cache."""

    def fetch_aircraft_reports(self) -> pd.DataFrame | None: ...


class HttpAwcClient:
    """The default `AwcClient`. Talks HTTP to AWC.

    This class is intentionally synchronous; the collector is single-threaded
    and the request itself dominates the cycle time. Adding async would
    change the operational story (event loop, signal handling) without
    enough benefit.
    """

    def __init__(
        self,
        url: str,
        user_agent: str,
        timeout_seconds: int = 60,
        max_retries: int = 5,
        backoff_base_seconds: int = 5,
        max_backoff_seconds: int = 300,
    ) -> None:
        self._url = url
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._max_backoff = max_backoff_seconds

    def fetch_aircraft_reports(self) -> pd.DataFrame | None:
        delay = self._backoff_base
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = requests.get(
                    self._url,
                    headers={"User-Agent": self._user_agent},
                    timeout=self._timeout,
                )

                if resp.status_code == 204:
                    log.info("collector.fetch.no_content", url=self._url)
                    return None

                if resp.status_code == 429:
                    log.warning(
                        "collector.fetch.rate_limited",
                        attempt=attempt,
                        backoff=delay,
                    )
                    if attempt == self._max_retries:
                        raise RateLimited(
                            f"AWC returned 429 after {attempt} attempts",
                        )
                    time.sleep(delay)
                    delay = min(delay * 2, self._max_backoff)
                    continue

                if resp.status_code >= 500:
                    log.warning(
                        "collector.fetch.server_error",
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=delay,
                    )
                    if attempt == self._max_retries:
                        raise HttpError(
                            f"AWC returned {resp.status_code}",
                            status=resp.status_code,
                            url=self._url,
                        )
                    time.sleep(delay)
                    delay = min(delay * 2, self._max_backoff)
                    continue

                resp.raise_for_status()
                return self._decode(resp.content)

            except requests.RequestException as e:
                last_error = e
                log.warning(
                    "collector.fetch.network_error",
                    error=type(e).__name__,
                    detail=str(e),
                    attempt=attempt,
                    backoff=delay,
                )
                if attempt == self._max_retries:
                    raise HttpError(
                        f"Network failure after {attempt} attempts: {e}",
                        status=0,
                        url=self._url,
                    ) from e
                time.sleep(delay)
                delay = min(delay * 2, self._max_backoff)

        # Unreachable; the loop returns or raises.
        raise HttpError(
            f"Failed to fetch {self._url}: {last_error}",
            status=0,
            url=self._url,
        )

    @staticmethod
    def _decode(content: bytes) -> pd.DataFrame:
        with gzip.open(io.BytesIO(content), "rt", errors="replace", encoding="utf-8") as fh:
            return pd.read_csv(fh, low_memory=False, on_bad_lines="skip")


__all__ = ["AwcClient", "HttpAwcClient"]
