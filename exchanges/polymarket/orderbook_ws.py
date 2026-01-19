"""Polymarket orderbook WebSocket.

Real-time bid/ask prices via WebSocket subscription.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from pmkit.websocket.base import BaseWebSocket
from pmkit.exchanges.base import Orderbook

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class OrderbookWebSocket(BaseWebSocket):
    """
    Polymarket orderbook WebSocket.

    Subscribes to real-time bid/ask updates for multiple tokens.

    Usage:
        ws = OrderbookWebSocket()
        await ws.connect(token_ids=["token1", "token2"])
        await ws.run()  # Blocks until stopped
    """

    def __init__(self):
        """Initialize orderbook WebSocket."""
        super().__init__(url=WS_URL)
        self.bids: Dict[str, float] = {}  # token_id -> best_bid
        self.asks: Dict[str, float] = {}  # token_id -> best_ask
        self.bid_sizes: Dict[str, float] = {}  # token_id -> best_bid_size
        self.ask_sizes: Dict[str, float] = {}  # token_id -> best_ask_size
        self._token_ids: List[str] = []
        self._on_update: Optional[Callable[[str, Orderbook], Any]] = None

    async def connect(
        self,
        token_ids: List[str],
        on_update: Optional[Callable[[str, Orderbook], Any]] = None,
    ) -> None:
        """
        Connect and subscribe to tokens.

        Args:
            token_ids: Token IDs to subscribe to
            on_update: Optional callback(token_id, Orderbook) on each update
        """
        self._token_ids = token_ids
        self._on_update = on_update
        await super().connect()

    async def _on_connect(self, ws) -> None:
        """Send subscription message on connect."""
        subscribe_msg = {"assets_ids": self._token_ids, "type": "market"}
        await ws.send(json.dumps(subscribe_msg))
        logger.info(f"[OrderbookWS] Subscribed to {len(self._token_ids)} tokens")

    async def _handle_message(self, data: Any) -> None:
        """Handle incoming WebSocket message."""
        if not isinstance(data, dict):
            if isinstance(data, list):
                for item in data:
                    await self._process_update(item)
            return

        event_type = data.get("event_type")

        if event_type == "book":
            await self._process_book(data)
        elif "price_changes" in data:
            for item in data["price_changes"]:
                await self._process_update(item)
        else:
            await self._process_update(data)

    async def _process_update(self, item: dict) -> None:
        """Process a price update."""
        if not isinstance(item, dict):
            return

        asset_id = item.get("asset_id")
        if not asset_id:
            return

        best_bid = item.get("best_bid")
        best_ask = item.get("best_ask")

        if best_bid:
            self.bids[asset_id] = float(best_bid)
        if best_ask:
            self.asks[asset_id] = float(best_ask)

        if self._on_update and (best_bid or best_ask):
            orderbook = self.get_orderbook(asset_id)
            result = self._on_update(asset_id, orderbook)
            if asyncio.iscoroutine(result):
                await result

    async def _process_book(self, data: dict) -> None:
        """Process a full book update."""
        asset_id = data.get("asset_id")
        if not asset_id:
            return

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        if bids:
            best_bid_item = max(bids, key=lambda x: float(x["price"]))
            self.bids[asset_id] = float(best_bid_item["price"])
            self.bid_sizes[asset_id] = float(best_bid_item["size"])

        if asks:
            best_ask_item = min(asks, key=lambda x: float(x["price"]))
            self.asks[asset_id] = float(best_ask_item["price"])
            self.ask_sizes[asset_id] = float(best_ask_item["size"])

        if self._on_update:
            orderbook = self.get_orderbook(asset_id)
            result = self._on_update(asset_id, orderbook)
            if asyncio.iscoroutine(result):
                await result

    def get_bid(self, token_id: str) -> Optional[float]:
        """Get best bid for a token."""
        return self.bids.get(token_id)

    def get_ask(self, token_id: str) -> Optional[float]:
        """Get best ask for a token."""
        return self.asks.get(token_id)

    def get_bid_ask(self, token_id: str) -> tuple:
        """Get (bid, ask) for a token."""
        return self.bids.get(token_id), self.asks.get(token_id)

    def get_spread(self, token_id: str) -> Optional[float]:
        """Get bid-ask spread for a token."""
        bid = self.bids.get(token_id)
        ask = self.asks.get(token_id)
        if bid is not None and ask is not None:
            return ask - bid
        return None

    def get_orderbook(self, token_id: str) -> Orderbook:
        """
        Get orderbook for a token.

        Returns:
            Orderbook with best bid/ask as single-level book
        """
        bids = []
        asks = []

        bid = self.bids.get(token_id)
        bid_size = self.bid_sizes.get(token_id)
        if bid is not None:
            bids = [(bid, bid_size or 0.0)]

        ask = self.asks.get(token_id)
        ask_size = self.ask_sizes.get(token_id)
        if ask is not None:
            asks = [(ask, ask_size or 0.0)]

        return Orderbook(token_id=token_id, bids=bids, asks=asks)

    def clear(self) -> None:
        """Clear all stored orderbook data."""
        self.bids.clear()
        self.asks.clear()
        self.bid_sizes.clear()
        self.ask_sizes.clear()
