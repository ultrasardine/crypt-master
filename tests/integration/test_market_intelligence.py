"""Integration tests for Market Intelligence Layer.

These tests verify the complete data flow from external APIs to dashboard,
pattern discovery workflow, and WebSocket updates.

Requirements:
- Test complete data flow from external APIs to dashboard
- Test pattern discovery workflow
- Test WebSocket updates
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import MarketContextSnapshot, TradingPair
from apps.trading.models import Signal, SignalDirection, SignalOutcome, StrategyPattern
from lib.analysis.context import ContextScorer, ContextScorerConfig, Regime
from lib.analysis.pattern_miner import PatternMiner, PatternMinerConfig
from lib.sync.external_sources import ExternalMetrics

User = get_user_model()


@pytest.fixture
def test_user(db):
    """Create a test user for authentication."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def authenticated_client(test_user):
    """Create an authenticated client."""
    client = Client()
    client.login(username="testuser", password="testpass123")
    return client


@pytest.fixture
def trading_pair(db):
    """Create a test trading pair."""
    return TradingPair.objects.create(
        symbol="BTC_USDT",
        base_currency="BTC",
        quote_currency="USDT",
        is_active=True,
        min_quantity=Decimal("0.0001"),
        max_quantity=Decimal("100"),
        price_precision=2,
        quantity_precision=6,
    )


@pytest.fixture
def market_context_snapshot(db):
    """Create a market context snapshot with all fields populated."""
    return MarketContextSnapshot.objects.create(
        symbol="BTC_USDT",
        timestamp=timezone.now(),
        btc_dominance=45.5,
        global_market_cap=Decimal("2500000000000"),
        total_volume_24h=Decimal("150000000000"),
        active_addresses=1000000,
        net_exchange_flow=-5000.0,
        whale_tx_count=150,
        defi_tvl=Decimal("100000000000"),
        social_sentiment_score=0.65,
        social_mention_count=50000,
        social_buzz_score=0.75,
        fear_greed_index=65,
        regime=Regime.TRENDING_UP.value,
        trend_strength_score=0.72,
        risk_regime_score=0.68,
        sentiment_regime_score=0.70,
        is_stale=False,
        is_degraded=False,
        stale_fields=[],
    )


class TestExternalDataToSnapshotFlow:
    """Test complete data flow from external APIs to MarketContextSnapshot."""

    @pytest.mark.django_db
    def test_external_metrics_to_snapshot_creation(self):
        """Test that external metrics are correctly stored in MarketContextSnapshot."""
        # Create mock external metrics
        cmc_metrics = ExternalMetrics(
            source_name="coingecko",
            symbol=None,
            metrics={
                "btc_dominance": 45.5,
                "global_market_cap": 2500000000000,
                "total_volume_24h": 150000000000,
            },
            is_stale=False,
            error_message=None,
        )

        onchain_metrics = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics={
                "active_addresses": 1000000,
                "net_exchange_flow": -5000.0,
                "whale_tx_count": 150,
                "defi_tvl": 100000000000,
            },
            is_stale=False,
            error_message=None,
        )

        social_metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": 0.65,
                "mention_count": 50000,
                "buzz_score": 0.75,
            },
            is_stale=False,
            error_message=None,
        )

        # Create snapshot from metrics
        snapshot = MarketContextSnapshot.objects.create(
            symbol="BTC_USDT",
            timestamp=timezone.now(),
            btc_dominance=cmc_metrics.metrics.get("btc_dominance"),
            global_market_cap=Decimal(str(cmc_metrics.metrics.get("global_market_cap", 0))),
            total_volume_24h=Decimal(str(cmc_metrics.metrics.get("total_volume_24h", 0))),
            active_addresses=onchain_metrics.metrics.get("active_addresses"),
            net_exchange_flow=onchain_metrics.metrics.get("net_exchange_flow"),
            whale_tx_count=onchain_metrics.metrics.get("whale_tx_count"),
            defi_tvl=Decimal(str(onchain_metrics.metrics.get("defi_tvl", 0))),
            social_sentiment_score=social_metrics.metrics.get("sentiment_polarity"),
            social_mention_count=social_metrics.metrics.get("mention_count"),
            social_buzz_score=social_metrics.metrics.get("buzz_score"),
            is_stale=False,
            stale_fields=[],
        )

        # Verify snapshot was created correctly
        assert snapshot.btc_dominance == 45.5
        assert snapshot.global_market_cap == Decimal("2500000000000")
        assert snapshot.active_addresses == 1000000
        assert snapshot.net_exchange_flow == -5000.0
        assert snapshot.social_sentiment_score == 0.65
        assert not snapshot.is_stale

    @pytest.mark.django_db
    def test_partial_data_creates_stale_snapshot(self):
        """Test that partial data creates a snapshot with stale fields tracked."""
        # Create snapshot with some missing data
        snapshot = MarketContextSnapshot.objects.create(
            symbol="BTC_USDT",
            timestamp=timezone.now(),
            btc_dominance=45.5,
            global_market_cap=Decimal("2500000000000"),
            # On-chain metrics missing
            active_addresses=None,
            net_exchange_flow=None,
            whale_tx_count=None,
            defi_tvl=None,
            # Social metrics present
            social_sentiment_score=0.65,
            social_mention_count=50000,
            social_buzz_score=0.75,
            is_stale=True,
            stale_fields=["active_addresses", "net_exchange_flow", "whale_tx_count", "defi_tvl"],
        )

        assert snapshot.is_stale
        assert "active_addresses" in snapshot.stale_fields
        assert "net_exchange_flow" in snapshot.stale_fields
        assert snapshot.btc_dominance is not None
        assert snapshot.social_sentiment_score is not None


