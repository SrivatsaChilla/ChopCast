"""Model protocols and concrete implementations.

The `Model` Protocol is the contract that every model — baseline,
transformer, anything else — must satisfy. The downstream system
(inference API, registry, evaluation harness) talks only to this
Protocol, so swapping baseline for transformer requires no other
changes.

See `docs/MODULE_DESIGN.md` §7 and `docs/ML_ARCHITECTURE.md` §2.
"""