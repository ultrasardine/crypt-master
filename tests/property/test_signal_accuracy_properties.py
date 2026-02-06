"""
Property-based tests for Signal Accuracy Tracking.

Feature: dashboard-integration
Property 5: Signal Outcome Recording
Property 6: Accuracy Calculation
Property 7: Confidence Correlation Calculation

These tests use the hypothesis library to verify that the signal accuracy tracker
behaves correctly across all valid inputs.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.7**
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from lib.analysis.accuracy import SignalAccuracyTracker

# =============================================================================
# Custom Strategies for Signal Accuracy Testing
# =============================================================================

# Strategy for P&L values (can be positive or negative)
pnl_strategy = st.decimals(
    min_value=Decimal("-10000.00"),
    max_value=Decimal("10000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

# Strategy for positive invested amounts
invested_strategy = st.decimals(
    min_value=Decimal("10.00"),
    max_value=Decimal("10000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

# Strategy for confidence scores (0-100)
confidence_strategy = st.floats(
    min_value=0.0,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for signal directions
direction_strategy = st.sampled_from(["BUY", "SELL", "HOLD"])


@st.composite
def signal_outcome_data_strategy(draw: st.DrawFn) -> dict:
    """Generate mock signal outcome data for testing."""
    invested = draw(invested_strategy)
    pnl = draw(pnl_strategy)
    confidence = draw(confidence_strategy)
    direction = draw(direction_strategy)
    
    # Calculate P&L percent
    pnl_percent = float((pnl / invested) * 100) if invested > 0 else 0.0
    is_profitable = pnl > 0
    
    return {
        "invested": invested,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "is_profitable": is_profitable,
        "confidence": confidence,
        "direction": direction,
    }


# =============================================================================
# Property 5: Signal Outcome Recording
# =============================================================================


class TestSignalOutcomeRecording:
    """
    Property 5: Signal Outcome Recording

    *For any* stopped bot that has a triggering signal, a SignalOutcome record
    SHALL be created with:
    - is_profitable = (final_pnl > 0)
    - final_pnl matching the bot's final P&L
    - bot_duration_hours calculated from bot creation to stop time

    **Validates: Requirements 3.1**
    """

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        invested=invested_strategy,
        pnl=pnl_strategy,
        confidence=confidence_strategy,
    )
    def test_outcome_profitability_matches_pnl_sign(
        self,
        invested: Decimal,
        pnl: Decimal,
        confidence: float,
        django_user_model,
    ) -> None:
        """
        Property: is_profitable SHALL equal (final_pnl > 0).

        **Validates: Requirements 3.1**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        from apps.trading.models import Signal, SignalDirection
        
        # Create test user
        user = django_user_model.objects.create_user(
            username=f"test_outcome_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Create trading pair
            trading_pair, _ = TradingPair.objects.get_or_create(
                symbol="BTC_USDT",
                defaults={
                    "base_currency": "BTC",
                    "quote_currency": "USDT",
                    "is_active": True,
                },
            )
            
            # Create signal
            signal = Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=confidence,
                indicators={},
                executed=True,
                executed_at=timezone.now(),
            )
            
            # Create bot
            created_at = timezone.now() - timedelta(hours=24)
            stopped_at = timezone.now()
            
            bot = Bot.objects.create(
                user=user,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:12]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.STOPPED,
                invested_amount=invested,
                current_value=invested + pnl,
                current_pnl=pnl,
                pnl_percent=float((pnl / invested) * 100) if invested > 0 else 0.0,
                params={},
                is_simulated=False,
                triggered_by_signal=signal,
                stopped_at=stopped_at,
            )
            bot.created_at = created_at
            bot.save()
            
            # Record outcome
            tracker = SignalAccuracyTracker()
            outcome = tracker.record_outcome(signal, bot, pnl)
            
            # Verify is_profitable matches pnl sign
            expected_profitable = pnl > 0
            assert outcome.is_profitable == expected_profitable, (
                f"is_profitable should be {expected_profitable} for pnl={pnl}, "
                f"got {outcome.is_profitable}"
            )
            
            # Verify final_pnl matches
            assert outcome.final_pnl == pnl, (
                f"final_pnl should be {pnl}, got {outcome.final_pnl}"
            )
        finally:
            user.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        invested=invested_strategy,
        pnl=pnl_strategy,
        duration_hours=st.floats(min_value=0.1, max_value=720.0, allow_nan=False, allow_infinity=False),
    )
    def test_outcome_duration_calculation(
        self,
        invested: Decimal,
        pnl: Decimal,
        duration_hours: float,
        django_user_model,
    ) -> None:
        """
        Property: bot_duration_hours SHALL be calculated from bot creation to stop time.

        **Validates: Requirements 3.1**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        from apps.trading.models import Signal, SignalDirection
        
        # Create test user
        user = django_user_model.objects.create_user(
            username=f"test_duration_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Create trading pair
            trading_pair, _ = TradingPair.objects.get_or_create(
                symbol="BTC_USDT",
                defaults={
                    "base_currency": "BTC",
                    "quote_currency": "USDT",
                    "is_active": True,
                },
            )
            
            # Create signal
            signal = Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=75.0,
                indicators={},
                executed=True,
                executed_at=timezone.now(),
            )
            
            # Create bot with specific duration
            stopped_at = timezone.now()
            created_at = stopped_at - timedelta(hours=duration_hours)
            
            bot = Bot.objects.create(
                user=user,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:12]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.STOPPED,
                invested_amount=invested,
                current_value=invested + pnl,
                current_pnl=pnl,
                pnl_percent=float((pnl / invested) * 100) if invested > 0 else 0.0,
                params={},
                is_simulated=False,
                triggered_by_signal=signal,
                stopped_at=stopped_at,
            )
            bot.created_at = created_at
            bot.save()
            
            # Record outcome
            tracker = SignalAccuracyTracker()
            outcome = tracker.record_outcome(signal, bot, pnl)
            
            # Verify duration calculation (allow small tolerance for floating point)
            assert outcome.bot_duration_hours == pytest.approx(duration_hours, rel=1e-3), (
                f"bot_duration_hours should be {duration_hours}, got {outcome.bot_duration_hours}"
            )
        finally:
            user.delete()


# =============================================================================
# Property 6: Accuracy Calculation
# =============================================================================


class TestAccuracyCalculation:
    """
    Property 6: Accuracy Calculation

    *For any* set of SignalOutcome records for a user:
    - overall_accuracy SHALL equal (profitable_count / total_executed_count) * 100
    - buy_accuracy SHALL equal (profitable_buy_count / total_buy_count) * 100
    - sell_accuracy SHALL equal (profitable_sell_count / total_sell_count) * 100
    - Only signals with executed=True SHALL be included in calculations

    **Validates: Requirements 3.2, 3.3, 3.7**
    """

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        outcomes=st.lists(signal_outcome_data_strategy(), min_size=1, max_size=50),
    )
    def test_overall_accuracy_formula(
        self,
        outcomes: list[dict],
        django_user_model,
    ) -> None:
        """
        Property: overall_accuracy SHALL equal (profitable_count / total_count) * 100.

        **Validates: Requirements 3.2, 3.7**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        from apps.trading.models import Signal, SignalDirection, SignalOutcome
        
        # Create test user
        user = django_user_model.objects.create_user(
            username=f"test_accuracy_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Create trading pair
            trading_pair, _ = TradingPair.objects.get_or_create(
                symbol="BTC_USDT",
                defaults={
                    "base_currency": "BTC",
                    "quote_currency": "USDT",
                    "is_active": True,
                },
            )
            
            # Create signals and outcomes
            for outcome_data in outcomes:
                # Create signal
                direction_map = {
                    "BUY": SignalDirection.BUY,
                    "SELL": SignalDirection.SELL,
                    "HOLD": SignalDirection.HOLD,
                }
                signal = Signal.objects.create(
                    trading_pair=trading_pair,
                    direction=direction_map[outcome_data["direction"]],
                    confidence=outcome_data["confidence"],
                    indicators={},
                    executed=True,  # Only executed signals
                    executed_at=timezone.now(),
                )
                
                # Create bot
                bot = Bot.objects.create(
                    user=user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:12]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.STOPPED,
                    invested_amount=outcome_data["invested"],
                    current_value=outcome_data["invested"] + outcome_data["pnl"],
                    current_pnl=outcome_data["pnl"],
                    pnl_percent=outcome_data["pnl_percent"],
                    params={},
                    is_simulated=False,
                    triggered_by_signal=signal,
                    stopped_at=timezone.now(),
                )
                
                # Create outcome
                SignalOutcome.objects.create(
                    signal=signal,
                    bot=bot,
                    final_pnl=outcome_data["pnl"],
                    final_pnl_percent=outcome_data["pnl_percent"],
                    is_profitable=outcome_data["is_profitable"],
                    bot_duration_hours=24.0,
                )
            
            # Calculate metrics
            tracker = SignalAccuracyTracker()
            metrics = tracker.calculate_accuracy_metrics(user, days=30)
            
            # Calculate expected accuracy
            total_count = len(outcomes)
            profitable_count = sum(1 for o in outcomes if o["is_profitable"])
            expected_accuracy = (profitable_count / total_count) * 100
            
            assert metrics.overall_accuracy == pytest.approx(expected_accuracy, rel=1e-6), (
                f"overall_accuracy should be {expected_accuracy}, got {metrics.overall_accuracy}"
            )
            assert metrics.total_executed_signals == total_count, (
                f"total_executed_signals should be {total_count}, "
                f"got {metrics.total_executed_signals}"
            )
            assert metrics.profitable_signals == profitable_count, (
                f"profitable_signals should be {profitable_count}, "
                f"got {metrics.profitable_signals}"
            )
        finally:
            user.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        buy_outcomes=st.lists(signal_outcome_data_strategy(), min_size=1, max_size=25),
        sell_outcomes=st.lists(signal_outcome_data_strategy(), min_size=1, max_size=25),
    )
    def test_buy_sell_accuracy_separation(
        self,
        buy_outcomes: list[dict],
        sell_outcomes: list[dict],
        django_user_model,
    ) -> None:
        """
        Property: buy_accuracy and sell_accuracy SHALL be calculated separately.

        **Validates: Requirements 3.3**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        from apps.trading.models import Signal, SignalDirection, SignalOutcome
        
        # Create test user
        user = django_user_model.objects.create_user(
            username=f"test_buy_sell_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Create trading pair
            trading_pair, _ = TradingPair.objects.get_or_create(
                symbol="BTC_USDT",
                defaults={
                    "base_currency": "BTC",
                    "quote_currency": "USDT",
                    "is_active": True,
                },
            )
            
            # Create BUY signals and outcomes
            for outcome_data in buy_outcomes:
                signal = Signal.objects.create(
                    trading_pair=trading_pair,
                    direction=SignalDirection.BUY,
                    confidence=outcome_data["confidence"],
                    indicators={},
                    executed=True,
                    executed_at=timezone.now(),
                )
                
                bot = Bot.objects.create(
                    user=user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:12]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.STOPPED,
                    invested_amount=outcome_data["invested"],
                    current_value=outcome_data["invested"] + outcome_data["pnl"],
                    current_pnl=outcome_data["pnl"],
                    pnl_percent=outcome_data["pnl_percent"],
                    params={},
                    is_simulated=False,
                    triggered_by_signal=signal,
                    stopped_at=timezone.now(),
                )
                
                SignalOutcome.objects.create(
                    signal=signal,
                    bot=bot,
                    final_pnl=outcome_data["pnl"],
                    final_pnl_percent=outcome_data["pnl_percent"],
                    is_profitable=outcome_data["is_profitable"],
                    bot_duration_hours=24.0,
                )
            
            # Create SELL signals and outcomes
            for outcome_data in sell_outcomes:
                signal = Signal.objects.create(
                    trading_pair=trading_pair,
                    direction=SignalDirection.SELL,
                    confidence=outcome_data["confidence"],
                    indicators={},
                    executed=True,
                    executed_at=timezone.now(),
                )
                
                bot = Bot.objects.create(
                    user=user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:12]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.STOPPED,
                    invested_amount=outcome_data["invested"],
                    current_value=outcome_data["invested"] + outcome_data["pnl"],
                    current_pnl=outcome_data["pnl"],
                    pnl_percent=outcome_data["pnl_percent"],
                    params={},
                    is_simulated=False,
                    triggered_by_signal=signal,
                    stopped_at=timezone.now(),
                )
                
                SignalOutcome.objects.create(
                    signal=signal,
                    bot=bot,
                    final_pnl=outcome_data["pnl"],
                    final_pnl_percent=outcome_data["pnl_percent"],
                    is_profitable=outcome_data["is_profitable"],
                    bot_duration_hours=24.0,
                )
            
            # Calculate metrics
            tracker = SignalAccuracyTracker()
            metrics = tracker.calculate_accuracy_metrics(user, days=30)
            
            # Calculate expected accuracies
            buy_total = len(buy_outcomes)
            buy_profitable = sum(1 for o in buy_outcomes if o["is_profitable"])
            expected_buy_accuracy = (buy_profitable / buy_total) * 100
            
            sell_total = len(sell_outcomes)
            sell_profitable = sum(1 for o in sell_outcomes if o["is_profitable"])
            expected_sell_accuracy = (sell_profitable / sell_total) * 100
            
            assert metrics.buy_accuracy == pytest.approx(expected_buy_accuracy, rel=1e-6), (
                f"buy_accuracy should be {expected_buy_accuracy}, got {metrics.buy_accuracy}"
            )
            assert metrics.sell_accuracy == pytest.approx(expected_sell_accuracy, rel=1e-6), (
                f"sell_accuracy should be {expected_sell_accuracy}, got {metrics.sell_accuracy}"
            )
        finally:
            user.delete()


# =============================================================================
# Helper Functions for Correlation Tests
# =============================================================================


def create_mock_outcome(confidence: float, pnl_percent: float):
    """
    Create a mock SignalOutcome with given confidence and P&L.
    
    Args:
        confidence: Signal confidence value (0-100)
        pnl_percent: P&L percentage
        
    Returns:
        Mock outcome object with signal.confidence and final_pnl_percent attributes
    """
    class MockSignal:
        pass
    
    class MockOutcome:
        pass
    
    outcome = MockOutcome()
    outcome.signal = MockSignal()
    outcome.signal.confidence = confidence
    outcome.final_pnl_percent = pnl_percent
    return outcome


def generate_evenly_spaced_confidence_values(
    num_values: int,
    min_conf: float = 10.0,
    max_conf: float = 90.0,
) -> list[float]:
    """
    Generate evenly spaced confidence values avoiding edge effects.
    
    Uses range [10, 90] by default to avoid capping issues at 0 and 100.
    
    Args:
        num_values: Number of values to generate
        min_conf: Minimum confidence value
        max_conf: Maximum confidence value
        
    Returns:
        List of evenly spaced confidence values
    """
    if num_values == 1:
        return [(min_conf + max_conf) / 2]
    
    return [
        min_conf + ((max_conf - min_conf) * i / (num_values - 1))
        for i in range(num_values)
    ]


# Correlation thresholds for "perfect" correlation tests
# Using 0.95 instead of 1.0 to account for floating-point precision
PERFECT_CORRELATION_THRESHOLD = 0.95
PERFECT_NEGATIVE_CORRELATION_THRESHOLD = -0.95


# =============================================================================
# Property 7: Confidence Correlation Calculation
# =============================================================================


class TestConfidenceCorrelation:
    """
    Property 7: Confidence Correlation Calculation

    *For any* set of SignalOutcome records with at least 2 entries, the
    confidence_correlation SHALL equal the Pearson correlation coefficient
    between signal confidence values and final P&L percentages, bounded to [-1, 1].

    **Validates: Requirements 3.4**
    """

    @settings(max_examples=100)
    @given(
        outcomes=st.lists(
            st.tuples(confidence_strategy, st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
            min_size=2,
            max_size=50,
        ),
    )
    def test_correlation_bounded_to_valid_range(
        self,
        outcomes: list[tuple[float, float]],
    ) -> None:
        """
        Property: Correlation SHALL be bounded to [-1, 1].

        **Validates: Requirements 3.4**
        """
        # Create mock outcomes using helper function
        mock_outcomes = [
            create_mock_outcome(confidence, pnl_percent)
            for confidence, pnl_percent in outcomes
        ]
        
        # Calculate correlation
        tracker = SignalAccuracyTracker()
        correlation = tracker.calculate_confidence_correlation(mock_outcomes)
        
        if correlation is not None:
            assert -1.0 <= correlation <= 1.0, (
                f"Correlation {correlation} outside valid range [-1, 1]"
            )

    @settings(max_examples=100)
    @given(
        num_outcomes=st.integers(min_value=2, max_value=50),
    )
    def test_perfect_positive_correlation(
        self,
        num_outcomes: int,
    ) -> None:
        """
        Property: When P&L increases linearly with confidence,
        correlation SHALL be close to 1.0.

        **Validates: Requirements 3.4**
        """
        # Create perfectly correlated data with confidence values in valid range
        # Use evenly spaced values from 10 to 90 to avoid capping issues
        confidence_values = generate_evenly_spaced_confidence_values(num_outcomes)
        outcomes = [
            create_mock_outcome(conf, conf * 0.5)  # Linear relationship
            for conf in confidence_values
        ]
        
        # Calculate correlation
        tracker = SignalAccuracyTracker()
        correlation = tracker.calculate_confidence_correlation(outcomes)
        
        # Should be close to 1.0 (perfect positive correlation)
        assert correlation is not None
        assert correlation >= PERFECT_CORRELATION_THRESHOLD, (
            f"Perfect positive correlation should be >= {PERFECT_CORRELATION_THRESHOLD}, got {correlation}"
        )

    @settings(max_examples=100)
    @given(
        num_outcomes=st.integers(min_value=2, max_value=50),
    )
    def test_perfect_negative_correlation(
        self,
        num_outcomes: int,
    ) -> None:
        """
        Property: When P&L decreases linearly with confidence,
        correlation SHALL be close to -1.0.

        **Validates: Requirements 3.4**
        """
        # Create perfectly negatively correlated data with confidence values in valid range
        # Use evenly spaced values from 10 to 90 to avoid capping issues
        confidence_values = generate_evenly_spaced_confidence_values(num_outcomes)
        outcomes = [
            create_mock_outcome(conf, -conf * 0.5)  # Inverse linear relationship
            for conf in confidence_values
        ]
        
        # Calculate correlation
        tracker = SignalAccuracyTracker()
        correlation = tracker.calculate_confidence_correlation(outcomes)
        
        # Should be close to -1.0 (perfect negative correlation)
        assert correlation is not None
        assert correlation <= PERFECT_NEGATIVE_CORRELATION_THRESHOLD, (
            f"Perfect negative correlation should be <= {PERFECT_NEGATIVE_CORRELATION_THRESHOLD}, got {correlation}"
        )

    @settings(max_examples=100)
    @given(
        confidence=confidence_strategy,
        num_outcomes=st.integers(min_value=2, max_value=50),
    )
    def test_zero_correlation_with_constant_confidence(
        self,
        confidence: float,
        num_outcomes: int,
    ) -> None:
        """
        Property: When confidence is constant, correlation SHALL be None
        (undefined due to zero variance).

        **Validates: Requirements 3.4**
        """
        # Create data with constant confidence but varying P&L
        outcomes = [
            create_mock_outcome(confidence, float(i - num_outcomes / 2))
            for i in range(num_outcomes)
        ]
        
        # Calculate correlation
        tracker = SignalAccuracyTracker()
        correlation = tracker.calculate_confidence_correlation(outcomes)
        
        # Should be None (undefined due to zero variance in confidence)
        assert correlation is None, (
            f"Correlation with constant confidence should be None, got {correlation}"
        )

    @settings(max_examples=100)
    @given(
        outcomes=st.lists(
            st.tuples(confidence_strategy, st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
            min_size=2,
            max_size=50,
        ),
    )
    def test_correlation_is_deterministic(
        self,
        outcomes: list[tuple[float, float]],
    ) -> None:
        """
        Property: Calculating correlation twice SHALL produce identical results.

        **Validates: Requirements 3.4**
        """
        # Create mock outcomes using helper function
        mock_outcomes = [
            create_mock_outcome(confidence, pnl_percent)
            for confidence, pnl_percent in outcomes
        ]
        
        # Calculate correlation twice
        tracker = SignalAccuracyTracker()
        correlation1 = tracker.calculate_confidence_correlation(mock_outcomes)
        correlation2 = tracker.calculate_confidence_correlation(mock_outcomes)
        
        assert correlation1 == correlation2, (
            f"Correlation calculation not deterministic: {correlation1} vs {correlation2}"
        )
