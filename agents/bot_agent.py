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
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import django
import redis.asyncio as aioredis

# Setup Django before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.utils import timezone as django_timezone

from apps.bots.models import Bot, BotEvent, BotStatus, BotType
from apps.core.models import TradingPair
from lib.analysis.signal import Signal
from lib.analysis.technical import SignalDirection
from lib.logging import (
    get_bot_logger,
    get_system_logger,
    setup_logging,
    LoggingConfig,
)
from lib.messaging.signals import SignalMessage, SignalSubscriber, signal_from_json
from lib.messaging.websocket import get_broadcaster
from lib.pionex.client import PionexClient
from lib.pionex.models import BotInfo, DCABotParams, GridBotParams
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
    
    @classmethod
    def from_settings(cls) -> "BotAgentConfig":
        """Create config from Django settings."""
        return cls(
            dry_run=getattr(settings, "DRY_RUN", True),
            evaluation_interval=getattr(settings, "BOT_EVALUATION_INTERVAL", DEFAULT_EVALUATION_INTERVAL),
            min_confidence_for_bot=getattr(settings, "RISK_MIN_CONFIDENCE", 0.85) * 100,
            bot_loss_threshold_pct=getattr(settings, "BOT_LOSS_THRESHOLD_PCT", 0.10),
            auto_stop_underperforming=getattr(settings, "AUTO_STOP_UNDERPERFORMING_BOTS", True),
            max_bots_per_symbol=getattr(settings, "MAX_BOTS_PER_SYMBOL", 2),
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
    ) -> None:
        """
        Initialize the BotManagementAgent.
        
        Args:
            config: Agent configuration (uses defaults from settings if None)
            pionex_client: Optional Pionex client for dependency injection
            redis_client: Optional Redis client for dependency injection
            risk_manager: Optional RiskManager for dependency injection
            simulator: Optional DryRunSimulator for dry-run mode
        """
        self.config = config or BotAgentConfig.from_settings()
        self._pionex_client = pionex_client
        self._redis_client = redis_client
        self._owns_pionex = pionex_client is None
        self._owns_redis = redis_client is None
        
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
        
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._signal_subscriber: SignalSubscriber | None = None

    async def _get_pionex_client(self) -> PionexClient:
        """Get or create the Pionex client."""
        if self._pionex_client is None:
            api_key = getattr(settings, "PIONEX_API_KEY", "")
            api_secret = getattr(settings, "PIONEX_API_SECRET", "")
            
            if not api_key or not api_secret:
                raise ValueError(
                    "PIONEX_API_KEY and PIONEX_API_SECRET must be set in environment"
                )
            
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
    
    async def __aenter__(self) -> "BotManagementAgent":
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
        logger.info(
            f"BotManagementAgent starting (dry_run={self.config.dry_run})..."
        )
        
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
                bot_allocation = Bot.objects.active().live().total_invested()
            
            self._risk_manager.update_portfolio(portfolio_value, bot_allocation)
            
            logger.info(
                f"Portfolio initialized: value={portfolio_value}, "
                f"bot_allocation={bot_allocation}"
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
            except asyncio.TimeoutError:
                # Normal timeout, continue to next evaluation
                pass
    
    async def _handle_signal(self, message: SignalMessage) -> None:
        """
        Handle a signal received from the market analysis agent.
        
        Args:
            message: The signal message received
            
        Requirements:
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
        
        # Get existing bots for this symbol
        existing_bots = await self._get_active_bots_for_symbol(symbol)
        
        # Decide action based on signal direction and confidence
        if signal.direction == SignalDirection.BUY and signal.meets_threshold:
            # Favorable conditions - consider creating a bot
            await self._handle_buy_signal(signal, existing_bots)
        
        elif signal.direction == SignalDirection.SELL and signal.meets_threshold:
            # Unfavorable conditions - consider stopping bots
            await self._handle_sell_signal(signal, existing_bots)
        
        elif signal.direction == SignalDirection.HOLD:
            # Neutral - evaluate existing bots only
            logger.debug(f"HOLD signal for {symbol}, no action taken")

    async def _handle_buy_signal(
        self,
        signal: Signal,
        existing_bots: list[Bot],
    ) -> None:
        """
        Handle a BUY signal - consider creating a new bot.
        
        Args:
            signal: The buy signal
            existing_bots: Existing active bots for this symbol
            
        Requirements:
            - 10.3: Create Grid Bot for range-bound markets
            - 10.4: Create DCA Bot for accumulation
        """
        symbol = signal.symbol
        
        # Check if we already have max bots for this symbol
        if len(existing_bots) >= self.config.max_bots_per_symbol:
            logger.info(
                f"Max bots ({self.config.max_bots_per_symbol}) already active "
                f"for {symbol}, skipping bot creation"
            )
            return
        
        # Determine bot type based on market conditions
        # Use technical indicators to decide between Grid and DCA
        bot_type = self._determine_bot_type(signal)
        
        # Calculate investment amount
        investment = await self._calculate_bot_investment(signal)
        
        if investment <= 0:
            logger.info(f"No available allocation for new bot on {symbol}")
            return
        
        # Validate bot creation against risk limits
        validation = self._risk_manager.validate_bot_creation(investment)
        
        if not validation.is_valid:
            logger.warning(
                f"Bot creation rejected for {symbol}: {validation.reasoning}"
            )
            return
        
        # Create the bot
        try:
            if bot_type == BotType.GRID:
                await self._create_grid_bot(signal, investment)
            else:
                await self._create_dca_bot(signal, investment)
        except Exception as e:
            logger.error(f"Failed to create bot for {symbol}: {e}", exc_info=True)

    async def _handle_sell_signal(
        self,
        signal: Signal,
        existing_bots: list[Bot],
    ) -> None:
        """
        Handle a SELL signal - consider stopping existing bots.
        
        Args:
            signal: The sell signal
            existing_bots: Existing active bots for this symbol
            
        Requirements:
            - 10.5: Stop bot when signals turn unfavorable
            - 10.6: Close all open orders when stopping
        """
        symbol = signal.symbol
        
        if not existing_bots:
            logger.debug(f"No active bots for {symbol} to stop")
            return
        
        for bot in existing_bots:
            reason = (
                f"SELL signal received with {signal.confidence:.1f}% confidence. "
                f"Stopping bot to protect capital."
            )
            
            try:
                await self._stop_bot(bot, reason)
            except Exception as e:
                logger.error(
                    f"Failed to stop bot {bot.pionex_bot_id}: {e}",
                    exc_info=True
                )
    
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
        """Get active bots for a trading pair."""
        if self.config.dry_run:
            return list(Bot.objects.active().simulated().for_pair(symbol))
        return list(Bot.objects.active().live().for_pair(symbol))

    async def _create_grid_bot(
        self,
        signal: Signal,
        investment: Decimal,
    ) -> Bot:
        """
        Create a Grid trading bot.
        
        Args:
            signal: The signal triggering creation
            investment: Amount to invest
            
        Returns:
            Created Bot model instance
            
        Requirements:
            - 10.3: Create Grid Bot with calculated price range and grid count
        """
        symbol = signal.symbol
        
        # Get current price from Bollinger Bands middle or estimate
        current_price = await self._get_current_price(signal)
        
        # Calculate price range (e.g., ±10% from current price)
        range_pct = Decimal(str(self.config.grid_bot_price_range_pct))
        lower_price = float(current_price * (1 - range_pct))
        upper_price = float(current_price * (1 + range_pct))
        
        grid_count = self.config.grid_bot_grid_count
        
        logger.info(
            f"Creating Grid bot for {symbol}: "
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
            # Create real bot via Pionex API
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
        
        # Save to database
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
    ) -> Bot:
        """
        Create a DCA (Dollar Cost Averaging) bot.
        
        Args:
            signal: The signal triggering creation
            investment: Total amount to invest
            
        Returns:
            Created Bot model instance
            
        Requirements:
            - 10.4: Create DCA Bot with calculated investment intervals
        """
        symbol = signal.symbol
        
        interval_hours = self.config.dca_interval_hours
        orders_count = self.config.dca_orders_count
        investment_per_order = investment / Decimal(str(orders_count))
        
        logger.info(
            f"Creating DCA bot for {symbol}: "
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
            # Create real bot via Pionex API
            client = await self._get_pionex_client()
            params = DCABotParams(
                symbol=symbol,
                investment_per_order=investment_per_order,
                interval_hours=interval_hours,
                total_investment=investment,
            )
            bot_info = await client.create_dca_bot(params)
            bot_id = bot_info.bot_id
        
        # Save to database
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

    async def _stop_bot(self, bot: Bot, reason: str) -> None:
        """
        Stop a bot and return funds.
        
        Args:
            bot: The bot to stop
            reason: Reason for stopping
            
        Requirements:
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
            # Stop real bot via Pionex API
            client = await self._get_pionex_client()
            await client.stop_bot(bot.pionex_bot_id)
        
        # Update database
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
        
        Checks for underperforming bots and takes action based on config.
        
        Requirements:
            - 10.8: Flag/auto-stop underperforming bots
        """
        logger.debug("Evaluating existing bots...")
        
        if self.config.dry_run:
            active_bots = Bot.objects.active().simulated()
        else:
            active_bots = Bot.objects.active().live()
        
        for bot in active_bots:
            try:
                await self._evaluate_bot(bot)
            except Exception as e:
                logger.error(
                    f"Error evaluating bot {bot.pionex_bot_id}: {e}",
                    exc_info=True
                )
    
    async def _evaluate_bot(self, bot: Bot) -> None:
        """
        Evaluate a single bot's performance.
        
        Args:
            bot: The bot to evaluate
            
        Requirements:
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
            client = await self._get_pionex_client()
            bot_info = await client.get_bot_details(bot.pionex_bot_id)
            pnl = bot_info.pnl
            pnl_percent = bot_info.pnl_percent / 100  # Convert to decimal
            current_value = bot_info.current_value
        
        # Update bot in database
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
                f"Bot {bot.pionex_bot_id} is underperforming: "
                f"P&L={pnl_percent*100:.2f}%"
            )
            
            if self.config.auto_stop_underperforming:
                reason = (
                    f"Auto-stopped due to underperformance: "
                    f"P&L={pnl_percent*100:.2f}% exceeds loss threshold "
                    f"of {self.config.bot_loss_threshold_pct*100:.1f}%"
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
            
        Returns:
            Created Bot instance
        """
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
        
        logger.info(f"Bot {bot_id} saved to database")
        
        return bot

    def get_total_bot_allocation(self) -> Decimal:
        """
        Get total amount allocated to active bots.
        
        Includes both live and simulated bots based on mode.
        
        Returns:
            Total allocation amount
            
        Requirements:
            - 10.10: Include funds allocated to all active bots in exposure calculation
        """
        if self.config.dry_run:
            # Include simulated bots
            db_allocation = Bot.objects.active().simulated().total_invested()
            if self._simulator:
                sim_allocation = self._simulator.get_bot_allocation()
                return max(db_allocation, sim_allocation)
            return db_allocation
        else:
            return Bot.objects.active().live().total_invested()


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
    setup_logging(LoggingConfig(
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        json_format=True,
    ))
    
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
