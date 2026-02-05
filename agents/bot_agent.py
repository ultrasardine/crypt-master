"""
Bot Management Agent Service.

This module implements the BotManagementAgent, a long-running service that:
1. Subscribes to signals from Redis
2. Evaluates existing bots performance
3. Creates/stops bots based on signals and risk rules
4. Updates bot status in PostgreSQL
5. Enforces risk limits (drawdown, position sizing)

Requirements:
- 10.3: Create Grid Bot when market analysis indicates favorable conditions
- 10.4: Create DCA Bot when market analysis indicates favorable conditions for accumulation
- 10.5: Stop bot when trading pair shows unfavorable signals
- 10.6: Close all open orders and return funds when stopping bot
- 10.8: Flag/auto-stop underperforming bots
- 10.9: Support modifying bot parameters when market conditions change
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import django
import redis.asyncio as aioredis

# Setup Django before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.utils import timezone as django_timezone

from django.contrib.auth.models import User

from apps.bots.models import Bot, BotEvent, BotStatus, BotType
from apps.core.models import TradingPair, UserProfile
from lib.analysis.signal import Signal
from lib.pionex.client_factory import MissingAPIKeysError, PionexClientFactory
from lib.analysis.technical import SignalDirection
from lib.logging import (
    LoggingConfig,
    get_bot_logger,
    get_system_logger,
    setup_logging,
)
from lib.crypto.api_key_manager import APIKeyManager
from lib.messaging.signals import SignalMessage, SignalSubscriber
from lib.messaging.websocket import get_broadcaster
from lib.pionex.client import PionexClient
from lib.pionex.models import DCABotParams, GridBotParams
from lib.risk import RiskManager, RiskManagerConfig
from lib.simulation import DryRunSimulator

logger = logging.getLogger(__name__)
bot_logger = get_bot_logger()
system_logger = get_system_logger()


# Redis channel for signals
SIGNALS_CHANNEL = "signals"

# Bot events channel for dashboard updates
BOT_EVENTS_CHANNEL = "bot-events"

# Default evaluation interval (seconds)
DEFAULT_EVALUATION_INTERVAL = 300  # 5 minutes

# Default rate limit settings
DEFAULT_RATE_LIMIT_CALLS = 10  # Max API calls per window
DEFAULT_RATE_LIMIT_WINDOW = 60  # Window size in seconds


@dataclass
class UserRateLimitState:
    """Tracks rate limit state for a single user."""

    user_id: int
    call_timestamps: list[float]

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.call_timestamps = []


class PerUserRateLimiter:
    """
    Per-user rate limiter for API calls.

    Tracks API calls per user and enforces rate limits to prevent
    API quota exhaustion.

    Requirements:
        - 7.6: Implement rate limiting per user to prevent API quota exhaustion
    """

    def __init__(
        self,
        max_calls: int = DEFAULT_RATE_LIMIT_CALLS,
        window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW,
    ):
        """
        Initialize the rate limiter.

        Args:
            max_calls: Maximum number of API calls allowed per window
            window_seconds: Size of the rate limit window in seconds
        """
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._user_states: dict[int, UserRateLimitState] = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, user_id: int) -> bool:
        """
        Check if a user is within their rate limit.

        Args:
            user_id: The user's ID

        Returns:
            True if the user can make an API call, False if rate limited
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            state = self._get_or_create_state(user_id)

            # Remove timestamps outside the window
            cutoff = now - self._window_seconds
            state.call_timestamps = [ts for ts in state.call_timestamps if ts > cutoff]

            return len(state.call_timestamps) < self._max_calls

    async def record_call(self, user_id: int) -> None:
        """
        Record an API call for a user.

        Args:
            user_id: The user's ID
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            state = self._get_or_create_state(user_id)
            state.call_timestamps.append(now)

    async def get_wait_time(self, user_id: int) -> float:
        """
        Get the time to wait before the user can make another call.

        Args:
            user_id: The user's ID

        Returns:
            Seconds to wait, or 0 if no wait needed
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            state = self._get_or_create_state(user_id)

            # Remove timestamps outside the window
            cutoff = now - self._window_seconds
            state.call_timestamps = [ts for ts in state.call_timestamps if ts > cutoff]

            if len(state.call_timestamps) < self._max_calls:
                return 0.0

            # Calculate when the oldest call will expire
            oldest = min(state.call_timestamps)
            return max(0.0, oldest + self._window_seconds - now)

    def _get_or_create_state(self, user_id: int) -> UserRateLimitState:
        """Get or create rate limit state for a user."""
        if user_id not in self._user_states:
            self._user_states[user_id] = UserRateLimitState(user_id)
        return self._user_states[user_id]

    def get_call_count(self, user_id: int) -> int:
        """
        Get the current call count for a user within the window.

        Args:
            user_id: The user's ID

        Returns:
            Number of calls made in the current window
        """
        if user_id not in self._user_states:
            return 0

        now = asyncio.get_event_loop().time()
        cutoff = now - self._window_seconds
        state = self._user_states[user_id]
        return len([ts for ts in state.call_timestamps if ts > cutoff])


