# Coding Patterns for pmkit

## Async-First

All I/O operations must be async:
- Every exchange/data call uses `await`
- Never block the event loop - no `time.sleep()`, use `asyncio.sleep()`
- Use `asyncio.gather()` for parallel operations

## Configuration

- **Secrets in .env only** - Use `require_env()` for credentials, never hardcode
- **Strategy config as constants** - Put `ORDER_SIZE`, `ASSETS`, etc. at top of runner file (not YAML/JSON)
- **Inquirer for interaction** - Use `select_mode()`, `select_assets()` instead of CLI flags

## Exchange-Native Terms

Use exchange-native terminology, don't normalize:
- Polymarket: `Up`, `Down`
- Kalshi: `yes`, `no`
- Predict.fun: `Up`, `Down`

## Price Handling

Prices are decimals internally (0.00-1.00):
- Polymarket uses decimals directly
- Kalshi converts to/from cents (1-99)
- Predict.fun uses decimals (internally wei, converted automatically)

## Bot Structure

- **Extend BaseBot** - Use `_setup()`, `_tick()`, `_on_rollover()`, `_cleanup()` hooks
- **Handle rollover** - Refresh markets in `_on_rollover()`, don't assume tokens persist across 15-min boundaries
- **Dry-run first** - Always test with `dry_run=True` before going live

## Trading Patterns

- Check balance before trading: `await exchange.get_balance()`
- Check positions before new orders to avoid doubling up
- Use market finders: `await finder.get_smart_market("btc")` for fresh tokens each period

## Logging

- Use `TradeLogger` - Logs include mode in filename automatically (`trades_dry-run_*.csv`)
- Use `PathManager` - Consistent `/logs` and `/trades` directories

## When Extending pmkit

1. Don't add strategy logic - that belongs in strategy code
2. Keep it async - all I/O must be async
3. Use exchange-native terms - don't normalize terminology
4. Follow existing patterns - check similar code first
5. No over-engineering - simple and focused
