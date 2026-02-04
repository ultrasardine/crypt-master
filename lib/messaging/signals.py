"""
Redis Pub/Sub for Trading Signals.

This module provides Redis pub/sub functionality for distributing trading
signals between the market analysis agent and bot management agent.

Requirements:
- 5.1: Generate Signal containing direction, confidence_score, supporting_factors
- Publish signals to 'signals' channel for bot-agent consumption
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from lib.analysis.confidence import ConfidenceBreakdown, IndicatorScore
from lib.analysis.signal import Signal
from lib.analysis.technical import SignalDirection

logger = logging.getLogger(__name__)


# Redis channel for publishing signals
SIGNALS_CHANNEL = "signals"


@dataclass
class SignalMessage:
    """
    Message wrapper for signals transmitted via Redis.

    Attributes:
        signal: The trading signal
        published_at: When the message was published
        source: Identifier of the publishing agent
    """

    signal: Signal
    published_at: datetime
    source: str = "market-agent"


def signal_to_json(signal: Signal) -> dict[str, Any]:
    """
    Convert a Signal to a JSON-serializable dictionary.

    Args:
        signal: The signal to convert

    Returns:
        Dictionary representation of the signal

    Requirements:
        - 5.1: Include direction, confidence_score, and supporting_factors
    """
    return {
        "symbol": signal.symbol,
        "direction": signal.direction.value,
        "confidence": signal.confidence,
        "timestamp": signal.timestamp.isoformat(),
        "meets_threshold": signal.meets_threshold,
        "threshold_used": signal.threshold_used,
        "reasoning": signal.reasoning,
        "indicators": [
            {
                "name": ind.name,
                "signal": ind.signal.value,
                "confidence": ind.confidence,
                "weight": ind.weight,
                "value": ind.value,
                "data_insufficient": ind.data_insufficient,
            }
            for ind in signal.indicators
        ],
        "breakdown": {
            "technical_score": signal.breakdown.technical_score,
            "sentiment_score": signal.breakdown.sentiment_score,
            "news_score": signal.breakdown.news_score,
            "alignment_bonus": signal.breakdown.alignment_bonus,
            "base_score": signal.breakdown.base_score,
            "final_score": signal.breakdown.final_score,
            "agreeing_indicators": signal.breakdown.agreeing_indicators,
            "total_indicators": signal.breakdown.total_indicators,
        },
    }


def signal_from_json(data: dict[str, Any]) -> Signal:
    """
    Reconstruct a Signal from a JSON dictionary.

    Args:
        data: Dictionary containing signal data

    Returns:
        Reconstructed Signal object
    """
    # Parse direction
    direction = SignalDirection(data["direction"])

    # Parse timestamp
    timestamp = datetime.fromisoformat(data["timestamp"])

    # Parse indicators
    indicators = tuple(
        IndicatorScore(
            name=ind["name"],
            signal=SignalDirection(ind["signal"]),
            confidence=ind["confidence"],
            weight=ind["weight"],
            value=ind.get("value"),
            data_insufficient=ind.get("data_insufficient", False),
        )
        for ind in data["indicators"]
    )

    # Parse breakdown
    breakdown_data = data["breakdown"]
    breakdown = ConfidenceBreakdown(
        technical_score=breakdown_data["technical_score"],
        sentiment_score=breakdown_data["sentiment_score"],
        news_score=breakdown_data["news_score"],
        alignment_bonus=breakdown_data["alignment_bonus"],
        base_score=breakdown_data["base_score"],
        final_score=breakdown_data["final_score"],
        indicators=indicators,
        agreeing_indicators=breakdown_data["agreeing_indicators"],
        total_indicators=breakdown_data["total_indicators"],
    )

    return Signal(
        symbol=data["symbol"],
        direction=direction,
        confidence=data["confidence"],
        timestamp=timestamp,
        indicators=indicators,
        breakdown=breakdown,
        reasoning=data["reasoning"],
        meets_threshold=data["meets_threshold"],
        threshold_used=data["threshold_used"],
    )


class SignalPublisher:
    """
    Publisher for trading signals via Redis pub/sub.

    Publishes signals to the 'signals' channel for consumption by
    the bot management agent.

    Example:
        >>> async with SignalPublisher(redis_url) as publisher:
        ...     await publisher.publish(signal)
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        source: str = "market-agent",
    ) -> None:
        """
        Initialize the SignalPublisher.

        Args:
            redis_url: Redis connection URL
            source: Identifier for this publisher
        """
        self._redis_url = redis_url
        self._source = source
        self._client: aioredis.Redis | None = None

    async def _ensure_client(self) -> aioredis.Redis:
        """Get or create the Redis client."""
        if self._client is None:
            self._client = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> SignalPublisher:
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def publish(self, signal: Signal) -> int:
        """
        Publish a signal to the signals channel.

        Args:
            signal: The signal to publish

        Returns:
            Number of subscribers that received the message
        """
        client = await self._ensure_client()

        # Create message payload
        payload = {
            "signal": signal_to_json(signal),
            "published_at": datetime.now(tz=UTC).isoformat(),
            "source": self._source,
        }

        # Publish to channel
        num_subscribers = await client.publish(
            SIGNALS_CHANNEL,
            json.dumps(payload),
        )

        logger.debug(f"Published signal for {signal.symbol} to {num_subscribers} subscribers")

        return num_subscribers


class SignalSubscriber:
    """
    Subscriber for trading signals via Redis pub/sub.

    Subscribes to the 'signals' channel and yields signals as they
    are published by the market analysis agent.

    Example:
        >>> async with SignalSubscriber(redis_url) as subscriber:
        ...     async for message in subscriber.listen():
        ...         print(f"Received: {message.signal.symbol}")
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
    ) -> None:
        """
        Initialize the SignalSubscriber.

        Args:
            redis_url: Redis connection URL
        """
        self._redis_url = redis_url
        self._client: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._running = False

    async def _ensure_client(self) -> aioredis.Redis:
        """Get or create the Redis client."""
        if self._client is None:
            self._client = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the Redis connection."""
        self._running = False

        if self._pubsub is not None:
            await self._pubsub.unsubscribe(SIGNALS_CHANNEL)
            await self._pubsub.close()
            self._pubsub = None

        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> SignalSubscriber:
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def listen(self) -> AsyncIterator[SignalMessage]:
        """
        Listen for signals on the signals channel.

        Yields:
            SignalMessage objects as they are received
        """
        client = await self._ensure_client()
        self._pubsub = client.pubsub()

        await self._pubsub.subscribe(SIGNALS_CHANNEL)
        logger.info(f"Subscribed to {SIGNALS_CHANNEL} channel")

        self._running = True

        try:
            while self._running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message is None:
                    continue

                if message["type"] != "message":
                    continue

                try:
                    payload = json.loads(message["data"])
                    signal = signal_from_json(payload["signal"])
                    published_at = datetime.fromisoformat(payload["published_at"])
                    source = payload.get("source", "unknown")

                    yield SignalMessage(
                        signal=signal,
                        published_at=published_at,
                        source=source,
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(f"Failed to parse signal message: {e}")
                    continue
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop listening for signals."""
        self._running = False


async def subscribe_to_signals(
    redis_url: str,
    callback: Callable[[SignalMessage], Any],
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    Convenience function to subscribe to signals with a callback.

    Args:
        redis_url: Redis connection URL
        callback: Async function to call for each signal
        stop_event: Optional event to signal when to stop
    """
    async with SignalSubscriber(redis_url) as subscriber:
        async for message in subscriber.listen():
            if stop_event is not None and stop_event.is_set():
                break

            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Error in signal callback: {e}", exc_info=True)
