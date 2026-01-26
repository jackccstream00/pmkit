# pmkit

**Open-source toolkit for prediction market trading bots.**

pmkit provides infrastructure primitives for building trading bots on prediction markets. It handles the plumbing—exchange connections, data feeds, order management, WebSocket reconnection—so you can focus on strategy logic.

## Features

| Category | What's Included |
|----------|-----------------|
| **Exchanges** | Polymarket, Kalshi, Predict.fun (BNB Chain) |
| **Data Feeds** | Binance real-time WebSocket, REST historical data |
| **Bot Framework** | Lifecycle management, 15-min market rollover handling |
| **WebSockets** | Orderbook streams, user fills, auto-reconnect with backoff |
| **Utilities** | Logging, trade CSV export, .env config, interactive prompts |

## Supported Exchanges

| Exchange | Type | Features |
|----------|------|----------|
| **Polymarket** | Prediction market | Limit/market orders, positions, balance, trade history, redemption, orderbook WS, fills WS |
| **Kalshi** | Prediction market | Limit orders, positions, balance, orderbook WS |
| **Predict.fun** | Prediction market (BNB Chain) | Limit/market orders, positions, balance, trade history, orderbook WS |

### Supported Markets

15-minute crypto up/down markets:

| Asset | Polymarket | Kalshi |
|-------|------------|--------|
| BTC | `btc-updown-15m` | `KXBTC15M` |
| ETH | `eth-updown-15m` | `KXETH15M` |
| SOL | `sol-updown-15m` | `KXSOL15M` |
| XRP | `xrp-updown-15m` | — |

## Installation

### From GitHub

```bash
pip install git+https://github.com/jackccstream00/pmkit.git
```

With optional web3 support (for on-chain operations):

```bash
pip install "pmkit[web3] @ git+https://github.com/jackccstream00/pmkit.git"
```

### For Development

Clone and install in editable mode:

```bash
git clone https://github.com/jackccstream00/pmkit.git
cd pmkit
pip install -e .
```

### Requirements

- Python 3.10+

## Quick Start

```python
import asyncio
from pmkit.bot import BaseBot
from pmkit.exchanges.polymarket import PolymarketExchange, MarketFinder
from pmkit.data.binance import BinanceFeed
from pmkit.config import load_env, require_env

load_env()

class MyBot(BaseBot):
    async def _setup(self):
        self.exchange = PolymarketExchange(
            require_env("POLYMARKET_PRIVATE_KEY"),
            require_env("POLYMARKET_FUNDER_ADDRESS"),
        )
        await self.exchange.connect()

        self.feed = BinanceFeed(symbol="BTCUSDT")
        await self.feed.start()

        self.finder = MarketFinder()
        self.market = await self.finder.get_smart_market("btc")

    async def _tick(self):
        price = self.feed.get_current_price()
        # Your strategy logic here

    async def _on_rollover(self):
        self.market = await self.finder.get_smart_market("btc")

    async def _cleanup(self):
        await self.exchange.disconnect()
        await self.feed.stop()

asyncio.run(MyBot(dry_run=True).run())
```

## Configuration

Create a `.env` file:

```bash
# Polymarket (Polygon)
POLYMARKET_PRIVATE_KEY=...      # Wallet private key (no 0x prefix)
POLYMARKET_FUNDER_ADDRESS=...   # Profile address

# Kalshi
KALSHI_API_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=...     # Path to .pem file

# Predict.fun (BNB Chain)
PREDICTFUN_PRIVATE_KEY=...      # EOA private key (no 0x prefix)
PREDICTFUN_API_KEY=...          # API key (required for mainnet)
```

## Package Structure

```
pmkit/
├── bot/base.py              # BaseBot lifecycle (_setup, _tick, _on_rollover, _cleanup)
├── config/env.py            # load_env(), get_env(), require_env()
├── data/
│   ├── binance/
│   │   ├── fetcher.py       # REST historical data (BinanceFetcher)
│   │   ├── feed.py          # WebSocket real-time (BinanceFeed)
│   │   └── types.py         # Candle, Interval, SYMBOLS
│   └── storage.py           # CSV storage
├── exchanges/
│   ├── base.py              # BaseExchange ABC, OrderSide, Order, Position, Trade
│   ├── polymarket/          # PolymarketExchange, MarketFinder, OrderbookWebSocket, UserWebSocket
│   ├── kalshi/              # KalshiExchange, MarketFinder, OrderbookWebSocket
│   └── predictfun/          # PredictfunExchange, MarketFinder, OrderbookWebSocket
├── log/
│   ├── logger.py            # setup_logging()
│   ├── csv_logger.py        # TradeLogger
│   └── paths.py             # PathManager
├── prompts/inquirer.py      # select_mode(), select_assets(), confirm()
└── websocket/base.py        # BaseWebSocket with exponential backoff
```

