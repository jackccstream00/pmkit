"""Predict.fun market finder.

Discovers daily crypto UP/DOWN markets.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from pmkit.exchanges.predictfun.types import (
    API_BASE,
    API_BASE_TESTNET,
    SUPPORTED_ASSETS,
    PredictfunMarket,
)

logger = logging.getLogger(__name__)


class MarketFinder:
    """
    Find crypto UP/DOWN markets on Predict.fun.

    Usage:
        finder = MarketFinder()
        # Get current open market for BTC
        market = await finder.get_current_market("btc")
        up_token = market.up_token_id
        down_token = market.down_token_id
    """

    def __init__(
        self,
        api_base: str = API_BASE,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
    ):
        """
        Initialize market finder.

        Args:
            api_base: API base URL (mainnet or testnet)
            api_key: Optional API key
            timeout: HTTP request timeout in seconds
        """
        self.api_base = api_base
        self.api_key = api_key
        self.timeout = timeout

    async def get_markets(
        self,
        variant: str = "CRYPTO_UP_DOWN",
        status: str = "OPEN",
    ) -> List[PredictfunMarket]:
        """
        Get all markets matching criteria.

        Args:
            variant: Market variant (e.g., "CRYPTO_UP_DOWN")
            status: Market status filter ("OPEN", "CLOSED", "RESOLVED")

        Returns:
            List of PredictfunMarket objects
        """
        headers = {}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_base}/v1/markets",
                    params={
                        "marketVariant": variant,
                        "status": status,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                markets = []
                for item in data.get("markets", data) if isinstance(data, dict) else data:
                    try:
                        markets.append(PredictfunMarket.from_api_response(item))
                    except Exception as e:
                        logger.warning(f"Failed to parse market: {e}")

                return markets

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    async def get_current_market(self, asset: str) -> Optional[PredictfunMarket]:
        """
        Get current open market for an asset.

        Args:
            asset: Asset symbol (btc, eth, sol)

        Returns:
            PredictfunMarket or None if not found
        """
        asset_lower = asset.lower()
        if asset_lower not in SUPPORTED_ASSETS:
            logger.error(f"Unsupported asset: {asset}. Supported: {SUPPORTED_ASSETS}")
            return None

        markets = await self.get_markets(status="OPEN")

        # Filter by asset in title (case-insensitive)
        asset_upper = asset.upper()
        matching = [
            m for m in markets
            if asset_upper in m.title.upper()
            and ("UP" in m.title.upper() or "DOWN" in m.title.upper())
        ]

        if not matching:
            logger.warning(f"No open market found for {asset}")
            return None

        # Sort by ends_at ascending (earliest first)
        matching.sort(key=lambda m: m.ends_at or "9999")

        market = matching[0]
        logger.info(f"Found market: {market.title} (ID: {market.market_id})")
        return market

    async def get_all_current_markets(self) -> List[PredictfunMarket]:
        """
        Get current open markets for all supported assets.

        Returns:
            List of PredictfunMarket objects
        """
        markets = []
        for asset in SUPPORTED_ASSETS:
            market = await self.get_current_market(asset)
            if market:
                markets.append(market)
        return markets

    async def get_market_by_id(self, market_id: int) -> Optional[PredictfunMarket]:
        """
        Get market by ID.

        Args:
            market_id: Market ID

        Returns:
            PredictfunMarket or None if not found
        """
        headers = {}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_base}/v1/markets/{market_id}",
                    headers=headers,
                )

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                data = response.json()
                return PredictfunMarket.from_api_response(data)

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch market {market_id}: {e}")
            return None

    async def search_markets(
        self,
        query: str,
        status: str = "OPEN",
    ) -> List[PredictfunMarket]:
        """
        Search markets by title.

        Args:
            query: Search query
            status: Market status filter

        Returns:
            List of matching PredictfunMarket objects
        """
        headers = {}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_base}/v1/markets",
                    params={
                        "search": query,
                        "status": status,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                markets = []
                for item in data.get("markets", data) if isinstance(data, dict) else data:
                    try:
                        markets.append(PredictfunMarket.from_api_response(item))
                    except Exception as e:
                        logger.warning(f"Failed to parse market: {e}")

                return markets

        except httpx.RequestError as e:
            logger.error(f"Market search failed: {e}")
            return []
