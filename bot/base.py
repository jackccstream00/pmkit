"""Base bot with lifecycle management.

Provides start/stop/tick pattern for trading bots.
Handles graceful shutdown via signals.
"""

import asyncio
import logging
import signal
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class BaseBot(ABC):
    """
    Base class for trading bots.

    Provides lifecycle management:
    - start(): Initialize resources and run main loop
    - stop(): Graceful shutdown
    - _tick(): Override for main loop logic
    - _on_rollover(): Override for 15-min boundary transitions

    Usage:
        class MyBot(BaseBot):
            async def _setup(self):
                # Initialize exchanges, feeds, etc.
                pass

            async def _tick(self):
                # Main logic called each iteration
                pass

            async def _on_rollover(self):
                # Called on 15-min boundary transitions
                pass

            async def _cleanup(self):
                # Cleanup on shutdown
                pass

        bot = MyBot(dry_run=True)
        await bot.run()
    """

    def __init__(
        self,
        dry_run: bool = True,
        tick_interval: float = 1.0,
        rollover_interval: int = 900,  # 15 minutes
    ):
        """
        Initialize bot.

        Args:
            dry_run: If True, don't execute real trades
            tick_interval: Seconds between tick() calls
            rollover_interval: Seconds between market rollovers (default 15 min)
        """
        self.dry_run = dry_run
        self.tick_interval = tick_interval
        self.rollover_interval = rollover_interval

        self._running = False
        self._last_boundary: Optional[int] = None
        self._tasks: list = []

    @property
    def mode(self) -> str:
        """Get current mode string."""
        return "dry-run" if self.dry_run else "live"

    def _get_current_boundary(self) -> int:
        """Get current interval boundary timestamp."""
        now = int(datetime.now(timezone.utc).timestamp())
        return (now // self.rollover_interval) * self.rollover_interval

    def _get_seconds_into_interval(self) -> int:
        """Get seconds since interval started."""
        now = int(datetime.now(timezone.utc).timestamp())
        boundary = self._get_current_boundary()
        return now - boundary

    def _get_seconds_until_next_interval(self) -> int:
        """Get seconds until next interval."""
        return self.rollover_interval - self._get_seconds_into_interval()

    # === Lifecycle Hooks ===

    async def _setup(self) -> None:
        """
        Initialize bot resources.

        Override to set up exchanges, data feeds, models, etc.
        Called once at the start of run().
        """
        pass

    @abstractmethod
    async def _tick(self) -> None:
        """
        Main loop logic.

        Override to implement trading logic.
        Called every tick_interval seconds.
        """
        pass

    async def _on_rollover(self) -> None:
        """
        Handle interval boundary transition.

        Override to handle market rollovers, reconnect WebSockets, etc.
        Called automatically when a new interval starts.
        """
        pass

    async def _cleanup(self) -> None:
        """
        Cleanup bot resources.

        Override to close connections, cancel tasks, etc.
        Called once during stop().
        """
        pass

    # === Main Lifecycle ===

    async def run(self) -> None:
        """
        Run the bot.

        Sets up signal handlers, initializes resources,
        runs main loop until stopped.
        """
        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        try:
            await self.start()
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        logger.info("Shutdown signal received")
        asyncio.create_task(self.stop())

    async def start(self) -> None:
        """
        Start the bot.

        Initializes resources and runs main loop.
        """
        mode = "DRY-RUN" if self.dry_run else "LIVE"
        logger.info("=" * 60)
        logger.info(f"Starting {self.__class__.__name__} ({mode})")
        logger.info("=" * 60)

        # Setup
        await self._setup()

        # Initialize boundary tracking
        self._last_boundary = self._get_current_boundary()
        self._running = True

        logger.info("Bot started. Press Ctrl+C to stop.")

        # Main loop
        while self._running:
            try:
                # Check for rollover
                current_boundary = self._get_current_boundary()
                if current_boundary != self._last_boundary:
                    self._last_boundary = current_boundary
                    logger.info(f"Interval rollover detected")
                    await self._on_rollover()

                # Run tick
                await self._tick()

                # Wait for next tick
                await asyncio.sleep(self.tick_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(1)  # Prevent tight error loop

    async def stop(self) -> None:
        """
        Stop the bot gracefully.

        Cancels tasks and runs cleanup.
        """
        if not self._running:
            return

        logger.info("Stopping bot...")
        self._running = False

        # Cancel any background tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        # Run cleanup
        await self._cleanup()

        logger.info("=" * 60)
        logger.info("Bot stopped")
        logger.info("=" * 60)

    def add_task(self, coro) -> asyncio.Task:
        """
        Add a background task that will be cancelled on stop.

        Args:
            coro: Coroutine to run

        Returns:
            Task handle
        """
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task
