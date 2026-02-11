"""
Property-based tests for Pionex API Authentication Module.

Feature: pionex-trading-bot
Property 1: HMAC-SHA256 Signature Determinism

These tests use the hypothesis library to verify that the authentication
module behaves correctly across a wide range of inputs.
"""

import hashlib
import hmac
import string

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from lib.pionex.auth import PionexAuthenticator

# Custom strategies for generating realistic API parameters
api_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits,
    min_size=1,
    max_size=64,
)

api_secret_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + string.punctuation,
    min_size=1,
    max_size=128,
)

# Strategy for HTTP methods
http_method_strategy = st.sampled_from(["GET", "POST", "DELETE"])

# Strategy for API paths
api_path_strategy = st.text(
    alphabet=string.ascii_lowercase + string.digits + "/_",
    min_size=1,
    max_size=64,
).map(lambda s: f"/api/v1/{s}")

# Strategy for query string parameters (key-value pairs)
param_key_strategy = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_",
    min_size=1,
    max_size=32,
)

param_value_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "_-.",
    min_size=0,
    max_size=64,
)

params_strategy = st.dictionaries(
    keys=param_key_strategy,
    values=param_value_strategy,
    min_size=0,
    max_size=10,
)

# Strategy for timestamps (realistic millisecond timestamps)
timestamp_strategy = st.integers(
    min_value=1_000_000_000_000,  # ~2001
    max_value=9_999_999_999_999,  # ~2286
)

# Strategy for arbitrary query strings
query_string_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "=&_-.",
    min_size=0,
    max_size=500,
)


