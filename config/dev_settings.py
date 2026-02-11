"""
Django development settings for crypt-master project.

Optimized for local development with shorter sync intervals
to see data flow quickly without waiting 15+ minutes.
"""

import os

from config.settings import *  # noqa: F401, F403

# Force SQLite for frictionless dev setup
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# Shorter Celery beat intervals for development
# See data flow in minutes instead of waiting 15-60 minutes
CELERY_BEAT_SCHEDULE = {
    # Portfolio sync: every 1 minute (prod: 5 min)
    "sync-portfolios": {
        "task": "apps.core.tasks.sync_portfolios",
        "schedule": float(os.getenv("DEV_PORTFOLIO_SYNC_INTERVAL", "60")),
    },
    # Bot sync: every 30 seconds (prod: 2 min)
    "sync-bots": {
        "task": "apps.core.tasks.sync_bots",
        "schedule": float(os.getenv("DEV_BOT_SYNC_INTERVAL", "30")),
    },
    # Public market data (Fear & Greed): every 5 minutes (prod: 1 hour)
    "fetch-public-market-data": {
        "task": "apps.core.tasks.fetch_public_market_data",
        "schedule": float(os.getenv("DEV_PUBLIC_DATA_INTERVAL", "300")),
    },
    # External market data (context snapshots): every 2 minutes (prod: 15 min)
    "fetch-external-market-data": {
        "task": "apps.core.tasks.fetch_external_market_data",
        "schedule": float(os.getenv("DEV_EXTERNAL_DATA_INTERVAL", "120")),
    },
    # Pattern miner: every 10 minutes for dev (prod: weekly)
    "run-pattern-miner": {
        "task": "apps.core.tasks.run_pattern_miner",
        "schedule": float(os.getenv("DEV_PATTERN_MINER_INTERVAL", "600")),
    },
    # Signal accuracy: every 5 minutes (prod: 1 hour)
    "update-signal-accuracy": {
        "task": "apps.trading.tasks.update_signal_accuracy",
        "schedule": float(os.getenv("DEV_SIGNAL_ACCURACY_INTERVAL", "300")),
    },
    # Cleanup: every 30 minutes (prod: 1 hour)
    "cleanup-old-signals": {
        "task": "apps.trading.tasks.cleanup_old_signals",
        "schedule": float(os.getenv("DEV_CLEANUP_INTERVAL", "1800")),
    },
}

# More verbose logging for development
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["agents"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["trading"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["bots"]["level"] = "DEBUG"  # noqa: F405

# Add console handler to all loggers for visibility
for logger_name in ["apps", "agents", "trading", "bots", "system"]:
    if logger_name in LOGGING["loggers"]:  # noqa: F405
        if "console" not in LOGGING["loggers"][logger_name].get("handlers", []):  # noqa: F405
            LOGGING["loggers"][logger_name]["handlers"].append("console")  # noqa: F405

# Print startup message
print("\n" + "=" * 60)
print("🚀 DEVELOPMENT MODE - Shortened sync intervals active")
print("=" * 60)
print(f"  Portfolio sync:     every {CELERY_BEAT_SCHEDULE['sync-portfolios']['schedule']}s")
print(f"  Bot sync:           every {CELERY_BEAT_SCHEDULE['sync-bots']['schedule']}s")
print(f"  Public data:        every {CELERY_BEAT_SCHEDULE['fetch-public-market-data']['schedule']}s")
print(f"  External data:      every {CELERY_BEAT_SCHEDULE['fetch-external-market-data']['schedule']}s")
print(f"  Pattern miner:      every {CELERY_BEAT_SCHEDULE['run-pattern-miner']['schedule']}s")
print("=" * 60 + "\n")
