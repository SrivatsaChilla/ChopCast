"""Top-level `chopcast` CLI.

Subcommands:
  config show [--section X]    print the effective config
  config validate              check the config and exit
  paths                        print the resolved paths
"""

from __future__ import annotations

import sys
from typing import Any, NoReturn

import click
import yaml

from chopcast.config import Settings
from chopcast.errors import ChopcastError, ConfigError
from chopcast.logging import configure as configure_logging


@click.group(name="chopcast", help="ChopCast root CLI.")
def root() -> None:
    """Top-level group."""


@root.group(name="config", help="Inspect and validate configuration.")
def config_group() -> None:
    """Configuration subcommands."""


@config_group.command("show", help="Print the effective configuration.")
@click.option("--section", default=None, help="Show only this top-level section.")
def config_show(section: str | None) -> None:
    try:
        settings = Settings.load()
    except ConfigError as e:
        click.echo(f"config error: {e}", err=True)
        sys.exit(2)

    data: dict[str, Any] = settings.model_dump(mode="json")
    if section is not None:
        if section not in data:
            click.echo(f"unknown section: {section}", err=True)
            click.echo(f"available: {', '.join(sorted(data))}", err=True)
            sys.exit(2)
        data = {section: data[section]}
    click.echo(yaml.safe_dump(data, sort_keys=False).rstrip())


@config_group.command("validate", help="Validate the configuration and exit.")
def config_validate() -> None:
    try:
        Settings.load()
    except ConfigError as e:
        click.echo(f"invalid: {e}", err=True)
        sys.exit(1)
    click.echo("configuration is valid")


@root.command("paths", help="Print the resolved filesystem paths.")
def paths() -> None:
    try:
        settings = Settings.load()
        configure_logging(settings.logging)
    except ConfigError as e:
        click.echo(f"config error: {e}", err=True)
        sys.exit(2)
    p = settings.to_paths()
    rows = [
        ("root", p.root_path),
        ("raw_db", p.raw_db_path),
        ("raw_dir", p.raw_dir_path),
        ("processed_dir", p.processed_dir_path),
        ("features_dir", p.features_dir_path),
        ("models_dir", p.models_dir_path),
        ("registry_db", p.registry_db_path),
        ("runs_dir", p.runs_dir_path),
        ("logs_dir", p.logs_dir_path),
        ("backups_dir", p.backups_dir_path),
    ]
    width = max(len(name) for name, _ in rows)
    for name, path in rows:
        exists = "ok" if path.exists() else "missing"
        click.echo(f"  {name:<{width}}  {str(path):<60}  [{exists}]")


def main() -> NoReturn:
    try:
        root(obj={})
    except ChopcastError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
