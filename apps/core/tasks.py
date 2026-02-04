"""Celery tasks for core app."""

from celery import shared_task


@shared_task
def create_portfolio_snapshot():
    """
    Create a periodic snapshot of the portfolio state.

    This task runs every 5 minutes to track portfolio value over time.
    """
    # TODO: Implement portfolio snapshot creation
    # This will be implemented when the Pionex client is ready
    pass
