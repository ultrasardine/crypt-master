"""
Unit tests for BotManagementAgent.

Tests the bot lifecycle management including:
- Signal handling (BUY/SELL/HOLD)
- Grid bot creation for range-bound markets
- DCA bot creation for accumulation
- Stopping underperforming bots
- Risk validation for bot creation

Requirements:
- 10.3: Create Grid Bot when favorable conditions
- 10.4: Create DCA Bot when favorable for accumulation
- 10.5: Stop bot when signals turn unfavorable
- 10.8: Flag/auto-stop underperforming bots
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from lib.analysis.confidence import ConfidenceBreakdown, IndicatorScore
from lib.analysis.signal import Signal
from lib.analysis.technical import SignalDirection
from lib.risk import RiskManager, RiskManagerConfig
from lib.simulation import DryRunSimulator


# Import after Django setup
import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from agents.bot_agent import BotManagementAgent, BotAgentConfig
from apps.bots.models import BotType


class TestBotAgentConfig:
    """Tests for BotAgentConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = BotAgentConfig()
        
        assert config.dry_run is True
        assert config.min_confidence_for_bot == 85.0
        assert config.bot_loss_threshold_pct == 0.10
        assert config.auto_stop_underperforming is True
        assert config.max_bots_per_symbol == 2
        assert config.grid_bot_grid_count == 10
        assert config.dca_interval_hours == 24
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = BotAgentConfig(
            dry_run=False,
            min_confidence_for_bot=90.0,
            bot_loss_threshold_pct=0.15,
            max_bots_per_symbol=3,
        )
        
        assert config.dry_run is False
        assert config.min_confidence_for_bot == 90.0
        assert config.bot_loss_threshold_pct == 0.15
        assert config.max_bots_per_symbol == 3


class TestBotTypeSelection:
    """Tests for bot type selection based on market conditions."""
    
    def _create_signal(
        self,
        symbol: str = "BTC_USDT",
        direction: SignalDirection = SignalDirection.BUY,
        confidence: float = 90.0,
        adx_value: float | None = None,
    ) -> Signal:
        """Create a test signal with specified parameters."""
        indicators = []
        
        if adx_value is not None:
            indicators.append(IndicatorScore(
                name="ADX",
                signal=SignalDirection.BUY,
                confidence=70.0,
                weight=0.15,
                value=adx_value,
                data_insufficient=False,
            ))
        
        # Add other required indicators
        indicators.append(IndicatorScore(
            name="RSI",
            signal=direction,
            confidence=80.0,
            weight=0.20,
            value=35.0,
            data_insufficient=False,
        ))
        
        breakdown = ConfidenceBreakdown(
            technical_score=confidence,
            sentiment_score=0.0,
            news_score=0.0,
            alignment_bonus=5.0,
            base_score=confidence,
            final_score=confidence,
            indicators=tuple(indicators),
            agreeing_indicators=2,
            total_indicators=2,
        )
        
        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            timestamp=datetime.now(tz=timezone.utc),
            indicators=tuple(indicators),
            breakdown=breakdown,
            reasoning="Test signal",
            meets_threshold=confidence >= 85.0,
            threshold_used=85.0,
        )
    
    def test_grid_bot_for_range_bound_market(self):
        """Test that Grid bot is selected when ADX < 25 (range-bound)."""
        config = BotAgentConfig(dry_run=True)
        agent = BotManagementAgent(config=config)
        
        # ADX = 20 indicates range-bound market
        signal = self._create_signal(adx_value=20.0)
        
        bot_type = agent._determine_bot_type(signal)
        
        assert bot_type == BotType.GRID
    
    def test_dca_bot_for_trending_market(self):
        """Test that DCA bot is selected when ADX >= 25 (trending)."""
        config = BotAgentConfig(dry_run=True)
        agent = BotManagementAgent(config=config)
        
        # ADX = 30 indicates trending market
        signal = self._create_signal(adx_value=30.0)
        
        bot_type = agent._determine_bot_type(signal)
        
        assert bot_type == BotType.DCA
    
    def test_dca_bot_when_no_adx(self):
        """Test that DCA bot is selected when ADX is not available."""
        config = BotAgentConfig(dry_run=True)
        agent = BotManagementAgent(config=config)
        
        # No ADX indicator
        signal = self._create_signal(adx_value=None)
        
        bot_type = agent._determine_bot_type(signal)
        
        assert bot_type == BotType.DCA


