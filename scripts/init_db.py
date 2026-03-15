#!/usr/bin/env python3
"""
SolarWatch — Database Initialization Script
=============================================
Creates the SQLite database and all tables.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --db-path /custom/path/solarwatch.db
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.db import init_database, get_engine
from src.utils.logger import get_logger
from src.config.settings import load_settings

logger = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize SolarWatch database")
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Override database path (default: from settings.yaml)",
    )
    args = parser.parse_args()

    logger.info("[bold cyan]SolarWatch Database Initialization[/bold cyan]")

    # Load settings to show config
    settings = load_settings()
    db_path = args.db_path or settings.database.path
    logger.info(f"Database path: {db_path}")

    # Create tables
    init_database(db_path)

    # Verify by listing tables
    engine = get_engine(db_path)
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    logger.info(f"Tables created: {tables}")

    for table in tables:
        columns = inspector.get_columns(table)
        col_names = [c["name"] for c in columns]
        logger.info(f"  {table}: {col_names}")

    logger.info("[bold green]✓ Database initialization complete![/bold green]")


if __name__ == "__main__":
    main()
