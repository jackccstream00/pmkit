"""Polymarket market finder.

Discovers current and next 15-minute UP/DOWN markets.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from pmkit.exchanges.polymarket.types import (
    ASSET_PREFIXES_15M,
    SUPPORTED_ASSETS,
    PolymarketMarket,
)

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"


class MarketFinder:
    """
    Find 15-minute UP/DOWN markets on Polymarket.

    Usage:
        finder = MarketFinder()
        # Smart market (next before boundary, current after)
        market = await finder.get_smart_market("btc")
        # Explicit next market
        next_market = await finder.get_next_market("btc")
        # Explicit current interval market
        slug = finder.get_current_slug("btc")
        market = await finder.fetch_by_slug(slug)
    """

    def __init__(self, timeout: float = 10.0):
        """
        Initialize market finder.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout

    def _get_slug_prefix(self, asset: str) -> Optional[str]:
        """Get slug prefix for asset."""
        asset_lower = asset.lower()
        if asset_lower not in ASSET_PREFIXES_15M:
            logger.error(f"Unsupported asset: {asset}. Supported: {SUPPORTED_ASSETS}")
            return None
        return ASSET_PREFIXES_15M[asset_lower]

    def generate_slug(self, timestamp: int, prefix: str) -> str:
        """
        Generate market slug from timestamp.

        Args:
            timestamp: Unix timestamp of market start time
            prefix: Market slug prefix (e.g., 'btc-updown-15m')

        Returns:
            Market slug (e.g., 'btc-updown-15m-1700000000')
        """
        return f"{prefix}-{timestamp}"

    def get_current_interval_start(self) -> int:
        """Get Unix timestamp of current 15-min interval start."""
        now = int(datetime.now(timezone.utc).timestamp())
        interval = 15 * 60
        return (now // interval) * interval

    def get_next_interval_start(self) -> int:
        """Get Unix timestamp of next 15-min interval start."""
        now = int(datetime.now(timezone.utc).timestamp())
        interval = 15 * 60
        return ((now // interval) + 1) * interval

    def get_current_slug(self, asset: str) -> Optional[str]:
        """Get slug for current 15-min market."""
        prefix = self._get_slug_prefix(asset)
        if not prefix:
            return None
        return self.generate_slug(self.get_current_interval_start(), prefix)

    def get_next_slug(self, asset: str) -> Optional[str]:
        """Get slug for next 15-min market."""
        prefix = self._get_slug_prefix(asset)
        if not prefix:
            return None
        return self.generate_slug(self.get_next_interval_start(), prefix)

    def get_smart_slug(self, asset: str) -> Optional[str]:
        """
        Get market slug using intelligent time-based selection.

        Before 15-min boundary: returns NEXT market (for early trigger)
        At/after boundary: returns CURRENT market

        This ensures correct market selection for both early and on-time triggers.

        Args:
            asset: Asset symbol (btc, eth, sol, xrp)

        Returns:
            Market slug for appropriate interval
        """
        prefix = self._get_slug_prefix(asset)
        if not prefix:
            return None

        now = int(datetime.now(timezone.utc).timestamp())
        interval = 15 * 60
        next_boundary = ((now // interval) + 1) * interval

        if now < next_boundary:
            return self.generate_slug(self.get_next_interval_start(), prefix)
        else:
            return self.generate_slug(self.get_current_interval_start(), prefix)

    async def fetch_by_slug(self, slug: str) -> Optional[PolymarketMarket]:
        """
        Fetch market by slug from Gamma API.

        Args:
            slug: Market slug

        Returns:
            PolymarketMarket or None if not found
        """
        try:
            url = f"{GAMMA_API}/markets/slug/{slug}"
            logger.debug(f"Fetching market: {url}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)

                if response.status_code == 404:
                    logger.warning(f"Market not found: {slug}")
                    return None

                response.raise_for_status()
                data = response.json()

                if not data:
                    logger.error(f"No data returned for market: {slug}")
                    return None

                market = PolymarketMarket.from_api_response(data)
                logger.info(f"Fetched market: {market.slug}")
                logger.debug(f"  Outcomes: {market.outcomes}")
                logger.debug(f"  Token IDs: {market.clob_token_ids}")

                return market

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch market {slug}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing market data for {slug}: {e}")
            return None

    async def get_smart_market(self, asset: str) -> Optional[PolymarketMarket]:
        """
        Get market using smart time-based selection.

        Uses smart slug selection:
        - Before 15-min boundary: returns NEXT market
        - At/after boundary: returns CURRENT market

        This is intended for trading bots that need to act on the upcoming market.

        Args:
            asset: Asset symbol (btc, eth, sol, xrp)

        Returns:
            PolymarketMarket or None if not found
        """
        slug = self.get_smart_slug(asset)
        if not slug:
            return None

        logger.info(f"Looking for smart market: {slug}")
        return await self.fetch_by_slug(slug)

    async def get_next_market(self, asset: str) -> Optional[PolymarketMarket]:
        """
        Get next 15-minute market for an asset.

        Args:
            asset: Asset symbol (btc, eth, sol, xrp)

        Returns:
            PolymarketMarket or None if not found
        """
        slug = self.get_next_slug(asset)
        if not slug:
            return None

        logger.info(f"Looking for next market: {slug}")
        return await self.fetch_by_slug(slug)

    def get_seconds_until_next_boundary(self) -> int:
        """Get seconds until next 15-minute boundary."""
        now = int(datetime.now(timezone.utc).timestamp())
        next_boundary = self.get_next_interval_start()
        return max(0, next_boundary - now)

    def get_seconds_since_boundary(self) -> int:
        """Get seconds since last 15-minute boundary."""
        now = int(datetime.now(timezone.utc).timestamp())
        current_start = self.get_current_interval_start()
        return now - current_start
