from __future__ import annotations

"""
SolarWatch Database Session Management
========================================
Provides SQLite engine creation and session lifecycle management.
Uses contextmanager pattern for safe transaction handling.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import load_settings
from src.models.database import Base
from src.utils.logger import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def _enable_sqlite_fk(dbapi_con, connection_record) -> None:
    """Enable SQLite foreign key enforcement (off by default)."""
    cursor = dbapi_con.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(db_path: str | Path | None = None) -> Engine:
    """
    Get or create the SQLAlchemy engine.

    Args:
        db_path: Override path to SQLite file. Defaults to settings.yaml value.

    Returns:
        SQLAlchemy Engine instance.
    """
    global _engine

    if _engine is not None:
        return _engine

    if db_path is None:
        settings = load_settings()
        db_path = settings.database.path

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        pool_pre_ping=True,
    )

    # Enable FK enforcement for SQLite
    event.listen(_engine, "connect", _enable_sqlite_fk)

    logger.info(f"Database engine created: {db_path}")
    return _engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker:
    """Get or create session factory."""
    global _SessionFactory

    if _SessionFactory is not None:
        return _SessionFactory

    if engine is None:
        engine = get_engine()

    _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Provide a transactional session scope.

    Usage:
        with get_session() as session:
            session.query(RawReview).all()

    Automatically commits on success, rolls back on exception.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database(db_path: str | Path | None = None) -> None:
    """
    Initialize database — create all tables defined in Base.metadata.

    Args:
        db_path: Override path. Defaults to settings.yaml value.
    """
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    logger.info("All database tables created successfully.")


def reset_engine() -> None:
    """Reset the cached engine and session factory (useful for testing)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def bulk_insert_ignore(reviews: list) -> int:
    """
    Bulk insert RawReview records, ignoring duplicates by review_id.

    Uses SQLite's INSERT OR IGNORE dialect for idempotent ingestion.
    This ensures that re-running the scraper for the same time window
    does not produce duplicate records.

    Args:
        reviews: List of RawReview ORM instances (detached / transient).

    Returns:
        Number of newly inserted records (excludes ignored duplicates).
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if not reviews:
        return 0

    engine = get_engine()

    # Convert ORM objects to dicts for dialect-specific insert
    records = []
    for r in reviews:
        records.append({
            "review_id": r.review_id,
            "source_platform": r.source_platform.value if hasattr(r.source_platform, 'value') else r.source_platform,
            "region_iso": r.region_iso,
            "app_name": r.app_name,
            "content": r.content,
            "rating": r.rating,
            "review_language": r.review_language,
            "version": r.version,
            "review_date": r.review_date,
            "is_analyzed": r.is_analyzed,
            "fetched_at": r.fetched_at or _utcnow(),
        })

    from src.models.database import RawReview as RawReviewModel
    stmt = sqlite_insert(RawReviewModel.__table__).values(records)
    stmt = stmt.on_conflict_do_nothing(index_elements=["review_id"])

    with engine.begin() as conn:
        result = conn.execute(stmt)
        inserted = result.rowcount

    logger.info(f"Bulk insert: {inserted}/{len(records)} new records (rest skipped as duplicates)")
    return inserted


def _utcnow():
    """Import-safe UTC now helper for bulk_insert_ignore."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
