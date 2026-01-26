"""Interactive prompts using inquirer.

Provides simple prompts for common bot configuration:
- Mode selection (dry-run vs live)
- Asset selection
- Confirmation dialogs
"""

from typing import Any, List, Optional

try:
    import inquirer
    HAS_INQUIRER = True
except ImportError:
    HAS_INQUIRER = False


# Default assets for selection
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "XRP", "ADA", "LTC", "BNB"]


def _check_inquirer() -> None:
    """Check if inquirer is available."""
    if not HAS_INQUIRER:
        raise ImportError(
            "inquirer not installed. Install with: pip install inquirer"
        )


def select(
    message: str,
    choices: List[str],
    default: Optional[str] = None,
) -> str:
    """
    Single-select from a list of choices.

    Args:
        message: Prompt message
        choices: List of options
        default: Default selection

    Returns:
        Selected choice
    """
    _check_inquirer()

    questions = [
        inquirer.List(
            "selection",
            message=message,
            choices=choices,
            default=default,
        )
    ]

    answers = inquirer.prompt(questions)

    if not answers:
        raise KeyboardInterrupt("User cancelled prompt")

    return answers["selection"]


def select_mode(default: str = "Dry Run") -> bool:
    """
    Select trading mode.

    Returns:
        True for dry-run, False for live
    """
    _check_inquirer()

    choices = ["Dry Run", "Live"]

    questions = [
        inquirer.List(
            "mode",
            message="Select trading mode",
            choices=choices,
            default=default,
        )
    ]

    answers = inquirer.prompt(questions)

    if not answers:
        raise KeyboardInterrupt("User cancelled prompt")

    return answers["mode"] == "Dry Run"


def select_assets(
    available: Optional[List[str]] = None,
    default: Optional[List[str]] = None,
) -> List[str]:
    """
    Multi-select assets to trade.

    Args:
        available: List of available assets (default: DEFAULT_ASSETS)
        default: Pre-selected assets

    Returns:
        List of selected assets
    """
    _check_inquirer()

    available = available or DEFAULT_ASSETS
    default = default or ["BTC"]

    questions = [
        inquirer.Checkbox(
            "assets",
            message="Select assets to trade",
            choices=available,
            default=default,
        )
    ]

    answers = inquirer.prompt(questions)

    if not answers:
        raise KeyboardInterrupt("User cancelled prompt")

    selected = answers["assets"]

    if not selected:
        print("No assets selected. Please select at least one.")
        return select_assets(available, default)

    return selected


def confirm(
    message: str,
    default: bool = True,
) -> bool:
    """
    Yes/no confirmation prompt.

    Args:
        message: Prompt message
        default: Default answer

    Returns:
        True for yes, False for no
    """
    _check_inquirer()

    questions = [
        inquirer.Confirm(
            "confirm",
            message=message,
            default=default,
        )
    ]

    answers = inquirer.prompt(questions)

    if answers is None:
        raise KeyboardInterrupt("User cancelled prompt")

    return answers["confirm"]


def prompt_text(
    message: str,
    default: str = "",
    validate: Optional[Any] = None,
) -> str:
    """
    Text input prompt.

    Args:
        message: Prompt message
        default: Default value
        validate: Optional validation function

    Returns:
        User input string
    """
    _check_inquirer()

    kwargs = {
        "message": message,
        "default": default,
    }

    if validate:
        kwargs["validate"] = validate

    questions = [inquirer.Text("input", **kwargs)]

    answers = inquirer.prompt(questions)

    if not answers:
        raise KeyboardInterrupt("User cancelled prompt")

    return answers["input"]


def prompt_number(
    message: str,
    default: float = 0.0,
) -> float:
    """
    Numeric input prompt.

    Args:
        message: Prompt message
        default: Default value

    Returns:
        User input as float
    """
    def validate_number(_, answer):
        try:
            float(answer)
            return True
        except ValueError:
            raise inquirer.errors.ValidationError(
                "", reason="Please enter a valid number"
            )

    text = prompt_text(message, str(default), validate_number)
    return float(text)
