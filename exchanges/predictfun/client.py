"""Predict.fun exchange client.

Building blocks for trading on Predict.fun prediction markets (BNB Chain).
Uses predict-sdk for order building/signing.
"""

import logging
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount
from predict_sdk import OrderBuilder
from predict_sdk.constants import ChainId, Side
from predict_sdk.types import (
    Book,
    BuildOrderInput,
    CancelOrdersOptions,
    LimitHelperInput,
    MarketHelperInput,
    MarketHelperValueInput,
    Order,
)

from pmkit.exchanges.base import (
    BaseExchange,
    Orderbook,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Trade,
)
from pmkit.exchanges.predictfun.auth import get_jwt
from pmkit.exchanges.predictfun.types import API_BASE, API_BASE_TESTNET, PredictfunMarket

logger = logging.getLogger(__name__)

# Precision: 1e18 (wei)
WEI = 10**18


class PredictfunExchange(BaseExchange):
    """
    Predict.fun exchange client.

    Building blocks only - no strategy logic.

    Usage:
        exchange = PredictfunExchange(private_key)
        await exchange.connect()

        # Place orders
        result = await exchange.place_limit_order(token_id, OrderSide.BUY, 0.50, 10.0)

        # Get positions
        positions = await exchange.get_positions()

        # Cleanup
        await exchange.disconnect()
    """

    name = "predictfun"

    def __init__(
        self,
        private_key: str,
        chain_id: int = ChainId.BNB_MAINNET,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Predict.fun client.

        Args:
            private_key: EOA private key (without 0x prefix)
            chain_id: 56 for BNB mainnet, 97 for BNB testnet
            api_key: API key (required for mainnet)
        """
        self.private_key = private_key
        self.chain_id = ChainId(chain_id)
        self.api_key = api_key

        # Determine API base from chain ID
        self.api_base = API_BASE if chain_id == ChainId.BNB_MAINNET else API_BASE_TESTNET

        # Create signer account
        self._signer: LocalAccount = Account.from_key(private_key)
        self.address = self._signer.address

        # Will be initialized on connect()
        self._builder: Optional[OrderBuilder] = None
        self._jwt: Optional[str] = None
        self._http: Optional[httpx.AsyncClient] = None
        self._initialized = False

        # Cache for market metadata (market_id -> PredictfunMarket)
        self._market_cache: Dict[int, PredictfunMarket] = {}
        # Cache for token_id -> market mapping
        self._token_market_cache: Dict[str, PredictfunMarket] = {}

        logger.info(f"Predict.fun client initializing...")
        logger.info(f"  Address: {self.address}")
        logger.info(f"  Chain: {'BNB Mainnet' if chain_id == ChainId.BNB_MAINNET else 'BNB Testnet'}")

    # === Connection ===

    async def connect(self) -> None:
        """Initialize and authenticate with Predict.fun."""
        if self._initialized:
            return

        try:
            logger.info("Initializing predict-sdk OrderBuilder...")
            self._builder = OrderBuilder.make(
                chain_id=self.chain_id,
                signer=self._signer,
            )

            logger.info("Getting JWT token...")
            self._jwt = await get_jwt(
                signer=self._signer,
                api_base=self.api_base,
                api_key=self.api_key,
            )

            # Create HTTP client with auth headers
            headers = {"Authorization": f"Bearer {self._jwt}"}
            if self.api_key:
                headers["X-Api-Key"] = self.api_key
            self._http = httpx.AsyncClient(
                base_url=self.api_base,
                headers=headers,
                timeout=30.0,
            )

            self._initialized = True
            logger.info("Predict.fun client connected")

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connections."""
        if self._http:
            await self._http.aclose()
            self._http = None
        self._builder = None
        self._jwt = None
        self._initialized = False
        self._market_cache.clear()
        self._token_market_cache.clear()
        logger.info("Predict.fun client disconnected")

    def _ensure_connected(self) -> None:
        """Ensure client is connected."""
        if not self._initialized:
            raise RuntimeError("Not connected. Call connect() first.")

    # === Market Metadata ===

    async def get_market(self, market_id: int) -> Optional[PredictfunMarket]:
        """
        Get market metadata by ID.

        Args:
            market_id: Market ID

        Returns:
            PredictfunMarket or None if not found
        """
        self._ensure_connected()

        # Check cache
        if market_id in self._market_cache:
            return self._market_cache[market_id]

        try:
            response = await self._http.get(f"/v1/markets/{market_id}")
            response.raise_for_status()
            data = response.json()

            market = PredictfunMarket.from_api_response(data)
            self._market_cache[market_id] = market

            # Cache token -> market mapping
            for outcome in market.outcomes:
                token_id = outcome.get("onChainId")
                if token_id:
                    self._token_market_cache[token_id] = market

            return market

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def _get_market_for_token(self, token_id: str) -> Optional[PredictfunMarket]:
        """Get market metadata for a token ID (from cache or API)."""
        if token_id in self._token_market_cache:
            return self._token_market_cache[token_id]

        # Need to search for the market - this is expensive
        logger.warning(f"Token {token_id} not in cache, searching...")
        return None

    # === Orders ===

    async def place_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
        market: Optional[PredictfunMarket] = None,
    ) -> OrderResult:
        """
        Place a limit order (GTC).

        Args:
            token_id: On-chain token ID
            side: BUY or SELL
            price: Limit price (0.01-0.99)
            size: Size in USDT
            market: Optional market metadata (for fee_rate, is_neg_risk)

        Returns:
            OrderResult with order_id and status
        """
        self._ensure_connected()

        # Get market metadata if not provided
        if not market:
            market = await self._get_market_for_token(token_id)

        # Default values if market not found
        fee_rate_bps = market.fee_rate_bps if market else 0
        is_neg_risk = market.is_neg_risk if market else False
        is_yield_bearing = market.is_yield_bearing if market else False

        try:
            # Convert to wei
            price_wei = int(price * WEI)
            quantity_wei = int(size * WEI)

            # Calculate order amounts
            sdk_side = Side.BUY if side == OrderSide.BUY else Side.SELL
            amounts = self._builder.get_limit_order_amounts(
                LimitHelperInput(
                    side=sdk_side,
                    price_per_share_wei=price_wei,
                    quantity_wei=quantity_wei,
                )
            )

            # Build order
            order = self._builder.build_order(
                "LIMIT",
                BuildOrderInput(
                    side=sdk_side,
                    token_id=token_id,
                    maker_amount=amounts.maker_amount,
                    taker_amount=amounts.taker_amount,
                    fee_rate_bps=fee_rate_bps,
                ),
            )

            # Build typed data and sign
            typed_data = self._builder.build_typed_data(
                order,
                is_neg_risk=is_neg_risk,
                is_yield_bearing=is_yield_bearing,
            )
            signed_order = self._builder.sign_typed_data_order(typed_data)

            # Submit to API
            response = await self._http.post(
                "/v1/orders",
                json=self._signed_order_to_api(signed_order, is_neg_risk, is_yield_bearing),
            )
            response.raise_for_status()
            data = response.json()

            order_id = data.get("id") or data.get("orderId") or data.get("hash", "")
            return OrderResult(
                order_id=str(order_id),
                status=OrderStatus.OPEN,
                raw_response=data,
            )

        except Exception as e:
            logger.error(f"Limit order failed: {e}")
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
        market: Optional[PredictfunMarket] = None,
    ) -> OrderResult:
        """
        Place a market order.

        Args:
            token_id: On-chain token ID
            side: BUY or SELL
            size: Size in USDT (for BUY) or shares (for SELL)
            market: Optional market metadata

        Returns:
            OrderResult with order_id and status
        """
        self._ensure_connected()

        # Get market metadata if not provided
        if not market:
            market = await self._get_market_for_token(token_id)

        # Get market ID for orderbook
        market_id = market.market_id if market else None
        if not market_id:
            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                message="Market ID required for market orders",
            )

        fee_rate_bps = market.fee_rate_bps if market else 0
        is_neg_risk = market.is_neg_risk if market else False
        is_yield_bearing = market.is_yield_bearing if market else False

        try:
            # Fetch orderbook
            orderbook = await self.get_orderbook(token_id, market_id=market_id)

            # Convert to SDK Book format
            book = Book(
                market_id=market_id,
                update_timestamp_ms=0,
                asks=[(a[0], a[1]) for a in orderbook.asks],
                bids=[(b[0], b[1]) for b in orderbook.bids],
            )

            # Convert to wei
            sdk_side = Side.BUY if side == OrderSide.BUY else Side.SELL

            if side == OrderSide.BUY:
                # For BUY, size is in USDT value
                value_wei = int(size * WEI)
                amounts = self._builder.get_market_order_amounts(
                    MarketHelperValueInput(side=Side.BUY, value_wei=value_wei),
                    book,
                )
            else:
                # For SELL, size is in shares
                quantity_wei = int(size * WEI)
                amounts = self._builder.get_market_order_amounts(
                    MarketHelperInput(side=sdk_side, quantity_wei=quantity_wei),
                    book,
                )

            # Build order
            order = self._builder.build_order(
                "MARKET",
                BuildOrderInput(
                    side=sdk_side,
                    token_id=token_id,
                    maker_amount=amounts.maker_amount,
                    taker_amount=amounts.taker_amount,
                    fee_rate_bps=fee_rate_bps,
                ),
            )

            # Build typed data and sign
            typed_data = self._builder.build_typed_data(
                order,
                is_neg_risk=is_neg_risk,
                is_yield_bearing=is_yield_bearing,
            )
            signed_order = self._builder.sign_typed_data_order(typed_data)

            # Submit to API
            response = await self._http.post(
                "/v1/orders",
                json=self._signed_order_to_api(signed_order, is_neg_risk, is_yield_bearing),
            )
            response.raise_for_status()
            data = response.json()

            order_id = data.get("id") or data.get("orderId") or data.get("hash", "")
            return OrderResult(
                order_id=str(order_id),
                status=OrderStatus.FILLED,
                raw_response=data,
            )

        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                message=str(e),
            )

    def _signed_order_to_api(
        self,
        signed_order: Any,
        is_neg_risk: bool,
        is_yield_bearing: bool,
    ) -> Dict[str, Any]:
        """Convert SDK SignedOrder to API format."""
        return {
            "salt": signed_order.salt,
            "maker": signed_order.maker,
            "signer": signed_order.signer,
            "taker": signed_order.taker,
            "tokenId": signed_order.token_id,
            "makerAmount": signed_order.maker_amount,
            "takerAmount": signed_order.taker_amount,
            "expiration": signed_order.expiration,
            "nonce": signed_order.nonce,
            "feeRateBps": signed_order.fee_rate_bps,
            "side": signed_order.side.value if hasattr(signed_order.side, "value") else signed_order.side,
            "signatureType": signed_order.signature_type.value if hasattr(signed_order.signature_type, "value") else signed_order.signature_type,
            "signature": signed_order.signature,
            "isNegRisk": is_neg_risk,
            "isYieldBearing": is_yield_bearing,
        }

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Note: Predict.fun cancel is an on-chain transaction. This method
        uses the SDK's cancel_orders which sends a blockchain tx.

        Args:
            order_id: Order ID (hash) to cancel

        Returns:
            True if cancelled successfully
        """
        self._ensure_connected()

        try:
            # First get order details to reconstruct the Order object
            response = await self._http.get(
                "/v1/orders",
                params={"hash": order_id},
            )
            response.raise_for_status()
            orders = response.json()

            if not orders:
                logger.warning(f"Order not found: {order_id}")
                return False

            order_data = orders[0] if isinstance(orders, list) else orders

            # Get market info for cancel options
            is_neg_risk = order_data.get("isNegRisk", False)
            is_yield_bearing = order_data.get("isYieldBearing", False)

            # Reconstruct Order object
            order = Order(
                salt=str(order_data.get("salt", "0")),
                maker=order_data.get("maker", ""),
                signer=order_data.get("signer", ""),
                taker=order_data.get("taker", ""),
                token_id=str(order_data.get("tokenId", "")),
                maker_amount=str(order_data.get("makerAmount", "0")),
                taker_amount=str(order_data.get("takerAmount", "0")),
                expiration=str(order_data.get("expiration", "0")),
                nonce=str(order_data.get("nonce", "0")),
                fee_rate_bps=str(order_data.get("feeRateBps", "0")),
                side=Side(order_data.get("side", 0)),
                signature_type=order_data.get("signatureType", 0),
            )

            # Cancel on-chain
            result = await self._builder.cancel_orders_async(
                [order],
                CancelOrdersOptions(
                    is_neg_risk=is_neg_risk,
                    is_yield_bearing=is_yield_bearing,
                ),
            )

            if result.success:
                logger.info(f"Order cancelled: {order_id}")
                return True
            else:
                logger.warning(f"Cancel failed: {result}")
                return False

        except Exception as e:
            logger.error(f"Cancel order error: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """
        Get order status.

        Args:
            order_id: Order ID (hash) to check

        Returns:
            OrderResult with current status, or None if not found
        """
        self._ensure_connected()

        try:
            response = await self._http.get(
                "/v1/orders",
                params={"hash": order_id},
            )
            response.raise_for_status()
            orders = response.json()

            if not orders:
                return None

            order = orders[0] if isinstance(orders, list) else orders
            status = self._parse_order_status(order.get("status", ""))

            return OrderResult(
                order_id=order_id,
                status=status,
                filled_size=float(order.get("filledAmount", 0)) / WEI,
                raw_response=order,
            )

        except Exception as e:
            logger.error(f"Get order status error: {e}")
            return None

    async def get_open_orders(self) -> List[OrderResult]:
        """Get all open orders."""
        self._ensure_connected()

        try:
            response = await self._http.get(
                "/v1/orders",
                params={"status": "OPEN", "maker": self.address},
            )
            response.raise_for_status()
            orders = response.json()

            results = []
            for order in orders or []:
                status = self._parse_order_status(order.get("status", ""))
                results.append(
                    OrderResult(
                        order_id=order.get("hash", order.get("id", "")),
                        status=status,
                        filled_size=float(order.get("filledAmount", 0)) / WEI,
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
            "OPEN": OrderStatus.OPEN,
            "FILLED": OrderStatus.FILLED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "EXPIRED": OrderStatus.CANCELLED,
            "PENDING": OrderStatus.PENDING,
        }
        return status_map.get(status.upper(), OrderStatus.PENDING)

    # === Positions ===

    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        self._ensure_connected()

        try:
            response = await self._http.get(
                "/v1/positions",
                params={"address": self.address},
            )
            response.raise_for_status()
            data = response.json()

            positions = []
            for pos in data or []:
                size = float(pos.get("size", 0)) / WEI
                if size <= 0:
                    continue

                # Determine direction from outcome name
                outcome_name = pos.get("outcomeName", "")
                direction = outcome_name.upper() if outcome_name else ""

                positions.append(
                    Position(
                        token_id=pos.get("tokenId", ""),
                        size=size,
                        avg_price=float(pos.get("avgPrice", 0)) / WEI if pos.get("avgPrice") else 0,
                        side=direction,
                        market_id=str(pos.get("marketId", "")),
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
        """Get available USDT balance."""
        self._ensure_connected()

        try:
            # Use SDK to get on-chain balance
            balance_wei = await self._builder.balance_of_async("USDT")
            return Decimal(str(balance_wei)) / Decimal(str(WEI))

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

        try:
            params = {
                "address": self.address,
                "limit": limit,
            }
            if market_id:
                params["marketId"] = market_id

            response = await self._http.get("/v1/orders", params={**params, "status": "FILLED"})
            response.raise_for_status()
            data = response.json()

            trades = []
            for t in data or []:
                from datetime import datetime

                # Parse timestamp
                timestamp = None
                ts_str = t.get("filledAt") or t.get("createdAt")
                if ts_str:
                    try:
                        timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                trades.append(
                    Trade(
                        trade_id=t.get("hash", t.get("id", "")),
                        token_id=t.get("tokenId", ""),
                        side="BUY" if t.get("side") == 0 else "SELL",
                        price=float(t.get("price", 0)) / WEI if t.get("price") else 0,
                        size=float(t.get("filledAmount", 0)) / WEI,
                        timestamp=timestamp,
                        market_id=str(t.get("marketId", "")),
                    )
                )

            return trades[:limit]

        except Exception as e:
            logger.error(f"Get trade history error: {e}")
            return []

    # === Market Data ===

    async def get_orderbook(
        self,
        token_id: str,
        market_id: Optional[int] = None,
    ) -> Orderbook:
        """
        Get current orderbook for a token.

        Args:
            token_id: On-chain token ID
            market_id: Market ID (required for API call)
        """
        self._ensure_connected()

        if not market_id:
            # Try to get from cache
            market = self._token_market_cache.get(token_id)
            if market:
                market_id = market.market_id
            else:
                return Orderbook(token_id=token_id, bids=[], asks=[])

        try:
            response = await self._http.get(f"/v1/orderbook/{market_id}")
            response.raise_for_status()
            data = response.json()

            bids = []
            asks = []

            # Find the right outcome in the orderbook
            for outcome in data.get("outcomes", []):
                if outcome.get("onChainId") == token_id:
                    for b in outcome.get("bids", []):
                        bids.append((float(b["price"]), float(b["quantity"])))
                    for a in outcome.get("asks", []):
                        asks.append((float(a["price"]), float(a["quantity"])))
                    break

            # Sort: bids descending, asks ascending
            bids.sort(key=lambda x: x[0], reverse=True)
            asks.sort(key=lambda x: x[0])

            return Orderbook(token_id=token_id, bids=bids, asks=asks)

        except Exception as e:
            logger.error(f"Get orderbook error: {e}")
            return Orderbook(token_id=token_id, bids=[], asks=[])

    # === Approvals ===

    async def set_approvals(
        self,
        is_yield_bearing: bool = False,
    ) -> bool:
        """
        Set all necessary approvals for trading.

        Args:
            is_yield_bearing: Whether to set approvals for yield-bearing markets

        Returns:
            True if all approvals succeeded
        """
        self._ensure_connected()

        try:
            result = await self._builder.set_approvals_async(is_yield_bearing=is_yield_bearing)
            if result.success:
                logger.info("All approvals set successfully")
            else:
                logger.warning(f"Some approvals failed: {result}")
            return result.success

        except Exception as e:
            logger.error(f"Set approvals error: {e}")
            return False