@dataclass
class BotAgentConfig:
    """
    Configuration for BotManagementAgent.

    Attributes:
        dry_run: Whether to run in dry-run mode (no real API calls)
        evaluation_interval: Seconds between bot performance evaluations
        min_confidence_for_bot: Minimum signal confidence to create a bot
        bot_loss_threshold_pct: P&L threshold for flagging underperforming bots
        auto_stop_underperforming: Whether to auto-stop underperforming bots
        max_bots_per_symbol: Maximum number of active bots per trading pair
        grid_bot_grid_count: Default number of grids for grid bots
        grid_bot_price_range_pct: Price range as percentage of current price
        dca_interval_hours: Default interval for DCA bots
        dca_orders_count: Default number of DCA orders
        rate_limit_calls: Maximum API calls per user per window
        rate_limit_window: Rate limit window size in seconds
    """

    dry_run: bool = True
    evaluation_interval: int = DEFAULT_EVALUATION_INTERVAL
    min_confidence_for_bot: float = 85.0
    bot_loss_threshold_pct: float = 0.10
    auto_stop_underperforming: bool = True
    max_bots_per_symbol: int = 2
    grid_bot_grid_count: int = 10
    grid_bot_price_range_pct: float = 0.10
    dca_interval_hours: int = 24
    dca_orders_count: int = 10
    rate_limit_calls: int = DEFAULT_RATE_LIMIT_CALLS
    rate_limit_window: int = DEFAULT_RATE_LIMIT_WINDOW

    @classmethod
    def from_settings(cls) -> BotAgentConfig:
        """Create config from Django settings."""
        return cls(
            dry_run=getattr(settings, "DRY_RUN", True),
            evaluation_interval=getattr(
                settings, "BOT_EVALUATION_INTERVAL", DEFAULT_EVALUATION_INTERVAL
            ),
            min_confidence_for_bot=getattr(settings, "RISK_MIN_CONFIDENCE", 0.85) * 100,
            bot_loss_threshold_pct=getattr(settings, "BOT_LOSS_THRESHOLD_PCT", 0.10),
            auto_stop_underperforming=getattr(settings, "AUTO_STOP_UNDERPERFORMING_BOTS", True),
            max_bots_per_symbol=getattr(settings, "MAX_BOTS_PER_SYMBOL", 2),
            rate_limit_calls=getattr(settings, "RATE_LIMIT_CALLS_PER_USER", DEFAULT_RATE_LIMIT_CALLS),
            rate_limit_window=getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", DEFAULT_RATE_LIMIT_WINDOW),
        )


