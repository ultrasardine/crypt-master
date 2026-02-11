"""
Pionex API Rate Limiter.

This module provides rate limiting functionality for the Pionex API client
to prevent 429 errors and ensure reliable API access.

Requirements:
- 4.1: Track request weights per IP (10 weight/second limit)
- 4.2: Track request weights per account (10 weight/second limit for private endpoints)
- 4.3: Queue requests to stay within limits
- 4.4: Wait 60 seconds on 429 response before retrying
- 4.5: Log rate limit events
- 4.6: Expose current usage metrics via dashboard
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Pionex rate limits
IP_WEIGHT_LIMIT = 10  # 10 weight per second for all endpoints
ACCOUNT_WEIGHT_LIMIT = 10  # 10 weight per second for private endpoints
WINDOW_SIZE_SECONDS = 1.0  # 1 second sliding window
BAN_DURATION_SECONDS = 60.0  # 60 second ban on 429


@dataclass
class WeightRecord:
    """Record of a request's weight and timestamp."""

    timestamp: float
    weight: int


class RateLimiter:
    """
    Tracks API request weights to prevent 429 errors.

    Pionex limits:
    - IP: 10 weight/second (all endpoints)
    - Account: 10 weight/second (private endpoints)

    The rate limiter uses a sliding window approach to track request weights
    and will wait if necessary to stay within limits.

    Example:
        >>> limiter = RateLimiter()
        >>> await limiter.acquire(weight=1, is_private=False)
        >>> # Make API request...
        >>> limiter.record_request(weight=1, is_private=False)

    Attributes:
        ip_weight_limit: Maximum IP weight per second
        account_weight_limit: Maximum account weight per second
        window_size: Size of the sliding window in seconds
        ban_duration: Duration of ban after 429 in seconds
    """

    def __init__(
        self,
        ip_weight_limit: int = IP_WEIGHT_LIMIT,
        account_weight_limit: int = ACCOUNT_WEIGHT_LIMIT,
        window_size: float = WINDOW_SIZE_SECONDS,
        ban_duration: float = BAN_DURATION_SECONDS,
    ) -> None:
        """
        Initialize the rate limiter.

        Args:
            ip_weight_limit: Maximum IP weight per second (default: 10)
            account_weight_limit: Maximum account weight per second (default: 10)
            window_size: Size of the sliding window in seconds (default: 1.0)
            ban_duration: Duration of ban after 429 in seconds (default: 60.0)
        """
        self.ip_weight_limit = ip_weight_limit
        self.account_weight_limit = account_weight_limit
        self.window_size = window_size
        self.ban_duration = ban_duration

        # Weight tracking using deques for efficient sliding window
        self._ip_weights: deque[WeightRecord] = deque()
        self._account_weights: deque[WeightRecord] = deque()

        # Ban tracking
        self._banned_until: float | None = None

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    def _cleanup_old_weights(self, now: float) -> None:
        """
        Remove weight records older than the sliding window.

        Args:
            now: Current timestamp
        """
        cutoff = now - self.window_size

        # Clean up IP weights
        while self._ip_weights and self._ip_weights[0].timestamp < cutoff:
            self._ip_weights.popleft()

        # Clean up account weights
        while self._account_weights and self._account_weights[0].timestamp < cutoff:
            self._account_weights.popleft()

    def _get_current_ip_weight(self, now: float) -> int:
        """
        Get the current total IP weight in the sliding window.

        Args:
            now: Current timestamp

        Returns:
            Total weight in the current window
        """
        self._cleanup_old_weights(now)
        return sum(record.weight for record in self._ip_weights)

    def _get_current_account_weight(self, now: float) -> int:
        """
        Get the current total account weight in the sliding window.

        Args:
            now: Current timestamp

        Returns:
            Total weight in the current window
        """
        self._cleanup_old_weights(now)
        return sum(record.weight for record in self._account_weights)

    def _calculate_wait_time(self, weight: int, is_private: bool, now: float) -> float:
        """
        Calculate how long to wait before making a request.

        Args:
            weight: Weight of the request
            is_private: Whether this is a private endpoint
            now: Current timestamp

        Returns:
            Seconds to wait (0 if no wait needed)
        """
        # Check if banned
        if self._banned_until is not None and now < self._banned_until:
            return self._banned_until - now

        self._cleanup_old_weights(now)

        wait_time = 0.0

        # Check IP weight limit
        current_ip_weight = self._get_current_ip_weight(now)
        if current_ip_weight + weight > self.ip_weight_limit:
            # Need to wait for oldest weight to expire
            if self._ip_weights:
                oldest = self._ip_weights[0]
                wait_time = max(wait_time, oldest.timestamp + self.window_size - now)

        # Check account weight limit for private endpoints
        if is_private:
            current_account_weight = self._get_current_account_weight(now)
            if current_account_weight + weight > self.account_weight_limit:
                # Need to wait for oldest weight to expire
                if self._account_weights:
                    oldest = self._account_weights[0]
                    wait_time = max(wait_time, oldest.timestamp + self.window_size - now)

        return max(0.0, wait_time)

    async def acquire(self, weight: int = 1, is_private: bool = False) -> None:
        """
        Wait if necessary to stay within rate limits.

        This method should be called before making an API request.
        It will block until the request can be made without exceeding
        rate limits.

        Args:
            weight: Weight of the request (default: 1)
            is_private: Whether this is a private endpoint (default: False)

        Requirements:
            - 4.1: Track IP weights
            - 4.2: Track account weights for private endpoints
            - 4.3: Queue requests to stay within limits
        """
        async with self._lock:
            now = time.monotonic()

            # Check if banned
            if self._banned_until is not None and now < self._banned_until:
                wait_time = self._banned_until - now
                logger.warning(
                    f"Rate limited: waiting {wait_time:.1f}s until ban expires",
                    extra={"wait_time": wait_time, "banned_until": self._banned_until},
                )
                await asyncio.sleep(wait_time)
                now = time.monotonic()
                self._banned_until = None

            # Calculate wait time
            wait_time = self._calculate_wait_time(weight, is_private, now)

            if wait_time > 0:
                logger.debug(
                    f"Rate limit: waiting {wait_time:.3f}s before request",
                    extra={
                        "wait_time": wait_time,
                        "weight": weight,
                        "is_private": is_private,
                        "ip_usage": self.ip_usage,
                        "account_usage": self.account_usage,
                    },
                )
                await asyncio.sleep(wait_time)

    def record_request(self, weight: int = 1, is_private: bool = False) -> None:
        """
        Record a request's weight after it has been made.

        This method should be called after making an API request
        to track the weight for rate limiting purposes.
        Also broadcasts warnings when approaching limits.

        Args:
            weight: Weight of the request (default: 1)
            is_private: Whether this was a private endpoint (default: False)

        Requirements:
            - 4.1: Track IP weights
            - 4.2: Track account weights for private endpoints
            - 4.5: Show warning when approaching limits
        """
        now = time.monotonic()
        record = WeightRecord(timestamp=now, weight=weight)

        # Always record IP weight
        self._ip_weights.append(record)

        # Record account weight for private endpoints
        if is_private:
            self._account_weights.append(record)

        logger.debug(
            f"Recorded request weight: {weight}",
            extra={
                "weight": weight,
                "is_private": is_private,
                "ip_usage": self.ip_usage,
                "account_usage": self.account_usage,
            },
        )

        # Check if approaching limits and broadcast warning
        if self.ip_usage >= 0.8 or self.account_usage >= 0.8:
            try:
                from lib.pionex.rate_limit_broadcast import broadcast_rate_limit_warning

                broadcast_rate_limit_warning(self)
            except ImportError:
                # Broadcast module not available (e.g., in tests)
                pass

    def handle_429(self) -> None:
        """
        Handle a 429 rate limit response.

        Sets a ban timer for 60 seconds and logs the event.
        Also broadcasts a rate limit alert via WebSocket.

        Requirements:
            - 4.4: Wait 60 seconds on 429 response
            - 4.5: Log rate limit events and notify via WebSocket alert
        """
        now = time.monotonic()
        self._banned_until = now + self.ban_duration

        logger.warning(
            f"Rate limited (429): banned for {self.ban_duration}s",
            extra={
                "banned_until": self._banned_until,
                "ban_duration": self.ban_duration,
                "ip_usage": self.ip_usage,
                "account_usage": self.account_usage,
            },
        )

        # Broadcast rate limit error via WebSocket
        try:
            from lib.pionex.rate_limit_broadcast import broadcast_rate_limit_error

            broadcast_rate_limit_error(self)
        except ImportError:
            # Broadcast module not available (e.g., in tests)
            pass

    @property
    def ip_usage(self) -> float:
        """
        Current IP weight usage as a ratio (0-1).

        Returns:
            Current usage ratio (e.g., 0.5 means 50% of limit used)

        Requirements:
            - 4.6: Expose current usage metrics
        """
        now = time.monotonic()
        current_weight = self._get_current_ip_weight(now)
        return min(1.0, current_weight / self.ip_weight_limit)

    @property
    def account_usage(self) -> float:
        """
        Current account weight usage as a ratio (0-1).

        Returns:
            Current usage ratio (e.g., 0.5 means 50% of limit used)

        Requirements:
            - 4.6: Expose current usage metrics
        """
        now = time.monotonic()
        current_weight = self._get_current_account_weight(now)
        return min(1.0, current_weight / self.account_weight_limit)

    @property
    def is_banned(self) -> bool:
        """
        Check if currently banned due to 429 response.

        Returns:
            True if currently banned, False otherwise
        """
        if self._banned_until is None:
            return False
        now = time.monotonic()
        if now >= self._banned_until:
            self._banned_until = None
            return False
        return True

    @property
    def ban_remaining(self) -> float:
        """
        Get remaining ban time in seconds.

        Returns:
            Seconds remaining in ban, or 0 if not banned
        """
        if self._banned_until is None:
            return 0.0
        now = time.monotonic()
        remaining = self._banned_until - now
        if remaining <= 0:
            self._banned_until = None
            return 0.0
        return remaining

    def reset(self) -> None:
        """
        Reset all rate limit tracking.

        Clears all weight records and ban status.
        Useful for testing or when reconnecting.
        """
        self._ip_weights.clear()
        self._account_weights.clear()
        self._banned_until = None
        logger.debug("Rate limiter reset")