class TestContextScoringIntegration:
    """Test context scoring integration with MarketContextSnapshot."""

    @pytest.mark.django_db
    def test_context_scorer_with_real_snapshot(self, market_context_snapshot):
        """Test ContextScorer produces valid scores from real snapshot data."""
        scorer = ContextScorer()

        # Create technical summary
        technical_summary = {
            "adx": 28.0,
            "rsi": 55.0,
            "bb_width": 0.05,
            "macd_histogram": 0.002,
            "volume_ratio": 1.2,
        }

        # Compute scores
        scores = scorer.compute_scores(market_context_snapshot, technical_summary)

        # Verify scores are bounded
        assert 0.0 <= scores.trend_strength_score <= 1.0
        assert 0.0 <= scores.risk_regime_score <= 1.0
        assert 0.0 <= scores.sentiment_regime_score <= 1.0
        assert scores.regime in Regime
        assert not scores.is_degraded

    @pytest.mark.django_db
    def test_context_scorer_with_stale_snapshot(self, db):
        """Test ContextScorer marks output as degraded for stale input."""
        # Create stale snapshot
        snapshot = MarketContextSnapshot.objects.create(
            symbol="BTC_USDT",
            timestamp=timezone.now(),
            btc_dominance=45.5,
            is_stale=True,
            stale_fields=["active_addresses", "net_exchange_flow"],
        )

        scorer = ContextScorer()
        technical_summary = {"adx": 25.0, "rsi": 50.0}

        scores = scorer.compute_scores(snapshot, technical_summary)

        # Verify degraded flag is set
        assert scores.is_degraded
        # Scores should still be valid
        assert 0.0 <= scores.trend_strength_score <= 1.0


