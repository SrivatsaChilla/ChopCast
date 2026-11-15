"""Label distributions and a clearly-labelled rule preview.

The dashboard does not run the parser or the labeler. It reads the stored
``turbulence``/``turbulence_2`` columns and applies ``configs/labeling.yaml``
as a *preview*, labelled as such in the UI.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from adapters.settings import AdapterSettings
from adapters.sqlite_ro import ReadOnlyDatabase, SourceError
from adapters.types import (
    LabelCount,
    LabelDistribution,
    Result,
    SourceState,
    SourceStatus,
    TrainableVariant,
)

_ORDER = {"None": 0, "Light": 1, "Moderate": 2, "Severe": 3}


def _status(
    key: str,
    label: str,
    state: SourceState,
    detail: str = "",
    path: str = "",
    provenance: str | None = None,
) -> SourceStatus:
    return SourceStatus(key=key, label=label, state=state, detail=detail, path=path, provenance=provenance)


class _Rules:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.version: str | None = None
        self.patterns: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {}
        self.combination = "max"
        self.chop_only = "light"
        self.unknown = "none"
        self.error: str | None = None
        self._load()

    def _load(self) -> None:
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("labeling rules must be a mapping")
            self.version = str(data.get("version")) if data.get("version") else None
            for key, label in (
                ("none", "None"),
                ("light", "Light"),
                ("moderate", "Moderate"),
                ("severe", "Severe"),
            ):
                raw = data.get(key) or []
                compiled = tuple(
                    (str(p), re.compile(re.escape(str(p)), re.IGNORECASE))
                    for p in raw
                    if str(p).strip()
                )
                self.patterns[label] = compiled
            self.combination = str(data.get("combination_strategy") or "max")
            self.chop_only = str(data.get("chop_only_label") or "light")
            self.unknown = str(data.get("unknown_strategy") or "none")
        except (OSError, ValueError, yaml.YAMLError, TypeError) as exc:
            self.error = str(exc)

    def map(self, value: str | None) -> tuple[str, str]:
        if value is None or not str(value).strip():
            return "None", "empty"
        raw = str(value).strip()
        upper = raw.upper()
        if upper == "CHOP":
            return ("Light" if self.chop_only == "light" else "None"), "chop_only"
        hits: list[tuple[str, str]] = []
        for label, patterns in self.patterns.items():
            for pattern, compiled in patterns:
                if compiled.search(upper):
                    hits.append((label, pattern))
                    break
        if not hits:
            return ("Moderate" if self.unknown == "moderate" else "None"), "unknown"
        if len(hits) == 1:
            return hits[0][0], hits[0][1]
        if self.combination == "first":
            return hits[0][0], hits[0][1]
        key = max if self.combination == "max" else min
        winner = key(hits, key=lambda item: _ORDER.get(item[0], 0))
        return winner[0], winner[1]


class LabelService:
    def __init__(self, settings: AdapterSettings) -> None:
        self.settings = settings
        self.db = ReadOnlyDatabase(settings.raw_db)
        self._rules: _Rules | None = None

    def rules(self) -> _Rules:
        if self._rules is None:
            self._rules = _Rules(self.settings.config_dir / "labeling.yaml")
        return self._rules

    def _profile(self):
        from adapters.schema_probe import probe_raw_db

        return probe_raw_db(self.db)

    # ------------------------------------------------------------------
    def distribution(self) -> Result[LabelDistribution]:
        profile = self._profile()
        if not self.db.exists or "reports" not in profile.tables:
            return Result(
                None,
                _status("labels", "Labels", SourceState.MISSING if not self.db.exists else SourceState.SCHEMA_MISMATCH),
            )
        rules = self.rules()
        try:
            total = int(self.db.scalar("SELECT COUNT(*) FROM reports", default=0))
            primary = self._counts("turbulence", profile.reports_columns, rules)
            secondary = self._counts("turbulence_2", profile.reports_columns, rules)
            types = self._counts("turbulence_type", profile.reports_columns, rules)
            freqs = self._counts("turbulence_freq", profile.reports_columns, rules)
            combined: dict[str, int] = {}
            for row in self.db.query(
                "SELECT COALESCE(turbulence, turbulence_2) AS v, COUNT(*) AS n "
                "FROM reports WHERE COALESCE(turbulence, turbulence_2) IS NOT NULL "
                "GROUP BY COALESCE(turbulence, turbulence_2)"
            ):
                label, _ = rules.map(row["v"])
                combined[label] = combined.get(label, 0) + int(row["n"])
            labelled = int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM reports WHERE turbulence IS NOT NULL OR turbulence_2 IS NOT NULL",
                    default=0,
                )
            )
        except SourceError as exc:
            return Result(None, _status("labels", "Labels", SourceState.ERROR, str(exc)))

        warnings: list[str] = []
        if rules.error:
            warnings.append(f"labeling.yaml could not be read: {rules.error}")
        if secondary:
            warnings.append(
                "The secondary layer exists in the database, but process() currently ignores it (ISS-009)."
            )
        if profile.trainable_predicate == "primary_only":
            warnings.append("The live trainable view uses the primary-only predicate (ISS-003).")
        elif profile.trainable_predicate == "either_layer":
            warnings.append("The trainable view uses either-layer semantics (ISS-003).")
        if total and not labelled:
            warnings.append("No rows have a turbulence label.")
        return Result(
            LabelDistribution(
                total=total,
                primary=tuple(primary),
                secondary=tuple(secondary),
                types=tuple(types),
                freqs=tuple(freqs),
                combined=combined,
                labelled=labelled,
                unlabelled=total - labelled,
                rules_version=rules.version,
                warnings=tuple(warnings),
            ),
            _status(
                "labels",
                "Labels",
                SourceState.OK if total else SourceState.EMPTY,
                f"{labelled:,} labelled / {total:,} reports",
            ),
        )

    def _counts(self, column: str, columns: tuple[str, ...], rules: _Rules) -> list[LabelCount]:
        if column not in columns:
            return []
        rows = self.db.query(
            f"SELECT {column} AS v, COUNT(*) AS n FROM reports "
            f"WHERE {column} IS NOT NULL GROUP BY {column} ORDER BY n DESC"
        )
        out: list[LabelCount] = []
        for row in rows:
            value = str(row["v"])
            label, rule = rules.map(value)
            out.append(LabelCount(value=value, count=int(row["n"]), mapped=label, rule=rule))
        return out

    # ------------------------------------------------------------------
    def trainable_variants(self) -> Result[list[TrainableVariant]]:
        profile = self._profile()
        if not self.db.exists or "reports" not in profile.tables:
            return Result(
                None,
                _status("trainable", "Trainable set", SourceState.MISSING if not self.db.exists else SourceState.SCHEMA_MISMATCH),
            )
        type_filter = ""
        if "report_type" in profile.reports_columns:
            type_filter = " AND report_type IN ('PIREP', 'Urgent PIREP')"
        variants: list[TrainableVariant] = []
        try:
            legacy = int(
                self.db.scalar(
                    f"SELECT COUNT(*) FROM reports WHERE turbulence IS NOT NULL{type_filter}",
                    default=0,
                )
            )
            either = int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM reports WHERE (turbulence IS NOT NULL OR turbulence_2 IS NOT NULL)"
                    + type_filter,
                    default=0,
                )
            )
            live = 0
            if "trainable" in profile.views:
                live = int(self.db.scalar("SELECT COUNT(*) FROM trainable", default=0))
        except SourceError as exc:
            return Result(None, _status("trainable", "Trainable set", SourceState.ERROR, str(exc)))
        variants.append(
            TrainableVariant(
                key="legacy",
                label="Legacy predicate (live)",
                predicate="turbulence IS NOT NULL" + type_filter,
                count=legacy,
                description="The predicate in the existing trainable view.",
            )
        )
        variants.append(
            TrainableVariant(
                key="either",
                label="Migration-3 predicate",
                predicate="turbulence IS NOT NULL OR turbulence_2 IS NOT NULL" + type_filter,
                count=either,
                description="The predicate defined by storage/migrations.py version 3.",
            )
        )
        if "trainable" in profile.views:
            variants.append(
                TrainableVariant(
                    key="live_view",
                    label="Live trainable view",
                    predicate=profile.views.get("trainable", ""),
                    count=live,
                    description="The count returned by the view that actually exists.",
                )
            )
        return Result(
            variants,
            _status("trainable", "Trainable set", SourceState.OK, f"{len(variants)} variants"),
        )

    # ------------------------------------------------------------------
    def status(self) -> SourceStatus:
        profile = self._profile()
        if not self.db.exists:
            return _status("labels", "Labels", SourceState.MISSING, "raw database missing")
        if "reports" not in profile.tables:
            return _status("labels", "Labels", SourceState.SCHEMA_MISMATCH, "reports table missing")
        try:
            total = int(self.db.scalar("SELECT COUNT(*) FROM reports", default=0))
        except SourceError as exc:
            return _status("labels", "Labels", SourceState.ERROR, str(exc))
        return _status(
            "labels",
            "Labels",
            SourceState.OK if total else SourceState.EMPTY,
            f"{total:,} reports",
        )

    def raw_value_preview(self, limit: int = 100) -> list[dict[str, Any]]:
        profile = self._profile()
        if "reports" not in profile.tables:
            return []
        try:
            return self.db.query(
                "SELECT turbulence AS value, 'primary' AS layer, COUNT(*) AS n FROM reports "
                "WHERE turbulence IS NOT NULL GROUP BY turbulence "
                "UNION ALL "
                "SELECT turbulence_2 AS value, 'secondary' AS layer, COUNT(*) AS n FROM reports "
                "WHERE turbulence_2 IS NOT NULL GROUP BY turbulence_2 "
                "ORDER BY n DESC LIMIT ?",
                (limit,),
            )
        except SourceError:
            return []
