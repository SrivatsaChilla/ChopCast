from __future__ import annotations

import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from chopcast.config import Settings
from chopcast.weather.features import WeatherFeatures

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    \"\"\"Calculate the great circle distance between two points in kilometers.
    \"\"\"
    R = 6371.0  # Earth radius in km
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)

    a = np.sin(dphi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2)**2
    return 2 * R * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

class WeatherMatcher:
    \"\"\"Spatial-temporal matcher for fusing PIREPs with METAR observations.
    \"\"\"
    def __init__(self, settings: Settings):
        self.settings = settings
        self.max_dist = settings.weather.metar.max_distance_km
        self.max_time = settings.weather.metar.max_time_delta_minutes

    def find_nearest(self, pirep_lat: float, pirep_lon: float, pirep_time: str, observations: list) -> Optional[WeatherFeatures]:
        \"\"\"Find the closest METAR observation within spatial and temporal bounds.
        \"\"\"
        import pandas as pd

        best_station = None
        min_dist = float('inf')

        # Convert pirep_time to pandas timestamp for comparison
        p_time = pd.to_datetime(pirep_time)

        for obs in observations:
            # 1. Temporal Filter
            o_time = pd.to_datetime(obs['time'])
            time_delta = abs((p_time - o_time).total_seconds()) / 60.0
            if time_delta > self.max_time:
                continue

            # 2. Spatial Filter
            dist = haversine_distance(pirep_lat, pirep_lon, obs['lat'], obs['lon'])
            if dist > self.max_dist:
                continue

            if dist < min_dist:
                min_dist = dist
                best_station = obs

        if not best_station:
            return None

        return WeatherFeatures(
            wind_speed=best_station.get('wind_speed'),
            wind_direction=best_station.get('wind_direction'),
            temperature=best_station.get('temperature'),
            pressure=best_station.get('pressure'),
            station_id=best_station.get('station_id')
        )

__all__ = ["WeatherMatcher"]