class TestBotInvestmentCalculation:
    """Tests for bot investment amount calculation."""
    
    def _create_signal(
        self,
        confidence: float = 90.0,
    ) -> Signal:
        """Create a test signal."""
        indicators = [
            IndicatorScore(
                name="RSI",
                signal=SignalDirection.BUY,
                confidence=confidence,
                weight=0.20,
                value=35.0,
                data_insufficient=False,
            ),
        ]
        
        breakdown = ConfidenceBreakdown(
            technical_score=confidence,
            sentiment_score=0.0,
            news_score=0.0,
            alignment_bonus=0.0,
            base_score=confidence,
            final_score=confidence,
            indicators=tuple(indicators),
            agreeing_indicators=1,
            total_indicators=1,
        )
        
        return Signal(
            symbol="BTC_USDT",
            direction=SignalDirection.BUY,
            confidence=confidence,
            timestamp=datetime.now(tz=timezone.utc),
            indicators=tuple(indicators),
            breakdown=breakdown,
            reasoning="Test signal",
            meets_threshold=confidence >= 85.0,
            threshold_used=85.0,
        )
    
    @pytest.mark.asyncio
    async def test_investment_scales_with_confidence(self):
        """Test that investment amount scales with signal confidence."""
        config = BotAgentConfig(dry_run=True)
        risk_config = RiskManagerConfig(max_bot_allocation_pct=0.50)
        risk_manager = RiskManager(config=risk_config)
        risk_manager.update_portfolio(Decimal("10000.00"))
        
        agent = BotManagementAgent(config=config, risk_manager=risk_manager)
        
        # High confidence signal
        high_conf_signal = self._create_signal(confidence=95.0)
        high_investment = await agent._calculate_bot_investment(high_conf_signal)
        
        # Lower confidence signal
        low_conf_signal = self._create_signal(confidence=85.0)
        low_investment = await agent._calculate_bot_investment(low_conf_signal)
        
        # Higher confidence should result in larger investment
        assert high_investment > low_investment
    
    @pytest.mark.asyncio
    async def test_zero_investment_when_no_allocation(self):
        """Test that investment is zero when no allocation available."""
        config = BotAgentConfig(dry_run=True)
        risk_config = RiskManagerConfig(max_bot_allocation_pct=0.50)
        risk_manager = RiskManager(config=risk_config)
        risk_manager.update_portfolio(Decimal("10000.00"))
        # Allocate all available
        risk_manager.update_bot_allocation(Decimal("5000.00"))
        
        agent = BotManagementAgent(config=config, risk_manager=risk_manager)
        
        signal = self._create_signal(confidence=90.0)
        investment = await agent._calculate_bot_investment(signal)
        
        assert investment == Decimal("0")


class TestUnderperformingBotDetection:
    """Tests for underperforming bot detection."""
    
    def test_bot_flagged_as_underperforming(self):
        """Test that bots with losses exceeding threshold are flagged."""
        config = BotAgentConfig(
            dry_run=True,
            bot_loss_threshold_pct=0.10,  # 10% loss threshold
        )
        risk_config = RiskManagerConfig(bot_loss_threshold_pct=0.10)
        risk_manager = RiskManager(config=risk_config)
        
        agent = BotManagementAgent(config=config, risk_manager=risk_manager)
        
        # 15% loss exceeds 10% threshold
        assert risk_manager.is_bot_underperforming(-0.15) is True
        
        # 5% loss is within threshold
        assert risk_manager.is_bot_underperforming(-0.05) is False
        
        # Profit is not underperforming
        assert risk_manager.is_bot_underperforming(0.10) is False


class TestTotalBotAllocation:
    """Tests for total bot allocation calculation."""
    
    def test_allocation_from_simulator_only(self):
        """Test that allocation includes simulator bots in dry-run mode."""
        config = BotAgentConfig(dry_run=True)
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        # Create a simulated bot
        simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=Decimal("1000.00"),
        )
        
        # Test simulator allocation directly
        allocation = simulator.get_bot_allocation()
        
        # Should include the simulated bot allocation
        assert allocation == Decimal("1000.00")
    
    def test_simulator_tracks_multiple_bots(self):
        """Test that simulator tracks multiple bot allocations."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        # Create multiple bots
        simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=Decimal("1000.00"),
        )
        simulator.simulate_bot_creation(
            symbol="ETH_USDT",
            bot_type="DCA",
            investment=Decimal("500.00"),
        )
        
        allocation = simulator.get_bot_allocation()
        
        assert allocation == Decimal("1500.00")
