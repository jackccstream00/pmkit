"""Binance data types.

Pure OHLCV data structures - no labels, no features.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Interval(Enum):
    """Binance kline intervals."""

    SECOND_1 = "1s"
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"

    @property
    def seconds(self) -> int:
        """Get interval duration in seconds."""
        mapping = {
            "1s": 1,
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return mapping[self.value]


@dataclass
class Candle:
    """
    OHLCV candle data.

    Pure data structure - no labels, no computed features.
    """

    timestamp: datetime  # Candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float

    # Optional metadata
    symbol: Optional[str] = None
    interval: Optional[str] = None
    close_time: Optional[datetime] = None
    quote_volume: Optional[float] = None
    trades: Optional[int] = None
    taker_buy_base: Optional[float] = None
    taker_buy_quote: Optional[float] = None

    @classmethod
    def from_binance_kline(cls, kline: list, symbol: str = "", interval: str = "") -> "Candle":
        """
        Create Candle from Binance kline response.

        Binance kline format:
        [
            0: open_time (ms),
            1: open,
            2: high,
            3: low,
            4: close,
            5: volume,
            6: close_time (ms),
            7: quote_volume,
            8: trades,
            9: taker_buy_base,
            10: taker_buy_quote,
            11: ignore
        ]
        """
        return cls(
            timestamp=datetime.fromtimestamp(kline[0] / 1000),
            open=float(kline[1]),
            high=float(kline[2]),
            low=float(kline[3]),
            close=float(kline[4]),
            volume=float(kline[5]),
            symbol=symbol,
            interval=interval,
            close_time=datetime.fromtimestamp(kline[6] / 1000),
            quote_volume=float(kline[7]),
            trades=int(kline[8]),
            taker_buy_base=float(kline[9]),
            taker_buy_quote=float(kline[10]),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for CSV/DataFrame."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
            "interval": self.interval,
        }

    def to_ohlcv_dict(self) -> dict:
        """Convert to pure OHLCV dictionary (minimal)."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


# Standard symbols with USDT pairs
SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
    "ADA": "ADAUSDT",
    "LTC": "LTCUSDT",
    "BNB": "BNBUSDT",
}


def get_symbol(asset: str) -> str:
    """
    Get Binance symbol for an asset.

    Args:
        asset: Asset name (e.g., "BTC", "ETH")

    Returns:
        Binance symbol (e.g., "BTCUSDT")
    """
    asset_upper = asset.upper()
    if asset_upper in SYMBOLS:
        return SYMBOLS[asset_upper]
    # Assume USDT pair if not in map
    if not asset_upper.endswith("USDT"):
        return f"{asset_upper}USDT"
    return asset_upper
