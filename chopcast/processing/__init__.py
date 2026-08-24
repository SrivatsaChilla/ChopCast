"""Text processing: cleaning, feature building, pipeline.

The leakage linter lives in `cleaner.py`. Every other module must
route text cleaning through this one — CI enforces the rule that
no other module contains the string `/TB` (regex-based lint).

See `docs/MODULE_DESIGN.md` §5.
"""