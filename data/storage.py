"""CSV storage for OHLCV data.

Features:
- Pure OHLCV storage (no labels, no features)
- Append mode for live data accumulation
- Simple CSV format for human readability
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd

from pmkit.data.binance.types import Candle

logger = logging.getLogger(__name__)


class CSVStorage:
    """
    Simple CSV storage for OHLCV data.

    Usage:
        storage = CSVStorage(Path("data/btc_1s.csv"))

        # Save candles
        storage.save(candles)

        # Load data
        df = storage.load()

        # Append single candle (for live trading)
        storage.append(candle)
    """

    COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

    def __init__(self, path: Union[str, Path]):
        """
        Initialize storage.

        Args:
            path: Path to CSV file
        """
        self.path = Path(path)

    def save(
        self,
        data: Union[pd.DataFrame, List[Candle]],
        append: bool = False,
    ) -> None:
        """
        Save data to CSV.

        Args:
            data: DataFrame or list of Candle objects
            append: If True, append to existing file
        """
        # Convert Candles to DataFrame if needed
        if isinstance(data, list) and data and isinstance(data[0], Candle):
            df = pd.DataFrame([c.to_ohlcv_dict() for c in data])
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            raise ValueError("data must be DataFrame or List[Candle]")

        # Ensure columns
        df = df[self.COLUMNS]

        # Create directory if needed
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Save
        mode = "a" if append and self.path.exists() else "w"
        header = not (append and self.path.exists())

        df.to_csv(self.path, mode=mode, header=header, index=False)

        logger.debug(f"Saved {len(df)} rows to {self.path} (append={append})")

    def append(self, candle: Candle) -> None:
        """
        Append a single candle to the file.

        Args:
            candle: Candle to append
        """
        self.save([candle], append=True)

    def load(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Load data from CSV.

        Args:
            start: Filter from this datetime
            end: Filter to this datetime

        Returns:
            DataFrame with OHLCV columns
        """
        if not self.path.exists():
            logger.warning(f"File not found: {self.path}")
            return pd.DataFrame(columns=self.COLUMNS)

        df = pd.read_csv(self.path)

        # Parse timestamp
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Filter by time range
        if start is not None:
            df = df[df["timestamp"] >= start]
        if end is not None:
            df = df[df["timestamp"] <= end]

        # Sort and deduplicate
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
        df = df.reset_index(drop=True)

        logger.debug(f"Loaded {len(df)} rows from {self.path}")

        return df

    def get_latest_timestamp(self) -> Optional[datetime]:
        """
        Get the timestamp of the most recent candle.

        Returns:
            Latest timestamp, or None if file is empty
        """
        if not self.path.exists():
            return None

        df = pd.read_csv(self.path)

        if df.empty:
            return None

        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df["timestamp"].max()

    def exists(self) -> bool:
        """Check if the CSV file exists."""
        return self.path.exists()

    def count(self) -> int:
        """Get number of rows in the file."""
        if not self.path.exists():
            return 0

        # Count lines (excluding header)
        with open(self.path) as f:
            return sum(1 for _ in f) - 1
