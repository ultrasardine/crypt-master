"""
Unit tests for Redis signal pub/sub messaging.

Tests the signal serialization, publishing, and subscribing functionality.

Requirements tested:
- 5.1: Generate Signal containing direction, confidence_score, supporting_factors
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.analysis.confidence import ConfidenceBreakdown, IndicatorScore
from lib.analysis.signal import Signal
from lib.analysis.technical import SignalDirection
from lib.messaging.signals import (
    SIGNALS_CHANNEL,
    SignalMessage,
    SignalPublisher,
    SignalSubscriber,
    signal_from_json,
    signal_to_json,
)


@pytest.fixture
def sample_indicators():
    """Create sample indicator scores."""
    return (
        IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.2, 35.0, False),
        IndicatorScore("MACD", SignalDirection.BUY, 75.0, 0.2, 0.5, False),
        IndicatorScore("FGI", SignalDirection.BUY, 70.0, 1.0, 25.0, False),
    )


@pytest.fixture
def sample_breakdown(sample_indicators):
    """Create a sample confidence breakdown."""
    return ConfidenceBreakdown(
        technical_score=48.0,
        sentiment_score=21.0,
        news_score=0.0,
        alignment_bonus=10.0,
        base_score=69.0,
        final_score=79.0,
        indicators=sample_indicators,
        agreeing_indicators=3,
        total_indicators=3,
    )


@pytest.fixture
def sample_signal(sample_indicators, sample_breakdown):
    """Create a sample signal for testing."""
    return Signal(
        symbol="BTC_USDT",
        direction=SignalDirection.BUY,
        confidence=79.0,
        timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        indicators=sample_indicators,
        breakdown=sample_breakdown,
        reasoning="BUY signal with 79.0% confidence",
        meets_threshold=False,
        threshold_used=85.0,
    )


class TestSignalSerialization:
    """Tests for signal JSON serialization."""

    def test_signal_to_json_contains_all_fields(self, sample_signal):
        """signal_to_json should include all required fields."""
        json_data = signal_to_json(sample_signal)

        assert "symbol" in json_data
        assert "direction" in json_data
        assert "confidence" in json_data
        assert "timestamp" in json_data
        assert "meets_threshold" in json_data
        assert "threshold_used" in json_data
        assert "reasoning" in json_data
        assert "indicators" in json_data
        assert "breakdown" in json_data

    def test_signal_to_json_values(self, sample_signal):
        """signal_to_json should have correct values."""
        json_data = signal_to_json(sample_signal)

        assert json_data["symbol"] == "BTC_USDT"
        assert json_data["direction"] == "BUY"
        assert json_data["confidence"] == 79.0
        assert json_data["meets_threshold"] is False
        assert json_data["threshold_used"] == 85.0

    def test_signal_to_json_indicators(self, sample_signal):
        """signal_to_json should include indicator details."""
        json_data = signal_to_json(sample_signal)

        assert len(json_data["indicators"]) == 3

        rsi = json_data["indicators"][0]
        assert rsi["name"] == "RSI"
        assert rsi["signal"] == "BUY"
        assert rsi["confidence"] == 80.0
        assert rsi["weight"] == 0.2
        assert rsi["value"] == 35.0
        assert rsi["data_insufficient"] is False

    def test_signal_to_json_breakdown(self, sample_signal):
        """signal_to_json should include breakdown details."""
        json_data = signal_to_json(sample_signal)

        breakdown = json_data["breakdown"]
        assert breakdown["technical_score"] == 48.0
        assert breakdown["sentiment_score"] == 21.0
        assert breakdown["news_score"] == 0.0
        assert breakdown["alignment_bonus"] == 10.0
        assert breakdown["base_score"] == 69.0
        assert breakdown["final_score"] == 79.0
        assert breakdown["agreeing_indicators"] == 3
        assert breakdown["total_indicators"] == 3

    def test_signal_to_json_is_json_serializable(self, sample_signal):
        """signal_to_json output should be JSON serializable."""
        json_data = signal_to_json(sample_signal)

        # Should not raise
        serialized = json.dumps(json_data)
        assert isinstance(serialized, str)


class TestSignalDeserialization:
    """Tests for signal JSON deserialization."""

    def test_signal_from_json_roundtrip(self, sample_signal):
        """signal_from_json should reconstruct the original signal."""
        json_data = signal_to_json(sample_signal)
        reconstructed = signal_from_json(json_data)

        assert reconstructed.symbol == sample_signal.symbol
        assert reconstructed.direction == sample_signal.direction
        assert reconstructed.confidence == sample_signal.confidence
        assert reconstructed.meets_threshold == sample_signal.meets_threshold
        assert reconstructed.threshold_used == sample_signal.threshold_used
        assert reconstructed.reasoning == sample_signal.reasoning

    def test_signal_from_json_indicators(self, sample_signal):
        """signal_from_json should reconstruct indicators."""
        json_data = signal_to_json(sample_signal)
        reconstructed = signal_from_json(json_data)

        assert len(reconstructed.indicators) == len(sample_signal.indicators)

        for orig, recon in zip(sample_signal.indicators, reconstructed.indicators):
            assert recon.name == orig.name
            assert recon.signal == orig.signal
            assert recon.confidence == orig.confidence
            assert recon.weight == orig.weight
            assert recon.value == orig.value

    def test_signal_from_json_breakdown(self, sample_signal):
        """signal_from_json should reconstruct breakdown."""
        json_data = signal_to_json(sample_signal)
        reconstructed = signal_from_json(json_data)

        assert reconstructed.breakdown.technical_score == sample_signal.breakdown.technical_score
        assert reconstructed.breakdown.sentiment_score == sample_signal.breakdown.sentiment_score
        assert reconstructed.breakdown.alignment_bonus == sample_signal.breakdown.alignment_bonus
        assert reconstructed.breakdown.final_score == sample_signal.breakdown.final_score

    def test_signal_from_json_timestamp(self, sample_signal):
        """signal_from_json should reconstruct timestamp."""
        json_data = signal_to_json(sample_signal)
        reconstructed = signal_from_json(json_data)

        assert reconstructed.timestamp == sample_signal.timestamp

    def test_signal_from_json_direction_buy(self, sample_signal):
        """signal_from_json should handle BUY direction."""
        json_data = signal_to_json(sample_signal)
        json_data["direction"] = "BUY"

        reconstructed = signal_from_json(json_data)
        assert reconstructed.direction == SignalDirection.BUY

    def test_signal_from_json_direction_sell(self, sample_signal):
        """signal_from_json should handle SELL direction."""
        json_data = signal_to_json(sample_signal)
        json_data["direction"] = "SELL"

        reconstructed = signal_from_json(json_data)
        assert reconstructed.direction == SignalDirection.SELL

    def test_signal_from_json_direction_hold(self, sample_signal):
        """signal_from_json should handle HOLD direction."""
        json_data = signal_to_json(sample_signal)
        json_data["direction"] = "HOLD"

        reconstructed = signal_from_json(json_data)
        assert reconstructed.direction == SignalDirection.HOLD


class TestSignalPublisher:
    """Tests for SignalPublisher."""

    @pytest.mark.asyncio
    async def test_publish_calls_redis(self, sample_signal):
        """publish should call Redis publish."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=1)

        publisher = SignalPublisher()
        publisher._client = mock_redis

        result = await publisher.publish(sample_signal)

        assert result == 1
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_uses_correct_channel(self, sample_signal):
        """publish should use the signals channel."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=1)

        publisher = SignalPublisher()
        publisher._client = mock_redis

        await publisher.publish(sample_signal)

        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == SIGNALS_CHANNEL

    @pytest.mark.asyncio
    async def test_publish_payload_contains_signal(self, sample_signal):
        """publish payload should contain the signal data."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=1)

        publisher = SignalPublisher()
        publisher._client = mock_redis

        await publisher.publish(sample_signal)

        call_args = mock_redis.publish.call_args
        payload = json.loads(call_args[0][1])

        assert "signal" in payload
        assert payload["signal"]["symbol"] == "BTC_USDT"
        assert payload["signal"]["direction"] == "BUY"

    @pytest.mark.asyncio
    async def test_publish_payload_contains_metadata(self, sample_signal):
        """publish payload should contain metadata."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=1)

        publisher = SignalPublisher(source="test-agent")
        publisher._client = mock_redis

        await publisher.publish(sample_signal)

        call_args = mock_redis.publish.call_args
        payload = json.loads(call_args[0][1])

        assert "published_at" in payload
        assert "source" in payload
        assert payload["source"] == "test-agent"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """SignalPublisher should work as context manager."""
        with patch("lib.messaging.signals.aioredis") as mock_aioredis:
            mock_client = AsyncMock()
            mock_aioredis.from_url.return_value = mock_client

            async with SignalPublisher() as publisher:
                assert publisher._client is not None

            mock_client.close.assert_called_once()


class TestSignalSubscriber:
    """Tests for SignalSubscriber."""

    @pytest.mark.asyncio
    async def test_subscribe_to_channel(self):
        """SignalSubscriber should subscribe to signals channel."""
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        # Make get_message return None once, then stop the subscriber
        call_count = 0

        async def mock_get_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                subscriber.stop()
            return None

        mock_pubsub.get_message = mock_get_message

        mock_redis = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        subscriber = SignalSubscriber()
        subscriber._client = mock_redis

        # Listen - will stop after 2 get_message calls
        async for _ in subscriber.listen():
            break

        mock_pubsub.subscribe.assert_called_once_with(SIGNALS_CHANNEL)

    @pytest.mark.asyncio
    async def test_stop_stops_listening(self):
        """stop() should stop the listener."""
        subscriber = SignalSubscriber()
        subscriber._running = True

        subscriber.stop()

        assert subscriber._running is False


class TestSignalMessage:
    """Tests for SignalMessage dataclass."""

    def test_signal_message_creation(self, sample_signal):
        """SignalMessage should be created with all fields."""
        now = datetime.now(tz=UTC)

        message = SignalMessage(
            signal=sample_signal,
            published_at=now,
            source="test-agent",
        )

        assert message.signal == sample_signal
        assert message.published_at == now
        assert message.source == "test-agent"

    def test_signal_message_default_source(self, sample_signal):
        """SignalMessage should have default source."""
        now = datetime.now(tz=UTC)

        message = SignalMessage(
            signal=sample_signal,
            published_at=now,
        )

        assert message.source == "market-agent"


class TestChannelConstant:
    """Tests for channel constant."""

    def test_signals_channel_value(self):
        """SIGNALS_CHANNEL should be 'signals'."""
        assert SIGNALS_CHANNEL == "signals"
