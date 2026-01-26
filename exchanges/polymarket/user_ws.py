"""Polymarket user WebSocket.

Authenticated WebSocket for fill and order notifications.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Callable, Optional

from pmkit.websocket.base import BaseWebSocket

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"


class UserWebSocket(BaseWebSocket):
    """
    Authenticated Polymarket user WebSocket.

    Receives real-time fill and order notifications.

    Usage:
        ws = UserWebSocket(api_key, api_secret, api_passphrase)
        await ws.connect(on_fill=handle_fill, on_order=handle_order)
        await ws.run()  # Blocks until stopped
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
    ):
        """
        Initialize user WebSocket.

        Args:
            api_key: Polymarket API key
            api_secret: Polymarket API secret (base64 encoded)
            api_passphrase: Polymarket API passphrase
        """
        super().__init__(url=WS_URL)
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self._on_fill: Optional[Callable[[dict], Any]] = None
        self._on_order: Optional[Callable[[dict], Any]] = None

    async def connect(
        self,
        on_fill: Optional[Callable[[dict], Any]] = None,
        on_order: Optional[Callable[[dict], Any]] = None,
    ) -> None:
        """
        Connect to authenticated user WebSocket.

        Args:
            on_fill: Callback for trade fill events
            on_order: Callback for order events (placement, update, cancellation)
        """
        self._on_fill = on_fill
        self._on_order = on_order
        await self.start()

    async def _on_connect(self, ws) -> None:
        """Authenticate on connect."""
        timestamp = int(time.time())
        message = f"GET\n{timestamp}\n/ws/user"

        # Sign the message
        signature = hmac.new(
            base64.b64decode(self.api_secret),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        auth_msg = {
            "type": "auth",
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "passphrase": self.api_passphrase,
            "timestamp": timestamp,
            "signature": signature_b64,
        }

        await ws.send(json.dumps(auth_msg))
        logger.info("[UserWS] Authenticated")

    async def _handle_message(self, data: Any) -> None:
        """Handle incoming WebSocket message."""
        if not isinstance(data, dict):
            return

        event_type = data.get("event_type", "").lower()

        if event_type == "trade":
            await self._handle_trade(data)
        elif event_type == "order":
            await self._handle_order(data)

    async def _handle_trade(self, data: dict) -> None:
        """Handle trade/fill event."""
        status = data.get("status", "").upper()

        # Only process completed fills
        if status in ("MATCHED", "MINED", "CONFIRMED"):
            logger.info(
                f"[UserWS] Fill: {data.get('side')} {data.get('size')} @ {data.get('price')} ({status})"
            )

            if self._on_fill:
                result = self._on_fill(data)
                if asyncio.iscoroutine(result):
                    await result

    async def _handle_order(self, data: dict) -> None:
        """Handle order event."""
        if self._on_order:
            result = self._on_order(data)
            if asyncio.iscoroutine(result):
                await result
