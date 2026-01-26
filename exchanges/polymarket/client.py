"""Polymarket exchange client.

Building blocks for trading on Polymarket prediction markets.
Uses py-clob-client for order placement.
"""

import logging
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

import httpx
from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderArgs, OrderType, TradeParams

from pmkit.exchanges.base import (
    BaseExchange,
    Order,
    Orderbook,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Trade,
)

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"


class PolymarketExchange(BaseExchange):
    """
    Polymarket exchange client.

    Building blocks only - no strategy logic.

    Usage:
        exchange = PolymarketExchange(private_key, funder_address)
        await exchange.connect()

        # Place orders
        result = await exchange.place_limit_order(token_id, OrderSide.BUY, 0.50, 10.0)

        # Get positions
        positions = await exchange.get_positions()

        # Cleanup
        await exchange.disconnect()
    """

    name = "polymarket"

    def __init__(
        self,
        private_key: str,
        funder_address: str,
        chain_id: int = 137,
        host: str = CLOB_HOST,
    ):
        """
        Initialize Polymarket client.

        Args:
            private_key: Ethereum private key (signer wallet, without 0x prefix)
            funder_address: Polymarket Profile Address (where USDC is deposited)
            chain_id: 137 for Polygon mainnet, 80002 for Amoy testnet
            host: CLOB API host
        """
        self.private_key = private_key
        self.funder_address = funder_address
        self.chain_id = chain_id
        self.host = host
        self._client: Optional[ClobClient] = None
        self._api_creds = None
        self._initialized = False

        # Get signer address
        account = Account.from_key(private_key)
        self.signer_address = account.address

        logger.info(f"Polymarket client initializing...")
        logger.info(f"  Signer: {self.signer_address}")
        logger.info(f"  Funder: {self.funder_address}")

    # === Connection ===

    async def connect(self) -> None:
        """Initialize and authenticate with Polymarket."""
        if self._initialized:
            return

        try:
            logger.info("Deriving API key from private key...")

            self._client = ClobClient(
                host=self.host,
                chain_id=self.chain_id,
                key=self.private_key,
                funder=self.funder_address,
                signature_type=2,  # Magic/email-based logins
            )

            self._api_creds = self._client.derive_api_key()
            self._client.set_api_creds(self._api_creds)

            self._initialized = True
            logger.info("Polymarket client connected")

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connections."""
        self._client = None
        self._api_creds = None
        self._initialized = False
        logger.info("Polymarket client disconnected")

    def _ensure_connected(self) -> None:
        """Ensure client is connected."""
        if not self._initialized:
            raise RuntimeError("Not connected. Call connect() first.")

    # === Orders ===

    async def place_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
    ) -> OrderResult:
        """
        Place a limit order (GTC).

        Args:
            token_id: CLOB token ID
            side: BUY or SELL
            price: Limit price (0.01-0.99)
            size: Number of shares

        Returns:
            OrderResult with order_id and status
        """
        self._ensure_connected()

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side.value,
        )

        try:
            response = self._client.create_and_post_order(order_args)

            if response and "orderID" in response:
                return OrderResult(
                    order_id=response["orderID"],
                    status=OrderStatus.OPEN,
                    raw_response=response,
                )
            else:
                return OrderResult(
                    order_id="",
                    status=OrderStatus.REJECTED,
                    message=str(response),
                    raw_response=response,
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
    ) -> OrderResult:
        """
        Place a market order (FAK - Fill And Kill, allows partial fills).

        Args:
            token_id: CLOB token ID
            side: BUY or SELL
            size: Dollar amount to spend

        Returns:
            OrderResult with order_id and status
        """
        self._ensure_connected()

        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=size,
            side=side.value,
        )

        try:
            signed_order = self._client.create_market_order(order_args)
            response = self._client.post_order(signed_order, OrderType.FAK)

            if response and "orderID" in response:
                return OrderResult(
                    order_id=response["orderID"],
                    status=OrderStatus.FILLED,
                    raw_response=response,
                )
            else:
                return OrderResult(
                    order_id="",
                    status=OrderStatus.REJECTED,
                    message=str(response),
                    raw_response=response,
                )

        except Exception as e:
            error_msg = str(e).lower()
            if "no orders found to match" in error_msg:
                logger.warning("Market order: no liquidity")
            else:
                logger.error(f"Market order failed: {e}")

            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                message=str(e),
            )

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        self._ensure_connected()

        try:
            response = self._client.cancel(order_id)
            if response:
                logger.info(f"Order cancelled: {order_id}")
                return True
            else:
                logger.warning(f"Failed to cancel order: {order_id}")
                return False

        except Exception as e:
            logger.error(f"Cancel order error: {e}")
            return False

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        self._ensure_connected()

        try:
            response = self._client.cancel_all()
            if response:
                logger.info("All orders cancelled")
                return True
            else:
                logger.warning("Failed to cancel all orders")
                return False

        except Exception as e:
            logger.error(f"Cancel all orders error: {e}")
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

        try:
            orders = self._client.get_orders()
            for order in orders or []:
                if order.get("id") == order_id:
                    status = self._parse_order_status(order.get("status", ""))
                    return OrderResult(
                        order_id=order_id,
                        status=status,
                        filled_size=float(order.get("size_matched", 0)),
                        raw_response=order,
                    )
            return None

        except Exception as e:
            logger.error(f"Get order status error: {e}")
            return None

    async def get_open_orders(self) -> List[OrderResult]:
        """Get all open orders."""
        self._ensure_connected()

        try:
            orders = self._client.get_orders() or []
            results = []

            for order in orders:
                status = self._parse_order_status(order.get("status", ""))
                results.append(
                    OrderResult(
                        order_id=order.get("id", ""),
                        status=status,
                        filled_size=float(order.get("size_matched", 0)),
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
            "live": OrderStatus.OPEN,
            "matched": OrderStatus.FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "pending": OrderStatus.PENDING,
        }
        return status_map.get(status.lower(), OrderStatus.PENDING)

    # === Positions ===

    async def get_positions(self) -> List[Position]:
        """Get all current positions (paginated)."""
        try:
            from datetime import datetime

            positions = []
            offset = 0
            page_size = 500

            async with httpx.AsyncClient(timeout=30.0) as client:
                while True:
                    response = await client.get(
                        f"{DATA_API}/positions",
                        params={"user": self.funder_address, "limit": page_size, "offset": offset},
                    )

                    if response.status_code != 200:
                        logger.error(f"Failed to fetch positions: {response.status_code}")
                        break

                    data = response.json()
                    if not data or not isinstance(data, list):
                        break

                    for pos in data:
                        size = float(pos.get("size", 0))
                        if size <= 0:
                            continue

                        asset_id = (
                            pos.get("asset")
                            or pos.get("assetId")
                            or pos.get("token_id")
                            or pos.get("tokenId")
                        )

                        # Parse end_date
                        end_date = None
                        end_date_str = pos.get("endDate")
                        if end_date_str:
                            try:
                                end_date = datetime.fromisoformat(end_date_str)
                            except Exception:
                                pass

                        positions.append(
                            Position(
                                token_id=asset_id or "",
                                size=size,
                                avg_price=float(pos.get("avgPrice", pos.get("avg_price", 0))),
                                side=pos.get("outcome", "").upper(),
                                market_id=pos.get("conditionId"),
                                market_slug=pos.get("slug") or pos.get("eventSlug"),
                                redeemable=str(pos.get("redeemable", "")).lower() == "true",
                                end_date=end_date,
                                current_value=float(pos.get("currentValue", 0)),
                            )
                        )

                    # Check if we got less than a full page (no more data)
                    if len(data) < page_size:
                        break
                    offset += page_size

            return positions

        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []

    async def get_positions_by_market(self, market_id: str) -> List[Position]:
        """
        Get positions for a specific market.

        Args:
            market_id: Condition ID or slug
        """
        positions = await self.get_positions()
        return [
            p
            for p in positions
            if p.market_id == market_id or p.market_slug == market_id
        ]

    async def get_positions_by_token(self, token_id: str) -> List[Position]:
        """
        Get positions for a specific token.

        Args:
            token_id: CLOB token ID
        """
        positions = await self.get_positions()
        return [p for p in positions if p.token_id == token_id]

    async def get_balance(self) -> Decimal:
        """Get available USDC balance."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{DATA_API}/balance",
                    params={"user": self.funder_address},
                )

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and "balance" in data:
                        return Decimal(str(data["balance"]))
                    elif isinstance(data, (int, float, str)):
                        return Decimal(str(data))

                logger.debug("Balance endpoint not available")
                return Decimal("0")

        except Exception as e:
            logger.error(f"Get balance error: {e}")
            return Decimal("0")

    # === Trade History ===

    async def get_trade_history(
        self,
        limit: int = 100,
        market_id: Optional[str] = None,
    ) -> List[Trade]:
        """
        Get historical trades where this account was the maker.

        Args:
            limit: Maximum number of trades to return
            market_id: Optional token/asset ID to filter by

        Returns:
            List of Trade objects, most recent first
        """
        self._ensure_connected()

        try:
            if market_id:
                params = TradeParams(maker_address=self.funder_address, asset_id=market_id)
            else:
                params = TradeParams(maker_address=self.funder_address)

            raw_trades = self._client.get_trades(params) or []

            # Parse all trades with timestamps
            from datetime import datetime, timezone as tz

            trades = []
            for t in raw_trades:
                # Parse timestamp (ISO format or unix timestamp)
                ts_str = t.get("created_at") or t.get("timestamp") or t.get("match_time", "")
                timestamp = None
                if ts_str:
                    try:
                        if "T" in ts_str:
                            if ts_str.endswith("Z"):
                                ts_str = ts_str[:-1] + "+00:00"
                            timestamp = datetime.fromisoformat(ts_str)
                        else:
                            # Unix timestamp fallback
                            timestamp = datetime.fromtimestamp(float(ts_str), tz=tz.utc)
                    except Exception:
                        pass

                trades.append(
                    Trade(
                        trade_id=t.get("id", t.get("trade_id", "")),
                        token_id=t.get("asset_id", t.get("market", "")),
                        side=t.get("side", "").upper(),
                        price=float(t.get("price", 0)),
                        size=float(t.get("size", 0)),
                        timestamp=timestamp,
                        outcome=t.get("outcome", ""),
                    )
                )

            # Sort by timestamp descending (newest first), then limit
            min_time = datetime.min.replace(tzinfo=tz.utc)
            trades.sort(key=lambda t: t.timestamp or min_time, reverse=True)

            return trades[:limit]

        except Exception as e:
            logger.error(f"Get trade history error: {e}")
            return []

    # === Market Data ===

    async def get_orderbook(self, token_id: str) -> Orderbook:
        """Get current orderbook for a token."""
        self._ensure_connected()

        try:
            book = self._client.get_order_book(token_id)

            bids = []
            asks = []

            if book and "bids" in book:
                for b in book["bids"]:
                    bids.append((float(b["price"]), float(b["size"])))

            if book and "asks" in book:
                for a in book["asks"]:
                    asks.append((float(a["price"]), float(a["size"])))

            return Orderbook(token_id=token_id, bids=bids, asks=asks)

        except Exception as e:
            logger.error(f"Get orderbook error: {e}")
            return Orderbook(token_id=token_id, bids=[], asks=[])

    async def get_midpoint(self, token_id: str) -> Optional[float]:
        """Get midpoint price for a token."""
        self._ensure_connected()

        try:
            midpoint = self._client.get_midpoint(token_id)

            if midpoint is None:
                return None

            if isinstance(midpoint, dict):
                mid_val = midpoint.get("mid") or midpoint.get("midpoint")
                if mid_val is not None:
                    return float(mid_val)
                return None
            else:
                return float(midpoint)

        except Exception as e:
            logger.error(f"Get midpoint error: {e}")
            return None

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
        from pmkit.exchanges.polymarket.orderbook_ws import OrderbookWebSocket

        self._orderbook_ws = OrderbookWebSocket()
        await self._orderbook_ws.connect(token_ids, callback)

    async def subscribe_fills(
        self,
        callback: Callable[[OrderResult], None],
    ) -> None:
        """
        Subscribe to fill notifications.

        Note: Use UserWebSocket directly for more control.
        """
        if not self._api_creds:
            raise RuntimeError("Not connected. Call connect() first.")

        from pmkit.exchanges.polymarket.user_ws import UserWebSocket

        def wrap_callback(data: dict):
            result = OrderResult(
                order_id=data.get("id", ""),
                status=OrderStatus.FILLED,
                filled_size=float(data.get("size", 0)),
                filled_price=float(data.get("price", 0)) if data.get("price") else None,
                raw_response=data,
            )
            callback(data.get("asset_id", ""), result)

        self._user_ws = UserWebSocket(
            api_key=self._api_creds.api_key,
            api_secret=self._api_creds.api_secret,
            api_passphrase=self._api_creds.api_passphrase,
        )
        await self._user_ws.connect(on_fill=wrap_callback)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all WebSocket subscriptions."""
        if hasattr(self, "_orderbook_ws") and self._orderbook_ws:
            await self._orderbook_ws.stop()
            self._orderbook_ws = None

        if hasattr(self, "_user_ws") and self._user_ws:
            await self._user_ws.stop()
            self._user_ws = None

    # === API Credentials ===

    @property
    def api_credentials(self):
        """Get API credentials for external use (e.g., UserWebSocket)."""
        return self._api_creds

    # === Redemption ===

    async def redeem(self, condition_id: str) -> Dict[str, Any]:
        """
        Redeem positions for a resolved market.

        Claims USDC collateral for winning positions after market resolution.
        Requires web3.py and sufficient MATIC for gas.

        Args:
            condition_id: The market's condition ID (bytes32 hex string)

        Returns:
            Dict with transaction hash and status

        Raises:
            ImportError: If web3.py is not installed
            RuntimeError: If not connected or transaction fails
        """
        try:
            from web3 import Web3
            from web3.middleware import ExtraDataToPOAMiddleware
        except ImportError:
            raise ImportError(
                "web3.py required for redemption. Install with: pip install web3"
            )

        # Polygon mainnet RPC
        POLYGON_RPC = "https://polygon-rpc.com"

        # Contract addresses
        CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
        USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e

        # CTF redeemPositions ABI (minimal)
        CTF_ABI = [
            {
                "inputs": [
                    {"name": "collateralToken", "type": "address"},
                    {"name": "parentCollectionId", "type": "bytes32"},
                    {"name": "conditionId", "type": "bytes32"},
                    {"name": "indexSets", "type": "uint256[]"},
                ],
                "name": "redeemPositions",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]

        try:
            # Connect to Polygon
            w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

            if not w3.is_connected():
                raise RuntimeError("Failed to connect to Polygon RPC")

            # Create contract instance
            ctf_contract = w3.eth.contract(
                address=Web3.to_checksum_address(CTF_ADDRESS),
                abi=CTF_ABI,
            )

            # Prepare parameters
            collateral_token = Web3.to_checksum_address(USDC_ADDRESS)
            parent_collection_id = bytes(32)  # Null for Polymarket
            condition_id_bytes = bytes.fromhex(
                condition_id[2:] if condition_id.startswith("0x") else condition_id
            )
            # Binary market: index sets [1, 2] for YES and NO outcomes
            index_sets = [1, 2]

            # Get account from private key
            account = Account.from_key(self.private_key)

            # Build transaction
            tx = ctf_contract.functions.redeemPositions(
                collateral_token,
                parent_collection_id,
                condition_id_bytes,
                index_sets,
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": w3.eth.get_transaction_count(account.address),
                    "gas": 200000,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": 137,
                }
            )

            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(f"Redeem transaction sent: {tx_hash.hex()}")

            # Wait for receipt
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt["status"] == 1:
                logger.info(f"Redeem successful: {tx_hash.hex()}")
                return {
                    "success": True,
                    "tx_hash": tx_hash.hex(),
                    "gas_used": receipt["gasUsed"],
                }
            else:
                logger.error(f"Redeem failed: {tx_hash.hex()}")
                return {
                    "success": False,
                    "tx_hash": tx_hash.hex(),
                    "error": "Transaction reverted",
                }

        except Exception as e:
            logger.error(f"Redeem error: {e}")
            raise RuntimeError(f"Redeem failed: {e}")
