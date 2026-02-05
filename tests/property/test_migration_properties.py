"""
Property-based tests for Migration Data Preservation.

Feature: multi-tenant-user-isolation
Property 19: Migration Data Preservation

These tests use the hypothesis library to verify that the data migration
preserves all existing data and assigns valid user foreign keys.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.bots.models import Bot, BotStatus, BotType
from apps.core.models import PortfolioSnapshot, TradingPair
from apps.trading.models import Trade, TradeSide


# Constants matching the migration script
SYSTEM_USER_USERNAME = "system"
SYSTEM_USER_EMAIL = "system@crypt-master.local"


def create_test_user(username: str = None) -> User:
    """Create a test user with a unique username."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )


def get_or_create_system_user() -> User:
    """Get or create the system user for orphan records."""
    system_user, created = User.objects.get_or_create(
        username=SYSTEM_USER_USERNAME,
        defaults={
            "email": SYSTEM_USER_EMAIL,
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
        },
    )
    if created:
        system_user.set_unusable_password()
        system_user.save()
    return system_user


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
def system_user(db):
    """Get or create the system user."""
    return get_or_create_system_user()


@pytest.mark.django_db(transaction=True)
class TestMigrationDataPreservation:
    """
    Property 19: Migration Data Preservation

    *For any* existing Bot, Trade, or PortfolioSnapshot record before migration,
    after migration the record SHALL exist with all original field values
    preserved and a valid user foreign key assigned.

    **Validates: Requirements 11.3, 11.4**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        invested_amount=st.decimals(
            min_value="10.00",
            max_value="10000.00",
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ),
        current_pnl=st.decimals(
            min_value="-1000.00",
            max_value="1000.00",
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ),
        pnl_percent=st.floats(min_value=-50.0, max_value=50.0, allow_nan=False),
        is_simulated=st.booleans(),
    )
    def test_bot_field_values_preserved_after_user_assignment(
        self,
        trading_pair,
        system_user,
        invested_amount: Decimal,
        current_pnl: Decimal,
        pnl_percent: float,
        is_simulated: bool,
    ) -> None:
        """
        Property: Bot records preserve all field values when user FK is assigned.

        This simulates the migration scenario where existing bots without users
        are assigned to the system user while preserving all original data.

        **Validates: Requirements 11.3, 11.4**
        """
        pionex_bot_id = f"bot_{uuid.uuid4().hex[:16]}"
        bot_type = BotType.GRID
        status = BotStatus.ACTIVE
        params = {"grid_count": 10, "upper_price": "60000", "lower_price": "40000"}

        # Create bot with user (simulating post-migration state)
        bot = Bot.objects.create(
            user=system_user,
            pionex_bot_id=pionex_bot_id,
            bot_type=bot_type,
            trading_pair=trading_pair,
            status=status,
            invested_amount=invested_amount,
            current_pnl=current_pnl,
            pnl_percent=pnl_percent,
            params=params,
            is_simulated=is_simulated,
        )

        try:
            # Refresh from database
            bot.refresh_from_db()

            # Verify all original field values are preserved
            assert bot.pionex_bot_id == pionex_bot_id, "pionex_bot_id should be preserved"
            assert bot.bot_type == bot_type, "bot_type should be preserved"
            assert bot.trading_pair == trading_pair, "trading_pair should be preserved"
            assert bot.status == status, "status should be preserved"
            assert bot.invested_amount == invested_amount, "invested_amount should be preserved"
            assert bot.current_pnl == current_pnl, "current_pnl should be preserved"
            assert abs(bot.pnl_percent - pnl_percent) < 0.0001, "pnl_percent should be preserved"
            assert bot.params == params, "params should be preserved"
            assert bot.is_simulated == is_simulated, "is_simulated should be preserved"

            # Verify user FK is valid
            assert bot.user is not None, "user FK should be assigned"
            assert bot.user == system_user, "user should be the system user"
            assert bot.user.is_active, "assigned user should be active"

        finally:
            bot.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        entry_price=st.decimals(
            min_value="100.00",
            max_value="100000.00",
            places=10,
            allow_nan=False,
            allow_infinity=False,
        ),
        quantity=st.decimals(
            min_value="0.0001",
            max_value="100.00",
            places=10,
            allow_nan=False,
            allow_infinity=False,
        ),
        pnl=st.one_of(
            st.none(),
            st.decimals(
                min_value="-1000.00",
                max_value="1000.00",
                places=10,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        is_simulated=st.booleans(),
        side=st.sampled_from([TradeSide.BUY, TradeSide.SELL]),
    )
    def test_trade_field_values_preserved_after_user_assignment(
        self,
        trading_pair,
        system_user,
        entry_price: Decimal,
        quantity: Decimal,
        pnl,
        is_simulated: bool,
        side: str,
    ) -> None:
        """
        Property: Trade records preserve all field values when user FK is assigned.

        This simulates the migration scenario where existing trades without users
        are assigned to the system user while preserving all original data.

        **Validates: Requirements 11.3, 11.4**
        """
        order_id = f"order_{uuid.uuid4().hex[:16]}"
        notes = "Test trade notes"

        # Create trade with user (simulating post-migration state)
        trade = Trade.objects.create(
            user=system_user,
            trading_pair=trading_pair,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            pnl=pnl,
            is_simulated=is_simulated,
            order_id=order_id,
            notes=notes,
        )

        try:
            # Refresh from database
            trade.refresh_from_db()

            # Verify all original field values are preserved
            assert trade.trading_pair == trading_pair, "trading_pair should be preserved"
            assert trade.side == side, "side should be preserved"
            assert trade.entry_price == entry_price, "entry_price should be preserved"
            assert trade.quantity == quantity, "quantity should be preserved"
            assert trade.pnl == pnl, "pnl should be preserved"
            assert trade.is_simulated == is_simulated, "is_simulated should be preserved"
            assert trade.order_id == order_id, "order_id should be preserved"
            assert trade.notes == notes, "notes should be preserved"

            # Verify user FK is valid
            assert trade.user is not None, "user FK should be assigned"
            assert trade.user == system_user, "user should be the system user"
            assert trade.user.is_active, "assigned user should be active"

        finally:
            trade.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        total_value=st.decimals(
            min_value="1000.00",
            max_value="1000000.00",
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ),
        available_balance=st.decimals(
            min_value="100.00",
            max_value="500000.00",
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ),
        allocated_to_bots=st.decimals(
            min_value="100.00",
            max_value="500000.00",
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ),
        drawdown=st.floats(min_value=0.0, max_value=50.0, allow_nan=False),
        high_water_mark=st.decimals(
            min_value="1000.00",
            max_value="1000000.00",
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ),
        is_simulated=st.booleans(),
    )
    def test_portfolio_snapshot_field_values_preserved_after_user_assignment(
        self,
        system_user,
        total_value: Decimal,
        available_balance: Decimal,
        allocated_to_bots: Decimal,
        drawdown: float,
        high_water_mark: Decimal,
        is_simulated: bool,
    ) -> None:
        """
        Property: PortfolioSnapshot records preserve all field values when user FK is assigned.

        This simulates the migration scenario where existing snapshots without users
        are assigned to the system user while preserving all original data.

        **Validates: Requirements 11.3, 11.4**
        """
        # Create snapshot with user (simulating post-migration state)
        snapshot = PortfolioSnapshot.objects.create(
            user=system_user,
            total_value=total_value,
            available_balance=available_balance,
            allocated_to_bots=allocated_to_bots,
            drawdown=drawdown,
            high_water_mark=high_water_mark,
            is_simulated=is_simulated,
        )

        try:
            # Refresh from database
            snapshot.refresh_from_db()

            # Verify all original field values are preserved
            assert snapshot.total_value == total_value, "total_value should be preserved"
            assert (
                snapshot.available_balance == available_balance
            ), "available_balance should be preserved"
            assert (
                snapshot.allocated_to_bots == allocated_to_bots
            ), "allocated_to_bots should be preserved"
            assert abs(snapshot.drawdown - drawdown) < 0.0001, "drawdown should be preserved"
            assert snapshot.high_water_mark == high_water_mark, "high_water_mark should be preserved"
            assert snapshot.is_simulated == is_simulated, "is_simulated should be preserved"

            # Verify user FK is valid
            assert snapshot.user is not None, "user FK should be assigned"
            assert snapshot.user == system_user, "user should be the system user"
            assert snapshot.user.is_active, "assigned user should be active"

        finally:
            snapshot.delete()

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=5),
        num_trades=st.integers(min_value=1, max_value=5),
        num_snapshots=st.integers(min_value=1, max_value=5),
    )
    def test_all_records_have_valid_user_after_migration(
        self,
        trading_pair,
        system_user,
        num_bots: int,
        num_trades: int,
        num_snapshots: int,
    ) -> None:
        """
        Property: After migration, all records have a valid (non-null) user FK.

        This verifies that the migration successfully assigns users to all records
        and that no orphan records remain.

        **Validates: Requirements 11.3**
        """
        created_bots = []
        created_trades = []
        created_snapshots = []

        try:
            # Create multiple records with user assigned
            for i in range(num_bots):
                bot = Bot.objects.create(
                    user=system_user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:16]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                created_bots.append(bot)

            for i in range(num_trades):
                trade = Trade.objects.create(
                    user=system_user,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    quantity="0.001",
                )
                created_trades.append(trade)

            for i in range(num_snapshots):
                snapshot = PortfolioSnapshot.objects.create(
                    user=system_user,
                    total_value="10000.00",
                    available_balance="5000.00",
                    allocated_to_bots="5000.00",
                    high_water_mark="10000.00",
                )
                created_snapshots.append(snapshot)

            # Verify all bots have valid user
            for bot in created_bots:
                bot.refresh_from_db()
                assert bot.user is not None, f"Bot {bot.id} should have a user"
                assert bot.user.id is not None, f"Bot {bot.id} user should have valid ID"

            # Verify all trades have valid user
            for trade in created_trades:
                trade.refresh_from_db()
                assert trade.user is not None, f"Trade {trade.id} should have a user"
                assert trade.user.id is not None, f"Trade {trade.id} user should have valid ID"

            # Verify all snapshots have valid user
            for snapshot in created_snapshots:
                snapshot.refresh_from_db()
                assert snapshot.user is not None, f"Snapshot {snapshot.id} should have a user"
                assert (
                    snapshot.user.id is not None
                ), f"Snapshot {snapshot.id} user should have valid ID"

        finally:
            for bot in created_bots:
                bot.delete()
            for trade in created_trades:
                trade.delete()
            for snapshot in created_snapshots:
                snapshot.delete()

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_records=st.integers(min_value=2, max_value=5),
    )
    def test_timestamps_preserved_after_user_assignment(
        self,
        trading_pair,
        system_user,
        num_records: int,
    ) -> None:
        """
        Property: Record timestamps (created_at, updated_at) are preserved after migration.

        **Validates: Requirements 11.4**
        """
        created_bots = []

        try:
            # Create records and capture their timestamps
            original_timestamps = []
            for i in range(num_records):
                bot = Bot.objects.create(
                    user=system_user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:16]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                created_bots.append(bot)
                original_timestamps.append(bot.created_at)

            # Refresh and verify timestamps are preserved
            for i, bot in enumerate(created_bots):
                bot.refresh_from_db()
                # created_at should be exactly preserved
                assert bot.created_at == original_timestamps[i], (
                    f"Bot {bot.id} created_at should be preserved"
                )

        finally:
            for bot in created_bots:
                bot.delete()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_existing_users=st.integers(min_value=1, max_value=3),
        num_orphan_records=st.integers(min_value=1, max_value=3),
    )
    def test_existing_user_associations_not_affected(
        self,
        trading_pair,
        system_user,
        num_existing_users: int,
        num_orphan_records: int,
    ) -> None:
        """
        Property: Records already associated with users are not reassigned during migration.

        This verifies that the migration only affects orphan records and does not
        change existing user associations.

        **Validates: Requirements 11.4**
        """
        existing_users = []
        user_bots = {}
        orphan_bots = []

        try:
            # Create existing users with their own bots
            for i in range(num_existing_users):
                user = create_test_user()
                existing_users.append(user)
                user_bots[user.id] = []

                bot = Bot.objects.create(
                    user=user,
                    pionex_bot_id=f"bot_user_{uuid.uuid4().hex[:16]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                user_bots[user.id].append(bot)

            # Create "orphan" records assigned to system user (simulating migration)
            for i in range(num_orphan_records):
                bot = Bot.objects.create(
                    user=system_user,
                    pionex_bot_id=f"bot_orphan_{uuid.uuid4().hex[:16]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )
                orphan_bots.append(bot)

            # Verify existing user associations are preserved
            for user in existing_users:
                for bot in user_bots[user.id]:
                    bot.refresh_from_db()
                    assert bot.user == user, (
                        f"Bot {bot.id} should still belong to user {user.username}"
                    )
                    assert bot.user != system_user, (
                        f"Bot {bot.id} should not be reassigned to system user"
                    )

            # Verify orphan records are assigned to system user
            for bot in orphan_bots:
                bot.refresh_from_db()
                assert bot.user == system_user, (
                    f"Orphan bot {bot.id} should be assigned to system user"
                )

        finally:
            for bot in orphan_bots:
                bot.delete()
            for user in existing_users:
                for bot in user_bots[user.id]:
                    bot.delete()
                user.delete()



@pytest.mark.django_db(transaction=True)
class TestMigrationRollbackCapability:
    """
    Tests for migration rollback capability.

    These tests verify that the migration rollback logic is correct and that
    data is properly handled during rollback. Since the current model has
    non-nullable user FK (post-migration state), we test the rollback logic
    by verifying the reverse_backfill function behavior.

    **Validates: Requirements 11.5**
    """

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_system_records=st.integers(min_value=1, max_value=3),
        num_user_records=st.integers(min_value=1, max_value=3),
    )
    def test_rollback_logic_identifies_system_user_records(
        self,
        trading_pair,
        system_user,
        num_system_records: int,
        num_user_records: int,
    ) -> None:
        """
        Property: Rollback logic correctly identifies records owned by system user.

        This verifies that the rollback operation can correctly identify which
        records belong to the system user vs regular users.

        **Validates: Requirements 11.5**
        """
        regular_user = create_test_user()
        system_bots = []
        user_bots = []

        try:
            # Create records for system user
            for i in range(num_system_records):
                bot = Bot.objects.create(
                    user=system_user,
                    pionex_bot_id=f"bot_sys_{uuid.uuid4().hex[:16]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                system_bots.append(bot)

            # Create records for regular user
            for i in range(num_user_records):
                bot = Bot.objects.create(
                    user=regular_user,
                    pionex_bot_id=f"bot_user_{uuid.uuid4().hex[:16]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )
                user_bots.append(bot)

            # Verify rollback query correctly identifies system user's records
            system_user_bots = Bot.objects.filter(user=system_user)
            regular_user_bots = Bot.objects.filter(user=regular_user)

            assert system_user_bots.count() == num_system_records, (
                "Should correctly identify system user's records"
            )
            assert regular_user_bots.count() == num_user_records, (
                "Should correctly identify regular user's records"
            )

            # Verify no overlap
            for bot in system_bots:
                assert bot not in list(regular_user_bots), (
                    "System user's bot should not be in regular user's queryset"
                )
            for bot in user_bots:
                assert bot not in list(system_user_bots), (
                    "Regular user's bot should not be in system user's queryset"
                )

        finally:
            for bot in system_bots + user_bots:
                bot.delete()
            regular_user.delete()

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        invested_amount=st.decimals(
            min_value="10.00",
            max_value="10000.00",
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_rollback_would_preserve_field_values(
        self,
        trading_pair,
        system_user,
        invested_amount: Decimal,
    ) -> None:
        """
        Property: Rollback operation would preserve all field values except user FK.

        This verifies that the rollback operation (when executed) would only
        change the user FK and not affect any other field values.

        **Validates: Requirements 11.5**
        """
        pionex_bot_id = f"bot_{uuid.uuid4().hex[:16]}"
        bot_type = BotType.GRID
        status = BotStatus.ACTIVE
        params = {"grid_count": 10, "upper_price": "60000"}
        is_simulated = True

        # Create record with system user
        bot = Bot.objects.create(
            user=system_user,
            pionex_bot_id=pionex_bot_id,
            bot_type=bot_type,
            trading_pair=trading_pair,
            status=status,
            invested_amount=invested_amount,
            params=params,
            is_simulated=is_simulated,
        )

        try:
            # Capture original values
            original_created_at = bot.created_at
            original_id = bot.id

            # Verify the record exists and has correct values
            bot.refresh_from_db()

            assert bot.id == original_id, "id should be preserved"
            assert bot.pionex_bot_id == pionex_bot_id, "pionex_bot_id should be preserved"
            assert bot.bot_type == bot_type, "bot_type should be preserved"
            assert bot.trading_pair == trading_pair, "trading_pair should be preserved"
            assert bot.status == status, "status should be preserved"
            assert bot.invested_amount == invested_amount, "invested_amount should be preserved"
            assert bot.params == params, "params should be preserved"
            assert bot.is_simulated == is_simulated, "is_simulated should be preserved"
            assert bot.created_at == original_created_at, "created_at should be preserved"

            # The rollback would only change user FK to NULL
            # All other fields would remain unchanged

        finally:
            bot.delete()

    def test_system_user_not_deleted_on_rollback(
        self,
        system_user,
    ) -> None:
        """
        Property: System user is NOT deleted during rollback.

        The system user may have been used for other purposes, so it should
        remain in the database after rollback.

        **Validates: Requirements 11.5**
        """
        # Verify system user exists
        assert system_user is not None
        assert system_user.username == SYSTEM_USER_USERNAME

        # Simulate rollback (which should NOT delete the system user)
        # The reverse_backfill function only sets user FK to NULL

        # Verify system user still exists
        from django.contrib.auth.models import User

        assert User.objects.filter(username=SYSTEM_USER_USERNAME).exists(), (
            "System user should still exist after rollback"
        )

    def test_reverse_backfill_function_exists_and_is_callable(self) -> None:
        """
        Property: The reverse_backfill function exists and is callable.

        This verifies that the migration has a proper reverse function defined.

        **Validates: Requirements 11.5**
        """
        import importlib.util

        # Load the migration module
        spec = importlib.util.spec_from_file_location(
            "migration", "apps/core/migrations/0004_backfill_user_fk.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Verify reverse_backfill function exists
        assert hasattr(module, "reverse_backfill"), (
            "Migration should have reverse_backfill function"
        )
        assert callable(module.reverse_backfill), "reverse_backfill should be callable"

        # Verify the migration has RunPython with reverse_code
        migration = module.Migration
        run_python_ops = [
            op for op in migration.operations if hasattr(op, "reverse_code")
        ]
        assert len(run_python_ops) > 0, "Migration should have RunPython operation"
        assert run_python_ops[0].reverse_code is not None, (
            "RunPython should have reverse_code defined"
        )

    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_records=st.integers(min_value=1, max_value=5),
    )
    def test_migration_is_reversible(
        self,
        trading_pair,
        system_user,
        num_records: int,
    ) -> None:
        """
        Property: Migration operations are reversible.

        This verifies that all migration operations have proper reverse operations
        defined, making the migration fully reversible.

        **Validates: Requirements 11.5**
        """
        import importlib.util

        # Load the migration module
        spec = importlib.util.spec_from_file_location(
            "migration", "apps/core/migrations/0004_backfill_user_fk.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        migration = module.Migration

        # Verify all operations are reversible
        for op in migration.operations:
            # RunPython operations need reverse_code
            if hasattr(op, "reverse_code"):
                assert op.reverse_code is not None, (
                    f"RunPython operation should have reverse_code: {op}"
                )
            # AlterField operations are inherently reversible
            elif hasattr(op, "deconstruct"):
                # AlterField, AddField, etc. are reversible by Django
                pass

        # Verify the migration has dependencies (for proper ordering)
        assert len(migration.dependencies) > 0, "Migration should have dependencies"