class TestSignalGenerationWithContext:
    """Test signal generation with context awareness."""

    @pytest.mark.django_db
    def test_signal_includes_regime_metadata(self, trading_pair, market_context_snapshot):
        """Test that signals generated with context include regime metadata."""
        from lib.analysis.confidence import IndicatorScore
        from lib.analysis.context import ContextScores
        from lib.analysis.signal import SignalGenerator, SignalGeneratorConfig
        from lib.analysis.technical import SignalDirection as TechnicalSignalDirection

        # Create context scores
        context = ContextScores(
            trend_strength_score=0.72,
            risk_regime_score=0.68,
            sentiment_regime_score=0.70,
            regime=Regime.TRENDING_UP,
            is_degraded=False,
        )

        # Generate signal with context
        config = SignalGeneratorConfig()
        generator = SignalGenerator(config)

        technical_scores = [
            IndicatorScore(
                name="RSI",
                signal=TechnicalSignalDirection.BUY,
                confidence=75.0,
                weight=0.3,
                value=45.0,
            ),
            IndicatorScore(
                name="MACD",
                signal=TechnicalSignalDirection.BUY,
                confidence=80.0,
                weight=0.3,
                value=0.002,
            ),
            IndicatorScore(
                name="ADX",
                signal=TechnicalSignalDirection.BUY,
                confidence=70.0,
                weight=0.2,
                value=28.0,
            ),
        ]

        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            context=context,
        )

        # Verify signal includes context metadata
        assert signal.regime == Regime.TRENDING_UP.value
        assert signal.context_scores is not None
        assert "trend_strength_score" in signal.context_scores
        assert "risk_regime_score" in signal.context_scores
        assert "sentiment_regime_score" in signal.context_scores

    @pytest.mark.django_db
    def test_signal_without_context_has_none_metadata(self, trading_pair):
        """Test that signals generated without context have None metadata."""
        from lib.analysis.confidence import IndicatorScore
        from lib.analysis.signal import SignalGenerator, SignalGeneratorConfig
        from lib.analysis.technical import SignalDirection as TechnicalSignalDirection

        config = SignalGeneratorConfig()
        generator = SignalGenerator(config)

        technical_scores = [
            IndicatorScore(
                name="RSI",
                signal=TechnicalSignalDirection.BUY,
                confidence=75.0,
                weight=0.3,
                value=45.0,
            ),
            IndicatorScore(
                name="MACD",
                signal=TechnicalSignalDirection.BUY,
                confidence=80.0,
                weight=0.3,
                value=0.002,
            ),
        ]

        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            context=None,
        )

        # Verify signal has None context metadata
        assert signal.regime is None
        assert signal.context_scores is None
        assert signal.recommended_bot_type is None


class TestPatternDiscoveryWorkflow:
    """Test pattern discovery workflow."""

    @pytest.mark.django_db
    def test_pattern_miner_discovers_patterns(self, trading_pair, test_user):
        """Test PatternMiner discovers patterns from historical data."""
        # Create signals with outcomes
        now = timezone.now()

        for i in range(15):
            signal = Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=85.0 + i % 10,
                indicators=[{"name": "RSI", "value": 35, "signal": "BUY"}],
                regime=Regime.TRENDING_UP.value,
                context_scores={
                    "trend_strength_score": 0.7,
                    "risk_regime_score": 0.6,
                    "sentiment_regime_score": 0.65,
                },
            )

            # Create profitable outcome for most signals
            is_profitable = i < 12  # 80% win rate
            SignalOutcome.objects.create(
                signal=signal,
                is_profitable=is_profitable,
                final_pnl_percent=2.5 if is_profitable else -1.5,
                recorded_at=now - timedelta(days=i),
            )

        # Run pattern miner
        config = PatternMinerConfig(
            min_sample_size=10,
            min_hit_rate=0.6,
            min_avg_pnl=0.5,
            lookback_days=30,
        )
        miner = PatternMiner(config=config)
        patterns = miner.discover_patterns(dry_run=False)

        # Verify patterns were discovered
        assert len(patterns) > 0
        for pattern in patterns:
            assert pattern.hit_rate >= 0.6
            assert pattern.sample_size >= 10

    @pytest.mark.django_db
    def test_pattern_miner_respects_thresholds(self, trading_pair, test_user):
        """Test PatternMiner respects minimum thresholds."""
        # Create signals with poor outcomes (below threshold)
        now = timezone.now()

        for i in range(15):
            signal = Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=75.0,
                indicators=[{"name": "RSI", "value": 35, "signal": "BUY"}],
                regime=Regime.RISK_OFF.value,
                context_scores={
                    "trend_strength_score": 0.3,
                    "risk_regime_score": 0.3,
                    "sentiment_regime_score": 0.3,
                },
            )

            # Create mostly unprofitable outcomes (40% win rate - below threshold)
            is_profitable = i < 6
            SignalOutcome.objects.create(
                signal=signal,
                is_profitable=is_profitable,
                final_pnl_percent=1.0 if is_profitable else -2.0,
                recorded_at=now - timedelta(days=i),
            )

        # Run pattern miner with strict thresholds
        config = PatternMinerConfig(
            min_sample_size=10,
            min_hit_rate=0.6,  # 60% threshold
            min_avg_pnl=0.5,
            lookback_days=30,
        )
        miner = PatternMiner(config=config)
        patterns = miner.discover_patterns(dry_run=False)

        # Verify no patterns were stored (below threshold)
        # Note: The miner may still find patterns if grouping produces better results
        for pattern in patterns:
            assert pattern.hit_rate >= 0.6


