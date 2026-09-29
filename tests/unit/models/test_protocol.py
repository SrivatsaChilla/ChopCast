"""Tests for chopcast.models.protocol (StubModel)."""

from __future__ import annotations

import pytest

from chopcast.models.protocol import Model, StubModel


def test_stub_model_satisfies_protocol() -> None:
    m = StubModel(["A", "B", "C"], majority="A")
    assert isinstance(m, Model)


def test_stub_predict_returns_majority() -> None:
    m = StubModel(["A", "B"], majority="A")
    preds = list(m.predict(["x", "y", "z"]))
    assert preds == ["A", "A", "A"]


def test_stub_predict_proba_shape() -> None:
    m = StubModel(["A", "B", "C"], majority="B")
    proba = m.predict_proba(["x", "y"])
    assert proba.shape == (2, 3)
    # Probabilities sum to 1 per row.
    sums = proba.sum(axis=1)
    for s in sums:
        assert s == pytest.approx(1.0)


def test_stub_classes() -> None:
    m = StubModel(["A", "B"], majority="A")
    assert m.classes() == ["A", "B"]


def test_stub_save(tmp_path) -> None:
    m = StubModel(["A"], majority="A")
    m.save(tmp_path)
    assert (tmp_path / "STUB.txt").exists()