class TestSignatureDeterminism:
    """
    Property 1: HMAC-SHA256 Signature Determinism

    *For any* API request parameters and secret key, generating the signature
    twice SHALL produce identical results.

    **Validates: Requirements 1.8**
    """

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        method=http_method_strategy,
        path=api_path_strategy,
        query_string=query_string_strategy,
    )
    def test_compute_signature_is_deterministic(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path: str,
        query_string: str,
    ) -> None:
        """
        Property: compute_signature() produces identical results for identical inputs.

        **Validates: Requirements 1.8**
        """
        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)

        # Generate signature twice with same inputs
        signature1 = auth.compute_signature(
            method=method, path=path, query_string=query_string
        )
        signature2 = auth.compute_signature(
            method=method, path=path, query_string=query_string
        )

        # Signatures must be identical
        assert signature1 == signature2, (
            f"Signature not deterministic for method={method}, path={path}, "
            f"query_string={query_string!r}"
        )

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        method=http_method_strategy,
        path=api_path_strategy,
        params=params_strategy,
        timestamp=timestamp_strategy,
    )
    def test_generate_auth_is_deterministic(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path: str,
        params: dict[str, str],
        timestamp: int,
    ) -> None:
        """
        Property: generate_auth() produces identical AuthHeaders for identical inputs.

        **Validates: Requirements 1.8**
        """
        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)

        # Generate auth headers twice with same inputs
        auth_headers1 = auth.generate_auth(
            method=method, path=path, params=params, timestamp=timestamp
        )
        auth_headers2 = auth.generate_auth(
            method=method, path=path, params=params, timestamp=timestamp
        )

        # All fields must be identical
        assert auth_headers1.pionex_key == auth_headers2.pionex_key
        assert auth_headers1.pionex_signature == auth_headers2.pionex_signature
        assert auth_headers1.timestamp == auth_headers2.timestamp

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        method=http_method_strategy,
        path=api_path_strategy,
        params=params_strategy,
        timestamp=timestamp_strategy,
    )
    def test_sign_request_is_deterministic(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path: str,
        params: dict[str, str],
        timestamp: int,
    ) -> None:
        """
        Property: sign_request() produces identical results for identical inputs.

        **Validates: Requirements 1.8**
        """
        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)

        # Sign request twice with same inputs
        headers1, params1 = auth.sign_request(
            method=method, path=path, params=params, timestamp=timestamp
        )
        headers2, params2 = auth.sign_request(
            method=method, path=path, params=params, timestamp=timestamp
        )

        # Headers and params must be identical
        assert headers1 == headers2
        assert params1 == params2

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        method=http_method_strategy,
        path=api_path_strategy,
        query_string=query_string_strategy,
    )
    def test_signature_matches_standard_hmac_sha256(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path: str,
        query_string: str,
    ) -> None:
        """
        Property: compute_signature() produces valid HMAC-SHA256 output.

        This verifies that our implementation matches the standard HMAC-SHA256
        algorithm, ensuring interoperability with the Pionex API.

        **Validates: Requirements 1.8**
        """
        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)

        # Compute signature using our implementation
        our_signature = auth.compute_signature(
            method=method, path=path, query_string=query_string
        )

        # Compute expected signature using standard library
        # Message format: METHOD + PATH + ? + QUERY_STRING
        message = f"{method.upper()}{path}?{query_string}"
        expected_signature = hmac.new(
            key=api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Must match exactly
        assert our_signature == expected_signature, (
            f"Signature mismatch: got {our_signature}, expected {expected_signature}"
        )

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        path=api_path_strategy,
        query_string=query_string_strategy,
    )
    def test_post_signature_includes_body(
        self,
        api_key: str,
        api_secret: str,
        path: str,
        query_string: str,
    ) -> None:
        """
        Property: POST signature includes body per Pionex documentation.

        Per Pionex docs Step 6: Concatenate entity body for POST and DELETE.

        **Validates: Requirements 1.8**
        """
        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)
        body = '{"test":"value"}'

        # Compute signature with body
        sig_with_body = auth.compute_signature(
            method="POST", path=path, query_string=query_string, body=body
        )

        # Compute expected: METHOD + PATH + ? + QUERY_STRING + BODY
        message = f"POST{path}?{query_string}{body}"
        expected = hmac.new(
            key=api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert sig_with_body == expected

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        path=api_path_strategy,
        query_string=query_string_strategy,
    )
    def test_get_signature_ignores_body(
        self,
        api_key: str,
        api_secret: str,
        path: str,
        query_string: str,
    ) -> None:
        """
        Property: GET signature does not include body.

        Per Pionex docs, only POST and DELETE include entity body.

        **Validates: Requirements 1.8**
        """
        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)
        body = '{"ignored":"value"}'

        # GET with body should equal GET without body
        sig_with_body = auth.compute_signature(
            method="GET", path=path, query_string=query_string, body=body
        )
        sig_without_body = auth.compute_signature(
            method="GET", path=path, query_string=query_string, body=None
        )

        assert sig_with_body == sig_without_body

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        params=params_strategy,
        timestamp=timestamp_strategy,
    )
    def test_build_query_string_is_deterministic(
        self,
        api_key: str,
        api_secret: str,
        params: dict[str, str],
        timestamp: int,
    ) -> None:
        """
        Property: build_query_string() produces identical results for identical inputs.

        This is a prerequisite for signature determinism - if the query string
        varies, the signature will also vary.

        **Validates: Requirements 1.8**
        """
        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)

        # Build query string twice with same inputs
        query1 = auth.build_query_string(params=params, timestamp=timestamp)
        query2 = auth.build_query_string(params=params, timestamp=timestamp)

        # Query strings must be identical
        assert query1 == query2, f"Query string not deterministic: {query1!r} != {query2!r}"

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret1=api_secret_strategy,
        api_secret2=api_secret_strategy,
        method=http_method_strategy,
        path=api_path_strategy,
        query_string=query_string_strategy,
    )
    def test_different_secrets_produce_different_signatures(
        self,
        api_key: str,
        api_secret1: str,
        api_secret2: str,
        method: str,
        path: str,
        query_string: str,
    ) -> None:
        """
        Property: Different secrets produce different signatures (collision resistance).

        This verifies that the signature is actually dependent on the secret key,
        which is essential for security.

        **Validates: Requirements 1.8**
        """
        # Skip if secrets are the same (trivial case)
        assume(api_secret1 != api_secret2)

        auth1 = PionexAuthenticator(api_key=api_key, api_secret=api_secret1)
        auth2 = PionexAuthenticator(api_key=api_key, api_secret=api_secret2)

        signature1 = auth1.compute_signature(
            method=method, path=path, query_string=query_string
        )
        signature2 = auth2.compute_signature(
            method=method, path=path, query_string=query_string
        )

        # Signatures should differ (with overwhelming probability for HMAC-SHA256)
        assert signature1 != signature2, (
            f"Different secrets produced same signature for method={method}, "
            f"path={path}, query={query_string!r}"
        )

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        method1=http_method_strategy,
        method2=http_method_strategy,
        path=api_path_strategy,
        query_string=query_string_strategy,
    )
    def test_different_methods_produce_different_signatures(
        self,
        api_key: str,
        api_secret: str,
        method1: str,
        method2: str,
        path: str,
        query_string: str,
    ) -> None:
        """
        Property: Different HTTP methods produce different signatures.

        This verifies that the signature includes the HTTP method, preventing
        replay attacks across different request types.

        **Validates: Requirements 1.8**
        """
        # Skip if methods are the same (trivial case)
        assume(method1 != method2)

        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)

        signature1 = auth.compute_signature(
            method=method1, path=path, query_string=query_string
        )
        signature2 = auth.compute_signature(
            method=method2, path=path, query_string=query_string
        )

        # Signatures should differ
        assert signature1 != signature2, (
            f"Different methods produced same signature: {method1} vs {method2}"
        )

    @settings(max_examples=20)
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
        method=http_method_strategy,
        path1=api_path_strategy,
        path2=api_path_strategy,
        query_string=query_string_strategy,
    )
    def test_different_paths_produce_different_signatures(
        self,
        api_key: str,
        api_secret: str,
        method: str,
        path1: str,
        path2: str,
        query_string: str,
    ) -> None:
        """
        Property: Different API paths produce different signatures.

        This verifies that the signature includes the request path, preventing
        replay attacks across different endpoints.

        **Validates: Requirements 1.8**
        """
        # Skip if paths are the same (trivial case)
        assume(path1 != path2)

        auth = PionexAuthenticator(api_key=api_key, api_secret=api_secret)

        signature1 = auth.compute_signature(
            method=method, path=path1, query_string=query_string
        )
        signature2 = auth.compute_signature(
            method=method, path=path2, query_string=query_string
        )

        # Signatures should differ
        assert signature1 != signature2, (
            f"Different paths produced same signature: {path1} vs {path2}"
        )
