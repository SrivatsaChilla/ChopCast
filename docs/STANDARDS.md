# Coding Standards

> Authoritative for style and structure. Lint rules are mechanical; the principles behind them are not. Read this once; consult it often.

---

## 1. Language and runtime

- **Python 3.11+.** We use `match` statements, `tomllib`, and `Self` from `typing`.
- **Type hints everywhere.** Every public function has parameter and return type annotations. `Any` is allowed only at the boundary of a third-party library that lacks types.
- **No `from __future__ import annotations`** is needed on 3.11+; the runtime handles PEP 604 unions natively. We do still write `from __future__ import annotations` to make tools faster.
- **No implicit re-exports.** A `from chopcast.x import y` only works if `y` is in `__all__` of `chopcast.x`. This prevents accidental public surface.

---

## 2. Type system

### 2.1 Pydantic for data crossing module boundaries

Anything that crosses a module boundary and represents structured data is a Pydantic `BaseModel` or a frozen dataclass. Pydantic for data that originates from outside the system (config, API requests, raw rows from disk). Frozen dataclasses for internal data with no validation needs.

### 2.2 Protocols for abstractions

Every interface between major subsystems is a `typing.Protocol` with `@runtime_checkable`. The interface is owned by the consumer, not the producer (dependency inversion).

```python
# owned by the consumer
class Model(Protocol):
    def predict(self, X: list[str]) -> np.ndarray: ...
```

The producer (`BaselineSklearn`) implements the protocol structurally — no `implements Model` declaration. This keeps the producer decoupled and prevents accidental coupling to a particular interface version.

### 2.3 `mypy` strict

`pyproject.toml` configures `mypy --strict`. Every PR must pass `mypy chopcast`. Exceptions require a `# type: ignore[code]` with a reason comment.

### 2.4 No `Any` in public APIs

Public functions take and return typed values. `Any` is a sign of untyped design. If you find yourself reaching for `Any`, redesign the function.

---

## 3. SOLID, applied

### 3.1 Single responsibility

A module has one reason to change. `chopcast.collector.client` changes if AWC's protocol changes; it does not change if our database schema changes. Splitting along this line makes migrations cheap.

### 3.2 Open/closed

Adding a new weather provider should not modify `chopcast.weather.matcher`. The matcher accepts a `MetarProvider` protocol; a new provider implements the protocol. The `weather` package's `__init__.py` is the only place that names concrete providers.

### 3.3 Liskov substitution

`BaselineSklearn` and `TransformerDistilBERT` are both `Model`. Anywhere a `Model` is accepted, either can be substituted. The system has tests that prove this with a stub `Model`.

### 3.4 Interface segregation

The `Model` protocol has only the methods that the API needs. The `Predictor` does not see `train()` or `save()`; those belong to the trainer. If a future model needs additional methods (e.g., `explain()`), they go into a separate `ExplainableModel` protocol that extends `Model`.

### 3.5 Dependency inversion

High-level modules (`chopcast.inference`) depend on abstractions (`Model`, `Registry`). They do not depend on concrete implementations (`BaselineSklearn`, `SqliteRegistry`). The `container.py` module at the top of the package wires concrete implementations to abstractions. Swapping an implementation is one line in `container.py`.

```python
# chopcast/container.py
def build_predictor(settings: Settings) -> Predictor:
    registry = SqliteRegistry(settings.paths.registry_db)
    return Predictor(registry, model_id=settings.api.model_id)
```

Tests build their own `container_test.py` with mocks.

---

## 4. Naming

| Thing | Convention | Example |
|---|---|---|
| Modules | lowercase, snake_case | `chopcast/collector/hasher.py` |
| Classes | PascalCase | `DefaultRowValidator` |
| Functions and methods | snake_case, verb-led | `compute_hash`, `parse_pirep` |
| Variables | snake_case | `report_count` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRIES` |
| Type variables | PascalCase, descriptive | `ModelT = TypeVar("ModelT", bound=Model)` |
| Protocols | noun describing capability | `Model`, `MetarProvider` |
| Exceptions | `<What>Error` | `LeakageError` |
| Test functions | `test_<thing>_<condition>_<expected>` | `test_hasher_with_missing_lat_returns_stable_hash` |
| Files with side effects | `_run_*.py` | `_run_migrations.py` |
| Private functions | leading underscore | `_clean_value` |

A function name should describe what it returns, not how it computes it. `report_hash(...)` not `sha256_concat_with_pipe(...)`.

---

## 5. Functions

- **Length:** aim for under 30 lines. A function longer than that is doing too many things.
- **Arguments:** aim for under 5. If you need more, group them into a dataclass.
- **Side effects:** pure functions are preferred. Side effects (I/O, network, time) are isolated at the module boundary.
- **Return values:** be explicit. `-> None` for procedures, `-> str` for functions. Avoid returning `Optional` when returning a sentinel is clearer; conversely, prefer `Optional` over sentinel values for "absent."

### 5.1 No mutable default arguments

```python
def f(items: list[int] = []) -> list[int]:  # WRONG
    items.append(1)
    return items
