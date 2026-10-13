from __future__ import annotations

import requests
import re
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass

from chopcast.config import Settings

logger = logging.getLogger(__name__)

@dataclass
class MetarObservation:
    \"\"\"Parsed METAR observation.

    Note: METAR parsing is complex; this is a simplified version focusing on
    turbulence-relevant features.
    \"\"\"
    station_id: str
    time: str
    wind_speed: Optional[float]
    wind_direction: Optional[float]
    temperature: Optional[float]
    pressure: Optional[float]
    raw_text: str

class MetarProvider:
    \"\"\"Fetch and parse METAR data from the Aviation Weather Center (AWC).
    \"\"\"
    def __init__(self, settings: Settings):
        self.settings = settings
        self.url = settings.weather.metar.source_url
        self.user_agent = settings.collector.user_agent

    def fetch_metars(self, station_ids: list[str]) -> list[MetarObservation]:
        \"\"\"Fetch METARs for specific stations.
        \"\"\"
        params = {"ids": ",".join(station_ids)}
        try:
            response = requests.get(
                self.url,
                params=params,
                headers={"User-Agent": self.user_agent},
                timeout=10
            )
            response.raise_for_status()

            # The AWC API returns a list of METAR strings
            # This is a simplified parsing logic
            return self._parse_metar_responses(response.text, station_ids)
        except requests.RequestException as e:
            logger.error(f"Failed to fetch METARs: {e}")
            return []

    def _parse_metar_responses(self, text: str, ids: list[str]) -> list[MetarObservation]:
        \"\"\"Robust regex-based METAR parser.

        Extracts:
        - Date/Time: 101200Z (10th day, 12:00 UTC)
        - Wind: <dir><speed>KT or <dir>G<speed>KT
        - Temp: T<temp>/<dew>
        - Pressure: Q<pressure>
        \"\"\"
        observations = []
        lines = text.splitlines()

        # METARs only contain day, hour, min. We assume current month/year.
        from datetime import datetime
        now = datetime.utcnow()
        year, month = now.year, now.month

        for line in lines:
            if not line.strip():
                continue

            station_id = None
            for sid in ids:
                if sid in line:
                    station_id = sid
                    break

            if not station_id:
                continue

            # Time: e.g., 101200Z
            time_match = re.search(r'(\d{2})(\d{2})(\d{2})(\d{2})Z', line)
            obs_time = "2026-10-10T12:00:00Z" # Fallback
            if time_match:
                try:
                    day, hour, minute, second = map(int, time_match.groups())
                    dt = datetime(year, month, day, hour, minute, second)
                    obs_time = dt.isoformat() + "Z"
                except (ValueError, TypeError):
                    pass

            # Wind: e.g., 24015KT or 24015G25KT
            wind_match = re.search(r'(\d{3})(\d{2,3})(?:G(\d{2,3}))?KT', line)
            wind_dir, wind_spd = None, None
            if wind_match:
                wind_dir = float(wind_match.group(1))
                wind_spd = float(wind_match.group(2))

            # Temp: e.g., T15/M02 (15C / -2C)
            temp_match = re.search(r'T([MS]?\d{2})/([MS]?\d{2})', line)
            temp = None
            if temp_match:
                t_str = temp_match.group(1)
                temp = float(t_str.replace('M', '-').replace('S', ''))

            # Pressure: e.g., Q1013
            press_match = re.search(r'Q(\d{4})', line)
            press = float(press_match.group(1)) if press_match else None

            observations.append(MetarObservation(
                station_id=station_id,
                time=obs_time,
                wind_speed=wind_spd,
                wind_direction=wind_dir,
                temperature=temp,
                pressure=press,
                raw_text=line
            ))
        return observations

__all__ = ["MetarProvider"]
