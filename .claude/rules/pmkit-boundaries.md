# pmkit Boundaries

## What pmkit Provides (Infrastructure Only)

| Category | Features |
|----------|----------|
| **Exchanges** | Polymarket, Kalshi, Lighter, Predict.fun clients |
| **Data** | Binance REST fetcher, WebSocket feed, CSV storage |
| **Bot** | BaseBot lifecycle hooks, rollover detection, shutdown handling |
| **Logging** | Python logging, Trade CSV logging, PathManager |
| **Config** | .env loading, get_env(), require_env() |
| **Prompts** | Inquirer-based interactive prompts |
| **WebSocket** | Base class with exponential backoff reconnection |

## What Does NOT Belong in pmkit

These belong in **strategy code**, not pmkit:

- Feature engineering
- ML models or predictions
- ML calibration
- Risk management logic
- Backtesting infrastructure
- Strategy-specific logic
- `wait_for_fill()` or retry logic
- Timeout handling

## Philosophy

pmkit is a **building-block framework** for prediction market trading bots. It provides infrastructure primitives that strategies compose.

**It does NOT contain strategy logic.**

## Before Writing Code

Check if pmkit already has what you need:
- Exchange client? `pmkit.exchanges.polymarket`, `pmkit.exchanges.kalshi`, `pmkit.exchanges.lighter`, or `pmkit.exchanges.predictfun`
- Binance data? `pmkit.data.binance`
- Bot lifecycle? `pmkit.bot.BaseBot`
- Logging? `pmkit.log`
- Config loading? `pmkit.config`
