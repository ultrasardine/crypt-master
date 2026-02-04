"""
Pionex API Authentication Module.

This module provides HMAC-SHA256 signature generation for authenticating
requests to the Pionex exchange API.

The Pionex API requires:
- PIONEX-KEY header: The API key
- PIONEX-SIGNATURE header: HMAC-SHA256 signature of the query string
- timestamp query parameter: Current time in milliseconds since epoch

The signature is computed over the complete query string (including timestamp)
using HMAC-SHA256 with the API secret as the key.

Requirements:
- 1.1: Authenticate using PIONEX-KEY header, PIONEX-SIGNATURE header, and timestamp
- 1.8: Compute HMAC-SHA256 signature using the API secret key
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class AuthHeaders:
    """
    Authentication headers required for Pionex API requests.

    Attributes:
        pionex_key: The API key to be sent in PIONEX-KEY header
        pionex_signature: The HMAC-SHA256 signature for PIONEX-SIGNATURE header
        timestamp: The timestamp in milliseconds used for the request
    """

    pionex_key: str
    pionex_signature: str
    timestamp: int

    def to_headers(self) -> dict[str, str]:
        """
        Convert to a dictionary suitable for HTTP headers.

        Returns:
            Dictionary with PIONEX-KEY and PIONEX-SIGNATURE headers
        """
        return {
            "PIONEX-KEY": self.pionex_key,
            "PIONEX-SIGNATURE": self.pionex_signature,
        }


class PionexAuthenticator:
    """
    Handles authentication for Pionex API requests.

    This class generates timestamps, computes HMAC-SHA256 signatures,
    and produces the required authentication headers for API requests.

    The signature is computed over the query string (including timestamp)
    using HMAC-SHA256 with the API secret as the key.

    Example:
        >>> auth = PionexAuthenticator(api_key="my_key", api_secret="my_secret")
        >>> headers = auth.generate_auth(params={"symbol": "BTC_USDT"})
        >>> print(headers.to_headers())
        {'PIONEX-KEY': 'my_key', 'PIONEX-SIGNATURE': '...'}

    Attributes:
        api_key: The Pionex API key
        api_secret: The Pionex API secret used for signing
    """

    def __init__(self, api_key: str, api_secret: str) -> None:
        """
        Initialize the authenticator with API credentials.

        Args:
            api_key: The Pionex API key
            api_secret: The Pionex API secret for HMAC signing

        Raises:
            ValueError: If api_key or api_secret is empty
        """
        if not api_key:
            raise ValueError("API key cannot be empty")
        if not api_secret:
            raise ValueError("API secret cannot be empty")

        self._api_key = api_key
        self._api_secret = api_secret

    @property
    def api_key(self) -> str:
        """The Pionex API key."""
        return self._api_key

    @staticmethod
    def generate_timestamp() -> int:
        """
        Generate current timestamp in milliseconds since epoch.

        Returns:
            Current time as milliseconds since Unix epoch
        """
        return int(time.time() * 1000)

    def compute_signature(self, query_string: str) -> str:
        """
        Compute HMAC-SHA256 signature for the given query string.

        The signature is computed using the API secret as the key
        and the query string as the message.

        Args:
            query_string: The URL-encoded query string to sign

        Returns:
            Hexadecimal string representation of the HMAC-SHA256 signature
        """
        signature = hmac.new(
            key=self._api_secret.encode("utf-8"),
            msg=query_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        )
        return signature.hexdigest()

    def build_query_string(
        self,
        params: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> str:
        """
        Build a query string with timestamp included.

        The timestamp is always added to the parameters. If not provided,
        the current timestamp is generated.

        Args:
            params: Optional dictionary of query parameters
            timestamp: Optional timestamp in milliseconds. If None, current time is used.

        Returns:
            URL-encoded query string with timestamp included
        """
        if timestamp is None:
            timestamp = self.generate_timestamp()

        # Start with provided params or empty dict
        query_params: dict[str, Any] = dict(params) if params else {}

        # Add timestamp to params
        query_params["timestamp"] = timestamp

        # Sort parameters alphabetically for consistent signature generation
        sorted_params = sorted(query_params.items())

        return urlencode(sorted_params)

    def generate_auth(
        self,
        params: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> AuthHeaders:
        """
        Generate authentication headers for a Pionex API request.

        This method:
        1. Generates a timestamp (if not provided)
        2. Builds the query string with all parameters including timestamp
        3. Computes the HMAC-SHA256 signature
        4. Returns the authentication headers

        Args:
            params: Optional dictionary of query parameters for the request
            timestamp: Optional timestamp in milliseconds. If None, current time is used.

        Returns:
            AuthHeaders containing the API key, signature, and timestamp

        Example:
            >>> auth = PionexAuthenticator("key", "secret")
            >>> headers = auth.generate_auth({"symbol": "BTC_USDT"})
            >>> print(headers.timestamp)  # Timestamp used
            >>> print(headers.to_headers())  # Headers dict
        """
        if timestamp is None:
            timestamp = self.generate_timestamp()

        query_string = self.build_query_string(params=params, timestamp=timestamp)
        signature = self.compute_signature(query_string)

        return AuthHeaders(
            pionex_key=self._api_key,
            pionex_signature=signature,
            timestamp=timestamp,
        )

    def sign_request(
        self,
        params: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """
        Sign a request and return headers and updated params.

        This is a convenience method that returns both the HTTP headers
        and the query parameters (with timestamp added) ready for use
        in an HTTP request.

        Args:
            params: Optional dictionary of query parameters
            timestamp: Optional timestamp in milliseconds

        Returns:
            Tuple of (headers_dict, params_with_timestamp)

        Example:
            >>> auth = PionexAuthenticator("key", "secret")
            >>> headers, params = auth.sign_request({"symbol": "BTC_USDT"})
            >>> # Use headers and params in HTTP request
        """
        if timestamp is None:
            timestamp = self.generate_timestamp()

        auth_headers = self.generate_auth(params=params, timestamp=timestamp)

        # Build params with timestamp
        request_params: dict[str, Any] = dict(params) if params else {}
        request_params["timestamp"] = timestamp

        return auth_headers.to_headers(), request_params
