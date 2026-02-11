"""
Unit tests for Pionex API Authentication Module.

Tests the PionexAuthenticator class for:
- Timestamp generation
- HMAC-SHA256 signature computation (with method + path + query string)
- Query string building
- Authentication header generation
"""

import hashlib
import hmac
import time
from unittest.mock import patch

import pytest

from lib.pionex.auth import AuthHeaders, PionexAuthenticator


class TestAuthHeaders:
    """Tests for the AuthHeaders dataclass."""

    def test_auth_headers_creation(self) -> None:
        """Test AuthHeaders can be created with required fields."""
        headers = AuthHeaders(
            pionex_key="test_key",
            pionex_signature="test_signature",
            timestamp=1234567890000,
        )
        assert headers.pionex_key == "test_key"
        assert headers.pionex_signature == "test_signature"
        assert headers.timestamp == 1234567890000

    def test_auth_headers_to_headers(self) -> None:
        """Test AuthHeaders.to_headers() returns correct dictionary."""
        headers = AuthHeaders(
            pionex_key="my_api_key",
            pionex_signature="abc123signature",
            timestamp=1234567890000,
        )
        result = headers.to_headers()

        assert result == {
            "PIONEX-KEY": "my_api_key",
            "PIONEX-SIGNATURE": "abc123signature",
        }

    def test_auth_headers_immutable(self) -> None:
        """Test AuthHeaders is immutable (frozen dataclass)."""
        headers = AuthHeaders(
            pionex_key="key",
            pionex_signature="sig",
            timestamp=1000,
        )
        with pytest.raises(AttributeError):
            headers.pionex_key = "new_key"  # type: ignore[misc]


