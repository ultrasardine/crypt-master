"""
Core models shared across the application.

Contains base models and shared entities like TradingPair,
PortfolioSnapshot, and SystemConfig.
"""

from datetime import timedelta

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base model with created_at and updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TradingPairQuerySet(QuerySet):
    """Custom QuerySet for TradingPair model."""

    def active(self) -> "TradingPairQuerySet":
        """Return only active trading pairs."""
        return self.filter(is_active=True)

    def by_quote(self, quote_currency: str) -> "TradingPairQuerySet":
        """Filter by quote currency (e.g., USDT)."""
        return self.filter(quote_currency=quote_currency)

    def by_base(self, base_currency: str) -> "TradingPairQuerySet":
        """Filter by base currency (e.g., BTC)."""
        return self.filter(base_currency=base_currency)


class TradingPairManager(models.Manager):
    """Custom manager for TradingPair model."""

    def get_queryset(self) -> TradingPairQuerySet:
        """Return custom queryset."""
        return TradingPairQuerySet(self.model, using=self._db)

    def active(self) -> TradingPairQuerySet:
        """Get active trading pairs."""
        return self.get_queryset().active()

    def usdt_pairs(self) -> TradingPairQuerySet:
        """Get USDT trading pairs."""
        return self.get_queryset().active().by_quote("USDT")


class TradingPair(TimeStampedModel):
    """
    Represents a trading pair available on Pionex.

    Example: BTC_USDT, ETH_USDT
    """

    symbol = models.CharField(max_length=20, unique=True, db_index=True)
    base_currency = models.CharField(max_length=10)
    quote_currency = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    min_quantity = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    max_quantity = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    price_precision = models.IntegerField(default=8)
    quantity_precision = models.IntegerField(default=8)

    objects = TradingPairManager()

    class Meta:
        ordering = ["symbol"]
        verbose_name = "Trading Pair"
        verbose_name_plural = "Trading Pairs"

    def __str__(self) -> str:
        return self.symbol


class PortfolioSnapshotQuerySet(QuerySet):
    """Custom QuerySet for PortfolioSnapshot model."""

    def live(self) -> "PortfolioSnapshotQuerySet":
        """Return only live (non-simulated) snapshots."""
        return self.filter(is_simulated=False)

    def simulated(self) -> "PortfolioSnapshotQuerySet":
        """Return only simulated snapshots."""
        return self.filter(is_simulated=True)

    def recent(self, hours: int = 24) -> "PortfolioSnapshotQuerySet":
        """Return snapshots from the last N hours."""
        cutoff = timezone.now() - timedelta(hours=hours)
        return self.filter(created_at__gte=cutoff)

    def in_drawdown(self, threshold: float = 0.0) -> "PortfolioSnapshotQuerySet":
        """Return snapshots where drawdown exceeds threshold."""
        return self.filter(drawdown__gt=threshold)


class PortfolioSnapshotManager(models.Manager):
    """Custom manager for PortfolioSnapshot model."""

    def get_queryset(self) -> PortfolioSnapshotQuerySet:
        """Return custom queryset."""
        return PortfolioSnapshotQuerySet(self.model, using=self._db)

    def latest_live(self):
        """Get the most recent live snapshot."""
        return self.get_queryset().live().first()

    def latest_simulated(self):
        """Get the most recent simulated snapshot."""
        return self.get_queryset().simulated().first()

    def recent(self, hours: int = 24, simulated: bool = False) -> PortfolioSnapshotQuerySet:
        """Get recent snapshots."""
        qs = self.get_queryset().recent(hours)
        return qs.simulated() if simulated else qs.live()


class PortfolioSnapshot(TimeStampedModel):
    """
    Point-in-time snapshot of portfolio state.

    Used for tracking portfolio value, drawdown, and high water mark over time.
    """

    total_value = models.DecimalField(max_digits=20, decimal_places=8)
    available_balance = models.DecimalField(max_digits=20, decimal_places=8)
    allocated_to_bots = models.DecimalField(max_digits=20, decimal_places=8)
    drawdown = models.FloatField(default=0.0)
    high_water_mark = models.DecimalField(max_digits=20, decimal_places=8)
    is_simulated = models.BooleanField(default=False)

    objects = PortfolioSnapshotManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Portfolio Snapshot"
        verbose_name_plural = "Portfolio Snapshots"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_simulated", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Portfolio @ {self.created_at}: {self.total_value}"


class SystemConfig(TimeStampedModel):
    """
    Key-value configuration storage.

    Stores runtime configuration that can be modified without restart.
    Sensitive values should use environment variables instead.
    """

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.JSONField()
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configurations"

    def __str__(self) -> str:
        return self.key

    @classmethod
    def get_value(cls, key: str, default=None):
        """Get a configuration value by key."""
        try:
            config = cls.objects.get(key=key)
            return config.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_value(cls, key: str, value, description: str = ""):
        """Set a configuration value."""
        config, _ = cls.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )
        return config
