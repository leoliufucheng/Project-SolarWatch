from __future__ import annotations

"""
SolarWatch Base Scraper Interface
===================================
Abstract base class for all platform-specific review scrapers.

Design notes:
  - fetch_reviews MUST accept region_iso because we scrape per-region.
    Different regions return different review pools (language, content, volume).
  - Each implementation (Google Play, App Store) inherits from this ABC.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from src.models.database import RawReview


class BaseScraper(ABC):
    """
    Abstract base class for review scrapers.

    Concrete implementations:
      - GooglePlayScraper (Sprint 2)
      - AppStoreScraper (Sprint 2)

    Usage:
        scraper = GooglePlayScraper()
        reviews = scraper.fetch_reviews(
            app_id="com.huawei.smartpvms",
            region_iso="DE",
            since_date=datetime(2025, 9, 10)
        )
    """

    @abstractmethod
    def fetch_reviews(
        self,
        app_id: str,
        region_iso: str,
        since_date: datetime,
    ) -> List[RawReview]:
        """
        Fetch reviews from the platform for a specific app and region.

        Args:
            app_id:      Platform-specific app identifier
                         (e.g., Google Play package name or App Store numeric ID).
            region_iso:  ISO 3166-1 alpha-2 country code (e.g., 'DE', 'AT', 'PL').
                         CRITICAL: We are multi-region — cannot default to a single country.
            since_date:  Only fetch reviews published after this date (UTC).
                         Used for incremental ingestion.

        Returns:
            List of RawReview ORM instances (not yet committed to DB).

        Raises:
            ScrapingError: If the platform API returns an error or times out.
        """
        ...

    @abstractmethod
    def get_platform_name(self) -> str:
        """Return the platform identifier (e.g., 'google_play', 'app_store')."""
        ...


class ScrapingError(Exception):
    """Raised when a scraping operation fails."""

    def __init__(self, platform: str, app_id: str, region: str, message: str):
        self.platform = platform
        self.app_id = app_id
        self.region = region
        super().__init__(
            f"[{platform}] Failed to scrape {app_id} in {region}: {message}"
        )
