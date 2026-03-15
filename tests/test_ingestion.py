from __future__ import annotations

"""
SolarWatch Ingestion Integration Tests
=========================================
Tests for Google Play scraper, App Store scraper, ingestion manager,
and bulk_insert_ignore deduplication.

All external API calls are mocked.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.constants import SourcePlatform
from src.models.database import Base, RawReview
from src.utils.db import (
    bulk_insert_ignore,
    get_engine,
    get_session,
    init_database,
    reset_engine,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _setup_test_db(tmp_path):
    """Create a fresh in-memory test DB for each test."""
    reset_engine()
    test_db = tmp_path / "test.db"
    init_database(str(test_db))
    yield
    reset_engine()


def _make_gp_review(review_id: str, days_ago: int = 0, rating: int = 4) -> dict:
    """Create a mock Google Play review response dict."""
    return {
        "reviewId": review_id,
        "content": f"Test review content for {review_id}",
        "score": rating,
        "appVersion": "2.1.0",
        "at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago),
        "userName": "TestUser",
    }


def _make_rss_entry(review_id: str, days_ago: int = 0, rating: int = 4) -> dict:
    """Create a mock iTunes RSS review entry dict."""
    review_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago)
    return {
        "id": {"label": review_id},
        "content": {"label": f"Test iOS review for {review_id}"},
        "im:rating": {"label": str(rating)},
        "im:version": {"label": "3.0.1"},
        "updated": {"label": review_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")},
        "author": {"name": {"label": "TestUser"}},
    }


def _make_rss_response(entries: list) -> dict:
    """Wrap entries in RSS feed structure."""
    return {"feed": {"entry": entries}}



# ─── Google Play Scraper Tests ────────────────────────────


class TestGooglePlayScraper:
    """Tests for GooglePlayReviewScraper."""

    @patch("src.ingestion.google_play_scraper.gp_reviews")
    def test_fetches_new_reviews(self, mock_reviews):
        """Should return RawReview objects for reviews newer than since_date."""
        mock_reviews.return_value = (
            [_make_gp_review("gp-1", days_ago=1), _make_gp_review("gp-2", days_ago=2)],
            None,  # no continuation token
        )

        from src.ingestion.google_play_scraper import GooglePlayReviewScraper

        scraper = GooglePlayReviewScraper()
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        results = scraper.fetch_reviews("com.test.app", "DE", since)

        assert len(results) == 2
        assert all(isinstance(r, RawReview) for r in results)
        assert results[0].review_id == "gp-1"
        assert results[0].region_iso == "DE"
        assert results[0].source_platform == SourcePlatform.GOOGLE_PLAY
        assert results[0].is_analyzed is False

    @patch("src.ingestion.google_play_scraper.gp_reviews")
    def test_breaks_on_old_reviews(self, mock_reviews):
        """Should stop collecting when hitting reviews older than since_date."""
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
        mock_reviews.return_value = (
            [
                _make_gp_review("gp-new", days_ago=1),
                _make_gp_review("gp-old", days_ago=10),
                _make_gp_review("gp-older", days_ago=20),
            ],
            None,
        )

        from src.ingestion.google_play_scraper import GooglePlayReviewScraper

        scraper = GooglePlayReviewScraper()
        results = scraper.fetch_reviews("com.test.app", "DE", since)

        assert len(results) == 1
        assert results[0].review_id == "gp-new"

    @patch("src.ingestion.google_play_scraper.gp_reviews")
    def test_skips_empty_content(self, mock_reviews):
        """Should skip reviews with empty content."""
        empty_review = _make_gp_review("gp-empty")
        empty_review["content"] = ""
        mock_reviews.return_value = ([empty_review], None)

        from src.ingestion.google_play_scraper import GooglePlayReviewScraper

        scraper = GooglePlayReviewScraper()
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        results = scraper.fetch_reviews("com.test.app", "DE", since)

        assert len(results) == 0


# ─── App Store Scraper Tests ─────────────────────────────


class TestAppStoreScraper:
    """Tests for AppStoreReviewScraper (iTunes RSS API)."""

    @patch("src.ingestion.app_store_scraper.requests.Session.get")
    def test_fetches_new_reviews(self, mock_get):
        """Should return RawReview objects for reviews newer than since_date."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_rss_response([
            {"id": {"label": "app-metadata"}},  # No im:rating → skipped
            _make_rss_entry("ios-1", days_ago=1),
            _make_rss_entry("ios-2", days_ago=2),
        ])
        mock_get.return_value = mock_resp

        from src.ingestion.app_store_scraper import AppStoreReviewScraper

        scraper = AppStoreReviewScraper()
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        results = scraper.fetch_reviews("1234567890", "DE", since)

        assert len(results) == 2
        assert all(isinstance(r, RawReview) for r in results)
        assert results[0].source_platform == SourcePlatform.APP_STORE
        assert results[0].region_iso == "DE"
        assert results[0].review_language == "de"  # From REGION_LANG_MAP

    @patch("src.ingestion.app_store_scraper.requests.Session.get")
    def test_filters_old_reviews(self, mock_get):
        """Should skip reviews older than since_date."""
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_rss_response([
            _make_rss_entry("ios-new", days_ago=1),
            _make_rss_entry("ios-old", days_ago=10),
        ])
        mock_get.return_value = mock_resp

        from src.ingestion.app_store_scraper import AppStoreReviewScraper

        scraper = AppStoreReviewScraper()
        results = scraper.fetch_reviews("1234567890", "DE", since)

        assert len(results) == 1


