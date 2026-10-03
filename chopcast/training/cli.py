"""CLI for the trainer.

Commands:
  baseline [--dataset PATH] [--register]   train the TF-IDF baseline
  split    [--dataset PATH]                show the split without training
  datasets                                 list available feature datasets

The CLI never raises ChopcastError to the user; it translates to a
one-line message and a non-zero exit code. Verbose mode shows the
traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NoReturn

import click

from chopcast.config import Settings
from chopcast.errors import ChopcastError
from chopcast.logging import configure as configure_logging
from chopcast.logging import get_logger
from chopcast.registry.store import SqliteModelRegistry
from chopcast.evaluation.report import to_markdown
from chopcast.training.class_weights import describe_imbalance
from chopcast.training.dataset import latest_dataset, load_dataset
from chopcast.training.split import make_split, save_split
from chopcast.training.baseline import train_baseline

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
    configure_logging(settings.logging, settings.to_paths().logs_dir_path / "training.log")
    return settings


def _fail(msg: str, exc: Exception | None = None, verbose: bool = False) -> NoReturn:
    click.echo(f"error: {msg}", err=True)
    if verbose and exc is not None:
        raise exc
    sys.exit(1)


def _resolve_dataset(settings: Settings, dataset: str | None) -> Path:
    """An explicit `--dataset` wins; otherwise take the newest built."""
    if dataset:
        return Path(dataset).expanduser().resolve()
    return latest_dataset(settings.to_paths().features_dir_path)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@click.group(name="chopcast-train", help="Train turbulence-severity models.")
def cli() -> None:
    pass


@cli.command("datasets", help="List feature datasets available to train on.")
@click.option("-v", "--verbose", is_flag=True)
def datasets(verbose: bool) -> None:
    settings = _build_settings(verbose)
    features_dir = settings.to_paths().features_dir_path
    found = sorted(features_dir.glob("features_*.jsonl")) if features_dir.exists() else []
    if not found:
        click.echo(f"no datasets in {features_dir} — run the feature build first")
        return
    for p in found:
        rows = sum(1 for line in p.open(encoding="utf-8") if line.strip())
        click.echo(f"{p.name}  {rows:,} rows  {p.stat().st_size / 1024:.0f} KB")


@cli.command("split", help="Show the train/test split without training.")
@click.option("--dataset", default=None, help="Path to a features_*.jsonl file.")
@click.option("-v", "--verbose", is_flag=True)
def split(dataset: str | None, verbose: bool) -> None:
    settings = _build_settings(verbose)
    try:
        path = _resolve_dataset(settings, dataset)
        data = load_dataset(path)
        manifest = make_split(
            data.hashes, data.labels, config=settings.training.default_split
        )
    except ChopcastError as e:
        _fail(str(e), e, verbose)

    click.echo(f"dataset      : {path.name}  ({len(data):,} rows)")
    click.echo(f"split version: {manifest.version}")
    click.echo(f"train / test : {len(manifest.train_hashes):,} / {len(manifest.test_hashes):,}")
    click.echo("")
    from collections import Counter

    train_counts = Counter(manifest.train_labels)
    test_counts = Counter(manifest.test_labels)
    click.echo(f"{'class':<12}{'train':>8}{'test':>8}")
    absent = []
    for label in sorted(set(data.labels)):
        tr, te = train_counts.get(label, 0), test_counts.get(label, 0)
        click.echo(f"{label:<12}{tr:>8,}{te:>8,}")
        if te == 0:
            absent.append(label)
    if absent:
        click.echo("")
        click.echo(
            "warning: absent from the test set, so their metrics are undefined "
            "rather than perfect: " + ", ".join(absent)
        )


@cli.command("baseline", help="Train the TF-IDF + LogReg baseline.")
@click.option("--dataset", default=None, help="Path to a features_*.jsonl file.")
@click.option("--register/--no-register", default=False, help="Record in the model registry.")
@click.option("-v", "--verbose", is_flag=True)
def baseline(dataset: str | None, register: bool, verbose: bool) -> None:
    settings = _build_settings(verbose)
    paths = settings.to_paths()
    try:
        path = _resolve_dataset(settings, dataset)
        data = load_dataset(path)
        model_version = f"baseline-{data.feature_version}"
        run = train_baseline(
            data.hashes,
            data.texts,
            data.labels,
            split_cfg=settings.training.default_split,
            text_cfg=settings.text,
            train_cfg=settings.training.baseline,
            labeling_cfg=settings.labeling,
            feature_version=data.feature_version,
            model_version=model_version,
        )
        paths.models_dir_path.mkdir(parents=True, exist_ok=True)
        artifact_path = paths.models_dir_path / model_version
        run.model.save(artifact_path)
        save_split(run.split, paths.models_dir_path / f"{model_version}.split.json")
        report_path = paths.models_dir_path / f"{model_version}.report.md"
        report_path.write_text(to_markdown(run.evaluation), encoding="utf-8")
    except ChopcastError as e:
        _fail(str(e), e, verbose)
    except Exception as e:  # noqa: BLE001 - surfaced, never swallowed
        _fail(f"training failed: {type(e).__name__}: {e}", e, verbose)

    imbalance = describe_imbalance(list(run.split.train_labels))
    floor = imbalance["majority_baseline_accuracy"]
    click.echo("")
    click.echo(f"  macro_f1                    {run.evaluation.macro:.4f}   <- headline")
    click.echo(f"  weighted_f1                 {run.evaluation.weighted:.4f}")
    click.echo(f"  accuracy                    {run.evaluation.acc:.4f}")
    click.echo(f"  majority_baseline_accuracy  {floor:.4f}")
    click.echo(f"  n_train / n_test            {run.split.n_train:,} / {run.split.n_test:,}")
    click.echo(f"  split_version               {run.split.version}")
    click.echo("")
    click.echo(f"  artifact  {artifact_path}")
    click.echo(f"  report    {report_path}")

    if run.evaluation.acc <= floor:
        click.echo("")
        click.echo(
            "  warning: accuracy does not beat the majority-class floor. "
            "Read macro-F1, not accuracy."
        )

    if register:
        registry = SqliteModelRegistry(paths.registry_db_path)
        try:
            model_id = registry.register(
                model_version=model_version,
                model_kind="baseline",
                feature_version=data.feature_version,
                metrics={
                    "macro_f1": run.evaluation.macro,
                    "weighted_f1": run.evaluation.weighted,
                    "accuracy": run.evaluation.acc,
                    "majority_baseline_accuracy": floor,
                    "n_test": run.split.n_test,
                },
                artifact_path=artifact_path,
                notes=f"split={run.split.version}",
            )
            click.echo(f"  registered as model id {model_id}")
        except Exception as e:  # noqa: BLE001
            _fail(f"could not register model: {e}", e, verbose)
        finally:
            registry.close()


def main() -> None:
    try:
        cli(obj={})
    except ChopcastError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
