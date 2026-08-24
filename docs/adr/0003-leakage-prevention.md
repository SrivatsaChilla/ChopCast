# ADR-0003: Label leakage prevention — structural, not aspirational

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

PIREPs contain both the label (`/TB MOD`) and the model input (the rest of the report, including `RM` remarks). If `/TB` is left in the input, a model learns to read the answer, and reported metrics are meaningless. This is the most common failure mode of PIREP classifier projects, and the literature is full of papers that report 0.95 accuracy on a test set and 0.0 on real-world data.

The current code does not have a leakage problem because it has no model. The risk is that we add a model without designing for leakage prevention, and then retrofit a fix that misses some path.

## Decision

Leakage prevention is enforced at three independent layers. All three must pass for the system to ship a model. The architectural rule is:

> **`chopcast.processing.cleaner` is the only function in the codebase that knows how to remove `/TB` from a PIREP. Trainers do not have access to raw text. The lint test enforces that no other module references `/TB` in code.**

The three layers are:

### 1. Structural

The `cleaner` module is the only path from raw text to clean text. The `FeatureRow` dataclass (the only input a trainer accepts) has a `clean_text` field, not a `raw_text` field. The trainer cannot import from `chopcast.collector`; the dependency direction in `docs/MODULE_DESIGN.md` §0 forbids it.

### 2. Static

`tests/lint/test_no_tb_leakage.py` greps the source tree and fails if the literal `/TB` appears anywhere except:

- `chopcast/processing/cleaner.py` (where it is removed)
- `chopcast/parser/pirep.py` (where it is parsed, not passed through)
- test fixtures that intentionally contain it

This is a test. It runs on every commit. A regression in this test is treated as a critical defect.

### 3. Behavioral

`chopcast.processing.cleaner.clean_text` has a self-check at the end of every call. If a `/TB` value is detected in the output, it raises `LeakageError`. The function is paranoid by design; a false positive is cheap, a false negative is fatal.

In addition, a test walks the call graph of `train()` and asserts that no function reachable from it accepts a `RawReport` (the type that contains `raw_text`). The trainer's type signature restricts it to `FeatureRow`.

## Consequences

**Positive**

- Leakage cannot reach a model without three independent checks failing.
- New contributors cannot accidentally introduce a leaky path: the lint test fails on the first commit.
- A test that fails on this issue is unambiguous: either the cleaner has a bug, or some new code references `/TB` outside the allowed locations. Both are easy to diagnose.

**Negative**

- The lint test is a regex over a string. It is possible to defeat it by encoding `/TB` in a clever way (e.g., string concatenation, escape sequences). We accept this risk; the cleaner is the only place that decodes the encoded form, so the structural layer is the actual defense.
- The test makes it slightly harder to write tests that involve `/TB`. We mitigate by allowing it in `tests/parser/test_pirep.py` and `tests/processing/test_cleaner.py`, which are the only places it should appear.

**Mitigations**

- The behavioral self-check is a defense in depth. Even if the lint test is fooled, the cleaner itself catches leakage at runtime.
- A monthly review of the trainer's call graph verifies the structural rule has not been bypassed.

## Alternatives considered

**Document the rule and trust developers.** Rejected: this is exactly the failure mode that has burned the PIREP classification literature. Trust is not a defense.

**Use a separate process for cleaning** (a microservice that the trainer calls). Rejected: the project is small; an extra service is more surface area than the risk justifies. The function-level boundary is sufficient.

**Strip `/TB` inside the trainer.** Rejected: this is exactly the wrong place. The trainer should never see raw text. If the cleaner has a bug, we want a single place to fix it.

**Don't bother, because the model will learn not to overfit.** Rejected: empirically false. Even with strong regularization, models on PIREP text learn to use `/TB` if it is present. The reported metrics will be high; the real metrics will not.

## References

- `docs/ARCHITECTURE.md` §3 (principle 3)
- `docs/DATA_ENGINEERING.md` §7
- `docs/TESTING.md` §7.2
- `docs/MODULE_DESIGN.md` §5.1