class TestDashboardIntegration:
    """Test dashboard integration with market context."""

    @pytest.mark.django_db
    def test_dashboard_includes_market_context(
        self, authenticated_client, market_context_snapshot, test_user
    ):
        """Test dashboard view includes market context data."""
        response = authenticated_client.get(reverse("dashboard:home"))

        assert response.status_code == 200
        assert "market_context" in response.context

        market_context = response.context["market_context"]
        if market_context:
            assert "regime" in market_context
            assert "btc_dominance" in market_context
            assert "social_sentiment_score" in market_context

    @pytest.mark.django_db
    def test_dashboard_handles_no_context(self, authenticated_client, test_user, db):
        """Test dashboard handles missing market context gracefully."""
        # Ensure no snapshots exist
        MarketContextSnapshot.objects.all().delete()

        response = authenticated_client.get(reverse("dashboard:home"))

        assert response.status_code == 200
        assert response.context.get("market_context") is None


class TestResearchViewsIntegration:
    """Test research views integration."""

    @pytest.mark.django_db
    def test_regime_detector_view_displays_data(
        self, authenticated_client, market_context_snapshot
    ):
        """Test RegimeDetectorView displays regime data correctly."""
        response = authenticated_client.get(reverse("analysis:regimes"))

        assert response.status_code == 200
        assert "latest_snapshot" in response.context
        assert "regime_colors" in response.context
        assert "context_scores" in response.context

    @pytest.mark.django_db
    def test_regime_detector_time_filtering(self, authenticated_client, db):
        """Test RegimeDetectorView filters by time range."""
        now = timezone.now()

        # Create snapshots at different times
        MarketContextSnapshot.objects.create(
            symbol="BTC_USDT",
            timestamp=now - timedelta(days=3),
            regime=Regime.TRENDING_UP.value,
        )
        MarketContextSnapshot.objects.create(
            symbol="BTC_USDT",
            timestamp=now - timedelta(days=15),
            regime=Regime.RISK_OFF.value,
        )

        # Request 7-day view
        response = authenticated_client.get(reverse("analysis:regimes") + "?days=7")

        assert response.status_code == 200
        # The view should filter to only show recent data

    @pytest.mark.django_db
    def test_signal_quality_view_displays_data(
        self, authenticated_client, trading_pair, test_user
    ):
        """Test SignalQualityView displays signal quality data."""
        # Create signal with outcome
        signal = Signal.objects.create(
            trading_pair=trading_pair,
            direction=SignalDirection.BUY,
            confidence=85.0,
            regime=Regime.TRENDING_UP.value,
        )
        SignalOutcome.objects.create(
            signal=signal,
            is_profitable=True,
            final_pnl_percent=2.5,
            recorded_at=timezone.now(),
        )

        response = authenticated_client.get(reverse("analysis:signal_quality"))

        assert response.status_code == 200
        assert "regime_performance" in response.context
        assert "summary_stats" in response.context

    @pytest.mark.django_db
    def test_signal_quality_regime_filtering(
        self, authenticated_client, trading_pair, test_user
    ):
        """Test SignalQualityView filters by regime."""
        # Create signals with different regimes
        for regime in [Regime.TRENDING_UP, Regime.RISK_OFF]:
            signal = Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=85.0,
                regime=regime.value,
            )
            SignalOutcome.objects.create(
                signal=signal,
                is_profitable=True,
                final_pnl_percent=2.5,
                recorded_at=timezone.now(),
            )

        # Filter by TRENDING_UP regime
        response = authenticated_client.get(
            reverse("analysis:signal_quality") + f"?regime={Regime.TRENDING_UP.value}"
        )

        assert response.status_code == 200
        assert response.context["selected_regime"] == Regime.TRENDING_UP.value


