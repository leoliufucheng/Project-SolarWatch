"""SolarWatch Ingestion Package."""
from src.ingestion.base_scraper import BaseScraper, ScrapingError
from src.ingestion.google_play_scraper import GooglePlayReviewScraper
from src.ingestion.app_store_scraper import AppStoreReviewScraper
from src.ingestion.ingestion_manager import IngestionManager

__all__ = [
    "BaseScraper",
    "ScrapingError",
    "GooglePlayReviewScraper",
    "AppStoreReviewScraper",
    "IngestionManager",
]
