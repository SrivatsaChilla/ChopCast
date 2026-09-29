"""Dataset versioning.

A processed dataset is identified by the tuple
`(parser_version, labeler_version, cleaner_version, feature_builder_version)`.
The version is also a content hash of the configuration that produced
the dataset, so any rule change forces a new version.

See `docs/DATA_ENGINEERING.md` §3.1.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from chopcast.config import ProcessingConfig


@dataclass(frozen=True)
class DatasetVersion:
    """The four version strings plus a short content fingerprint."""

    parser: str
    labeler: str
    cleaner: str
    features: str
    content_hash: str

    def as_path_suffix(self) -> str:
        return (
            f"parser-{self.parser}_"
            f"labeler-{self.labeler}_"
            f"cleaner-{self.cleaner}_"
            f"features-{self.features}_"
            f"{self.content_hash[:8]}"
        )

    def __str__(self) -> str:
        return self.as_path_suffix()


def derive_version(config: ProcessingConfig, *, salt: str = "") -> DatasetVersion:
    """Derive a version from a `ProcessingConfig`.

    The `salt` argument is a string the caller can pass to force a
    re-version (e.g. when the golden corpus is extended).
    """
    h = hashlib.sha256()
    payload = (
        f"{config.parser_version}|"
        f"{config.labeler_version}|"
        f"{config.cleaner_version}|"
        f"{config.feature_builder_version}|"
        f"{tuple(config.cleaner.strip_fields)}|"
        f"{config.cleaner.lowercase}|"
        f"{config.cleaner.collapse_whitespace}|"
        f"{tuple(config.features.altitude_bands)}|"
        f"{salt}"
    ).encode("utf-8")
    h.update(payload)
    return DatasetVersion(
        parser=config.parser_version,
        labeler=config.labeler_version,
        cleaner=config.cleaner_version,
        features=config.feature_builder_version,
        content_hash=h.hexdigest(),
    )


__all__ = ["DatasetVersion", "derive_version"]