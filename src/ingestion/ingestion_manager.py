from __future__ import annotations

"""
SolarWatch Ingestion Manager
===============================
Orchestrates multi-app × multi-region review scraping.
Handles incremental logic, cold starts, error isolation, and summary reporting.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, text

from src.config.constants import SourcePlatform
from src.config.settings import Settings, TargetApp, load_settings
from src.ingestion.app_store_scraper import AppStoreReviewScraper
from src.ingestion.base_scraper import BaseScraper, ScrapingError
from src.ingestion.google_play_scraper import GooglePlayReviewScraper
from src.models.database import RawReview
from src.utils.db import bulk_insert_ignore, get_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


class IngestionManager:
    """
    Orchestrates the full ingestion pipeline.

    Iterates over all (target × region × platform) combinations,
    applies incremental logic, calls the appropriate scraper,
    and writes results to the database.

    Error isolation: a failure for one (app, region, platform) triple
    is logged but does NOT block other combinations.
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or load_settings()
        self._gp_scraper = GooglePlayReviewScraper()
        self._ios_scraper = AppStoreReviewScraper()

    def run(
        self,
        platform_filter: str | None = None,
        app_filter: str | None = None,
        region_filter: str | None = None,
    ) -> dict:
        """
        Execute the full ingestion cycle.

        Args:
            platform_filter: 'google_play', 'app_store', or None for both.
            app_filter:      Specific app name to scrape, or None for all.
            region_filter:   Specific region ISO code, or None for all.

        Returns:
            Summary dict: {(app, region, platform): count_of_new_reviews}
        """
        targets = self._settings.targets
        summary: dict = {}
        total_new = 0
        total_errors = 0

        # Apply app filter
        if app_filter:
            targets = [t for t in targets if t.name == app_filter]
            if not targets:
                logger.warning(f"No target found matching app_filter='{app_filter}'")
                return summary

        # Determine platforms
        platforms: List[str] = []
        if platform_filter is None or platform_filter == "both":
            platforms = ["google_play", "app_store"]
        else:
            platforms = [platform_filter]

        for target in targets:
            regions = target.regions
            if region_filter:
                regions = [r for r in regions if r == region_filter]

            for region in regions:
                for platform in platforms:
                    key = (target.name, region, platform)
                    try:
                        count = self._scrape_single(target, region, platform)
                        summary[key] = count
                        total_new += count
                    except ScrapingError as e:
                        logger.error(f"Scraping failed: {e}")
                        summary[key] = -1  # Mark as error
                        total_errors += 1
                    except Exception as e:
                        logger.error(
                            f"Unexpected error for {key}: {e}",
                            exc_info=True,
                        )
                        summary[key] = -1
                        total_errors += 1

        logger.info(
            f"Ingestion complete: {total_new} new reviews, "
            f"{total_errors} errors out of {len(summary)} combinations"
        )
        return summary

    def _scrape_single(
        self,
        target: TargetApp,
        region: str,
        platform: str,
    ) -> int:
        """
        Scrape reviews for a single (target, region, platform) combination.

        Returns the number of new reviews inserted.
        """
        # Determine since_date (incremental logic)
        since_date = self._get_since_date(target.name, region, platform)

        # Select scraper and app_id
        if platform == "google_play":
            scraper: BaseScraper = self._gp_scraper
            app_id = target.google_play_id
        else:
            scraper = self._ios_scraper
            app_id = target.app_store_id

        # Fetch reviews from API
        reviews = scraper.fetch_reviews(
            app_id=app_id,
            region_iso=region,
            since_date=since_date,
        )

        if not reviews:
            logger.debug(
                f"No new reviews for {target.name} in {region} ({platform})"
            )
            return 0

        # Write to DB with deduplication
        inserted = bulk_insert_ignore(reviews)
        return inserted

    def _get_since_date(
        self,
        app_name: str,
        region: str,
        platform: str,
    ) -> datetime:
        """
        Compute the since_date for incremental scraping.

        1. Query MAX(review_date) from raw_reviews for this (app, region, platform)
        2. If no prior data → cold start: now - initial_lookback_days
        """
        with get_session() as session:
            result = session.query(func.max(RawReview.review_date)).filter(
                RawReview.app_name == app_name,
                RawReview.region_iso == region,
                RawReview.source_platform == platform,
            ).scalar()

        if result is not None:
            logger.debug(
                f"Incremental: last review for {app_name}/{region}/{platform} "
                f"at {result.isoformat()}"
            )
            return result

        # Cold start
        lookback = self._settings.scraping.initial_lookback_days
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=lookback)
        logger.info(
            f"Cold start: {app_name}/{region}/{platform} → "
            f"looking back {lookback} days to {since.isoformat()}"
        )
        return since
