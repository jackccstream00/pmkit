"""Base WebSocket class with automatic reconnection.

Features:
- Exponential backoff reconnection (1s -> 2s -> 4s -> max 30s)
- Graceful shutdown
- Abstract methods for connection and message handling
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

import websockets
from websockets.client import WebSocketClientProtocol


logger = logging.getLogger(__name__)


class BaseWebSocket(ABC):
    """
    Abstract base class for WebSocket connections with auto-reconnection.

    Subclasses must implement:
    - _on_connect(ws): Handle connection, send subscriptions
    - _handle_message(data): Process incoming messages

    Example:
        class OrderbookWebSocket(BaseWebSocket):
            def __init__(self, on_update: Callable):
                super().__init__(url="wss://ws-subscriptions-clob.polymarket.com/ws/market")
                self.on_update = on_update

            async def _on_connect(self, ws):
                await ws.send(json.dumps({"type": "subscribe", "markets": [...]}))

            async def _handle_message(self, data: dict):
                self.on_update(data)
    """

    # Reconnection settings
    INITIAL_RETRY_DELAY = 1.0  # seconds
    MAX_RETRY_DELAY = 30.0  # seconds
    BACKOFF_MULTIPLIER = 2.0

    def __init__(self, url: str, name: Optional[str] = None):
        """
        Initialize WebSocket.

        Args:
            url: WebSocket URL to connect to.
            name: Optional name for logging. Defaults to class name.
        """
        self.url = url
        self.name = name or self.__class__.__name__

        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._ws: Optional[WebSocketClientProtocol] = None
        self._retry_delay = self.INITIAL_RETRY_DELAY

    async def connect(self) -> None:
        """Start the WebSocket connection."""
        if self.running:
            logger.warning(f"[{self.name}] Already connected")
            return

        self.running = True
        self._retry_delay = self.INITIAL_RETRY_DELAY
        self._task = asyncio.create_task(self._run())
        logger.info(f"[{self.name}] Connection started")

    async def disconnect(self) -> None:
        """Stop the WebSocket connection gracefully."""
        self.running = False

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

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

        logger.info(f"[{self.name}] Disconnected")

    async def _run(self) -> None:
        """Main connection loop with reconnection logic."""
        while self.running:
            try:
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    self._retry_delay = self.INITIAL_RETRY_DELAY  # Reset on success

                    logger.info(f"[{self.name}] Connected to {self.url}")

                    # Let subclass handle connection setup
                    await self._on_connect(ws)

                    # Message loop
                    async for message in ws:
                        if not self.running:
                            break
                        await self._process_message(message)

            except websockets.ConnectionClosed as e:
                if self.running:
                    logger.warning(
                        f"[{self.name}] Connection closed: {e.code} {e.reason}. "
                        f"Reconnecting in {self._retry_delay:.1f}s..."
                    )
                    await self._wait_and_backoff()

            except Exception as e:
                if self.running:
                    logger.error(
                        f"[{self.name}] Error: {e}. "
                        f"Reconnecting in {self._retry_delay:.1f}s..."
                    )
                    await self._wait_and_backoff()

        self._ws = None

    async def _wait_and_backoff(self) -> None:
        """Wait before reconnecting with exponential backoff."""
        await asyncio.sleep(self._retry_delay)

        # Increase delay for next time (exponential backoff)
        self._retry_delay = min(
            self._retry_delay * self.BACKOFF_MULTIPLIER,
            self.MAX_RETRY_DELAY,
        )

    async def _process_message(self, message: str) -> None:
        """Parse and handle incoming message."""
        try:
            data = json.loads(message)
            await self._handle_message(data)
        except json.JSONDecodeError:
            logger.warning(f"[{self.name}] Invalid JSON: {message[:100]}")
        except Exception as e:
            logger.error(f"[{self.name}] Error handling message: {e}")

    async def send(self, data: Dict[str, Any]) -> None:
        """
        Send a message to the WebSocket.

        Args:
            data: Dictionary to send as JSON.
        """
        if self._ws is None:
            logger.warning(f"[{self.name}] Cannot send, not connected")
            return

        try:
            await self._ws.send(json.dumps(data))
        except Exception as e:
            logger.error(f"[{self.name}] Error sending message: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self._ws is not None and self._ws.open

    @abstractmethod
    async def _on_connect(self, ws: WebSocketClientProtocol) -> None:
        """
        Handle connection setup (send subscriptions, auth, etc.).

        Args:
            ws: The connected WebSocket.
        """
        pass

    @abstractmethod
    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """
        Handle an incoming message.

        Args:
            data: Parsed JSON message data.
        """
        pass


class SimpleWebSocket(BaseWebSocket):
    """
    Simple WebSocket that calls a callback for each message.

    Usage:
        ws = SimpleWebSocket(
            url="wss://example.com/ws",
            on_connect=lambda ws: ws.send('{"subscribe": true}'),
            on_message=lambda data: print(data),
        )
        await ws.connect()
    """

    def __init__(
        self,
        url: str,
        on_message: Callable[[Dict[str, Any]], None],
        on_connect: Optional[Callable[[WebSocketClientProtocol], Any]] = None,
        name: Optional[str] = None,
    ):
        """
        Initialize simple WebSocket.

        Args:
            url: WebSocket URL.
            on_message: Callback for each message.
            on_connect: Optional callback when connected.
            name: Optional name for logging.
        """
        super().__init__(url, name)
        self._on_message_callback = on_message
        self._on_connect_callback = on_connect

    async def _on_connect(self, ws: WebSocketClientProtocol) -> None:
        """Call the on_connect callback if provided."""
        if self._on_connect_callback:
            result = self._on_connect_callback(ws)
            if asyncio.iscoroutine(result):
                await result

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """Call the on_message callback."""
        result = self._on_message_callback(data)
        if asyncio.iscoroutine(result):
            await result
