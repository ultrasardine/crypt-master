"""
Celery configuration for crypt-master project.

This module configures Celery for background task processing,
including scheduled tasks via Celery Beat.
"""

import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("crypt-master")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat schedule for periodic tasks
app.conf.beat_schedule = {
    # Dashboard Integration Tasks
    "sync-portfolios": {
        "task": "apps.core.tasks.sync_portfolios",
        "schedule": 300.0,  # Every 5 minutes
    },
    "sync-bots": {
        "task": "apps.core.tasks.sync_bots",
        "schedule": 120.0,  # Every 2 minutes
    },
    "fetch-public-market-data": {
        "task": "apps.core.tasks.fetch_public_market_data",
        "schedule": 3600.0,  # Every 1 hour
    },
    # Market Intelligence Layer Tasks
    "fetch-external-market-data": {
        "task": "apps.core.tasks.fetch_external_market_data",
        "schedule": float(os.getenv("EXTERNAL_DATA_SYNC_INTERVAL", "900")),  # Every 15 minutes (default)
    },
    "run-pattern-miner": {
        "task": "apps.core.tasks.run_pattern_miner",
        "schedule": float(os.getenv("PATTERN_MINER_INTERVAL", "604800")),  # Weekly (default: 7 days)
    },
    # Analysis Tasks
    "update-signal-accuracy": {
        "task": "apps.trading.tasks.update_signal_accuracy",
        "schedule": 3600.0,  # Every 1 hour
    },
    # Legacy Tasks
    "cleanup-old-signals": {
        "task": "apps.trading.tasks.cleanup_old_signals",
        "schedule": 3600.0,  # Every hour
    },
    "portfolio-snapshot": {
        "task": "apps.core.tasks.create_portfolio_snapshot",
        "schedule": 300.0,  # Every 5 minutes (DEPRECATED)
    },
    "daily-report": {
        "task": "apps.trading.tasks.generate_daily_report",
        "schedule": 86400.0,  # Every 24 hours
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery configuration."""
    print(f"Request: {self.request!r}")
