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
    "cleanup-old-signals": {
        "task": "apps.trading.tasks.cleanup_old_signals",
        "schedule": 3600.0,  # Every hour
    },
    "portfolio-snapshot": {
        "task": "apps.core.tasks.create_portfolio_snapshot",
        "schedule": 300.0,  # Every 5 minutes
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
