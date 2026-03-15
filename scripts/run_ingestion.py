#!/usr/bin/env python3
from __future__ import annotations

"""
SolarWatch Ingestion Runner
==============================
CLI entry point for running the review ingestion pipeline.

Usage:
    # Full run (all apps, all regions, both platforms)
    python scripts/run_ingestion.py

    # Google Play only, specific app
    python scripts/run_ingestion.py --platform google_play --app "Huawei FusionSolar"

    # Specific region
    python scripts/run_ingestion.py --region DE
"""
import argparse
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from src.ingestion.ingestion_manager import IngestionManager
from src.utils.db import init_database
from src.utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="SolarWatch Review Ingestion Pipeline"
    )
    parser.add_argument(
        "--platform",
        choices=["google_play", "app_store", "both"],
        default="both",
        help="Platform to scrape (default: both)",
    )
    parser.add_argument(
        "--app",
        type=str,
        default=None,
        help="Specific app name to scrape (e.g., 'Huawei FusionSolar')",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Specific region ISO code (e.g., 'DE')",
    )
    args = parser.parse_args()

    # Ensure DB is initialized
    init_database()

    console.print("\n[bold cyan]🔄 SolarWatch Ingestion Pipeline[/bold cyan]\n")
    console.print(f"  Platform: [yellow]{args.platform}[/yellow]")
    console.print(f"  App:      [yellow]{args.app or 'All'}[/yellow]")
    console.print(f"  Region:   [yellow]{args.region or 'All'}[/yellow]")
    console.print()

    # Run ingestion
    manager = IngestionManager()
    platform = None if args.platform == "both" else args.platform
    summary = manager.run(
        platform_filter=platform,
        app_filter=args.app,
        region_filter=args.region,
    )

    # Display summary table
    _print_summary(summary)


def _print_summary(summary: dict) -> None:
    """Print ingestion results as a Rich table."""
    table = Table(title="Ingestion Summary", show_lines=True)
    table.add_column("App", style="cyan", min_width=20)
    table.add_column("Region", style="magenta", justify="center")
    table.add_column("Platform", style="blue")
    table.add_column("New Reviews", justify="right")
    table.add_column("Status", justify="center")

    total_new = 0
    total_errors = 0

    for (app, region, platform), count in sorted(summary.items()):
        if count < 0:
            status = "[red]❌ ERROR[/red]"
            total_errors += 1
            count_str = "-"
        elif count == 0:
            status = "[dim]⚪ No new[/dim]"
            count_str = "0"
        else:
            status = "[green]✅ OK[/green]"
            count_str = f"[bold green]{count}[/bold green]"
            total_new += count

        table.add_row(app, region, platform, count_str, status)

    console.print(table)
    console.print(
        f"\n  [bold green]Total new reviews: {total_new}[/bold green]  |  "
        f"[bold red]Errors: {total_errors}[/bold red]\n"
    )


if __name__ == "__main__":
    main()
