"""File path management for logs and trades.

Standard directories:
- /logs for log files
- /trades for trade CSVs

Filenames include mode: trades_live_2026-01-10.csv vs trades_dry-run_2026-01-10.csv
"""

from datetime import datetime
from pathlib import Path
from typing import Optional


class PathManager:
    """
    Manages file paths for logs and trades with consistent structure.

    Standard structure:
        base_dir/
        ├── logs/
        │   ├── strategy_live_2026-01-10.log
        │   └── strategy_dry-run_2026-01-10.log
        └── trades/
            ├── trades_live_2026-01-10.csv
            └── trades_dry-run_2026-01-10.csv
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        strategy_name: str = "strategy",
        dry_run: bool = True,
    ):
        """
        Initialize path manager.

        Args:
            base_dir: Base directory for logs/trades. Defaults to current working directory.
            strategy_name: Name of the strategy (used in filenames).
            dry_run: Whether running in dry-run mode (affects filenames).
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.strategy_name = strategy_name
        self.dry_run = dry_run

        # Create directories
        self.logs_dir = self.base_dir / "logs"
        self.trades_dir = self.base_dir / "trades"

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.trades_dir.mkdir(parents=True, exist_ok=True)

    @property
    def mode_suffix(self) -> str:
        """Get mode suffix for filenames."""
        return "dry-run" if self.dry_run else "live"

    def _get_date_str(self) -> str:
        """Get current date string for filenames."""
        return datetime.now().strftime("%Y-%m-%d")

    def get_log_path(self, name: Optional[str] = None) -> Path:
        """
        Get path for a log file.

        Args:
            name: Optional custom name. Defaults to strategy_name.

        Returns:
            Path like: logs/strategy_live_2026-01-10.log
        """
        name = name or self.strategy_name
        filename = f"{name}_{self.mode_suffix}_{self._get_date_str()}.log"
        return self.logs_dir / filename

    def get_trades_path(self, name: Optional[str] = None) -> Path:
        """
        Get path for a trades CSV file.

        Args:
            name: Optional custom name. Defaults to "trades".

        Returns:
            Path like: trades/trades_live_2026-01-10.csv
        """
        name = name or "trades"
        filename = f"{name}_{self.mode_suffix}_{self._get_date_str()}.csv"
        return self.trades_dir / filename

    def get_custom_path(
        self,
        directory: str,
        name: str,
        extension: str = "csv",
        include_mode: bool = True,
        include_date: bool = True,
    ) -> Path:
        """
        Get a custom file path with consistent naming.

        Args:
            directory: Subdirectory name (e.g., "orderbooks")
            name: Base filename
            extension: File extension
            include_mode: Include dry-run/live in filename
            include_date: Include date in filename

        Returns:
            Path with consistent naming structure.
        """
        target_dir = self.base_dir / directory
        target_dir.mkdir(parents=True, exist_ok=True)

        parts = [name]
        if include_mode:
            parts.append(self.mode_suffix)
        if include_date:
            parts.append(self._get_date_str())

        filename = "_".join(parts) + f".{extension}"
        return target_dir / filename