```

The Python default-argument trap. Use `None` and create a new list inside:

```python
def f(items: list[int] | None = None) -> list[int]:
    items = items or []
    items.append(1)
    return items
```

### 5.2 No bare `except`

```python
try:
    ...
except Exception:  # WRONG
    ...
```

Catch specific exceptions. Catch `Exception` only at the top of a CLI or service entry point, with a log of the traceback.

---

## 6. Imports

```python
# 1. Standard library
import json
from collections.abc import Callable
from pathlib import Path

# 2. Third-party
import pandas as pd
import requests

# 3. First-party
from chopcast.config import Settings
from chopcast.errors import ValidationError
```

`ruff` enforces this order. `from chopcast import x` is preferred over `import chopcast.x` because it makes the dependency visible at the call site.

No `import *`. No relative imports (`from .x import y`); always use the absolute path so refactoring is safe.

---

## 7. Error handling

### 7.1 Raise, don't return error codes

A function returns its result or raises. It does not return `(result, error)`. The caller does not need to remember to check.

### 7.2 Use the project exception hierarchy

Raise `chopcast.errors.ChopcastError` subclasses. Never raise bare `Exception` or a stdlib exception for project-specific errors.

### 7.3 Translate at the boundary

The CLI catches `ChopcastError` and prints a one-line message. Library code does not catch; it lets exceptions propagate. The framework boundary (e.g., the FastAPI app) has exception handlers that map `ChopcastError` subclasses to HTTP status codes.

### 7.4 Log with context

A caught exception is logged with `log.exception(...)` (which includes the traceback) and enough context to diagnose. `log.error("failed to fetch %s: %s", url, e)` is not enough; the traceback is.

---

## 8. Logging

- `log = get_logger(__name__)` at the top of every module.
- Log messages are full sentences.
- Use `%s` formatting, not f-strings, so the log site is cheap when the level is filtered.
- Never log raw PIREP text at INFO. The text may contain identifying information. DEBUG is acceptable, with a log-volume warning in the docs.
- Never log API keys, even in error paths.

---

## 9. Configuration

- Read settings from `Settings`, never from `os.environ`.
- Read paths from `Paths`, never from a literal `Path("data/...")`.
- Module-level constants are allowed only for *non-behavioral* values: type names, magic numbers that are part of an algorithm, regex patterns that are part of a parser's grammar.

---

## 10. Concurrency

- The collector is single-threaded. SQLite WAL mode supports one writer and many readers; we do not need threading for write throughput.
- The API is multi-worker via uvicorn. Workers do not share state; the model is loaded per worker.
- Long-running computations (e.g., transformer training) run in subprocesses via `subprocess.run` or in dedicated training jobs, not in the API process.

---

## 11. Time

- All timestamps are `datetime` with `tzinfo=timezone.utc`.
- Never use `datetime.now()` without a timezone; use `datetime.now(timezone.utc)`.
- Never compare naive and aware datetimes. Pydantic models reject naive datetimes at the boundary.

---

## 12. Code review etiquette

- Review the diff, not the file. The whole file may be a mess, but the diff is what you're approving.
- Distinguish blocking comments (`This will cause...`) from non-blocking (`nit: ...`).
- Approve with comments. Don't withhold approval over a nit; let the author decide.
- If you disagree with a design, raise it in an issue, not a PR comment. PRs are for the specific change, not the architecture.

---

## 13. Tooling

| Tool | Purpose | Config |
|---|---|---|
| `ruff` | Lint + format | `pyproject.toml [tool.ruff]` |
| `mypy` | Type check | `pyproject.toml [tool.mypy]` |
| `pytest` | Test runner | `pyproject.toml [tool.pytest]` |
| `pre-commit` | Pre-commit hooks | `.pre-commit-config.yaml` |
| `coverage` | Coverage measurement | `pyproject.toml [tool.coverage]` |
| `mkdocs` | Docs site (later) | `mkdocs.yml` |

### 13.1 `pyproject.toml` highlights

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "PT", "RUF"]
ignore = ["E501"]  # line-length handled by formatter

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B011"]  # asserts are fine

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["integration: integration tests"]
addopts = "-m 'not integration'"

[tool.coverage.run]
source = ["chopcast"]
omit = ["tests/*", "scripts/*"]

[tool.coverage.report]
fail_under = 80
```

---

## 14. Anti-patterns

These are explicitly rejected in code review:

| Anti-pattern | Why | Replacement |
|---|---|---|
| `from typing import Any, cast` to silence mypy | Hides real type errors | Redesign the function |
| `try / except: pass` | Hides bugs | Log and re-raise, or handle explicitly |
| `if x is None: return None` chains | "Pyramid of doom" | Pattern matching, or refactor |
| Module-level `print` calls | Pollutes output | `log.info(...)` |
| Hardcoded URLs, paths, or thresholds | Breaks on environment change | `Settings` |
| `pytest.skip` without a reason | Hides test gaps | `pytest.skip(reason="...")` |
| `from chopcast import *` | Pollutes namespace | Explicit imports |
| Commented-out code in commits | Git remembers | Delete it; the history has it |
| `TODO` without an owner | Never gets done | `TODO(@username): ...` or an issue link |
