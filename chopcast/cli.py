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


@root.command("map", help="Generate a geospatial map of turbulence reports.")
@click.option("--model", type=int, default=None, help="Use predictions from this model ID instead of ground truth.")
@click.option("--output", type=click.Path(), default="turbulence_map.html", help="Output HTML file path.")
@click.option("--profile", default=None, help="Configuration profile to use.")
def map_reports(model: int | None, output: str, profile: str | None) -> None:
    try:
        settings = Settings.load(profile)
        configure_logging(settings.logging)
    except ConfigError as e:
        click.echo(f"config error: {e}", err=True)
        sys.exit(2)

    from chopcast.map.folium_app import generate_map
    from chopcast.registry.store import SqliteModelRegistry

    registry = SqliteModelRegistry(settings.to_paths().registry_db_path)
    try:
        out_path = generate_map(settings, registry, model_id=model, output_path=Path(output))
        click.echo(f"map successfully generated at: {out_path}")
    except Exception as e:
        click.echo(f"mapping failed: {e}", err=True)
        sys.exit(1)
    finally:
        registry.close()

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


@root.group(name="train", help="Model training and experimentation.")
def train_group() -> None:
    """Training subcommands."""


@train_group.command("run", help="Train a new model version.")
@click.option("--version", required=True, help="Version string for the new model (e.g. v1).")
@click.option("--profile", default=None, help="Configuration profile to use.")
def train_run(version: str, profile: str | None) -> None:
    try:
        settings = Settings.load(profile)
        configure_logging(settings.logging)
    except ConfigError as e:
        click.echo(f"config error: {e}", err=True)
        sys.exit(2)

    from chopcast.training.orchestrator import run_training
    try:
        model_id = run_training(settings, version)
        click.echo(f"successfully trained and registered model {model_id}")
    except ChopcastError as e:
        click.echo(f"training error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"unexpected training failure: {e}", err=True)
        sys.exit(1)
@root.group(name="eval", help="Model evaluation and comparison.")
def eval_group() -> None:
    """Evaluation subcommands."""


@eval_group.command("compare", help="Compare two model versions side-by-side.")
@click.argument("id_a", type=int)
@click.argument("id_b", type=int)
@click.option("--profile", default=None, help="Configuration profile to use.")
def eval_compare(id_a: int, id_b: int, profile: str | None) -> None:
    try:
        settings = Settings.load(profile)
        configure_logging(settings.logging)
    except ConfigError as e:
        click.echo(f"config error: {e}", err=True)
        sys.exit(2)

    from chopcast.evaluation.orchestrator import compare_models
    from chopcast.registry.store import SqliteModelRegistry

    registry = SqliteModelRegistry(settings.to_paths().registry_db_path)
    try:
        report = compare_models(settings, registry, id_a, id_b)
        click.echo(report)
    except ChopcastError as e:
        click.echo(f"evaluation error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"unexpected evaluation failure: {e}", err=True)
        sys.exit(1)
    finally:
        registry.close()

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
