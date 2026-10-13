from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
from chopcast.config import Settings

@dataclass
class WeatherCache:
    \"\"\"Local Parquet-based cache for METAR observations.
    \"\"\"
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache_path = settings.to_paths().weather_cache_path

    def store_observations(self, df: pd.DataFrame):
        \"\"\"Store a batch of METAR observations to the Parquet cache.
        \"\"\"
        if self.cache_path.exists():
            existing_df = pd.read_parquet(self.cache_path)
            df = pd.concat([existing_df, df]).drop_duplicates(subset=['station_id', 'time'])

        df.to_parquet(self.cache_path, index=False)

    def get_observations_for_time_range(self, start_time: str, end_time: str) -> pd.DataFrame:
        \"\"\"Retrieve observations within a specific time window.
        \"\"\"
        if not self.cache_path.exists():
            return pd.DataFrame()

        df = pd.read_parquet(self.cache_path)
        # Ensure time is datetime for filtering
        df['time'] = pd.to_datetime(df['time'])
        mask = (df['time'] >= pd.to_datetime(start_time)) & (df['time'] <= pd.to_datetime(end_time))
        return df.loc[mask]

    def cleanup(self):
        \"\"\"Remove observations older than the retention period.
        \"\"\"
        if not self.cache_path.exists():
            return

        df = pd.read_parquet(self.cache_path)
        df['time'] = pd.to_datetime(df['time'])
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=self.settings.weather.cache.retention_days)
        df = df[df['time'] >= cutoff]
        df.to_parquet(self.cache_path, index=False)
