"""Polymarket-specific types."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Supported assets and their slug prefixes for 15m markets
ASSET_PREFIXES_15M = {
    "btc": "btc-updown-15m",
    "eth": "eth-updown-15m",
    "sol": "sol-updown-15m",
    "xrp": "xrp-updown-15m",
}

SUPPORTED_ASSETS = list(ASSET_PREFIXES_15M.keys())


@dataclass
class PolymarketMarket:
    """
    Polymarket market metadata.

    UP/DOWN terminology used per exchange-native conventions.
    """

    condition_id: str
    slug: str
    question: str
    closed: bool = False
    description: Optional[str] = None
    winning_outcome: Optional[str] = None
    uma_resolution_status: Optional[str] = None
    end_date_iso: Optional[str] = None
    clob_token_ids: List[str] = field(default_factory=list)
    outcomes: List[str] = field(default_factory=list)
    outcome_prices: Optional[List[float]] = None

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "PolymarketMarket":
        """
        Create market from Gamma API response.

        Args:
            data: Raw market data from API

        Returns:
            PolymarketMarket instance
        """
        # Parse JSON string fields
        clob_token_ids = []
        try:
            clob_token_ids = json.loads(data.get("clobTokenIds", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass

        outcomes = []
        try:
            outcomes = json.loads(data.get("outcomes", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass

        # Parse outcome prices if available
        outcome_prices = None
        if "outcomePrices" in data and data["outcomePrices"]:
            try:
                prices_str = json.loads(data["outcomePrices"])
                outcome_prices = [float(p) for p in prices_str]
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        return cls(
            condition_id=data["conditionId"],
            slug=data["slug"],
            question=data["question"],
            closed=data.get("closed", False),
            description=data.get("description"),
            winning_outcome=data.get("winning_outcome"),
            uma_resolution_status=data.get("umaResolutionStatus"),
            end_date_iso=data.get("endDateIso") or data.get("end_date_iso"),
            clob_token_ids=clob_token_ids,
            outcomes=outcomes,
            outcome_prices=outcome_prices,
        )

    def is_resolved(self) -> bool:
        """Check if market is resolved."""
        if self.uma_resolution_status == "resolved":
            return True
        return self.closed and self.winning_outcome is not None

    def get_winning_outcome(self) -> Optional[str]:
        """
        Get the winning outcome if market is resolved.

        Returns:
            Winning outcome string (e.g., 'Up' or 'Down'), or None if not resolved
        """
        if not self.is_resolved():
            return None

        if self.winning_outcome:
            return self.winning_outcome

        # Derive from outcome prices (winning outcome has price = 1.0)
        if self.outcome_prices and self.outcomes:
            for i, price in enumerate(self.outcome_prices):
                if price >= 0.99 and i < len(self.outcomes):
                    return self.outcomes[i]

        return None

    def get_token_id(self, direction: str) -> Optional[str]:
        """
        Get CLOB token ID for a direction.

        Args:
            direction: 'Up' or 'Down'

        Returns:
            CLOB token ID, or None if not found
        """
        try:
            index = self.outcomes.index(direction)
            if index < len(self.clob_token_ids):
                return self.clob_token_ids[index]
        except ValueError:
            logger.warning(f"Direction '{direction}' not found in outcomes: {self.outcomes}")
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
            Seconds remaining, or None if end_date not available
        """
        if not self.end_date_iso:
            return None

        try:
            from datetime import timezone

            end_dt = datetime.fromisoformat(self.end_date_iso.replace("Z", "+00:00"))
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
    return "Down" if direction == "Up" else "Up"
