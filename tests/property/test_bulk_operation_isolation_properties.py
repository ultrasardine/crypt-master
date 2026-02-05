"""
Property-based tests for Bulk Operation User Isolation.

Feature: multi-tenant-user-isolation
Property 20: Bulk Operation User Isolation

These tests use the hypothesis library to verify that bulk operations
(bulk update, bulk delete) only affect records belonging to the authenticated user.

Requirements:
- 12.6: Filter all records by user before bulk operations
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.bots.models import Bot, BotStatus, BotType
from apps.core.models import PortfolioSnapshot, TradingPair
from apps.trading.models import Trade, TradeSide

if TYPE_CHECKING:
    pass


@pytest.fixture
def trading_pair(db):
    """Create a trading pair for tests."""
    pair, _ = TradingPair.objects.get_or_create(
        symbol="BTC_USDT",
        defaults={
            "base_currency": "BTC",
            "quote_currency": "USDT",
            "is_active": True,
        },
    )
    return pair


@pytest.fixture
def request_factory():
    """Create a request factory for tests."""
    return RequestFactory()


def create_test_user(username: str | None = None) -> User:
    """Create a test user with a unique username."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )


@pytest.mark.django_db(transaction=True)
class TestBulkUpdateUserIsolation:
    """
    Property 20: Bulk Operation User Isolation - Bulk Update

    *For any* bulk update operation on user-owned models, only records
    belonging to the authenticated user SHALL be affected.

    Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

    **Validates: Requirements 12.6**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_bots=st.integers(min_value=1, max_value=5),
        num_user2_bots=st.integers(min_value=1, max_value=5),
    )
    def test_bulk_update_bots_only_affects_user_records(
        self,
        trading_pair,
        num_user1_bots: int,
        num_user2_bots: int,
    ) -> None:
        """
        Property: Bulk update on Bot model only affects the authenticated user's bots.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create bots for user1 (ACTIVE status)
            user1_bot_ids = []
            for i in range(num_user1_bots):
                bot = Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                user1_bot_ids.append(bot.id)

            # Create bots for user2 (ACTIVE status)
            user2_bot_ids = []
            for i in range(num_user2_bots):
                bot = Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )
                user2_bot_ids.append(bot.id)

            # Perform bulk update on user1's bots only (using for_user filter)
            updated_count = Bot.objects.for_user(user1).update(status=BotStatus.STOPPED)

            # Verify only user1's bots were updated
            assert updated_count == num_user1_bots, (
                f"Expected {num_user1_bots} bots to be updated, but {updated_count} were updated"
            )

            # Verify user1's bots are now STOPPED
            for bot_id in user1_bot_ids:
                bot = Bot.objects.get(id=bot_id)
                assert bot.status == BotStatus.STOPPED, (
                    f"User1's bot {bot_id} should be STOPPED after bulk update"
                )

            # Verify user2's bots are still ACTIVE (not affected)
            for bot_id in user2_bot_ids:
                bot = Bot.objects.get(id=bot_id)
                assert bot.status == BotStatus.ACTIVE, (
                    f"User2's bot {bot_id} should still be ACTIVE (not affected by user1's bulk update)"
                )

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_trades=st.integers(min_value=1, max_value=5),
        num_user2_trades=st.integers(min_value=1, max_value=5),
    )
    def test_bulk_update_trades_only_affects_user_records(
        self,
        trading_pair,
        num_user1_trades: int,
        num_user2_trades: int,
    ) -> None:
        """
        Property: Bulk update on Trade model only affects the authenticated user's trades.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create trades for user1 (not simulated)
            user1_trade_ids = []
            for i in range(num_user1_trades):
                trade = Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    quantity="0.001",
                    is_simulated=False,
                )
                user1_trade_ids.append(trade.id)

            # Create trades for user2 (not simulated)
            user2_trade_ids = []
            for i in range(num_user2_trades):
                trade = Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="51000.00",
                    quantity="0.002",
                    is_simulated=False,
                )
                user2_trade_ids.append(trade.id)

            # Perform bulk update on user1's trades only
            updated_count = Trade.objects.for_user(user1).update(is_simulated=True)

            # Verify only user1's trades were updated
            assert updated_count == num_user1_trades, (
                f"Expected {num_user1_trades} trades to be updated, but {updated_count} were updated"
            )

            # Verify user1's trades are now simulated
            for trade_id in user1_trade_ids:
                trade = Trade.objects.get(id=trade_id)
                assert trade.is_simulated is True, (
                    f"User1's trade {trade_id} should be simulated after bulk update"
                )

            # Verify user2's trades are still not simulated (not affected)
            for trade_id in user2_trade_ids:
                trade = Trade.objects.get(id=trade_id)
                assert trade.is_simulated is False, (
                    f"User2's trade {trade_id} should still be not simulated"
                )

        finally:
            Trade.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_snapshots=st.integers(min_value=1, max_value=5),
        num_user2_snapshots=st.integers(min_value=1, max_value=5),
        new_drawdown=st.floats(min_value=0.0, max_value=50.0, allow_nan=False),
    )
    def test_bulk_update_portfolio_snapshots_only_affects_user_records(
        self,
        num_user1_snapshots: int,
        num_user2_snapshots: int,
        new_drawdown: float,
    ) -> None:
        """
        Property: Bulk update on PortfolioSnapshot only affects the authenticated user's snapshots.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create snapshots for user1 (drawdown = 0)
            user1_snapshot_ids = []
            for i in range(num_user1_snapshots):
                snapshot = PortfolioSnapshot.objects.create(
                    user=user1,
                    total_value="10000.00",
                    available_balance="5000.00",
                    allocated_to_bots="5000.00",
                    high_water_mark="10000.00",
                    drawdown=0.0,
                )
                user1_snapshot_ids.append(snapshot.id)

            # Create snapshots for user2 (drawdown = 0)
            user2_snapshot_ids = []
            for i in range(num_user2_snapshots):
                snapshot = PortfolioSnapshot.objects.create(
                    user=user2,
                    total_value="20000.00",
                    available_balance="10000.00",
                    allocated_to_bots="10000.00",
                    high_water_mark="20000.00",
                    drawdown=0.0,
                )
                user2_snapshot_ids.append(snapshot.id)

            # Perform bulk update on user1's snapshots only
            updated_count = PortfolioSnapshot.objects.for_user(user1).update(drawdown=new_drawdown)

            # Verify only user1's snapshots were updated
            assert updated_count == num_user1_snapshots, (
                f"Expected {num_user1_snapshots} snapshots to be updated, "
                f"but {updated_count} were updated"
            )

            # Verify user1's snapshots have new drawdown
            for snapshot_id in user1_snapshot_ids:
                snapshot = PortfolioSnapshot.objects.get(id=snapshot_id)
                assert abs(snapshot.drawdown - new_drawdown) < 0.001, (
                    f"User1's snapshot {snapshot_id} should have drawdown {new_drawdown}"
                )

            # Verify user2's snapshots still have drawdown = 0 (not affected)
            for snapshot_id in user2_snapshot_ids:
                snapshot = PortfolioSnapshot.objects.get(id=snapshot_id)
                assert snapshot.drawdown == 0.0, (
                    f"User2's snapshot {snapshot_id} should still have drawdown 0.0"
                )

        finally:
            PortfolioSnapshot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


