"""
Property-based tests for User Data Isolation.

Feature: multi-tenant-user-isolation
Properties 6-8: User Data Isolation, Cross-User Access Prevention, User Association

These tests use the hypothesis library to verify that the data isolation
layer behaves correctly across a wide range of inputs.
"""

from __future__ import annotations

import string
import uuid

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.bots.models import Bot, BotStatus, BotType
from apps.core.models import PortfolioSnapshot, TradingPair
from apps.trading.models import Trade, TradeSide

# Strategies for generating test data
username_strategy = st.text(
    alphabet=string.ascii_lowercase + string.digits,
    min_size=4,
    max_size=12,
).map(lambda x: f"user_{x}")

decimal_strategy = st.decimals(
    min_value="0.01",
    max_value="10000.00",
    places=8,
    allow_nan=False,
    allow_infinity=False,
)


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


def create_test_user(username: str = None) -> User:
    """Create a test user with a unique username."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )


@pytest.mark.django_db(transaction=True)
class TestUserDataIsolationQueryFiltering:
    """
    Property 6: User Data Isolation - Query Filtering

    *For any* user querying Bots, Trades, or PortfolioSnapshots, the returned
    results SHALL only include records where the user foreign key matches
    the authenticated user.

    **Validates: Requirements 3.2, 4.2, 5.2, 12.1, 12.3**
    """

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_user1_bots=st.integers(min_value=1, max_value=3),
        num_user2_bots=st.integers(min_value=1, max_value=3),
    )
    def test_bot_queryset_filters_by_user(
        self,
        trading_pair,
        num_user1_bots: int,
        num_user2_bots: int,
    ) -> None:
        """
        Property: Bot.objects.for_user() returns only bots owned by that user.

        **Validates: Requirements 3.2, 12.1, 12.3**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create bots for user1
            user1_bots = []
            for i in range(num_user1_bots):
                bot = Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                user1_bots.append(bot)

            # Create bots for user2
            user2_bots = []
            for i in range(num_user2_bots):
                bot = Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )
                user2_bots.append(bot)

            # Query for user1's bots
            user1_queryset = Bot.objects.for_user(user1)
            assert user1_queryset.count() == num_user1_bots
            for bot in user1_queryset:
                assert bot.user == user1

            # Query for user2's bots
            user2_queryset = Bot.objects.for_user(user2)
            assert user2_queryset.count() == num_user2_bots
            for bot in user2_queryset:
                assert bot.user == user2

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_user1_trades=st.integers(min_value=1, max_value=3),
        num_user2_trades=st.integers(min_value=1, max_value=3),
    )
    def test_trade_queryset_filters_by_user(
        self,
        trading_pair,
        num_user1_trades: int,
        num_user2_trades: int,
    ) -> None:
        """
        Property: Trade.objects.for_user() returns only trades owned by that user.

        **Validates: Requirements 4.2, 12.1, 12.3**
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
            for i in range(num_user2_trades):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="51000.00",
                    quantity="0.002",
                )

            # Query for user1's trades
            user1_queryset = Trade.objects.for_user(user1)
            assert user1_queryset.count() == num_user1_trades
            for trade in user1_queryset:
                assert trade.user == user1

            # Query for user2's trades
            user2_queryset = Trade.objects.for_user(user2)
            assert user2_queryset.count() == num_user2_trades
            for trade in user2_queryset:
                assert trade.user == user2

        finally:
            Trade.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_user1_snapshots=st.integers(min_value=1, max_value=3),
        num_user2_snapshots=st.integers(min_value=1, max_value=3),
    )
    def test_portfolio_snapshot_queryset_filters_by_user(
        self,
        num_user1_snapshots: int,
        num_user2_snapshots: int,
    ) -> None:
        """
        Property: PortfolioSnapshot.objects.for_user() returns only snapshots owned by that user.

        **Validates: Requirements 5.2, 12.1, 12.3**
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
            for i in range(num_user2_snapshots):
                PortfolioSnapshot.objects.create(
                    user=user2,
                    total_value="20000.00",
                    available_balance="10000.00",
                    allocated_to_bots="10000.00",
                    high_water_mark="20000.00",
                )

            # Query for user1's snapshots
            user1_queryset = PortfolioSnapshot.objects.for_user(user1)
            assert user1_queryset.count() == num_user1_snapshots
            for snapshot in user1_queryset:
                assert snapshot.user == user1

            # Query for user2's snapshots
            user2_queryset = PortfolioSnapshot.objects.for_user(user2)
            assert user2_queryset.count() == num_user2_snapshots
            for snapshot in user2_queryset:
                assert snapshot.user == user2

        finally:
            PortfolioSnapshot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=3),
    )
    def test_admin_bypass_returns_all_records(
        self,
        trading_pair,
        request_factory,
        num_bots: int,
    ) -> None:
        """
        Property: Admin users (is_superuser=True) see all records regardless of ownership.

        **Validates: Requirements 10.2**
        """
        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Create bots for both users
            for i in range(num_bots):
                Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )

            # Create a request with admin user
            request = request_factory.get("/")
            request.user = admin_user

            # Admin should see all bots
            queryset = Bot.objects.get_queryset()
            if hasattr(queryset, "for_request"):
                admin_queryset = queryset.for_request(request)
            else:
                # Use UserFilteredQuerySet directly
                from lib.multitenancy.managers import UserFilteredQuerySet

                admin_queryset = UserFilteredQuerySet(Bot, using="default").for_request(request)

            # Admin should see bots from both users
            assert admin_queryset.filter(user=user1).count() == num_bots
            assert admin_queryset.filter(user=user2).count() == num_bots

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=3),
    )
    def test_unauthenticated_request_returns_empty(
        self,
        trading_pair,
        request_factory,
        num_bots: int,
    ) -> None:
        """
        Property: Unauthenticated requests return empty querysets.

        **Validates: Requirements 12.1**
        """
        from django.contrib.auth.models import AnonymousUser

        user1 = create_test_user()

        try:
            # Create bots
            for i in range(num_bots):
                Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )

            # Create a request with anonymous user
            request = request_factory.get("/")
            request.user = AnonymousUser()

            # Use UserFilteredQuerySet
            from lib.multitenancy.managers import UserFilteredQuerySet

            queryset = UserFilteredQuerySet(Bot, using="default").for_request(request)

            # Unauthenticated should see nothing
            assert queryset.count() == 0

        finally:
            Bot.objects.filter(user=user1).delete()
            user1.delete()


