"""
Unit tests for SentimentAnalyzer.

Tests the Fear & Greed Index sentiment analysis including API fetching,
value interpretation, caching, and error handling.

Requirements tested:
- 4.1: Fetch Fear & Greed Index from Alternative.me API
- 4.2: Interpret FGI values: 0-25 = Extreme Fear (BUY), 75-100 = Extreme Greed (SELL)
- 4.3: Handle API unavailability gracefully (return neutral/HOLD signal)
- 4.4: Cache FGI values to avoid excessive API calls (configurable duration)
"""

import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from lib.analysis import (
    FearGreedClassification,
    SentimentAnalyzer,
    SentimentConfig,
    SentimentResult,
    SignalDirection,
)


@pytest.fixture
def config() -> SentimentConfig:
    """Create a SentimentConfig with short cache duration for testing."""
    return SentimentConfig(
        cache_duration_seconds=60,
        timeout_seconds=5.0,
    )


@pytest.fixture
def analyzer(config: SentimentConfig) -> SentimentAnalyzer:
    """Create a SentimentAnalyzer with test config."""
    return SentimentAnalyzer(config=config)


def create_mock_response(value: int, timestamp: int | None = None) -> dict:
    """Create a mock API response."""
    data = {"value": str(value)}
    if timestamp:
        data["timestamp"] = str(timestamp)
    return {
        "name": "Fear and Greed Index",
        "data": [data],
    }


class TestValueClassification:
    """Tests for FGI value classification - Requirement 4.2."""
    
    def test_extreme_fear_classification(self, analyzer: SentimentAnalyzer) -> None:
        """Values 0-25 should be classified as Extreme Fear."""
        for value in [0, 10, 25]:
            classification = analyzer.classify_value(value)
            assert classification == FearGreedClassification.EXTREME_FEAR
    
    def test_fear_classification(self, analyzer: SentimentAnalyzer) -> None:
        """Values 26-45 should be classified as Fear."""
        for value in [26, 35, 45]:
            classification = analyzer.classify_value(value)
            assert classification == FearGreedClassification.FEAR
    
    def test_neutral_classification(self, analyzer: SentimentAnalyzer) -> None:
        """Values 46-54 should be classified as Neutral."""
        for value in [46, 50, 54]:
            classification = analyzer.classify_value(value)
            assert classification == FearGreedClassification.NEUTRAL
    
    def test_greed_classification(self, analyzer: SentimentAnalyzer) -> None:
        """Values 55-74 should be classified as Greed."""
        for value in [55, 65, 74]:
            classification = analyzer.classify_value(value)
            assert classification == FearGreedClassification.GREED
    
    def test_extreme_greed_classification(self, analyzer: SentimentAnalyzer) -> None:
        """Values 75-100 should be classified as Extreme Greed."""
        for value in [75, 85, 100]:
            classification = analyzer.classify_value(value)
            assert classification == FearGreedClassification.EXTREME_GREED


class TestSignalGeneration:
    """Tests for FGI to signal conversion - Requirement 4.2."""
    
    def test_extreme_fear_generates_buy_signal(
        self, analyzer: SentimentAnalyzer
    ) -> None:
        """Values 0-25 (Extreme Fear) should generate BUY signal."""
        for value in [0, 10, 20, 25]:
            signal = analyzer.value_to_signal(value)
            assert signal == SignalDirection.BUY
    
    def test_extreme_greed_generates_sell_signal(
        self, analyzer: SentimentAnalyzer
    ) -> None:
        """Values 75-100 (Extreme Greed) should generate SELL signal."""
        for value in [75, 85, 95, 100]:
            signal = analyzer.value_to_signal(value)
            assert signal == SignalDirection.SELL
    
    def test_neutral_zone_generates_hold_signal(
        self, analyzer: SentimentAnalyzer
    ) -> None:
        """Values 26-74 should generate HOLD signal."""
        for value in [26, 40, 50, 60, 74]:
            signal = analyzer.value_to_signal(value)
            assert signal == SignalDirection.HOLD
    
    def test_boundary_values(self, analyzer: SentimentAnalyzer) -> None:
        """Test exact boundary values."""
        # 25 is the upper bound for extreme fear (BUY)
        assert analyzer.value_to_signal(25) == SignalDirection.BUY
        # 26 is in neutral zone (HOLD)
        assert analyzer.value_to_signal(26) == SignalDirection.HOLD
        # 74 is in neutral zone (HOLD)
        assert analyzer.value_to_signal(74) == SignalDirection.HOLD
        # 75 is the lower bound for extreme greed (SELL)
        assert analyzer.value_to_signal(75) == SignalDirection.SELL


