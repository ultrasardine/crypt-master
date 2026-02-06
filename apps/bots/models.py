"""Bot management models."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.db import models
from django.db.models import QuerySet, Sum

from apps.core.models import TimeStampedModel, TradingPair

if TYPE_CHECKING:
    pass


class BotQuerySet(QuerySet):
    """Custom QuerySet for Bot model with common filtering methods."""

    def for_user(self, user: User) -> "BotQuerySet":
        """
        Filter bots to only those owned by the specified user.

        Args:
            user: The user to filter bots for.

        Returns:
            QuerySet filtered to the user's bots.

        Requirements: 3.2 - Filter results to only include bots owned by user
        """
        return self.filter(user=user)

    def active(self) -> "BotQuerySet":
        """Return only active bots."""
        return self.filter(status=BotStatus.ACTIVE)

    def stopped(self) -> "BotQuerySet":
        """Return only stopped bots."""
        return self.filter(status=BotStatus.STOPPED)

    def with_errors(self) -> "BotQuerySet":
        """Return bots in error state."""
        return self.filter(status=BotStatus.ERROR)

    def live(self) -> "BotQuerySet":
        """Return only live (non-simulated) bots."""
        return self.filter(is_simulated=False)

    def simulated(self) -> "BotQuerySet":
        """Return only simulated bots."""
        return self.filter(is_simulated=True)

    def by_type(self, bot_type: str) -> "BotQuerySet":
        """Filter bots by type."""
        return self.filter(bot_type=bot_type)

    def for_pair(self, symbol: str) -> "BotQuerySet":
        """Filter bots for a specific trading pair."""
        return self.filter(trading_pair__symbol=symbol)

    def profitable(self) -> "BotQuerySet":
        """Return bots with positive P&L."""
        return self.filter(current_pnl__gt=0)

    def unprofitable(self) -> "BotQuerySet":
        """Return bots with negative P&L."""
        return self.filter(current_pnl__lt=0)

    def underperforming(self, threshold: float = -10.0) -> "BotQuerySet":
        """Return bots with P&L percentage below threshold."""
        return self.filter(pnl_percent__lt=threshold)

    def total_invested(self) -> Decimal:
        """Calculate total invested amount across all bots in queryset."""
        result = self.aggregate(total=Sum("invested_amount"))
        return result["total"] or Decimal("0")

    def total_pnl(self) -> Decimal:
        """Calculate total P&L across all bots in queryset."""
        result = self.aggregate(total=Sum("current_pnl"))
        return result["total"] or Decimal("0")


class BotManager(models.Manager):
    """Custom manager for Bot model."""

    def get_queryset(self) -> BotQuerySet:
        """Return custom queryset."""
        return BotQuerySet(self.model, using=self._db)

    def for_user(self, user: User) -> BotQuerySet:
        """
        Get all bots for a specific user.

        Args:
            user: The user to filter bots for.

        Returns:
            QuerySet filtered to the user's bots.

        Requirements: 3.2 - Filter results to only include bots owned by user
        """
        return self.get_queryset().for_user(user)

    def active(self) -> BotQuerySet:
        """Return only active bots."""
        return self.get_queryset().active()

    def live_active(self) -> BotQuerySet:
        """Return active live (non-simulated) bots."""
        return self.get_queryset().active().live()

    def simulated_active(self) -> BotQuerySet:
        """Return active simulated bots."""
        return self.get_queryset().active().simulated()

    def for_pair(self, symbol: str) -> BotQuerySet:
        """Get all bots for a trading pair."""
        return self.get_queryset().for_pair(symbol)

    def underperforming(self, threshold: float = -10.0) -> BotQuerySet:
        """Get underperforming bots."""
        return self.get_queryset().active().underperforming(threshold)

    def total_active_investment(self, simulated: bool = False) -> Decimal:
        """Get total investment in active bots."""
        qs = self.get_queryset().active()
        if simulated:
            qs = qs.simulated()
        else:
            qs = qs.live()
        return qs.total_invested()


class BotType(models.TextChoices):
    """Types of Pionex bots."""

    GRID = "GRID", "Grid Bot"
    DCA = "DCA", "DCA Bot"
    INFINITY_GRID = "INFINITY_GRID", "Infinity Grid Bot"
    FUTURES_GRID = "FUTURES_GRID", "Futures Grid Bot"


class BotStatus(models.TextChoices):
    """Bot status."""

    ACTIVE = "ACTIVE", "Active"
    STOPPED = "STOPPED", "Stopped"
    ERROR = "ERROR", "Error"
    PENDING = "PENDING", "Pending"


class Bot(TimeStampedModel):
    """
    Represents a Pionex trading bot.

    Tracks bot configuration, status, and performance.

    Requirements:
    - 3.1: Include a foreign key reference to the owning User
    - 3.6: BotEvent inherits user association from parent Bot
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="bots",
        help_text="The user who owns this bot",
    )
    pionex_bot_id = models.CharField(max_length=100, unique=True, db_index=True)
    bot_type = models.CharField(max_length=20, choices=BotType.choices)
    trading_pair = models.ForeignKey(
        TradingPair,
        on_delete=models.CASCADE,
        related_name="bots",
    )
    status = models.CharField(
        max_length=10,
        choices=BotStatus.choices,
        default=BotStatus.PENDING,
    )
    invested_amount = models.DecimalField(max_digits=20, decimal_places=8)
    current_value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    current_pnl = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    pnl_percent = models.FloatField(null=True, blank=True)
    params = models.JSONField(default=dict, help_text="Bot-specific parameters")
    is_simulated = models.BooleanField(default=False)
    stopped_at = models.DateTimeField(null=True, blank=True)
    stop_reason = models.TextField(blank=True)
    
    # New fields for dashboard integration
    triggered_by_signal = models.ForeignKey(
        "trading.Signal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_bots",
        help_text="The signal that triggered this bot creation",
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time bot data was synced from Pionex",
    )

    objects = BotManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bot"
        verbose_name_plural = "Bots"
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["bot_type", "-created_at"]),
            models.Index(fields=["trading_pair", "-created_at"]),
            models.Index(fields=["is_simulated", "status"]),
            # New indexes for user-filtered queries (Requirements: 3.1)
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["user", "trading_pair", "-created_at"]),
            models.Index(fields=["user", "is_simulated", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.bot_type} {self.trading_pair.symbol} ({self.status})"


class BotEvent(TimeStampedModel):
    """
    Log of bot lifecycle events.

    Tracks creation, modification, and termination with full context.
    """

    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        STARTED = "STARTED", "Started"
        MODIFIED = "MODIFIED", "Modified"
        STOPPED = "STOPPED", "Stopped"
        ERROR = "ERROR", "Error"
        PERFORMANCE_UPDATE = "PERFORMANCE_UPDATE", "Performance Update"

    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    details = models.JSONField(default=dict)
    reasoning = models.TextField(blank=True, help_text="Why this action was taken")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bot Event"
        verbose_name_plural = "Bot Events"
        indexes = [
            models.Index(fields=["bot", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.bot} - {self.event_type} @ {self.created_at}"
