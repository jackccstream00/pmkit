"""Kalshi exchange client.

Building blocks for trading on Kalshi prediction markets.
"""

import logging
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

import httpx

from pmkit.exchanges.base import (
    BaseExchange,
    Orderbook,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Trade,
)
from pmkit.exchanges.kalshi.auth import get_auth_headers, load_private_key
from pmkit.exchanges.kalshi.types import API_BASE

logger = logging.getLogger(__name__)


class KalshiExchange(BaseExchange):
    """
    Kalshi exchange client.

    Building blocks only - no strategy logic.

    Usage:
        exchange = KalshiExchange(api_key_id, private_key_path)
        await exchange.connect()

        # Place orders
        result = await exchange.place_limit_order(ticker, OrderSide.BUY, 0.50, 10)

        # Get positions
        positions = await exchange.get_positions()

        # Cleanup
        await exchange.disconnect()
    """

    name = "kalshi"

    def __init__(
        self,
        api_key_id: str,
        private_key_path: Union[str, Path],
    ):
        """
        Initialize Kalshi client.

        Args:
            api_key_id: Kalshi API key ID
            private_key_path: Path to RSA private key PEM file
        """
        self.api_key_id = api_key_id
        self.private_key_path = Path(private_key_path)
        self._private_key = None
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

        logger.info("Kalshi client initializing...")
        logger.info(f"  API Key: {api_key_id[:8]}...")

    # === Connection ===

    async def connect(self) -> None:
        """Initialize and authenticate with Kalshi."""
        if self._initialized:
            return

        try:
            self._private_key = load_private_key(self.private_key_path)
            self._client = httpx.AsyncClient(timeout=30.0)
            self._initialized = True
            logger.info("Kalshi client connected")

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connections."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._private_key = None
        self._initialized = False
        logger.info("Kalshi client disconnected")

    def _ensure_connected(self) -> None:
        """Ensure client is connected."""
        if not self._initialized:
            raise RuntimeError("Not connected. Call connect() first.")

    def _get_headers(self, method: str, path: str) -> Dict[str, str]:
        """Get authentication headers for a request."""
        return get_auth_headers(self.api_key_id, self._private_key, method, path)

    # === Orders ===

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
            token_id: Market ticker (e.g., "KXBTC15M-26JAN061745-45")
            side: BUY or SELL (BUY = yes, SELL = no in Kalshi terms)
            price: Limit price (0.01-0.99 decimal)
            size: Number of contracts

        Returns:
            OrderResult with order_id and status
        """
        self._ensure_connected()

        path = "/portfolio/orders"
        url = f"{API_BASE}{path}"

        # Convert price to cents
        price_cents = int(price * 100)

        # Map side to Kalshi terminology
        kalshi_side = "yes" if side == OrderSide.BUY else "no"

        body = {
            "ticker": token_id,
            "side": kalshi_side,
            "action": "buy",
            "type": "limit",
            "count": int(size),
        }

        # Set price based on side
        if kalshi_side == "yes":
            body["yes_price"] = price_cents
        else:
            body["no_price"] = price_cents

        headers = self._get_headers("POST", path)

        logger.info(f"Placing Kalshi order: {token_id} {kalshi_side} @ {price_cents}c x{int(size)}")

        try:
            resp = await self._client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

            order = data.get("order", {})
            order_id = order.get("order_id", "")
            status = self._parse_order_status(order.get("status", ""))

            logger.info(f"Kalshi order placed: {order_id}")

            return OrderResult(
                order_id=order_id,
                status=status,
                raw_response=order,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Order failed: {e.response.status_code} - {e.response.text}")
            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                message=e.response.text,
            )
        except Exception as e:
            logger.error(f"Order error: {e}")
            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                message=str(e),
            )

    async def place_market_order(
        self,
        token_id: str,
        side: OrderSide,
        size: float,
    ) -> OrderResult:
        """
        Place a market order.

        Note: Kalshi doesn't have true market orders. This places a limit order
        at an aggressive price that should fill immediately.

        Args:
            token_id: Market ticker
            side: BUY or SELL
            size: Number of contracts

        Returns:
            OrderResult with order_id and status
        """
        # Use aggressive price for "market" order
        price = 0.99 if side == OrderSide.BUY else 0.01
        return await self.place_limit_order(token_id, side, price, size)

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        self._ensure_connected()

        path = f"/portfolio/orders/{order_id}"
        url = f"{API_BASE}{path}"
        headers = self._get_headers("DELETE", path)

        logger.info(f"Cancelling Kalshi order: {order_id}")

        try:
            resp = await self._client.delete(url, headers=headers)
            resp.raise_for_status()
            logger.info(f"Order cancelled: {order_id}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Cancel failed: {e.response.status_code}")
            return False
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """
        Get order status.

        Args:
            order_id: Order ID to check

        Returns:
            OrderResult with current status, or None if not found
        """
        self._ensure_connected()

        path = f"/portfolio/orders/{order_id}"
        url = f"{API_BASE}{path}"
        headers = self._get_headers("GET", path)

        try:
            resp = await self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            order = data.get("order", {})

            return OrderResult(
                order_id=order_id,
                status=self._parse_order_status(order.get("status", "")),
                filled_size=float(order.get("fill_count", 0)),
                raw_response=order,
            )

        except httpx.HTTPStatusError:
            return None
        except Exception as e:
            logger.error(f"Get order error: {e}")
            return None

    async def get_open_orders(self) -> List[OrderResult]:
        """Get all open orders."""
        self._ensure_connected()

        path = "/portfolio/orders"
        url = f"{API_BASE}{path}"
        headers = self._get_headers("GET", path)

        try:
            resp = await self._client.get(url, headers=headers, params={"status": "resting"})
            resp.raise_for_status()
            data = resp.json()
            orders = data.get("orders", [])

            results = []
            for order in orders:
                results.append(
                    OrderResult(
                        order_id=order.get("order_id", ""),
                        status=self._parse_order_status(order.get("status", "")),
                        filled_size=float(order.get("fill_count", 0)),
                        raw_response=order,
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Get open orders error: {e}")
            return []

    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse API order status to OrderStatus enum."""
        status_map = {
            "resting": OrderStatus.OPEN,
            "executed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "pending": OrderStatus.PENDING,
        }
        return status_map.get(status.lower(), OrderStatus.PENDING)

    # === Positions ===

    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        self._ensure_connected()

        path = "/portfolio/positions"
        url = f"{API_BASE}{path}"
        headers = self._get_headers("GET", path)

        try:
            resp = await self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            positions_data = data.get("market_positions", [])

            positions = []
            for pos in positions_data:
                # Kalshi positions have yes and no counts
                yes_count = pos.get("position", 0)
                if yes_count > 0:
                    positions.append(
                        Position(
                            token_id=pos.get("ticker", ""),
                            size=float(yes_count),
                            avg_price=0.0,  # Kalshi doesn't provide avg price
                            side="yes",
                            market_id=pos.get("ticker"),
                        )
                    )

            return positions

        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []

    async def get_positions_by_market(self, market_id: str) -> List[Position]:
        """Get positions for a specific market."""
        positions = await self.get_positions()
        return [p for p in positions if p.market_id == market_id]

    async def get_balance(self) -> Decimal:
        """Get available USD balance."""
        self._ensure_connected()

        path = "/portfolio/balance"
        url = f"{API_BASE}{path}"
        headers = self._get_headers("GET", path)

        try:
            resp = await self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # Balance in cents, convert to dollars
            balance_cents = data.get("balance", 0)
            return Decimal(str(balance_cents)) / 100

        except Exception as e:
            logger.error(f"Get balance error: {e}")
            return Decimal("0")

    # === Trade History ===

    async def get_trade_history(
        self,
        limit: int = 100,
        market_id: Optional[str] = None,
    ) -> List[Trade]:
        """Get historical trades."""
        self._ensure_connected()

        path = "/portfolio/fills"
        url = f"{API_BASE}{path}"
        headers = self._get_headers("GET", path)

        params = {"limit": limit}
        if market_id:
            params["ticker"] = market_id

        try:
            resp = await self._client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            fills = data.get("fills", [])

            trades = []
            for fill in fills:
                from datetime import datetime

                created_at = fill.get("created_time", "")
                try:
                    timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except ValueError:
                    timestamp = datetime.now()

                trades.append(
                    Trade(
                        trade_id=fill.get("trade_id", ""),
                        timestamp=timestamp,
                        token_id=fill.get("ticker", ""),
                        side=OrderSide.BUY if fill.get("side") == "yes" else OrderSide.SELL,
                        size=float(fill.get("count", 0)),
                        price=float(fill.get("price", 0)) / 100,
                        market_id=fill.get("ticker"),
                    )
                )

            return trades

        except Exception as e:
            logger.error(f"Get trade history error: {e}")
            return []

    # === Market Data ===

    async def get_orderbook(self, token_id: str) -> Orderbook:
        """Get current orderbook for a market."""
        self._ensure_connected()

        path = f"/markets/{token_id}/orderbook"
        url = f"{API_BASE}{path}"
        headers = self._get_headers("GET", path)

        try:
            resp = await self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            orderbook = data.get("orderbook", {})

            bids = []
            asks = []

            # Kalshi orderbook has yes/no levels
            # Convert to bids/asks format
            yes_levels = orderbook.get("yes", [])
            no_levels = orderbook.get("no", [])

            # YES bids (highest YES prices)
            for level in yes_levels:
                price_cents = level[0]
                qty = level[1]
                bids.append((price_cents / 100, qty))

            # YES asks derived from NO bids
            for level in no_levels:
                price_cents = level[0]
                qty = level[1]
                asks.append(((100 - price_cents) / 100, qty))

            return Orderbook(token_id=token_id, bids=bids, asks=asks)

        except Exception as e:
            logger.error(f"Get orderbook error: {e}")
            return Orderbook(token_id=token_id, bids=[], asks=[])

    # === WebSocket Subscriptions ===

    async def subscribe_orderbook(
        self,
        token_ids: List[str],
        callback: Callable[[str, Orderbook], None],
    ) -> None:
        """
        Subscribe to orderbook updates.

        Note: Use OrderbookWebSocket directly for more control.
        """
        from pmkit.exchanges.kalshi.orderbook_ws import OrderbookWebSocket

        def wrap_callback(update):
            orderbook = Orderbook(
                token_id=update.market_ticker,
                bids=[(update.yes_bid, update.yes_bid_size)] if update.yes_bid else [],
                asks=[(update.yes_ask, update.yes_ask_size)] if update.yes_ask else [],
            )
            callback(update.market_ticker, orderbook)

        self._orderbook_ws = OrderbookWebSocket(
            api_key_id=self.api_key_id,
            private_key_path=self.private_key_path,
            on_update=wrap_callback,
        )
        await self._orderbook_ws.connect(token_ids)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all WebSocket subscriptions."""
        if hasattr(self, "_orderbook_ws") and self._orderbook_ws:
            await self._orderbook_ws.close()
            self._orderbook_ws = None
