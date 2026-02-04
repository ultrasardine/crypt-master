"""Celery tasks for trading app."""

from celery import shared_task


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