class TestPionexAuthenticatorInit:
    """Tests for PionexAuthenticator initialization."""

    def test_init_with_valid_credentials(self) -> None:
        """Test authenticator initializes with valid credentials."""
        auth = PionexAuthenticator(api_key="test_key", api_secret="test_secret")
        assert auth.api_key == "test_key"

    def test_init_with_empty_api_key_raises(self) -> None:
        """Test authenticator raises ValueError for empty API key."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            PionexAuthenticator(api_key="", api_secret="test_secret")

    def test_init_with_empty_api_secret_raises(self) -> None:
        """Test authenticator raises ValueError for empty API secret."""
        with pytest.raises(ValueError, match="API secret cannot be empty"):
            PionexAuthenticator(api_key="test_key", api_secret="")


class TestTimestampGeneration:
    """Tests for timestamp generation."""

    def test_generate_timestamp_returns_milliseconds(self) -> None:
        """Test timestamp is in milliseconds (13+ digits)."""
        timestamp = PionexAuthenticator.generate_timestamp()
        # Millisecond timestamps should be 13 digits for current era
        assert timestamp > 1_000_000_000_000
        assert timestamp < 10_000_000_000_000

    def test_generate_timestamp_is_current_time(self) -> None:
        """Test timestamp is close to current time."""
        before = int(time.time() * 1000)
        timestamp = PionexAuthenticator.generate_timestamp()
        after = int(time.time() * 1000)

        assert before <= timestamp <= after

    def test_generate_timestamp_is_integer(self) -> None:
        """Test timestamp is an integer."""
        timestamp = PionexAuthenticator.generate_timestamp()
        assert isinstance(timestamp, int)


class TestSignatureComputation:
    """Tests for HMAC-SHA256 signature computation."""

    def test_compute_signature_returns_hex_string(self) -> None:
        """Test signature is a hexadecimal string."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        signature = auth.compute_signature(
            method="GET",
            path="/api/v1/account/balances",
            query_string="timestamp=1234567890000",
        )

        # Should be 64 hex characters (256 bits = 32 bytes = 64 hex chars)
        assert len(signature) == 64
        assert all(c in "0123456789abcdef" for c in signature)

    def test_compute_signature_includes_method_and_path(self) -> None:
        """Test signature is computed over method + path + query string."""
        api_secret = "my_secret_key"
        method = "GET"
        path = "/api/v1/account/balances"
        query_string = "symbol=BTC_USDT&timestamp=1234567890000"

        auth = PionexAuthenticator(api_key="key", api_secret=api_secret)
        signature = auth.compute_signature(
            method=method,
            path=path,
            query_string=query_string,
        )

        # Compute expected signature manually: METHOD + PATH + ? + QUERY_STRING
        message = f"{method}{path}?{query_string}"
        expected = hmac.new(
            key=api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert signature == expected

    def test_compute_signature_includes_body_for_post(self) -> None:
        """Test signature includes body for POST requests per Pionex docs."""
        api_secret = "my_secret_key"
        method = "POST"
        path = "/api/v1/trade/order"
        query_string = "timestamp=1234567890000"
        body = '{"side":"BUY","symbol":"BTC_USDT"}'

        auth = PionexAuthenticator(api_key="key", api_secret=api_secret)
        signature = auth.compute_signature(
            method=method,
            path=path,
            query_string=query_string,
            body=body,
        )

        # Compute expected: METHOD + PATH + ? + QUERY_STRING + BODY
        message = f"{method}{path}?{query_string}{body}"
        expected = hmac.new(
            key=api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert signature == expected

    def test_compute_signature_includes_body_for_delete(self) -> None:
        """Test signature includes body for DELETE requests per Pionex docs."""
        api_secret = "my_secret_key"
        method = "DELETE"
        path = "/api/v1/trade/order"
        query_string = "timestamp=1234567890000"
        body = '{"orderId":"12345"}'

        auth = PionexAuthenticator(api_key="key", api_secret=api_secret)
        signature = auth.compute_signature(
            method=method,
            path=path,
            query_string=query_string,
            body=body,
        )

        # Compute expected: METHOD + PATH + ? + QUERY_STRING + BODY
        message = f"{method}{path}?{query_string}{body}"
        expected = hmac.new(
            key=api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert signature == expected

    def test_compute_signature_no_body_for_get(self) -> None:
        """Test GET requests don't include body even if provided."""
        api_secret = "my_secret_key"
        method = "GET"
        path = "/api/v1/account/balances"
        query_string = "timestamp=1234567890000"
        body = '{"ignored":"value"}'

        auth = PionexAuthenticator(api_key="key", api_secret=api_secret)
        signature_with_body = auth.compute_signature(
            method=method,
            path=path,
            query_string=query_string,
            body=body,
        )
        signature_without_body = auth.compute_signature(
            method=method,
            path=path,
            query_string=query_string,
            body=None,
        )

        # GET should ignore body
        assert signature_with_body == signature_without_body

    def test_compute_signature_deterministic(self) -> None:
        """Test same inputs produce same signature."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")

        sig1 = auth.compute_signature(
            method="GET",
            path="/api/v1/test",
            query_string="param1=value1&param2=value2",
        )
        sig2 = auth.compute_signature(
            method="GET",
            path="/api/v1/test",
            query_string="param1=value1&param2=value2",
        )

        assert sig1 == sig2

    def test_compute_signature_different_secrets_differ(self) -> None:
        """Test different secrets produce different signatures."""
        auth1 = PionexAuthenticator(api_key="key", api_secret="secret1")
        auth2 = PionexAuthenticator(api_key="key", api_secret="secret2")

        sig1 = auth1.compute_signature(
            method="GET", path="/api/v1/test", query_string="test=value"
        )
        sig2 = auth2.compute_signature(
            method="GET", path="/api/v1/test", query_string="test=value"
        )

        assert sig1 != sig2

    def test_compute_signature_different_methods_differ(self) -> None:
        """Test different HTTP methods produce different signatures."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")

        sig_get = auth.compute_signature(
            method="GET", path="/api/v1/test", query_string="test=value"
        )
        sig_post = auth.compute_signature(
            method="POST", path="/api/v1/test", query_string="test=value"
        )

        assert sig_get != sig_post

    def test_compute_signature_different_paths_differ(self) -> None:
        """Test different paths produce different signatures."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")

        sig1 = auth.compute_signature(
            method="GET", path="/api/v1/path1", query_string="test=value"
        )
        sig2 = auth.compute_signature(
            method="GET", path="/api/v1/path2", query_string="test=value"
        )

        assert sig1 != sig2

    def test_compute_signature_different_queries_differ(self) -> None:
        """Test different query strings produce different signatures."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")

        sig1 = auth.compute_signature(
            method="GET", path="/api/v1/test", query_string="query1=value1"
        )
        sig2 = auth.compute_signature(
            method="GET", path="/api/v1/test", query_string="query2=value2"
        )

        assert sig1 != sig2

    def test_compute_signature_method_case_normalized(self) -> None:
        """Test method is normalized to uppercase."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")

        sig_lower = auth.compute_signature(
            method="get", path="/api/v1/test", query_string="test=value"
        )
        sig_upper = auth.compute_signature(
            method="GET", path="/api/v1/test", query_string="test=value"
        )

        assert sig_lower == sig_upper


class TestQueryStringBuilding:
    """Tests for query string building."""

    def test_build_query_string_with_timestamp_only(self) -> None:
        """Test query string with only timestamp."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        query = auth.build_query_string(params=None, timestamp=1234567890000)

        assert query == "timestamp=1234567890000"

    def test_build_query_string_with_params(self) -> None:
        """Test query string includes provided params."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        query = auth.build_query_string(
            params={"symbol": "BTC_USDT"},
            timestamp=1234567890000,
        )

        # Params should be sorted alphabetically
        assert query == "symbol=BTC_USDT&timestamp=1234567890000"

    def test_build_query_string_sorts_params(self) -> None:
        """Test query string params are sorted alphabetically."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        query = auth.build_query_string(
            params={"zebra": "z", "apple": "a", "middle": "m"},
            timestamp=1234567890000,
        )

        assert query == "apple=a&middle=m&timestamp=1234567890000&zebra=z"

    def test_build_query_string_generates_timestamp_if_not_provided(self) -> None:
        """Test timestamp is generated if not provided."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")

        with patch.object(PionexAuthenticator, "generate_timestamp", return_value=9999999999999):
            query = auth.build_query_string(params={"test": "value"})

        assert "timestamp=9999999999999" in query

    def test_build_query_string_url_encodes_special_chars(self) -> None:
        """Test special characters are URL encoded."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        query = auth.build_query_string(
            params={"param": "value with spaces"},
            timestamp=1000,
        )

        assert "value+with+spaces" in query or "value%20with%20spaces" in query


