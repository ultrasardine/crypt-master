"""
Core models shared across the application.

Contains base models and shared entities like TradingPair,
PortfolioSnapshot, SystemConfig, and UserProfile.
"""

from __future__ import annotations

import base64
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import QuerySet
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

if TYPE_CHECKING:
    pass


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

    def get_or_create_from_symbol(self, symbol: str) -> "TradingPair":
        """
        Get or create a trading pair from a symbol string.

        Parses the symbol (e.g., 'BTC_USDT') to extract base and quote currencies.

        Args:
            symbol: Trading pair symbol in format 'BASE_QUOTE' (e.g., 'BTC_USDT')

        Returns:
            TradingPair instance (created if it didn't exist)
        """
        symbol = symbol.upper().strip()
        if "_" in symbol:
            base, quote = symbol.split("_", 1)
        else:
            # Assume USDT quote if no separator
            base = symbol
            quote = "USDT"
            symbol = f"{base}_{quote}"

        pair, _ = self.get_or_create(
            symbol=symbol,
            defaults={
                "base_currency": base,
                "quote_currency": quote,
                "is_active": True,
            },
        )
        return pair

    def ensure_pairs_exist(self, symbols: list[str]) -> list["TradingPair"]:
        """
        Ensure all trading pairs in the list exist in the database.

        Args:
            symbols: List of trading pair symbols

        Returns:
            List of TradingPair instances
        """
        pairs = []
        for symbol in symbols:
            if symbol:
                pairs.append(self.get_or_create_from_symbol(symbol))
        return pairs


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

    def for_user(self, user) -> "PortfolioSnapshotQuerySet":
        """
        Filter snapshots to only those owned by the specified user.

        Args:
            user: The user to filter snapshots for.

        Returns:
            QuerySet filtered to the user's snapshots.

        Requirements: 5.2 - Filter results to only include snapshots owned by user
        """
        return self.filter(user=user)

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

    def for_user(self, user) -> PortfolioSnapshotQuerySet:
        """
        Get all snapshots for a specific user.

        Args:
            user: The user to filter snapshots for.

        Returns:
            QuerySet filtered to the user's snapshots.

        Requirements: 5.2 - Filter results to only include snapshots owned by user
        """
        return self.get_queryset().for_user(user)

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

    Requirements:
    - 5.1: Include a foreign key reference to the owning User
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="portfolio_snapshots",
        help_text="The user who owns this portfolio snapshot",
    )
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
            # New indexes for user-filtered queries (Requirements: 5.1)
            models.Index(fields=["user", "is_simulated", "-created_at"]),
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


# Trading mode choices for UserProfile
class TradingMode(models.TextChoices):
    """Trading mode options for user preferences."""

    DRY_RUN = "dry_run", "Dry Run (Simulation)"
    LIVE = "live", "Live Trading"


class RiskTolerance(models.TextChoices):
    """Risk tolerance levels for user preferences."""

    CONSERVATIVE = "conservative", "Conservative"
    MODERATE = "moderate", "Moderate"
    AGGRESSIVE = "aggressive", "Aggressive"


