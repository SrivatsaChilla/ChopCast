"""`chopcast-train` CLI.

Commands:
- `run` — end-to-end: load a feature dataset, split, train, evaluate,
  register, and optionally promote.
- `list` — show registered models.
- `promote` — promote a registered model to a tag (default: production).
- `compare` — side-by-side report between two registered model IDs.

The CLI is intentionally thin — it just wires the library together
and surfaces the standard knobs. No business logic lives here.

See `docs/MODULE_DESIGN.md` §8.3.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from chopcast.config import Settings
from chopcast.evaluation.report import to_markdown
from chopcast.logging import configure, get_logger
from chopcast.registry.store import SqliteModelRegistry
from chopcast.training.split import save_split


log = get_logger(__name__)


def _load_features(path: Path) -> tuple[list[str], list[str], list[str]]:
    """Load a versioned JSONL feature file. Returns (hashes, texts, labels)."""
    hashes: list[str] = []
    texts: list[str] = []
    labels: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        hashes.append(rec["hash"])
        texts.append(rec["clean_text"])
        labels.append(rec["severity_label"])
    return hashes, texts, labels


@click.group()
@click.option("--profile", default=None, help="Config profile (dev|prod|ci)")
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
)
def main(profile: str | None, log_level: str) -> None:
    """Train and register ChopCast models."""
    settings = Settings.load(profile=profile)
    configure(settings.logging, log_file_path=settings.to_paths().logs_dir_path / "train.log")
    log.debug("cli.train.started", profile=profile, level=log_level)


@main.command()
@click.option(
    "--features",
    "features_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--model-version", required=True)
@click.option(
    "--kind",
    "model_kind",
    default="baseline",
    type=click.Choice(["baseline", "transformer"]),
    help="Which trainer to use. 'baseline' is TF-IDF + LogReg/SVM; "
    "'transformer' is DistilBERT fine-tuning (requires torch+transformers).",
)
@click.option("--promote/--no-promote", default=False)
@click.option("--tag", default="production")
def run(
    features_path: Path,
    model_version: str,
    model_kind: str,
    promote: bool,
    tag: str,
) -> None:
    """Train a model on `features_path` and register it."""
    settings = Settings.load()
    cfg = settings
    paths = settings.to_paths()
    paths.ensure_dirs()

    log.info("cli.train.loading_features", path=str(features_path))
    hashes, texts, labels = _load_features(features_path)
    log.info("cli.train.dataset_size", n=len(hashes))

    if model_kind == "baseline":
        from chopcast.training.baseline import train_baseline

        run_result = train_baseline(
            hashes,
            texts,
            labels,
            split_cfg=cfg.split,
            text_cfg=cfg.text,
            train_cfg=cfg.training.baseline,
            labeling_cfg=cfg.labeling,
            feature_version=features_path.stem,
            model_version=model_version,
        )
    else:
        from chopcast.training.transformer_trainer import train_transformer

        run_result = train_transformer(
            hashes,
            texts,
            labels,
            split_cfg=cfg.split,
            text_cfg=cfg.text.transformer,
            train_cfg=cfg.training.transformer,
            labeling_cfg=cfg.labeling,
            feature_version=features_path.stem,
            model_version=model_version,
            output_dir=str(
                paths.models_dir_path
                / f"{model_version}_{features_path.stem}_transformer"
            ),
        )

    # Persist the model artefact.
    artefact_dir = paths.models_dir_path / f"{model_version}_{run_result.evaluation.feature_version}"
    run_result.model.save(artefact_dir)
    log.info("cli.train.artefact_saved", path=str(artefact_dir))

    # Persist the split manifest next to the artefact.
    save_split(run_result.split, artefact_dir / "split.json")

    # Render the report and write it as Markdown + JSON.
    report_md = to_markdown(run_result.evaluation)
    (artefact_dir / "report.md").write_text(report_md, encoding="utf-8")
    (artefact_dir / "report.json").write_text(
        json.dumps(run_result.evaluation.to_dict(), indent=2),
        encoding="utf-8",
    )

    # Register the model.
    reg = SqliteModelRegistry(paths.registry_db_path)
    try:
        model_id = reg.register(
            model_version=model_version,
            model_kind=model_kind,
            feature_version=run_result.evaluation.feature_version,
            metrics=run_result.evaluation.to_dict(),
            artifact_path=artefact_dir,
        )
        if promote:
            reg.promote(model_id, tag=tag)
        click.echo(
            f"registered model id={model_id} kind={model_kind} version={model_version}"
        )
        click.echo(
            f"macro_f1={run_result.evaluation.macro:.4f} "
            f"weighted_f1={run_result.evaluation.weighted:.4f} "
            f"acc={run_result.evaluation.acc:.4f}"
        )
    finally:
        reg.close()


@main.command(name="list")
def list_cmd() -> None:
    """List registered models."""
    settings = Settings.load()
    paths = settings.to_paths()
    paths.ensure_dirs()
    reg = SqliteModelRegistry(paths.registry_db_path)
    try:
        rows = reg.list()
        for r in rows:
            click.echo(
                f"id={r.id:3d} kind={r.model_kind:10} "
                f"version={r.model_version:8} feature={r.feature_version}"
            )
    finally:
        reg.close()


@main.command()
@click.argument("model_id", type=int)
@click.option("--tag", default="production")
def promote(model_id: int, tag: str) -> None:
    """Promote MODEL_ID to TAG (default: production)."""
    settings = Settings.load()
    paths = settings.to_paths()
    paths.ensure_dirs()
    reg = SqliteModelRegistry(paths.registry_db_path)
    try:
        reg.promote(model_id, tag=tag)
        click.echo(f"promoted model_id={model_id} tag={tag}")
    finally:
        reg.close()


@main.command()
@click.argument("model_id_a", type=int)
@click.argument("model_id_b", type=int)
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional path to write the Markdown comparison report to. "
    "The summary is always printed to stdout.",
)
@click.option(
    "--allow-mismatched-features",
    is_flag=True,
    default=False,
    help="Permit comparison of models trained on different feature versions. "
    "Off by default because that's almost always a mistake.",
)
def compare(
    model_id_a: int,
    model_id_b: int,
    output_path: Path | None,
    allow_mismatched_features: bool,
) -> None:
    """Compare MODEL_ID_A against MODEL_ID_B and report deltas."""
    from chopcast.evaluation.compare import compare as compare_records, to_markdown

    settings = Settings.load()
    paths = settings.to_paths()
    paths.ensure_dirs()
    reg = SqliteModelRegistry(paths.registry_db_path)
    try:
        a = reg.get(model_id_a)
        b = reg.get(model_id_b)
        if a is None:
            raise click.ClickException(f"no model with id={model_id_a}")
        if b is None:
            raise click.ClickException(f"no model with id={model_id_b}")
        report = compare_records(
            a,
            b,
            feature_version_must_match=not allow_mismatched_features,
        )
        md = to_markdown(report)
        click.echo(md)
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(md, encoding="utf-8")
            click.echo(f"wrote comparison to {output_path}")
    finally:
        reg.close()


if __name__ == "__main__":
    main()