@pytest.mark.django_db(transaction=True)
class TestBulkDeleteUserIsolation:
    """
    Property 20: Bulk Operation User Isolation - Bulk Delete

    *For any* bulk delete operation on user-owned models, only records
    belonging to the authenticated user SHALL be affected.

    Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

    **Validates: Requirements 12.6**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_bots=st.integers(min_value=1, max_value=5),
        num_user2_bots=st.integers(min_value=1, max_value=5),
    )
    def test_bulk_delete_bots_only_affects_user_records(
        self,
        trading_pair,
        num_user1_bots: int,
        num_user2_bots: int,
    ) -> None:
        """
        Property: Bulk delete on Bot model only deletes the authenticated user's bots.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create bots for user1
            for i in range(num_user1_bots):
                Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.STOPPED,
                    invested_amount="100.00",
                )

            # Create bots for user2
            user2_bot_ids = []
            for i in range(num_user2_bots):
                bot = Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )
                user2_bot_ids.append(bot.id)

            # Perform bulk delete on user1's bots only
            deleted_count, _ = Bot.objects.for_user(user1).delete()

            # Verify only user1's bots were deleted
            assert deleted_count == num_user1_bots, (
                f"Expected {num_user1_bots} bots to be deleted, but {deleted_count} were deleted"
            )

            # Verify user1 has no bots left
            assert Bot.objects.for_user(user1).count() == 0, (
                "User1 should have no bots after bulk delete"
            )

            # Verify user2's bots still exist (not affected)
            assert Bot.objects.for_user(user2).count() == num_user2_bots, (
                f"User2 should still have {num_user2_bots} bots"
            )

            # Verify each of user2's bots still exists
            for bot_id in user2_bot_ids:
                assert Bot.objects.filter(id=bot_id).exists(), (
                    f"User2's bot {bot_id} should still exist after user1's bulk delete"
                )

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_trades=st.integers(min_value=1, max_value=5),
        num_user2_trades=st.integers(min_value=1, max_value=5),
    )
    def test_bulk_delete_trades_only_affects_user_records(
        self,
        trading_pair,
        num_user1_trades: int,
        num_user2_trades: int,
    ) -> None:
        """
        Property: Bulk delete on Trade model only deletes the authenticated user's trades.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create trades for user1
            for i in range(num_user1_trades):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    quantity="0.001",
                )

            # Create trades for user2
            user2_trade_ids = []
            for i in range(num_user2_trades):
                trade = Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="51000.00",
                    quantity="0.002",
                )
                user2_trade_ids.append(trade.id)

            # Perform bulk delete on user1's trades only
            deleted_count, _ = Trade.objects.for_user(user1).delete()

            # Verify only user1's trades were deleted
            assert deleted_count == num_user1_trades, (
                f"Expected {num_user1_trades} trades to be deleted, but {deleted_count} were deleted"
            )

            # Verify user1 has no trades left
            assert Trade.objects.for_user(user1).count() == 0, (
                "User1 should have no trades after bulk delete"
            )

            # Verify user2's trades still exist (not affected)
            assert Trade.objects.for_user(user2).count() == num_user2_trades, (
                f"User2 should still have {num_user2_trades} trades"
            )

            # Verify each of user2's trades still exists
            for trade_id in user2_trade_ids:
                assert Trade.objects.filter(id=trade_id).exists(), (
                    f"User2's trade {trade_id} should still exist after user1's bulk delete"
                )

        finally:
            Trade.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_snapshots=st.integers(min_value=1, max_value=5),
        num_user2_snapshots=st.integers(min_value=1, max_value=5),
    )
    def test_bulk_delete_portfolio_snapshots_only_affects_user_records(
        self,
        num_user1_snapshots: int,
        num_user2_snapshots: int,
    ) -> None:
        """
        Property: Bulk delete on PortfolioSnapshot only deletes the authenticated user's snapshots.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create snapshots for user1
            for i in range(num_user1_snapshots):
                PortfolioSnapshot.objects.create(
                    user=user1,
                    total_value="10000.00",
                    available_balance="5000.00",
                    allocated_to_bots="5000.00",
                    high_water_mark="10000.00",
                )

            # Create snapshots for user2
            user2_snapshot_ids = []
            for i in range(num_user2_snapshots):
                snapshot = PortfolioSnapshot.objects.create(
                    user=user2,
                    total_value="20000.00",
                    available_balance="10000.00",
                    allocated_to_bots="10000.00",
                    high_water_mark="20000.00",
                )
                user2_snapshot_ids.append(snapshot.id)

            # Perform bulk delete on user1's snapshots only
            deleted_count, _ = PortfolioSnapshot.objects.for_user(user1).delete()

            # Verify only user1's snapshots were deleted
            assert deleted_count == num_user1_snapshots, (
                f"Expected {num_user1_snapshots} snapshots to be deleted, "
                f"but {deleted_count} were deleted"
            )

            # Verify user1 has no snapshots left
            assert PortfolioSnapshot.objects.for_user(user1).count() == 0, (
                "User1 should have no snapshots after bulk delete"
            )

            # Verify user2's snapshots still exist (not affected)
            assert PortfolioSnapshot.objects.for_user(user2).count() == num_user2_snapshots, (
                f"User2 should still have {num_user2_snapshots} snapshots"
            )

            # Verify each of user2's snapshots still exists
            for snapshot_id in user2_snapshot_ids:
                assert PortfolioSnapshot.objects.filter(id=snapshot_id).exists(), (
                    f"User2's snapshot {snapshot_id} should still exist after user1's bulk delete"
                )

        finally:
            PortfolioSnapshot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


