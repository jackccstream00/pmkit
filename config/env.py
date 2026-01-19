"""Environment variable loading and access.

Secrets should be stored in .env files only.
Strategy config should be constants at top of strategy runner file.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env(env_path: Optional[Path] = None) -> bool:
    """
    Load environment variables from .env file.

    Args:
        env_path: Path to .env file. If None, searches current directory
                  and parent directories.

    Returns:
        True if .env file was found and loaded, False otherwise.
    """
    if env_path:
        return load_dotenv(env_path)
    return load_dotenv()


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get an environment variable value.

    Args:
        key: Environment variable name
        default: Default value if not found

    Returns:
        The environment variable value or default.
    """
    return os.getenv(key, default)


def require_env(key: str) -> str:
    """
    Get a required environment variable.

    Args:
        key: Environment variable name

    Returns:
        The environment variable value.

    Raises:
        RuntimeError: If the environment variable is not set.
    """
    value = os.getenv(key)
    if value is None:
        raise RuntimeError(f"Required environment variable not set: {key}")
    return value


# Common environment variable keys
class EnvKeys:
    """Standard environment variable names for pmkit."""

    # Polymarket
    POLYMARKET_PRIVATE_KEY = "POLYMARKET_PRIVATE_KEY"
    POLYMARKET_FUNDER_ADDRESS = "POLYMARKET_FUNDER_ADDRESS"

    # Kalshi
    KALSHI_API_KEY_ID = "KALSHI_API_KEY_ID"
    KALSHI_PRIVATE_KEY_PATH = "KALSHI_PRIVATE_KEY_PATH"
