"""
Data migration to backfill user foreign keys for existing records.

This migration:
1. Creates a system user for orphan records (records without user association)
2. Assigns existing Bot, Trade, and PortfolioSnapshot records to the system user
3. Makes the user FK non-nullable after backfill

Requirements:
- 11.2: Create a default system user for existing records without user association
- 11.3: Enforce non-null user constraints on new records after migration completes
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


SYSTEM_USER_USERNAME = "system"
SYSTEM_USER_EMAIL = "system@crypt-master.local"


def create_system_user_and_backfill(apps, schema_editor):
    """
    Create system user and assign orphan records to it.

    This function:
    1. Creates a system user if it doesn't exist
    2. Finds all Bot, Trade, and PortfolioSnapshot records without a user
    3. Assigns them to the system user
    """
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("core", "UserProfile")
    Bot = apps.get_model("bots", "Bot")
    Trade = apps.get_model("trading", "Trade")
    PortfolioSnapshot = apps.get_model("core", "PortfolioSnapshot")

    # Create or get the system user
    # Note: In migrations, we use the historical model which doesn't have
    # set_unusable_password(). We set password to '!' which Django recognizes
    # as an unusable password marker.
    system_user, created = User.objects.get_or_create(
        username=SYSTEM_USER_USERNAME,
        defaults={
            "email": SYSTEM_USER_EMAIL,
            "password": "!",  # Django's marker for unusable password
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
        },
    )

    if created:
        # Create a profile for the system user
        # Note: The signal won't fire during migrations, so we create it manually
        UserProfile.objects.get_or_create(user=system_user)

    # Backfill orphan Bot records
    orphan_bots = Bot.objects.filter(user__isnull=True)
    orphan_bot_count = orphan_bots.count()
    if orphan_bot_count > 0:
        orphan_bots.update(user=system_user)
        print(f"  Assigned {orphan_bot_count} orphan Bot records to system user")

    # Backfill orphan Trade records
    orphan_trades = Trade.objects.filter(user__isnull=True)
    orphan_trade_count = orphan_trades.count()
    if orphan_trade_count > 0:
        orphan_trades.update(user=system_user)
        print(f"  Assigned {orphan_trade_count} orphan Trade records to system user")

    # Backfill orphan PortfolioSnapshot records
    orphan_snapshots = PortfolioSnapshot.objects.filter(user__isnull=True)
    orphan_snapshot_count = orphan_snapshots.count()
    if orphan_snapshot_count > 0:
        orphan_snapshots.update(user=system_user)
        print(f"  Assigned {orphan_snapshot_count} orphan PortfolioSnapshot records to system user")

    if created:
        print(f"  Created system user '{SYSTEM_USER_USERNAME}' for orphan records")
    else:
        print(f"  Using existing system user '{SYSTEM_USER_USERNAME}'")


def reverse_backfill(apps, schema_editor):
    """
    Reverse the backfill by setting user to NULL for system user's records.

    Note: This does NOT delete the system user, as it may have been used
    for other purposes. It only removes the user association from records
    that were assigned to the system user during the forward migration.
    """
    User = apps.get_model("auth", "User")
    Bot = apps.get_model("bots", "Bot")
    Trade = apps.get_model("trading", "Trade")
    PortfolioSnapshot = apps.get_model("core", "PortfolioSnapshot")

    try:
        system_user = User.objects.get(username=SYSTEM_USER_USERNAME)

        # Set user to NULL for records owned by system user
        # This reverses the backfill operation
        Bot.objects.filter(user=system_user).update(user=None)
        Trade.objects.filter(user=system_user).update(user=None)
        PortfolioSnapshot.objects.filter(user=system_user).update(user=None)

        print(f"  Removed user association from system user's records")
    except User.DoesNotExist:
        # System user doesn't exist, nothing to reverse
        print("  System user not found, nothing to reverse")


class Migration(migrations.Migration):
    """
    Data migration to backfill user foreign keys and make them non-nullable.

    This migration depends on all the previous migrations that added the
    nullable user FK fields to Bot, Trade, and PortfolioSnapshot models.
    """

    dependencies = [
        ("core", "0003_add_user_fk"),
        ("bots", "0002_add_user_fk"),
        ("trading", "0002_add_user_fk"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: Run the data migration to create system user and backfill
        migrations.RunPython(
            create_system_user_and_backfill,
            reverse_code=reverse_backfill,
        ),
        # Step 2: Make the user FK non-nullable on PortfolioSnapshot
        # (This is in the core app, so we can alter it here)
        migrations.AlterField(
            model_name="portfoliosnapshot",
            name="user",
            field=models.ForeignKey(
                help_text="The user who owns this portfolio snapshot",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="portfolio_snapshots",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
