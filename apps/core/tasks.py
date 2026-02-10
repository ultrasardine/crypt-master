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

    async def _fetch_and_close():
        """Run fetch and cleanup in a single event loop."""
        broadcaster = WebSocketBroadcaster()
        service = PublicDataService(broadcaster=broadcaster)
        try:
            return await service.fetch_all_public_data()
        finally:
            await service.close()

    try:
        logger.info("Starting public market data fetch task")

        # Run async fetch and cleanup in single event loop
        sentiment_data = asyncio.run(_fetch_and_close())

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


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def fetch_external_market_data(self):
    """
    Fetch external market data from all sources and create MarketContextSnapshot.

    This task:
    - Fetches BTC dominance, global market cap, volume from CoinGecko/CoinMarketCap
    - Fetches on-chain metrics (active addresses, exchange flow, whale activity, TVL)
    - Fetches social sentiment (polarity, mention count, buzz score)
    - Normalizes scores to 0.0-1.0 range
    - Merges results and creates MarketContextSnapshot record
    - Tracks stale fields when clients fail
    - Broadcasts WebSocket update after creating snapshot

    Runs every 15 minutes by default.

    Requirements:
    - 1.5.1: Celery task calls MarketDataHub.sync()
    - 1.5.3: Task registered in beat schedule
    - 1.5.4: Create snapshot marked is_stale=True if all APIs fail
    - 1.5.5: Broadcast WebSocket update after creating snapshot
    """

    async def _sync_and_broadcast():
        """Run sync, broadcast, and cleanup in a single event loop."""
        from lib.messaging.websocket import WebSocketBroadcaster
        from lib.sync.hub import HubConfig, MarketDataHub

        broadcaster = WebSocketBroadcaster()
        config = HubConfig()
        hub = MarketDataHub(config=config)

        try:
            # Sync external data
            snapshot = await hub.sync()

            # Broadcast WebSocket update
            await broadcaster.broadcast_market_context_update(
                {
                    "type": "market_context_update",
                    "snapshot_id": snapshot.id,
                    "symbol": snapshot.symbol,
                    "regime": snapshot.regime,
                    "btc_dominance": snapshot.btc_dominance,
                    "social_sentiment_score": snapshot.social_sentiment_score,
                    "social_buzz_score": snapshot.social_buzz_score,
                    "net_exchange_flow": snapshot.net_exchange_flow,
                    "whale_tx_count": snapshot.whale_tx_count,
                    "trend_strength_score": snapshot.trend_strength_score,
                    "risk_regime_score": snapshot.risk_regime_score,
                    "sentiment_regime_score": snapshot.sentiment_regime_score,
                    "is_stale": snapshot.is_stale,
                    "is_degraded": snapshot.is_degraded,
                    "timestamp": snapshot.timestamp.isoformat(),
                }
            )

            return snapshot
        finally:
            await hub.close()

    try:
        logger.info("Starting external market data fetch task")

        # Run async sync and cleanup in single event loop
        snapshot = asyncio.run(_sync_and_broadcast())

        logger.info(
            f"External market data fetch task completed: "
            f"snapshot_id={snapshot.id}, regime={snapshot.regime}, "
            f"is_stale={snapshot.is_stale}"
        )

        return {
            "status": "success",
            "snapshot_id": snapshot.id,
            "regime": snapshot.regime,
            "is_stale": snapshot.is_stale,
            "is_degraded": snapshot.is_degraded,
        }

    except Exception as e:
        logger.error(f"External market data fetch task failed: {e}", exc_info=True)
        # If all APIs fail, create a stale snapshot
        try:
            from apps.core.models import MarketContextSnapshot
            from django.utils import timezone

            snapshot = MarketContextSnapshot.objects.create(
                symbol=None,
                timestamp=timezone.now(),
                is_stale=True,
                is_degraded=True,
                stale_fields=[
                    "btc_dominance",
                    "global_market_cap",
                    "total_volume_24h",
                    "active_addresses",
                    "net_exchange_flow",
                    "whale_tx_count",
                    "defi_tvl",
                    "sentiment_polarity",
                    "mention_count",
                    "buzz_score",
                ],
            )
            logger.warning(
                f"Created stale snapshot due to all API failures: snapshot_id={snapshot.id}"
            )
            return {
                "status": "degraded",
                "snapshot_id": snapshot.id,
                "is_stale": True,
                "error": str(e),
            }
        except Exception as fallback_error:
            logger.error(f"Failed to create fallback stale snapshot: {fallback_error}")
            raise


@shared_task
def create_portfolio_snapshot():
    """
    Create a periodic snapshot of the portfolio state.

    This task runs every 5 minutes to track portfolio value over time.

    DEPRECATED: Use sync_portfolios instead.
    """
    # TODO: Implement portfolio snapshot snapshot creation
    # This will be implemented when the Pionex client is ready
    pass


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def run_pattern_miner(self):
    """
    Run pattern mining to discover winning strategy patterns.

    This task:
    - Analyzes historical Signal records with associated SignalOutcome data
    - Groups signals by regime and indicator ranges
    - Calculates win rate and average P&L for each group
    - Stores groups meeting thresholds as StrategyPattern records

    Runs weekly by default.

    Requirements:
    - 3.3.6: Pattern mining can be scheduled as a Celery beat task (weekly)
    """
    try:
        logger.info("Starting pattern mining task")

        from lib.analysis.pattern_miner import PatternMiner, PatternMinerConfig

        # Use default configuration
        config = PatternMinerConfig()
        miner = PatternMiner(config=config)

        # Discover and save patterns
        patterns = miner.discover_patterns(dry_run=False)

        logger.info(f"Pattern mining task completed: {len(patterns)} patterns discovered")

        return {
            "status": "success",
            "patterns_discovered": len(patterns),
            "patterns": [
                {
                    "id": p.id,
                    "regime": p.feature_combination.get("regime"),
                    "hit_rate": p.hit_rate,
                    "average_pnl": p.average_pnl,
                    "sample_size": p.sample_size,
                }
                for p in patterns
            ],
        }

    except Exception as e:
        logger.error(f"Pattern mining task failed: {e}", exc_info=True)
        raise
