from __future__ import annotations

"""
SolarWatch Google Play Scraper
================================
Concrete implementation of BaseScraper for Google Play Store.
Uses google-play-scraper library with per-region + incremental logic.
"""
import time
from datetime import datetime
from typing import List

from google_play_scraper import Sort
from google_play_scraper import reviews as gp_reviews

from src.config.constants import REGION_LANG_MAP, SourcePlatform
from src.config.settings import load_settings
from src.ingestion.base_scraper import BaseScraper, ScrapingError
from src.models.database import RawReview
from src.utils.logger import get_logger
from src.utils.text_utils import clean_review_text

logger = get_logger(__name__)


class GooglePlayReviewScraper(BaseScraper):
    """
    Google Play review scraper.

    Fetches reviews using google-play-scraper library with:
      - Per-region filtering (country + lang)
      - Sort.NEWEST for incremental efficiency
      - Pagination via continuation_token
      - Early break when hitting reviews older than since_date
    """

    def __init__(self):
        self._settings = load_settings()
        self._rate_limit = self._settings.scraping.rate_limit_google

    def get_platform_name(self) -> str:
        return SourcePlatform.GOOGLE_PLAY.value

    def fetch_reviews(
        self,
        app_id: str,
        region_iso: str,
        since_date: datetime,
    ) -> List[RawReview]:
        """
        Fetch Google Play reviews for a specific app and region.

        Paginates through all review pages sorted by newest first,
        stopping as soon as we encounter a review older than since_date.
        """
        app_name = self._resolve_app_name(app_id)
        # CRITICAL: AT→de, CH→de. Do NOT use region_iso.lower() as lang!
        lang = REGION_LANG_MAP.get(region_iso, region_iso.lower())
        country = region_iso.lower()
        collected: List[RawReview] = []
        continuation_token = None
        page = 0

        logger.info(
            f"[GooglePlay] Fetching reviews: app={app_id}, "
            f"region={region_iso}, since={since_date.isoformat()}"
        )

        try:
            while True:
                page += 1
                result, continuation_token = gp_reviews(
                    app_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=100,
                    continuation_token=continuation_token,
                )

                if not result:
                    logger.debug(f"[GooglePlay] No more results on page {page}")
                    break

                hit_old_review = False
                for raw in result:
                    review_date = raw.get("at")
                    if review_date is None:
                        continue

                    # Make naive datetime for comparison if needed
                    if hasattr(review_date, 'tzinfo') and review_date.tzinfo is not None:
                        compare_date = review_date.replace(tzinfo=None)
                    else:
                        compare_date = review_date

                    compare_since = since_date.replace(tzinfo=None) if hasattr(since_date, 'tzinfo') and since_date.tzinfo is not None else since_date

                    if compare_date <= compare_since:
                        hit_old_review = True
                        break  # Stop — all subsequent reviews are older

                    content = raw.get("content", "")
                    if not content or not content.strip():
                        continue  # Skip empty reviews

                    review = RawReview(
                        review_id=str(raw["reviewId"]),
                        source_platform=SourcePlatform.GOOGLE_PLAY,
                        region_iso=region_iso,
                        app_name=app_name,
                        content=clean_review_text(content),
                        rating=int(raw["score"]),
                        review_language=lang,  # From REGION_LANG_MAP
                        version=raw.get("appVersion"),
                        review_date=review_date,
                        is_analyzed=False,
                    )
                    collected.append(review)

                logger.debug(
                    f"[GooglePlay] Page {page}: fetched {len(result)} reviews, "
                    f"collected {len(collected)} total"
                )

                if hit_old_review:
                    logger.info(
                        f"[GooglePlay] Reached reviews older than since_date on page {page}, stopping"
                    )
                    break

                if continuation_token is None:
                    break  # No more pages

                # Rate limiting between pages
                time.sleep(self._rate_limit)

        except Exception as e:
            raise ScrapingError(
                platform="google_play",
                app_id=app_id,
                region=region_iso,
                message=str(e),
            ) from e

        logger.info(
            f"[GooglePlay] Complete: {app_id} in {region_iso} → {len(collected)} new reviews"
        )
        return collected

    def _resolve_app_name(self, app_id: str) -> str:
        """Resolve google_play_id back to canonical app name from settings."""
        for target in self._settings.targets:
            if target.google_play_id == app_id:
                return target.name
        return app_id  # Fallback to app_id if not found