@pytest.mark.django_db(transaction=True)
class TestBulkOperationWithMultipleUsers:
    """
    Property 20: Bulk Operation User Isolation - Multiple Users

    Tests that verify bulk operations correctly isolate data when
    multiple users are involved.

    Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

    **Validates: Requirements 12.6**
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=2, max_value=4),
        bots_per_user=st.integers(min_value=1, max_value=3),
    )
    def test_bulk_update_with_multiple_users_isolates_correctly(
        self,
        trading_pair,
        num_users: int,
        bots_per_user: int,
    ) -> None:
        """
        Property: Bulk update with multiple users only affects the target user's records.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        users = [create_test_user() for _ in range(num_users)]
        user_bot_ids: dict[int, list[int]] = {user.id: [] for user in users}

        try:
            # Create bots for each user
            for user in users:
                for i in range(bots_per_user):
                    bot = Bot.objects.create(
                        user=user,
                        pionex_bot_id=f"bot_{user.id}_{uuid.uuid4().hex[:8]}",
                        bot_type=BotType.GRID,
                        trading_pair=trading_pair,
                        status=BotStatus.ACTIVE,
                        invested_amount="100.00",
                    )
                    user_bot_ids[user.id].append(bot.id)

            # Pick the first user to perform bulk update
            target_user = users[0]
            other_users = users[1:]

            # Perform bulk update on target user's bots only
            updated_count = Bot.objects.for_user(target_user).update(status=BotStatus.STOPPED)

            # Verify only target user's bots were updated
            assert updated_count == bots_per_user, (
                f"Expected {bots_per_user} bots to be updated, but {updated_count} were updated"
            )

            # Verify target user's bots are now STOPPED
            for bot_id in user_bot_ids[target_user.id]:
                bot = Bot.objects.get(id=bot_id)
                assert bot.status == BotStatus.STOPPED, (
                    f"Target user's bot {bot_id} should be STOPPED"
                )

            # Verify other users' bots are still ACTIVE
            for other_user in other_users:
                for bot_id in user_bot_ids[other_user.id]:
                    bot = Bot.objects.get(id=bot_id)
                    assert bot.status == BotStatus.ACTIVE, (
                        f"Other user's bot {bot_id} should still be ACTIVE"
                    )

        finally:
            Bot.objects.filter(user__in=users).delete()
            for user in users:
                user.delete()


    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=2, max_value=4),
        bots_per_user=st.integers(min_value=1, max_value=3),
    )
    def test_bulk_delete_with_multiple_users_isolates_correctly(
        self,
        trading_pair,
        num_users: int,
        bots_per_user: int,
    ) -> None:
        """
        Property: Bulk delete with multiple users only affects the target user's records.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        users = [create_test_user() for _ in range(num_users)]
        user_bot_ids: dict[int, list[int]] = {user.id: [] for user in users}

        try:
            # Create bots for each user
            for user in users:
                for i in range(bots_per_user):
                    bot = Bot.objects.create(
                        user=user,
                        pionex_bot_id=f"bot_{user.id}_{uuid.uuid4().hex[:8]}",
                        bot_type=BotType.GRID,
                        trading_pair=trading_pair,
                        status=BotStatus.ACTIVE,
                        invested_amount="100.00",
                    )
                    user_bot_ids[user.id].append(bot.id)

            # Pick the first user to perform bulk delete
            target_user = users[0]
            other_users = users[1:]

            # Perform bulk delete on target user's bots only
            deleted_count, _ = Bot.objects.for_user(target_user).delete()

            # Verify only target user's bots were deleted
            assert deleted_count == bots_per_user, (
                f"Expected {bots_per_user} bots to be deleted, but {deleted_count} were deleted"
            )

            # Verify target user has no bots left
            assert Bot.objects.for_user(target_user).count() == 0, (
                "Target user should have no bots after bulk delete"
            )

            # Verify other users still have all their bots
            for other_user in other_users:
                assert Bot.objects.for_user(other_user).count() == bots_per_user, (
                    f"Other user should still have {bots_per_user} bots"
                )
                for bot_id in user_bot_ids[other_user.id]:
                    assert Bot.objects.filter(id=bot_id).exists(), (
                        f"Other user's bot {bot_id} should still exist"
                    )

        finally:
            Bot.objects.filter(user__in=users).delete()
            for user in users:
                user.delete()


@pytest.mark.django_db(transaction=True)
class TestBulkOperationRecordIntegrity:
    """
    Property 20: Bulk Operation User Isolation - Record Integrity

    Tests that verify records belonging to other users are never modified
    or deleted during bulk operations.

    Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

    **Validates: Requirements 12.6**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_bots=st.integers(min_value=1, max_value=5),
        num_user2_bots=st.integers(min_value=1, max_value=5),
        new_invested_amount=st.decimals(
            min_value="50.00",
            max_value="500.00",
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_other_user_records_unchanged_after_bulk_update(
        self,
        trading_pair,
        num_user1_bots: int,
        num_user2_bots: int,
        new_invested_amount: Decimal,
    ) -> None:
        """
        Property: Other user's records remain completely unchanged after bulk update.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create bots for user1
            for i in range(num_user1_bots):
                Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )

            # Create bots for user2 with specific values to verify
            user2_original_data: dict[int, dict] = {}
            for i in range(num_user2_bots):
                bot = Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount=Decimal("200.00"),
                )
                # Refresh from DB to get the actual stored values
                bot.refresh_from_db()
                user2_original_data[bot.id] = {
                    "status": bot.status,
                    "invested_amount": bot.invested_amount,
                    "bot_type": bot.bot_type,
                    "pionex_bot_id": bot.pionex_bot_id,
                }

            # Perform bulk update on user1's bots
            Bot.objects.for_user(user1).update(
                status=BotStatus.STOPPED,
                invested_amount=new_invested_amount,
            )

            # Verify user2's bots are completely unchanged
            for bot_id, original_data in user2_original_data.items():
                bot = Bot.objects.get(id=bot_id)
                assert bot.status == original_data["status"], (
                    f"User2's bot {bot_id} status should be unchanged"
                )
                assert bot.invested_amount == original_data["invested_amount"], (
                    f"User2's bot {bot_id} invested_amount should be unchanged"
                )
                assert bot.bot_type == original_data["bot_type"], (
                    f"User2's bot {bot_id} bot_type should be unchanged"
                )
                assert bot.pionex_bot_id == original_data["pionex_bot_id"], (
                    f"User2's bot {bot_id} pionex_bot_id should be unchanged"
                )

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_bots=st.integers(min_value=1, max_value=5),
        num_user2_bots=st.integers(min_value=1, max_value=5),
    )
    def test_other_user_record_count_unchanged_after_bulk_delete(
        self,
        trading_pair,
        num_user1_bots: int,
        num_user2_bots: int,
    ) -> None:
        """
        Property: Other user's record count remains unchanged after bulk delete.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create bots for user1
            for i in range(num_user1_bots):
                Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )

            # Create bots for user2
            for i in range(num_user2_bots):
                Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )

            # Record user2's bot count before delete
            user2_count_before = Bot.objects.for_user(user2).count()

            # Perform bulk delete on user1's bots
            Bot.objects.for_user(user1).delete()

            # Verify user2's bot count is unchanged
            user2_count_after = Bot.objects.for_user(user2).count()
            assert user2_count_after == user2_count_before, (
                f"User2's bot count should be unchanged: "
                f"expected {user2_count_before}, got {user2_count_after}"
            )
            assert user2_count_after == num_user2_bots, (
                f"User2 should still have {num_user2_bots} bots"
            )

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


