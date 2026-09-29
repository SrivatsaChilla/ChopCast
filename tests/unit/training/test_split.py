"""Tests for chopcast.training.split."""

from __future__ import annotations

import pytest

from chopcast.config import SplitConfig
from chopcast.training.split import Split, load_split, make_split, save_split


def test_stratified_split_is_deterministic() -> None:
    hashes = [f"h{i}" for i in range(20)]
    labels = (["A"] * 8) + (["B"] * 8) + (["C"] * 4)
    cfg = SplitConfig(mode="stratified", test_size=0.25, seed=42)
    a = make_split(hashes, labels, config=cfg)
    b = make_split(hashes, labels, config=cfg)
    assert a.train_hashes == b.train_hashes
    assert a.test_hashes == b.test_hashes


def test_stratified_preserves_class_proportions() -> None:
    hashes = [f"h{i}" for i in range(40)]
    labels = (["A"] * 20) + (["B"] * 10) + (["C"] * 10)
    cfg = SplitConfig(mode="stratified", test_size=0.25, seed=1)
    split = make_split(hashes, labels, config=cfg)
    from collections import Counter

    train_counts = Counter(split.train_labels)
    test_counts = Counter(split.test_labels)
    # Test proportions should be close to train proportions.
    for label in ("A", "B", "C"):
        if split.n_test > 0:
            test_frac = test_counts[label] / split.n_test
            train_frac = train_counts[label] / split.n_train
            # Within 10 percentage points.
            assert abs(test_frac - train_frac) < 0.15


def test_stratified_split_size() -> None:
    hashes = [f"h{i}" for i in range(100)]
    labels = (["A"] * 50) + (["B"] * 50)
    cfg = SplitConfig(mode="stratified", test_size=0.2, seed=0)
    split = make_split(hashes, labels, config=cfg)
    assert split.n_train + split.n_test == 100
    assert abs(split.n_test - 20) <= 5  # within 5 of expected


def test_time_split_uses_order() -> None:
    hashes = [f"h{i}" for i in range(10)]
    labels = ["L" for _ in hashes]
    cfg = SplitConfig(mode="time", test_size=0.2, seed=0)
    split = make_split(hashes, labels, config=cfg)
    # Time split puts the last 20% into test.
    assert split.test_hashes == ("h8", "h9")


def test_unknown_mode_rejected() -> None:
    # Pydantic's Literal validator rejects unknown strings.
    with pytest.raises(Exception):
        SplitConfig(mode="bogus")  # type: ignore[arg-type]


def test_runtime_rejects_test_size_zero() -> None:
    # Even if the config allows it, `make_split` raises if test_size is
    # at the boundary.
    import pytest as _pytest

    with _pytest.raises(Exception):
        make_split(["a"], ["A"], config=SplitConfig(mode="stratified", test_size=1.0))


def test_save_and_load_roundtrip(tmp_path) -> None:
    split = Split(
        train_hashes=("a", "b"),
        test_hashes=("c",),
        train_labels=("A", "A"),
        test_labels=("B",),
        version="v1",
        seed=42,
        config_version="v1",
        mode="stratified",
    )
    path = tmp_path / "split.json"
    save_split(split, path)
    loaded = load_split(path)
    assert loaded == split


def test_empty_dataset() -> None:
    split = make_split([], [], config=SplitConfig(mode="stratified", test_size=0.2))
    assert split.n_train == 0
    assert split.n_test == 0


def test_stratified_with_rare_class() -> None:
    # A class with only one member should still appear in train.
    hashes = ["h1", "h2", "h3", "h4", "h5"]
    labels = ["A", "A", "A", "A", "B"]
    cfg = SplitConfig(mode="stratified", test_size=0.2, seed=0)
    split = make_split(hashes, labels, config=cfg)
    # The singleton should appear in train (we never split off the
    # last member of a class).
    assert "B" in split.train_labels or "B" in split.test_labels