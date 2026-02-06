"""Celery tasks for core app."""

import asyncio
import logging

from celery import shared_task

from lib.messaging.websocket import WebSocketBroadcaster
from lib.pionex.client_factory import PionexClientFactory
from lib.sync.bots import BotSyncService
from lib.sync.portfolio import PortfolioSyncService
from lib.sync.public_data import PublicDataService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def sync_portfolios(self):
    """
    Sync portfolio data for all users from Pionex.

    This task:
    - Fetches account balances from Pionex API
    - Creates PortfolioSnapshot records
    - Calculates drawdown and high water mark
    - Broadcasts updates via WebSocket

    Runs every 5 minutes by default.

    Requirements:
    - 8.1: Periodic portfolio sync task
    - 8.4: Retry policy with exponential backoff
    """
    try:
        logger.info("Starting portfolio sync task")

        # Create service dependencies
        from django.conf import settings

        from lib.crypto.api_key_manager import APIKeyManager

        api_key_manager = APIKeyManager(master_key=settings.SECRET_KEY)
        client_factory = PionexClientFactory(api_key_manager)
        broadcaster = WebSocketBroadcaster()
        service = PortfolioSyncService(client_factory, broadcaster)

        # Run async sync
        snapshots = asyncio.run(service.sync_all_portfolios())

        logger.info(f"Portfolio sync task completed: {len(snapshots)} snapshots created")

        return {
            "status": "success",
            "snapshots_created": len(snapshots),
        }

    except Exception as e:
        logger.error(f"Portfolio sync task failed: {e}", exc_info=True)
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def sync_bots(self):
    """
    Sync bot data for all users from Pionex.

    This task:
    - Fetches running bots from Pionex API
    - Updates local Bot records with current P&L
    - Creates new bots discovered on Pionex
    - Marks local bots as STOPPED if not found on Pionex
    - Records signal outcomes for stopped bots
    - Broadcasts updates via WebSocket

    Runs every 2 minutes by default.

    Requirements:
    - 8.2: Periodic bot sync task
    - 8.4: Retry policy with exponential backoff
    """
    try:
        logger.info("Starting bot sync task")

        # Create service dependencies
        from django.conf import settings

        from lib.crypto.api_key_manager import APIKeyManager

        api_key_manager = APIKeyManager(master_key=settings.SECRET_KEY)
        client_factory = PionexClientFactory(api_key_manager)
        broadcaster = WebSocketBroadcaster()
        service = BotSyncService(client_factory, broadcaster)

        # Run async sync
        bots = asyncio.run(service.sync_all_bots())

        logger.info(f"Bot sync task completed: {len(bots)} bots synced")

        return {
            "status": "success",
            "bots_synced": len(bots),
        }

    except Exception as e:
        logger.error(f"Bot sync task failed: {e}", exc_info=True)
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def fetch_public_market_data(self):
    """
    Fetch public market sentiment data from external APIs.

    This task:
    - Fetches Fear & Greed Index from Alternative.me
    - Fetches funding rates from Binance
    - Fetches liquidation data from CoinGlass
    - Fetches open interest data
    - Creates MarketSentimentData record
    - Broadcasts updates via WebSocket

    Runs every 1 hour by default.

    Requirements:
    - 8.3: Periodic public data fetch task
    - 8.4: Retry policy with exponential backoff
    """
    try:
        logger.info("Starting public market data fetch task")

        # Create service dependencies
        broadcaster = WebSocketBroadcaster()
        service = PublicDataService(broadcaster=broadcaster)

        # Run async fetch
        sentiment_data = asyncio.run(service.fetch_all_public_data())

        # Close HTTP client
        asyncio.run(service.close())

        logger.info(
            f"Public market data fetch task completed: "
            f"FGI={sentiment_data.fear_greed_index}, stale={sentiment_data.is_stale}"
        )

        return {
            "status": "success",
            "fear_greed_index": sentiment_data.fear_greed_index,
            "is_stale": sentiment_data.is_stale,
        }

    except Exception as e:
        logger.error(f"Public market data fetch task failed: {e}", exc_info=True)
        raise


@shared_task
def create_portfolio_snapshot():
    """
    Create a periodic snapshot of the portfolio state.

    This task runs every 5 minutes to track portfolio value over time.

    DEPRECATED: Use sync_portfolios instead.
    """
    # TODO: Implement portfolio snapshot creation
    # This will be implemented when the Pionex client is ready
    pass
