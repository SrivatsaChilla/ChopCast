"""Golden corpus loader.

The golden corpus is a hand-curated set of PIREPs with expected parse
output, used by `test_parser_golden.py`. For M1 the corpus is empty;
M2 will populate it from a couple of weeks of collected data plus a
handwritten set covering the long tail (CHOP only, /RM with embedded
slashes, /TB ranges, etc.).

See `docs/MODULE_DESIGN.md` §3.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from chopcast.parser.pirep import PirepFields


@dataclass(frozen=True)
class GoldenCase:
    """One row in the golden corpus."""

    raw: str
    expected: PirepFields
    source: str  # provenance, e.g. "AWC 2026-01"


def load_golden(path: Path | None = None) -> list[GoldenCase]:
    """Load the golden corpus from disk. Empty list if the file is absent."""
    if path is None or not path.exists():
        return []
    cases: list[GoldenCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: <source>\t<raw>\t<expected>
        # For now we just record provenance + raw; expected is recomputed
        # by the test fixture. M2 will fill in expected.
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        cases.append(
            GoldenCase(raw=parts[1], expected=PirepFields(raw=parts[1], **{  # type: ignore[arg-type]
                "location": None,
                "location_parsed": None,
                "obs_time": None,
                "flight_level": None,
                "aircraft_type": None,
                "turbulence": None,
                "sky_conditions": None,
                "weather": None,
                "temperature": None,
                "icing": None,
                "remarks": None,
            }), source=parts[0])
        )
    return cases


__all__ = ["GoldenCase", "load_golden"]