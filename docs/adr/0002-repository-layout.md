# ADR-0002: Repository layout — code, configs, data, models, tests, docs

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

The project needs to be runnable in three modes: as a Python library (importable), as a CLI (operational), and as a research workspace (notebooks, exploratory analysis). The same code must support all three. Configuration, data, and model artifacts have very different lifecycles, and conflating them is what gets research codebases into trouble.

## Decision

The repository top-level is laid out as follows:

```
chopcast/         source code
configs/          YAML configuration
data/             versioned datasets (DVC-tracked, gitignored)
models/           model registry (gitignored except for manifest)
tests/            tests
docs/             documentation
notebooks/        exploratory analysis (not used to ship models)
scripts/          operational scripts (backup, migration)
pyproject.toml    package definition
.env.example      template for local secrets
.gitignore
README.md
CLAUDE.md
```

The rules:

- **Source code lives in `chopcast/`.** Nothing else in the repo is importable as `chopcast.*`. Notebooks reference the package by path or by an editable install.
- **Configuration lives in `configs/`.** No YAML in `chopcast/`. No environment variable reads in `chopcast/`.
- **Data is gitignored.** Raw SQLite is local-only. Parquet is DVC-tracked. Snapshot CSVs are gitignored after a one-time commit.
- **Models are gitignored.** The registry SQLite is local. Model artifacts are produced by the trainer; they live in `models/registry/`. Only the registry's `manifest.json` (a list of model versions, their metrics, and their code commit) is committed.
- **Tests mirror the source layout.** `tests/unit/<module>/test_<thing>.py`.
- **Documentation lives in `docs/`.** This is the architectural home. `README.md` is a thin entry point.

## Consequences

**Positive**

- It is obvious where a new file goes. New collector code? `chopcast/collector/`. New collector test? `tests/unit/collector/`. New config? `configs/`. The convention is mechanical.
- `.gitignore` rules are simple: ignore everything under `data/`, `models/registry/*`, `*.log`, and `.env`.
- The boundary between "things you commit" (code, configs, docs) and "things you do not" (data, models, secrets) is clear.

**Negative**

- The `models/` directory is largely empty in version control. New contributors may not realize that `models/registry/` exists. We mitigate with a `models/README.md` that explains the layout.
- Notebooks in `notebooks/` and code in `chopcast/` can drift in style. We mitigate with a lint rule that excludes `notebooks/` from `ruff` but includes a `pre-commit` notebook-clean step.

**Mitigations**

- A `make` target (or a `scripts/check_layout.sh`) verifies the layout invariants: every test file has a corresponding source file, every config has a `default:` section, etc.
- `models/README.md` documents the registry layout and how to load a model.

## Alternatives considered

**Single `src/` layout.** Rejected: the project is small enough that a flat package directory is more discoverable. The `src/` layout is more useful when there are many top-level Python packages and you want to enforce that they are not importable from the repo root.

**Co-locate tests with source** (`chopcast/parser/test_pirep.py`). Rejected: makes the package larger than necessary, complicates distribution, and makes it harder to run tests with `pytest` from the project root. We follow the standard `tests/` convention.

**Keep data in version control.** Rejected: PIREP data accrues daily. A 50,000-row Parquet file is small, but ten versions of it is 500 MB. DVC gives us content-addressed storage without forcing the data into git.

## References

- `docs/ARCHITECTURE.md` §5
- `docs/MODULE_DESIGN.md` §0
