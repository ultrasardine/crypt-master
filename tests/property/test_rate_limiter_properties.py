"""
Property-based tests for Pionex Rate Limiter.

Feature: pionex-api-extended
Property 1: Rate Limit Weight Tracking

These tests use the hypothesis library to verify that the rate limiter
correctly tracks weights and enforces limits.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from lib.pionex.rate_limiter import RateLimiter

# Custom strategies for rate limiter testing
weight_strategy = st.integers(min_value=1, max_value=10)
is_private_strategy = st.booleans()


class TestRateLimitWeightTracking:
    """
    Property 1: Rate Limit Weight Tracking

    *For any* sequence of API requests, the total weight in any 1-second window
    SHALL NOT exceed 10 for IP or account limits.

    **Validates: Requirements 4.1, 4.2**
    """

    @settings(max_examples=100)
    @given(
        weights=st.lists(weight_strategy, min_size=1, max_size=20),
    )
    def test_ip_weight_never_exceeds_limit(self, weights: list[int]) -> None:
        """
        Property: IP weight usage never exceeds 1.0 (100% of limit).

        After recording any sequence of weights, the ip_usage property
        should never exceed 1.0 when weights are recorded with proper timing.

        **Validates: Requirements 4.1**
        """
        limiter = RateLimiter(ip_weight_limit=10, account_weight_limit=10)

        for weight in weights:
            # Record the weight
            limiter.record_request(weight=weight, is_private=False)

        # Usage should be capped at 1.0
        assert limiter.ip_usage <= 1.0, (
            f"IP usage {limiter.ip_usage} exceeded 1.0 after recording weights {weights}"
        )

    @settings(max_examples=100)
    @given(
        weights=st.lists(weight_strategy, min_size=1, max_size=20),
    )
    def test_account_weight_never_exceeds_limit(self, weights: list[int]) -> None:
        """
        Property: Account weight usage never exceeds 1.0 (100% of limit).

        After recording any sequence of weights for private endpoints,
        the account_usage property should never exceed 1.0.

        **Validates: Requirements 4.2**
        """
        limiter = RateLimiter(ip_weight_limit=10, account_weight_limit=10)

        for weight in weights:
            # Record the weight as private
            limiter.record_request(weight=weight, is_private=True)

        # Usage should be capped at 1.0
        assert limiter.account_usage <= 1.0, (
            f"Account usage {limiter.account_usage} exceeded 1.0 after recording weights {weights}"
        )

    @settings(max_examples=100)
    @given(
        weight=weight_strategy,
        is_private=is_private_strategy,
    )
    def test_single_weight_recorded_correctly(self, weight: int, is_private: bool) -> None:
        """
        Property: A single recorded weight is reflected in usage metrics.

        After recording a single weight, the usage should equal weight/limit.

        **Validates: Requirements 4.1, 4.2**
        """
        limiter = RateLimiter(ip_weight_limit=10, account_weight_limit=10)
        limiter.reset()

        # Record a single weight
        limiter.record_request(weight=weight, is_private=is_private)

        # IP usage should reflect the weight
        expected_ip_usage = min(1.0, weight / 10)
        assert abs(limiter.ip_usage - expected_ip_usage) < 0.001, (
            f"IP usage {limiter.ip_usage} != expected {expected_ip_usage} for weight {weight}"
        )

        # Account usage should only reflect weight if private
        if is_private:
            expected_account_usage = min(1.0, weight / 10)
            assert abs(limiter.account_usage - expected_account_usage) < 0.001, (
                f"Account usage {limiter.account_usage} != expected {expected_account_usage}"
            )
        else:
            assert limiter.account_usage == 0.0, (
                f"Account usage {limiter.account_usage} should be 0 for public request"
            )

    @settings(max_examples=100)
    @given(
        weights=st.lists(weight_strategy, min_size=2, max_size=5),
    )
    def test_cumulative_weights_sum_correctly(self, weights: list[int]) -> None:
        """
        Property: Multiple weights sum correctly in the usage calculation.

        After recording multiple weights, the usage should equal sum(weights)/limit,
        capped at 1.0.

        **Validates: Requirements 4.1, 4.2**
        """
        limiter = RateLimiter(ip_weight_limit=10, account_weight_limit=10)
        limiter.reset()

        # Record all weights
        for weight in weights:
            limiter.record_request(weight=weight, is_private=True)

        # Calculate expected usage
        total_weight = sum(weights)
        expected_usage = min(1.0, total_weight / 10)

        # Both IP and account usage should match (all private)
        assert abs(limiter.ip_usage - expected_usage) < 0.001, (
            f"IP usage {limiter.ip_usage} != expected {expected_usage} for weights {weights}"
        )
        assert abs(limiter.account_usage - expected_usage) < 0.001, (
            f"Account usage {limiter.account_usage} != expected {expected_usage}"
        )

    @settings(max_examples=50)
    @given(
        weight=weight_strategy,
    )
    def test_reset_clears_all_weights(self, weight: int) -> None:
        """
        Property: Reset clears all tracked weights.

        After recording weights and calling reset(), usage should be 0.

        **Validates: Requirements 4.1, 4.2**
        """
        limiter = RateLimiter(ip_weight_limit=10, account_weight_limit=10)

        # Record some weights
        limiter.record_request(weight=weight, is_private=True)

        # Verify weights were recorded
        assert limiter.ip_usage > 0 or weight == 0

        # Reset
        limiter.reset()

        # Usage should be 0
        assert limiter.ip_usage == 0.0, f"IP usage {limiter.ip_usage} should be 0 after reset"
        assert limiter.account_usage == 0.0, (
            f"Account usage {limiter.account_usage} should be 0 after reset"
        )

    @settings(max_examples=50)
    @given(
        ban_duration=st.floats(min_value=0.1, max_value=120.0),
    )
    def test_handle_429_sets_ban(self, ban_duration: float) -> None:
        """
        Property: handle_429() sets the ban correctly.

        After calling handle_429(), is_banned should be True and
        ban_remaining should be approximately ban_duration.

        **Validates: Requirements 4.4**
        """
        limiter = RateLimiter(ban_duration=ban_duration)

        # Handle 429
        limiter.handle_429()

        # Should be banned
        assert limiter.is_banned, "Should be banned after handle_429()"

        # Ban remaining should be close to ban_duration
        # Allow some tolerance for execution time
        assert limiter.ban_remaining <= ban_duration + 0.1, (
            f"Ban remaining {limiter.ban_remaining} > ban_duration {ban_duration}"
        )
        assert limiter.ban_remaining >= ban_duration - 0.1, (
            f"Ban remaining {limiter.ban_remaining} < ban_duration - 0.1"
        )

    @settings(max_examples=50)
    @given(
        public_weights=st.lists(weight_strategy, min_size=1, max_size=5),
        private_weights=st.lists(weight_strategy, min_size=1, max_size=5),
    )
    def test_public_private_weight_separation(
        self, public_weights: list[int], private_weights: list[int]
    ) -> None:
        """
        Property: Public requests only affect IP usage, private affect both.

        Public requests should only increment IP usage.
        Private requests should increment both IP and account usage.

        **Validates: Requirements 4.1, 4.2**
        """
        limiter = RateLimiter(ip_weight_limit=100, account_weight_limit=100)
        limiter.reset()

        # Record public weights
        for weight in public_weights:
            limiter.record_request(weight=weight, is_private=False)

        public_total = sum(public_weights)
        expected_ip_after_public = min(1.0, public_total / 100)

        # IP should have public weights, account should be 0
        assert abs(limiter.ip_usage - expected_ip_after_public) < 0.001
        assert limiter.account_usage == 0.0

        # Record private weights
        for weight in private_weights:
            limiter.record_request(weight=weight, is_private=True)

        private_total = sum(private_weights)
        total_ip = public_total + private_total
        expected_ip_final = min(1.0, total_ip / 100)
        expected_account_final = min(1.0, private_total / 100)

        # IP should have all weights, account should have only private
        assert abs(limiter.ip_usage - expected_ip_final) < 0.001, (
            f"IP usage {limiter.ip_usage} != expected {expected_ip_final}"
        )
        assert abs(limiter.account_usage - expected_account_final) < 0.001, (
            f"Account usage {limiter.account_usage} != expected {expected_account_final}"
        )