@pytest.mark.django_db(transaction=True)
class TestBulkOperationSecurityLogging:
    """
    Property 20: Bulk Operation User Isolation - Security Logging

    Tests that verify bulk operations are properly logged for security monitoring.

    Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

    **Validates: Requirements 12.6**
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=5),
    )
    def test_bulk_operation_can_be_logged(
        self,
        trading_pair,
        num_bots: int,
    ) -> None:
        """
        Property: Bulk operations can be logged using the security logger.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        from unittest.mock import patch

        from lib.multitenancy.security import SecurityEventLogger

        user = create_test_user()

        try:
            # Create bots for user
            for i in range(num_bots):
                Bot.objects.create(
                    user=user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )

            logger = SecurityEventLogger()

            with patch.object(logger._logger, "debug") as mock_debug:
                # Log the bulk operation
                logger.log_bulk_operation_filtered(
                    requesting_user=user,
                    resource_type="Bot",
                    total_requested=num_bots,
                    filtered_count=num_bots,
                    operation="update",
                )

                # Verify logging was called (debug level when no filtering occurred)
                mock_debug.assert_called_once()
                extra = mock_debug.call_args[1]["extra"]
                security_event = extra["security_event"]

                # Verify event contains correct information
                assert security_event["requesting_user_id"] == user.id
                assert security_event["target_resource_type"] == "Bot"
                assert security_event["details"]["operation"] == "update"
                assert security_event["details"]["total_requested"] == num_bots
                assert security_event["details"]["filtered_count"] == num_bots

        finally:
            Bot.objects.filter(user=user).delete()
            user.delete()


    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        total_requested=st.integers(min_value=5, max_value=20),
        filtered_count=st.integers(min_value=1, max_value=4),
    )
    def test_bulk_operation_logs_warning_when_records_filtered(
        self,
        total_requested: int,
        filtered_count: int,
    ) -> None:
        """
        Property: Bulk operations log a warning when records are filtered out.

        Feature: multi-tenant-user-isolation, Property 20: Bulk Operation User Isolation

        **Validates: Requirements 12.6**
        """
        from unittest.mock import patch

        from lib.multitenancy.security import SecurityEventLogger

        # Ensure filtered_count is less than total_requested
        if filtered_count >= total_requested:
            filtered_count = total_requested - 1

        user = create_test_user()

        try:
            logger = SecurityEventLogger()

            with patch.object(logger._logger, "warning") as mock_warning:
                # Log a bulk operation where records were filtered
                logger.log_bulk_operation_filtered(
                    requesting_user=user,
                    resource_type="Bot",
                    total_requested=total_requested,
                    filtered_count=filtered_count,
                    operation="delete",
                )

                # Verify warning was logged (because records were filtered)
                mock_warning.assert_called_once()
                extra = mock_warning.call_args[1]["extra"]
                security_event = extra["security_event"]

                # Verify event contains correct information
                assert security_event["requesting_user_id"] == user.id
                assert security_event["target_resource_type"] == "Bot"
                assert security_event["details"]["operation"] == "delete"
                assert security_event["details"]["total_requested"] == total_requested
                assert security_event["details"]["filtered_count"] == filtered_count

        finally:
            user.delete()
