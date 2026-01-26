"""Predict.fun orderbook WebSocket.

Real-time bid/ask prices via WebSocket subscription.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from pmkit.websocket.base import BaseWebSocket
from pmkit.exchanges.base import Orderbook
from pmkit.exchanges.predictfun.types import WS_URL, WS_URL_TESTNET

logger = logging.getLogger(__name__)


class OrderbookWebSocket(BaseWebSocket):
    """
    Predict.fun orderbook WebSocket.

    Subscribes to real-time orderbook updates for markets.

    Usage:
        ws = OrderbookWebSocket()
        await ws.connect()
        await ws.subscribe(market_id=123, callback=lambda mid, ob: print(ob))
        # ... later
        await ws.disconnect()
    """

    # Heartbeat interval in seconds
    HEARTBEAT_INTERVAL = 15.0

    def __init__(self, testnet: bool = False):
        """
        Initialize orderbook WebSocket.

        Args:
            testnet: If True, use testnet WebSocket URL
        """
        url = WS_URL_TESTNET if testnet else WS_URL
        super().__init__(url=url)

        # market_id -> latest orderbook
        self._orderbooks: Dict[int, Orderbook] = {}

        # market_id -> token_id -> Orderbook
        self._token_orderbooks: Dict[int, Dict[str, Orderbook]] = {}

        # Subscribed market IDs
        self._subscribed: List[int] = []

        # Callbacks: market_id -> callback
        self._callbacks: Dict[int, Callable[[int, Orderbook], Any]] = {}

        # Heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Message ID counter
        self._msg_id = 0

    async def _on_connect(self, ws) -> None:
        """Handle connection setup."""
        logger.info("[PredictfunOrderbookWS] Connected")

        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Resubscribe to any previously subscribed markets
        for market_id in self._subscribed:
            await self._send_subscribe(market_id)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self.running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                if self._ws and self._ws.open:
                    self._msg_id += 1
                    await self._ws.send(json.dumps({
                        "id": self._msg_id,
                        "type": "ping",
                    }))
            except Exception as e:
                if self.running:
                    logger.warning(f"[PredictfunOrderbookWS] Heartbeat error: {e}")

    async def _send_subscribe(self, market_id: int) -> None:
        """Send subscription message for a market."""
        if self._ws and self._ws.open:
            self._msg_id += 1
            msg = {
                "id": self._msg_id,
                "type": "subscribe",
                "topic": f"predictOrderbook/{market_id}",
            }
            await self._ws.send(json.dumps(msg))
            logger.info(f"[PredictfunOrderbookWS] Subscribed to market {market_id}")

    async def subscribe(
        self,
        market_id: int,
        callback: Optional[Callable[[int, Orderbook], Any]] = None,
    ) -> None:
        """
        Subscribe to orderbook updates for a market.

        Args:
            market_id: Market ID to subscribe to
            callback: Optional callback(market_id, Orderbook) on each update
        """
        if market_id not in self._subscribed:
            self._subscribed.append(market_id)

        if callback:
            self._callbacks[market_id] = callback

        if self.is_connected:
            await self._send_subscribe(market_id)

    async def unsubscribe(self, market_id: int) -> None:
        """
        Unsubscribe from orderbook updates for a market.

        Args:
            market_id: Market ID to unsubscribe from
        """
        if market_id in self._subscribed:
            self._subscribed.remove(market_id)

        if market_id in self._callbacks:
            del self._callbacks[market_id]

        if self._ws and self._ws.open:
            self._msg_id += 1
            msg = {
                "id": self._msg_id,
                "type": "unsubscribe",
                "topic": f"predictOrderbook/{market_id}",
            }
            await self._ws.send(json.dumps(msg))
            logger.info(f"[PredictfunOrderbookWS] Unsubscribed from market {market_id}")

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        msg_type = data.get("type")

        if msg_type == "pong":
            return

        if msg_type == "subscribed":
            topic = data.get("topic", "")
            logger.debug(f"[PredictfunOrderbookWS] Subscription confirmed: {topic}")
            return

        if msg_type == "error":
            logger.error(f"[PredictfunOrderbookWS] Error: {data.get('message')}")
            return

        # Handle orderbook update
        if "topic" in data and "predictOrderbook" in data.get("topic", ""):
            await self._process_orderbook_update(data)

    async def _process_orderbook_update(self, data: Dict[str, Any]) -> None:
        """Process an orderbook update message."""
        topic = data.get("topic", "")
        try:
            # Extract market_id from topic (e.g., "predictOrderbook/123")
            market_id = int(topic.split("/")[-1])
        except (ValueError, IndexError):
            logger.warning(f"[PredictfunOrderbookWS] Invalid topic: {topic}")
            return

        payload = data.get("data", data)

        # Initialize storage for this market
        if market_id not in self._token_orderbooks:
            self._token_orderbooks[market_id] = {}

        # Process each outcome in the orderbook
        for outcome in payload.get("outcomes", []):
            token_id = outcome.get("onChainId")
            if not token_id:
                continue

            bids = []
            asks = []

            for b in outcome.get("bids", []):
                bids.append((float(b.get("price", 0)), float(b.get("quantity", 0))))
            for a in outcome.get("asks", []):
                asks.append((float(a.get("price", 0)), float(a.get("quantity", 0))))

            # Sort: bids descending, asks ascending
            bids.sort(key=lambda x: x[0], reverse=True)
            asks.sort(key=lambda x: x[0])

            orderbook = Orderbook(token_id=token_id, bids=bids, asks=asks)
            self._token_orderbooks[market_id][token_id] = orderbook

        # Call callback if registered
        callback = self._callbacks.get(market_id)
        if callback:
            # Use first token's orderbook for the callback
            for token_id, ob in self._token_orderbooks.get(market_id, {}).items():
                result = callback(market_id, ob)
                if asyncio.iscoroutine(result):
                    await result
                break

    def get_orderbook(self, market_id: int, token_id: str) -> Optional[Orderbook]:
        """
        Get cached orderbook for a token.

        Args:
            market_id: Market ID
            token_id: Token ID

        Returns:
            Orderbook or None if not available
        """
        return self._token_orderbooks.get(market_id, {}).get(token_id)

    def get_mid_price(self, market_id: int, token_id: str) -> Optional[float]:
        """
        Get mid price for a token.

        Args:
            market_id: Market ID
            token_id: Token ID

        Returns:
            Mid price or None if not available
        """
        ob = self.get_orderbook(market_id, token_id)
        return ob.mid_price if ob else None

    def get_spread(self, market_id: int, token_id: str) -> Optional[float]:
        """
        Get bid-ask spread for a token.

        Args:
            market_id: Market ID
            token_id: Token ID

        Returns:
            Spread or None if not available
        """
        ob = self.get_orderbook(market_id, token_id)
        return ob.spread if ob else None

    async def disconnect(self) -> None:
        """Stop the WebSocket connection gracefully."""
        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        await super().disconnect()

    def clear(self) -> None:
        """Clear all cached orderbook data."""
        self._orderbooks.clear()
        self._token_orderbooks.clear()
