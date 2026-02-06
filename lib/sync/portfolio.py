"""
Portfolio Sync Service.

This module provides a service for synchronizing portfolio data from Pionex,
creating PortfolioSnapshot records, and broadcasting updates via WebSocket.

Requirements:
- 1.1: Fetch account balances from Pionex API using user's encrypted API credentials
- 1.2: Create PortfolioSnapshot record with total_value, available_balance, allocated_to_bots
- 1.3: Calculate drawdown by comparing current total_value against high_water_mark
- 1.4: Update high_water_mark when current total_value exceeds previous high_water_mark
- 1.5: Log errors and retry with exponential backoff when Pionex API is unavailable
- 1.6: Run at configurable interval with default of 5 minutes
- 1.7: Broadcast update via WebSocket_Broadcaster when new PortfolioSnapshot is created
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.db.models import Max
from django.utils import timezone

from apps.bots.models import Bot, BotStatus
from apps.core.models import PortfolioSnapshot
from lib.messaging.websocket import WebSocketBroadcaster
from lib.pionex.client_factory import (
    APIKeyDecryptionError,
    MissingAPIKeysError,
    PionexClientFactory,
)
from lib.pionex.models import PionexAPIError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PortfolioSyncService:
    """
    Service for synchronizing portfolio data from Pionex.

    Fetches account balances and creates PortfolioSnapshot records
    for each user with configured API keys.

    Requirements:
    - 1.1: Fetch account balances from Pionex API
    - 1.2: Create PortfolioSnapshot records
    - 1.3: Calculate drawdown
    - 1.4: Track high water mark
    - 1.7: Broadcast WebSocket updates
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

    async def sync_user_portfolio(self, user: User) -> PortfolioSnapshot | None:
        """
        Sync portfolio for a single user.

        This method:
        1. Fetches account balances from Pionex
        2. Calculates total value and allocated amounts
        3. Calculates drawdown and updates high water mark
        4. Creates a PortfolioSnapshot record
        5. Broadcasts the update via WebSocket

        Args:
            user: The user whose portfolio to sync

        Returns:
            Created PortfolioSnapshot or None if sync failed

        Requirements:
        - 1.1: Fetch balances from Pionex API
        - 1.2: Create PortfolioSnapshot
        - 1.3: Calculate drawdown
        - 1.4: Update high water mark
        - 1.5: Handle API errors gracefully
        - 1.7: Broadcast WebSocket update
        """
        try:
            # Get Pionex client for user
            async with await self.client_factory.get_client_for_user(user) as client:
                # Fetch balances from Pionex
                balances = await client.get_balances()

                # Calculate total value (sum of all balances)
                total_value = sum(
                    (balance.free + balance.locked for balance in balances),
                    start=Decimal("0"),
                )

                # Calculate available balance (sum of free balances)
                available_balance = sum(
                    (balance.free for balance in balances),
                    start=Decimal("0"),
                )

                # Calculate allocated to bots (sum of invested amounts in active bots)
                allocated_to_bots = (
                    Bot.objects.for_user(user)
                    .active()
                    .live()
                    .total_invested()
                )

                # Get previous high water mark
                previous_snapshot = (
                    PortfolioSnapshot.objects.for_user(user)
                    .live()
                    .first()
                )

                if previous_snapshot:
                    high_water_mark = previous_snapshot.high_water_mark
                else:
                    # First snapshot - use current value as high water mark
                    high_water_mark = total_value

                # Update high water mark if current value exceeds it
                if total_value > high_water_mark:
                    high_water_mark = total_value

                # Calculate drawdown
                drawdown = self._calculate_drawdown(total_value, high_water_mark)

                # Create PortfolioSnapshot
                snapshot = PortfolioSnapshot.objects.create(
                    user=user,
                    total_value=total_value,
                    available_balance=available_balance,
                    allocated_to_bots=allocated_to_bots,
                    drawdown=drawdown,
                    high_water_mark=high_water_mark,
                    is_simulated=False,
                )

                logger.info(
                    f"Created portfolio snapshot for user {user.username}: "
                    f"total_value={total_value}, drawdown={drawdown:.2f}%"
                )

                # Broadcast update via WebSocket
                await self.broadcaster.broadcast_portfolio_update(
                    total_value=total_value,
                    available_balance=available_balance,
                    allocated_to_bots=allocated_to_bots,
                    drawdown=drawdown,
                    high_water_mark=high_water_mark,
                )

                return snapshot

        except MissingAPIKeysError:
            logger.warning(
                f"User {user.username} has no API keys configured. Skipping portfolio sync."
            )
            return None

        except APIKeyDecryptionError as e:
            logger.error(
                f"Failed to decrypt API keys for user {user.username}: {e.reason}"
            )
            return None

        except PionexAPIError as e:
            logger.error(
                f"Pionex API error while syncing portfolio for user {user.username}: "
                f"{e.error.message} (status: {e.error.status_code})"
            )
            return None

        except Exception as e:
            logger.exception(
                f"Unexpected error while syncing portfolio for user {user.username}: {e}"
            )
            return None

    async def sync_all_portfolios(self) -> list[PortfolioSnapshot]:
        """
        Sync portfolios for all users with API keys.

        Iterates over all users who have API keys configured and syncs
        their portfolios. Errors for individual users are logged but
        don't stop processing of other users.

        Returns:
            List of created PortfolioSnapshot records

        Requirements:
        - 1.5: Continue processing other users if one fails
        """
        from asgiref.sync import sync_to_async

        snapshots: list[PortfolioSnapshot] = []

        # Get all users with API keys configured (sync operation)
        users_with_keys = await sync_to_async(list)(
            User.objects.filter(
                profile__encrypted_api_key__isnull=False,
                profile__encrypted_api_key__gt="",
            ).select_related("profile")
        )

        logger.info(f"Syncing portfolios for {len(users_with_keys)} users")

        for user in users_with_keys:
            snapshot = await self.sync_user_portfolio(user)
            if snapshot:
                snapshots.append(snapshot)

        logger.info(f"Successfully synced {len(snapshots)} portfolios")

        return snapshots

    def _calculate_drawdown(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> float:
        """
        Calculate drawdown percentage from high water mark.

        Drawdown is the percentage decline from the high water mark.
        Formula: (high_water_mark - current_value) / high_water_mark * 100

        Args:
            current_value: Current portfolio value
            high_water_mark: Historical high water mark

        Returns:
            Drawdown percentage (0-100), clamped to [0, 100]

        Requirements:
        - 1.3: Calculate drawdown correctly
        """
        if high_water_mark <= 0:
            return 0.0

        drawdown = float((high_water_mark - current_value) / high_water_mark * 100)

        # Clamp to [0, 100] range
        return max(0.0, min(100.0, drawdown))