## API Examples

### Polymarket

```python
from pmkit.exchanges.polymarket import PolymarketExchange, MarketFinder
from pmkit.exchanges.base import OrderSide

exchange = PolymarketExchange(private_key, funder_address)
await exchange.connect()

# Orders
result = await exchange.place_limit_order(token_id, OrderSide.BUY, 0.50, 10.0)
result = await exchange.place_market_order(token_id, OrderSide.SELL, 5.0)
await exchange.cancel_order(result.order_id)

# Account
positions = await exchange.get_positions()
balance = await exchange.get_balance()
trades = await exchange.get_trade_history(limit=100)

# Markets
finder = MarketFinder()
market = await finder.get_smart_market("btc")
up_token = market.up_token_id
down_token = market.down_token_id
```

### Kalshi

```python
from pmkit.exchanges.kalshi import KalshiExchange, MarketFinder
from pmkit.exchanges.base import OrderSide

exchange = KalshiExchange(api_key_id, "/path/to/key.pem")
await exchange.connect()

result = await exchange.place_limit_order(ticker, OrderSide.BUY, 0.45, 10)

finder = MarketFinder()
market = await finder.get_current_market("BTC")
```

### Predict.fun

```python
from pmkit.exchanges.predictfun import PredictfunExchange, MarketFinder
from pmkit.exchanges.base import OrderSide

exchange = PredictfunExchange(private_key, api_key=api_key)
await exchange.connect()
await exchange.set_approvals()  # One-time on-chain approval

finder = MarketFinder(api_key=api_key)
market = await finder.get_current_market("btc")

result = await exchange.place_limit_order(
    market.up_token_id, OrderSide.BUY, 0.50, 10.0, market=market
)
```

### Binance Data

```python
from pmkit.data.binance import BinanceFeed, BinanceFetcher

# Real-time WebSocket
feed = BinanceFeed(symbol="BTCUSDT")
await feed.start()
price = feed.get_current_price()
df = feed.get_candles_df()

# Historical REST
fetcher = BinanceFetcher()
candles = await fetcher.fetch("BTCUSDT", "1s", limit=1000)
```

### Logging

```python
from pmkit.log import setup_logging, TradeLogger, PathManager

logger = setup_logging("my_strategy", level="INFO", dry_run=True)

paths = PathManager("my_strategy")
trade_logger = TradeLogger(paths.trades_dir, dry_run=True)
trade_logger.log_trade({"side": "BUY", "price": 0.50, "size": 10.0})
```

## Claude Code Integration

This project is configured for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code). The configuration includes:

- **`CLAUDE.md`** — Reference documentation for the API, package structure, and examples
- **`.claude/rules/`** — Behavioral rules for Claude agents:
  - `pmkit-editing.md` — When and how to modify pmkit code
  - `file-organization.md` — Where different file types belong
  - `pmkit-boundaries.md` — What pmkit provides vs what belongs in strategy code
  - `coding-patterns.md` — Required patterns (async-first, exchange-native terms, etc.)

When using Claude Code with this project, the AI assistant will automatically follow these guidelines to maintain code quality and consistency.

## Design Philosophy

1. **Infrastructure only** — No strategy logic, ML, or risk management
2. **Exchange-native terms** — Polymarket uses Up/Down, Kalshi uses yes/no
3. **Async-first** — All I/O operations are async
4. **Auto-reconnect** — WebSockets reconnect with exponential backoff
5. **Rollover handling** — BaseBot detects 15-min market boundaries

## Dependencies

```
httpx, aiohttp          # HTTP clients
websockets              # WebSocket client
pandas                  # Data handling
python-dotenv           # .env loading
inquirer                # Interactive prompts
py-clob-client          # Polymarket CLOB
eth-account             # Ethereum signing
cryptography            # Kalshi RSA-PSS
web3                    # On-chain operations (optional)
```

## License

MIT

## Contributing

Contributions welcome. Please open an issue first to discuss what you'd like to change.
