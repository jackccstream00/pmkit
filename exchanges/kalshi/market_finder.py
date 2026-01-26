"""Kalshi market finder.

Discovers current and next 15-minute crypto markets.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from pmkit.exchanges.kalshi.types import (
    API_BASE,
    SERIES_TICKERS,
    SUPPORTED_ASSETS,
    KalshiMarket,
)

logger = logging.getLogger(__name__)


class MarketFinder:
    """
    Find 15-minute crypto markets on Kalshi.

    Usage:
        finder = MarketFinder()
        market = await finder.get_current_market("BTC")
        markets = await finder.get_current_markets(["BTC", "ETH"])
    """

    def __init__(self, timeout: float = 10.0):
        """
        Initialize market finder.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout

    def _get_series_ticker(self, asset: str) -> Optional[str]:
        """Get series ticker for asset."""
        asset_upper = asset.upper()
        if asset_upper not in SERIES_TICKERS:
            logger.error(f"Unsupported asset: {asset}. Supported: {SUPPORTED_ASSETS}")
            return None
        return SERIES_TICKERS[asset_upper]

    async def get_current_market(self, asset: str) -> Optional[KalshiMarket]:
        """
        Get current open 15-minute market for an asset.

        Returns the market expiring soonest (current 15-min period).

        Args:
            asset: Asset symbol (BTC, ETH, SOL)

        Returns:
            KalshiMarket or None if not found
        """
        series_ticker = self._get_series_ticker(asset)
        if not series_ticker:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{API_BASE}/markets",
                    params={
                        "series_ticker": series_ticker,
                        "status": "open",
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Failed to fetch markets: {response.status_code}")
                    return None

                data = response.json()
                markets_list = data.get("markets", [])

                if not markets_list:
                    logger.debug(f"No open markets found for {series_ticker}")
                    return None

                # Find market expiring soonest
                now = datetime.now(timezone.utc)
                earliest_market = None
                earliest_close = None

                for m in markets_list:
                    ticker = m.get("ticker")
                    close_time_str = m.get("close_time")

                    if not ticker or not close_time_str:
                        continue

                    try:
                        close_time = datetime.fromisoformat(
                            close_time_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        continue

                    # Only consider markets that haven't closed
                    if close_time <= now:
                        continue

                    if earliest_close is None or close_time < earliest_close:
                        earliest_close = close_time
                        earliest_market = KalshiMarket.from_api_response(m)

                if earliest_market:
                    logger.info(f"Found market: {earliest_market.ticker}")

                return earliest_market

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch markets for {asset}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching market for {asset}: {e}")
            return None

    async def get_current_markets(
        self, assets: List[str]
    ) -> Dict[str, KalshiMarket]:
        """
        Get current open markets for multiple assets.

        Args:
            assets: List of asset symbols (e.g., ["BTC", "ETH"])

        Returns:
            Dict mapping asset -> KalshiMarket
        """
        markets = {}

        for asset in assets:
            market = await self.get_current_market(asset)
            if market:
                markets[asset.upper()] = market

        return markets

    async def get_next_market(self, asset: str) -> Optional[KalshiMarket]:
        """
        Get next 15-minute market for an asset.

        Returns the market expiring second-soonest.

        Args:
            asset: Asset symbol (BTC, ETH, SOL)

        Returns:
            KalshiMarket or None if not found
        """
        series_ticker = self._get_series_ticker(asset)
        if not series_ticker:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{API_BASE}/markets",
                    params={
                        "series_ticker": series_ticker,
                        "status": "open",
                    },
                )

                if response.status_code != 200:
                    return None

                data = response.json()
                markets_list = data.get("markets", [])

                if len(markets_list) < 2:
                    return None

                # Sort by close time and get second-soonest
                now = datetime.now(timezone.utc)
                valid_markets = []

                for m in markets_list:
                    close_time_str = m.get("close_time")
                    if not close_time_str:
                        continue

                    try:
                        close_time = datetime.fromisoformat(
                            close_time_str.replace("Z", "+00:00")
                        )
                        if close_time > now:
                            valid_markets.append((close_time, m))
                    except ValueError:
                        continue

                valid_markets.sort(key=lambda x: x[0])

                if len(valid_markets) >= 2:
                    return KalshiMarket.from_api_response(valid_markets[1][1])

                return None

        except Exception as e:
            logger.error(f"Error fetching next market for {asset}: {e}")
            return None
