"""Binance REST API data fetcher.

Features:
- Historical data fetching with pagination
- Warmup data fetching for live strategies
- Interactive configuration via inquirer
- Rate limiting

Intervals: 1s, 1m, 5m, 15m
Assets: BTC, ETH, SOL, XRP, ADA, LTC, BNB (extensible)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import httpx
import pandas as pd

from pmkit.data.binance.types import Candle, Interval, get_symbol

logger = logging.getLogger(__name__)

BINANCE_API = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000  # Binance max per request
RATE_LIMIT_DELAY = 0.1  # seconds between requests


class BinanceFetcher:
    """
    Fetcher for historical Binance OHLCV data.

    Usage:
        fetcher = BinanceFetcher()

        # Fetch historical data
        df = await fetcher.fetch(
            symbol="BTCUSDT",
            interval=Interval.SECOND_1,
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 2),
        )

        # Warmup fetch for live trading
        candles = await fetcher.fetch_warmup(
            symbol="BTCUSDT",
            interval=Interval.SECOND_1,
            count=1000,
        )
    """

    def __init__(self, timeout: float = 30.0):
        """
        Initialize fetcher.

        Args:
            timeout: HTTP request timeout in seconds.
        """
        self.timeout = timeout

    async def fetch(
        self,
        symbol: str,
        interval: Interval,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.

        Args:
            symbol: Binance symbol (e.g., "BTCUSDT") or asset (e.g., "BTC")
            interval: Candle interval
            start: Start datetime (UTC)
            end: End datetime (UTC). Defaults to now.

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        symbol = get_symbol(symbol)
        end = end or datetime.now(timezone.utc)

        # Ensure timezone-aware
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        logger.info(f"Fetching {symbol} {interval.value} from {start} to {end}...")

        all_klines = await self._fetch_klines(symbol, interval.value, start_ms, end_ms)

        if not all_klines:
            logger.warning(f"No data returned for {symbol}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = self._klines_to_dataframe(all_klines)
        logger.info(f"Fetched {len(df)} candles for {symbol}")

        return df

    async def fetch_warmup(
        self,
        symbol: str,
        interval: Interval,
        count: int = 1000,
    ) -> List[Candle]:
        """
        Fetch recent candles for model warmup.

        Args:
            symbol: Binance symbol or asset
            interval: Candle interval
            count: Number of candles to fetch

        Returns:
            List of Candle objects (oldest first)
        """
        symbol = get_symbol(symbol)

        logger.info(f"Fetching {count} warmup candles for {symbol} {interval.value}...")

        all_klines = []
        remaining = count
        end_time = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while remaining > 0:
                batch_size = min(remaining, MAX_LIMIT)

                params = {
                    "symbol": symbol,
                    "interval": interval.value,
                    "limit": batch_size,
                }

                if end_time:
                    params["endTime"] = end_time

                response = await client.get(BINANCE_API, params=params)

                if response.status_code != 200:
                    raise RuntimeError(f"Binance API error: {response.status_code} - {response.text}")

                data = response.json()

                if not data:
                    break

                all_klines.extend(data)

                # Set end_time for next batch (1ms before oldest candle)
                end_time = data[0][0] - 1
                remaining -= len(data)

                logger.debug(f"Fetched {len(data)} candles, {remaining} remaining")
                await asyncio.sleep(RATE_LIMIT_DELAY)

        # Sort oldest first and convert to Candle objects
        all_klines.sort(key=lambda x: x[0])

        candles = [
            Candle.from_binance_kline(k, symbol=symbol, interval=interval.value)
            for k in all_klines
        ]

        # Deduplicate by timestamp
        seen = set()
        unique_candles = []
        for c in candles:
            key = c.timestamp.isoformat()
            if key not in seen:
                seen.add(key)
                unique_candles.append(c)

        logger.info(f"Fetched {len(unique_candles)} unique warmup candles for {symbol}")
        return unique_candles

    async def _fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> list:
        """Fetch all klines with pagination."""
        all_klines = []
        current_start = start_ms

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while current_start < end_ms:
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": current_start,
                    "endTime": end_ms,
                    "limit": MAX_LIMIT,
                }

                response = await client.get(BINANCE_API, params=params)

                if response.status_code != 200:
                    raise RuntimeError(f"Binance API error: {response.status_code} - {response.text}")

                data = response.json()

                if not data:
                    break

                all_klines.extend(data)
                current_start = data[-1][0] + 1  # Next ms after last candle

                logger.debug(f"Fetched {len(data)} klines, total: {len(all_klines)}")
                await asyncio.sleep(RATE_LIMIT_DELAY)

        return all_klines

    def _klines_to_dataframe(self, klines: list) -> pd.DataFrame:
        """Convert Binance klines to DataFrame."""
        df = pd.DataFrame(klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])

        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        return df[["timestamp", "open", "high", "low", "close", "volume"]]


async def interactive_fetch():
    """
    Interactive data fetching with inquirer prompts.

    Usage:
        python -m pmkit.data.binance.fetcher
    """
    import inquirer

    # Assets selection
    questions = [
        inquirer.Checkbox(
            "assets",
            message="Select assets to fetch",
            choices=["BTC", "ETH", "SOL", "XRP", "ADA", "LTC", "BNB"],
            default=["BTC"],
        ),
        inquirer.List(
            "interval",
            message="Select interval",
            choices=["1s", "1m", "5m", "15m"],
            default="1s",
        ),
        inquirer.List(
            "period",
            message="Select time period",
            choices=[
                ("Last 3 days", "3d"),
                ("Last week", "7d"),
                ("Last month", "30d"),
                ("Custom range", "custom"),
            ],
        ),
        inquirer.Path(
            "output_dir",
            message="Output directory",
            default="./data/raw",
            path_type=inquirer.Path.DIRECTORY,
        ),
    ]

    answers = inquirer.prompt(questions)

    if not answers:
        return

    # Handle custom date range
    if answers["period"] == "custom":
        date_questions = [
            inquirer.Text(
                "start_date",
                message="Start date (YYYY-MM-DD)",
            ),
            inquirer.Text(
                "end_date",
                message="End date (YYYY-MM-DD)",
            ),
        ]
        date_answers = inquirer.prompt(date_questions)
        if not date_answers:
            return

        start = datetime.strptime(date_answers["start_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(date_answers["end_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        days = int(answers["period"].rstrip("d"))
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

    # Fetch data
    fetcher = BinanceFetcher()
    interval = Interval(answers["interval"])
    output_dir = Path(answers["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    for asset in answers["assets"]:
        symbol = get_symbol(asset)
        logger.info(f"Fetching {symbol}...")

        df = await fetcher.fetch(symbol, interval, start, end)

        if not df.empty:
            filename = f"{asset}_{interval.value}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
            filepath = output_dir / filename
            df.to_csv(filepath, index=False)
            logger.info(f"Saved {len(df)} candles to {filepath}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    asyncio.run(interactive_fetch())
