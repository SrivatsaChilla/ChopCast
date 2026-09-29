"""Side-by-side comparison between two registered model versions.

The report is the artefact we attach to a PR or release notes: it
says which model won, by how much, and on which slice. The numbers come
from each model's stored metrics in the registry (so the comparison is
reproducible without re-loading artefacts), plus — optionally — a
re-run on a fresh test split for tie-breaking.

Inputs are always two `ModelRecord`s. Outputs are pure data
(`ComparisonReport`) plus a Markdown renderer. No I/O, no randomness.

See `docs/MODULE_DESIGN.md` §9.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chopcast.logging import get_logger
from chopcast.registry.store import ModelRecord

log = get_logger(__name__)


@dataclass(frozen=True)
class MetricDelta:
    """The signed difference between two scalars, expressed for a single metric."""

    metric: str
    a: float
    b: float
    delta: float  # b - a

    def to_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "a": self.a, "b": self.b, "delta": self.delta}


@dataclass(frozen=True)
class PerClassDelta:
    """Per-class F1 comparison."""

    label: str
    a_f1: float
    b_f1: float
    delta: float


@dataclass(frozen=True)
class ComparisonReport:
    """The structured result of comparing two model versions."""

    a: ModelRecord
    b: ModelRecord
    metric_deltas: tuple[MetricDelta, ...]
    per_class_deltas: tuple[PerClassDelta, ...]
    winner: str  # "a", "b", or "tie"
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "a": self.a.model_version,
            "b": self.b.model_version,
            "metric_deltas": [m.to_dict() for m in self.metric_deltas],
            "per_class_deltas": [
                {"label": p.label, "a_f1": p.a_f1, "b_f1": p.b_f1, "delta": p.delta}
                for p in self.per_class_deltas
            ],
            "winner": self.winner,
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# The metrics we care about for headline numbers. Each entry is the
# path inside the stored `metrics` dict.
_HEADLINE_METRICS = ("accuracy", "macro_f1", "weighted_f1")


def _extract_metric(metrics: dict[str, Any], key: str) -> float:
    """Pull a top-level metric out of a stored metrics dict.

    Falls back to 0.0 if the key is missing — this lets us compare
    records that were registered before richer metrics were added
    without crashing.
    """
    if not isinstance(metrics, dict):
        return 0.0
    val = metrics.get(key)
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _extract_per_class(metrics: dict[str, Any]) -> dict[str, float]:
    """Return a `{label: f1}` mapping from the stored per-class metrics.

    Accepts two shapes:
        {"per_class": [{"label": "None", "f1": 0.8}, ...]}
        {"per_class_f1": {"None": 0.8, "Light": 0.5}}
    Returns {} if neither is present.
    """
    if not isinstance(metrics, dict):
        return {}
    pc = metrics.get("per_class")
    if isinstance(pc, list):
        out: dict[str, float] = {}
        for entry in pc:
            if not isinstance(entry, dict):
                continue
            label = entry.get("label")
            f1 = entry.get("f1")
            if label is None or f1 is None:
                continue
            try:
                out[str(label)] = float(f1)
            except (TypeError, ValueError):
                continue
        if out:
            return out
    pc2 = metrics.get("per_class_f1")
    if isinstance(pc2, dict):
        out = {}
        for k, v in pc2.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    return {}


def _winning_metric(metric_deltas: tuple[MetricDelta, ...]) -> tuple[str, float]:
    """Decide which record wins.

    We aggregate by the sum of signed deltas across headline metrics.
    A positive sum means B beats A; negative means A beats B; zero is
    a tie.

    Returns (winner, margin) where winner ∈ {"a","b","tie"}.
    """
    if not metric_deltas:
        return ("tie", 0.0)
    margin = sum(m.delta for m in metric_deltas)
    if margin > 0:
        return ("b", margin)
    if margin < 0:
        return ("a", -margin)
    return ("tie", 0.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compare(
    a: ModelRecord,
    b: ModelRecord,
    *,
    feature_version_must_match: bool = True,
) -> ComparisonReport:
    """Compare two registered models and report deltas.

    Args:
        a: the "before" model.
        b: the "after" model.
        feature_version_must_match: if True (default), raise ValueError
            when the two records were trained on different feature
            versions. Comparing across feature versions is apples-to-
            oranges and almost always a mistake.
    """
    if a.id == b.id:
        raise ValueError("cannot compare a model with itself")
    if feature_version_must_match and a.feature_version != b.feature_version:
        raise ValueError(
            f"cannot compare models trained on different feature versions: "
            f"{a.feature_version!r} vs {b.feature_version!r}"
        )

    metric_deltas: list[MetricDelta] = []
    for key in _HEADLINE_METRICS:
        av = _extract_metric(a.metrics, key)
        bv = _extract_metric(b.metrics, key)
        metric_deltas.append(MetricDelta(metric=key, a=av, b=bv, delta=bv - av))

    a_pc = _extract_per_class(a.metrics)
    b_pc = _extract_per_class(b.metrics)
    labels = sorted({*a_pc.keys(), *b_pc.keys()})
    per_class_deltas: list[PerClassDelta] = []
    for label in labels:
        av = a_pc.get(label, 0.0)
        bv = b_pc.get(label, 0.0)
        per_class_deltas.append(
            PerClassDelta(label=label, a_f1=av, b_f1=bv, delta=bv - av)
        )

    winner, margin = _winning_metric(tuple(metric_deltas))
    if winner == "tie":
        rationale = (
            f"No headline metric differs (margin={margin:.4f}); the two "
            f"models are tied on this split."
        )
    else:
        winning_record = b if winner == "b" else a
        rationale = (
            f"{winning_record.model_version} wins by {margin:.4f} on the "
            f"sum of headline-metric deltas "
            f"(acc / macro-F1 / weighted-F1)."
        )

    log.info(
        "comparison.complete",
        a=a.model_version,
        b=b.model_version,
        winner=winner,
        margin=margin,
    )
    return ComparisonReport(
        a=a,
        b=b,
        metric_deltas=tuple(metric_deltas),
        per_class_deltas=tuple(per_class_deltas),
        winner=winner,
        rationale=rationale,
    )


def to_markdown(report: ComparisonReport) -> str:
    """Render a `ComparisonReport` as Markdown."""
    lines: list[str] = []
    lines.append(f"# Model comparison — {report.a.model_version} vs {report.b.model_version}")
    lines.append("")
    lines.append(f"- **A (baseline)**: `{report.a.model_version}` ({report.a.model_kind})")
    lines.append(f"- **B (candidate)**: `{report.b.model_version}` ({report.b.model_kind})")
    lines.append(f"- **Winner**: **{report.winner}**")
    lines.append(f"- **Rationale**: {report.rationale}")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | A | B | Δ (B − A) |")
    lines.append("|---|---|---|---|")
    for m in report.metric_deltas:
        lines.append(f"| {m.metric} | {m.a:.4f} | {m.b:.4f} | {m.delta:+.4f} |")
    lines.append("")
    if report.per_class_deltas:
        lines.append("## Per-class F1")
        lines.append("")
        lines.append("| Label | A | B | Δ (B − A) |")
        lines.append("|---|---|---|---|")
        for p in report.per_class_deltas:
            lines.append(
                f"| {p.label} | {p.a_f1:.4f} | {p.b_f1:.4f} | {p.delta:+.4f} |"
            )
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "ComparisonReport",
    "MetricDelta",
    "PerClassDelta",
    "compare",
    "to_markdown",
]
