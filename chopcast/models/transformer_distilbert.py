"""DistilBERT-based severity classifier.

This module is the transformer sibling of `baseline_sklearn`. It
implements the same `Model` protocol so the inference layer can swap
between them based on a config flag, no code change required.

Heavy imports (`torch`, `transformers`) are lazy: they only happen
inside `train()` and `predict()`. The module loads cleanly on a
machine without those packages; in that environment callers fall
back to `BaselineSklearn` or `StubTransformerModel` for tests.

PIREP-specific truncation: a typical cleaned PIREP fits well within
DistilBERT's 512-token window, but a transformer that hits `max_length`
mid-field wastes attention on truncated tokens. We configure a small
`max_length` (default 128) with `head_tail` truncation so the model
always sees the start (location, time) and end (severity-bearing
remarks) of the report.

See `docs/MODULE_DESIGN.md` §7.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from chopcast.config import TransformerTextConfig, TransformerTrainConfig
from chopcast.logging import get_logger
from chopcast.models.protocol import Model

log = get_logger(__name__)


def _import_torch() -> object:
    """Lazy import torch. Raises a clear error if not installed."""
    try:
        import torch  # noqa: F401
    except ImportError as e:  # pragma: no cover - import guard
        raise RuntimeError(
            "torch is required for the transformer model. "
            "Install with `pip install torch transformers`."
        ) from e
    return torch


def _import_transformers() -> object:
    """Lazy import transformers. Raises a clear error if not installed."""
    try:
        import transformers  # noqa: F401
    except ImportError as e:  # pragma: no cover - import guard
        raise RuntimeError(
            "transformers is required for the transformer model. "
            "Install with `pip install torch transformers`."
        ) from e
    return transformers


# ---------------------------------------------------------------------------
# Trainer configuration helper
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TransformerTrainerSettings:
    """What `train_transformer` needs to set up HuggingFace's Trainer."""

    text_cfg: TransformerTextConfig
    train_cfg: TransformerTrainConfig
    output_dir: Path
    model_version: str
    feature_version: str

# ---------------------------------------------------------------------------
# Stub model (for tests / lightweight fallback)
# ---------------------------------------------------------------------------
class StubTransformerModel:
    """A trivial transformer-shaped model used by tests.

    Same behaviour as `StubModel` — predicts the majority class. The
    model_kind is "transformer" so the registry can distinguish it.
    """

    def __init__(self, classes: list[str], majority: str, *, feature_version: str = "stub") -> None:
        self._classes = list(classes)
        self._majority = majority
        self.model_version = "transformer-stub-1"
        self.model_kind = "transformer"
        self.feature_version = feature_version

    def predict(self, X: list[str]) -> np.ndarray:
        return np.array([self._majority] * len(X), dtype=object)

    def predict_proba(self, X: list[str]) -> np.ndarray:
        rows = []
        for _ in X:
            row = [1.0 if c == self._majority else 0.0 for c in self._classes]
            rows.append(row)
        return np.array(rows, dtype=float)

    def classes(self) -> list[str]:
        return list(self._classes)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "TRANSFORMER_STUB.txt").write_text("stub transformer model\n")


