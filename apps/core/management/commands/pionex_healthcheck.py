"""
Pionex API health check management command.

Verifies that Pionex API credentials are configured correctly and the API is reachable.
"""

import asyncio
import sys
from datetime import UTC, datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from lib.pionex.client import PionexClient
from lib.pionex.models import PionexAPIError


class Command(BaseCommand):
    """Check Pionex API connectivity and credentials."""

    help = "Verify Pionex API credentials and connectivity"

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed response information",
        )
        parser.add_argument(
            "--test-balances",
            action="store_true",
            help="Also test fetching account balances (requires read permissions)",
        )
        parser.add_argument(
            "--test-bots",
            action="store_true",
            help="Also test fetching bot list (requires bot permissions)",
        )

    def handle(self, *args, **options):
        """Execute the health check."""
        verbose = options["verbose"]
        test_balances = options["test_balances"]
        test_bots = options["test_bots"]

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("Pionex API Health Check"))
        self.stdout.write("=" * 60 + "\n")

        # Check environment configuration
        self._check_env_config()

        api_key = settings.PIONEX_API_KEY
        api_secret = settings.PIONEX_API_SECRET

        if not api_key or not api_secret:
            raise CommandError(
                "PIONEX_API_KEY and PIONEX_API_SECRET must be set in environment.\n"
                "See .env.example for configuration details."
            )

        # Run async health checks
        try:
            asyncio.run(self._run_checks(api_key, api_secret, verbose, test_balances, test_bots))
        except PionexAPIError as e:
            self._handle_api_error(e)
            sys.exit(1)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"\n✗ Unexpected error: {e}"))
            if verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✓ All health checks passed!"))
        self.stdout.write("=" * 60 + "\n")

    def _check_env_config(self):
        """Check and display environment configuration."""
        self.stdout.write(self.style.HTTP_INFO("Environment Configuration:"))

        api_key = settings.PIONEX_API_KEY
        api_secret = settings.PIONEX_API_SECRET
        dry_run = getattr(settings, "DRY_RUN", True)

        # Mask API key for display
        if api_key:
            masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
            self.stdout.write(f"  API Key: {masked_key}")
        else:
            self.stdout.write(self.style.WARNING("  API Key: NOT SET"))

        if api_secret:
            self.stdout.write(f"  API Secret: {'*' * 16} (configured)")
        else:
            self.stdout.write(self.style.WARNING("  API Secret: NOT SET"))

        mode = "DRY-RUN (simulated)" if dry_run else "LIVE (real trades)"
        mode_style = self.style.WARNING if dry_run else self.style.ERROR
        self.stdout.write(f"  Trading Mode: {mode_style(mode)}")
        self.stdout.write("")

    async def _run_checks(
        self,
        api_key: str,
        api_secret: str,
        verbose: bool,
        test_balances: bool,
        test_bots: bool,
    ):
        """Run all health checks."""
        async with PionexClient(api_key=api_key, api_secret=api_secret) as client:
            # Test 1: Public endpoint (symbols)
            await self._test_public_endpoint(client, verbose)

            # Test 2: Authenticated endpoint (balances)
            if test_balances:
                await self._test_balances(client, verbose)

            # Test 3: Bot list
            if test_bots:
                await self._test_bots(client, verbose)

    async def _test_public_endpoint(self, client: PionexClient, verbose: bool):
        """Test public API endpoint."""
        self.stdout.write(self.style.HTTP_INFO("Testing public endpoint (symbols)..."))

        start = datetime.now(UTC)
        symbols = await client.get_symbols()
        elapsed = (datetime.now(UTC) - start).total_seconds()

        spot_count = sum(1 for s in symbols if s.symbol_type.value == "SPOT")
        perp_count = sum(1 for s in symbols if s.symbol_type.value == "PERP")

        self.stdout.write(self.style.SUCCESS(f"  ✓ Retrieved {len(symbols)} symbols in {elapsed:.2f}s"))
        self.stdout.write(f"    - SPOT pairs: {spot_count}")
        self.stdout.write(f"    - PERP pairs: {perp_count}")

        if verbose and symbols:
            self.stdout.write("    Sample symbols:")
            for symbol in symbols[:5]:
                self.stdout.write(f"      - {symbol.symbol} ({symbol.symbol_type.value})")
        self.stdout.write("")

    async def _test_balances(self, client: PionexClient, verbose: bool):
        """Test authenticated balances endpoint."""
        self.stdout.write(self.style.HTTP_INFO("Testing authenticated endpoint (balances)..."))

        start = datetime.now(UTC)
        balances = await client.get_balances()
        elapsed = (datetime.now(UTC) - start).total_seconds()

        non_zero = [b for b in balances if b.free > 0 or b.locked > 0]

        self.stdout.write(self.style.SUCCESS(f"  ✓ Retrieved {len(non_zero)} non-zero balances in {elapsed:.2f}s"))

        if verbose and non_zero:
            self.stdout.write("    Balances:")
            for balance in non_zero[:10]:
                total = balance.free + balance.locked
                self.stdout.write(f"      - {balance.currency}: {total:.8f} (free: {balance.free:.8f}, locked: {balance.locked:.8f})")
            if len(non_zero) > 10:
                self.stdout.write(f"      ... and {len(non_zero) - 10} more")
        self.stdout.write("")

    async def _test_bots(self, client: PionexClient, verbose: bool):
        """Test bot list endpoint."""
        self.stdout.write(self.style.HTTP_INFO("Testing bot list endpoint..."))

        start = datetime.now(UTC)
        bots = await client.list_bots()
        elapsed = (datetime.now(UTC) - start).total_seconds()

        active_bots = [b for b in bots if b.status.value == "ACTIVE"]

        self.stdout.write(self.style.SUCCESS(f"  ✓ Retrieved {len(bots)} bots in {elapsed:.2f}s"))
        self.stdout.write(f"    - Active: {len(active_bots)}")
        self.stdout.write(f"    - Total: {len(bots)}")

        if verbose and bots:
            self.stdout.write("    Bots:")
            for bot in bots[:5]:
                pnl_str = f"{bot.pnl_percent:.2f}%" if bot.pnl_percent else "N/A"
                self.stdout.write(f"      - {bot.bot_type.value} on {bot.symbol}: {bot.status.value}, P&L: {pnl_str}")
            if len(bots) > 5:
                self.stdout.write(f"      ... and {len(bots) - 5} more")
        self.stdout.write("")

    def _handle_api_error(self, error: PionexAPIError):
        """Handle and display API errors with helpful messages."""
        self.stderr.write(self.style.ERROR(f"\n✗ Pionex API Error"))
        self.stderr.write(f"  Status Code: {error.error.status_code}")
        self.stderr.write(f"  Error Code: {error.error.error_code or 'N/A'}")
        self.stderr.write(f"  Message: {error.error.message}")

        # Provide helpful suggestions based on error
        status = error.error.status_code
        code = error.error.error_code

        self.stderr.write(self.style.WARNING("\nPossible causes:"))

        if status == 401 or code in ("INVALID_SIGNATURE", "SIGNATURE_FAILED"):
            self.stderr.write("  - API secret may be incorrect")
            self.stderr.write("  - Timestamp drift between your system and Pionex servers")
            self.stderr.write("  - Check that your system clock is synchronized")

        elif status == 403 or "permission" in str(error.error.message).lower():
            self.stderr.write("  - API key may lack required permissions")
            self.stderr.write("  - Ensure key has: 'Read account information', 'Trade spot', 'Manage trading bots'")
            self.stderr.write("  - Check IP whitelist settings on Pionex")

        elif status == 429:
            self.stderr.write("  - Rate limit exceeded")
            self.stderr.write("  - Wait a few minutes and try again")

        elif status >= 500:
            self.stderr.write("  - Pionex API may be experiencing issues")
            self.stderr.write("  - Check Pionex status page or try again later")

        else:
            self.stderr.write("  - Verify API key and secret are correct")
            self.stderr.write("  - Check Pionex API documentation for error details")
