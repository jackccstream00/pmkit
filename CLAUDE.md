# pmkit - Reference Documentation

pmkit is a **building-block framework** for prediction market trading bots. It provides infrastructure primitives that strategies compose - it does NOT contain strategy logic.

> **Note:** Behavioral rules are in `.claude/rules/`. This file is reference documentation only.

---

## Package Structure

```
pmkit/
├── bot/base.py           # BaseBot lifecycle (start/stop/tick/rollover)
├── config/env.py         # .env loading (load_env, get_env, require_env)
├── data/
│   ├── binance/
│   │   ├── fetcher.py    # REST historical data (BinanceFetcher)
│   │   ├── feed.py       # WebSocket real-time (BinanceFeed)
│   │   └── types.py      # Candle, Interval, SYMBOLS
│   └── storage.py        # CSV storage (CSVStorage)
├── exchanges/
│   ├── base.py           # BaseExchange ABC, Order/Position/Trade types
│   ├── polymarket/
│   │   ├── client.py     # PolymarketExchange
│   │   ├── market_finder.py
│   │   ├── orderbook_ws.py
│   │   ├── user_ws.py
│   │   └── types.py      # PolymarketMarket
│   ├── kalshi/
│   │   ├── client.py     # KalshiExchange
│   │   ├── market_finder.py
│   │   ├── orderbook_ws.py
│   │   ├── auth.py       # RSA-PSS signing
│   │   └── types.py      # KalshiMarket
│   └── predictfun/
│       ├── client.py     # PredictfunExchange (BNB Chain)
│       ├── market_finder.py
│       ├── orderbook_ws.py
│       ├── auth.py       # JWT authentication
│       └── types.py      # PredictfunMarket
├── log/
│   ├── logger.py         # setup_logging()
│   ├── csv_logger.py     # CSVLogger, TradeLogger
│   └── paths.py          # PathManager
├── prompts/inquirer.py   # select_mode, select_assets, confirm
└── websocket/base.py     # BaseWebSocket with reconnection
```

---

## API Reference

### BaseBot Lifecycle

```python
from pmkit.bot import BaseBot

class MyBot(BaseBot):
    async def _setup(self):
        # Initialize exchanges, feeds, etc.
        pass

    async def _tick(self):
        # Main loop logic (called every tick_interval seconds)
        pass

    async def _on_rollover(self):
        # Handle 15-min market boundary transitions
        pass

    async def _cleanup(self):
        # Cleanup on shutdown
        pass

bot = MyBot(dry_run=True, tick_interval=1.0)
await bot.run()
```

### Polymarket Exchange

```python
from pmkit.exchanges.polymarket import PolymarketExchange, MarketFinder
from pmkit.exchanges.base import OrderSide

exchange = PolymarketExchange(private_key, funder_address)
await exchange.connect()

# Orders
result = await exchange.place_limit_order(token_id, OrderSide.BUY, 0.50, 10.0)
result = await exchange.place_market_order(token_id, OrderSide.SELL, 5.0)
await exchange.cancel_order(result.order_id)

# Positions
positions = await exchange.get_positions()
positions = await exchange.get_positions_by_market(condition_id)
positions = await exchange.get_positions_by_token(token_id)
balance = await exchange.get_balance()

# Trade history
trades = await exchange.get_trade_history(limit=100)

# Redemption (requires web3.py)
result = await exchange.redeem(condition_id)

# Markets
finder = MarketFinder()
market = await finder.get_smart_market("btc")  # Smart: next before boundary, current after
up_token = market.up_token_id
down_token = market.down_token_id
```

### Kalshi Exchange

```python
from pmkit.exchanges.kalshi import KalshiExchange, MarketFinder
from pmkit.exchanges.base import OrderSide

exchange = KalshiExchange(api_key_id, "/path/to/key.pem")
await exchange.connect()

# Orders (price in decimal 0.01-0.99, size in contracts)
result = await exchange.place_limit_order(ticker, OrderSide.BUY, 0.45, 10)

# Markets
finder = MarketFinder()
market = await finder.get_current_market("BTC")
ticker = market.ticker
```

### Predict.fun Exchange (BNB Chain)

**Note:** Uses predict-sdk for order building/signing.