class UserProfile(TimeStampedModel):
    """
    Extended user profile with trading settings and encrypted API keys.

    This model stores user-specific settings and encrypted Pionex API credentials.
    Each user has a unique salt for key derivation, ensuring encryption keys are
    unique per user.

    Requirements:
    - 1.1: Create UserProfile with default settings on user registration
    - 1.2: Persist user preference changes
    - 1.3: Store user preferences (trading mode, notifications, risk tolerance)
    - 2.3: Decrypt API keys in memory only for the duration of operations
    - 2.5: Securely overwrite previous encrypted values on update
    - 2.6: Securely remove encrypted data on deletion

    Attributes:
        user: One-to-one relationship with Django User model
        encrypted_api_key: Fernet-encrypted Pionex API key
        encrypted_api_secret: Fernet-encrypted Pionex API secret
        api_key_salt: Per-user salt for key derivation (base64 encoded)
        default_trading_mode: User's preferred trading mode (dry_run/live)
        risk_tolerance: User's risk tolerance level
        notification_email_enabled: Whether email notifications are enabled
        active_trading_pairs: List of trading pair symbols the user is interested in
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    # Encrypted Pionex API credentials
    encrypted_api_key = models.TextField(blank=True, default="")
    encrypted_api_secret = models.TextField(blank=True, default="")
    api_key_salt = models.CharField(max_length=64, blank=True, default="")

    # User preferences
    default_trading_mode = models.CharField(
        max_length=20,
        choices=TradingMode.choices,
        default=TradingMode.DRY_RUN,
    )
    risk_tolerance = models.CharField(
        max_length=20,
        choices=RiskTolerance.choices,
        default=RiskTolerance.MODERATE,
    )
    notification_email_enabled = models.BooleanField(default=True)

    # Trading pair preferences
    active_trading_pairs = models.JSONField(
        default=list,
        blank=True,
        help_text="List of trading pair symbols the user is interested in",
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self) -> str:
        return f"Profile for {self.user.username}"

    def _get_api_key_manager(self):
        """Get the API key manager instance with the application master key."""
        from lib.crypto.api_key_manager import APIKeyManager

        return APIKeyManager(master_key=settings.SECRET_KEY)

    def has_api_keys(self) -> bool:
        """
        Check if the user has API keys configured.

        Returns:
            True if both encrypted API key and secret are present, False otherwise.
        """
        return bool(self.encrypted_api_key and self.encrypted_api_secret and self.api_key_salt)

    def get_decrypted_api_key(self) -> str:
        """
        Decrypt and return the user's Pionex API key.

        The decrypted key is only held in memory for the duration of the call.

        Returns:
            The decrypted API key string.

        Raises:
            ValueError: If no API keys are configured.
            APIKeyDecryptionError: If decryption fails.
        """
        if not self.has_api_keys():
            raise ValueError("No API keys configured for this user")

        manager = self._get_api_key_manager()
        salt = base64.b64decode(self.api_key_salt)
        return manager.decrypt(self.encrypted_api_key, salt)

    def get_decrypted_api_secret(self) -> str:
        """
        Decrypt and return the user's Pionex API secret.

        The decrypted secret is only held in memory for the duration of the call.

        Returns:
            The decrypted API secret string.

        Raises:
            ValueError: If no API keys are configured.
            APIKeyDecryptionError: If decryption fails.
        """
        if not self.has_api_keys():
            raise ValueError("No API keys configured for this user")

        manager = self._get_api_key_manager()
        salt = base64.b64decode(self.api_key_salt)
        return manager.decrypt(self.encrypted_api_secret, salt)

    def set_api_credentials(self, api_key: str, api_secret: str) -> None:
        """
        Encrypt and store new API credentials.

        This method generates a new salt and encrypts both the API key and secret.
        If credentials already exist, they are securely overwritten.

        Args:
            api_key: The Pionex API key to encrypt and store.
            api_secret: The Pionex API secret to encrypt and store.

        Raises:
            APIKeyValidationError: If the API key format is invalid.
            ValueError: If api_key or api_secret is empty.
        """
        from lib.crypto.api_key_manager import APIKeyValidationError

        if not api_key or not api_secret:
            raise ValueError("API key and secret cannot be empty")

        manager = self._get_api_key_manager()

        # Validate API key format
        if not manager.validate_api_key_format(api_key):
            raise APIKeyValidationError(
                "Invalid API key format. Pionex API keys must be 16-128 alphanumeric characters."
            )

        # Generate a new salt for this user (or regenerate on update)
        salt = manager.generate_salt()

        # Encrypt the credentials
        self.encrypted_api_key = manager.encrypt(api_key, salt)
        self.encrypted_api_secret = manager.encrypt(api_secret, salt)
        self.api_key_salt = base64.b64encode(salt).decode("utf-8")

        self.save(update_fields=["encrypted_api_key", "encrypted_api_secret", "api_key_salt"])

    def clear_api_credentials(self) -> None:
        """
        Securely remove stored API credentials.

        This method clears all encrypted credential fields and the salt.
        After calling this method, has_api_keys() will return False.
        """
        self.encrypted_api_key = ""
        self.encrypted_api_secret = ""
        self.api_key_salt = ""

        self.save(update_fields=["encrypted_api_key", "encrypted_api_secret", "api_key_salt"])


class MarketSentimentData(TimeStampedModel):
    """
    Stores public market sentiment data from external APIs.

    Fetched periodically and displayed on dashboard.

    Requirements:
    - 4.5: Store market sentiment data in database
    """

    fear_greed_index = models.IntegerField(null=True)
    fear_greed_classification = models.CharField(max_length=20, blank=True)
    funding_rates = models.JSONField(default=dict)
    liquidation_volume_24h = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
    )
    liquidation_long_percent = models.FloatField(null=True)
    liquidation_short_percent = models.FloatField(null=True)
    open_interest = models.JSONField(default=dict)
    btc_dominance = models.FloatField(null=True)
    is_stale = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fetched_at"]
        get_latest_by = "fetched_at"
        verbose_name = "Market Sentiment Data"
        verbose_name_plural = "Market Sentiment Data"

    @classmethod
    def get_latest(cls) -> "MarketSentimentData | None":
        """Get the most recent market sentiment data."""
        return cls.objects.first()

    def __str__(self) -> str:
        return f"Market Sentiment @ {self.fetched_at}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance: User, created: bool, **kwargs) -> None:
    """
    Signal handler to auto-create UserProfile when a User is created.

    This ensures every user has a profile with default settings.

    Requirements:
    - 1.1: Create UserProfile with default settings on user registration
    """
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance: User, **kwargs) -> None:
    """
    Signal handler to save UserProfile when User is saved.

    This ensures the profile is saved when the user is updated.
    """
    # Only save if profile exists (it might not during initial creation)
    if hasattr(instance, "profile"):
        instance.profile.save()