# ---------------------------------------------------------------------------
# Real DistilBERT model
# ---------------------------------------------------------------------------
class TransformerDistilbert:
    """A fine-tuned DistilBERT classifier satisfying the `Model` protocol.

    Construction is split:
    - `from_pretrained(path)` — load a saved model for inference.
    - `train(...)` — fine-tune from a base checkpoint and persist.

    The model is wrapped in a tiny adapter so the prediction methods
    accept `list[str]` (matching the protocol) instead of tokenised
    inputs.
    """

    def __init__(
        self,
        *,
        model: object,
        tokenizer: object,
        classes: list[str],
        model_version: str,
        feature_version: str,
        max_length: int = 128,
        truncation: str = "head_tail",
    ) -> None:
        self._model = model
        self._tokenizer = tokenizer
        self._classes = list(classes)
        self.model_version = model_version
        self.model_kind = "transformer"
        self.feature_version = feature_version
        self._max_length = max_length
        self._truncation = truncation

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def _tokenize(self, X: list[str]) -> dict[str, object]:
        if self._truncation == "head_tail":
            # Encode each input fully, then keep only the first and
            # last `max_length//2` tokens. Falls back to "head" if the
            # input is shorter than max_length.
            max_len = self._max_length
            half = max_len // 2
            batch: list[list[int]] = []
            for text in X:
                ids = self._tokenizer.encode(text, add_special_tokens=False)
                if len(ids) > max_len:
                    ids = ids[:half] + ids[-(max_len - half):]
                batch.append(ids)
            return self._tokenizer.pad(
                {"input_ids": batch},
                padding=True,
                return_tensors="pt",
            )
        # Default: "head" truncation. We accept "head" / "tail" / "head_tail".
        return self._tokenizer(
            X,
            padding=True,
            truncation=True,
            max_length=self._max_length,
            return_tensors="pt",
        )

    def predict(self, X: list[str]) -> np.ndarray:
        if not X:
            return np.array([], dtype=object)
        torch = _import_torch()
        self._model.eval()
        with torch.no_grad():
            inputs = self._tokenize(X)
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
            logits = self._model(**inputs).logits
            idx = torch.argmax(logits, dim=-1).cpu().numpy()
        return np.array([self._classes[i] for i in idx], dtype=object)

    def predict_proba(self, X: list[str]) -> np.ndarray:
        if not X:
            return np.array([], dtype=float)
        torch = _import_torch()
        self._model.eval()
        with torch.no_grad():
            inputs = self._tokenize(X)
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
            logits = self._model(**inputs).logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
        return probs

    def classes(self) -> list[str]:
        return list(self._classes)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self._model.save_pretrained(str(path))
        self._tokenizer.save_pretrained(str(path))
        (path / "chopcast_manifest.txt").write_text(
            f"model_version={self.model_version}\n"
            f"model_kind={self.model_kind}\n"
            f"feature_version={self.feature_version}\n"
            f"classes={','.join(self._classes)}\n"
            f"max_length={self._max_length}\n"
            f"truncation={self._truncation}\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "TransformerDistilbert":
        transformers = _import_transformers()
        manifest_lines = (path / "chopcast_manifest.txt").read_text(encoding="utf-8").splitlines()
        manifest = {}
        for line in manifest_lines:
            if "=" in line:
                k, _, v = line.partition("=")
                manifest[k.strip()] = v.strip()
        tokenizer = transformers.AutoTokenizer.from_pretrained(str(path))
        model = transformers.AutoModelForSequenceClassification.from_pretrained(str(path))
        classes = manifest.get("classes", "").split(",") if manifest.get("classes") else []
        return cls(
            model=model,
            tokenizer=tokenizer,
            classes=classes,
            model_version=manifest.get("model_version", "unknown"),
            feature_version=manifest.get("feature_version", "unknown"),
            max_length=int(manifest.get("max_length", "128")),
            truncation=manifest.get("truncation", "head_tail"),
        )

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    @classmethod
    def train(
        cls,
        X: list[str],
        y: list[str],
        text_cfg: TransformerTextConfig,
        train_cfg: TransformerTrainConfig,
        *,
        model_version: str,
        feature_version: str,
        output_dir: Path | None = None,
    ) -> "TransformerDistilbert":
        """Fine-tune DistilBERT on (X, y).

        Returns a `TransformerDistilbert` ready to save and predict.
        """
        torch = _import_torch()
        transformers = _import_transformers()

        if not X:
            raise ValueError("cannot train on empty X")
        if len(X) != len(y):
            raise ValueError(f"X and y must have the same length, got {len(X)} vs {len(y)}")

        # Sort classes so the label->id mapping is deterministic.
        classes = sorted(set(y))
        label2id = {label: i for i, label in enumerate(classes)}

        tokenizer = transformers.AutoTokenizer.from_pretrained(text_cfg.model_name)
        model = transformers.AutoModelForSequenceClassification.from_pretrained(
            text_cfg.model_name,
            num_labels=len(classes),
            id2label={i: label for label, i in label2id.items()},
            label2id=label2id,
        )

        # Tokenize once up front. Truncation is "longest_first" — for
        # PIREPs this is usually fine since most fit under max_length.
        encodings = tokenizer(
            X,
            truncation=True,
            padding=True,
            max_length=text_cfg.max_length,
            return_tensors="pt",
        )
        labels = torch.tensor([label2id[label] for label in y], dtype=torch.long)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        model.train()

        optim = torch.optim.AdamW(model.parameters(), lr=5e-5)
        dataset = torch.utils.data.TensorDataset(
            encodings["input_ids"], encodings["attention_mask"], labels
        )
        loader = torch.utils.data.DataLoader(
            dataset, batch_size=train_cfg.batch_size, shuffle=True
        )

        epochs = train_cfg.epochs
        log.info(
            "transformer.training_start",
            n_train=len(X),
            epochs=epochs,
            batch_size=train_cfg.batch_size,
            device=device,
        )
        for epoch in range(epochs):
            epoch_loss = 0.0
            n_batches = 0
            for input_ids, attention_mask, batch_labels in loader:
                input_ids = input_ids.to(device)
                attention_mask = attention_mask.to(device)
                batch_labels = batch_labels.to(device)
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=batch_labels,
                )
                loss = outputs.loss
                loss.backward()
                optim.step()
                optim.zero_grad()
                epoch_loss += float(loss.item())
                n_batches += 1
            avg = epoch_loss / max(n_batches, 1)
            log.info("transformer.epoch_done", epoch=epoch + 1, loss=avg)

        trained = cls(
            model=model,
            tokenizer=tokenizer,
            classes=classes,
            model_version=model_version,
            feature_version=feature_version,
            max_length=text_cfg.max_length,
            truncation=text_cfg.truncation,
        )
        if output_dir is not None:
            trained.save(output_dir)
        return trained


__all__ = [
    "StubTransformerModel",
    "TransformerDistilbert",
    "TransformerTrainerSettings",
]


# Re-export Model so users have a single import path.
__all__.append("Model")


# Type checks: confirm both model classes satisfy the protocol at import time.
def _check_protocol() -> None:  # pragma: no cover
    from chopcast.models.protocol import Model as _M

    assert isinstance(StubTransformerModel(["A"], "A"), _M)
    # TransformerDistilbert cannot be instantiated without torch/transformers,
    # so we only check StubTransformerModel here. Real model conformance is
    # validated in tests.


_check_protocol()