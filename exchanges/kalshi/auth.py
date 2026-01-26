"""Kalshi authentication utilities.

RSA-PSS signing for API requests.
"""

import base64
import time
from pathlib import Path
from typing import Dict, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key


def load_private_key(key_path: Union[str, Path]):
    """
    Load RSA private key from PEM file.

    Args:
        key_path: Path to PEM file

    Returns:
        Private key object
    """
    with open(key_path, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def sign_pss_text(private_key, text: str) -> str:
    """
    Sign text using RSA-PSS and return base64 encoded signature.

    Args:
        private_key: RSA private key
        text: Text to sign

    Returns:
        Base64 encoded signature
    """
    message = text.encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def get_auth_headers(
    api_key_id: str,
    private_key,
    method: str,
    path: str,
) -> Dict[str, str]:
    """
    Generate authentication headers for a REST API request.

    Args:
        api_key_id: Kalshi API key ID
        private_key: RSA private key
        method: HTTP method (GET, POST, DELETE)
        path: API path (without /trade-api/v2 prefix)

    Returns:
        Dict of authentication headers
    """
    timestamp_ms = int(time.time() * 1000)
    timestamp_str = str(timestamp_ms)

    # Message to sign: timestamp + method + full path
    path_without_query = path.split("?")[0]
    full_path = "/trade-api/v2" + path_without_query
    msg_string = timestamp_str + method + full_path
    signature = sign_pss_text(private_key, msg_string)

    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
    }


def get_ws_auth_headers(api_key_id: str, private_key) -> Dict[str, str]:
    """
    Generate authentication headers for WebSocket connection.

    Args:
        api_key_id: Kalshi API key ID
        private_key: RSA private key

    Returns:
        Dict of authentication headers
    """
    timestamp_ms = int(time.time() * 1000)
    timestamp_str = str(timestamp_ms)

    path = "/trade-api/ws/v2"
    msg_string = timestamp_str + "GET" + path
    signature = sign_pss_text(private_key, msg_string)

    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
    }
