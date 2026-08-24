"""CLI for the collector.

Commands:
  once                  single collection cycle
  run                   continuous loop
  status                show last runs, accrual rate, dedup rate
  rejected [--reason X] inspect quarantined rows
  migrate-legacy <path> ingest an old-format pireps.db (M0 migration)

The CLI never raises ChopcastError to the user; it translates to a one-line
message and a non-zero exit code. Verbose mode shows the traceback.
"""

from __future__ import annotations

import signal
import sqlite3
import sys
import time
from pathlib import Path
from typing import NoReturn

import click

from chopcast.collector.client import HttpAwcClient
from chopcast.collector.service import DefaultCollectionService
from chopcast.config import Settings
from chopcast.errors import ChopcastError
from chopcast.logging import configure as configure_logging
from chopcast.logging import get_logger
from chopcast.paths import Paths
from chopcast.storage.schema import SqliteReportStore

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_settings(verbose: bool) -> Settings:
    try:
        settings = Settings.load()
    except ChopcastError as e:
        click.echo(f"config error: {e}", err=True)
        sys.exit(2)
    configure_logging(settings.logging, settings.to_paths().logs_dir_path / "collector.log")
    if verbose:
        log.debug("collector.cli.started", profile=settings.paths.root)
    return settings


def _build_service(settings: Settings) -> tuple[DefaultCollectionService, SqliteReportStore]:
    paths = settings.to_paths()
    paths.ensure_dirs()
    store = SqliteReportStore(paths.raw_db_path, journal_mode=settings.database.journal_mode)
    client = HttpAwcClient(
        url=settings.collector.source_url,
        user_agent=settings.collector.user_agent,
        timeout_seconds=settings.collector.request_timeout_seconds,
        max_retries=settings.collector.max_retries,
        backoff_base_seconds=settings.collector.backoff_base_seconds,
        max_backoff_seconds=settings.collector.max_backoff_seconds,
    )
    service = DefaultCollectionService(
        client=client,
        store=store,
        config=settings.collector,
    )
    return service, store


def _fail(msg: str, exc: Exception | None = None, verbose: bool = False) -> NoReturn:
    if verbose and exc is not None:
        click.echo(f"error: {msg}: {type(exc).__name__}: {exc}", err=True)
        raise SystemExit(1)
    click.echo(f"error: {msg}", err=True)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
@click.group(name="chopcast-collector", help="Collect PIREPs from the AWC cache.")
@click.option("-v", "--verbose", is_flag=True, help="Show tracebacks on error.")
def cli(verbose: bool) -> None:
    """Top-level group."""


@cli.command("once", help="Run a single collection cycle and exit.")
@click.option("-v", "--verbose", is_flag=True, help="Show tracebacks on error.")
def once(verbose: bool) -> None:
    settings = _build_settings(verbose)
    service, store = _build_service(settings)
    try:
        result = service.run_once()
    except ChopcastError as e:
        store.close()
        _fail(str(e), e, verbose)
    store.close()
    click.echo(
        f"status={result.status} seen={result.rows_seen} "
        f"inserted={result.rows_inserted} skipped={result.rows_skipped} "
        f"rejected={result.rows_rejected}"
    )


@cli.command("run", help="Run the collector continuously.")
@click.option("-v", "--verbose", is_flag=True, help="Show tracebacks on error.")
def run(verbose: bool) -> None:
    settings = _build_settings(verbose)
    service, store = _build_service(settings)

    shutdown = False

    def _handle(signum: int, _frame: object) -> None:
        nonlocal shutdown
        log.info("collector.cli.signal", signum=signum)
        shutdown = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    log.info("collector.cli.started", poll_seconds=settings.collector.poll_seconds)
    try:
        while not shutdown:
            try:
                result = service.run_once()
                click.echo(
                    f"[{result.status}] seen={result.rows_seen} "
                    f"new={result.rows_inserted} dup={result.rows_skipped} "
                    f"rejected={result.rows_rejected}"
                )
            except ChopcastError as e:
                log.error("collector.cycle.exception", error=str(e))
            for _ in range(settings.collector.poll_seconds):
                if shutdown:
                    break
                time.sleep(1)
    finally:
        store.close()
        log.info("collector.cli.stopped")


@cli.command("status", help="Show the last 10 runs and overall counts.")
@click.option("-v", "--verbose", is_flag=True, help="Show tracebacks on error.")
def status(verbose: bool) -> None:
    settings = _build_settings(verbose)
    paths = settings.to_paths()
    store = SqliteReportStore(paths.raw_db_path, journal_mode=settings.database.journal_mode)
    try:
        total = store.count()
        click.echo(f"total reports stored: {total:,}")
        if total:
            click.echo("\nlast 10 runs:")
            click.echo(f"  {'started_at':<25} {'status':<12} {'seen':>6} {'new':>6} {'dup':>6} {'rej':>6}")
            for r in store.last_runs(10):
                click.echo(
                    f"  {r.started_at[:19]:<25} {r.status:<12} "
                    f"{(r.rows_seen or 0):>6} {(r.rows_inserted or 0):>6} "
                    f"{(r.rows_skipped or 0):>6} {(r.rows_rejected or 0):>6}"
                )
    finally:
        store.close()


@cli.command("rejected", help="Inspect quarantined rows.")
@click.option("--reason", default=None, help="Filter by reason (e.g., invalid_lat).")
@click.option("--limit", default=20, show_default=True, type=int, help="Max rows to show.")
@click.option("-v", "--verbose", is_flag=True, help="Show tracebacks on error.")
def rejected(reason: str | None, limit: int, verbose: bool) -> None:
    settings = _build_settings(verbose)
    paths = settings.to_paths()
    conn = sqlite3.connect(paths.raw_db_path)
    conn.row_factory = sqlite3.Row
    try:
        if reason:
            rows = conn.execute(
                "SELECT id, fetched_at, reason, detail FROM rejected "
                "WHERE reason = ? ORDER BY id DESC LIMIT ?",
                (reason, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, fetched_at, reason, detail FROM rejected "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        if not rows:
            click.echo("no rejected rows" + (f" with reason={reason}" if reason else ""))
            return
        click.echo(f"  {'id':>6}  {'fetched_at':<25}  {'reason':<24}  detail")
        for r in rows:
            click.echo(
                f"  {r['id']:>6}  {r['fetched_at'][:19]:<25}  "
                f"{r['reason']:<24}  {(r['detail'] or '')[:60]}"
            )
    finally:
        conn.close()


@cli.command("migrate-legacy", help="Ingest an old-format pireps.db.")
@click.argument("legacy_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-v", "--verbose", is_flag=True, help="Show tracebacks on error.")
def migrate_legacy(legacy_path: Path, verbose: bool) -> None:
    """Migrate the existing `collector.py`-era pireps.db into the new schema.

    Idempotent: re-running inserts zero new rows. See scripts/migrate_legacy_db.py
    for the implementation; this is a thin wrapper.
    """
    from scripts.migrate_legacy_db import migrate  # local import: keeps top-level imports lean

    settings = _build_settings(verbose)
    paths = settings.to_paths()
    paths.ensure_dirs()
    try:
        inserted, skipped = migrate(legacy_path, paths)
    except ChopcastError as e:
        _fail(str(e), e, verbose)
    click.echo(f"migration complete: inserted={inserted} skipped={skipped}")


def main() -> NoReturn:
    try:
        cli(obj={})
    except ChopcastError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
