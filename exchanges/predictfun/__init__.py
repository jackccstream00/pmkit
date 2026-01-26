"""Predict.fun exchange module.

Building blocks for trading on Predict.fun prediction markets (BNB Chain).
"""

from pmkit.exchanges.predictfun.client import PredictfunExchange
from pmkit.exchanges.predictfun.market_finder import MarketFinder
from pmkit.exchanges.predictfun.orderbook_ws import OrderbookWebSocket
from pmkit.exchanges.predictfun.types import (
    API_BASE,
    API_BASE_TESTNET,
    WS_URL,
    WS_URL_TESTNET,
    SUPPORTED_ASSETS,
    PredictfunMarket,
    get_opposite_direction,
)

__all__ = [
    # Main client
    "PredictfunExchange",
    # Market discovery
    "MarketFinder",
    # WebSocket
    "OrderbookWebSocket",
    # Types
    "PredictfunMarket",
    # Constants
    "API_BASE",
    "API_BASE_TESTNET",
    "WS_URL",
    "WS_URL_TESTNET",
    "SUPPORTED_ASSETS",
    # Helpers
    "get_opposite_direction",
]
