"""Tests for chopcast.models.transformer_distilbert.

`StubTransformerModel` is testable on any environment.
`TransformerDistilbert` itself depends on torch + transformers and is
covered by guarded tests that skip when those are missing.
"""

from __future__ import annotations

import pytest

from chopcast.models.protocol import Model
from chopcast.models.transformer_distilbert import (
    StubTransformerModel,
    TransformerDistilbert,
    TransformerTrainerSettings,
    _import_torch,
    _import_transformers,
)


# ---------------------------------------------------------------------------
# Imports / capability probes
# ---------------------------------------------------------------------------
def _has_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _has_transformers() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Stub model — these tests run everywhere.
# ---------------------------------------------------------------------------
def test_stub_satisfies_protocol() -> None:
    m = StubTransformerModel(["A", "B"], majority="A")
    assert isinstance(m, Model)


def test_stub_predict_returns_majority() -> None:
    m = StubTransformerModel(["A", "B"], majority="A")
    preds = list(m.predict(["x", "y"]))
    assert preds == ["A", "A"]


def test_stub_predict_proba_shape() -> None:
    m = StubTransformerModel(["A", "B", "C"], majority="B")
    proba = m.predict_proba(["x", "y"])
    assert proba.shape == (2, 3)
    sums = proba.sum(axis=1)
    for s in sums:
        assert s == pytest.approx(1.0)


def test_stub_classes() -> None:
    m = StubTransformerModel(["A", "B"], majority="A")
    assert m.classes() == ["A", "B"]


def test_stub_save(tmp_path) -> None:
    m = StubTransformerModel(["A"], majority="A")
    m.save(tmp_path)
    assert (tmp_path / "TRANSFORMER_STUB.txt").exists()


def test_stub_model_kind() -> None:
    m = StubTransformerModel(["A"], majority="A")
    assert m.model_kind == "transformer"


def test_stub_feature_version_default() -> None:
    m = StubTransformerModel(["A"], majority="A")
    assert m.feature_version == "stub"


# ---------------------------------------------------------------------------
# Trainer settings dataclass
# ---------------------------------------------------------------------------
def test_trainer_settings_frozen() -> None:
    import dataclasses

    from chopcast.config import TransformerTextConfig, TransformerTrainConfig

    s = TransformerTrainerSettings(
        text_cfg=TransformerTextConfig(),
        train_cfg=TransformerTrainConfig(),
        output_dir=__import__("pathlib").Path("/tmp/x"),
        model_version="v1",
        feature_version="fv1",
    )
    assert s.model_version == "v1"
    # Frozen => __setattr__ raises FrozenInstanceError.
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.model_version = "v2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Lazy imports: import guard messages
# ---------------------------------------------------------------------------
def test_import_torch_raises_when_missing(monkeypatch) -> None:
    """When torch is uninstalled, calling _import_torch should raise a clear
    RuntimeError, not ImportError.
    """
    import builtins

    original = __import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "torch":
            raise ImportError("no torch")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="torch is required"):
        _import_torch()


def test_import_transformers_raises_when_missing(monkeypatch) -> None:
    import builtins

    original = __import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "transformers":
            raise ImportError("no transformers")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="transformers is required"):
        _import_transformers()


# ---------------------------------------------------------------------------
# Real TransformerDistilbert — skipif torch / transformers not installed
# ---------------------------------------------------------------------------
class _FakeModel:
    """Minimal stand-in for a HuggingFace model.

    Has `.device`, `.eval()`, `.to()`, and a `forward` method that
    returns logits-shaped tensors.
    """

    def __init__(self, classes: list[str], device: str = "cpu") -> None:
        self.classes = classes
        self.device = device
        # Map class index → position of argmax.
        self._always = 0

    def eval(self) -> None:
        return None

    def to(self, device: str) -> "_FakeModel":
        self.device = device
        return self

    def __call__(self, *, input_ids, attention_mask=None, labels=None):  # type: ignore[no-untyped-def]
        import torch

        batch = input_ids.shape[0]
        logits = torch.zeros(batch, len(self.classes), device=input_ids.device)
        logits[:, self._always] = 1.0
        return _FakeOutput(logits=logits)


class _FakeOutput:
    def __init__(self, logits) -> None:  # type: ignore[no-untyped-def]
        from chopcast.models.transformer_distilbert import _import_torch

        torch = _import_torch()
        self.logits = logits
        # Provide a fake "loss" attribute for the training loop.
        self.loss = torch.tensor(0.1)