class TestGenerateAuth:
    """Tests for generate_auth method."""

    def test_generate_auth_returns_auth_headers(self) -> None:
        """Test generate_auth returns AuthHeaders instance."""
        auth = PionexAuthenticator(api_key="test_key", api_secret="test_secret")
        result = auth.generate_auth(
            method="GET",
            path="/api/v1/account/balances",
            timestamp=1234567890000,
        )

        assert isinstance(result, AuthHeaders)

    def test_generate_auth_includes_api_key(self) -> None:
        """Test generated auth includes the API key."""
        auth = PionexAuthenticator(api_key="my_api_key", api_secret="secret")
        result = auth.generate_auth(
            method="GET",
            path="/api/v1/test",
            timestamp=1000,
        )

        assert result.pionex_key == "my_api_key"

    def test_generate_auth_includes_timestamp(self) -> None:
        """Test generated auth includes the timestamp."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        result = auth.generate_auth(
            method="GET",
            path="/api/v1/test",
            timestamp=1234567890000,
        )

        assert result.timestamp == 1234567890000

    def test_generate_auth_computes_valid_signature(self) -> None:
        """Test generated signature is valid HMAC-SHA256."""
        api_secret = "my_secret"
        method = "GET"
        path = "/api/v1/account/balances"
        auth = PionexAuthenticator(api_key="key", api_secret=api_secret)

        result = auth.generate_auth(
            method=method,
            path=path,
            params={"symbol": "BTC_USDT"},
            timestamp=1234567890000,
        )

        # Verify signature manually: METHOD + PATH + ? + SORTED_QUERY_STRING
        query_string = "symbol=BTC_USDT&timestamp=1234567890000"
        message = f"{method}{path}?{query_string}"
        expected_sig = hmac.new(
            key=api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert result.pionex_signature == expected_sig

    def test_generate_auth_includes_body_in_signature_for_post(self) -> None:
        """Test POST request signature includes JSON body per Pionex docs."""
        api_secret = "my_secret"
        method = "POST"
        path = "/api/v1/trade/order"
        body = {"side": "BUY", "symbol": "BTC_USDT"}
        auth = PionexAuthenticator(api_key="key", api_secret=api_secret)

        result = auth.generate_auth(
            method=method,
            path=path,
            body=body,
            timestamp=1234567890000,
        )

        # Verify signature: METHOD + PATH + ? + QUERY_STRING + JSON_BODY
        # Body is serialized with sort_keys=True and compact separators
        query_string = "timestamp=1234567890000"
        body_str = '{"side":"BUY","symbol":"BTC_USDT"}'
        message = f"{method}{path}?{query_string}{body_str}"
        expected_sig = hmac.new(
            key=api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert result.pionex_signature == expected_sig

    def test_generate_auth_generates_timestamp_if_not_provided(self) -> None:
        """Test timestamp is auto-generated if not provided."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")

        before = int(time.time() * 1000)
        result = auth.generate_auth(method="GET", path="/api/v1/test")
        after = int(time.time() * 1000)

        assert before <= result.timestamp <= after


