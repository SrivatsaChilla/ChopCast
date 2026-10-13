from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class WeatherFeatures:
    \"\"\"Structured weather features extracted from a METAR observation.

    These features represent the atmospheric state at the time and location
    of a PIREP report.
    \"\"\"
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    temperature: Optional[float] = None
    pressure: Optional[float] = None
    station_id: Optional[str] = None