class _FakeTokenizer:
    """Minimal stand-in for a HuggingFace tokenizer.

    Encodes as a list of ints derived from word length so that
    head-tail truncation is meaningful.
    """

    pad_token_id = 0
    eos_token = "</s>"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        # Fake tokens: 5 tokens per word.
        return [ord(c) % 1000 + 1 for c in text[:20]] * 5

    def pad(self, batch: dict, *, padding: bool = True, return_tensors: str = "pt") -> dict:
        # Pad all sequences to the longest one.
        import torch

        ids = batch["input_ids"]
        max_len = max(len(s) for s in ids)
        padded = [s + [0] * (max_len - len(s)) for s in ids]
        return {
            "input_ids": torch.tensor(padded, dtype=torch.long),
            "attention_mask": torch.tensor(
                [[1] * len(s) + [0] * (max_len - len(s)) for s in ids],
                dtype=torch.long,
            ),
        }

    def __call__(self, X, *, padding: bool = True, truncation: bool = True,
                 max_length: int = 128, return_tensors: str = "pt") -> dict:
        from chopcast.models.transformer_distilbert import _import_torch

        torch = _import_torch()
        encoded = [self.encode(text) for text in X]
        if truncation:
            encoded = [s[:max_length] for s in encoded]
        max_len = max(len(s) for s in encoded) if encoded else 1
        padded = [s + [0] * (max_len - len(s)) for s in encoded]
        return {
            "input_ids": torch.tensor(padded, dtype=torch.long),
            "attention_mask": torch.tensor(
                [[1] * len(s) + [0] * (max_len - len(s)) for s in encoded],
                dtype=torch.long,
            ),
        }

    def save_pretrained(self, path: str) -> None:  # type: ignore[no-untyped-def]
        from pathlib import Path

        Path(path).mkdir(parents=True, exist_ok=True)


@pytest.mark.skipif(
    not (_has_torch() and _has_transformers()),
    reason="torch/transformers not installed",
)
def test_transformer_predict_with_fakes(monkeypatch) -> None:
    """Build a TransformerDistilbert with fake model + tokenizer, then
    exercise predict / predict_proba. This validates the dispatch and
    output shape without needing real weights.
    """
    import torch

    fake_model = _FakeModel(["None", "Light"], device="cpu")
    fake_tok = _FakeTokenizer()
    m = TransformerDistilbert(
        model=fake_model,
        tokenizer=fake_tok,
        classes=["None", "Light"],
        model_version="v1",
        feature_version="fv1",
        max_length=64,
        truncation="head",
    )
    assert m.model_kind == "transformer"
    preds = list(m.predict(["hello world", "goodbye world"]))
    assert preds == ["None", "None"]
    proba = m.predict_proba(["hello world"])
    assert proba.shape == (1, 2)
    s = proba.sum(axis=1)[0]
    assert s == pytest.approx(1.0)


@pytest.mark.skipif(
    not (_has_torch() and _has_transformers()),
    reason="torch/transformers not installed",
)
def test_transformer_predict_empty() -> None:
    fake_model = _FakeModel(["None", "Light"])
    fake_tok = _FakeTokenizer()
    m = TransformerDistilbert(
        model=fake_model,
        tokenizer=fake_tok,
        classes=["None", "Light"],
        model_version="v1",
        feature_version="fv1",
    )
    assert list(m.predict([])) == []
    assert m.predict_proba([]).shape == (0,)


@pytest.mark.skipif(
    not (_has_torch() and _has_transformers()),
    reason="torch/transformers not installed",
)
def test_transformer_save_creates_manifest(tmp_path) -> None:
    fake_model = _FakeModel(["A", "B"])
    fake_tok = _FakeTokenizer()
    m = TransformerDistilbert(
        model=fake_model,
        tokenizer=fake_tok,
        classes=["A", "B"],
        model_version="v_x",
        feature_version="fv_x",
        max_length=42,
        truncation="head_tail",
    )
    m.save(tmp_path)
    manifest = (tmp_path / "chopcast_manifest.txt").read_text()
    assert "model_version=v_x" in manifest
    assert "truncation=head_tail" in manifest
    assert "max_length=42" in manifest
    assert "classes=A,B" in manifest


@pytest.mark.skipif(
    not (_has_torch() and _has_transformers()),
    reason="torch/transformers not installed",
)
def test_transformer_train_rejects_empty() -> None:
    from chopcast.config import TransformerTextConfig, TransformerTrainConfig

    text_cfg = TransformerTextConfig()
    train_cfg = TransformerTrainConfig()
    with pytest.raises(ValueError, match="cannot train on empty"):
        TransformerDistilbert.train(
            [],
            [],
            text_cfg=text_cfg,
            train_cfg=train_cfg,
            model_version="v",
            feature_version="fv",
        )


@pytest.mark.skipif(
    not (_has_torch() and _has_transformers()),
    reason="torch/transformers not installed",
)
def test_transformer_train_rejects_length_mismatch() -> None:
    from chopcast.config import TransformerTextConfig, TransformerTrainConfig

    with pytest.raises(ValueError, match="X and y must have the same length"):
        TransformerDistilbert.train(
            ["a", "b"],
            ["A"],
            text_cfg=TransformerTextConfig(),
            train_cfg=TransformerTrainConfig(),
            model_version="v",
            feature_version="fv",
        )
