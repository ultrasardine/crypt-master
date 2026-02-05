"""
Migration to make the user FK non-nullable on Bot model.

This migration runs after the data backfill in core.0004_backfill_user_fk,
which ensures all existing Bot records have a user assigned.

Requirements:
- 11.3: Enforce non-null user constraints on new records after migration completes
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Make the user FK non-nullable on Bot model."""

    dependencies = [
        ("bots", "0002_add_user_fk"),
        ("core", "0004_backfill_user_fk"),  # Depends on the backfill migration
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="bot",
            name="user",
            field=models.ForeignKey(
                help_text="The user who owns this bot",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bots",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
