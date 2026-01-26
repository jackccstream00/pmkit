"""Base exchange abstract class.

Defines the interface that all exchange implementations must follow.
Provides building blocks only - no strategy logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class OrderSide(Enum):
    """Order side."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """Order to place on exchange."""
    token_id: str
    side: OrderSide
    size: float  # Size in USD or contracts
    order_type: OrderType = OrderType.LIMIT
    price: Optional[float] = None  # Required for limit orders

    # Optional metadata
    market_id: Optional[str] = None
    direction: Optional[str] = None  # "UP"/"DOWN" or "yes"/"no"


@dataclass
class OrderResult:
    """Result of order placement."""
    order_id: str
    status: OrderStatus
    filled_size: float = 0.0
    filled_price: Optional[float] = None
    message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class Position:
    """Open position on exchange."""
    token_id: str
    size: float
    avg_price: float
    side: str  # "UP"/"DOWN" or "yes"/"no"
    market_id: Optional[str] = None
    market_slug: Optional[str] = None
    unrealized_pnl: Optional[float] = None
    redeemable: bool = False
    end_date: Optional[datetime] = None
    current_value: float = 0.0  # Value if redeemed now (0 for losers)


@dataclass
class Trade:
    """Historical trade record."""
    trade_id: str
    token_id: str
    side: str  # "BUY" or "SELL"
    size: float
    price: float
    timestamp: Optional[datetime] = None
    market_id: Optional[str] = None
    outcome: Optional[str] = None  # "won", "lost", "pending"


@dataclass
class Market:
    """Market/contract info."""
    market_id: str
    slug: str
    question: str
    status: str  # "active", "resolved", etc.
    close_time: Optional[datetime] = None
    tokens: Dict[str, str] = field(default_factory=dict)  # {"UP": "token_id", "DOWN": "token_id"}
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Orderbook:
    """Orderbook snapshot."""
    token_id: str
    bids: List[tuple]  # [(price, size), ...]
    asks: List[tuple]  # [(price, size), ...]
    timestamp: Optional[datetime] = None

    @property
    def best_bid(self) -> Optional[float]:
        """Get best bid price."""
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        """Get best ask price."""
        return self.asks[0][0] if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        """Get mid price."""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> Optional[float]:
        """Get bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None


class BaseExchange(ABC):
    """
    Abstract base class for exchange implementations.

    Provides building blocks only - strategies compose these primitives.
    No strategy logic (no wait_for_fill, no retry logic, no timeouts).

    Subclasses must implement all abstract methods.
    """

    name: str  # "polymarket", "kalshi", etc.

    # === Connection ===

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection and authenticate."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close all connections gracefully."""
        pass

    # === Orders ===

    @abstractmethod
    async def place_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
    ) -> OrderResult:
        """
        Place a limit order.

        Args:
            token_id: Token/contract ID
            side: BUY or SELL
            price: Limit price (0.01-0.99 for PM, 1-99 cents for Kalshi)
            size: Size in USD or contracts

        Returns:
            OrderResult with order_id and status
        """
        pass

    @abstractmethod
    async def place_market_order(
        self,
        token_id: str,
        side: OrderSide,
        size: float,
    ) -> OrderResult:
        """
        Place a market order.

        Args:
            token_id: Token/contract ID
            side: BUY or SELL
            size: Size in USD or contracts

        Returns:
            OrderResult with order_id and status
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """
        Get current order status.

        Args:
            order_id: Order ID to check

        Returns:
            OrderResult with current status, or None if not found
        """
        pass

    @abstractmethod
    async def get_open_orders(self) -> List[OrderResult]:
        """Get all open orders."""
        pass

    # === Positions ===

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        pass

    @abstractmethod
    async def get_positions_by_market(self, market_id: str) -> List[Position]:
        """Get positions for a specific market."""
        pass

    @abstractmethod
    async def get_balance(self) -> Decimal:
        """Get available balance (USDC for PM, USD for Kalshi)."""
        pass

    # === Trade History ===

    @abstractmethod
    async def get_trade_history(
        self,
        limit: int = 100,
        market_id: Optional[str] = None,
    ) -> List[Trade]:
        """
        Get historical trades.

        Args:
            limit: Max number of trades to return
            market_id: Filter by market (optional)

        Returns:
            List of Trade objects with outcome info if available
        """
        pass

    # === Market Data ===

    @abstractmethod
    async def get_orderbook(self, token_id: str) -> Orderbook:
        """Get current orderbook for a token."""
        pass

    # === WebSocket Subscriptions (Optional) ===

    async def subscribe_orderbook(
        self,
        token_ids: List[str],
        callback: Callable[[str, Orderbook], None],
    ) -> None:
        """
        Subscribe to orderbook updates.

        Args:
            token_ids: Token IDs to subscribe to
            callback: Called with (token_id, orderbook) on each update
        """
        raise NotImplementedError(f"{self.name} doesn't support orderbook subscriptions")

    async def subscribe_fills(
        self,
        callback: Callable[[OrderResult], None],
    ) -> None:
        """
        Subscribe to fill notifications.

        Args:
            callback: Called with OrderResult when order fills
        """
        raise NotImplementedError(f"{self.name} doesn't support fill subscriptions")

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all WebSocket subscriptions."""
        pass
