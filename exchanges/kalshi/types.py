"""Kalshi-specific types and constants."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

# API endpoints
API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"

# Series tickers for 15-minute crypto markets
SERIES_TICKERS = {
    "BTC": "KXBTC15M",
    "ETH": "KXETH15M",
    "SOL": "KXSOL15M",
}

SUPPORTED_ASSETS = list(SERIES_TICKERS.keys())


@dataclass
class KalshiMarket:
    """
    Kalshi market metadata.

    YES/NO terminology used per exchange-native conventions.
    """

    ticker: str
    close_time: datetime
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    status: str = "open"

    @classmethod
    def from_api_response(cls, data: Dict) -> "KalshiMarket":
        """
        Create market from API response.

        Args:
            data: Raw market data from API

        Returns:
            KalshiMarket instance
        """
        close_time_str = data.get("close_time", "")
        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))

        return cls(
            ticker=data.get("ticker", ""),
            close_time=close_time,
            yes_bid=data.get("yes_bid"),
            yes_ask=data.get("yes_ask"),
            no_bid=data.get("no_bid"),
            no_ask=data.get("no_ask"),
            status=data.get("status", "open"),
        )

    def get_seconds_remaining(self) -> int:
        """Get seconds until market closes."""
        from datetime import timezone

        now = datetime.now(timezone.utc)
        delta = self.close_time - now
        return max(0, int(delta.total_seconds()))

    @property
    def is_open(self) -> bool:
        """Check if market is open."""
        return self.status == "open" and self.get_seconds_remaining() > 0


@dataclass
class OrderbookUpdate:
    """Orderbook update from WebSocket."""

    timestamp_ms: int
    market_ticker: str
    asset: str

    # YES side (price goes UP)
    yes_bid: Optional[float] = None
    yes_bid_size: Optional[int] = None
    yes_ask: Optional[float] = None
    yes_ask_size: Optional[int] = None

    # NO side (price goes DOWN)
    no_bid: Optional[float] = None
    no_bid_size: Optional[int] = None
    no_ask: Optional[float] = None
    no_ask_size: Optional[int] = None