class BotManagementAgent:
    """
    Long-running service for bot lifecycle management.

    This agent continuously:
    1. Subscribes to signals from Redis published by market analysis agent
    2. Evaluates existing bot performance periodically
    3. Creates new bots when signals indicate favorable conditions
    4. Stops bots when signals turn unfavorable or performance degrades
    5. Enforces risk limits on all bot operations

    Requirements:
        - 10.3: Create Grid Bot for range-bound markets
        - 10.4: Create DCA Bot for accumulation
        - 10.5: Stop bot when signals turn unfavorable
        - 10.6: Close all open orders when stopping bot
        - 10.8: Flag/auto-stop underperforming bots
        - 10.9: Support modifying bot parameters

    Example:
        >>> agent = BotManagementAgent()
        >>> await agent.run()  # Runs until stopped
    """

    def __init__(
        self,
        config: BotAgentConfig | None = None,
        pionex_client: PionexClient | None = None,
        redis_client: aioredis.Redis | None = None,
        risk_manager: RiskManager | None = None,
        simulator: DryRunSimulator | None = None,
        client_factory: PionexClientFactory | None = None,
    ) -> None:
        """
        Initialize the BotManagementAgent.

        Args:
            config: Agent configuration (uses defaults from settings if None)
            pionex_client: Optional Pionex client for dependency injection (legacy)
            redis_client: Optional Redis client for dependency injection
            risk_manager: Optional RiskManager for dependency injection
            simulator: Optional DryRunSimulator for dry-run mode
            client_factory: Optional PionexClientFactory for multi-user support
        """
        self.config = config or BotAgentConfig.from_settings()
        self._pionex_client = pionex_client
        self._redis_client = redis_client
        self._owns_pionex = pionex_client is None
        self._owns_redis = redis_client is None

        # Initialize client factory for multi-user support
        if client_factory is None:
            api_key_manager = APIKeyManager(master_key=settings.SECRET_KEY)
            self._client_factory = PionexClientFactory(api_key_manager)
        else:
            self._client_factory = client_factory

        # Initialize risk manager
        if risk_manager is None:
            risk_config = RiskManagerConfig(
                bot_loss_threshold_pct=self.config.bot_loss_threshold_pct,
                min_confidence=self.config.min_confidence_for_bot,
            )
            self._risk_manager = RiskManager(config=risk_config)
        else:
            self._risk_manager = risk_manager

        # Initialize simulator for dry-run mode
        self._simulator = simulator or DryRunSimulator() if self.config.dry_run else None

        # Initialize per-user rate limiter
        self._rate_limiter = PerUserRateLimiter(
            max_calls=self.config.rate_limit_calls,
            window_seconds=self.config.rate_limit_window,
        )

        self._running = False
        self._shutdown_event = asyncio.Event()
        self._signal_subscriber: SignalSubscriber | None = None

    async def _get_pionex_client(self) -> PionexClient:
        """Get or create the Pionex client."""
        if self._pionex_client is None:
            api_key = getattr(settings, "PIONEX_API_KEY", "")
            api_secret = getattr(settings, "PIONEX_API_SECRET", "")

            if not api_key or not api_secret:
                raise ValueError("PIONEX_API_KEY and PIONEX_API_SECRET must be set in environment")

            self._pionex_client = PionexClient(
                api_key=api_key,
                api_secret=api_secret,
            )
            await self._pionex_client._ensure_client()

        return self._pionex_client

    async def _get_redis_client(self) -> aioredis.Redis:
        """Get or create the Redis client."""
        if self._redis_client is None:
            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
            self._redis_client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis_client

    async def close(self) -> None:
        """Close all clients and resources."""
        if self._signal_subscriber is not None:
            self._signal_subscriber.stop()
            await self._signal_subscriber.close()
            self._signal_subscriber = None

        if self._owns_pionex and self._pionex_client is not None:
            await self._pionex_client.close()
            self._pionex_client = None

        if self._owns_redis and self._redis_client is not None:
            await self._redis_client.close()
            self._redis_client = None

    async def __aenter__(self) -> BotManagementAgent:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def run(self) -> None:
        """
        Main event loop for the bot management agent.

        Subscribes to signals from Redis and handles them as they arrive.
        Also periodically evaluates existing bot performance.
        """
        self._running = True
        logger.info(f"BotManagementAgent starting (dry_run={self.config.dry_run})...")

        try:
            # Initialize portfolio state
            await self._initialize_portfolio_state()

            # Start signal listener and evaluation tasks
            signal_task = asyncio.create_task(self._signal_listener())
            evaluation_task = asyncio.create_task(self._evaluation_loop())

            # Wait for shutdown or task completion
            done, pending = await asyncio.wait(
                [signal_task, evaluation_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Check for exceptions in completed tasks
            for task in done:
                if task.exception():
                    logger.error(f"Task failed with exception: {task.exception()}")
        finally:
            self._running = False
            logger.info("BotManagementAgent stopped")

    async def shutdown(self) -> None:
        """Signal the agent to stop gracefully."""
        logger.info("Shutdown requested...")
        self._running = False
        self._shutdown_event.set()
        if self._signal_subscriber:
            self._signal_subscriber.stop()

    async def _initialize_portfolio_state(self) -> None:
        """Initialize portfolio state from current balances and bots."""
        from asgiref.sync import sync_to_async

        try:
            if self.config.dry_run and self._simulator:
                # In dry-run mode, use simulated balances
                portfolio_value = self._simulator.get_portfolio_value({})
                bot_allocation = self._simulator.get_bot_allocation()
            else:
                # Get real balances from Pionex
                client = await self._get_pionex_client()
                balances = await client.get_balances()

                # Calculate portfolio value (sum of all USDT-equivalent balances)
                portfolio_value = Decimal("0")
                for balance in balances:
                    if balance.currency == "USDT":
                        portfolio_value += balance.total

                # Get current bot allocation from database
                @sync_to_async
                def get_bot_allocation() -> Decimal:
                    return Bot.objects.active().live().total_invested()

                bot_allocation = await get_bot_allocation()

            self._risk_manager.update_portfolio(portfolio_value, bot_allocation)

            logger.info(
                f"Portfolio initialized: value={portfolio_value}, bot_allocation={bot_allocation}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize portfolio state: {e}")
            # Use defaults
            self._risk_manager.update_portfolio(Decimal("0"))

    async def _signal_listener(self) -> None:
        """Listen for signals from Redis and handle them."""
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")

        self._signal_subscriber = SignalSubscriber(redis_url=redis_url)

        async with self._signal_subscriber:
            logger.info("Signal listener started, waiting for signals...")

            async for message in self._signal_subscriber.listen():
                if not self._running:
                    break

                try:
                    await self._handle_signal(message)
                except Exception as e:
                    logger.error(f"Error handling signal: {e}", exc_info=True)

    async def _evaluation_loop(self) -> None:
        """Periodically evaluate existing bot performance."""
        while self._running and not self._shutdown_event.is_set():
            try:
                await self._evaluate_existing_bots()
            except Exception as e:
                logger.error(f"Error in evaluation loop: {e}", exc_info=True)

            # Wait for next evaluation or shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.evaluation_interval,
                )
            except TimeoutError:
                # Normal timeout, continue to next evaluation
                pass

    async def _handle_signal(self, message: SignalMessage) -> None:
        """
        Handle a signal received from the market analysis agent.

        For multi-user support, this method finds all users who have the
        signal's trading pair in their active_trading_pairs and processes
        the signal for each user individually.

        Args:
            message: The signal message received

        Requirements:
            - 6.4: When a signal triggers bot creation, use the user's API keys
            - 7.3: Bot creation uses correct user's API keys
            - 10.3: Create Grid Bot when favorable conditions
            - 10.4: Create DCA Bot when favorable for accumulation
            - 10.5: Stop bot when signals turn unfavorable
        """
        signal = message.signal
        symbol = signal.symbol

        logger.info(
            f"Received signal for {symbol}: {signal.direction.value} "
            f"({signal.confidence:.1f}% confidence)"
        )

        # Get all users who have this trading pair active
        users = await self._get_users_for_symbol(symbol)

        if not users:
            logger.debug(f"No users have {symbol} in their active trading pairs")
            return

        logger.info(f"Processing signal for {len(users)} user(s) with {symbol} active")

        # Process signal for each user
        for user in users:
            try:
                await self._handle_signal_for_user(message, user)
            except MissingAPIKeysError as e:
                logger.warning(
                    f"Skipping signal for user {e.username} (id={e.user_id}): no API keys"
                )
            except Exception as e:
                logger.error(
                    f"Error handling signal for user {user.username} (id={user.id}): {e}",
                    exc_info=True,
                )

    async def _get_users_for_symbol(self, symbol: str) -> list[User]:
        """
        Find all users who have the given trading pair in their active pairs.

        Args:
            symbol: The trading pair symbol (e.g., "BTC_USDT")

        Returns:
            List of User objects with this symbol in their active_trading_pairs

        Requirements:
            - 6.4: Signal triggers bot creation for users with active pair
        """
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_users():
            # Find profiles with this symbol in active_trading_pairs
            profiles = UserProfile.objects.filter(
                active_trading_pairs__contains=[symbol]
            ).select_related("user")
            return [profile.user for profile in profiles]

        return await get_users()

    async def _handle_signal_for_user(
        self,
        message: SignalMessage,
        user: User,
    ) -> None:
        """
        Handle a signal for a specific user.

        Args:
            message: The signal message received
            user: The user to process the signal for

        Requirements:
            - 6.4: When a signal triggers bot creation, use the user's API keys
            - 7.3: Bot creation uses correct user's API keys
            - 7.6: Implement rate limiting per user
        """
        signal = message.signal
        symbol = signal.symbol

        # Check rate limit before processing
        if not await self._rate_limiter.check_rate_limit(user.id):
            wait_time = await self._rate_limiter.get_wait_time(user.id)
            logger.warning(
                f"Rate limit exceeded for user {user.username} (id={user.id}), "
                f"skipping signal. Wait time: {wait_time:.1f}s"
            )
            return

        logger.debug(f"Processing signal for user {user.username} (id={user.id})")

        # Get existing bots for this symbol owned by this user
        existing_bots = await self._get_active_bots_for_symbol_and_user(symbol, user)

        # Decide action based on signal direction and confidence
        if signal.direction == SignalDirection.BUY and signal.meets_threshold:
            # Favorable conditions - consider creating a bot
            await self._handle_buy_signal(signal, existing_bots, user)

        elif signal.direction == SignalDirection.SELL and signal.meets_threshold:
            # Unfavorable conditions - consider stopping bots
            await self._handle_sell_signal(signal, existing_bots, user)

        elif signal.direction == SignalDirection.HOLD:
            # Neutral - evaluate existing bots only
            logger.debug(f"HOLD signal for {symbol}, no action for user {user.username}")

    async def _handle_buy_signal(
        self,
        signal: Signal,
        existing_bots: list[Bot],
        user: User | None = None,
    ) -> None:
        """
        Handle a BUY signal - consider creating a new bot.

        Args:
            signal: The buy signal
            existing_bots: Existing active bots for this symbol (and user if provided)
            user: The user to create the bot for (None for legacy single-user mode)

        Requirements:
            - 3.3: Associate created bot with authenticated user
            - 7.3: Bot creation uses correct user's API keys
            - 10.3: Create Grid Bot for range-bound markets
            - 10.4: Create DCA Bot for accumulation
        """
        symbol = signal.symbol
        user_info = f" for user {user.username}" if user else ""

        # Check if we already have max bots for this symbol
        if len(existing_bots) >= self.config.max_bots_per_symbol:
            logger.info(
                f"Max bots ({self.config.max_bots_per_symbol}) already active "
                f"for {symbol}{user_info}, skipping bot creation"
            )
            return

        # Determine bot type based on market conditions
        # Use technical indicators to decide between Grid and DCA
        bot_type = self._determine_bot_type(signal)

        # Calculate investment amount
        investment = await self._calculate_bot_investment(signal)

        if investment <= 0:
            logger.info(f"No available allocation for new bot on {symbol}{user_info}")
            return

        # Validate bot creation against risk limits
        validation = self._risk_manager.validate_bot_creation(investment)

        if not validation.is_valid:
            logger.warning(
                f"Bot creation rejected for {symbol}{user_info}: {validation.reasoning}"
            )
            return

        # Create the bot
        try:
            if bot_type == BotType.GRID:
                await self._create_grid_bot(signal, investment, user)
            else:
                await self._create_dca_bot(signal, investment, user)
        except MissingAPIKeysError as e:
            logger.warning(f"Cannot create bot for {symbol}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create bot for {symbol}{user_info}: {e}", exc_info=True)

    async def _handle_sell_signal(
        self,
        signal: Signal,
        existing_bots: list[Bot],
        user: User | None = None,
    ) -> None:
        """
        Handle a SELL signal - consider stopping existing bots.

        Args:
            signal: The sell signal
            existing_bots: Existing active bots for this symbol (and user if provided)
            user: The user whose bots to stop (None for legacy single-user mode)

        Requirements:
            - 10.5: Stop bot when signals turn unfavorable
            - 10.6: Close all open orders when stopping
        """
        symbol = signal.symbol
        user_info = f" for user {user.username}" if user else ""

        if not existing_bots:
            logger.debug(f"No active bots for {symbol}{user_info} to stop")
            return

        for bot in existing_bots:
            reason = (
                f"SELL signal received with {signal.confidence:.1f}% confidence. "
                f"Stopping bot to protect capital."
            )

            try:
                await self._stop_bot(bot, reason, user)
            except MissingAPIKeysError as e:
                logger.warning(f"Cannot stop bot {bot.pionex_bot_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to stop bot {bot.pionex_bot_id}: {e}", exc_info=True)

    def _determine_bot_type(self, signal: Signal) -> BotType:
        """
        Determine the appropriate bot type based on market conditions.

        Grid bots are better for range-bound markets.
        DCA bots are better for accumulation in trending markets.

        Args:
            signal: The signal with indicator data

        Returns:
            BotType to create
        """
        # Look for ADX indicator to determine trend strength
        adx_value = None
        for indicator in signal.indicators:
            if indicator.name == "ADX" and indicator.value is not None:
                adx_value = indicator.value
                break

        # ADX < 25 indicates range-bound market (good for Grid)
        # ADX >= 25 indicates trending market (good for DCA)
        if adx_value is not None and adx_value < 25:
            return BotType.GRID

        return BotType.DCA

    async def _calculate_bot_investment(self, signal: Signal) -> Decimal:
        """
        Calculate the investment amount for a new bot.

        Uses available allocation and signal confidence to determine size.

        Args:
            signal: The signal triggering bot creation

        Returns:
            Investment amount in quote currency
        """
        available = self._risk_manager.get_available_bot_allocation()

        if available <= 0:
            return Decimal("0")

        # Scale investment by confidence (higher confidence = larger investment)
        confidence_factor = Decimal(str(signal.confidence / 100))

        # Use up to 25% of available allocation per bot
        max_per_bot = available * Decimal("0.25")

        investment = max_per_bot * confidence_factor

        # Ensure minimum investment (e.g., $50)
        min_investment = Decimal("50.00")
        if investment < min_investment:
            if available >= min_investment:
                investment = min_investment
            else:
                return Decimal("0")

        return investment.quantize(Decimal("0.01"))

    async def _get_active_bots_for_symbol(self, symbol: str) -> list[Bot]:
        """Get active bots for a trading pair (legacy single-user mode)."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def fetch_bots() -> list[Bot]:
            if self.config.dry_run:
                return list(Bot.objects.active().simulated().for_pair(symbol))
            return list(Bot.objects.active().live().for_pair(symbol))

        return await fetch_bots()

    async def _get_active_bots_for_symbol_and_user(
        self,
        symbol: str,
        user: User,
    ) -> list[Bot]:
        """
        Get active bots for a trading pair owned by a specific user.

        Args:
            symbol: The trading pair symbol
            user: The user whose bots to retrieve

        Returns:
            List of active bots for the symbol owned by the user

        Requirements:
            - 3.2: Filter results to only include bots owned by user
        """
        from asgiref.sync import sync_to_async

        @sync_to_async
        def fetch_bots() -> list[Bot]:
            qs = Bot.objects.for_user(user).active().for_pair(symbol)
            if self.config.dry_run:
                return list(qs.simulated())
            return list(qs.live())

        return await fetch_bots()

    async def _create_grid_bot(
        self,
        signal: Signal,
        investment: Decimal,
        user: User | None = None,
    ) -> Bot:
        """
        Create a Grid trading bot.

        Args:
            signal: The signal triggering creation
            investment: Amount to invest
            user: The user to create the bot for (None for legacy single-user mode)

        Returns:
            Created Bot model instance

        Requirements:
            - 3.3: Associate created bot with authenticated user
            - 7.3: Bot creation uses correct user's API keys
            - 10.3: Create Grid Bot with calculated price range and grid count
        """
        symbol = signal.symbol
        user_info = f" for user {user.username}" if user else ""

        # Get current price from Bollinger Bands middle or estimate
        current_price = await self._get_current_price(signal)

        # Calculate price range (e.g., ±10% from current price)
        range_pct = Decimal(str(self.config.grid_bot_price_range_pct))
        lower_price = float(current_price * (1 - range_pct))
        upper_price = float(current_price * (1 + range_pct))

        grid_count = self.config.grid_bot_grid_count

        logger.info(
            f"Creating Grid bot for {symbol}{user_info}: "
            f"range=[{lower_price:.2f}, {upper_price:.2f}], "
            f"grids={grid_count}, investment={investment}"
        )

        if self.config.dry_run and self._simulator:
            # Simulate bot creation
            sim_bot = self._simulator.simulate_bot_creation(
                symbol=symbol,
                bot_type="GRID",
                investment=investment,
                params={
                    "lower_price": lower_price,
                    "upper_price": upper_price,
                    "grid_count": grid_count,
                },
            )
            bot_id = sim_bot.bot_id
        else:
            # Create real bot via Pionex API using user-specific client
            if user is not None:
                client = await self._client_factory.get_client_for_user(user)
                # Record API call for rate limiting
                await self._rate_limiter.record_call(user.id)
            else:
                client = await self._get_pionex_client()

            params = GridBotParams(
                symbol=symbol,
                lower_price=lower_price,
                upper_price=upper_price,
                grid_count=grid_count,
                investment=investment,
            )
            bot_info = await client.create_grid_bot(params)
            bot_id = bot_info.bot_id

        # Save to database with user association
        bot = await self._save_bot_to_db(
            bot_id=bot_id,
            bot_type=BotType.GRID,
            symbol=symbol,
            investment=investment,
            params={
                "lower_price": lower_price,
                "upper_price": upper_price,
                "grid_count": grid_count,
            },
            reasoning=f"Created due to BUY signal with {signal.confidence:.1f}% confidence",
            user=user,
        )

        # Update risk manager allocation
        current_allocation = self._risk_manager.current_bot_allocation
        self._risk_manager.update_bot_allocation(current_allocation + investment)

        # Log bot creation using structured bot logger (Requirement 10.11)
        bot_logger.log_bot_created(
            bot_id=bot_id,
            bot_type="GRID",
            symbol=symbol,
            invested=investment,
            params={
                "lower_price": lower_price,
                "upper_price": upper_price,
                "grid_count": grid_count,
            },
            reasoning=f"Created due to BUY signal with {signal.confidence:.1f}% confidence",
            is_simulated=self.config.dry_run,
        )

        # Broadcast bot creation to WebSocket
        try:
            broadcaster = get_broadcaster()
            await broadcaster.broadcast_bot_created(
                bot_id=bot_id,
                bot_type="GRID",
                symbol=symbol,
                invested=investment,
                params={
                    "lower_price": lower_price,
                    "upper_price": upper_price,
                    "grid_count": grid_count,
                },
                reasoning=f"Created due to BUY signal with {signal.confidence:.1f}% confidence",
                is_simulated=self.config.dry_run,
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast bot creation to WebSocket: {e}")

        return bot

    async def _create_dca_bot(
        self,
        signal: Signal,
        investment: Decimal,
        user: User | None = None,
    ) -> Bot:
        """
        Create a DCA (Dollar Cost Averaging) bot.

        Args:
            signal: The signal triggering creation
            investment: Total amount to invest
            user: The user to create the bot for (None for legacy single-user mode)

        Returns:
            Created Bot model instance

        Requirements:
            - 3.3: Associate created bot with authenticated user
            - 7.3: Bot creation uses correct user's API keys
            - 10.4: Create DCA Bot with calculated investment intervals
        """
        symbol = signal.symbol
        user_info = f" for user {user.username}" if user else ""

        interval_hours = self.config.dca_interval_hours
        orders_count = self.config.dca_orders_count
        investment_per_order = investment / Decimal(str(orders_count))

        logger.info(
            f"Creating DCA bot for {symbol}{user_info}: "
            f"per_order={investment_per_order}, interval={interval_hours}h, "
            f"total={investment}"
        )

        if self.config.dry_run and self._simulator:
            # Simulate bot creation
            sim_bot = self._simulator.simulate_bot_creation(
                symbol=symbol,
                bot_type="DCA",
                investment=investment,
                params={
                    "investment_per_order": str(investment_per_order),
                    "interval_hours": interval_hours,
                    "total_investment": str(investment),
                },
            )
            bot_id = sim_bot.bot_id
        else:
            # Create real bot via Pionex API using user-specific client
            if user is not None:
                client = await self._client_factory.get_client_for_user(user)
                # Record API call for rate limiting
                await self._rate_limiter.record_call(user.id)
            else:
                client = await self._get_pionex_client()

            params = DCABotParams(
                symbol=symbol,
                investment_per_order=investment_per_order,
                interval_hours=interval_hours,
                total_investment=investment,
            )
            bot_info = await client.create_dca_bot(params)
            bot_id = bot_info.bot_id

        # Save to database with user association
        bot = await self._save_bot_to_db(
            bot_id=bot_id,
            bot_type=BotType.DCA,
            symbol=symbol,
            investment=investment,
            params={
                "investment_per_order": str(investment_per_order),
                "interval_hours": interval_hours,
                "total_investment": str(investment),
            },
            reasoning=f"Created due to BUY signal with {signal.confidence:.1f}% confidence",
            user=user,
        )

        # Update risk manager allocation
        current_allocation = self._risk_manager.current_bot_allocation
        self._risk_manager.update_bot_allocation(current_allocation + investment)

        # Log bot creation using structured bot logger (Requirement 10.11)
        bot_logger.log_bot_created(
            bot_id=bot_id,
            bot_type="DCA",
            symbol=symbol,
            invested=investment,
            params={
                "investment_per_order": str(investment_per_order),
                "interval_hours": interval_hours,
                "total_investment": str(investment),
            },
            reasoning=f"Created due to BUY signal with {signal.confidence:.1f}% confidence",
            is_simulated=self.config.dry_run,
        )

        # Broadcast bot creation to WebSocket
        try:
            broadcaster = get_broadcaster()
            await broadcaster.broadcast_bot_created(
                bot_id=bot_id,
                bot_type="DCA",
                symbol=symbol,
                invested=investment,
                params={
                    "investment_per_order": str(investment_per_order),
                    "interval_hours": interval_hours,
                    "total_investment": str(investment),
                },
                reasoning=f"Created due to BUY signal with {signal.confidence:.1f}% confidence",
                is_simulated=self.config.dry_run,
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast bot creation to WebSocket: {e}")

        return bot

    async def _stop_bot(
        self,
        bot: Bot,
        reason: str,
        user: User | None = None,
    ) -> None:
        """
        Stop a bot and return funds.

        Args:
            bot: The bot to stop
            reason: Reason for stopping
            user: The user who owns the bot (None to use bot.user or legacy mode)

        Requirements:
            - 7.3: Bot operations use correct user's API keys
            - 10.5: Stop bot when signals turn unfavorable
            - 10.6: Close all open orders and return funds
            - 10.11: Log all bot termination events
        """
        logger.info(f"Stopping bot {bot.pionex_bot_id}: {reason}")

        if self.config.dry_run and self._simulator:
            # Simulate bot stop
            try:
                self._simulator.simulate_bot_stop(bot.pionex_bot_id)
            except ValueError:
                # Bot might not exist in simulator
                pass
        else:
            # Stop real bot via Pionex API using user-specific client
            # Prefer the user parameter, then bot.user, then legacy client
            effective_user = user or bot.user
            if user is not None:
                client = await self._client_factory.get_client_for_user(user)
            elif bot.user is not None:
                client = await self._client_factory.get_client_for_bot(bot)
            else:
                client = await self._get_pionex_client()

            await client.stop_bot(bot.pionex_bot_id)

            # Record API call for rate limiting
            if effective_user is not None:
                await self._rate_limiter.record_call(effective_user.id)

        # Update database using sync_to_async
        from asgiref.sync import sync_to_async

        @sync_to_async
        def update_bot_stopped():
            bot.status = BotStatus.STOPPED
            bot.stopped_at = django_timezone.now()
            bot.stop_reason = reason
            bot.save()

            # Log event
            BotEvent.objects.create(
                bot=bot,
                event_type=BotEvent.EventType.STOPPED,
                details={"reason": reason},
                reasoning=reason,
            )

        await update_bot_stopped()

        # Update risk manager allocation
        current_allocation = self._risk_manager.current_bot_allocation
        new_allocation = max(Decimal("0"), current_allocation - bot.invested_amount)
        self._risk_manager.update_bot_allocation(new_allocation)

        # Log bot stop using structured bot logger (Requirement 10.11)
        bot_logger.log_bot_stopped(
            bot_id=bot.pionex_bot_id,
            symbol=bot.trading_pair.symbol,
            reason=reason,
            final_pnl=bot.current_pnl,
            is_simulated=bot.is_simulated,
        )

        # Broadcast bot stopped to WebSocket
        try:
            broadcaster = get_broadcaster()
            await broadcaster.broadcast_bot_stopped(
                bot_id=bot.pionex_bot_id,
                symbol=bot.trading_pair.symbol,
                reason=reason,
                final_pnl=bot.current_pnl,
                is_simulated=bot.is_simulated,
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast bot stop to WebSocket: {e}")

        logger.info(f"Bot {bot.pionex_bot_id} stopped successfully")

    async def _evaluate_existing_bots(self) -> None:
        """
        Evaluate performance of all active bots.

        Groups bots by user for efficient API key usage and handles errors
        per-user without affecting other users.

        Requirements:
            - 7.4: Bot evaluation uses correct user's API keys
            - 7.5: Skip user operations if API keys are invalid/missing
            - 10.8: Flag/auto-stop underperforming bots
        """
        from asgiref.sync import sync_to_async

        logger.debug("Evaluating existing bots...")

        # Group bots by user for efficient processing
        bots_by_user = await self._get_active_bots_grouped_by_user()

        for user, user_bots in bots_by_user.items():
            try:
                await self._evaluate_bots_for_user(user, user_bots)
            except MissingAPIKeysError as e:
                logger.warning(
                    f"Skipping bot evaluation for user {e.username} (id={e.user_id}): "
                    "no API keys configured"
                )
            except Exception as e:
                logger.error(
                    f"Error evaluating bots for user {user.username if user else 'unknown'}: {e}",
                    exc_info=True,
                )

        # Also evaluate bots without user association (legacy bots)
        @sync_to_async
        def fetch_legacy_bots() -> list[Bot]:
            if self.config.dry_run:
                return list(Bot.objects.active().simulated().filter(user__isnull=True))
            else:
                return list(Bot.objects.active().live().filter(user__isnull=True))

        legacy_bots = await fetch_legacy_bots()
        if legacy_bots:
            logger.debug(f"Evaluating {len(legacy_bots)} legacy bots without user association")
            for bot in legacy_bots:
                try:
                    await self._evaluate_bot(bot)
                except Exception as e:
                    logger.error(f"Error evaluating legacy bot {bot.pionex_bot_id}: {e}")

    async def _get_active_bots_grouped_by_user(self) -> dict[User, list[Bot]]:
        """
        Get all active bots grouped by their owner.

        Returns:
            Dictionary mapping users to their list of active bots

        Requirements:
            - 7.4: Group bots by user for efficient API key usage
        """
        from collections import defaultdict
        from asgiref.sync import sync_to_async

        @sync_to_async
        def fetch_bots() -> dict[User, list[Bot]]:
            if self.config.dry_run:
                active_bots = Bot.objects.active().simulated().select_related("user", "trading_pair")
            else:
                active_bots = Bot.objects.active().live().select_related("user", "trading_pair")

            bots_by_user: dict[User, list[Bot]] = defaultdict(list)

            for bot in active_bots:
                if bot.user is not None:
                    bots_by_user[bot.user].append(bot)

            return dict(bots_by_user)

        return await fetch_bots()

    async def _evaluate_bots_for_user(self, user: User, bots: list[Bot]) -> None:
        """
        Evaluate all bots for a specific user.

        Uses the user's API keys to fetch bot status from Pionex.

        Args:
            user: The user whose bots to evaluate
            bots: List of bots owned by the user

        Requirements:
            - 7.4: Bot evaluation uses correct user's API keys
            - 7.5: Skip user operations if API keys are invalid/missing
            - 7.6: Implement rate limiting per user
        """
        if not bots:
            return

        # Check rate limit before processing
        if not await self._rate_limiter.check_rate_limit(user.id):
            wait_time = await self._rate_limiter.get_wait_time(user.id)
            logger.warning(
                f"Rate limit exceeded for user {user.username} (id={user.id}), "
                f"skipping bot evaluation. Wait time: {wait_time:.1f}s"
            )
            return

        logger.debug(f"Evaluating {len(bots)} bots for user {user.username} (id={user.id})")

        # Get client for this user (will raise MissingAPIKeysError if no keys)
        if not self.config.dry_run:
            client = await self._client_factory.get_client_for_user(user)
            # Record API call for rate limiting (one call to get client)
            await self._rate_limiter.record_call(user.id)
        else:
            client = None

        for bot in bots:
            try:
                await self._evaluate_bot(bot, client, user)
            except Exception as e:
                logger.error(
                    f"Error evaluating bot {bot.pionex_bot_id} for user {user.username}: {e}",
                    exc_info=True,
                )

    async def _evaluate_bot(
        self,
        bot: Bot,
        client: PionexClient | None = None,
        user: User | None = None,
    ) -> None:
        """
        Evaluate a single bot's performance.

        Args:
            bot: The bot to evaluate
            client: Optional pre-created Pionex client for the bot's owner
            user: Optional user for rate limiting tracking

        Requirements:
            - 7.4: Bot evaluation uses correct user's API keys
            - 7.6: Implement rate limiting per user
            - 10.8: Flag/auto-stop underperforming bots
        """
        # Get current bot status from Pionex or simulator
        if self.config.dry_run and self._simulator:
            sim_bot = self._simulator.get_bot(bot.pionex_bot_id)
            if sim_bot:
                pnl = sim_bot.pnl
                pnl_percent = sim_bot.pnl_percent / 100  # Convert to decimal
                current_value = sim_bot.current_value
            else:
                return
        else:
            # Use provided client or get one for the bot's owner
            if client is None:
                if bot.user is not None:
                    client = await self._client_factory.get_client_for_bot(bot)
                else:
                    client = await self._get_pionex_client()

            bot_info = await client.get_bot_details(bot.pionex_bot_id)
            pnl = bot_info.pnl
            pnl_percent = bot_info.pnl_percent / 100  # Convert to decimal
            current_value = bot_info.current_value

        # Update bot in database using sync_to_async
        from asgiref.sync import sync_to_async

        @sync_to_async
        def update_bot_performance():
            bot.current_pnl = pnl
            bot.pnl_percent = pnl_percent * 100
            bot.current_value = current_value
            bot.save()

            # Log performance update
            BotEvent.objects.create(
                bot=bot,
                event_type=BotEvent.EventType.PERFORMANCE_UPDATE,
                details={
                    "pnl": str(pnl),
                    "pnl_percent": pnl_percent * 100,
                    "current_value": str(current_value),
                },
            )

        await update_bot_performance()

        # Check if underperforming
        is_underperforming = self._risk_manager.is_bot_underperforming(pnl_percent)

        # Log performance update using structured bot logger
        bot_logger.log_bot_performance(
            bot_id=bot.pionex_bot_id,
            symbol=bot.trading_pair.symbol,
            pnl=pnl,
            pnl_percent=pnl_percent * 100,
            current_value=current_value,
            is_underperforming=is_underperforming,
        )

        # Broadcast performance update to WebSocket
        try:
            broadcaster = get_broadcaster()
            await broadcaster.broadcast_bot_performance(
                bot_id=bot.pionex_bot_id,
                symbol=bot.trading_pair.symbol,
                pnl=pnl,
                pnl_percent=pnl_percent * 100,
                current_value=current_value,
                is_underperforming=is_underperforming,
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast bot performance to WebSocket: {e}")

        if is_underperforming:
            logger.warning(
                f"Bot {bot.pionex_bot_id} is underperforming: P&L={pnl_percent * 100:.2f}%"
            )

            if self.config.auto_stop_underperforming:
                reason = (
                    f"Auto-stopped due to underperformance: "
                    f"P&L={pnl_percent * 100:.2f}% exceeds loss threshold "
                    f"of {self.config.bot_loss_threshold_pct * 100:.1f}%"
                )
                await self._stop_bot(bot, reason)

    async def _get_current_price(self, signal: Signal) -> Decimal:
        """
        Get current price from signal indicators or API.

        Args:
            signal: The signal with indicator data

        Returns:
            Current price estimate
        """
        # Try to get price from Bollinger Bands middle band
        for indicator in signal.indicators:
            if indicator.name == "BB" and indicator.value is not None:
                return Decimal(str(indicator.value))

        # Fallback: get from API
        if not self.config.dry_run:
            client = await self._get_pionex_client()
            trades = await client.get_trades(signal.symbol, limit=1)
            if trades:
                return trades[0].price

        # Default fallback
        return Decimal("0")

    async def _save_bot_to_db(
        self,
        bot_id: str,
        bot_type: BotType,
        symbol: str,
        investment: Decimal,
        params: dict[str, Any],
        reasoning: str,
        user: User | None = None,
    ) -> Bot:
        """
        Save a new bot to the database.

        Args:
            bot_id: Pionex bot ID
            bot_type: Type of bot
            symbol: Trading pair symbol
            investment: Investment amount
            params: Bot parameters
            reasoning: Reason for creation
            user: The user who owns this bot (None for legacy single-user mode)

        Returns:
            Created Bot instance

        Requirements:
            - 3.3: Associate created bot with authenticated user
        """
        from asgiref.sync import sync_to_async

        @sync_to_async
        def create_bot() -> Bot:
            # Get or create trading pair
            trading_pair, _ = TradingPair.objects.get_or_create(
                symbol=symbol,
                defaults={
                    "base_currency": symbol.split("_")[0] if "_" in symbol else symbol[:3],
                    "quote_currency": symbol.split("_")[1] if "_" in symbol else "USDT",
                    "is_active": True,
                },
            )

            bot = Bot.objects.create(
                user=user,  # Associate with user (can be None for legacy mode)
                pionex_bot_id=bot_id,
                bot_type=bot_type,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount=investment,
                current_value=investment,
                current_pnl=Decimal("0"),
                pnl_percent=0.0,
                params=params,
                is_simulated=self.config.dry_run,
            )

            # Log creation event
            BotEvent.objects.create(
                bot=bot,
                event_type=BotEvent.EventType.CREATED,
                details=params,
                reasoning=reasoning,
            )

            return bot

        bot = await create_bot()

        user_info = f" for user {user.username}" if user else ""
        logger.info(f"Bot {bot_id} saved to database{user_info}")

        return bot

    async def get_total_bot_allocation(self) -> Decimal:
        """
        Get total amount allocated to active bots.

        Includes both live and simulated bots based on mode.

        Returns:
            Total allocation amount

        Requirements:
            - 10.10: Include funds allocated to all active bots in exposure calculation
        """
        from asgiref.sync import sync_to_async

        @sync_to_async
        def fetch_allocation() -> Decimal:
            if self.config.dry_run:
                return Bot.objects.active().simulated().total_invested()
            else:
                return Bot.objects.active().live().total_invested()

        db_allocation = await fetch_allocation()

        if self.config.dry_run and self._simulator:
            sim_allocation = self._simulator.get_bot_allocation()
            return max(db_allocation, sim_allocation)

        return db_allocation


def setup_signal_handlers(agent: BotManagementAgent) -> None:
    """Setup signal handlers for graceful shutdown."""
    loop = asyncio.get_event_loop()

    def handle_signal(sig):
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        asyncio.create_task(agent.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))


async def main() -> None:
    """Main entry point for the bot management agent."""
    # Setup structured logging
    setup_logging(
        LoggingConfig(
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            json_format=True,
        )
    )

    logger.info("Starting Bot Management Agent...")

    # Log startup with configuration
    config = BotAgentConfig.from_settings()
    system_logger.log_startup(
        service_name="BotManagementAgent",
        mode="dry-run" if config.dry_run else "live",
        config={
            "dry_run": config.dry_run,
            "evaluation_interval": config.evaluation_interval,
            "min_confidence_for_bot": config.min_confidence_for_bot,
            "bot_loss_threshold_pct": config.bot_loss_threshold_pct,
            "auto_stop_underperforming": config.auto_stop_underperforming,
            "max_bots_per_symbol": config.max_bots_per_symbol,
            "grid_bot_grid_count": config.grid_bot_grid_count,
            "grid_bot_price_range_pct": config.grid_bot_price_range_pct,
            "dca_interval_hours": config.dca_interval_hours,
            "dca_orders_count": config.dca_orders_count,
        },
    )

    async with BotManagementAgent(config=config) as agent:
        setup_signal_handlers(agent)
        await agent.run()

    # Log shutdown
    system_logger.log_shutdown(
        service_name="BotManagementAgent",
        reason="normal",
    )


if __name__ == "__main__":
    asyncio.run(main())