```python
from pmkit.exchanges.predictfun import PredictfunExchange, MarketFinder, OrderbookWebSocket
from pmkit.exchanges.base import OrderSide

exchange = PredictfunExchange(private_key, api_key=api_key)  # api_key required for mainnet
await exchange.connect()

# Set approvals (one-time, on-chain)
await exchange.set_approvals()

# Find markets
finder = MarketFinder(api_key=api_key)
market = await finder.get_current_market("btc")
up_token = market.up_token_id
down_token = market.down_token_id

# Orders (price 0.01-0.99, size in USDT)
result = await exchange.place_limit_order(up_token, OrderSide.BUY, 0.50, 10.0, market=market)
result = await exchange.place_market_order(up_token, OrderSide.BUY, 10.0, market=market)
await exchange.cancel_order(result.order_id)  # On-chain transaction

# Positions & balance
positions = await exchange.get_positions()
balance = await exchange.get_balance()  # USDT balance

# Trade history
trades = await exchange.get_trade_history(limit=100)

# Real-time orderbook
ws = OrderbookWebSocket()
await ws.connect()
await ws.subscribe(market_id=market.market_id, callback=lambda mid, ob: print(ob.mid_price))
await ws.disconnect()

await exchange.disconnect()
```

### Binance Data

```python
from pmkit.data.binance import BinanceFeed, BinanceFetcher

# Live WebSocket feed
feed = BinanceFeed(symbol="BTCUSDT")
await feed.start()
price = feed.get_current_price()
df = feed.get_candles_df()

# Historical REST data
fetcher = BinanceFetcher()
candles = await fetcher.fetch("BTCUSDT", "1s", limit=1000)
```

### Logging

```python
from pmkit.log import setup_logging, TradeLogger, PathManager

# Python logging
logger = setup_logging("my_strategy", level="INFO", dry_run=True)

# Trade CSV logging
paths = PathManager("my_strategy")
trade_logger = TradeLogger(paths.trades_dir, dry_run=True)
trade_logger.log_trade({...})
```

### Configuration

```python
from pmkit.config import load_env, get_env, require_env

load_env()  # Load .env from current dir
api_key = get_env("API_KEY", "default")  # With default
secret = require_env("SECRET")  # Raises if missing
```

---

## Environment Variables

```bash
# Polymarket
POLYMARKET_PRIVATE_KEY=...      # Signer wallet private key (no 0x prefix)
POLYMARKET_FUNDER_ADDRESS=...   # Profile address (where USDC is)

# Kalshi
KALSHI_API_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=...     # Path to .pem file

# Predict.fun
PREDICTFUN_PRIVATE_KEY=...      # EOA private key (no 0x prefix)
PREDICTFUN_API_KEY=...          # API key (required for mainnet)
```

---

## Terminology

Exchange-native terms:
- Polymarket: `Up`, `Down`
- Kalshi: `yes`, `no`
- Predict.fun: `Up`, `Down`

Prices are decimals internally (0.00-1.00):
- Polymarket uses decimals directly
- Kalshi converts to/from cents (1-99)
- Predict.fun uses decimals (internally wei, converted automatically)

---

## Dependencies

```
httpx           # HTTP client (async)
websockets      # WebSocket client
pandas          # Data handling
python-dotenv   # .env loading
inquirer        # Interactive prompts
py-clob-client  # Polymarket CLOB
eth-account     # Ethereum signing
cryptography    # Kalshi RSA-PSS signing
web3            # For on-chain operations (Polymarket redemption, Predict.fun)
```

---

## Supported Markets

### 15-Minute Crypto Markets

| Asset | Polymarket Slug | Kalshi Series |
|-------|-----------------|---------------|
| BTC | `btc-updown-15m` | `KXBTC15M` |
| ETH | `eth-updown-15m` | `KXETH15M` |
| SOL | `sol-updown-15m` | `KXSOL15M` |
| XRP | `xrp-updown-15m` | - |

---

## Contract Addresses (Polygon)

- **CTF Contract:** `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`
- **USDC.e (collateral):** `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
- **CTF Exchange:** `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E`

---

## Testing Code

```python
import asyncio
from pmkit.exchanges.polymarket import PolymarketExchange
from pmkit.config import load_env, require_env

async def test():
    load_env()
    exchange = PolymarketExchange(
        require_env("POLYMARKET_PRIVATE_KEY"),
        require_env("POLYMARKET_FUNDER_ADDRESS"),
    )
    await exchange.connect()
    print(await exchange.get_balance())
    print(await exchange.get_positions())
    await exchange.disconnect()

asyncio.run(test())
```

---

## Common Patterns

### WebSocket Reconnection
All WebSockets extend `BaseWebSocket` with exponential backoff reconnection (1s → 2s → 4s → max 30s).

### Market Rollover
BaseBot automatically detects 15-min boundaries and calls `_on_rollover()`.

### Mode in Filenames
Trade logs include mode: `trades_dry-run_2024-01-01.csv` vs `trades_live_2024-01-01.csv`