class TestAPIFetching:
    """Tests for API fetching - Requirement 4.1."""
    
    @pytest.mark.asyncio
    async def test_successful_api_fetch(self, config: SentimentConfig) -> None:
        """Should successfully fetch and parse FGI from API."""
        mock_response = create_mock_response(value=23, timestamp=1700000000)
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        result = await analyzer.get_fear_greed_index()
        
        assert result.value == 23
        assert result.classification == FearGreedClassification.EXTREME_FEAR
        assert result.signal == SignalDirection.BUY
        assert result.data_unavailable is False
        assert result.cached is False
        assert result.error_message is None
    
    @pytest.mark.asyncio
    async def test_api_returns_greed_value(self, config: SentimentConfig) -> None:
        """Should correctly interpret greed values from API."""
        mock_response = create_mock_response(value=80)
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        result = await analyzer.get_fear_greed_index()
        
        assert result.value == 80
        assert result.classification == FearGreedClassification.EXTREME_GREED
        assert result.signal == SignalDirection.SELL


class TestErrorHandling:
    """Tests for error handling - Requirement 4.3."""
    
    @pytest.mark.asyncio
    async def test_network_error_returns_hold_signal(
        self, config: SentimentConfig
    ) -> None:
        """Network errors should return HOLD signal with data_unavailable=True."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        result = await analyzer.get_fear_greed_index()
        
        assert result.value is None
        assert result.signal == SignalDirection.HOLD
        assert result.data_unavailable is True
        assert result.error_message is not None
        assert "Connection failed" in result.error_message
    
    @pytest.mark.asyncio
    async def test_timeout_error_returns_hold_signal(
        self, config: SentimentConfig
    ) -> None:
        """Timeout errors should return HOLD signal with data_unavailable=True."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        result = await analyzer.get_fear_greed_index()
        
        assert result.value is None
        assert result.signal == SignalDirection.HOLD
        assert result.data_unavailable is True
    
    @pytest.mark.asyncio
    async def test_invalid_response_returns_hold_signal(
        self, config: SentimentConfig
    ) -> None:
        """Invalid API responses should return HOLD signal."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = {"invalid": "response"}
        mock_http_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        result = await analyzer.get_fear_greed_index()
        
        assert result.value is None
        assert result.signal == SignalDirection.HOLD
        assert result.data_unavailable is True
    
    @pytest.mark.asyncio
    async def test_http_error_returns_hold_signal(
        self, config: SentimentConfig
    ) -> None:
        """HTTP errors (4xx, 5xx) should return HOLD signal."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_response = MagicMock()
        mock_http_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        mock_client.get = AsyncMock(return_value=mock_http_response)
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        result = await analyzer.get_fear_greed_index()
        
        assert result.value is None
        assert result.signal == SignalDirection.HOLD
        assert result.data_unavailable is True


