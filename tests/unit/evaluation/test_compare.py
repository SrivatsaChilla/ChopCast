"""Tests for the side-by-side comparison report."""

from __future__ import annotations

import pytest

from chopcast.evaluation.compare import (
    ComparisonReport,
    compare,
    to_markdown,
)
from chopcast.registry.store import ModelRecord


def _record(
    *,
    id: int,
    version: str,
    kind: str = "baseline",
    feature_version: str = "fv1",
    metrics: dict | None = None,
) -> ModelRecord:
    return ModelRecord(
        id=id,
        model_version=version,
        model_kind=kind,
        feature_version=feature_version,
        registered_at="2026-08-25T00:00:00+00:00",
        metrics=metrics or {},
        artifact_path=f"/tmp/{version}",
        notes=None,
    )


def _full_metrics(
    *,
    acc: float = 0.8,
    macro: float = 0.7,
    weighted: float = 0.75,
    per_class: dict[str, float] | None = None,
) -> dict:
    return {
        "accuracy": acc,
        "macro_f1": macro,
        "weighted_f1": weighted,
        "n_samples": 100,
        "per_class": [
            {"label": label, "f1": f1, "precision": f1, "recall": f1, "support": 25}
            for label, f1 in (per_class or {"None": 0.7, "Light": 0.5}).items()
        ],
    }


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------
def test_compare_same_feature_version() -> None:
    a = _record(id=1, version="v1", metrics=_full_metrics(macro=0.7))
    b = _record(id=2, version="v2", metrics=_full_metrics(macro=0.8))
    report = compare(a, b)
    assert isinstance(report, ComparisonReport)


def test_compare_rejects_self() -> None:
    a = _record(id=1, version="v1", metrics=_full_metrics())
    with pytest.raises(ValueError, match="itself"):
        compare(a, a)


def test_compare_rejects_mismatched_feature_version() -> None:
    a = _record(id=1, version="v1", feature_version="fv1", metrics=_full_metrics())
    b = _record(id=2, version="v2", feature_version="fv2", metrics=_full_metrics())
    with pytest.raises(ValueError, match="feature version"):
        compare(a, b)


def test_compare_allows_mismatched_feature_version_when_disabled() -> None:
    a = _record(id=1, version="v1", feature_version="fv1", metrics=_full_metrics())
    b = _record(id=2, version="v2", feature_version="fv2", metrics=_full_metrics())
    # Should NOT raise when feature_version_must_match=False.
    report = compare(a, b, feature_version_must_match=False)
    assert isinstance(report, ComparisonReport)


# ---------------------------------------------------------------------------
# Headline metric deltas
# ---------------------------------------------------------------------------
def test_compare_extracts_headline_metrics() -> None:
    a = _record(id=1, version="v1", metrics=_full_metrics(acc=0.7, macro=0.6, weighted=0.65))
    b = _record(id=2, version="v2", metrics=_full_metrics(acc=0.8, macro=0.7, weighted=0.75))
    report = compare(a, b)
    metrics = {m.metric: m for m in report.metric_deltas}
    assert metrics["accuracy"].a == pytest.approx(0.7)
    assert metrics["accuracy"].b == pytest.approx(0.8)
    assert metrics["accuracy"].delta == pytest.approx(0.1)
    assert metrics["macro_f1"].delta == pytest.approx(0.1)
    assert metrics["weighted_f1"].delta == pytest.approx(0.1)


def test_compare_handles_missing_metrics() -> None:
    a = _record(id=1, version="v1", metrics={})
    b = _record(id=2, version="v2", metrics=_full_metrics(acc=0.8))
    report = compare(a, b)
    metrics = {m.metric: m for m in report.metric_deltas}
    assert metrics["accuracy"].a == 0.0
    assert metrics["accuracy"].b == 0.8


def test_compare_handles_non_dict_metrics() -> None:
    a = _record(id=1, version="v1", metrics={})  # type: ignore[arg-type]
    # Replace metrics with a non-dict to exercise the type guard.
    a = ModelRecord(
        id=1, model_version="v1", model_kind="baseline",
        feature_version="fv1", registered_at="2026-08-25T00:00:00+00:00",
        metrics="not-a-dict",  # type: ignore[arg-type]
        artifact_path="/tmp/v1", notes=None,
    )
    b = _record(id=2, version="v2", metrics=_full_metrics(acc=0.8))
    # Should not crash; all metrics from A should be 0.0.
    report = compare(a, b)
    for m in report.metric_deltas:
        assert m.a == 0.0


# ---------------------------------------------------------------------------
# Winner logic
# ---------------------------------------------------------------------------
def test_winner_b_when_b_better() -> None:
    a = _record(id=1, version="v1", metrics=_full_metrics(acc=0.7, macro=0.6))
    b = _record(id=2, version="v2", metrics=_full_metrics(acc=0.8, macro=0.7))
    report = compare(a, b)
    assert report.winner == "b"
    assert "v2" in report.rationale


