# File Organization Rules

## Where Files Belong

| Type                           | Location                |
| ------------------------------ | ----------------------- |
| Temporary/adhoc/one-time files | `temporary/` folder     |
| Strategy-related logic         | `strategies/` folder    |
| Infrastructure code            | pmkit (with permission) |

## Creating New Files

When creating temporary, adhoc, or one-time files:

1. Default suggestion is the `temporary/` folder
2. Always ask user permission for location
3. Only put files elsewhere if it makes sense for the use case

## Strategy Logic

Strategy-related logic **always** goes under `strategies/`.

This includes:

- Trading strategies
- Feature engineering
- ML models
- Risk management
- Backtesting code
