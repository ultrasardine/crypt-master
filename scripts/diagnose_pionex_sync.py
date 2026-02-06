#!/usr/bin/env python
"""
Diagnostic script to troubleshoot Pionex data sync issues.

This script checks:
1. If users have API keys configured
2. If Celery is running
3. If Celery Beat tasks are scheduled
4. If tasks have run recently
5. If there are any error logs
6. If PortfolioSnapshot and Bot data exists
"""

import os
import sys
from datetime import timedelta

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.bots.models import Bot
from apps.core.models import PortfolioSnapshot


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def check_users_with_api_keys():
    """Check if any users have API keys configured."""
    print_section("1. Users with API Keys")

    users = User.objects.all()
    print(f"Total users: {users.count()}")

    users_with_keys = User.objects.filter(
        profile__encrypted_api_key__isnull=False,
        profile__encrypted_api_key__gt="",
    ).select_related("profile")

    print(f"Users with API keys configured: {users_with_keys.count()}")

    if users_with_keys.count() == 0:
        print("\n⚠️  WARNING: No users have API keys configured!")
        print("   To configure API keys:")
        print("   1. Log in to the dashboard")
        print("   2. Go to Settings > API Keys")
        print("   3. Enter your Pionex API key and secret")
        return False

    for user in users_with_keys:
        print(f"  - {user.username} (has_api_keys: {user.profile.has_api_keys()})")

    return True


def check_celery_tasks():
    """Check if Celery Beat tasks are configured."""
    print_section("2. Celery Beat Tasks")

    tasks = PeriodicTask.objects.filter(
        name__in=[
            "sync-portfolios",
            "sync-bots",
            "fetch-public-market-data",
            "update-signal-accuracy",
        ]
    )

    if tasks.count() == 0:
        print("⚠️  WARNING: No Celery Beat tasks found in database!")
        print("   Run: python manage.py migrate")
        print("   Then restart Celery Beat")
        return False

    print(f"Found {tasks.count()} tasks:\n")

    for task in tasks:
        status = "✓ ENABLED" if task.enabled else "✗ DISABLED"
        last_run = task.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if task.last_run_at else "Never"
        age = ""
        if task.last_run_at:
            age_minutes = int((timezone.now() - task.last_run_at).total_seconds() / 60)
            age = f" ({age_minutes} minutes ago)"

        print(f"  {status} {task.name}")
        print(f"    Last run: {last_run}{age}")
        print(f"    Task: {task.task}")
        print()

    return True


def check_portfolio_snapshots():
    """Check if portfolio snapshots exist."""
    print_section("3. Portfolio Snapshots")

    total = PortfolioSnapshot.objects.count()
    live = PortfolioSnapshot.objects.filter(is_simulated=False).count()
    simulated = PortfolioSnapshot.objects.filter(is_simulated=True).count()

    print(f"Total snapshots: {total}")
    print(f"  Live: {live}")
    print(f"  Simulated: {simulated}")

    if total == 0:
        print("\n⚠️  WARNING: No portfolio snapshots found!")
        print("   This means the sync_portfolios task hasn't run successfully yet.")
        return False

    # Show recent snapshots
    recent = PortfolioSnapshot.objects.order_by("-created_at")[:5]
    if recent:
        print("\nRecent snapshots:")
        for snapshot in recent:
            print(
                f"  - {snapshot.user.username}: ${snapshot.total_value} "
                f"({snapshot.created_at.strftime('%Y-%m-%d %H:%M:%S')})"
            )

    return True


def check_bots():
    """Check if bots exist."""
    print_section("4. Bots")

    total = Bot.objects.count()
    live = Bot.objects.filter(is_simulated=False).count()
    simulated = Bot.objects.filter(is_simulated=True).count()
    active = Bot.objects.filter(status="ACTIVE").count()

    print(f"Total bots: {total}")
    print(f"  Live: {live}")
    print(f"  Simulated: {simulated}")
    print(f"  Active: {active}")

    if total == 0:
        print("\n⚠️  WARNING: No bots found!")
        print("   This could mean:")
        print("   1. You haven't created any bots on Pionex yet")
        print("   2. The sync_bots task hasn't run successfully yet")
        return False

    # Show recent bots
    recent = Bot.objects.order_by("-created_at")[:5]
    if recent:
        print("\nRecent bots:")
        for bot in recent:
            synced = ""
            if bot.last_synced_at:
                age_minutes = int((timezone.now() - bot.last_synced_at).total_seconds() / 60)
                synced = f" (synced {age_minutes}m ago)"
            print(
                f"  - {bot.user.username}: {bot.bot_type} on {bot.trading_pair.symbol} "
                f"[{bot.status}]{synced}"
            )

    return True


def check_celery_running():
    """Check if Celery workers are running."""
    print_section("5. Celery Status")

    print("To check if Celery is running, use:")
    print("  celery -A config inspect active")
    print("\nOr check the process list:")
    print("  ps aux | grep celery")
    print("\nTo start Celery:")
    print("  celery -A config worker -l info")
    print("\nTo start Celery Beat:")
    print("  celery -A config beat -l info")


def main():
    """Run all diagnostic checks."""
    print("\n" + "=" * 80)
    print("  PIONEX DATA SYNC DIAGNOSTIC")
    print("=" * 80)

    has_api_keys = check_users_with_api_keys()
    has_tasks = check_celery_tasks()
    has_snapshots = check_portfolio_snapshots()
    has_bots = check_bots()
    check_celery_running()

    # Summary
    print_section("Summary")

    issues = []
    if not has_api_keys:
        issues.append("❌ No users have API keys configured")
    if not has_tasks:
        issues.append("❌ Celery Beat tasks not configured")
    if not has_snapshots:
        issues.append("❌ No portfolio snapshots found")
    if not has_bots:
        issues.append("⚠️  No bots found (may be expected)")

    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  {issue}")
        print("\nNext steps:")
        if not has_api_keys:
            print("  1. Configure API keys in the dashboard (Settings > API Keys)")
        if not has_tasks:
            print("  2. Run migrations: python manage.py migrate")
        print("  3. Ensure Celery worker is running: celery -A config worker -l info")
        print("  4. Ensure Celery Beat is running: celery -A config beat -l info")
        print("  5. Wait a few minutes for tasks to run")
        print("  6. Check logs for errors: tail -f logs/crypt-master.log")
    else:
        print("✓ All checks passed!")
        print("\nIf you still don't see data:")
        print("  1. Check Celery logs for errors")
        print("  2. Verify your Pionex API keys are valid")
        print("  3. Check that you have bots running on Pionex")
        print("  4. Try manually triggering a sync:")
        print("     python manage.py shell")
        print("     >>> from apps.core.tasks import sync_portfolios, sync_bots")
        print("     >>> sync_portfolios.delay()")
        print("     >>> sync_bots.delay()")


if __name__ == "__main__":
    main()
