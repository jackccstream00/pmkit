"""Predict.fun authentication helpers.

JWT-based authentication for the Predict.fun REST API.
"""

import logging
from typing import Optional

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount

from pmkit.exchanges.predictfun.types import API_BASE, API_BASE_TESTNET

logger = logging.getLogger(__name__)


async def get_jwt(
    signer: LocalAccount,
    api_base: str = API_BASE,
    api_key: Optional[str] = None,
    timeout: float = 10.0,
) -> str:
    """
    Get JWT token for authenticated API requests.

    Auth flow:
    1. GET /v1/auth/message -> get message to sign
    2. Sign with EIP-191 personal_sign
    3. POST /v1/auth -> exchange signature for JWT

    Args:
        signer: LocalAccount with private key for signing
        api_base: API base URL (mainnet or testnet)
        api_key: Optional API key (required for mainnet)
        timeout: HTTP request timeout

    Returns:
        JWT token string

    Raises:
        httpx.HTTPStatusError: If API request fails
        ValueError: If response is missing expected fields
    """
    headers = {}
    if api_key:
        headers["X-Api-Key"] = api_key

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Step 1: Get message to sign
        response = await client.get(
            f"{api_base}/v1/auth/message",
            params={"address": signer.address},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        message = data.get("message")
        if not message:
            raise ValueError("No message in auth response")

        logger.debug(f"Got auth message to sign: {message[:50]}...")

        # Step 2: Sign with EIP-191 personal_sign
        signable = encode_defunct(text=message)
        signed = signer.sign_message(signable)
        signature = signed.signature.hex()

        # Ensure 0x prefix
        if not signature.startswith("0x"):
            signature = "0x" + signature

        # Step 3: Exchange signature for JWT
        response = await client.post(
            f"{api_base}/v1/auth",
            json={
                "address": signer.address,
                "signature": signature,
            },
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        jwt = data.get("token") or data.get("jwt") or data.get("accessToken")
        if not jwt:
            raise ValueError(f"No JWT in auth response: {data.keys()}")

        logger.info(f"Got JWT token for {signer.address}")
        return jwt


async def refresh_jwt(
    current_jwt: str,
    api_base: str = API_BASE,
    api_key: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[str]:
    """
    Refresh an existing JWT token.

    Args:
        current_jwt: Current JWT token
        api_base: API base URL
        api_key: Optional API key
        timeout: HTTP request timeout

    Returns:
        New JWT token, or None if refresh fails
    """
    headers = {"Authorization": f"Bearer {current_jwt}"}
    if api_key:
        headers["X-Api-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{api_base}/v1/auth/refresh",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            jwt = data.get("token") or data.get("jwt") or data.get("accessToken")
            if jwt:
                logger.info("JWT refreshed successfully")
                return jwt

    except Exception as e:
        logger.warning(f"JWT refresh failed: {e}")

    return None
