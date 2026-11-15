"""Persisted evaluation metrics, comparison, and metric-shape normalisation.

The dashboard never evaluates anything. It reads the metric documents that the
pipeline already wrote and reports where each value came from. Shapes are
deliberately liberal because there is no schema/version field (ISS-087).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.registry import RegistryService
from adapters.settings import AdapterSettings
from adapters.types import (
    CompareField,
    CompareResult,
    EvaluationRecord,
    ModelRecord,
    Result,
    SourceState,
    SourceStatus,
)

NUMERIC_HINTS = (
    "accuracy",
    "macro_f1",
    "weighted_f1",
    "micro_f1",
    "f1",
    "precision",
    "recall",
    "n_samples",
    "samples",
    "loss",
)


@dataclass(frozen=True)
class ClassRow:
    label: str
    precision: float | None
    recall: float | None
    f1: float | None
    support: int | None


@dataclass(frozen=True)
class Confusion:
    labels: tuple[str, ...]
    matrix: tuple[tuple[int, ...], ...]

    @property
    def total(self) -> int:
        return sum(sum(row) for row in self.matrix)


def _status(
    key: str,
    label: str,
    state: SourceState,
    detail: str = "",
    path: str = "",
    provenance: str | None = None,
) -> SourceStatus:
    return SourceStatus(
        key=key, label=label, state=state, detail=detail, path=path, provenance=provenance
    )


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        if not path.is_file():
            return None, None
        if path.stat().st_size > 2_000_000:
            return None, "file is too large to display"
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "top-level JSON value is not an object"
    return data, None


def _get(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def numeric_metrics(metrics: dict[str, Any] | None) -> dict[str, float | int | str]:
    """Flatten the numeric top-level metrics worth showing, keeping source keys."""
    if not metrics:
        return {}
    out: dict[str, float | int | str] = {}
    for key, value in metrics.items():
        if key in {"per_class", "confusion", "labels", "extras"}:
            continue
        number = _num(value)
        if number is not None:
            out[str(key)] = int(number) if number.is_integer() and key in {"n_samples", "samples"} else number
        elif isinstance(value, str) and len(value) <= 80:
            out[str(key)] = value
    extras = metrics.get("extras")
    if isinstance(extras, dict):
        for key, value in extras.items():
            number = _num(value)
            if number is not None:
                out[f"extras.{key}"] = number
    return out


def class_rows(metrics: dict[str, Any] | None) -> tuple[ClassRow, ...]:
    if not metrics:
        return ()
    raw = _get(metrics, "per_class", "per_class_metrics", "class_metrics")
    rows: list[ClassRow] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = _get(item, "label", "class", "name", "label_name")
            if label is None:
                continue
            rows.append(
                ClassRow(
                    label=str(label),
                    precision=_num(_get(item, "precision", "prec")),
                    recall=_num(_get(item, "recall")),
                    f1=_num(_get(item, "f1", "f1_score")),
                    support=_int(_get(item, "support", "n", "count")),
                )
            )
    elif isinstance(raw, dict):
        for label, item in raw.items():
            if not isinstance(item, dict):
                continue
            rows.append(
                ClassRow(
                    label=str(label),
                    precision=_num(_get(item, "precision", "prec")),
                    recall=_num(_get(item, "recall")),
                    f1=_num(_get(item, "f1", "f1_score")),
                    support=_int(_get(item, "support", "n", "count")),
                )
            )
    return tuple(rows)


def confusion(metrics: dict[str, Any] | None) -> Confusion | None:
    if not metrics:
        return None
    raw = _get(metrics, "confusion", "confusion_matrix", "matrix")
    labels_raw: Any = None
    matrix_raw: Any = None
    if isinstance(raw, dict):
        labels_raw = _get(raw, "labels", "classes")
        matrix_raw = _get(raw, "matrix", "values", "counts")
    elif isinstance(raw, list):
        matrix_raw = raw
    if not isinstance(matrix_raw, list) or not matrix_raw:
        return None
    matrix: list[tuple[int, ...]] = []
    for row in matrix_raw:
        if not isinstance(row, list):
            return None
        matrix.append(tuple(int(_num(cell) or 0) for cell in row))
    labels: tuple[str, ...]
    if isinstance(labels_raw, list) and labels_raw:
        labels = tuple(str(x) for x in labels_raw)
    else:
        labels = tuple(str(i) for i in range(len(matrix)))
    if len(labels) != len(matrix):
        labels = tuple(str(i) for i in range(len(matrix)))
    return Confusion(labels=labels, matrix=tuple(matrix))


class EvaluationService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.registry = RegistryService(settings)

    # ------------------------------------------------------------------
    def status(self) -> SourceStatus:
        result = self.list_evaluations()
        return result.status

    def list_evaluations(self) -> Result[list[EvaluationRecord]]:
        models_result = self.registry.list_models()
        if models_result.data is None:
            return Result(None, models_result.status)
        records = [self._for_model(model) for model in models_result.data]
        with_metrics = [r for r in records if r.metrics]
        state = SourceState.OK if with_metrics else SourceState.EMPTY
        detail = (
            f"{len(with_metrics)}/{len(records)} model(s) have persisted metrics"
            if records
            else "no registry models"
        )
        return Result(
            records,
            _status("evaluation", "Evaluation", state, detail, provenance="persisted only"),
        )

    def get(self, model_id: int) -> Result[EvaluationRecord]:
        model_result = self.registry.get(model_id)
        if model_result.data is None:
            return Result(None, model_result.status)
        record = self._for_model(model_result.data)
        state = SourceState.OK if record.metrics else SourceState.EMPTY
        return Result(
            record,
            _status(
                "evaluation",
                "Evaluation",
                state,
                f"model {model_id}",
                provenance=record.source,
            ),
        )

    def previous(self, record: EvaluationRecord) -> EvaluationRecord | None:
        result = self.list_evaluations()
        if not result.data:
            return None
        older = [r for r in result.data if r.model_id < record.model_id and r.metrics]
        return older[0] if older else None

    def compare(self, a_id: int, b_id: int) -> Result[CompareResult]:
        a_result = self.get(a_id)
        if a_result.data is None:
            return Result(None, a_result.status)
        b_result = self.get(b_id)
        if b_result.data is None:
            return Result(None, b_result.status)
        a, b = a_result.data, b_result.data
        warnings: list[str] = []
        if a.feature_version != b.feature_version:
            warnings.append(
                f"Feature versions differ ({a.feature_version or 'unknown'} vs "
                f"{b.feature_version or 'unknown'}); the comparison is not like-for-like."
            )
        if a.model_kind != b.model_kind:
            warnings.append(
                f"Model kinds differ ({a.model_kind or 'unknown'} vs {b.model_kind or 'unknown'})."
            )
        if not a.metrics or not b.metrics:
            warnings.append("One or both models have no persisted metrics.")
        fields: list[CompareField] = []
        a_nums = numeric_metrics(a.metrics)
        b_nums = numeric_metrics(b.metrics)
        keys = list(dict.fromkeys([*a_nums.keys(), *b_nums.keys()]))
        for key in keys:
            av, bv = a_nums.get(key), b_nums.get(key)
            delta = None
            if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                delta = float(bv) - float(av)
            fields.append(CompareField(name=key, a=av, b=bv, delta=delta))
        return Result(
            CompareResult(a=a, b=b, fields=tuple(fields), warnings=tuple(warnings)),
            _status("evaluation", "Comparison", SourceState.OK, f"{a_id} vs {b_id}"),
        )

    # ------------------------------------------------------------------
    def _for_model(self, model: ModelRecord) -> EvaluationRecord:
        artifact = Path(model.artifact_resolved) if model.artifact_resolved else None
        metrics: dict[str, Any] | None = None
        source = "none"
        warnings: list[str] = list(model.warnings)

        metrics_json, metrics_error = _read_json(artifact / "metrics.json") if artifact else (None, None)
        report_json, report_error = _read_json(artifact / "report.json") if artifact else (None, None)
        if metrics_error:
            warnings.append(f"metrics.json could not be parsed: {metrics_error}")
        if report_error:
            warnings.append(f"report.json could not be parsed: {report_error}")

        if metrics_json is not None:
            metrics = metrics_json
            source = "metrics.json"
        elif report_json is not None:
            metrics = report_json
            source = "report.json"
        elif model.metrics:
            metrics = model.metrics
            source = "registry.metrics_json"

        duplicates = [name for name, value in (
            ("metrics.json", metrics_json),
            ("report.json", report_json),
            ("registry.metrics_json", model.metrics),
        ) if value]
        if len(duplicates) > 1:
            warnings.append(
                "Metrics are stored in multiple places ("
                + ", ".join(duplicates)
                + ") with no schema version (ISS-087)"
            )
        if metrics is None:
            warnings.append("No persisted evaluation found")

        return EvaluationRecord(
            model_id=model.id,
            model_version=model.model_version,
            model_kind=model.model_kind,
            feature_version=model.feature_version,
            registered_at=model.registered_at,
            metrics=metrics,
            source=source,
            warnings=tuple(dict.fromkeys(warnings)),
        )
