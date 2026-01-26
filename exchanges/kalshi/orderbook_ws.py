"""Kalshi orderbook WebSocket.

Real-time orderbook updates via WebSocket subscription.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import websockets

from pmkit.exchanges.kalshi.auth import get_ws_auth_headers, load_private_key
from pmkit.exchanges.kalshi.types import WS_URL, OrderbookUpdate
from pmkit.exchanges.base import Orderbook

logger = logging.getLogger(__name__)


class OrderbookWebSocket:
    """
    Kalshi orderbook WebSocket.

    Subscribes to orderbook_delta channel and maintains current best bid/ask.

    Usage:
        ws = OrderbookWebSocket(api_key_id, private_key_path)
        await ws.connect(market_tickers=["KXBTC15M-..."])
        # Use ws.get_prices(ticker) to get current prices
        await ws.close()
    """

    def __init__(
        self,
        api_key_id: str,
        private_key_path: Union[str, Path],
        on_update: Optional[Callable[[OrderbookUpdate], Any]] = None,
        ticker_to_asset: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize orderbook WebSocket.

        Args:
            api_key_id: Kalshi API key ID
            private_key_path: Path to RSA private key PEM file
            on_update: Callback for orderbook updates
            ticker_to_asset: Mapping of ticker -> asset (e.g., "KXBTC15M-..." -> "BTC")
        """
        self.api_key_id = api_key_id
        self.private_key = load_private_key(private_key_path)
        self._on_update = on_update
        self.ticker_to_asset = ticker_to_asset or {}

        self._ws = None
        self._message_id = 1
        self._running = False
        self._task = None

        # Orderbook state: ticker -> {yes: {price: qty}, no: {price: qty}}
        self._orderbooks: Dict[str, dict] = {}

        # Best prices cache: ticker -> {yes_bid, yes_ask, no_bid, no_ask, ...}
        self._prices: Dict[str, dict] = {}

    async def connect(self, market_tickers: List[str]) -> None:
        """
        Connect to WebSocket and subscribe to orderbook updates.

        Args:
            market_tickers: List of market tickers to subscribe to
        """
        self._market_tickers = market_tickers
        auth_headers = get_ws_auth_headers(self.api_key_id, self.private_key)

        logger.info("Connecting to Kalshi WebSocket...")

        self._ws = await websockets.connect(WS_URL, extra_headers=auth_headers)
        self._running = True
        logger.info("Connected to Kalshi WebSocket")

        # Subscribe to orderbook_delta channel
        await self._subscribe(market_tickers)

        # Start message handler
        self._task = asyncio.create_task(self._handle_messages())

    async def _subscribe(self, market_tickers: List[str]) -> None:
        """Subscribe to orderbook_delta channel for given markets."""
        msg = {
            "id": self._message_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": market_tickers,
            },
        }
        self._message_id += 1

        await self._ws.send(json.dumps(msg))
        logger.info(f"Subscribed to orderbook_delta for {len(market_tickers)} markets")

    async def _handle_messages(self) -> None:
        """Handle incoming WebSocket messages."""
        try:
            async for message in self._ws:
                if not self._running:
                    break

                try:
                    data = json.loads(message)
                    await self._process_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except websockets.ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self._running = False

    async def _process_message(self, data: dict) -> None:
        """Process a single WebSocket message."""
        msg_type = data.get("type")

        if msg_type == "orderbook_snapshot":
            self._handle_snapshot(data)
        elif msg_type == "orderbook_delta":
            self._handle_delta(data)
        elif msg_type == "subscribed":
            logger.debug(f"Subscription confirmed: {data}")
        elif msg_type == "error":
            logger.error(f"WebSocket error: {data}")

    def _handle_snapshot(self, data: dict) -> None:
        """Handle orderbook_snapshot message - full orderbook state."""
        msg = data.get("msg", {})
        ticker = msg.get("market_ticker")
        if not ticker:
            return

        yes_levels = msg.get("yes", [])
        no_levels = msg.get("no", [])

        self._orderbooks[ticker] = {
            "yes": {level[0]: level[1] for level in yes_levels},
            "no": {level[0]: level[1] for level in no_levels},
        }

        self._update_best_prices(ticker)

    def _handle_delta(self, data: dict) -> None:
        """Handle orderbook_delta message - incremental update."""
        msg = data.get("msg", {})
        ticker = msg.get("market_ticker")
        if not ticker:
            return

        side = msg.get("side")
        price = msg.get("price")
        delta = msg.get("delta")

        if side is None or price is None or delta is None:
            return

        if ticker not in self._orderbooks:
            self._orderbooks[ticker] = {"yes": {}, "no": {}}

        book = self._orderbooks[ticker][side]
        current_qty = book.get(price, 0)
        new_qty = current_qty + delta

        if new_qty <= 0:
            book.pop(price, None)
        else:
            book[price] = new_qty

        self._update_best_prices(ticker)

    def _update_best_prices(self, ticker: str) -> None:
        """Update best bid/ask prices for a ticker and emit update."""
        book = self._orderbooks.get(ticker, {})
        yes_book = book.get("yes", {})
        no_book = book.get("no", {})

        yes_bids = [p for p, q in yes_book.items() if q > 0]
        no_bids = [p for p, q in no_book.items() if q > 0]

        # YES best bid (highest)
        yes_bid = max(yes_bids) if yes_bids else None
        yes_bid_size = yes_book.get(yes_bid, 0) if yes_bid else None

        # NO best bid (highest)
        no_bid = max(no_bids) if no_bids else None
        no_bid_size = no_book.get(no_bid, 0) if no_bid else None

        # Calculate asks from complementary side
        yes_ask = (100 - no_bid) if no_bid else None
        yes_ask_size = no_bid_size
        no_ask = (100 - yes_bid) if yes_bid else None
        no_ask_size = yes_bid_size

        # Store prices (convert cents to decimal)
        self._prices[ticker] = {
            "yes_bid": yes_bid / 100 if yes_bid else None,
            "yes_bid_size": yes_bid_size,
            "yes_ask": yes_ask / 100 if yes_ask else None,
            "yes_ask_size": yes_ask_size,
            "no_bid": no_bid / 100 if no_bid else None,
            "no_bid_size": no_bid_size,
            "no_ask": no_ask / 100 if no_ask else None,
            "no_ask_size": no_ask_size,
        }

        # Emit update callback
        if self._on_update:
            now = datetime.now(timezone.utc)
            asset = self.ticker_to_asset.get(ticker, "UNKNOWN")

            update = OrderbookUpdate(
                timestamp_ms=int(now.timestamp() * 1000),
                market_ticker=ticker,
                asset=asset,
                yes_bid=self._prices[ticker]["yes_bid"],
                yes_bid_size=self._prices[ticker]["yes_bid_size"],
                yes_ask=self._prices[ticker]["yes_ask"],
                yes_ask_size=self._prices[ticker]["yes_ask_size"],
                no_bid=self._prices[ticker]["no_bid"],
                no_bid_size=self._prices[ticker]["no_bid_size"],
                no_ask=self._prices[ticker]["no_ask"],
                no_ask_size=self._prices[ticker]["no_ask_size"],
            )

            result = self._on_update(update)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

    # Public getters

    def get_yes_bid(self, ticker: str) -> Optional[float]:
        """Get best YES bid price (decimal)."""
        return self._prices.get(ticker, {}).get("yes_bid")

    def get_yes_ask(self, ticker: str) -> Optional[float]:
        """Get best YES ask price (decimal)."""
        return self._prices.get(ticker, {}).get("yes_ask")

    def get_no_bid(self, ticker: str) -> Optional[float]:
        """Get best NO bid price (decimal)."""
        return self._prices.get(ticker, {}).get("no_bid")

    def get_no_ask(self, ticker: str) -> Optional[float]:
        """Get best NO ask price (decimal)."""
        return self._prices.get(ticker, {}).get("no_ask")

    def get_prices(self, ticker: str) -> Optional[dict]:
        """Get all prices for a ticker."""
        return self._prices.get(ticker)

    def get_orderbook(self, ticker: str) -> Orderbook:
        """
        Get orderbook for a ticker.

        Returns:
            Orderbook with best bid/ask as single-level book
        """
        prices = self._prices.get(ticker, {})
        bids = []
        asks = []

        yes_bid = prices.get("yes_bid")
        yes_bid_size = prices.get("yes_bid_size")
        if yes_bid is not None:
            bids = [(yes_bid, yes_bid_size or 0)]

        yes_ask = prices.get("yes_ask")
        yes_ask_size = prices.get("yes_ask_size")
        if yes_ask is not None:
            asks = [(yes_ask, yes_ask_size or 0)]

        return Orderbook(token_id=ticker, bids=bids, asks=asks)

    async def close(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            logger.info("Kalshi WebSocket closed")
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
