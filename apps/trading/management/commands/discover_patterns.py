"""
Management command for discovering strategy patterns.

This command analyzes historical signals and their outcomes to discover
winning strategy patterns that can be used to improve signal generation.

Requirements:
- 3.3.1: Management command exists under apps/trading/management/commands/
- 3.3.4: Groups with win rate above threshold stored as StrategyPattern records
- 3.3.5: Support --dry-run flag to preview patterns without saving
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from lib.analysis.pattern_miner import PatternMiner, PatternMinerConfig


class Command(BaseCommand):
    """
    Discover winning strategy patterns from historical signal data.

    This command analyzes historical signals with their outcomes, groups them
    by regime and indicator ranges, and stores patterns that meet the configured
    thresholds (win rate, average P&L, sample size).

    Usage:
        # Run pattern discovery and save patterns
        python manage.py discover_patterns

        # Preview patterns without saving (dry run)
        python manage.py discover_patterns --dry-run

        # Custom thresholds
        python manage.py discover_patterns --min-hit-rate 0.6 --min-avg-pnl 1.0

        # Custom lookback period
        python manage.py discover_patterns --lookback-days 180

    Requirements:
    - 3.3.1: Management command exists
    - 3.3.4: Store groups meeting thresholds as StrategyPattern records
    - 3.3.5: Support --dry-run flag to preview patterns without saving
    """

    help = "Discover winning strategy patterns from historical signal data"

    def add_arguments(self, parser: CommandParser) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview discovered patterns without saving to database",
        )
        parser.add_argument(
            "--min-sample-size",
            type=int,
            default=30,
            help="Minimum number of signals required to form a pattern (default: 30)",
        )
        parser.add_argument(
            "--min-hit-rate",
            type=float,
            default=0.55,
            help="Minimum win rate to store a pattern (default: 0.55)",
        )
        parser.add_argument(
            "--min-avg-pnl",
            type=float,
            default=0.5,
            help="Minimum average P&L percentage to store a pattern (default: 0.5)",
        )
        parser.add_argument(
            "--lookback-days",
            type=int,
            default=90,
            help="Number of days to look back for historical data (default: 90)",
        )

    def handle(self, *args, **options) -> None:
        """Execute the command."""
        dry_run = options["dry_run"]

        # Create configuration from command options
        config = PatternMinerConfig(
            min_sample_size=options["min_sample_size"],
            min_hit_rate=options["min_hit_rate"],
            min_avg_pnl=options["min_avg_pnl"],
            lookback_days=options["lookback_days"],
        )

        self.stdout.write(
            self.style.NOTICE(
                f"Starting pattern discovery with config:\n"
                f"  - Min sample size: {config.min_sample_size}\n"
                f"  - Min hit rate: {config.min_hit_rate:.1%}\n"
                f"  - Min avg P&L: {config.min_avg_pnl:.2f}%\n"
                f"  - Lookback days: {config.lookback_days}\n"
                f"  - Dry run: {dry_run}"
            )
        )

        # Create miner and discover patterns
        miner = PatternMiner(config=config)
        patterns = miner.discover_patterns(dry_run=dry_run)

        if not patterns:
            self.stdout.write(
                self.style.WARNING("No patterns discovered meeting the configured thresholds.")
            )
            return

        # Display summary
        self.stdout.write(
            self.style.SUCCESS(f"\nDiscovered {len(patterns)} pattern(s):")
        )

        for i, pattern in enumerate(patterns, 1):
            regime = pattern.feature_combination.get("regime", "UNKNOWN")
            self.stdout.write(
                f"\n  {i}. Pattern [{regime}]:\n"
                f"     - Feature combination: {pattern.feature_combination}\n"
                f"     - Sample size: {pattern.sample_size}\n"
                f"     - Hit rate: {pattern.hit_rate:.1%}\n"
                f"     - Average P&L: {pattern.average_pnl:.2f}%"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN] {len(patterns)} pattern(s) would be saved. "
                    "Run without --dry-run to save."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nSaved {len(patterns)} pattern(s) to database.")
            )
