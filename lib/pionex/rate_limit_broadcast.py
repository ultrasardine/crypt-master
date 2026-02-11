"""
Rate limit broadcast utilities.

This module provides functions to broadcast rate limit updates
to the dashboard via WebSocket.

Requirements:
    - 4.5: Log rate limit events and notify via WebSocket alert
    - 4.6: Expose current usage metrics via dashboard
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

if TYPE_CHECKING:
    from lib.pionex.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# WebSocket group for dashboard updates
DASHBOARD_GROUP = "dashboard"


def broadcast_rate_limit_update(rate_limiter: RateLimiter) -> None:
    """
    Broadcast rate limit usage update to dashboard WebSocket.

    Args:
        rate_limiter: The RateLimiter instance to get metrics from

    Requirements:
        - 4.6: Expose current usage metrics via dashboard
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.debug("No channel layer available for rate limit broadcast")
            return

        # Calculate status
        ip_usage = rate_limiter.ip_usage
        account_usage = rate_limiter.account_usage
        is_banned = rate_limiter.is_banned
        ban_remaining = rate_limiter.ban_remaining

        if is_banned:
            status = "error"
            status_message = f"Rate limited - {int(ban_remaining)}s remaining"
        elif ip_usage >= 0.8 or account_usage >= 0.8:
            status = "warning"
            status_message = "Approaching rate limits"
        else:
            status = "ok"
            status_message = "API rate limits healthy"

        event = {
            "type": "rate_limit_update",
            "ip_usage": ip_usage,
            "account_usage": account_usage,
            "ip_usage_percent": int(ip_usage * 100),
            "account_usage_percent": int(account_usage * 100),
            "is_banned": is_banned,
            "ban_remaining": ban_remaining,
            "status": status,
            "status_message": status_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async_to_sync(channel_layer.group_send)(DASHBOARD_GROUP, event)
        logger.debug(f"Broadcast rate limit update: {status}")

    except Exception as e:
        logger.warning(f"Failed to broadcast rate limit update: {e}")


def broadcast_rate_limit_alert(
    level: str,
    title: str,
    message: str,
    ban_remaining: float = 0.0,
) -> None:
    """
    Broadcast rate limit alert to dashboard WebSocket.

    Args:
        level: Alert level ("warning" or "error")
        title: Alert title
        message: Alert message
        ban_remaining: Seconds remaining in ban (if rate limited)

    Requirements:
        - 4.5: Log rate limit events and notify via WebSocket alert
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.debug("No channel layer available for rate limit alert")
            return

        event = {
            "type": "rate_limit_alert",
            "level": level,
            "title": title,
            "message": message,
            "ban_remaining": ban_remaining,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async_to_sync(channel_layer.group_send)(DASHBOARD_GROUP, event)
        logger.info(f"Broadcast rate limit alert: {level} - {title}")

    except Exception as e:
        logger.warning(f"Failed to broadcast rate limit alert: {e}")


def broadcast_rate_limit_warning(rate_limiter: RateLimiter) -> None:
    """
    Broadcast a warning alert when approaching rate limits.

    Args:
        rate_limiter: The RateLimiter instance to check

    Requirements:
        - 4.5: Show warning when approaching limits
    """
    ip_usage = rate_limiter.ip_usage
    account_usage = rate_limiter.account_usage

    if ip_usage >= 0.8 or account_usage >= 0.8:
        usage_type = "IP" if ip_usage >= account_usage else "Account"
        usage_percent = max(ip_usage, account_usage) * 100

        broadcast_rate_limit_alert(
            level="warning",
            title="Approaching Rate Limits",
            message=f"{usage_type} usage at {usage_percent:.0f}%. Consider reducing request frequency.",
        )


def broadcast_rate_limit_error(rate_limiter: RateLimiter) -> None:
    """
    Broadcast an error alert when rate limited.

    Args:
        rate_limiter: The RateLimiter instance to check

    Requirements:
        - 4.5: Show error when rate limited
    """
    if rate_limiter.is_banned:
        broadcast_rate_limit_alert(
            level="error",
            title="Rate Limited",
            message=f"API requests blocked for {rate_limiter.ban_remaining:.0f} seconds.",
            ban_remaining=rate_limiter.ban_remaining,
        )
