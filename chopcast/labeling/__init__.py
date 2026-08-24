"""Severity labeling for PIREPs.

Maps the raw `/TB` value to one of `None`, `Light`, `Moderate`,
`Severe`. Rules live in `configs/labeling.yaml` so we can extend
them without code redeployments.

See `docs/MODULE_DESIGN.md` §4.
"""