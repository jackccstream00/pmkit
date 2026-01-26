Here is Claude's plan:                                                                                                         
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 pmkit - Prediction Market Bot Framework                                                                                        
                                                                                                                                
 Overview                                                                                                                       
                                                                                                                                
 A standalone framework providing building blocks for prediction market trading bots. Strategies compose these blocks - pmkit   
 doesn't impose strategy logic.                                                                                                 
                                                                                                                                
 Philosophy: Infrastructure only. No features, no ML, no risk management - those are strategy-specific.                         
                                                                                                                                
 ---                                                                                                                            
 Scope Summary                                                                                                                  
                                                                                                                                
 IN pmkit (Building Blocks)                                                                                                     
 ┌───────────────────────┬──────────────────────────────────────────────────────────────────────────────────┐                   
 │       Component       │                                   What It Does                                   │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Data - REST Fetcher   │ Binance historical data (1s/1m/5m/15m), configurable assets/periods via inquirer │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Data - WebSocket Feed │ Binance real-time 1s candles with buffer                                         │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Data - Warmup Fetch   │ Prefetch data when live strategy starts                                          │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Data - Storage        │ CSV files, pure OHLCV only                                                       │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ WebSocket Base        │ Shared reconnection logic (exponential backoff)                                  │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Exchange - Polymarket │ limit/market orders, cancel, positions, balance, trade history, redeem, WS       │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Exchange - Kalshi     │ limit/market orders, cancel, positions, balance, WS                              │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Market Finder         │ Get current + next market for both exchanges                                     │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Logging               │ Python logging, terminal + file, daily rotation                                  │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ File Paths            │ Abstract handler, /logs and /trades directories                                  │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ BaseBot               │ Lifecycle, market rollover, auto-reconnect                                       │                   
 ├───────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤                   
 │ Docs                  │ README.md + .claude/ instructions                                                │                   
 └───────────────────────┴──────────────────────────────────────────────────────────────────────────────────┘                   
 NOT in pmkit (Strategy-Specific)                                                                                               
                                                                                                                                
 - Feature engineering                                                                                                          
 - ML models / calibration                                                                                                      
 - Risk management                                                                                                              
 - Testing / backtesting                                                                                                        
                                                                                                                                
 ---                                                                                                                            
 Detailed Decisions                                                                                                             
                                                                                                                                
 1. Data Feeds                                                                                                                  
                                                                                                                                
 Binance Only (for now, extensible later)                                                                                       
                                                                                                                                
 REST Fetcher (Historical):                                                                                                     
 - Intervals: 1s, 1m, 5m, 15m                                                                                                   
 - Periods: Last 3 days, custom range, full history                                                                             
 - Assets: Multiselect from BTC, ETH, SOL, XRP, ADA, LTC, BNB (extensible)                                                      
 - Interactive config via inquirer prompts                                                                                      
 - Handle pagination automatically (max 1000 per request)                                                                       
                                                                                                                                
 REST Fetcher (Warmup):                                                                                                         
 - When live strategy starts, prefetch last N candles for model initialization                                                  
 - Same fetcher, different use case                                                                                             
                                                                                                                                
 WebSocket Feed (Live):                                                                                                         
 - Real-time 1s candles                                                                                                         
 - Buffer management (rolling deque)                                                                                            
 - Used for live trading only                                                                                                   
                                                                                                                                
 2. Data Storage                                                                                                                
                                                                                                                                
 - Format: CSV (simple, human-readable)                                                                                         
 - Content: Pure OHLCV only (timestamp, open, high, low, close, volume)                                                         
 - No labels - strategies create their own                                                                                      
 - Standard paths: Configurable via abstract file handler                                                                       
                                                                                                                                
 3. WebSocket Infrastructure                                                                                                    
                                                                                                                                
 Base class with shared logic:                                                                                                  
 class BaseWebSocket:                                                                                                           
     # Reconnection: exponential backoff (1s → 2s → 4s → max 30s)                                                               
     # No health monitoring (overkill)                                                                                          
                                                                                                                                
 All WebSocket implementations extend this base.                                                                                
                                                                                                                                
 4. Exchange Clients                                                                                                            
                                                                                                                                
 Both Polymarket and Kalshi needed.                                                                                             
                                                                                                                                
 Common interface (building blocks only):                                                                                       
 - place_limit_order() → returns order_id                                                                                       
 - place_market_order() → returns order_id                                                                                      
 - cancel_order(order_id) → returns success/fail                                                                                
 - get_order_status(order_id) → returns status, filled_amount                                                                   
 - get_positions() → all positions                                                                                              
 - get_positions_by_market_id() → filtered                                                                                      
 - get_positions_by_token_id() → filtered                                                                                       
 - get_balance() → available balance                                                                                            
 - get_trade_history() → past trades with outcome (won/lost via redeemable flag)                                                
 - subscribe_orderbook(callback) → WebSocket                                                                                    
 - subscribe_fills(callback) → WebSocket (if supported)                                                                         
                                                                                                                                
 Polymarket-specific:                                                                                                           
 - redeem(condition_id) → claim winnings from resolved markets                                                                  
                                                                                                                                
 No strategy logic in clients:                                                                                                  
 - No wait_for_fill()                                                                                                           
 - No retry logic                                                                                                               
 - No timeout handling                                                                                                          
 - Strategies compose these primitives                                                                                          
                                                                                                                                
 Terminology:                                                                                                                   
 - Use exchange-native terms: yes/no for Kalshi, UP/DOWN for Polymarket                                                         
 - Price normalization: Internal decimals (0.00-1.00), convert on API calls                                                     
   - Kalshi: multiply by 100 for cents                                                                                          
   - Polymarket: use directly                                                                                                   
                                                                                                                                
 5. Market Finder                                                                                                               
                                                                                                                                
 For both Polymarket and Kalshi:                                                                                                
 - get_smart_market(asset) → smart selection (next before boundary, current after)                                                                                    
 - get_next_market(asset) → upcoming market                                                                                     
 - list_markets(asset, status) → filtered list                                                                                  
 - get_seconds_remaining(market) → time until close                                                                             
                                                                                                                                
 15-min UP/DOWN markets only for now.                                                                                           
                                                                                                                                
 6. Logging                                                                                                                     
                                                                                                                                
 Python logging:                                                                                                                
 - Levels: DEBUG, INFO, WARNING, ERROR                                                                                          
 - Output: Terminal + .log file                                                                                                 
 - Daily rotation                                                                                                               
                                                                                                                                
 Trade CSV logging:                                                                                                             
 - Abstract file handler for consistent paths                                                                                   
 - Standard directories: /logs for logs, /trades for trades                                                                     
 - Filename includes mode: trades_live_2026-01-10.csv vs trades_dry-run_2026-01-10.csv                                          
                                                                                                                                
 7. Configuration                                                                                                               
                                                                                                                                
 Secrets: .env file only                                                                                                        
 POLYMARKET_PRIVATE_KEY=...                                                                                                     
 POLYMARKET_FUNDER_ADDRESS=...                                                                                                  
 KALSHI_API_KEY_ID=...                                                                                                          
 KALSHI_PRIVATE_KEY_PATH=...                                                                                                    
                                                                                                                                
 Strategy config: Constants at top of strategy runner file (not YAML/JSON)                                                      
 # Strategy configuration                                                                                                       
 ORDER_SIZE_USD = 5.0                                                                                                           
 ASSETS = ["BTC", "ETH"]                                                                                                        
 TRADING_WINDOW_SECONDS = 720                                                                                                   
                                                                                                                                
 8. Entry Points                                                                                                                
                                                                                                                                
 - Each strategy is its own script (no pmkit CLI wrapper)                                                                       
 - Inquirer prompts instead of CLI flags:                                                                                       
 ? Select mode: Dry Run / Live                                                                                                  
 ? Select assets: [x] BTC  [x] ETH  [ ] SOL                                                                                     
                                                                                                                                
 9. Bot Lifecycle                                                                                                               
                                                                                                                                
 BaseBot provides:                                                                                                              
 class BaseBot:                                                                                                                 
     async def start()       # initialize + run loop                                                                            
     async def stop()        # graceful shutdown (SIGINT/SIGTERM)                                                               
     async def _tick()       # override - single iteration                                                                      
     async def _on_rollover() # called when market period changes                                                               
                                                                                                                                
 Market rollover handling:                                                                                                      
 - Detect 15-min boundary transitions                                                                                           
 - Auto-reconnect WebSockets to new markets                                                                                     
 - Call _on_rollover() hook                                                                                                     
                                                                                                                                
 State:                                                                                                                         
 - Bot restart = fresh start (no persistence)                                                                                   
 - WebSocket reconnect (internet outage) = continue with existing in-memory state                                               
                                                                                                                                
 10. Async Patterns                                                                                                             
                                                                                                                                
 - Async-first (all exchange/data methods are async)                                                                            
 - Simple patterns: asyncio.gather() for parallel, async/await throughout                                                       
 - Strategies manage their own background tasks                                                                                 
                                                                                                                                
 11. Package Structure                                                                                                          
                                                                                                                                
 pmkit/                                                                                                                         
 ├── __init__.py                                                                                                                
 ├── version.py                                                                                                                 
 │                                                                                                                              
 ├── data/                                                                                                                      
 │   ├── __init__.py                                                                                                            
 │   ├── binance/                                                                                                               
 │   │   ├── __init__.py                                                                                                        
 │   │   ├── fetcher.py          # REST historical + warmup                                                                     
 │   │   ├── feed.py             # WebSocket real-time                                                                          
 │   │   └── types.py            # Candle dataclass                                                                             
 │   └── storage.py              # CSV storage                                                                                  
 │                                                                                                                              
 ├── exchanges/                                                                                                                 
 │   ├── __init__.py                                                                                                            
 │   ├── base.py                 # BaseExchange ABC                                                                             
 │   ├── polymarket/                                                                                                            
 │   │   ├── __init__.py                                                                                                        
 │   │   ├── client.py           # PolymarketExchange                                                                           
 │   │   ├── auth.py             # Magic signature                                                                              
 │   │   ├── orderbook_ws.py     # Orderbook WebSocket                                                                          
 │   │   ├── user_ws.py          # User/fills WebSocket                                                                         
 │   │   ├── market_finder.py    # Find current/next markets                                                                    
 │   │   └── types.py            # PM-specific types                                                                            
 │   └── kalshi/                                                                                                                
 │       ├── __init__.py                                                                                                        
 │       ├── client.py           # KalshiExchange                                                                               
 │       ├── auth.py             # RSA-PSS signing                                                                              
 │       ├── orderbook_ws.py     # Orderbook WebSocket                                                                          
 │       ├── market_finder.py    # Find current/next markets                                                                    
 │       └── types.py            # Kalshi-specific types                                                                        
 │                                                                                                                              
 ├── websocket/                                                                                                                 
 │   ├── __init__.py                                                                                                            
 │   └── base.py                 # BaseWebSocket with reconnection                                                              
 │                                                                                                                              
 ├── bot/                                                                                                                       
 │   ├── __init__.py                                                                                                            
 │   └── base.py                 # BaseBot lifecycle                                                                            
 │                                                                                                                              
 ├── logging/                                                                                                                   
 │   ├── __init__.py                                                                                                            
 │   ├── logger.py               # Python logging setup                                                                         
 │   ├── csv_logger.py           # Trade CSV logging                                                                            
 │   └── paths.py                # File path management                                                                         
 │                                                                                                                              
 ├── config/                                                                                                                    
 │   ├── __init__.py                                                                                                            
 │   └── env.py                  # .env loading                                                                                 
 │                                                                                                                              
 ├── prompts/                                                                                                                   
 │   ├── __init__.py                                                                                                            
 │   └── inquirer.py             # Inquirer prompt helpers                                                                      
 │                                                                                                                              
 ├── README.md                   # Comprehensive documentation                                                                  
 └── .claude/                                                                                                                   
     └── instructions.md         # Instructions for future Claudes                                                              
                                                                                                                                
 Location: pmkit/ in this repo, move to separate repo later                                                                     
 Installation: Direct import (no pip install for now)                                                                           
 Python: 3.10+                                                                                                                  
                                                                                                                                
 12. Dependencies                                                                                                               
                                                                                                                                
 httpx          # HTTP client (async)                                                                                           
 websockets     # WebSocket client                                                                                              
 pandas         # Data handling                                                                                                 
 python-dotenv  # .env loading                                                                                                  
 inquirer       # Interactive prompts                                                                                           
 py-clob-client # Polymarket CLOB (existing dependency)                                                                         
 cryptography   # Kalshi RSA-PSS signing                                                                                        
                                                                                                                                
 ---                                                                                                                            
 Implementation Order                                                                                                           
                                                                                                                                
 Phase 1: Core Infrastructure                                                                                                   
                                                                                                                                
 1. pmkit/__init__.py + version.py                                                                                              
 2. pmkit/config/env.py - .env loading                                                                                          
 3. pmkit/logging/paths.py - file path management                                                                               
 4. pmkit/logging/logger.py - Python logging setup                                                                              
 5. pmkit/logging/csv_logger.py - trade CSV logging                                                                             
 6. pmkit/websocket/base.py - BaseWebSocket with reconnection                                                                   
                                                                                                                                
 Phase 2: Data Layer                                                                                                            
                                                                                                                                
 7. pmkit/data/binance/types.py - Candle dataclass                                                                              
 8. pmkit/data/binance/fetcher.py - REST historical + warmup                                                                    
 9. pmkit/data/binance/feed.py - WebSocket real-time                                                                            
 10. pmkit/data/storage.py - CSV storage                                                                                        
                                                                                                                                
 Phase 3: Exchange Layer - Polymarket                                                                                           
                                                                                                                                
 11. pmkit/exchanges/base.py - BaseExchange ABC                                                                                 
 12. pmkit/exchanges/polymarket/types.py - PM types                                                                             
 13. pmkit/exchanges/polymarket/auth.py - Magic signature                                                                       
 14. pmkit/exchanges/polymarket/client.py - Main client                                                                         
 15. pmkit/exchanges/polymarket/orderbook_ws.py - Orderbook WS                                                                  
 16. pmkit/exchanges/polymarket/user_ws.py - User/fills WS                                                                      
 17. pmkit/exchanges/polymarket/market_finder.py - Market discovery                                                             
                                                                                                                                
 Phase 4: Exchange Layer - Kalshi                                                                                               
                                                                                                                                
 18. pmkit/exchanges/kalshi/types.py - Kalshi types                                                                             
 19. pmkit/exchanges/kalshi/auth.py - RSA-PSS signing                                                                           
 20. pmkit/exchanges/kalshi/client.py - Main client                                                                             
 21. pmkit/exchanges/kalshi/orderbook_ws.py - Orderbook WS                                                                      
 22. pmkit/exchanges/kalshi/market_finder.py - Market discovery                                                                 
                                                                                                                                
 Phase 5: Bot & Prompts                                                                                                         
                                                                                                                                
 23. pmkit/bot/base.py - BaseBot lifecycle                                                                                      
 24. pmkit/prompts/inquirer.py - Prompt helpers                                                                                 
                                                                                                                                
 Phase 6: Documentation                                                                                                         
                                                                                                                                
 25. pmkit/README.md - Comprehensive documentation                                                                              
 26. pmkit/.claude/instructions.md - Claude instructions                                                                        
                                                                                                                                
 ---                                                                                                                            
 Files to Reference (Existing Code)                                                                                             
 ┌──────────────────────────┬──────────────────────────────────────────┐                                                        
 │        Component         │              Reference File              │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Polymarket client        │ trading/polymarket_client.py             │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Polymarket orderbook WS  │ example_strategy/clients/orderbook_ws.py │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Polymarket user WS       │ example_strategy/clients/user_ws.py      │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Polymarket market finder │ trading/market_finder.py                 │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Kalshi client            │ v2/utils/kalshi/client.py                │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Kalshi market finder     │ v2/utils/kalshi/market_finder.py         │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Kalshi WebSocket         │ v2/utils/kalshi/websocket.py             │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Binance feed             │ arb_trading/binance_1s_feed.py           │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ Binance fetcher          │ btc_1s_predictor_v2/data/fetcher.py      │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ CSV logger               │ btc_1s_predictor_v2/live/csv_logger.py   │                                                        
 ├──────────────────────────┼──────────────────────────────────────────┤                                                        
 │ BaseBot pattern          │ fair_value_v2/live/trader.py             │                                                        
 └──────────────────────────┴──────────────────────────────────────────┘                                                        
 ---                                                                                                                            
 Key Design Principles                                                                                                          
                                                                                                                                
 1. Building blocks, not strategy logic - pmkit provides primitives, strategies compose them                                    
 2. Exchange-native terms - no normalization of YES/NO vs UP/DOWN                                                               
 3. Price normalization - internal decimals, convert on API calls                                                               
 4. Async-first - all I/O operations are async                                                                                  
 5. Inquirer for interaction - no CLI flags                                                                                     
 6. Secrets in .env only - never in code or config files                                                                        
 7. Strategy config in code - constants at top of runner file                                                                   
 8. Dry-run vs live in filenames - always differentiate logs                                                                    
 9. WebSocket auto-reconnect - exponential backoff, continue on reconnect                                                       
 10. Market rollover handling - auto-detect, auto-reconnect                                                                     
                                                                                                                                
 ---                                                                                                                            
 Verification                                                                                                                   
                                                                                                                                
 After implementation:                                                                                                          
 1. Import pmkit from a test script                                                                                             
 2. Initialize Binance feed, verify data flows                                                                                  
 3. Initialize Polymarket client, verify connection                                                                             
 4. Initialize Kalshi client, verify connection                                                                                 
 5. Run a minimal BaseBot subclass in dry-run mode                                                                              
 6. Verify logs appear in /logs, trades in /trades                                                                              
 7. Verify inquirer prompts work                                                                                                
                                                                                                                                
 ---                                                                                                                            
 Implementation Gaps (TO BE FIXED)                                                                                              
                                                                                                                                
 Polymarket Client - Missing Features                                                                                           
 ┌─────────────────────────────┬────────────────┬─────────────┬──────────────────────────────────────────────┐                  
 │           Feature           │ Plan Reference │   Status    │                    Notes                     │                  
 ├─────────────────────────────┼────────────────┼─────────────┼──────────────────────────────────────────────┤                  
 │ redeem(condition_id)        │ Line 97        │ ❌ NOT DONE │ Requires web3.py + CTF contract interaction  │                  
 ├─────────────────────────────┼────────────────┼─────────────┼──────────────────────────────────────────────┤                  
 │ get_positions_by_token_id() │ Line 90        │ ❌ NOT DONE │ Simple filter on get_positions()             │                  
 ├─────────────────────────────┼────────────────┼─────────────┼──────────────────────────────────────────────┤                  
 │ get_trade_history()         │ Line 92        │ ⚠️ STUB     │ Returns empty, needs Data API implementation │                  
 └─────────────────────────────┴────────────────┴─────────────┴──────────────────────────────────────────────┘                  
 Market Finder - Missing Features                                                                                               
 ┌─────────────────────────────┬────────────────┬─────────────┬──────────────────────────────┐                                  
 │           Feature           │ Plan Reference │   Status    │            Notes             │                                  
 ├─────────────────────────────┼────────────────┼─────────────┼──────────────────────────────┤                                  
 │ list_markets(asset, status) │ Line 116       │ ❌ NOT DONE │ Gamma API query with filters │                                  
 └─────────────────────────────┴────────────────┴─────────────┴──────────────────────────────┘                                  
 Redeem Implementation Details                                                                                                  
                                                                                                                                
 Per Polymarket CTF docs (https://docs.polymarket.com/developers/CTF/redeem):                                                   
                                                                                                                                
 Contract: Conditional Token Framework (CTF) on Polygon                                                                         
 Method: redeemPositions(collateralToken, parentCollectionId, conditionId, indexSets)                                           
                                                                                                                                
 Parameters:                                                                                                                    
 - collateralToken: USDC contract address on Polygon                                                                            
 - parentCollectionId: bytes32 (null/zero for Polymarket)                                                                       
 - conditionId: Market condition ID (from PolymarketMarket.condition_id)                                                        
 - indexSets: uint[] - Binary-encoded outcome partitions (e.g., [1, 2] for binary markets)                                      
                                                                                                                                
 Implementation needs:                                                                                                          
 1. web3.py dependency                                                                                                          
 2. CTF contract ABI                                                                                                            
 3. Private key signing for transaction                                                                                         
 4. Gas estimation and submission                                                                                               
                                                                                                                                
 File to modify: pmkit/exchanges/polymarket/client.py                                                                           
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
                                                                                                                                
 Would you like to proceed?                                                                                                     
                                                                                                                                
 ❯ 1. Yes, and auto-accept edits (shift+tab)                                                                                    
   2. Yes, and manually approve edits                                                                                           
   3. Type here to tell Claude what to change                                                                                   
                                                                                                                                
 ctrl-g to edit in VS Code · ~/.claude/plans/buzzing-discovering-thompson.md                                                    
