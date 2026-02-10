"""
Unit tests for Pattern Miner module.

Tests the PatternMiner class and PatternMinerConfig dataclass.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from lib.analysis.pattern_miner import PatternCandidate, PatternMiner, PatternMinerConfig


class TestPatternMinerConfig:
    """Tests for PatternMinerConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Test default configuration values."""
        config = PatternMinerConfig()

        assert config.min_sample_size == 30
        assert config.min_hit_rate == 0.55
        assert config.min_avg_pnl == 0.5
        assert config.lookback_days == 90
        assert "regime" in config.feature_keys

    def test_custom_config_values(self) -> None:
        """Test custom configuration values."""
        config = PatternMinerConfig(
            min_sample_size=50,
            min_hit_rate=0.6,
            min_avg_pnl=1.0,
            lookback_days=180,
        )

        assert config.min_sample_size == 50
        assert config.min_hit_rate == 0.6
        assert config.min_avg_pnl == 1.0
        assert config.lookback_days == 180

    def test_invalid_min_sample_size_raises_error(self) -> None:
        """Test that invalid min_sample_size raises ValueError."""
        with pytest.raises(ValueError, match="min_sample_size must be >= 1"):
            PatternMinerConfig(min_sample_size=0)

    def test_invalid_min_hit_rate_raises_error(self) -> None:
        """Test that invalid min_hit_rate raises ValueError."""
        with pytest.raises(ValueError, match="min_hit_rate must be between 0.0 and 1.0"):
            PatternMinerConfig(min_hit_rate=1.5)

        with pytest.raises(ValueError, match="min_hit_rate must be between 0.0 and 1.0"):
            PatternMinerConfig(min_hit_rate=-0.1)

    def test_invalid_lookback_days_raises_error(self) -> None:
        """Test that invalid lookback_days raises ValueError."""
        with pytest.raises(ValueError, match="lookback_days must be >= 1"):
            PatternMinerConfig(lookback_days=0)


class TestPatternCandidate:
    """Tests for PatternCandidate dataclass."""

    def test_pattern_candidate_creation(self) -> None:
        """Test creating a PatternCandidate."""
        candidate = PatternCandidate(
            feature_combination={"regime": "TRENDING_UP"},
            sample_size=100,
            hit_rate=0.65,
            average_pnl=2.5,
        )

        assert candidate.feature_combination == {"regime": "TRENDING_UP"}
        assert candidate.sample_size == 100
        assert candidate.hit_rate == 0.65
        assert candidate.average_pnl == 2.5


class TestPatternMiner:
    """Tests for PatternMiner class."""

    def test_pattern_miner_initialization_default_config(self) -> None:
        """Test PatternMiner initialization with default config."""
        miner = PatternMiner()

        assert miner.config.min_sample_size == 30
        assert miner.config.min_hit_rate == 0.55

    def test_pattern_miner_initialization_custom_config(self) -> None:
        """Test PatternMiner initialization with custom config."""
        config = PatternMinerConfig(min_sample_size=50, min_hit_rate=0.7)
        miner = PatternMiner(config=config)

        assert miner.config.min_sample_size == 50
        assert miner.config.min_hit_rate == 0.7


@pytest.mark.django_db
class TestPatternMinerDiscovery:
    """Tests for PatternMiner.discover_patterns method."""

    def test_discover_patterns_no_data(self) -> None:
        """Test pattern discovery with no historical data."""
        miner = PatternMiner()
        patterns = miner.discover_patterns()

        assert patterns == []

    def test_discover_patterns_dry_run(self) -> None:
        """Test pattern discovery in dry run mode."""
        miner = PatternMiner()
        patterns = miner.discover_patterns(dry_run=True)

        # Should return empty list when no data
        assert patterns == []


@pytest.mark.django_db
class TestPatternMinerWithData:
    """Tests for PatternMiner with sample data."""

    @pytest.fixture
    def setup_test_data(self, db):
        """Set up test data for pattern mining."""
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        from apps.trading.models import Signal, SignalDirection, SignalOutcome
        from django.contrib.auth.models import User

        # Create user
        user = User.objects.create_user(username="testuser", password="testpass")

        # Create trading pair
        pair = TradingPair.objects.create(
            symbol="BTC_USDT",
            base_currency="BTC",
            quote_currency="USDT",
        )

        # Create signals with outcomes
        signals = []
        for i in range(50):
            signal = Signal.objects.create(
                trading_pair=pair,
                direction=SignalDirection.BUY,
                confidence=80.0 + (i % 20),
                indicators={"rsi": 45, "macd": 0.5},
                regime="TRENDING_UP",
                context_scores={
                    "trend_strength_score": 0.7,
                    "risk_regime_score": 0.6,
                    "sentiment_regime_score": 0.65,
                },
            )
            signals.append(signal)

        # Create bot for outcomes
        bot = Bot.objects.create(
            user=user,
            trading_pair=pair,
            pionex_bot_id=f"test_bot_001",
            bot_type=BotType.GRID,
            status=BotStatus.STOPPED,
            invested_amount=Decimal("1000"),
        )

        # Create outcomes - 35 profitable, 15 unprofitable (70% hit rate)
        for i, signal in enumerate(signals):
            is_profitable = i < 35
            SignalOutcome.objects.create(
                signal=signal,
                bot=bot,
                final_pnl=Decimal("50") if is_profitable else Decimal("-30"),
                final_pnl_percent=5.0 if is_profitable else -3.0,
                is_profitable=is_profitable,
                bot_duration_hours=24.0,
            )

        return {
            "user": user,
            "pair": pair,
            "signals": signals,
            "bot": bot,
        }

    def test_discover_patterns_with_data(self, setup_test_data) -> None:
        """Test pattern discovery with sample data."""
        config = PatternMinerConfig(
            min_sample_size=10,
            min_hit_rate=0.5,
            min_avg_pnl=-10.0,  # Allow negative to ensure we find patterns
        )
        miner = PatternMiner(config=config)
        patterns = miner.discover_patterns()

        # Should find at least one pattern for TRENDING_UP regime
        assert len(patterns) >= 1

        # Check pattern properties
        for pattern in patterns:
            assert pattern.sample_size >= config.min_sample_size
            assert pattern.hit_rate >= config.min_hit_rate
            assert pattern.average_pnl >= config.min_avg_pnl
            assert "regime" in pattern.feature_combination

    def test_discover_patterns_dry_run_with_data(self, setup_test_data) -> None:
        """Test pattern discovery dry run with sample data."""
        from apps.trading.models import StrategyPattern

        initial_count = StrategyPattern.objects.count()

        config = PatternMinerConfig(
            min_sample_size=10,
            min_hit_rate=0.5,
            min_avg_pnl=-10.0,
        )
        miner = PatternMiner(config=config)
        patterns = miner.discover_patterns(dry_run=True)

        # Should find patterns but not save them
        assert len(patterns) >= 1

        # Database should not have new patterns
        assert StrategyPattern.objects.count() == initial_count

        # Patterns should not have IDs (not saved)
        for pattern in patterns:
            assert pattern.pk is None

    def test_threshold_filtering(self, setup_test_data) -> None:
        """Test that patterns below thresholds are filtered out."""
        # Use very high thresholds that won't be met
        config = PatternMinerConfig(
            min_sample_size=10,
            min_hit_rate=0.99,  # 99% hit rate - unlikely to be met
            min_avg_pnl=100.0,  # 100% avg P&L - unlikely to be met
        )
        miner = PatternMiner(config=config)
        patterns = miner.discover_patterns()

        # Should not find any patterns with such high thresholds
        assert len(patterns) == 0


@pytest.mark.django_db
class TestStrategyPatternModel:
    """Tests for StrategyPattern model."""

    def test_strategy_pattern_creation(self) -> None:
        """Test creating a StrategyPattern."""
        from apps.trading.models import StrategyPattern

        pattern = StrategyPattern.objects.create(
            feature_combination={"regime": "RISK_ON", "trend_strength_bucket": "high"},
            sample_size=100,
            hit_rate=0.65,
            average_pnl=2.5,
            is_active=True,
        )

        assert pattern.pk is not None
        assert pattern.feature_combination["regime"] == "RISK_ON"
        assert pattern.sample_size == 100
        assert pattern.hit_rate == 0.65
        assert pattern.average_pnl == 2.5
        assert pattern.is_active is True

    def test_strategy_pattern_manager_active(self) -> None:
        """Test StrategyPattern.objects.active() method."""
        from apps.trading.models import StrategyPattern

        # Create active and inactive patterns
        active = StrategyPattern.objects.create(
            feature_combination={"regime": "TRENDING_UP"},
            sample_size=50,
            hit_rate=0.6,
            average_pnl=1.5,
            is_active=True,
        )
        inactive = StrategyPattern.objects.create(
            feature_combination={"regime": "RISK_OFF"},
            sample_size=50,
            hit_rate=0.6,
            average_pnl=1.5,
            is_active=False,
        )

        active_patterns = StrategyPattern.objects.active()

        assert active in active_patterns
        assert inactive not in active_patterns

    def test_strategy_pattern_manager_for_regime(self) -> None:
        """Test StrategyPattern.objects.for_regime() method."""
        from apps.trading.models import StrategyPattern

        # Create patterns for different regimes
        trending_up = StrategyPattern.objects.create(
            feature_combination={"regime": "TRENDING_UP"},
            sample_size=50,
            hit_rate=0.6,
            average_pnl=1.5,
            is_active=True,
        )
        risk_on = StrategyPattern.objects.create(
            feature_combination={"regime": "RISK_ON"},
            sample_size=50,
            hit_rate=0.6,
            average_pnl=1.5,
            is_active=True,
        )

        trending_patterns = StrategyPattern.objects.for_regime("TRENDING_UP")

        assert trending_up in trending_patterns
        assert risk_on not in trending_patterns

    def test_strategy_pattern_str(self) -> None:
        """Test StrategyPattern string representation."""
        from apps.trading.models import StrategyPattern

        pattern = StrategyPattern.objects.create(
            feature_combination={"regime": "RANGE_BOUND"},
            sample_size=100,
            hit_rate=0.65,
            average_pnl=2.5,
            is_active=True,
        )

        str_repr = str(pattern)
        assert "RANGE_BOUND" in str_repr
        assert "65" in str_repr  # hit rate percentage
        assert "2.5" in str_repr  # avg P&L

    def test_strategy_pattern_regime_property(self) -> None:
        """Test StrategyPattern.regime property."""
        from apps.trading.models import StrategyPattern

        pattern = StrategyPattern.objects.create(
            feature_combination={"regime": "TRENDING_DOWN", "other_key": "value"},
            sample_size=50,
            hit_rate=0.6,
            average_pnl=1.5,
            is_active=True,
        )

        assert pattern.regime == "TRENDING_DOWN"
