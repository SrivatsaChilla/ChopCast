"""Model registry: SQL-backed ledger of trained models.

Every trained model is registered as one row. The row records the
metrics, the feature version, and the artefact path. The registry
is the single source of truth for "what models do we have, and
which is the current production one?".

See `docs/MODULE_DESIGN.md` §10.
"""