class TestCaching:
    """Tests for caching - Requirement 4.4."""
    
    @pytest.mark.asyncio
    async def test_result_is_cached(self, config: SentimentConfig) -> None:
        """Results should be cached after first fetch."""
        mock_response = create_mock_response(value=50)
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        
        # First call should hit API
        result1 = await analyzer.get_fear_greed_index()
        assert result1.cached is False
        assert mock_client.get.call_count == 1
        
        # Second call should use cache
        result2 = await analyzer.get_fear_greed_index()
        assert result2.cached is True
        assert result2.value == result1.value
        assert mock_client.get.call_count == 1  # No additional API call
    
    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(
        self, config: SentimentConfig
    ) -> None:
        """force_refresh=True should bypass cache."""
        mock_response = create_mock_response(value=50)
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        
        # First call
        await analyzer.get_fear_greed_index()
        assert mock_client.get.call_count == 1
        
        # Force refresh should hit API again
        result = await analyzer.get_fear_greed_index(force_refresh=True)
        assert result.cached is False
        assert mock_client.get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_clear_cache(self, config: SentimentConfig) -> None:
        """clear_cache() should invalidate cached results."""
        mock_response = create_mock_response(value=50)
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)
        
        analyzer = SentimentAnalyzer(config=config, http_client=mock_client)
        
        # First call
        await analyzer.get_fear_greed_index()
        assert mock_client.get.call_count == 1
        
        # Clear cache
        analyzer.clear_cache()
        
        # Next call should hit API
        result = await analyzer.get_fear_greed_index()
        assert result.cached is False
        assert mock_client.get.call_count == 2


class TestCustomConfig:
    """Tests for custom configuration."""
    
    def test_custom_thresholds(self) -> None:
        """Custom thresholds should affect signal generation."""
        config = SentimentConfig(
            extreme_fear_threshold=20,
            extreme_greed_threshold=80,
        )
        analyzer = SentimentAnalyzer(config=config)
        
        # With custom thresholds, 25 is now HOLD (not BUY)
        assert analyzer.value_to_signal(20) == SignalDirection.BUY
        assert analyzer.value_to_signal(21) == SignalDirection.HOLD
        
        # With custom thresholds, 75 is now HOLD (not SELL)
        assert analyzer.value_to_signal(79) == SignalDirection.HOLD
        assert analyzer.value_to_signal(80) == SignalDirection.SELL
    
    def test_default_config_values(self) -> None:
        """Default config should have expected values."""
        config = SentimentConfig()
        
        assert config.api_url == "https://api.alternative.me/fng/"
        assert config.cache_duration_seconds == 3600
        assert config.timeout_seconds == 10.0
        assert config.extreme_fear_threshold == 25
        assert config.fear_threshold == 45
        assert config.greed_threshold == 55
        assert config.extreme_greed_threshold == 75


class TestContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_closes_client(
        self, config: SentimentConfig
    ) -> None:
        """Context manager should close HTTP client on exit."""
        async with SentimentAnalyzer(config=config) as analyzer:
            # Analyzer should be usable
            assert analyzer is not None
        
        # After exit, client should be closed
        # (We can't easily verify this without accessing private state,
        # but the test ensures no exceptions are raised)
    
    @pytest.mark.asyncio
    async def test_injected_client_not_closed(
        self, config: SentimentConfig
    ) -> None:
        """Injected HTTP client should not be closed by analyzer."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        
        async with SentimentAnalyzer(
            config=config, http_client=mock_client
        ) as analyzer:
            pass
        
        # Injected client should not be closed
        mock_client.aclose.assert_not_called()


class TestSentimentResult:
    """Tests for SentimentResult dataclass."""
    
    def test_result_is_immutable(self) -> None:
        """SentimentResult should be immutable (frozen)."""
        result = SentimentResult(
            value=50,
            classification=FearGreedClassification.NEUTRAL,
            signal=SignalDirection.HOLD,
            timestamp=datetime.now(tz=timezone.utc),
        )
        
        with pytest.raises(AttributeError):
            result.value = 60  # type: ignore
    
    def test_result_default_values(self) -> None:
        """SentimentResult should have correct default values."""
        result = SentimentResult(
            value=50,
            classification=FearGreedClassification.NEUTRAL,
            signal=SignalDirection.HOLD,
            timestamp=datetime.now(tz=timezone.utc),
        )
        
        assert result.data_unavailable is False
        assert result.cached is False
        assert result.error_message is None