@pytest.mark.django_db(transaction=True)
class TestCrossUserAccessPrevention:
    """
    Property 7: Cross-User Access Prevention

    *For any* user attempting to access a Bot, Trade, or PortfolioSnapshot
    owned by a different user (via direct ID lookup), the system SHALL
    return a 404 Not Found response.

    **Validates: Requirements 3.4, 4.4, 5.4, 12.4**
    """

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=3),
    )
    def test_user_cannot_access_other_users_bots_via_queryset(
        self,
        trading_pair,
        num_bots: int,
    ) -> None:
        """
        Property: User's queryset never includes bots owned by other users.

        **Validates: Requirements 3.4, 12.4**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create bots for user2
            user2_bot_ids = []
            for i in range(num_bots):
                bot = Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                user2_bot_ids.append(bot.id)

            # User1's queryset should not include user2's bots
            user1_queryset = Bot.objects.for_user(user1)

            for bot_id in user2_bot_ids:
                assert not user1_queryset.filter(id=bot_id).exists(), (
                    f"User1 should not be able to access bot {bot_id} owned by user2"
                )

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_trades=st.integers(min_value=1, max_value=3),
    )
    def test_user_cannot_access_other_users_trades_via_queryset(
        self,
        trading_pair,
        num_trades: int,
    ) -> None:
        """
        Property: User's queryset never includes trades owned by other users.

        **Validates: Requirements 4.4, 12.4**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create trades for user2
            user2_trade_ids = []
            for i in range(num_trades):
                trade = Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    quantity="0.001",
                )
                user2_trade_ids.append(trade.id)

            # User1's queryset should not include user2's trades
            user1_queryset = Trade.objects.for_user(user1)

            for trade_id in user2_trade_ids:
                assert not user1_queryset.filter(id=trade_id).exists(), (
                    f"User1 should not be able to access trade {trade_id} owned by user2"
                )

        finally:
            Trade.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_snapshots=st.integers(min_value=1, max_value=3),
    )
    def test_user_cannot_access_other_users_snapshots_via_queryset(
        self,
        num_snapshots: int,
    ) -> None:
        """
        Property: User's queryset never includes snapshots owned by other users.

        **Validates: Requirements 5.4, 12.4**
        """
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create snapshots for user2
            user2_snapshot_ids = []
            for i in range(num_snapshots):
                snapshot = PortfolioSnapshot.objects.create(
                    user=user2,
                    total_value="10000.00",
                    available_balance="5000.00",
                    allocated_to_bots="5000.00",
                    high_water_mark="10000.00",
                )
                user2_snapshot_ids.append(snapshot.id)

            # User1's queryset should not include user2's snapshots
            user1_queryset = PortfolioSnapshot.objects.for_user(user1)

            for snapshot_id in user2_snapshot_ids:
                assert not user1_queryset.filter(id=snapshot_id).exists(), (
                    f"User1 should not be able to access snapshot {snapshot_id} owned by user2"
                )

        finally:
            PortfolioSnapshot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=3),
    )
    def test_mixin_returns_404_for_cross_user_access(
        self,
        trading_pair,
        request_factory,
        num_bots: int,
    ) -> None:
        """
        Property: UserIsolationMixin returns 404 for cross-user object access.

        **Validates: Requirements 3.4, 4.4, 5.4, 12.4**
        """
        from django.http import Http404
        from rest_framework import generics

        from lib.multitenancy.mixins import UserIsolationMixin

        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create a bot for user2
            bot = Bot.objects.create(
                user=user2,
                pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            # Create a mock view with the mixin
            class MockDetailView(UserIsolationMixin, generics.RetrieveAPIView):
                queryset = Bot.objects.all()
                lookup_field = "pk"

            view = MockDetailView()
            view.kwargs = {"pk": bot.id}

            # Create request as user1
            request = request_factory.get(f"/bots/{bot.id}/")
            request.user = user1
            view.request = request

            # User1 trying to access user2's bot should get 404
            with pytest.raises(Http404):
                view.get_object()

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()


@pytest.mark.django_db(transaction=True)
class TestUserAssociationOnCreation:
    """
    Property 8: User Association on Creation

    *For any* new Bot, Trade, or PortfolioSnapshot created through the API
    or agent services, the record SHALL have its user foreign key set to
    the authenticated user who initiated the action.

    **Validates: Requirements 3.3, 4.3, 5.3, 6.4, 7.3**
    """

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        invested_amount=st.decimals(
            min_value="10.00",
            max_value="1000.00",
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_mixin_associates_bot_with_user_on_create(
        self,
        trading_pair,
        request_factory,
        invested_amount,
    ) -> None:
        """
        Property: UserIsolationMixin.perform_create() sets user on new bots.

        **Validates: Requirements 3.3**
        """
        from unittest.mock import MagicMock

        from lib.multitenancy.mixins import UserIsolationMixin

        user = create_test_user()

        try:
            # Create a mock view with the mixin
            class MockCreateView(UserIsolationMixin):
                pass

            view = MockCreateView()

            # Create request
            request = request_factory.post("/bots/")
            request.user = user
            view.request = request

            # Create a mock serializer
            mock_serializer = MagicMock()
            saved_kwargs = {}

            def capture_save(**kwargs):
                saved_kwargs.update(kwargs)

            mock_serializer.save = capture_save

            # Call perform_create
            view.perform_create(mock_serializer)

            # Verify user was passed to save
            assert "user" in saved_kwargs, "User should be passed to serializer.save()"
            assert saved_kwargs["user"] == user, "User should be the authenticated user"

        finally:
            user.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        entry_price=st.decimals(
            min_value="100.00",
            max_value="100000.00",
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_mixin_associates_trade_with_user_on_create(
        self,
        trading_pair,
        request_factory,
        entry_price,
    ) -> None:
        """
        Property: UserIsolationMixin.perform_create() sets user on new trades.

        **Validates: Requirements 4.3**
        """
        from unittest.mock import MagicMock

        from lib.multitenancy.mixins import UserIsolationMixin

        user = create_test_user()

        try:

            class MockCreateView(UserIsolationMixin):
                pass

            view = MockCreateView()

            request = request_factory.post("/trades/")
            request.user = user
            view.request = request

            mock_serializer = MagicMock()
            saved_kwargs = {}

            def capture_save(**kwargs):
                saved_kwargs.update(kwargs)

            mock_serializer.save = capture_save

            view.perform_create(mock_serializer)

            assert "user" in saved_kwargs
            assert saved_kwargs["user"] == user

        finally:
            user.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        total_value=st.decimals(
            min_value="1000.00",
            max_value="100000.00",
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_mixin_associates_snapshot_with_user_on_create(
        self,
        request_factory,
        total_value,
    ) -> None:
        """
        Property: UserIsolationMixin.perform_create() sets user on new snapshots.

        **Validates: Requirements 5.3**
        """
        from unittest.mock import MagicMock

        from lib.multitenancy.mixins import UserIsolationMixin

        user = create_test_user()

        try:

            class MockCreateView(UserIsolationMixin):
                pass

            view = MockCreateView()

            request = request_factory.post("/portfolio/")
            request.user = user
            view.request = request

            mock_serializer = MagicMock()
            saved_kwargs = {}

            def capture_save(**kwargs):
                saved_kwargs.update(kwargs)

            mock_serializer.save = capture_save

            view.perform_create(mock_serializer)

            assert "user" in saved_kwargs
            assert saved_kwargs["user"] == user

        finally:
            user.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_users=st.integers(min_value=2, max_value=4),
    )
    def test_each_user_gets_own_association(
        self,
        trading_pair,
        request_factory,
        num_users: int,
    ) -> None:
        """
        Property: Different users creating objects get their own user association.

        **Validates: Requirements 3.3, 4.3, 5.3**
        """
        from unittest.mock import MagicMock

        from lib.multitenancy.mixins import UserIsolationMixin

        users = [create_test_user() for _ in range(num_users)]

        try:

            class MockCreateView(UserIsolationMixin):
                pass

            for user in users:
                view = MockCreateView()

                request = request_factory.post("/bots/")
                request.user = user
                view.request = request

                mock_serializer = MagicMock()
                saved_kwargs = {}

                def capture_save(**kwargs):
                    saved_kwargs.update(kwargs)

                mock_serializer.save = capture_save

                view.perform_create(mock_serializer)

                assert saved_kwargs["user"] == user, (
                    f"User {user.username} should be associated with their own objects"
                )

        finally:
            for user in users:
                user.delete()

    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        invested_amount=st.decimals(
            min_value="10.00",
            max_value="1000.00",
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_custom_user_field_name_supported(
        self,
        trading_pair,
        request_factory,
        invested_amount,
    ) -> None:
        """
        Property: UserIsolationMixin supports custom user field names.

        **Validates: Requirements 3.3, 4.3, 5.3**
        """
        from unittest.mock import MagicMock

        from lib.multitenancy.mixins import UserIsolationMixin

        user = create_test_user()

        try:

            class MockCreateView(UserIsolationMixin):
                user_field = "owner"  # Custom field name

            view = MockCreateView()

            request = request_factory.post("/items/")
            request.user = user
            view.request = request

            mock_serializer = MagicMock()
            saved_kwargs = {}

            def capture_save(**kwargs):
                saved_kwargs.update(kwargs)

            mock_serializer.save = capture_save

            view.perform_create(mock_serializer)

            # Should use custom field name
            assert "owner" in saved_kwargs, "Custom user field name should be used"
            assert saved_kwargs["owner"] == user

        finally:
            user.delete()


@pytest.mark.django_db(transaction=True)
class TestTradeStatisticsUserIsolation:
    """
    Property 9: Trade Statistics User Isolation

    *For any* trade statistics calculation (total P&L, win rate, etc.),
    the computation SHALL only include trades where the user foreign key
    matches the requesting user.

    Feature: multi-tenant-user-isolation, Property 9: Trade Statistics User Isolation

    **Validates: Requirements 4.5**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_trades=st.integers(min_value=1, max_value=5),
        num_user2_trades=st.integers(min_value=1, max_value=5),
        user1_pnl_values=st.lists(
            st.decimals(
                min_value="-1000.00",
                max_value="1000.00",
                places=2,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=5,
        ),
        user2_pnl_values=st.lists(
            st.decimals(
                min_value="-1000.00",
                max_value="1000.00",
                places=2,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=5,
        ),
    )
    def test_total_pnl_only_includes_user_trades(
        self,
        trading_pair,
        num_user1_trades: int,
        num_user2_trades: int,
        user1_pnl_values,
        user2_pnl_values,
    ) -> None:
        """
        Property: Total P&L calculation only includes trades owned by the requesting user.

        Feature: multi-tenant-user-isolation, Property 9: Trade Statistics User Isolation

        **Validates: Requirements 4.5**
        """
        from decimal import Decimal

        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create closed trades for user1 with specific P&L values
            user1_expected_pnl = Decimal("0")
            for i in range(min(num_user1_trades, len(user1_pnl_values))):
                pnl = user1_pnl_values[i]
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    exit_price="51000.00",  # Closed trade
                    quantity="0.001",
                    pnl=str(pnl),
                    is_simulated=False,
                )
                user1_expected_pnl += pnl

            # Create closed trades for user2 with different P&L values
            user2_expected_pnl = Decimal("0")
            for i in range(min(num_user2_trades, len(user2_pnl_values))):
                pnl = user2_pnl_values[i]
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="52000.00",
                    exit_price="51500.00",  # Closed trade
                    quantity="0.002",
                    pnl=str(pnl),
                    is_simulated=False,
                )
                user2_expected_pnl += pnl

            # Calculate total P&L for user1's trades only
            user1_queryset = Trade.objects.for_user(user1).live()
            user1_total_pnl = user1_queryset.total_pnl()

            # Calculate total P&L for user2's trades only
            user2_queryset = Trade.objects.for_user(user2).live()
            user2_total_pnl = user2_queryset.total_pnl()

            # Verify user1's P&L only includes their trades (with tolerance for DB precision)
            # Use abs() comparison with small tolerance for floating point precision
            tolerance = Decimal("0.01")
            assert abs(user1_total_pnl - user1_expected_pnl) < tolerance, (
                f"User1's total P&L ({user1_total_pnl}) should equal sum of their trades "
                f"({user1_expected_pnl}), not include user2's trades"
            )

            # Verify user2's P&L only includes their trades
            assert abs(user2_total_pnl - user2_expected_pnl) < tolerance, (
                f"User2's total P&L ({user2_total_pnl}) should equal sum of their trades "
                f"({user2_expected_pnl}), not include user1's trades"
            )

            # Verify the totals are different (unless by coincidence they're equal)
            # This ensures we're actually testing isolation
            all_trades_pnl = Trade.objects.live().total_pnl()
            expected_total = user1_expected_pnl + user2_expected_pnl
            assert abs(all_trades_pnl - expected_total) < tolerance, (
                f"Total of all trades ({all_trades_pnl}) should equal sum of both users' "
                f"trades ({expected_total})"
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
        num_user1_winners=st.integers(min_value=0, max_value=5),
        num_user1_losers=st.integers(min_value=0, max_value=5),
        num_user2_winners=st.integers(min_value=0, max_value=5),
        num_user2_losers=st.integers(min_value=0, max_value=5),
    )
    def test_win_rate_only_includes_user_trades(
        self,
        trading_pair,
        num_user1_winners: int,
        num_user1_losers: int,
        num_user2_winners: int,
        num_user2_losers: int,
    ) -> None:
        """
        Property: Win rate calculation only includes trades owned by the requesting user.

        Feature: multi-tenant-user-isolation, Property 9: Trade Statistics User Isolation

        **Validates: Requirements 4.5**
        """
        # Skip if no trades would be created
        if num_user1_winners + num_user1_losers == 0 and num_user2_winners + num_user2_losers == 0:
            return

        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create winning trades for user1 (positive P&L)
            for i in range(num_user1_winners):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    exit_price="51000.00",
                    quantity="0.001",
                    pnl="100.00",  # Positive P&L = winner
                    is_simulated=False,
                )

            # Create losing trades for user1 (negative P&L)
            for i in range(num_user1_losers):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    exit_price="49000.00",
                    quantity="0.001",
                    pnl="-100.00",  # Negative P&L = loser
                    is_simulated=False,
                )

            # Create winning trades for user2
            for i in range(num_user2_winners):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="52000.00",
                    exit_price="51000.00",
                    quantity="0.002",
                    pnl="200.00",
                    is_simulated=False,
                )

            # Create losing trades for user2
            for i in range(num_user2_losers):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="52000.00",
                    exit_price="53000.00",
                    quantity="0.002",
                    pnl="-200.00",
                    is_simulated=False,
                )

            # Calculate expected win rates
            user1_total = num_user1_winners + num_user1_losers
            user1_expected_win_rate = (
                (num_user1_winners / user1_total * 100) if user1_total > 0 else 0.0
            )

            user2_total = num_user2_winners + num_user2_losers
            user2_expected_win_rate = (
                (num_user2_winners / user2_total * 100) if user2_total > 0 else 0.0
            )

            # Get actual win rates from user-filtered querysets
            user1_queryset = Trade.objects.for_user(user1).live()
            user1_actual_win_rate = user1_queryset.win_rate()

            user2_queryset = Trade.objects.for_user(user2).live()
            user2_actual_win_rate = user2_queryset.win_rate()

            # Verify user1's win rate only includes their trades
            assert abs(user1_actual_win_rate - user1_expected_win_rate) < 0.01, (
                f"User1's win rate ({user1_actual_win_rate:.2f}%) should equal "
                f"expected ({user1_expected_win_rate:.2f}%), not include user2's trades"
            )

            # Verify user2's win rate only includes their trades
            assert abs(user2_actual_win_rate - user2_expected_win_rate) < 0.01, (
                f"User2's win rate ({user2_actual_win_rate:.2f}%) should equal "
                f"expected ({user2_expected_win_rate:.2f}%), not include user1's trades"
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
        num_user1_open=st.integers(min_value=0, max_value=3),
        num_user1_closed=st.integers(min_value=0, max_value=3),
        num_user2_open=st.integers(min_value=0, max_value=3),
        num_user2_closed=st.integers(min_value=0, max_value=3),
    )
    def test_statistics_only_includes_user_trades(
        self,
        trading_pair,
        num_user1_open: int,
        num_user1_closed: int,
        num_user2_open: int,
        num_user2_closed: int,
    ) -> None:
        """
        Property: Comprehensive statistics only include trades owned by the requesting user.

        Feature: multi-tenant-user-isolation, Property 9: Trade Statistics User Isolation

        **Validates: Requirements 4.5**
        """
        # Skip if no trades would be created
        total_trades = num_user1_open + num_user1_closed + num_user2_open + num_user2_closed
        if total_trades == 0:
            return

        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create open trades for user1 (no exit_price)
            for i in range(num_user1_open):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    exit_price=None,  # Open position
                    quantity="0.001",
                    pnl=None,
                    is_simulated=False,
                )

            # Create closed trades for user1
            for i in range(num_user1_closed):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    exit_price="51000.00",  # Closed
                    quantity="0.001",
                    pnl="10.00",
                    is_simulated=False,
                )

            # Create open trades for user2
            for i in range(num_user2_open):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="52000.00",
                    exit_price=None,  # Open position
                    quantity="0.002",
                    pnl=None,
                    is_simulated=False,
                )

            # Create closed trades for user2
            for i in range(num_user2_closed):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="52000.00",
                    exit_price="51000.00",  # Closed
                    quantity="0.002",
                    pnl="20.00",
                    is_simulated=False,
                )

            # Get statistics for user1
            user1_stats = Trade.objects.for_user(user1).live().statistics()

            # Get statistics for user2
            user2_stats = Trade.objects.for_user(user2).live().statistics()

            # Verify user1's statistics only include their trades
            assert user1_stats["total_trades"] == num_user1_open + num_user1_closed, (
                f"User1's total_trades ({user1_stats['total_trades']}) should equal "
                f"{num_user1_open + num_user1_closed}, not include user2's trades"
            )
            assert user1_stats["open_positions"] == num_user1_open, (
                f"User1's open_positions ({user1_stats['open_positions']}) should equal "
                f"{num_user1_open}"
            )
            assert user1_stats["closed_trades"] == num_user1_closed, (
                f"User1's closed_trades ({user1_stats['closed_trades']}) should equal "
                f"{num_user1_closed}"
            )

            # Verify user2's statistics only include their trades
            assert user2_stats["total_trades"] == num_user2_open + num_user2_closed, (
                f"User2's total_trades ({user2_stats['total_trades']}) should equal "
                f"{num_user2_open + num_user2_closed}, not include user1's trades"
            )
            assert user2_stats["open_positions"] == num_user2_open, (
                f"User2's open_positions ({user2_stats['open_positions']}) should equal "
                f"{num_user2_open}"
            )
            assert user2_stats["closed_trades"] == num_user2_closed, (
                f"User2's closed_trades ({user2_stats['closed_trades']}) should equal "
                f"{num_user2_closed}"
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
        num_user1_trades=st.integers(min_value=1, max_value=5),
        num_user2_trades=st.integers(min_value=1, max_value=5),
    )
    def test_trade_statistics_view_filters_by_user(
        self,
        trading_pair,
        num_user1_trades: int,
        num_user2_trades: int,
    ) -> None:
        """
        Property: TradeStatisticsView only returns statistics for the authenticated user's trades.

        Feature: multi-tenant-user-isolation, Property 9: Trade Statistics User Isolation

        **Validates: Requirements 4.5**
        """
        from rest_framework.test import APIClient

        client = APIClient()
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
                    exit_price="51000.00",
                    quantity="0.001",
                    pnl="10.00",
                    is_simulated=False,
                )

            # Create trades for user2
            for i in range(num_user2_trades):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="52000.00",
                    exit_price="51000.00",
                    quantity="0.002",
                    pnl="20.00",
                    is_simulated=False,
                )

            # Get statistics as user1
            client.force_authenticate(user=user1)
            response = client.get("/api/v1/trades/statistics/")

            # Verify the response only includes user1's trades
            assert response.data["total_trades"] == num_user1_trades, (
                f"TradeStatisticsView should return {num_user1_trades} trades for user1, "
                f"got {response.data['total_trades']}"
            )

            # Get statistics as user2
            client.force_authenticate(user=user2)
            response = client.get("/api/v1/trades/statistics/")

            # Verify the response only includes user2's trades
            assert response.data["total_trades"] == num_user2_trades, (
                f"TradeStatisticsView should return {num_user2_trades} trades for user2, "
                f"got {response.data['total_trades']}"
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
        num_trades=st.integers(min_value=1, max_value=5),
    )
    def test_admin_sees_all_trade_statistics(
        self,
        trading_pair,
        num_trades: int,
    ) -> None:
        """
        Property: Admin users see statistics for all trades regardless of ownership.

        Feature: multi-tenant-user-isolation, Property 9: Trade Statistics User Isolation

        **Validates: Requirements 4.5, 10.2**
        """
        from rest_framework.test import APIClient

        client = APIClient()
        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Create trades for user1
            for i in range(num_trades):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    exit_price="51000.00",
                    quantity="0.001",
                    pnl="10.00",
                    is_simulated=False,
                )

            # Create trades for user2
            for i in range(num_trades):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="52000.00",
                    exit_price="51000.00",
                    quantity="0.002",
                    pnl="20.00",
                    is_simulated=False,
                )

            # Get statistics as admin
            client.force_authenticate(user=admin_user)
            response = client.get("/api/v1/trades/statistics/")

            # Admin should see all trades from both users
            expected_total = num_trades * 2
            assert response.data["total_trades"] == expected_total, (
                f"Admin should see all {expected_total} trades, "
                f"got {response.data['total_trades']}"
            )

        finally:
            Trade.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_trades=st.integers(min_value=1, max_value=5),
    )
    def test_unauthenticated_user_gets_empty_statistics(
        self,
        trading_pair,
        num_trades: int,
    ) -> None:
        """
        Property: Unauthenticated users get empty statistics.

        Feature: multi-tenant-user-isolation, Property 9: Trade Statistics User Isolation

        **Validates: Requirements 4.5**
        """
        from rest_framework.test import APIClient

        client = APIClient()
        user1 = create_test_user()

        try:
            # Create trades for user1
            for i in range(num_trades):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    exit_price="51000.00",
                    quantity="0.001",
                    pnl="10.00",
                    is_simulated=False,
                )

            # Get statistics without authentication
            client.force_authenticate(user=None)
            response = client.get("/api/v1/trades/statistics/")

            # Unauthenticated user should see no trades
            assert response.data["total_trades"] == 0, (
                f"Unauthenticated user should see 0 trades, "
                f"got {response.data['total_trades']}"
            )

        finally:
            Trade.objects.filter(user=user1).delete()
            user1.delete()


@pytest.mark.django_db(transaction=True)
class TestSignalFilteringByUserPreferences:
    """
    Property 10: Signal Filtering by User Preferences

    *For any* user viewing signals, the returned signals SHALL only include
    those for trading pairs present in the user's active_trading_pairs configuration.

    Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

    **Validates: Requirements 6.3, 6.5**
    """

    @pytest.fixture
    def trading_pairs(self, db):
        """Create multiple trading pairs for testing."""
        pairs = []
        symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT", "XRP_USDT"]
        for symbol in symbols:
            base, quote = symbol.split("_")
            pair, _ = TradingPair.objects.get_or_create(
                symbol=symbol,
                defaults={
                    "base_currency": base,
                    "quote_currency": quote,
                    "is_active": True,
                },
            )
            pairs.append(pair)
        return pairs

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        active_pairs_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=0,
            max_size=5,
            unique=True,
        ),
        signal_pairs_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    def test_signals_filtered_to_user_active_pairs(
        self,
        trading_pairs,
        active_pairs_indices: list[int],
        signal_pairs_indices: list[int],
    ) -> None:
        """
        Property: Signals returned to a user only include those for trading pairs
        in the user's active_trading_pairs configuration.

        Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

        **Validates: Requirements 6.3, 6.5**
        """
        from apps.trading.models import Signal, SignalDirection
        from rest_framework.test import APIClient

        client = APIClient()
        user = create_test_user()

        try:
            # Configure user's active trading pairs
            all_symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT", "XRP_USDT"]
            active_symbols = [all_symbols[i] for i in active_pairs_indices]
            user.profile.active_trading_pairs = active_symbols
            user.profile.save()

            # Create signals for various trading pairs
            created_signals = []
            for idx in signal_pairs_indices:
                signal = Signal.objects.create(
                    trading_pair=trading_pairs[idx],
                    direction=SignalDirection.BUY,
                    confidence=85.0,
                    indicators={"rsi": {"value": 35, "signal": "BUY"}},
                    reasoning="Test signal",
                    executed=False,
                )
                created_signals.append(signal)

            # Get signals as the user
            client.force_authenticate(user=user)
            response = client.get("/api/v1/signals/")

            # Calculate expected signals (intersection of active pairs and signal pairs)
            signal_symbols = {all_symbols[i] for i in signal_pairs_indices}
            expected_symbols = set(active_symbols) & signal_symbols

            # Verify only signals for active pairs are returned
            returned_symbols = {
                r["trading_pair"]["symbol"] for r in response.data["results"]
            }

            assert returned_symbols == expected_symbols, (
                f"User with active_pairs={active_symbols} should see signals for "
                f"{expected_symbols}, but got {returned_symbols}"
            )

            # Verify count matches
            assert len(response.data["results"]) == len(expected_symbols), (
                f"Expected {len(expected_symbols)} signals, got {len(response.data['results'])}"
            )

        finally:
            Signal.objects.filter(id__in=[s.id for s in created_signals]).delete()
            user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_signals=st.integers(min_value=1, max_value=5),
    )
    def test_user_with_empty_preferences_sees_no_signals(
        self,
        trading_pairs,
        num_signals: int,
    ) -> None:
        """
        Property: A user with no active_trading_pairs configured sees no signals.

        Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

        **Validates: Requirements 6.3, 6.5**
        """
        from apps.trading.models import Signal, SignalDirection
        from rest_framework.test import APIClient

        client = APIClient()
        user = create_test_user()

        try:
            # Configure user with empty active trading pairs
            user.profile.active_trading_pairs = []
            user.profile.save()

            # Create signals for various trading pairs
            created_signals = []
            for i in range(num_signals):
                signal = Signal.objects.create(
                    trading_pair=trading_pairs[i % len(trading_pairs)],
                    direction=SignalDirection.BUY,
                    confidence=85.0,
                    indicators={"rsi": {"value": 35, "signal": "BUY"}},
                    reasoning="Test signal",
                    executed=False,
                )
                created_signals.append(signal)

            # Get signals as the user
            client.force_authenticate(user=user)
            response = client.get("/api/v1/signals/")

            # User with no preferences should see no signals
            assert len(response.data["results"]) == 0, (
                f"User with empty active_trading_pairs should see 0 signals, "
                f"got {len(response.data['results'])}"
            )

        finally:
            Signal.objects.filter(id__in=[s.id for s in created_signals]).delete()
            user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        user1_pairs_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=1,
            max_size=3,
            unique=True,
        ),
        user2_pairs_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=1,
            max_size=3,
            unique=True,
        ),
    )
    def test_different_users_see_different_signals_based_on_preferences(
        self,
        trading_pairs,
        user1_pairs_indices: list[int],
        user2_pairs_indices: list[int],
    ) -> None:
        """
        Property: Different users with different active_trading_pairs configurations
        see different subsets of signals.

        Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

        **Validates: Requirements 6.3, 6.5**
        """
        from apps.trading.models import Signal, SignalDirection
        from rest_framework.test import APIClient

        client = APIClient()
        user1 = create_test_user()
        user2 = create_test_user()

        try:
            all_symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT", "XRP_USDT"]

            # Configure different active trading pairs for each user
            user1_symbols = [all_symbols[i] for i in user1_pairs_indices]
            user2_symbols = [all_symbols[i] for i in user2_pairs_indices]

            user1.profile.active_trading_pairs = user1_symbols
            user1.profile.save()

            user2.profile.active_trading_pairs = user2_symbols
            user2.profile.save()

            # Create signals for all trading pairs
            created_signals = []
            for pair in trading_pairs:
                signal = Signal.objects.create(
                    trading_pair=pair,
                    direction=SignalDirection.BUY,
                    confidence=85.0,
                    indicators={"rsi": {"value": 35, "signal": "BUY"}},
                    reasoning="Test signal",
                    executed=False,
                )
                created_signals.append(signal)

            # Get signals as user1
            client.force_authenticate(user=user1)
            response1 = client.get("/api/v1/signals/")
            user1_returned_symbols = {
                r["trading_pair"]["symbol"] for r in response1.data["results"]
            }

            # Get signals as user2
            client.force_authenticate(user=user2)
            response2 = client.get("/api/v1/signals/")
            user2_returned_symbols = {
                r["trading_pair"]["symbol"] for r in response2.data["results"]
            }

            # Verify each user sees only their configured pairs
            assert user1_returned_symbols == set(user1_symbols), (
                f"User1 with active_pairs={user1_symbols} should see signals for "
                f"{set(user1_symbols)}, but got {user1_returned_symbols}"
            )

            assert user2_returned_symbols == set(user2_symbols), (
                f"User2 with active_pairs={user2_symbols} should see signals for "
                f"{set(user2_symbols)}, but got {user2_returned_symbols}"
            )

        finally:
            Signal.objects.filter(id__in=[s.id for s in created_signals]).delete()
            user1.delete()
            user2.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_signals=st.integers(min_value=1, max_value=5),
    )
    def test_admin_sees_all_signals_regardless_of_preferences(
        self,
        trading_pairs,
        num_signals: int,
    ) -> None:
        """
        Property: Admin users (is_superuser=True) see all signals regardless of
        their active_trading_pairs configuration.

        Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

        **Validates: Requirements 6.3, 6.5, 10.2**
        """
        from apps.trading.models import Signal, SignalDirection
        from rest_framework.test import APIClient

        client = APIClient()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Configure admin with limited active trading pairs
            admin_user.profile.active_trading_pairs = ["BTC_USDT"]
            admin_user.profile.save()

            # Create signals for various trading pairs
            created_signals = []
            used_pairs = set()
            for i in range(num_signals):
                pair = trading_pairs[i % len(trading_pairs)]
                signal = Signal.objects.create(
                    trading_pair=pair,
                    direction=SignalDirection.BUY,
                    confidence=85.0,
                    indicators={"rsi": {"value": 35, "signal": "BUY"}},
                    reasoning="Test signal",
                    executed=False,
                )
                created_signals.append(signal)
                used_pairs.add(pair.symbol)

            # Get signals as admin
            client.force_authenticate(user=admin_user)
            response = client.get("/api/v1/signals/")

            # Admin should see all signals regardless of preferences
            returned_symbols = {
                r["trading_pair"]["symbol"] for r in response.data["results"]
            }

            assert returned_symbols == used_pairs, (
                f"Admin should see all signals for {used_pairs}, "
                f"but got {returned_symbols}"
            )

            assert len(response.data["results"]) == num_signals, (
                f"Admin should see all {num_signals} signals, "
                f"got {len(response.data['results'])}"
            )

        finally:
            Signal.objects.filter(id__in=[s.id for s in created_signals]).delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_signals=st.integers(min_value=1, max_value=5),
    )
    def test_unauthenticated_user_sees_all_signals(
        self,
        trading_pairs,
        num_signals: int,
    ) -> None:
        """
        Property: Unauthenticated users see all signals (public market data).

        Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

        **Validates: Requirements 6.3**
        """
        from apps.trading.models import Signal, SignalDirection
        from rest_framework.test import APIClient

        client = APIClient()

        try:
            # Create signals for various trading pairs
            created_signals = []
            used_pairs = set()
            for i in range(num_signals):
                pair = trading_pairs[i % len(trading_pairs)]
                signal = Signal.objects.create(
                    trading_pair=pair,
                    direction=SignalDirection.BUY,
                    confidence=85.0,
                    indicators={"rsi": {"value": 35, "signal": "BUY"}},
                    reasoning="Test signal",
                    executed=False,
                )
                created_signals.append(signal)
                used_pairs.add(pair.symbol)

            # Get signals without authentication
            response = client.get("/api/v1/signals/")

            # Unauthenticated user should see all signals
            returned_symbols = {
                r["trading_pair"]["symbol"] for r in response.data["results"]
            }

            assert returned_symbols == used_pairs, (
                f"Unauthenticated user should see all signals for {used_pairs}, "
                f"but got {returned_symbols}"
            )

            assert len(response.data["results"]) == num_signals, (
                f"Unauthenticated user should see all {num_signals} signals, "
                f"got {len(response.data['results'])}"
            )

        finally:
            Signal.objects.filter(id__in=[s.id for s in created_signals]).delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        active_pairs_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=1,
            max_size=3,
            unique=True,
        ),
        num_signals_per_pair=st.integers(min_value=1, max_value=3),
    )
    def test_signal_count_matches_active_pairs_signals(
        self,
        trading_pairs,
        active_pairs_indices: list[int],
        num_signals_per_pair: int,
    ) -> None:
        """
        Property: The number of signals returned equals the number of signals
        that exist for the user's active trading pairs.

        Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

        **Validates: Requirements 6.3, 6.5**
        """
        from apps.trading.models import Signal, SignalDirection
        from rest_framework.test import APIClient

        client = APIClient()
        user = create_test_user()

        try:
            all_symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT", "XRP_USDT"]

            # Configure user's active trading pairs
            active_symbols = [all_symbols[i] for i in active_pairs_indices]
            user.profile.active_trading_pairs = active_symbols
            user.profile.save()

            # Create multiple signals for each trading pair
            created_signals = []
            for pair in trading_pairs:
                for _ in range(num_signals_per_pair):
                    signal = Signal.objects.create(
                        trading_pair=pair,
                        direction=SignalDirection.BUY,
                        confidence=85.0,
                        indicators={"rsi": {"value": 35, "signal": "BUY"}},
                        reasoning="Test signal",
                        executed=False,
                    )
                    created_signals.append(signal)

            # Get signals as the user
            client.force_authenticate(user=user)
            response = client.get("/api/v1/signals/")

            # Calculate expected count
            expected_count = len(active_pairs_indices) * num_signals_per_pair

            # Verify count matches
            assert len(response.data["results"]) == expected_count, (
                f"User with {len(active_pairs_indices)} active pairs and "
                f"{num_signals_per_pair} signals per pair should see "
                f"{expected_count} signals, got {len(response.data['results'])}"
            )

        finally:
            Signal.objects.filter(id__in=[s.id for s in created_signals]).delete()
            user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        active_pairs_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=1,
            max_size=3,
            unique=True,
        ),
    )
    def test_signal_filtering_with_nonexistent_pairs_in_preferences(
        self,
        trading_pairs,
        active_pairs_indices: list[int],
    ) -> None:
        """
        Property: When user has preferences for non-existent pairs mixed with
        valid pairs, only signals for valid pairs are returned.

        Feature: multi-tenant-user-isolation, Property 10: Signal Filtering by User Preferences

        **Validates: Requirements 6.3, 6.5**
        """
        from apps.trading.models import Signal, SignalDirection
        from rest_framework.test import APIClient

        client = APIClient()
        user = create_test_user()

        try:
            all_symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT", "XRP_USDT"]

            # Configure user with mix of valid and non-existent pairs
            valid_symbols = [all_symbols[i] for i in active_pairs_indices]
            nonexistent_symbols = ["FAKE_USDT", "INVALID_USDT"]
            user.profile.active_trading_pairs = valid_symbols + nonexistent_symbols
            user.profile.save()

            # Create signals for all trading pairs
            created_signals = []
            for pair in trading_pairs:
                signal = Signal.objects.create(
                    trading_pair=pair,
                    direction=SignalDirection.BUY,
                    confidence=85.0,
                    indicators={"rsi": {"value": 35, "signal": "BUY"}},
                    reasoning="Test signal",
                    executed=False,
                )
                created_signals.append(signal)

            # Get signals as the user
            client.force_authenticate(user=user)
            response = client.get("/api/v1/signals/")

            # Verify only signals for valid pairs are returned
            returned_symbols = {
                r["trading_pair"]["symbol"] for r in response.data["results"]
            }

            assert returned_symbols == set(valid_symbols), (
                f"User with preferences including non-existent pairs should only see "
                f"signals for valid pairs {set(valid_symbols)}, but got {returned_symbols}"
            )

            # Verify no signals for non-existent pairs
            for symbol in nonexistent_symbols:
                assert symbol not in returned_symbols, (
                    f"Non-existent pair {symbol} should not appear in results"
                )

        finally:
            Signal.objects.filter(id__in=[s.id for s in created_signals]).delete()
            user.delete()


@pytest.mark.django_db(transaction=True)
class TestAdminUserFilterBypass:
    """
    Property 16: Admin User Filter Bypass

    *For any* admin user (is_superuser=True) querying Bots, Trades, or PortfolioSnapshots,
    the returned results SHALL include all records regardless of ownership.

    Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

    **Validates: Requirements 10.2**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_bots=st.integers(min_value=1, max_value=3),
        num_user2_bots=st.integers(min_value=1, max_value=3),
    )
    def test_admin_sees_all_bots_via_for_request(
        self,
        trading_pair,
        request_factory,
        num_user1_bots: int,
        num_user2_bots: int,
    ) -> None:
        """
        Property: Admin users see all bots regardless of ownership via for_request().

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from lib.multitenancy.managers import UserFilteredQuerySet

        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

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

            # Create request with admin user
            request = request_factory.get("/")
            request.user = admin_user

            # Admin should see all bots via for_request
            admin_queryset = UserFilteredQuerySet(Bot, using="default").for_request(request)

            # Verify admin sees all bots from both users
            total_expected = num_user1_bots + num_user2_bots
            assert admin_queryset.count() == total_expected, (
                f"Admin should see all {total_expected} bots, got {admin_queryset.count()}"
            )
            assert admin_queryset.filter(user=user1).count() == num_user1_bots
            assert admin_queryset.filter(user=user2).count() == num_user2_bots

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_trades=st.integers(min_value=1, max_value=3),
        num_user2_trades=st.integers(min_value=1, max_value=3),
    )
    def test_admin_sees_all_trades_via_for_request(
        self,
        trading_pair,
        request_factory,
        num_user1_trades: int,
        num_user2_trades: int,
    ) -> None:
        """
        Property: Admin users see all trades regardless of ownership via for_request().

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from lib.multitenancy.managers import UserFilteredQuerySet

        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

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
            for i in range(num_user2_trades):
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="51000.00",
                    quantity="0.002",
                )

            # Create request with admin user
            request = request_factory.get("/")
            request.user = admin_user

            # Admin should see all trades via for_request
            admin_queryset = UserFilteredQuerySet(Trade, using="default").for_request(request)

            # Verify admin sees all trades from both users
            total_expected = num_user1_trades + num_user2_trades
            assert admin_queryset.count() == total_expected, (
                f"Admin should see all {total_expected} trades, got {admin_queryset.count()}"
            )
            assert admin_queryset.filter(user=user1).count() == num_user1_trades
            assert admin_queryset.filter(user=user2).count() == num_user2_trades

        finally:
            Trade.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_user1_snapshots=st.integers(min_value=1, max_value=3),
        num_user2_snapshots=st.integers(min_value=1, max_value=3),
    )
    def test_admin_sees_all_portfolio_snapshots_via_for_request(
        self,
        request_factory,
        num_user1_snapshots: int,
        num_user2_snapshots: int,
    ) -> None:
        """
        Property: Admin users see all portfolio snapshots regardless of ownership via for_request().

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from lib.multitenancy.managers import UserFilteredQuerySet

        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

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
            for i in range(num_user2_snapshots):
                PortfolioSnapshot.objects.create(
                    user=user2,
                    total_value="20000.00",
                    available_balance="10000.00",
                    allocated_to_bots="10000.00",
                    high_water_mark="20000.00",
                )

            # Create request with admin user
            request = request_factory.get("/")
            request.user = admin_user

            # Admin should see all snapshots via for_request
            admin_queryset = UserFilteredQuerySet(
                PortfolioSnapshot, using="default"
            ).for_request(request)

            # Verify admin sees all snapshots from both users
            total_expected = num_user1_snapshots + num_user2_snapshots
            assert admin_queryset.count() == total_expected, (
                f"Admin should see all {total_expected} snapshots, got {admin_queryset.count()}"
            )
            assert admin_queryset.filter(user=user1).count() == num_user1_snapshots
            assert admin_queryset.filter(user=user2).count() == num_user2_snapshots

        finally:
            PortfolioSnapshot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=2, max_value=4),
        records_per_user=st.integers(min_value=1, max_value=3),
    )
    def test_admin_sees_all_records_from_multiple_users(
        self,
        trading_pair,
        request_factory,
        num_users: int,
        records_per_user: int,
    ) -> None:
        """
        Property: Admin users see all records from any number of users.

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from lib.multitenancy.managers import UserFilteredQuerySet

        users = [create_test_user() for _ in range(num_users)]
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Create bots for each user
            for user in users:
                for i in range(records_per_user):
                    Bot.objects.create(
                        user=user,
                        pionex_bot_id=f"bot_{user.id}_{uuid.uuid4().hex[:8]}",
                        bot_type=BotType.GRID,
                        trading_pair=trading_pair,
                        status=BotStatus.ACTIVE,
                        invested_amount="100.00",
                    )

            # Create request with admin user
            request = request_factory.get("/")
            request.user = admin_user

            # Admin should see all bots
            admin_queryset = UserFilteredQuerySet(Bot, using="default").for_request(request)

            total_expected = num_users * records_per_user
            assert admin_queryset.count() == total_expected, (
                f"Admin should see all {total_expected} bots from {num_users} users, "
                f"got {admin_queryset.count()}"
            )

            # Verify each user's bots are included
            for user in users:
                assert admin_queryset.filter(user=user).count() == records_per_user, (
                    f"Admin should see {records_per_user} bots for user {user.id}"
                )

        finally:
            Bot.objects.filter(user__in=users).delete()
            for user in users:
                user.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=3),
        num_trades=st.integers(min_value=1, max_value=3),
        num_snapshots=st.integers(min_value=1, max_value=3),
    )
    def test_admin_bypass_works_for_all_model_types_simultaneously(
        self,
        trading_pair,
        request_factory,
        num_bots: int,
        num_trades: int,
        num_snapshots: int,
    ) -> None:
        """
        Property: Admin bypass works consistently across all user-owned model types.

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from lib.multitenancy.managers import UserFilteredQuerySet

        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Create bots for both users
            for user in [user1, user2]:
                for i in range(num_bots):
                    Bot.objects.create(
                        user=user,
                        pionex_bot_id=f"bot_{user.id}_{uuid.uuid4().hex[:8]}",
                        bot_type=BotType.GRID,
                        trading_pair=trading_pair,
                        status=BotStatus.ACTIVE,
                        invested_amount="100.00",
                    )

            # Create trades for both users
            for user in [user1, user2]:
                for i in range(num_trades):
                    Trade.objects.create(
                        user=user,
                        trading_pair=trading_pair,
                        side=TradeSide.BUY,
                        entry_price="50000.00",
                        quantity="0.001",
                    )

            # Create snapshots for both users
            for user in [user1, user2]:
                for i in range(num_snapshots):
                    PortfolioSnapshot.objects.create(
                        user=user,
                        total_value="10000.00",
                        available_balance="5000.00",
                        allocated_to_bots="5000.00",
                        high_water_mark="10000.00",
                    )

            # Create request with admin user
            request = request_factory.get("/")
            request.user = admin_user

            # Admin should see all records of each type
            bot_queryset = UserFilteredQuerySet(Bot, using="default").for_request(request)
            trade_queryset = UserFilteredQuerySet(Trade, using="default").for_request(request)
            snapshot_queryset = UserFilteredQuerySet(
                PortfolioSnapshot, using="default"
            ).for_request(request)

            # Verify counts
            assert bot_queryset.count() == num_bots * 2, (
                f"Admin should see {num_bots * 2} bots, got {bot_queryset.count()}"
            )
            assert trade_queryset.count() == num_trades * 2, (
                f"Admin should see {num_trades * 2} trades, got {trade_queryset.count()}"
            )
            assert snapshot_queryset.count() == num_snapshots * 2, (
                f"Admin should see {num_snapshots * 2} snapshots, got {snapshot_queryset.count()}"
            )

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            Trade.objects.filter(user__in=[user1, user2]).delete()
            PortfolioSnapshot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_bots=st.integers(min_value=1, max_value=3),
    )
    def test_regular_user_does_not_get_admin_bypass(
        self,
        trading_pair,
        request_factory,
        num_bots: int,
    ) -> None:
        """
        Property: Regular users (is_superuser=False) do NOT get admin bypass.

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from lib.multitenancy.managers import UserFilteredQuerySet

        user1 = create_test_user()
        user2 = create_test_user()

        try:
            # Create bots for user1
            for i in range(num_bots):
                Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )

            # Create bots for user2
            for i in range(num_bots):
                Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )

            # Create request with regular user1 (not admin)
            request = request_factory.get("/")
            request.user = user1

            # Regular user should only see their own bots
            user1_queryset = UserFilteredQuerySet(Bot, using="default").for_request(request)

            assert user1_queryset.count() == num_bots, (
                f"Regular user should only see their {num_bots} bots, "
                f"got {user1_queryset.count()}"
            )
            assert user1_queryset.filter(user=user2).count() == 0, (
                "Regular user should not see other user's bots"
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
        num_bots=st.integers(min_value=1, max_value=3),
    )
    def test_admin_bypass_via_api_endpoint_bots(
        self,
        trading_pair,
        num_bots: int,
    ) -> None:
        """
        Property: Admin users see all bots via API endpoint.

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from rest_framework.test import APIClient

        client = APIClient()
        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Create bots for both users
            for i in range(num_bots):
                Bot.objects.create(
                    user=user1,
                    pionex_bot_id=f"bot_u1_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                Bot.objects.create(
                    user=user2,
                    pionex_bot_id=f"bot_u2_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.DCA,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="200.00",
                )

            # Get bots as admin via API
            client.force_authenticate(user=admin_user)
            response = client.get("/api/v1/bots/")

            # Admin should see all bots
            total_expected = num_bots * 2
            assert response.data["count"] == total_expected, (
                f"Admin should see all {total_expected} bots via API, "
                f"got {response.data['count']}"
            )

        finally:
            Bot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_trades=st.integers(min_value=1, max_value=3),
    )
    def test_admin_bypass_via_api_endpoint_trades(
        self,
        trading_pair,
        num_trades: int,
    ) -> None:
        """
        Property: Admin users see all trades via API endpoint.

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from rest_framework.test import APIClient

        client = APIClient()
        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Create trades for both users
            for i in range(num_trades):
                Trade.objects.create(
                    user=user1,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    quantity="0.001",
                )
                Trade.objects.create(
                    user=user2,
                    trading_pair=trading_pair,
                    side=TradeSide.SELL,
                    entry_price="51000.00",
                    quantity="0.002",
                )

            # Get trades as admin via API
            client.force_authenticate(user=admin_user)
            response = client.get("/api/v1/trades/")

            # Admin should see all trades
            total_expected = num_trades * 2
            assert response.data["count"] == total_expected, (
                f"Admin should see all {total_expected} trades via API, "
                f"got {response.data['count']}"
            )

        finally:
            Trade.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_snapshots=st.integers(min_value=1, max_value=3),
    )
    def test_admin_bypass_via_api_endpoint_portfolio(
        self,
        num_snapshots: int,
    ) -> None:
        """
        Property: Admin users see all portfolio snapshots via API endpoint.

        Feature: multi-tenant-user-isolation, Property 16: Admin User Filter Bypass

        **Validates: Requirements 10.2**
        """
        from rest_framework.test import APIClient

        client = APIClient()
        user1 = create_test_user()
        user2 = create_test_user()
        admin_user = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email="admin@example.com",
            password="adminpass",
        )

        try:
            # Create snapshots for both users
            for i in range(num_snapshots):
                PortfolioSnapshot.objects.create(
                    user=user1,
                    total_value="10000.00",
                    available_balance="5000.00",
                    allocated_to_bots="5000.00",
                    high_water_mark="10000.00",
                )
                PortfolioSnapshot.objects.create(
                    user=user2,
                    total_value="20000.00",
                    available_balance="10000.00",
                    allocated_to_bots="10000.00",
                    high_water_mark="20000.00",
                )

            # Get portfolio history as admin via API
            client.force_authenticate(user=admin_user)
            response = client.get("/api/v1/portfolio/history/")

            # Admin should see all snapshots
            total_expected = num_snapshots * 2
            assert response.data["count"] == total_expected, (
                f"Admin should see all {total_expected} snapshots via API, "
                f"got {response.data['count']}"
            )

        finally:
            PortfolioSnapshot.objects.filter(user__in=[user1, user2]).delete()
            user1.delete()
            user2.delete()
            admin_user.delete()
