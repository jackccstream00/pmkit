"""Binance WebSocket real-time data feed.

Features:
- Real-time 1s candle streaming
- Rolling buffer for recent data
- Warmup initialization from REST API
- Only emits closed candles

Usage:
    feed = BinanceFeed(symbol="BTCUSDT")
    await feed.initialize(warmup_count=1000)
    await feed.start(on_candle=my_callback)
"""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import websockets
from websockets.client import WebSocketClientProtocol

from pmkit.data.binance.types import Candle, Interval, get_symbol
from pmkit.data.binance.fetcher import BinanceFetcher

logger = logging.getLogger(__name__)


class BinanceFeed:
    """
    Real-time Binance candle feed via WebSocket.

    Features:
    - Warmup: Preload historical candles at startup
    - Streaming: Real-time candles via WebSocket
    - Buffer: Rolling buffer for recent data access
    - Only closed candles: Wait for candle to close before emitting
    """

    WS_URL = "wss://stream.binance.com:9443/ws"

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: Interval = Interval.SECOND_1,
        buffer_size: int = 1500,
    ):
        """
        Initialize Binance feed.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT") or asset (e.g., "BTC")
            interval: Candle interval
            buffer_size: Max candles to keep in buffer
        """
        self.symbol = get_symbol(symbol)
        self.interval = interval
        self.buffer_size = buffer_size

        self._buffer: deque[Candle] = deque(maxlen=buffer_size)
        self._running = False
        self._initialized = False
        self._task: Optional[asyncio.Task] = None
        self._on_candle: Optional[Callable[[Candle], Any]] = None

        # Reconnection settings
        self._retry_delay = 1.0
        self._max_retry_delay = 30.0

    async def initialize(self, warmup_count: int = 1000) -> None:
        """
        Initialize with historical data for immediate use.

        Args:
            warmup_count: Number of historical candles to fetch
        """
        logger.info(f"Initializing {self.symbol} feed with {warmup_count} warmup candles...")

        fetcher = BinanceFetcher()
        candles = await fetcher.fetch_warmup(
            symbol=self.symbol,
            interval=self.interval,
            count=warmup_count,
        )

        for candle in candles:
            self._buffer.append(candle)

        self._initialized = True
        logger.info(f"Initialized with {len(self._buffer)} candles")

    async def start(self, on_candle: Optional[Callable[[Candle], Any]] = None) -> None:
        """
        Start the WebSocket stream.

        Args:
            on_candle: Callback for each closed candle
        """
        if self._running:
            logger.warning(f"[{self.symbol}] Already running")
            return

        self._on_candle = on_candle
        self._running = True
        self._retry_delay = 1.0

        self._task = asyncio.create_task(self._run())
        logger.info(f"[{self.symbol}] WebSocket stream started")

    async def stop(self) -> None:
        """Stop the WebSocket stream."""
        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

        logger.info(f"[{self.symbol}] WebSocket stream stopped")

    async def _run(self) -> None:
        """Main WebSocket connection loop."""
        stream_name = f"{self.symbol.lower()}@kline_{self.interval.value}"
        ws_url = f"{self.WS_URL}/{stream_name}"

        while self._running:
            try:
                logger.info(f"[{self.symbol}] Connecting to {ws_url}...")

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    logger.info(f"[{self.symbol}] Connected")
                    self._retry_delay = 1.0  # Reset on success

                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)

            except websockets.ConnectionClosed as e:
                if self._running:
                    logger.warning(
                        f"[{self.symbol}] Connection closed: {e.code}. "
                        f"Reconnecting in {self._retry_delay:.1f}s..."
                    )
                    await self._wait_and_backoff()

            except Exception as e:
                if self._running:
                    logger.error(
                        f"[{self.symbol}] Error: {e}. "
                        f"Reconnecting in {self._retry_delay:.1f}s..."
                    )
                    await self._wait_and_backoff()

    async def _wait_and_backoff(self) -> None:
        """Wait with exponential backoff."""
        await asyncio.sleep(self._retry_delay)
        self._retry_delay = min(self._retry_delay * 2, self._max_retry_delay)

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)

            if "k" not in data:
                return

            kline = data["k"]

            # Only process closed candles
            if not kline.get("x", False):
                return

            # Parse candle
            candle = Candle(
                timestamp=datetime.fromtimestamp(kline["t"] / 1000, tz=timezone.utc),
                open=float(kline["o"]),
                high=float(kline["h"]),
                low=float(kline["l"]),
                close=float(kline["c"]),
                volume=float(kline["v"]),
                symbol=self.symbol,
                interval=self.interval.value,
            )

            # Add to buffer
            self._buffer.append(candle)

            # Call callback
            if self._on_candle:
                result = self._on_candle(candle)
                if asyncio.iscoroutine(result):
                    await result

        except Exception as e:
            logger.error(f"[{self.symbol}] Error handling message: {e}")

    # === Data Access ===

    @property
    def is_initialized(self) -> bool:
        """Check if warmup data has been loaded."""
        return self._initialized

    @property
    def is_running(self) -> bool:
        """Check if WebSocket is running."""
        return self._running

    @property
    def candle_count(self) -> int:
        """Get number of candles in buffer."""
        return len(self._buffer)

    def get_latest(self) -> Optional[Candle]:
        """Get the most recent candle."""
        if not self._buffer:
            return None
        return self._buffer[-1]

    def get_latest_price(self) -> Optional[float]:
        """Get the most recent close price."""
        candle = self.get_latest()
        return candle.close if candle else None

    def get_buffer(self, n: Optional[int] = None) -> List[Candle]:
        """
        Get candles from buffer.

        Args:
            n: Number of recent candles. None for all.

        Returns:
            List of candles (oldest first)
        """
        if not self._buffer:
            return []

        candles = list(self._buffer)
        if n is not None:
            candles = candles[-n:]

        return candles

    def get_buffer_df(self, n: Optional[int] = None):
        """
        Get buffer as DataFrame.

        Args:
            n: Number of recent candles. None for all.

        Returns:
            DataFrame with OHLCV columns
        """
        import pandas as pd

        candles = self.get_buffer(n)

        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        data = [c.to_ohlcv_dict() for c in candles]
        df = pd.DataFrame(data)
        df = df.sort_values("timestamp").reset_index(drop=True)

        return df

    def get_prices(self, n: int = 900) -> List[float]:
        """
        Get recent close prices.

        Args:
            n: Number of prices

        Returns:
            List of close prices (oldest first)
        """
        candles = self.get_buffer(n)
        return [c.close for c in candles]