def test_winner_a_when_a_better() -> None:
    a = _record(id=1, version="v1", metrics=_full_metrics(acc=0.9, macro=0.85))
    b = _record(id=2, version="v2", metrics=_full_metrics(acc=0.8, macro=0.7))
    report = compare(a, b)
    assert report.winner == "a"
    assert "v1" in report.rationale


def test_winner_tie_when_identical() -> None:
    metrics = _full_metrics(acc=0.8, macro=0.7, weighted=0.75)
    a = _record(id=1, version="v1", metrics=metrics)
    b = _record(id=2, version="v2", metrics=metrics)
    report = compare(a, b)
    assert report.winner == "tie"
    assert "tied" in report.rationale


# ---------------------------------------------------------------------------
# Per-class F1 deltas
# ---------------------------------------------------------------------------
def test_per_class_deltas_extracted() -> None:
    a = _record(
        id=1, version="v1",
        metrics=_full_metrics(per_class={"None": 0.5, "Light": 0.6, "Severe": 0.4}),
    )
    b = _record(
        id=2, version="v2",
        metrics=_full_metrics(per_class={"None": 0.7, "Light": 0.6, "Severe": 0.5}),
    )
    report = compare(a, b)
    by_label = {p.label: p for p in report.per_class_deltas}
    assert by_label["None"].delta == pytest.approx(0.2)
    assert by_label["Light"].delta == pytest.approx(0.0)
    assert by_label["Severe"].delta == pytest.approx(0.1)


def test_per_class_deltas_alternate_shape() -> None:
    """Accepts {'per_class_f1': {label: f1, ...}} as well."""
    a = _record(id=1, version="v1", metrics={"per_class_f1": {"None": 0.5, "Light": 0.5}})
    b = _record(id=2, version="v2", metrics={"per_class_f1": {"None": 0.7, "Light": 0.5}})
    report = compare(a, b)
    by_label = {p.label: p for p in report.per_class_deltas}
    assert by_label["None"].delta == pytest.approx(0.2)


def test_per_class_deltas_empty_when_missing() -> None:
    a = _record(id=1, version="v1", metrics={"accuracy": 0.7})
    b = _record(id=2, version="v2", metrics={"accuracy": 0.8})
    report = compare(a, b)
    assert report.per_class_deltas == ()


def test_per_class_deltas_union_labels() -> None:
    """Labels in either A or B should appear in the comparison."""
    a = _record(id=1, version="v1", metrics={"per_class": [{"label": "None", "f1": 0.5}]})
    b = _record(id=2, version="v2", metrics={"per_class": [{"label": "Light", "f1": 0.7}]})
    report = compare(a, b)
    labels = {p.label for p in report.per_class_deltas}
    assert labels == {"None", "Light"}


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def test_to_markdown_contains_versions_and_winner() -> None:
    a = _record(id=1, version="v1", metrics=_full_metrics(macro=0.6))
    b = _record(id=2, version="v2", metrics=_full_metrics(macro=0.7))
    report = compare(a, b)
    md = to_markdown(report)
    assert "v1" in md
    assert "v2" in md
    assert "**b**" in md


def test_to_markdown_includes_per_class_section() -> None:
    a = _record(
        id=1, version="v1",
        metrics=_full_metrics(per_class={"None": 0.5, "Light": 0.6}),
    )
    b = _record(
        id=2, version="v2",
        metrics=_full_metrics(per_class={"None": 0.7, "Light": 0.5}),
    )
    report = compare(a, b)
    md = to_markdown(report)
    assert "Per-class F1" in md
    assert "None" in md
    assert "Light" in md


def test_to_markdown_skips_per_class_when_empty() -> None:
    # Build metrics WITHOUT per-class info so the section is omitted.
    a = _record(id=1, version="v1", metrics={"accuracy": 0.8, "macro_f1": 0.7, "weighted_f1": 0.75})
    b = _record(id=2, version="v2", metrics={"accuracy": 0.8, "macro_f1": 0.7, "weighted_f1": 0.75})
    report = compare(a, b)
    assert report.per_class_deltas == ()
    md = to_markdown(report)
    assert "Per-class F1" not in md


# ---------------------------------------------------------------------------
# to_dict round-trip
# ---------------------------------------------------------------------------
def test_to_dict_structure() -> None:
    a = _record(id=1, version="v1", metrics=_full_metrics())
    b = _record(id=2, version="v2", metrics=_full_metrics(macro=0.8))
    report = compare(a, b)
    d = report.to_dict()
    assert d["a"] == "v1"
    assert d["b"] == "v2"
    assert d["winner"] in {"a", "b", "tie"}
    assert "rationale" in d
    assert isinstance(d["metric_deltas"], list)
    assert isinstance(d["per_class_deltas"], list)
