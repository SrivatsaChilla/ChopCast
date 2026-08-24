# Architecture Decision Records

This directory holds the ADRs for ChopCast. Each ADR captures one significant architectural decision: its context, the decision itself, the consequences, and the alternatives considered.

ADRs are immutable once accepted. If a decision is reversed, a new ADR is written that supersedes the old one. The old ADR is updated with a "Superseded by" line at the top.

## Index

| Number | Title | Status |
|---|---|---|
| [0001](0001-redesign-rationale.md) | Redesign from a clean package structure rather than extend the 3-file prototype | Accepted |
| [0002](0002-repository-layout.md) | Repository layout — code, configs, data, models, tests, docs | Accepted |
| [0003](0003-leakage-prevention.md) | Label leakage prevention — structural, not aspirational | Accepted |
| [0004](0004-dedup-strategy.md) | Deduplication strategy — content hash, not source id | Accepted |
| [0005](0005-model-abstraction.md) | A single Model protocol abstracts baseline and transformer | Accepted |
| [0006](0006-no-onedrive.md) | The data directory must not live under a cloud-sync folder | Accepted |

## Conventions

- File names: `NNNN-kebab-case-slug.md`.
- Status: `Proposed`, `Accepted`, `Superseded`, or `Deprecated`.
- Each ADR has the same sections: Context, Decision, Consequences, Alternatives considered, References.
- The "References" section links to the relevant docs in `docs/` and to other ADRs.

## When to write a new ADR

Write one when:

- You are choosing between two or more technically reasonable approaches.
- The decision will be hard to reverse later.
- The decision affects more than one module or one milestone.
- Future contributors will benefit from understanding *why*, not just *what*.

Do not write one for:

- Implementation details that live in code.
- Decisions that are easily reversed (e.g., the name of a private function).
- Anything that belongs in a commit message.

## Template

```markdown
# ADR-NNNN: Title

- **Status:** Proposed
- **Date:** YYYY-MM-DD

## Context

What is the situation? What forces are at play?

## Decision

What did we choose? State it as a positive rule, not a negation.

## Consequences

What becomes easier? What becomes harder? What did we accept as a cost?

## Alternatives considered

What else did we look at, and why didn't we pick it?

## References

Links to docs, issues, other ADRs.
```
