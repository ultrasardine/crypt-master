"""
Signal Accuracy Tracker.

This module provides a service for tracking the accuracy of trading signals
by comparing predictions with actual bot outcomes.

Requirements:
- 3.1: Record signal outcomes when bots are stopped
- 3.2: Calculate accuracy rate as percentage of profitable signals
- 3.3: Track accuracy separately for BUY and SELL signals
- 3.4: Calculate correlation between signal confidence and P&L
- 3.7: Only consider executed signals for accuracy calculations
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.db.models import Avg
from django.utils import timezone

from apps.bots.models import Bot
from apps.trading.models import Signal, SignalAccuracyMetrics, SignalDirection, SignalOutcome

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SignalAccuracyTracker:
    """
    Tracks accuracy of trading signals by comparing predictions
    with actual bot outcomes.

    Requirements:
    - 3.1: Record signal outcomes when bots are stopped
    - 3.2: Calculate accuracy rate as percentage of profitable signals
    - 3.3: Track accuracy separately for BUY and SELL signals
    - 3.4: Calculate correlation between signal confidence and P&L
    - 3.7: Only consider executed signals for accuracy calculations
    """

    def __init__(self) -> None:
        """Initialize the tracker."""
        pass

    def record_outcome(
        self,
        signal: Signal,
        bot: Bot,
        final_pnl: Decimal,
    ) -> SignalOutcome:
        """
        Record the outcome of a signal that led to bot creation.

        This method creates a SignalOutcome record linking the signal to the bot
        and recording the final P&L and profitability.

        Args:
            signal: The signal that triggered bot creation
            bot: The bot that was created
            final_pnl: The final P&L when bot was stopped

        Returns:
            SignalOutcome record

        Requirements:
        - 3.1: Record signal outcomes when bots are stopped
        """
        # Calculate bot duration in hours
        if bot.stopped_at and bot.created_at:
            duration = bot.stopped_at - bot.created_at
            bot_duration_hours = duration.total_seconds() / 3600
        else:
            bot_duration_hours = None

        # Calculate P&L percentage
        if bot.invested_amount and bot.invested_amount > 0:
            final_pnl_percent = float((final_pnl / bot.invested_amount) * 100)
        else:
            final_pnl_percent = None

        # Determine if profitable
        is_profitable = final_pnl > 0

        # Create or update SignalOutcome
        outcome, created = SignalOutcome.objects.update_or_create(
            signal=signal,
            defaults={
                "bot": bot,
                "final_pnl": final_pnl,
                "final_pnl_percent": final_pnl_percent,
                "is_profitable": is_profitable,
                "bot_duration_hours": bot_duration_hours,
            },
        )

        action = "Created" if created else "Updated"
        logger.info(
            f"{action} SignalOutcome for signal {signal.id}: "
            f"profitable={is_profitable}, pnl={final_pnl}, pnl_percent={final_pnl_percent}"
        )

        return outcome

    def calculate_accuracy_metrics(
        self,
        user: User,
        days: int = 30,
    ) -> SignalAccuracyMetrics:
        """
        Calculate accuracy metrics for a user over a time period.

        This method:
        1. Fetches all executed signals with outcomes in the time period
        2. Calculates overall accuracy as percentage of profitable signals
        3. Calculates separate accuracy for BUY and SELL signals
        4. Calculates correlation between signal confidence and P&L
        5. Stores the metrics in a SignalAccuracyMetrics record

        Args:
            user: The user to calculate metrics for
            days: Number of days to include (default: 30)

        Returns:
            SignalAccuracyMetrics with calculated values

        Requirements:
        - 3.2: Calculate accuracy rate as percentage of profitable signals
        - 3.3: Track accuracy separately for BUY and SELL signals
        - 3.4: Calculate correlation between signal confidence and P&L
        - 3.7: Only consider executed signals for accuracy calculations
        """
        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=days)

        # Get all executed signals with outcomes for this user in the time period
        # Only include signals that were executed (led to bot creation)
        outcomes = SignalOutcome.objects.filter(
            signal__executed=True,
            bot__user=user,
            recorded_at__gte=cutoff_date,
        ).select_related("signal", "bot")

        # Count total executed signals
        total_executed_signals = outcomes.count()

        if total_executed_signals == 0:
            # No data to calculate metrics
            metrics = SignalAccuracyMetrics.objects.create(
                user=user,
                period_days=days,
                total_executed_signals=0,
                profitable_signals=0,
                unprofitable_signals=0,
                overall_accuracy=0.0,
                buy_accuracy=0.0,
                sell_accuracy=0.0,
                confidence_correlation=None,
                average_pnl_percent=None,
            )
            logger.info(f"No executed signals found for user {user.username} in last {days} days")
            return metrics

        # Count profitable and unprofitable signals
        profitable_signals = outcomes.filter(is_profitable=True).count()
        unprofitable_signals = outcomes.filter(is_profitable=False).count()

        # Calculate overall accuracy
        overall_accuracy = (profitable_signals / total_executed_signals) * 100

        # Calculate BUY accuracy
        buy_outcomes = outcomes.filter(signal__direction=SignalDirection.BUY)
        buy_total = buy_outcomes.count()
        if buy_total > 0:
            buy_profitable = buy_outcomes.filter(is_profitable=True).count()
            buy_accuracy = (buy_profitable / buy_total) * 100
        else:
            buy_accuracy = 0.0

        # Calculate SELL accuracy
        sell_outcomes = outcomes.filter(signal__direction=SignalDirection.SELL)
        sell_total = sell_outcomes.count()
        if sell_total > 0:
            sell_profitable = sell_outcomes.filter(is_profitable=True).count()
            sell_accuracy = (sell_profitable / sell_total) * 100
        else:
            sell_accuracy = 0.0

        # Calculate confidence correlation
        confidence_correlation = self.calculate_confidence_correlation(list(outcomes))

        # Calculate average P&L percent
        avg_pnl = outcomes.aggregate(avg=Avg("final_pnl_percent"))
        average_pnl_percent = avg_pnl["avg"]

        # Create or update metrics record
        metrics, created = SignalAccuracyMetrics.objects.update_or_create(
            user=user,
            period_days=days,
            defaults={
                "total_executed_signals": total_executed_signals,
                "profitable_signals": profitable_signals,
                "unprofitable_signals": unprofitable_signals,
                "overall_accuracy": overall_accuracy,
                "buy_accuracy": buy_accuracy,
                "sell_accuracy": sell_accuracy,
                "confidence_correlation": confidence_correlation,
                "average_pnl_percent": average_pnl_percent,
            },
        )

        action = "Created" if created else "Updated"
        logger.info(
            f"{action} SignalAccuracyMetrics for user {user.username}: "
            f"overall={overall_accuracy:.1f}%, buy={buy_accuracy:.1f}%, "
            f"sell={sell_accuracy:.1f}%, correlation={confidence_correlation}"
        )

        return metrics

    def calculate_confidence_correlation(
        self,
        outcomes: list[SignalOutcome],
    ) -> float | None:
        """
        Calculate correlation between signal confidence and P&L.

        Uses Pearson correlation coefficient to measure the linear relationship
        between signal confidence scores and actual P&L percentages.

        Args:
            outcomes: List of signal outcomes

        Returns:
            Pearson correlation coefficient (-1 to 1), or None if insufficient data

        Requirements:
        - 3.4: Calculate correlation between signal confidence and P&L
        """
        if len(outcomes) < 2:
            # Need at least 2 data points for correlation
            return None

        # Extract confidence and P&L percent pairs
        # Filter out outcomes with missing P&L percent
        data_pairs = [
            (outcome.signal.confidence, outcome.final_pnl_percent)
            for outcome in outcomes
            if outcome.final_pnl_percent is not None
        ]

        if len(data_pairs) < 2:
            return None

        # Calculate Pearson correlation coefficient
        n = len(data_pairs)
        confidence_values = [pair[0] for pair in data_pairs]
        pnl_values = [pair[1] for pair in data_pairs]

        # Calculate means
        mean_confidence = sum(confidence_values) / n
        mean_pnl = sum(pnl_values) / n

        # Calculate covariance and standard deviations
        covariance = sum(
            (confidence_values[i] - mean_confidence) * (pnl_values[i] - mean_pnl)
            for i in range(n)
        ) / n

        std_confidence = (
            sum((x - mean_confidence) ** 2 for x in confidence_values) / n
        ) ** 0.5
        std_pnl = (sum((x - mean_pnl) ** 2 for x in pnl_values) / n) ** 0.5

        # Avoid division by zero - use small epsilon for floating point comparison
        epsilon = 1e-10
        if std_confidence < epsilon or std_pnl < epsilon:
            return None

        # Calculate correlation coefficient
        correlation = covariance / (std_confidence * std_pnl)

        # Clamp to [-1, 1] to handle floating point errors
        correlation = max(-1.0, min(1.0, correlation))

        return correlation