# ─── Bulk Insert Tests ────────────────────────────────────


class TestBulkInsertIgnore:
    """Tests for bulk_insert_ignore deduplication."""

    def test_inserts_new_records(self):
        """Should insert new records and return count."""
        reviews = [
            RawReview(
                review_id="bulk-1",
                source_platform=SourcePlatform.GOOGLE_PLAY,
                region_iso="DE",
                app_name="TestApp",
                content="Great app",
                rating=5,
                review_language="de",
                review_date=datetime(2025, 1, 1),
                is_analyzed=False,
            ),
        ]
        count = bulk_insert_ignore(reviews)
        assert count == 1

    def test_ignores_duplicates(self):
        """Second insert of same review_id should return 0."""
        review = RawReview(
            review_id="dup-1",
            source_platform=SourcePlatform.GOOGLE_PLAY,
            region_iso="DE",
            app_name="TestApp",
            content="Duplicate test",
            rating=3,
            review_language="de",
            review_date=datetime(2025, 1, 1),
            is_analyzed=False,
        )
        first = bulk_insert_ignore([review])
        second = bulk_insert_ignore([review])
        assert first == 1
        assert second == 0

    def test_empty_list(self):
        """Empty input should return 0."""
        assert bulk_insert_ignore([]) == 0


# ─── Ingestion Manager Tests ─────────────────────────────


class TestIngestionManager:
    """Tests for IngestionManager orchestration."""

    @patch("src.ingestion.ingestion_manager.GooglePlayReviewScraper")
    @patch("src.ingestion.ingestion_manager.AppStoreReviewScraper")
    def test_error_isolation(self, MockIOS, MockGP):
        """One failed (app, region) should not block others."""
        # GP scraper: first call fails, second succeeds
        mock_gp = MagicMock()
        mock_gp.fetch_reviews.side_effect = [
            Exception("API Error"),
            [
                RawReview(
                    review_id="ok-1",
                    source_platform=SourcePlatform.GOOGLE_PLAY,
                    region_iso="AT",
                    app_name="TestApp",
                    content="OK review",
                    rating=4,
                    review_language="de",
                    review_date=datetime(2025, 6, 1),
                    is_analyzed=False,
                ),
            ],
        ]
        MockGP.return_value = mock_gp

        # iOS scraper: always returns empty
        mock_ios = MagicMock()
        mock_ios.fetch_reviews.return_value = []
        MockIOS.return_value = mock_ios

        from src.ingestion.ingestion_manager import IngestionManager

        manager = IngestionManager()

        # Create a minimal settings-like setup for two regions
        from unittest.mock import PropertyMock
        from src.config.settings import TargetApp

        test_target = TargetApp(
            name="TestApp",
            team="red",
            google_play_id="com.test.app",
            app_store_id="1234567890",
            regions=["DE", "AT"],
        )
        manager._settings.targets = [test_target]

        summary = manager.run(platform_filter="google_play")

        # One should have errored, one should have succeeded
        error_count = sum(1 for v in summary.values() if v == -1)
        success_count = sum(1 for v in summary.values() if v >= 0)
        assert error_count >= 1
        assert success_count >= 1

    def test_cold_start_since_date(self):
        """With empty DB, since_date should be now - initial_lookback_days."""
        from src.ingestion.ingestion_manager import IngestionManager

        manager = IngestionManager()
        since = manager._get_since_date("NonExistentApp", "DE", "google_play")

        expected_min = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=181)
        expected_max = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=179)
        assert expected_min <= since <= expected_max
