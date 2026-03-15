from __future__ import annotations

"""
SolarWatch App Store Scraper — iTunes RSS API
================================================
Concrete implementation of BaseScraper for Apple App Store.
Uses pure requests + Apple iTunes RSS JSON API.
NO third-party scraper libraries.

API Endpoint:
    https://itunes.apple.com/{country}/rss/customerreviews/
    page={page}/id={app_id}/sortBy=mostRecent/json

Pagination: pages 1-10, up to 50 entries per page (max 500 reviews).
"""
import time
from datetime import datetime
from typing import List

import requests

from src.config.constants import REGION_LANG_MAP, SourcePlatform
from src.config.settings import load_settings
from src.ingestion.base_scraper import BaseScraper, ScrapingError
from src.models.database import RawReview
from src.utils.logger import get_logger
from src.utils.text_utils import clean_review_text

logger = get_logger(__name__)

# Realistic browser headers to prevent blocking
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*;q=0.01",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}

_RSS_URL_TEMPLATE = (
    "https://itunes.apple.com/{country}/rss/customerreviews"
    "/page={page}/id={app_id}/sortBy=mostRecent/json"
)

_MAX_PAGES = 10       # Apple RSS supports pages 1-10
_ENTRIES_PER_PAGE = 50  # Up to 50 entries per page


class AppStoreReviewScraper(BaseScraper):
    """
    App Store review scraper using Apple iTunes RSS JSON API.

    Fetches reviews with:
      - Per-region filtering (country parameter)
      - Pagination through pages 1-10
      - Date filtering via since_date
      - Automatic retry with exponential backoff
      - REGION_LANG_MAP for review_language inference
    """

    def __init__(self):
        self._settings = load_settings()
        self._rate_limit = self._settings.scraping.rate_limit_appstore
        self._max_retries = self._settings.scraping.max_retries
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    def get_platform_name(self) -> str:
        return SourcePlatform.APP_STORE.value

    def fetch_reviews(
        self,
        app_id: str,
        region_iso: str,
        since_date: datetime,
    ) -> List[RawReview]:
        """
        Fetch App Store reviews via iTunes RSS JSON API.

        Paginates through pages 1-10, filtering by since_date.
        Stops when a page returns fewer than 50 entries.
        """
        app_name = self._resolve_app_name(app_id)
        country = region_iso.lower()
        collected: List[RawReview] = []

        logger.info(
            f"[AppStore] Fetching reviews: app_id={app_id}, "
            f"region={region_iso}, since={since_date.isoformat()}"
        )

        try:
            for page in range(1, _MAX_PAGES + 1):
                url = _RSS_URL_TEMPLATE.format(
                    country=country,
                    page=page,
                    app_id=app_id,
                )

                # Fetch with retry
                data = self._fetch_with_retry(url)
                if data is None:
                    break  # Unrecoverable error, stop pagination

                entries = data.get("feed", {}).get("entry", [])
                if not entries:
                    logger.debug(f"[AppStore] Page {page}: no entries, stopping")
                    break

                page_count = 0
                for entry in entries:
                    # Skip app metadata entry (first entry has no im:rating)
                    if "im:rating" not in entry:
                        continue

                    # Parse review date
                    review_date = self._parse_date(
                        entry.get("updated", {}).get("label", "")
                    )
                    if review_date is None:
                        continue

                    # Incremental filter
                    compare_since = since_date.replace(tzinfo=None) if hasattr(since_date, 'tzinfo') and since_date.tzinfo is not None else since_date
                    if review_date <= compare_since:
                        continue  # Skip old reviews (RSS not guaranteed sorted)

                    # Extract content
                    content = entry.get("content", {}).get("label", "")
                    if not content or not content.strip():
                        continue

                    review = RawReview(
                        review_id=entry.get("id", {}).get("label", ""),
                        source_platform=SourcePlatform.APP_STORE,
                        region_iso=region_iso,
                        app_name=app_name,
                        content=clean_review_text(content),
                        rating=int(entry.get("im:rating", {}).get("label", "0")),
                        # Apple API doesn't return language; infer from region
                        review_language=REGION_LANG_MAP.get(region_iso, country),
                        version=entry.get("im:version", {}).get("label"),
                        review_date=review_date,
                        is_analyzed=False,
                    )
                    collected.append(review)
                    page_count += 1

                logger.debug(
                    f"[AppStore] Page {page}: {len(entries)} entries, "
                    f"{page_count} new reviews collected"
                )

                # Stop if page has fewer entries than expected (end of data)
                if len(entries) < _ENTRIES_PER_PAGE:
                    break

                # Rate limiting between pages
                time.sleep(self._rate_limit)

        except ScrapingError:
            raise  # Re-raise our own errors
        except Exception as e:
            raise ScrapingError(
                platform="app_store",
                app_id=app_id,
                region=region_iso,
                message=str(e),
            ) from e

        logger.info(
            f"[AppStore] Complete: {app_id} in {region_iso} → {len(collected)} new reviews"
        )
        return collected

    def _fetch_with_retry(self, url: str) -> dict | None:
        """Fetch a URL with exponential backoff retry."""
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._session.get(url, timeout=15)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 404:
                    logger.warning(f"[AppStore] 404 for {url} — app may not exist in this region")
                    return None

                logger.warning(
                    f"[AppStore] HTTP {resp.status_code} on attempt {attempt}/{self._max_retries}"
                )

            except (requests.exceptions.RequestException, ValueError) as e:
                logger.warning(
                    f"[AppStore] Request error on attempt {attempt}/{self._max_retries}: {e}"
                )

            if attempt < self._max_retries:
                backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
                time.sleep(backoff)

        logger.error(f"[AppStore] All {self._max_retries} retries exhausted for {url}")
        return None

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        """Parse iTunes RSS date format: '2026-03-09T12:00:00-07:00' → naive datetime."""
        if not date_str:
            return None
        try:
            # Strip timezone offset for naive datetime comparison
            # Format: "2026-03-09T12:37:36-07:00"
            clean = date_str
            if "+" in clean:
                clean = clean.rsplit("+", 1)[0]
            elif clean.count("-") > 2:
                # Handle negative UTC offset like -07:00
                clean = clean.rsplit("-", 1)[0]

            return datetime.fromisoformat(clean)
        except (ValueError, AttributeError):
            return None

    def _resolve_app_name(self, app_id: str) -> str:
        """Resolve app_store_id back to canonical app name from settings."""
        for target in self._settings.targets:
            if target.app_store_id == app_id:
                return target.name
        return app_id
