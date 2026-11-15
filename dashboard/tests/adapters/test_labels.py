from __future__ import annotations

from adapters.labels import LabelService
from adapters.settings import AdapterSettings
from adapters.types import SourceState


def test_distribution_and_rules(full_settings):
    service = LabelService(full_settings)
    result = service.distribution()
    assert result.data is not None
    distribution = result.data
    assert distribution.total == 6
    assert distribution.labelled == 4
    assert distribution.unlabelled == 2
    assert distribution.rules_version == "v1"
    assert distribution.combined == {"None": 1, "Light": 1, "Moderate": 1, "Severe": 1}
    assert {item.mapped for item in distribution.primary} == {"None", "Light", "Moderate", "Severe"}
    assert distribution.warnings


def test_trainable_variants(full_settings):
    variants = LabelService(full_settings).trainable_variants()
    assert variants.data is not None
    counts = {variant.key: variant.count for variant in variants.data}
    assert counts == {"legacy": 3, "either": 3, "live_view": 3}


def test_missing_database(tmp_path):
    service = LabelService(AdapterSettings.from_env(tmp_path / "missing"))
    result = service.distribution()
    assert result.data is None
    assert result.status.state is SourceState.MISSING
    assert service.raw_value_preview() == []
