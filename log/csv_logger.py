"""CSV trade logging.

Abstract CSV logger that strategies can customize with their own columns.
Provides consistent file handling and path management.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pmkit.log.paths import PathManager


class CSVLogger:
    """
    Generic CSV logger with consistent file handling.

    Usage:
        logger = CSVLogger(
            path_manager=path_manager,
            name="trades",
            columns=["timestamp", "asset", "side", "price", "size", "order_id"],
        )
        logger.log_row({
            "timestamp": datetime.now(),
            "asset": "BTC",
            "side": "UP",
            "price": 0.55,
            "size": 10.0,
            "order_id": "abc123",
        })
    """

    def __init__(
        self,
        path_manager: PathManager,
        name: str = "trades",
        columns: Optional[List[str]] = None,
        directory: str = "trades",
    ):
        """
        Initialize CSV logger.

        Args:
            path_manager: PathManager for file paths.
            name: Base name for the CSV file.
            columns: Column headers. If None, first log_row() call defines them.
            directory: Subdirectory under base_dir.
        """
        self.path_manager = path_manager
        self.name = name
        self.directory = directory
        self.columns = columns

        self._file_path: Optional[Path] = None
        self._file_handle = None
        self._writer = None
        self._current_date: Optional[str] = None

    def _get_file_path(self) -> Path:
        """Get the current CSV file path."""
        if self.directory == "trades":
            return self.path_manager.get_trades_path(self.name)
        return self.path_manager.get_custom_path(
            directory=self.directory,
            name=self.name,
            extension="csv",
        )

    def _ensure_file(self) -> None:
        """Ensure file is open and writer is ready, handle daily rotation."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Check if we need to rotate (new day)
        if self._current_date != today:
            self.close()
            self._current_date = today

        if self._file_handle is None:
            self._file_path = self._get_file_path()
            file_exists = self._file_path.exists()

            self._file_handle = open(self._file_path, "a", newline="")
            self._writer = csv.DictWriter(
                self._file_handle,
                fieldnames=self.columns or [],
                extrasaction="ignore",
            )

            # Write header if new file and columns are defined
            if not file_exists and self.columns:
                self._writer.writeheader()
                self._file_handle.flush()

    def log_row(self, data: Dict[str, Any]) -> None:
        """
        Log a row to the CSV file.

        Args:
            data: Dictionary with column names as keys.
        """
        # Auto-detect columns from first row if not set
        if self.columns is None:
            self.columns = list(data.keys())

        self._ensure_file()

        # Convert datetime objects to strings
        row = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                row[key] = value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            else:
                row[key] = value

        self._writer.writerow(row)
        self._file_handle.flush()

    def log_rows(self, rows: List[Dict[str, Any]]) -> None:
        """
        Log multiple rows to the CSV file.

        Args:
            rows: List of dictionaries with column names as keys.
        """
        for row in rows:
            self.log_row(row)

    def close(self) -> None:
        """Close the file handle."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
            self._writer = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


class TradeLogger(CSVLogger):
    """
    Specialized CSV logger for trade records.

    Pre-defined columns for common trade data.
    """

    DEFAULT_COLUMNS = [
        "timestamp",
        "asset",
        "market_id",
        "direction",
        "side",
        "price",
        "size",
        "order_id",
        "status",
        "filled_size",
        "filled_price",
    ]

    def __init__(
        self,
        path_manager: PathManager,
        name: str = "trades",
        extra_columns: Optional[List[str]] = None,
    ):
        """
        Initialize trade logger.

        Args:
            path_manager: PathManager for file paths.
            name: Base name for the CSV file.
            extra_columns: Additional columns beyond the defaults.
        """
        columns = self.DEFAULT_COLUMNS.copy()
        if extra_columns:
            columns.extend(extra_columns)

        super().__init__(
            path_manager=path_manager,
            name=name,
            columns=columns,
            directory="trades",
        )

    def log_trade(
        self,
        asset: str,
        direction: str,
        price: float,
        size: float,
        order_id: str,
        status: str = "placed",
        market_id: str = "",
        side: str = "BUY",
        filled_size: Optional[float] = None,
        filled_price: Optional[float] = None,
        **extra,
    ) -> None:
        """
        Log a trade with standard fields.

        Args:
            asset: Asset symbol (e.g., "BTC")
            direction: Trade direction (e.g., "UP", "DOWN", "YES", "NO")
            price: Order price
            size: Order size in USD or contracts
            order_id: Exchange order ID
            status: Order status (placed, filled, cancelled, etc.)
            market_id: Market/condition ID
            side: BUY or SELL
            filled_size: Filled size (if known)
            filled_price: Average fill price (if known)
            **extra: Additional fields for extra_columns
        """
        data = {
            "timestamp": datetime.now(timezone.utc),
            "asset": asset,
            "market_id": market_id,
            "direction": direction,
            "side": side,
            "price": price,
            "size": size,
            "order_id": order_id,
            "status": status,
            "filled_size": filled_size,
            "filled_price": filled_price,
            **extra,
        }
        self.log_row(data)
