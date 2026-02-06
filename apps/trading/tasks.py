"""Celery tasks for trading app."""

import logging

from celery import shared_task
from django.contrib.auth.models import User

from lib.analysis.accuracy import SignalAccuracyTracker

logger = logging.getLogger(__name__)


@shared_task
def update_signal_accuracy():
    """
    Calculate and update signal accuracy metrics for all users.

    This task:
    - Iterates over all users
    - Calculates accuracy metrics for the last 30 days
    - Creates/updates SignalAccuracyMetrics records
    - Tracks overall accuracy, BUY/SELL accuracy, and confidence correlation

    Runs every 1 hour by default.

    Requirements:
    - 3.5: Periodic signal accuracy calculation
    """
    try:
        logger.info("Starting signal accuracy update task")

        # Create accuracy tracker
        tracker = SignalAccuracyTracker()

        # Get all users
        users = User.objects.all()

        metrics_updated = 0

        for user in users:
            try:
                # Calculate accuracy metrics for last 30 days
                metrics = tracker.calculate_accuracy_metrics(user, days=30)

                if metrics.total_executed_signals > 0:
                    metrics_updated += 1
                    logger.debug(
                        f"Updated accuracy metrics for user {user.username}: "
                        f"overall={metrics.overall_accuracy:.1f}%"
                    )

            except Exception as e:
                # Log error but continue processing other users
                logger.error(
                    f"Failed to update accuracy metrics for user {user.username}: {e}",
                    exc_info=True,
                )
                continue

        logger.info(
            f"Signal accuracy update task completed: {metrics_updated} users updated"
        )

        return {
            "status": "success",
            "users_updated": metrics_updated,
        }

    except Exception as e:
        logger.error(f"Signal accuracy update task failed: {e}", exc_info=True)
        raise


@shared_task
def cleanup_old_signals():
    """
    Clean up old signals that are no longer needed.

    Keeps signals for the last 30 days, removes older ones.
    """
    # TODO: Implement signal cleanup
    pass


@shared_task
def generate_daily_report():
    """
    Generate daily trading report.

    Summarizes trades, P&L, and performance metrics for the day.
    """
    # TODO: Implement daily report generation
    pass
