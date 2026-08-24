# ADR-0001: Redesign from a clean package structure rather than extend the 3-file prototype

- **Status:** Accepted
- **Date:** 2026-08-22
- **Deciders:** musiimenta-joachim
- **Supersedes:** the implicit decision in the original `collector.py` / `explore.py` / `test_collector.py` layout.

## Context

The project started as three flat scripts: `explore.py` (schema discovery), `collector.py` (data collection), and `test_collector.py` (synthetic tests). It works. We have a running collector, a SQLite database, and tests. The scripts are readable and the logic is sound.

The roadmap in `docs/ROADMAP.md` requires:

- A second storage layer (model registry) with a different lifecycle from the data store.
- A versioned feature store and Parquet exports, not just SQLite.
- An inference API, a dashboard, a weather fusion module.
- A baseline and a transformer model that share a contract.
- Tests that are not just "synthetic data + asserts."

None of these fit cleanly into the current shape. Adding them on top of the current files means:

- `collector.py` grows from 350 lines to 1,200+ as it absorbs validation, dedup, retries, the registry, and the metrics sink.
- The `test_collector.py` synthetic harness has to be duplicated in every test file because the scripts do not expose the pieces as units.
- The boundary between "collector" and "everything else" disappears, because the collector will inevitably need to know about features and labels to write them out.

The current shape was right for "Phase 0 plus a first cut at Phase 1." It is wrong for "everything else."

## Decision

Replace the flat structure with the package layout in `docs/MODULE_DESIGN.md` §0. The M0 milestone in `docs/ROADMAP.md` is the migration point. The existing scripts become:

| Old | New |
|---|---|
| `collector.py` | `chopcast.collector.service` + `chopcast.collector.cli` |
| `explore.py` | `chopcast.explorer` (a one-shot CLI tool) |
| `test_collector.py` | `tests/unit/collector/*` + `tests/integration/collector/*` |

A migration script (`scripts/migrate_legacy_db.py`) ingests any existing `pireps.db` into the new schema. The migration is idempotent.

## Consequences

**Positive**

- Boundaries are visible in the package layout. `parser` cannot import from `api`. The lint test in `tests/lint/test_imports.py` enforces this.
- Each module is testable in isolation. The collector's `service` is testable with a mocked client and a temp DB.
- New components (transformer model, weather fusion, inference API) slot in without rearranging existing code.
- The M0 migration is a one-time cost. Once the package exists, future work is additive.

**Negative**

- A working collector must be touched to migrate. The M0 milestone is not a feature; it is a refactor. That is a real cost.
- The migration script must round-trip the existing `pireps.db` correctly. This is a small but real risk.
- Reviewers comparing the new collector to the old one will see more files, more configuration, and less obvious entry points.

**Mitigations**

- The migration script has its own test (`tests/integration/collector/test_migration.py`).
- `collector.py` is kept in the repo at M0 as `scripts/legacy/collector.py` until M1 is verified. It can be invoked as a fallback if the new collector fails.
- The new CLI commands match the old invocation flags where possible: `chopcast-collector once` and `chopcast-collector status` map 1:1 to the old `--once` and `--stats`.

## Alternatives considered

**Extend the existing scripts.** Rejected: the scripts grow past 1,000 lines and the boundary between "collector" and "everything else" becomes a heuristic, not a rule.

**Adopt an existing framework** (e.g., Hamilton, Metaflow, Flyte, Kedro). Rejected: the project is small enough that a framework adds more concepts than it removes, and none of them solve the *specific* problem we have (label leakage from a structured field that must be stripped before modeling). A bespoke design with a clear `Model` protocol is simpler to reason about than a framework with a DAG.

**Build the M0 structure lazily, as each component is needed.** Rejected: by the time we need a third component, two of them will have already pulled in a half-baked structure that the third has to match. Doing the package layout now means every later component is built against the same conventions.

## References

- `docs/ARCHITECTURE.md` §2.1
- `docs/MODULE_DESIGN.md` §0
- `docs/ROADMAP.md` M0
