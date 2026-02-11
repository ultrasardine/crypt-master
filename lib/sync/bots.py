"""
Bot Sync Service.

This module provides a service for synchronizing bot data from Pionex,
updating local Bot records with current status and P&L, and broadcasting
updates via WebSocket.

Requirements:
- 2.1: Fetch the list of running bots from Pionex API
- 2.2: Update local Bot model with current_value, current_pnl, and pnl_percent from Pionex
- 2.3: Create new Bot record when bot exists in Pionex but not locally
- 2.4: Update local Bot status to STOPPED when bot exists locally but not in Pionex
- 2.5: Broadcast update via WebSocket_Broadcaster when bot performance is updated
- 2.6: Run at configurable interval with default of 2 minutes
- 2.7: Log errors and continue processing other bots if individual bot sync fails
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.utils import timezone

from apps.bots.models import Bot, BotStatus, BotType
from apps.core.models import TradingPair
from lib.analysis.accuracy import SignalAccuracyTracker
from lib.messaging.websocket import WebSocketBroadcaster
from lib.pionex.client_factory import (
    APIKeyDecryptionError,
    MissingAPIKeysError,
    PionexClientFactory,
)
from lib.pionex.models import BotInfo, PionexAPIError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class BotSyncService:
    """
    Service for synchronizing bot data from Pionex.

    Fetches running bots and updates local Bot records with
    current P&L and status.

    Requirements:
    - 2.1: Fetch the list of running bots from Pionex API
    - 2.2: Update local Bot model with current_value, current_pnl, and pnl_percent
    - 2.3: Create new Bot record when bot exists in Pionex but not locally
    - 2.4: Update local Bot status to STOPPED when bot exists locally but not in Pionex
    - 2.5: Broadcast update via WebSocket_Broadcaster
    - 2.7: Handle individual bot sync failures gracefully
    """

    def __init__(
        self,
        client_factory: PionexClientFactory,
        broadcaster: WebSocketBroadcaster,
    ) -> None:
        """
        Initialize with dependencies.

        Args:
            client_factory: Factory for creating user-specific Pionex clients
            broadcaster: WebSocket broadcaster for real-time updates
        """
        self.client_factory = client_factory
        self.broadcaster = broadcaster
        self.accuracy_tracker = SignalAccuracyTracker()

    async def sync_user_bots(self, user: User) -> list[Bot]:
        """
        Sync bots for a single user.

        This method:
        1. Fetches the list of bots from Pionex
        2. Reconciles remote bots with local database
        3. Updates existing bots with current P&L
        4. Creates new bots that exist remotely but not locally
        5. Marks local bots as STOPPED if they don't exist remotely
        6. Broadcasts updates via WebSocket

        Args:
            user: The user whose bots to sync

        Returns:
            List of updated Bot records

        Requirements:
        - 2.1: Fetch the list of running bots from Pionex API
        - 2.2: Update local Bot model with current_value, current_pnl, and pnl_percent
        - 2.3: Create new Bot record when bot exists in Pionex but not locally
        - 2.4: Update local Bot status to STOPPED when bot exists locally but not in Pionex
        - 2.5: Broadcast update via WebSocket_Broadcaster
        - 2.7: Handle errors gracefully
        """
        try:
            # Get Pionex client for user
            async with await self.client_factory.get_client_for_user(user) as client:
                # Fetch bots from Pionex
                remote_bots = await client.list_bots()

                logger.info(
                    f"Fetched {len(remote_bots)} bots from Pionex for user {user.username}"
                )

                from asgiref.sync import sync_to_async

                # Get all local bots for this user
                local_bots = await sync_to_async(list)(
                    Bot.objects.for_user(user).live()
                )

                # Create a mapping of pionex_bot_id -> local Bot
                local_bots_map = {bot.pionex_bot_id: bot for bot in local_bots}

                # Create a set of remote bot IDs
                remote_bot_ids = {bot.bot_id for bot in remote_bots}

                updated_bots: list[Bot] = []

                # Process each remote bot
                for remote_bot in remote_bots:
                    try:
                        local_bot = local_bots_map.get(remote_bot.bot_id)
                        reconciled_bot = await self._reconcile_bot(local_bot, remote_bot, user)
                        if reconciled_bot:
                            updated_bots.append(reconciled_bot)
                    except Exception as e:
                        # Log error but continue processing other bots
                        logger.error(
                            f"Failed to reconcile bot {remote_bot.bot_id} for user {user.username}: {e}",
                            exc_info=True,
                        )
                        continue

                # Mark local bots as STOPPED if they don't exist remotely
                for local_bot in local_bots:
                    if local_bot.pionex_bot_id not in remote_bot_ids:
                        try:
                            # Only update if bot is currently ACTIVE
                            if local_bot.status == BotStatus.ACTIVE:
                                local_bot.status = BotStatus.STOPPED
                                local_bot.stopped_at = timezone.now()
                                local_bot.stop_reason = "Bot no longer exists on Pionex"
                                local_bot.last_synced_at = timezone.now()
                                await sync_to_async(local_bot.save)()

                                logger.info(
                                    f"Marked bot {local_bot.pionex_bot_id} as STOPPED "
                                    f"(not found on Pionex)"
                                )

                                # Record signal outcome if bot was triggered by a signal
                                if local_bot.triggered_by_signal and local_bot.current_pnl is not None:
                                    try:
                                        self.accuracy_tracker.record_outcome(
                                            signal=local_bot.triggered_by_signal,
                                            bot=local_bot,
                                            final_pnl=local_bot.current_pnl,
                                        )
                                        logger.info(
                                            f"Recorded signal outcome for bot {local_bot.pionex_bot_id}"
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to record signal outcome for bot {local_bot.pionex_bot_id}: {e}",
                                            exc_info=True,
                                        )

                                # Broadcast bot stopped event
                                await self.broadcaster.broadcast_bot_stopped(
                                    bot_id=local_bot.pionex_bot_id,
                                    symbol=local_bot.trading_pair.symbol,
                                    reason="Bot no longer exists on Pionex",
                                    final_pnl=local_bot.current_pnl,
                                    is_simulated=local_bot.is_simulated,
                                )

                                updated_bots.append(local_bot)
                        except Exception as e:
                            # Log error but continue processing other bots
                            logger.error(
                                f"Failed to mark bot {local_bot.pionex_bot_id} as STOPPED: {e}",
                                exc_info=True,
                            )
                            continue

                logger.info(
                    f"Successfully synced {len(updated_bots)} bots for user {user.username}"
                )

                return updated_bots

        except MissingAPIKeysError:
            logger.warning(
                f"User {user.username} has no API keys configured. Skipping bot sync."
            )
            return []

        except APIKeyDecryptionError as e:
            logger.error(
                f"Failed to decrypt API keys for user {user.username}: {e.reason}"
            )
            return []

        except PionexAPIError as e:
            logger.error(
                f"Pionex API error while syncing bots for user {user.username}: "
                f"{e.error.message} (status: {e.error.status_code})"
            )
            return []

        except Exception as e:
            logger.exception(
                f"Unexpected error while syncing bots for user {user.username}: {e}"
            )
            return []

    async def sync_all_bots(self) -> list[Bot]:
        """
        Sync bots for all users with API keys.

        Iterates over all users who have API keys configured and syncs
        their bots. Errors for individual users are logged but
        don't stop processing of other users.

        Returns:
            List of updated Bot records

        Requirements:
        - 2.7: Continue processing other users if one fails
        """
        from asgiref.sync import sync_to_async

        updated_bots: list[Bot] = []

        # Get all users with API keys configured (sync operation)
        users_with_keys = await sync_to_async(list)(
            User.objects.filter(
                profile__encrypted_api_key__isnull=False,
                profile__encrypted_api_key__gt="",
            ).select_related("profile")
        )

        logger.info(f"Syncing bots for {len(users_with_keys)} users")

        for user in users_with_keys:
            bots = await self.sync_user_bots(user)
            updated_bots.extend(bots)

        logger.info(f"Successfully synced {len(updated_bots)} bots across all users")

        return updated_bots

    async def _reconcile_bot(
        self,
        local_bot: Bot | None,
        remote_bot: BotInfo,
        user: User,
    ) -> Bot | None:
        """
        Reconcile local and remote bot state.

        This method handles three cases:
        1. Bot exists locally and remotely: Update local bot with remote data
        2. Bot exists remotely but not locally: Create new local bot
        3. Bot exists locally but not remotely: Handled by caller (mark as STOPPED)

        Args:
            local_bot: Local Bot record (None if doesn't exist)
            remote_bot: Remote bot info from Pionex
            user: The user who owns the bot

        Returns:
            Updated or created Bot record, or None if reconciliation failed

        Requirements:
        - 2.2: Update local Bot model with current_value, current_pnl, and pnl_percent
        - 2.3: Create new Bot record when bot exists in Pionex but not locally
        - 2.5: Broadcast update via WebSocket_Broadcaster
        """
        try:
            from asgiref.sync import sync_to_async

            # Get or create trading pair
            trading_pair, _ = await sync_to_async(TradingPair.objects.get_or_create)(
                symbol=remote_bot.symbol,
                defaults={
                    "base_currency": remote_bot.symbol.split("_")[0],
                    "quote_currency": remote_bot.symbol.split("_")[1],
                    "is_active": True,
                },
            )

            # Map Pionex BotType to Django BotType
            bot_type_map = {
                "GRID": BotType.GRID,
                "DCA": BotType.DCA,
                "INFINITY_GRID": BotType.INFINITY_GRID,
                "FUTURES_GRID": BotType.FUTURES_GRID,
            }
            bot_type = bot_type_map.get(remote_bot.bot_type.value, BotType.GRID)

            # Map Pionex BotStatus to Django BotStatus
            status_map = {
                "ACTIVE": BotStatus.ACTIVE,
                "STOPPED": BotStatus.STOPPED,
                "ERROR": BotStatus.ERROR,
                "CREATING": BotStatus.PENDING,
                "STOPPING": BotStatus.STOPPED,
            }
            status = status_map.get(remote_bot.status.value, BotStatus.ACTIVE)

            if local_bot:
                # Check if bot is transitioning to STOPPED
                was_active = local_bot.status == BotStatus.ACTIVE
                is_now_stopped = status == BotStatus.STOPPED
                
                # Update existing bot
                local_bot.current_value = remote_bot.current_value
                local_bot.current_pnl = remote_bot.pnl
                local_bot.pnl_percent = remote_bot.pnl_percent
                local_bot.status = status
                local_bot.last_synced_at = timezone.now()

                # Update stopped_at if bot was stopped
                if status == BotStatus.STOPPED and not local_bot.stopped_at:
                    local_bot.stopped_at = timezone.now()
                    local_bot.stop_reason = "Bot stopped on Pionex"

                await sync_to_async(local_bot.save)()

                # Record signal outcome if bot transitioned to STOPPED
                if was_active and is_now_stopped:
                    if local_bot.triggered_by_signal and local_bot.current_pnl is not None:
                        try:
                            self.accuracy_tracker.record_outcome(
                                signal=local_bot.triggered_by_signal,
                                bot=local_bot,
                                final_pnl=local_bot.current_pnl,
                            )
                            logger.info(
                                f"Recorded signal outcome for bot {local_bot.pionex_bot_id} "
                                f"(transitioned to STOPPED)"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to record signal outcome for bot {local_bot.pionex_bot_id}: {e}",
                                exc_info=True,
                            )

                logger.debug(
                    f"Updated bot {local_bot.pionex_bot_id}: "
                    f"value={remote_bot.current_value}, pnl={remote_bot.pnl}, "
                    f"pnl_percent={remote_bot.pnl_percent}%"
                )

                # Broadcast bot update
                await self.broadcaster.broadcast_bot_update(
                    bot_id=local_bot.pionex_bot_id,
                    status=status.value,
                    symbol=trading_pair.symbol,
                    invested=local_bot.invested_amount,
                    current_value=remote_bot.current_value,
                    pnl=remote_bot.pnl,
                    pnl_percent=remote_bot.pnl_percent,
                )

                return local_bot

            else:
                # Create new bot
                new_bot = await sync_to_async(Bot.objects.create)(
                    user=user,
                    pionex_bot_id=remote_bot.bot_id,
                    bot_type=bot_type,
                    trading_pair=trading_pair,
                    status=status,
                    invested_amount=remote_bot.invested,
                    current_value=remote_bot.current_value,
                    current_pnl=remote_bot.pnl,
                    pnl_percent=remote_bot.pnl_percent,
                    params=remote_bot.params.__dict__ if remote_bot.params else {},
                    is_simulated=False,  # Bots from Pionex are always live
                    last_synced_at=timezone.now(),
                )

                logger.info(
                    f"Created new bot {new_bot.pionex_bot_id} for user {user.username}: "
                    f"{bot_type.value} on {trading_pair.symbol}"
                )

                # Broadcast bot created event
                await self.broadcaster.broadcast_bot_created(
                    bot_id=new_bot.pionex_bot_id,
                    bot_type=bot_type.value,
                    symbol=trading_pair.symbol,
                    invested=remote_bot.invested,
                    params=remote_bot.params.__dict__ if remote_bot.params else {},
                    reasoning="Bot discovered on Pionex during sync",
                    is_simulated=False,
                )

                return new_bot

        except Exception as e:
            logger.error(
                f"Failed to reconcile bot {remote_bot.bot_id}: {e}",
                exc_info=True,
            )
            return None
