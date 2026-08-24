"""PIREP text parsing.

The slash-delimited grammar of a PIREP is documented in
`docs/MODULE_DESIGN.md` §3. The parser here is intentionally forgiving:
missing or malformed fields become `None` instead of raising, with the
single exception that a completely unparseable input (no recognised
slash fields at all) raises `ParseError`.

This module never modifies the input text — that is `cleaner.py`'s job.
"""