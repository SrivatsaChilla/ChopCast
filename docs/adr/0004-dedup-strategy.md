# ADR-0004: Deduplication strategy — content hash, not source id

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

The AWC aircraft-reports cache is a rolling window. Every poll re-serves many of the same reports. If we store every row from every poll, we accumulate duplicates. Duplicates leak across train/test splits and inflate model metrics.

We need a stable identifier for a report. The AWC cache previously provided a `pirepId` field, but it was removed in September 2025. We cannot rely on any source-provided identifier.

The legacy `collector.py` uses `sha256(obs_time | lat | lon | raw_text)`. This works, but the question is whether it is the right key in the new architecture.

## Decision

The dedup key is `sha256(obs_time | "|" | lat_rounded | "|" | lon_rounded | "|" | normalized_raw_text)`, where:

- `obs_time` is ISO 8601 UTC.
- `lat_rounded` and `lon_rounded` are rounded to 4 decimal places (~11 m at the equator).
- `normalized_raw_text` is lowercased, with leading/trailing whitespace stripped and internal whitespace collapsed to single spaces.

This key is the primary key of the `reports` table. Insertion uses `INSERT OR IGNORE`, so dedup is atomic at the SQL level. There is no read-then-write path.

The 4-decimal rounding is coarser than GPS precision but finer than realistic PIREP position noise. It prevents two equivalent reports from differing by a rounding artifact. A report with `lat=37.61891` and a report with `lat=37.61893` are considered the same; a report with `lat=37.6` is not.

## Consequences

**Positive**

- Dedup is content-addressed. The same report from any source gets the same id. We can ingest from a different provider later without re-keying.
- The hash is computed once, at ingestion, and stored. It is cheap to check; it does not depend on the source format.
- `INSERT OR IGNORE` makes the operation atomic and concurrency-safe. Two collection cycles running simultaneously will not double-insert.

**Negative**

- A report that is genuinely *new* but happens to have the same (time, location, text) as a previous report will be silently dropped. This is extremely unlikely (it would require a duplicate observation at the same place and time with identical text), and the dedup is the right behavior in that case anyway.
- The hash does not survive a re-keying. If we change the rounding precision, every existing hash changes. We mitigate by treating this as a content-breaking change that requires a migration; the legacy DB migration script reads the old `pireps.db` and writes new hashes.
- The hash does not help us detect near-duplicates. Two reports that differ only by punctuation will not collide at the raw stage. The processing layer's cleaner produces a second hash on which a tighter dedup is performed for the training set.

**Mitigations**

- The `rejected` table logs every row that was not inserted because of a hash collision. A spike in collisions is a signal that something upstream changed, not that we are collecting the same reports again.
- The hash is also stored in the `lineage.json` of every derived artifact, so the data lineage is content-addressed at every level.

## Alternatives considered

**Use `pirepId` if it comes back.** Rejected as a primary strategy: it is a source-controlled id and we have no guarantee it will not change or disappear again. Content-addressed hashing is robust to source changes.

**Use a composite natural key** (`(obs_time, lat, lon)`). Rejected: it does not include text, so two reports at the same time and place with different text would collide. This is a real case: a PIREP and an AIREP at the same location and time.

**Use a UUID generated at insertion.** Rejected: it gives us a unique id but no way to detect that two rows are the same report. We would still need a separate dedup step, and the UUID would obscure the duplication.

**Use a vector similarity index** (e.g., pgvector, Faiss). Rejected: massive over-engineering for a problem that hash-based dedup solves in O(1).

**No dedup.** Rejected: this is the most common way for PIREP classifier projects to ship nonsense metrics. Duplicates in train and test inflate accuracy by 5–15 percentage points. Not deduping is not a defensible choice.

## References

- `docs/DATA_ENGINEERING.md` §3
- `docs/MODULE_DESIGN.md` §2.3