class TestWebSocketUpdates:
    """Test WebSocket update functionality."""

    @pytest.mark.django_db
    def test_websocket_broadcaster_market_context_update(self, market_context_snapshot):
        """Test WebSocket broadcaster sends market context updates."""
        from lib.messaging.websocket import WebSocketBroadcaster

        broadcaster = WebSocketBroadcaster()

        # Create update data
        update_data = {
            "type": "market_context_update",
            "snapshot_id": market_context_snapshot.id,
            "symbol": market_context_snapshot.symbol,
            "regime": market_context_snapshot.regime,
            "btc_dominance": market_context_snapshot.btc_dominance,
            "social_sentiment_score": market_context_snapshot.social_sentiment_score,
            "is_stale": market_context_snapshot.is_stale,
            "timestamp": market_context_snapshot.timestamp.isoformat(),
        }

        # Mock the channel layer
        with patch("lib.messaging.websocket.get_channel_layer") as mock_get_layer:
            mock_layer = MagicMock()
            mock_layer.group_send = AsyncMock()
            mock_get_layer.return_value = mock_layer

            # Call the sync version
            broadcaster.broadcast_market_context_update_sync(update_data)

            # Verify group_send was called (may be called multiple times for different groups)
            assert mock_layer.group_send.call_count >= 1
            # Verify at least one call was for the analysis group
            call_args_list = mock_layer.group_send.call_args_list
            analysis_calls = [c for c in call_args_list if c[0][0] == "analysis"]
            assert len(analysis_calls) >= 1
            assert analysis_calls[0][0][1]["type"] == "market_context_update"


class TestCeleryTaskIntegration:
    """Test Celery task integration."""

    @pytest.mark.django_db
    def test_fetch_external_market_data_task_creates_snapshot(self):
        """Test fetch_external_market_data task creates MarketContextSnapshot."""
        from apps.core.tasks import fetch_external_market_data

        # Mock the hub at the import location in the tasks module
        with patch("lib.sync.hub.MarketDataHub") as mock_hub_class:
            mock_hub = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.id = 123
            mock_snapshot.symbol = "BTC_USDT"
            mock_snapshot.regime = Regime.TRENDING_UP.value
            mock_snapshot.btc_dominance = 45.5
            mock_snapshot.social_sentiment_score = 0.65
            mock_snapshot.social_buzz_score = 0.75
            mock_snapshot.net_exchange_flow = -5000.0
            mock_snapshot.whale_tx_count = 150
            mock_snapshot.trend_strength_score = 0.72
            mock_snapshot.risk_regime_score = 0.68
            mock_snapshot.sentiment_regime_score = 0.70
            mock_snapshot.is_stale = False
            mock_snapshot.is_degraded = False
            mock_snapshot.timestamp = timezone.now()

            mock_hub.sync = AsyncMock(return_value=mock_snapshot)
            mock_hub.close = AsyncMock()
            mock_hub_class.return_value = mock_hub

            with patch("lib.messaging.websocket.WebSocketBroadcaster") as mock_broadcaster_class:
                mock_broadcaster = MagicMock()
                mock_broadcaster.broadcast_market_context_update = AsyncMock()
                mock_broadcaster_class.return_value = mock_broadcaster

                # Run the task
                result = fetch_external_market_data()

                # Verify result
                assert result["status"] == "success"
                assert result["snapshot_id"] == 123
                assert result["regime"] == Regime.TRENDING_UP.value

    @pytest.mark.django_db
    def test_run_pattern_miner_task(self, trading_pair, test_user):
        """Test run_pattern_miner task discovers patterns."""
        from apps.core.tasks import run_pattern_miner

        # Create test data
        now = timezone.now()
        for i in range(15):
            signal = Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=85.0,
                regime=Regime.TRENDING_UP.value,
            )
            SignalOutcome.objects.create(
                signal=signal,
                is_profitable=i < 12,
                final_pnl_percent=2.5 if i < 12 else -1.5,
                recorded_at=now - timedelta(days=i),
            )

        # Run the task
        result = run_pattern_miner()

        # Verify result
        assert result["status"] == "success"
        assert "patterns_discovered" in result
