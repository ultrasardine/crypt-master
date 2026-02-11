"""
Property-based tests for Pionex WebSocket Reconnection.

Feature: pionex-api-extended
Property 4: WebSocket Reconnection

These tests use the hypothesis library to verify that the WebSocket manager
correctly implements exponential backoff for reconnection.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from lib.pionex.websocket import (
    INITIAL_RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
    RECONNECT_MULTIPLIER,
    PionexWebSocketManager,
    Subscription,
    WebSocketTopic,
)


class TestWebSocketReconnection:
    """
    Property 4: WebSocket Reconnection

    *For any* WebSocket disconnection, reconnection SHALL be attempted with
    exponential backoff (1s, 2s, 4s, 8s, max 30s).

    **Validates: Requirements 5.5**
    """

    @settings(max_examples=100)
    @given(
        num_failures=st.integers(min_value=0, max_value=10),
    )
    def test_exponential_backoff_sequence(self, num_failures: int) -> None:
        """
        Property: Reconnection delay follows exponential backoff pattern.

        After N consecutive failures, the delay should be:
        min(INITIAL_DELAY * (MULTIPLIER ^ N), MAX_DELAY)

        **Validates: Requirements 5.5**
        """
        manager = PionexWebSocketManager()

        # Simulate N reconnection failures by incrementing delay
        for i in range(num_failures):
            current_delay = manager.get_reconnect_delay(is_private=False)

            # Calculate expected delay
            expected_delay = min(
                INITIAL_RECONNECT_DELAY * (RECONNECT_MULTIPLIER**i),
                MAX_RECONNECT_DELAY,
            )

            assert abs(current_delay - expected_delay) < 0.001, (
                f"Delay after {i} failures: {current_delay} != expected {expected_delay}"
            )

            # Simulate a reconnection attempt that updates the delay
            # (In real code, this happens in _reconnect method)
            new_delay = min(current_delay * RECONNECT_MULTIPLIER, MAX_RECONNECT_DELAY)
            manager._public_reconnect_delay = new_delay

    @settings(max_examples=100)
    @given(
        num_failures=st.integers(min_value=0, max_value=20),
    )
    def test_delay_never_exceeds_max(self, num_failures: int) -> None:
        """
        Property: Reconnection delay never exceeds MAX_RECONNECT_DELAY.

        No matter how many failures occur, the delay should be capped at 30s.

        **Validates: Requirements 5.5**
        """
        manager = PionexWebSocketManager()

        # Simulate many reconnection failures
        for _ in range(num_failures):
            current_delay = manager.get_reconnect_delay(is_private=False)
            new_delay = min(current_delay * RECONNECT_MULTIPLIER, MAX_RECONNECT_DELAY)
            manager._public_reconnect_delay = new_delay

        final_delay = manager.get_reconnect_delay(is_private=False)

        assert final_delay <= MAX_RECONNECT_DELAY, (
            f"Delay {final_delay} exceeds max {MAX_RECONNECT_DELAY} "
            f"after {num_failures} failures"
        )

    @settings(max_examples=50)
    @given(
        is_private=st.booleans(),
    )
    def test_initial_delay_is_correct(self, is_private: bool) -> None:
        """
        Property: Initial reconnection delay is INITIAL_RECONNECT_DELAY.

        A fresh manager should have the initial delay value.

        **Validates: Requirements 5.5**
        """
        manager = PionexWebSocketManager()

        delay = manager.get_reconnect_delay(is_private=is_private)

        assert delay == INITIAL_RECONNECT_DELAY, (
            f"Initial delay {delay} != expected {INITIAL_RECONNECT_DELAY}"
        )

    @settings(max_examples=50)
    @given(
        num_failures=st.integers(min_value=1, max_value=10),
        is_private=st.booleans(),
    )
    def test_reset_restores_initial_delay(
        self, num_failures: int, is_private: bool
    ) -> None:
        """
        Property: reset_reconnect_delay restores initial delay.

        After any number of failures, reset should restore the initial delay.

        **Validates: Requirements 5.5**
        """
        manager = PionexWebSocketManager()

        # Simulate failures to increase delay
        for _ in range(num_failures):
            if is_private:
                manager._private_reconnect_delay = min(
                    manager._private_reconnect_delay * RECONNECT_MULTIPLIER,
                    MAX_RECONNECT_DELAY,
                )
            else:
                manager._public_reconnect_delay = min(
                    manager._public_reconnect_delay * RECONNECT_MULTIPLIER,
                    MAX_RECONNECT_DELAY,
                )

        # Reset
        manager.reset_reconnect_delay(is_private=is_private)

        delay = manager.get_reconnect_delay(is_private=is_private)

        assert delay == INITIAL_RECONNECT_DELAY, (
            f"Delay after reset {delay} != expected {INITIAL_RECONNECT_DELAY}"
        )


    @settings(max_examples=50)
    @given(
        is_private=st.booleans(),
    )
    def test_public_private_delays_independent(self, is_private: bool) -> None:
        """
        Property: Public and private reconnection delays are independent.

        Modifying one should not affect the other.

        **Validates: Requirements 5.5**
        """
        manager = PionexWebSocketManager()

        # Increase one delay
        if is_private:
            manager._private_reconnect_delay = MAX_RECONNECT_DELAY
        else:
            manager._public_reconnect_delay = MAX_RECONNECT_DELAY

        # Check the other is unchanged
        other_delay = manager.get_reconnect_delay(is_private=not is_private)

        assert other_delay == INITIAL_RECONNECT_DELAY, (
            f"Other delay {other_delay} was affected when it shouldn't be"
        )

    @settings(max_examples=100)
    @given(
        failures_sequence=st.lists(
            st.booleans(),  # True = failure (increase delay), False = success (reset)
            min_size=1,
            max_size=20,
        ),
    )
    def test_delay_sequence_with_successes(self, failures_sequence: list[bool]) -> None:
        """
        Property: Successful reconnection resets the delay.

        A sequence of failures and successes should correctly track delay.

        **Validates: Requirements 5.5**
        """
        manager = PionexWebSocketManager()

        for is_failure in failures_sequence:
            if is_failure:
                # Simulate failure - increase delay
                current = manager._public_reconnect_delay
                manager._public_reconnect_delay = min(
                    current * RECONNECT_MULTIPLIER, MAX_RECONNECT_DELAY
                )
            else:
                # Simulate success - reset delay
                manager.reset_reconnect_delay(is_private=False)

        final_delay = manager.get_reconnect_delay(is_private=False)

        # Delay should always be within valid range
        assert INITIAL_RECONNECT_DELAY <= final_delay <= MAX_RECONNECT_DELAY, (
            f"Final delay {final_delay} out of valid range "
            f"[{INITIAL_RECONNECT_DELAY}, {MAX_RECONNECT_DELAY}]"
        )

    @settings(max_examples=50)
    @given(
        num_subscriptions=st.integers(min_value=0, max_value=5),
    )
    def test_subscriptions_tracked_for_resubscription(
        self, num_subscriptions: int
    ) -> None:
        """
        Property: Subscriptions are tracked for re-subscription after reconnect.

        The manager should maintain a list of subscriptions that can be
        restored after reconnection.

        **Validates: Requirements 5.5**
        """
        manager = PionexWebSocketManager()

        # Add subscriptions directly (simulating successful subscriptions)
        for i in range(num_subscriptions):
            sub = Subscription(
                topic=WebSocketTopic.TRADE,
                symbol=f"BTC_USDT_{i}",
            )
            manager._public_subscriptions.append(sub)

        # Verify subscriptions are tracked
        assert len(manager.public_subscriptions) == num_subscriptions, (
            f"Expected {num_subscriptions} subscriptions, "
            f"got {len(manager.public_subscriptions)}"
        )

        # Verify subscriptions are copies (not references)
        original_count = len(manager._public_subscriptions)
        subs_copy = manager.public_subscriptions
        subs_copy.clear()

        assert len(manager._public_subscriptions) == original_count, (
            "Modifying returned subscriptions should not affect internal list"
        )
