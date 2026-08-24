# ADR-0005: A single Model protocol abstracts baseline and transformer

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

The roadmap has two models: a TF-IDF + LogReg baseline (M3) and a DistilBERT classifier (M4). They have very different implementations: the baseline is a scikit-learn pipeline with a vectorizer and a linear model; the transformer is a HuggingFace model with tokenization, attention masks, and (optionally) GPU inference.

The naive approach is to have the inference API and the dashboard branch on `model_kind == "baseline" vs "transformer"`. The consequence is that every downstream component grows a `match` statement, and adding a third model (e.g., a smaller distilled model for low-latency inference) requires editing every consumer.

The naive approach also lets the two implementations diverge. A baseline that accepts `list[str]` and a transformer that accepts `np.ndarray` are not interchangeable. Subtle differences in tokenization, padding, or label encoding will surface as bugs at the integration boundary, far from the trainer.

## Decision

There is a single `Model` protocol, owned by the consumer (`chopcast.inference`), not by the producer. Both `BaselineSklearn` and `TransformerDistilBERT` implement it structurally — no `implements Model` declaration, just the same set of methods.

```python
class Model(Protocol):
    feature_version: str
    model_version: str
    model_kind: str

    def predict(self, X: list[str]) -> np.ndarray: ...
    def predict_proba(self, X: list[str]) -> np.ndarray: ...
    def classes(self) -> list[str]: ...
```

Properties:

- `predict` accepts `list[str]` (raw clean text). The model is responsible for its own tokenization or vectorization. The API does not know whether the model is doing TF-IDF or subword tokenization.
- `predict_proba` returns probabilities, not logits. The model applies softmax if necessary.
- `classes()` returns the canonical class list. Both models return `["None", "Light", "Moderate", "Severe"]` in that order.
- `feature_version` is the version of the feature store the model was trained on. The inference API checks this against the requested feature version (if any) and warns on mismatch.
- `model_kind` is for observability, not control flow. The API does not branch on it.

The protocol is `@runtime_checkable`. A test asserts that both concrete models satisfy the protocol at runtime. A new model that does not satisfy it cannot be registered.

The `Predictor` (the public surface of the model system) takes a `Model` and is not generic over the model's kind. It exposes `predict(raw_text, context) -> Prediction`. Adding a new model requires zero changes to the API, the dashboard, or the evaluator.

## Consequences

**Positive**

- The API, the dashboard, the evaluator, and the drift detector depend on `Model`, not on any concrete implementation. Swapping models is a registry change, not a code change.
- A new model (e.g., a smaller distilled transformer, a calibrated random forest) is added by writing one class that satisfies the protocol. No existing module is touched.
- The test `tests/unit/models/test_protocol.py` proves the contract holds for every concrete model. A regression in either implementation fails the build.
- Model comparison (`chopcast-eval compare baseline-v3 transformer-v2`) is trivial: load both, call `predict` on the same input, diff the outputs. No special handling per kind.

**Negative**

- The protocol is a lowest-common-denominator interface. It cannot expose model-specific capabilities (e.g., attention weights for explainability). If we need those, we add a separate `ExplainableModel` protocol that extends `Model`. Models that do not implement it simply are not used through that path.
- The protocol says `list[str]` is the input. If a future model needs structured features (e.g., flight level, aircraft type) directly, the protocol has to evolve. We mitigate by accepting an optional `context: dict` in `Predictor.predict()` (not in `Model.predict()`). Models that do not use it ignore it.
- The structural typing means a typo in a method signature is not caught at import time. The `runtime_checkable` decorator catches it at the first `isinstance` check, which is the test in `test_protocol.py`.

**Mitigations**

- `test_protocol.py` is run on every PR. It is a small test, but it is the keystone of the abstraction.
- A model card (a markdown file in the registry entry) documents the model's actual interface, including any deviations from the protocol's contract. The protocol is the floor; the card is the ceiling.

## Alternatives considered

**Abstract base class with `predict` and `predict_proba` as virtual methods.** Rejected: structural typing is more flexible. A new implementation does not need to import the abstract class, and an existing class (e.g., a third-party model we wrap) can be made to satisfy the protocol without modification.

**One interface per model kind**, with a dispatcher. Rejected: this is the "naive approach" that the decision is explicitly rejecting. A dispatcher is just a match statement with extra steps.

**Force the protocol to be richer** (e.g., `predict_with_attention`, `predict_with_embeddings`). Rejected: the principle is "smallest interface that does the job." Richer interfaces can be added as separate protocols.

**No abstraction; pass the concrete class around.** Rejected: the cost of the abstraction is one protocol definition; the cost of no abstraction is repeated `if model_kind == ...` blocks in every consumer.

## References

- `docs/ML_ARCHITECTURE.md` §2
- `docs/MODULE_DESIGN.md` §7
- `docs/TESTING.md` §3.3
