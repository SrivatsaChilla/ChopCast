"""Evaluation: metrics, report rendering, comparison.

The `evaluate()` function produces a structured `EvaluationReport`
that includes per-class precision/recall/F1, macro-F1, weighted-F1,
the confusion matrix, and per-class support. The same data drives
the Markdown renderer.

See `docs/MODULE_DESIGN.md` §9.
"""