class TestSignRequest:
    """Tests for sign_request convenience method."""

    def test_sign_request_returns_tuple(self) -> None:
        """Test sign_request returns tuple of headers and params."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        result = auth.sign_request(
            method="GET",
            path="/api/v1/test",
            timestamp=1000,
        )

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_sign_request_headers_contain_required_keys(self) -> None:
        """Test returned headers contain PIONEX-KEY and PIONEX-SIGNATURE."""
        auth = PionexAuthenticator(api_key="my_key", api_secret="secret")
        headers, _ = auth.sign_request(
            method="GET",
            path="/api/v1/test",
            timestamp=1000,
        )

        assert "PIONEX-KEY" in headers
        assert "PIONEX-SIGNATURE" in headers
        assert headers["PIONEX-KEY"] == "my_key"

    def test_sign_request_params_contain_timestamp(self) -> None:
        """Test returned params contain timestamp."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        _, params = auth.sign_request(
            method="GET",
            path="/api/v1/test",
            timestamp=1234567890000,
        )

        assert "timestamp" in params
        assert params["timestamp"] == 1234567890000

    def test_sign_request_params_include_original_params(self) -> None:
        """Test returned params include original params plus timestamp."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        _, params = auth.sign_request(
            method="GET",
            path="/api/v1/test",
            params={"symbol": "BTC_USDT", "limit": 100},
            timestamp=1000,
        )

        assert params["symbol"] == "BTC_USDT"
        assert params["limit"] == 100
        assert params["timestamp"] == 1000

    def test_sign_request_does_not_modify_original_params(self) -> None:
        """Test original params dict is not modified."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        original_params = {"symbol": "BTC_USDT"}

        auth.sign_request(
            method="GET",
            path="/api/v1/test",
            params=original_params,
            timestamp=1000,
        )

        assert "timestamp" not in original_params
        assert original_params == {"symbol": "BTC_USDT"}

    def test_sign_request_post_with_body(self) -> None:
        """Test sign_request works with POST method and body."""
        auth = PionexAuthenticator(api_key="key", api_secret="secret")
        headers, params = auth.sign_request(
            method="POST",
            path="/api/v1/trade/order",
            params={"symbol": "BTC_USDT"},
            body={"side": "BUY", "type": "LIMIT", "price": "50000", "quantity": "0.001"},
            timestamp=1000,
        )

        assert "PIONEX-KEY" in headers
        assert "PIONEX-SIGNATURE" in headers
        assert params["timestamp"] == 1000
