"""
pmkit - Prediction Market Bot Framework

A framework providing building blocks for prediction market trading bots.
Strategies compose these blocks - pmkit doesn't impose strategy logic.

Philosophy: Infrastructure only. No features, no ML, no risk management.
"""

from pmkit.version import __version__

# Bot lifecycle
from pmkit.bot import BaseBot

# Exchange base
from pmkit.exchanges.base import (
    BaseExchange,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Orderbook,
    Position,
    Trade,
    Market,
)

# WebSocket base
from pmkit.websocket import BaseWebSocket

# Configuration
from pmkit.config import load_env, get_env, require_env

# Logging
from pmkit.log import setup_logging, TradeLogger, PathManager

__all__ = [
    "__version__",
    # Bot
    "BaseBot",
    # Exchange base
    "BaseExchange",
    "Order",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Orderbook",
    "Position",
    "Trade",
    "Market",
    # WebSocket
    "BaseWebSocket",
    # Config
    "load_env",
    "get_env",
    "require_env",
    # Logging
    "setup_logging",
    "TradeLogger",
    "PathManager",
]
