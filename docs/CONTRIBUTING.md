# Contributing

> How to work on ChopCast. Read this before your first PR.

---

## 1. Setup

```bash
git clone <repo>
cd chopcast
python -m venv .venv
source .venv/bin/activate          # or: .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pre-commit install
cp .env.example .env
# edit .env to set CHOPCAST_COLLECTOR__USER_AGENT
chopcast config validate
```

The `pre-commit` hook runs `ruff`, `mypy`, and a few custom checks. If it fails, the commit is rejected.

---

## 2. Workflow

```
issue or design note
    -> branch
        -> commits
            -> PR
                -> CI
                    -> review
                        -> merge
```

### 2.1 Branching

We use a simplified git-flow:

| Branch | Purpose | Lifetime |
|---|---|---|
| `main` | Always releasable. Protected. | Permanent |
| `feat/<name>` | A new feature. Rebased on `main`. | Until merged |
| `fix/<name>` | A bug fix. Rebased on `main`. | Until merged |
| `chore/<name>` | Tooling, docs, refactors with no behavior change. | Until merged |
| `release/<version>` | Cut from `main`, only bug fixes, tagged, merged back. | Days |

Branch names are kebab-case. Example: `feat/collector-rate-limit-backoff`.

### 2.2 Commits

We use [Conventional Commits](https://www.conventionalcommits.org/). Format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`.

Scope: the module name (`collector`, `parser`, `training`, `docs`, `ci`, etc.).

Subject: imperative, no period, ≤ 72 characters.

Body: explain *why*, not *what*. The diff shows what.

Footer: reference issues (`Closes #42`), note breaking changes (`BREAKING CHANGE: ...`).

Example:

```
feat(collector): add 5xx retry with exponential backoff

AWC's cache occasionally returns 503 during peak hours. Previously
we surfaced this as a collection error; now we retry up to MAX_RETRIES
with backoff capped at MAX_BACKOFF_SECONDS.

Refs: #42
```

### 2.3 Pull requests

A PR is a unit of review. It should be small enough to review in under 30 minutes.

PR template (auto-populated):

```markdown
## What
One sentence describing the change.

## Why
One paragraph on the motivation. Link to an issue or design doc.

## How
Implementation notes, including anything surprising.

## Tests
What tests were added or updated. How were they run?

## Risks
What could go wrong? What was not tested?

## Checklist
- [ ] Tests added/updated
- [ ] Docs updated
- [ ] CHANGELOG.md updated
- [ ] No new lint warnings
```

A PR that introduces a behavior change must include a `CHANGELOG.md` entry under the `## Unreleased` heading.

### 2.4 Reviews

We require at least one review. Reviews are about:

- Correctness (does it do what it says)
- Tests (do they actually exercise the change)
- Contracts (is the public interface reasonable)
- Leakage (does any new code risk leaking `/TB`)
- Style (does it match the surrounding code)

We do not block on bikeshedding. A reviewer who wants a naming change should mark it `nit:` and approve.

### 2.5 Merge strategy

We squash-merge. The PR title becomes the commit message (rewritten if needed to match Conventional Commits). The branch is deleted automatically.

---

## 3. Coding standards

See [STANDARDS.md](STANDARDS.md) for the full set. Short version:

- Type hints on every public function.
- Pydantic for any data that crosses a module boundary.
- `from __future__ import annotations` at the top of every module.
- No `Any` unless crossing a library boundary that requires it.
- Docstrings on every public function in the format described in §4.
- No print statements; use the logger.
- No `os.environ.get` in `chopcast/*`; go through `Settings`.

---

## 4. Docstring format

We use Google-style docstrings. Example:

```python
def report_hash(obs_time: str, lat: float | None, lon: float | None, raw_text: str) -> str:
    """Compute the content hash of a PIREP.

    Args:
        obs_time: ISO 8601 UTC observation time.
        lat: Latitude in decimal degrees, or None if unknown.
        lon: Longitude in decimal degrees, or None if unknown.
        raw_text: The raw "/"-delimited PIREP string.

    Returns:
        A 64-character hex SHA-256 digest.

    Raises:
        ValidationError: If obs_time is not parseable as ISO 8601.
    """
```

A docstring is required on every public function. Internal helpers may use a one-line docstring or none.

---

## 5. Tests

See [TESTING.md](TESTING.md). Quick rules:

- Every PR must include tests.
- A new public function must have tests covering the happy path and at least one error path.
- A bug fix must include a regression test that fails on `main` and passes on the branch.
- Do not disable or skip a test without a `pytest.mark.skip(reason="...")` and an issue number.

---

## 6. Documentation

When you change behavior, update the docs in the same PR. The docs are:

- `README.md` — top-level intro and quickstart
- `docs/ARCHITECTURE.md` — system architecture
- `docs/DATA_ENGINEERING.md` — schema, dedup, datasets
- `docs/ML_ARCHITECTURE.md` — models, training, evaluation
- `docs/MODULE_DESIGN.md` — package layout and contracts
- `docs/TESTING.md` — testing strategy
- `docs/CONFIGURATION.md` — configuration schema
- `docs/ROADMAP.md` — milestones
- `docs/STANDARDS.md` — coding standards
- `docs/adr/` — architecture decision records

A behavior change without a doc update is incomplete.

---

## 7. Issue triage

Issues are labeled:

- `bug` — something is wrong
- `feat` — new functionality
- `chore` — tooling, refactor, no behavior change
- `docs` — documentation only
- `good first issue` — small enough for a new contributor
- `help wanted` — open to anyone
- `M0` … `M7` — which milestone it belongs to
- `priority: high|medium|low` — urgency

A new issue should get at least one label within 24 hours.

---

## 8. Releases

We tag releases. Format: `vMAJOR.MINOR.PATCH`.

- `MAJOR` — breaking change to a public API or a data format
- `MINOR` — new feature, backward-compatible
- `PATCH` — bug fix, backward-compatible

A release:

1. Cuts a `release/vX.Y.Z` branch from `main`.
2. Only bug fixes are merged in.
3. The release is tagged.
4. The release notes are drafted from the `CHANGELOG.md`.
5. The release branch is merged back to `main`.

---

## 9. Code of conduct

We follow the Contributor Covenant. Be kind, assume good faith, and focus on the work. Disagreements about technical direction are resolved in PRs and issues, never in personal messages.
