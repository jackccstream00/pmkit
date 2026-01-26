"""Predict.fun-specific types."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# API endpoints
API_BASE = "https://api.predict.fun"
API_BASE_TESTNET = "https://api-testnet.predict.fun"
WS_URL = "wss://ws.predict.fun/ws"
WS_URL_TESTNET = "wss://ws-testnet.predict.fun/ws"

# Supported assets for daily crypto up/down markets
SUPPORTED_ASSETS = ["btc", "eth", "sol"]


@dataclass
class PredictfunMarket:
    """
    Predict.fun market metadata.

    Up/Down terminology used per exchange-native conventions.
    """

    market_id: int
    title: str
    condition_id: str
    is_neg_risk: bool
    is_yield_bearing: bool
    fee_rate_bps: int
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "OPEN"
    ends_at: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "PredictfunMarket":
        """
        Create market from API response.

        Args:
            data: Raw market data from API

        Returns:
            PredictfunMarket instance
        """
        return cls(
            market_id=data["id"],
            title=data.get("title", ""),
            condition_id=data.get("conditionId", ""),
            is_neg_risk=data.get("isNegRisk", False),
            is_yield_bearing=data.get("isYieldBearing", False),
            fee_rate_bps=data.get("feeRateBps", 0),
            outcomes=data.get("outcomes", []),
            status=data.get("status", "OPEN"),
            ends_at=data.get("endsAt"),
        )

    def get_token_id(self, direction: str) -> Optional[str]:
        """
        Get on-chain token ID for a direction.

        Args:
            direction: 'Up' or 'Down'

        Returns:
            Token ID (onChainId), or None if not found
        """
        direction_lower = direction.lower()
        for outcome in self.outcomes:
            name = outcome.get("name", "").lower()
            if name == direction_lower:
                return outcome.get("onChainId")
        logger.warning(f"Direction '{direction}' not found in outcomes")
        return None

    def get_index_set(self, direction: str) -> Optional[int]:
        """
        Get index set for a direction.

        Args:
            direction: 'Up' or 'Down'

        Returns:
            Index set (1 or 2), or None if not found
        """
        direction_lower = direction.lower()
        for outcome in self.outcomes:
            name = outcome.get("name", "").lower()
            if name == direction_lower:
                return outcome.get("indexSet")
        return None

    @property
    def up_token_id(self) -> Optional[str]:
        """Get token ID for UP outcome."""
        return self.get_token_id("Up")

    @property
    def down_token_id(self) -> Optional[str]:
        """Get token ID for DOWN outcome."""
        return self.get_token_id("Down")

    @property
    def tokens(self) -> Dict[str, str]:
        """Get tokens dict for BaseExchange.Market compatibility."""
        result = {}
        if self.up_token_id:
            result["UP"] = self.up_token_id
        if self.down_token_id:
            result["DOWN"] = self.down_token_id
        return result

    def get_seconds_remaining(self) -> Optional[int]:
        """
        Get seconds until market closes.

        Returns:
            Seconds remaining, or None if ends_at not available
        """
        if not self.ends_at:
            return None

        try:
            end_dt = datetime.fromisoformat(self.ends_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = (end_dt - now).total_seconds()
            return max(0, int(delta))
        except (ValueError, TypeError):
            return None


def get_opposite_direction(direction: str) -> str:
    """
    Get the opposite direction.

    Args:
        direction: 'Up' or 'Down'

    Returns:
        Opposite direction
    """
    return "Down" if direction.lower() == "up" else "Up"
