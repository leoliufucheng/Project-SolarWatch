from __future__ import annotations

"""
SolarWatch ORM Models
======================
Two core tables forming the data foundation:
  - raw_reviews:       Data fidelity layer (ETL starting point)
  - processed_reviews: Cognitive analysis layer (core data asset)

Design Principle:
  raw_reviews stores the unmodified original data.
  processed_reviews stores LLM analysis results with anti-hallucination metadata.
  The relationship is 1:1 (one processed_review per raw_review).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all SolarWatch models."""
    pass


# ─── Import enums from constants ──────────────────────────
# We use native Python enums via SQLAlchemy's Enum type.
# The enum values are stored as strings in SQLite.
from src.config.constants import (
    ImpactSeverity,
    PrimaryCategory,
    SourcePlatform,
    UserPersona,
)


def _utcnow() -> datetime:
    """Generate timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# ─── Table A: raw_reviews ─────────────────────────────────

class RawReview(Base):
    """
    Raw Reviews Table — preserves data fidelity.

    Purpose: Store the original, unmodified review data as scraped from
    Google Play / App Store. This is the ETL starting point; all downstream
    analysis derives from this table.

    Key business fields:
      - region_iso: Enables DACH/South/Emerging geo-aggregation
      - version:    Enables Dynamic Version Regression analysis
      - is_analyzed: Incremental processing marker
      - review_language: Original language code for cross-lingual analysis
    """
    __tablename__ = "raw_reviews"

    # --- Primary Key ---
    review_id = Column(
        String(255), primary_key=True,
        comment="Platform-native unique review ID"
    )

    # --- Source Metadata ---
    source_platform = Column(
        Enum(SourcePlatform, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        comment="Data source: google_play | app_store"
    )
    region_iso = Column(
        String(5), nullable=False,
        comment="ISO 3166-1 alpha-2 country code (DE/AT/CH/IT/ES/PL/RO). "
                "KEY FIELD for regional aggregation analysis"
    )
    app_name = Column(
        String(100), nullable=False,
        comment="Target app canonical name (matches settings.yaml)"
    )

    # --- Review Content ---
    content = Column(
        Text, nullable=False,
        comment="Original multilingual review text"
    )
    rating = Column(
        Integer, nullable=False,
        comment="User rating 1-5 stars"
    )
    review_language = Column(
        String(10), nullable=True,
        comment="Review language code (e.g., 'de', 'en', 'it'). "
                "Populated from API response. Enables cross-lingual analysis"
    )
    version = Column(
        String(50), nullable=True,
        comment="App version string (e.g., 5.3.21). "
                "KEY FIELD for computing Update Regression Rate"
    )
    review_date = Column(
        DateTime, nullable=False,
        comment="Review publication timestamp (UTC)"
    )

    # --- Processing State ---
    is_analyzed = Column(
        Boolean, default=False, nullable=False,
        comment="Whether this review has been processed by Step 3 (cognitive analysis)"
    )
    fetched_at = Column(
        DateTime, default=_utcnow, nullable=False,
        comment="Data fetch timestamp"
    )

    # --- Relationship ---
    processed_review = relationship(
        "ProcessedReview", back_populates="raw_review", uselist=False,
        cascade="all, delete-orphan"
    )

    # --- Constraints & Indexes ---
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
        CheckConstraint("length(content) > 0", name="ck_content_not_empty"),
        Index("ix_raw_app_date", "app_name", "review_date"),
        Index("ix_raw_region", "region_iso"),
        Index("ix_raw_unanalyzed", "is_analyzed"),
    )

    def __repr__(self) -> str:
        return (
            f"<RawReview(id={self.review_id!r}, app={self.app_name!r}, "
            f"rating={self.rating}, region={self.region_iso!r})>"
        )


# ─── Table B: processed_reviews ──────────────────────────

class ProcessedReview(Base):
    """
    Processed Reviews Table — core data asset.

    Purpose: Store LLM deep-analysis results. Every field has a clear
    business rationale:

      - primary_category:  Vertical slice analysis using 4+1 framework
      - user_persona:      Filter B2B installer feedback from B2C noise
      - impact_severity:   Weighted scoring (Critical×3 + Major×2 + Minor×1)
      - is_sarcasm:        Correct European ironic reviews (→ negative sentiment)
      - evidence_quote:    Anti-hallucination anchor (verified via string match)
      - sentiment_score:   Sarcasm-corrected sentiment [-1.0, 1.0]
      - root_cause_tag:    Technical root cause for clustering analysis

    Anti-hallucination metadata:
      - hallucination_check_passed: Python validation result
      - llm_model_version:          Reproducibility tracking

    DESIGN NOTE — Hallucination Storage:
      Business fields (primary_category, user_persona, impact_severity,
      evidence_quote, sentiment_score) are NULLABLE so that records with
      hallucination_check_passed=False can still be persisted for audit.
      Aggregation queries MUST filter on hallucination_check_passed=True.
    """
    __tablename__ = "processed_reviews"

    # --- Primary Key ---
    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Foreign Key ---
    raw_id = Column(
        String(255),
        ForeignKey("raw_reviews.review_id", ondelete="CASCADE"),
        nullable=False, unique=True,
        comment="FK to raw_reviews"
    )

    # --- LLM Analysis Results ---
    # NOTE: Business fields are nullable=True to allow storage of hallucinated
    # records (hallucination_check_passed=False). Aggregation queries MUST
    # filter WHERE hallucination_check_passed = TRUE.
    primary_category = Column(
        Enum(PrimaryCategory, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        comment="4+1 framework category (nullable for hallucination records)"
    )
    user_persona = Column(
        Enum(UserPersona, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        comment="User persona: Installer (B2B) vs Homeowner (B2C) (nullable for hallucination records)"
    )
    impact_severity = Column(
        Enum(ImpactSeverity, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        comment="Severity: Critical > Major > Minor (nullable for hallucination records)"
    )
    is_sarcasm = Column(
        Boolean, default=False, nullable=True,
        comment="Sarcasm flag. When True, sentiment must be corrected to negative"
    )
    evidence_quote = Column(
        Text, nullable=True,
        comment="Verbatim quote from original text. Anti-hallucination anchor — "
                "validated via substring match against raw content. "
                "Nullable: may be absent or fabricated in hallucination cases"
    )
    sentiment_score = Column(
        Float, nullable=True,
        comment="Sentiment score [-1.0, 1.0]. If is_sarcasm=True, this is the "
                "corrected (negative) value. Nullable for hallucination records"
    )
    root_cause_tag = Column(
        Text, nullable=True,
        comment="Technical root cause tag (e.g., 'WiFi Handshake Timeout', "
                "'OTA Update Bricked')"
    )

    # --- Anti-Hallucination Metadata ---
    hallucination_check_passed = Column(
        Boolean, nullable=False,
        comment="evidence_quote validation result. False = hallucination detected"
    )
    processed_at = Column(
        DateTime, default=_utcnow, nullable=False,
        comment="Analysis completion timestamp"
    )
    llm_model_version = Column(
        String(50), nullable=True,
        comment="LLM model version used (for reproducibility)"
    )

    # --- Relationship ---
    raw_review = relationship("RawReview", back_populates="processed_review")

    # --- Constraints & Indexes ---
    __table_args__ = (
        # Sentiment range only enforced for non-hallucinated records (NULL is allowed)
        CheckConstraint(
            "sentiment_score IS NULL OR (sentiment_score >= -1.0 AND sentiment_score <= 1.0)",
            name="ck_sentiment_range"
        ),
        Index("ix_proc_category", "primary_category"),
        Index("ix_proc_severity", "impact_severity"),
        Index("ix_proc_persona", "user_persona"),
        Index("ix_proc_hallucination", "hallucination_check_passed"),
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessedReview(id={self.id}, raw_id={self.raw_id!r}, "
            f"cat={self.primary_category}, sev={self.impact_severity})>"
        )


# ─── Table C: app_releases ─────────────────────────────────

class AppRelease(Base):
    """
    App Releases Table — Ground-truth version history.

    Purpose: Establish the official 'Zero Moment' (T) for release blast radius calculations.
    It maps a specific brand's version to an exact release date, preventing timezone drift
    and ensuring we compute against true updates rather than legacy user stragglers.
    """
    __tablename__ = "app_releases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_name = Column(
        String(100), nullable=False, index=True,
        comment="Must perfectly match app_name in raw_reviews"
    )
    platform = Column(
        Enum(SourcePlatform, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        comment="app_store or google_play"
    )
    version = Column(
        String(50), nullable=False,
        comment="The exact version string (e.g., 'v2.1.0')"
    )
    release_date = Column(
        DateTime, nullable=False, index=True,
        comment="Official release launch date (Zero Moment/T)"
    )
    changelog = Column(
        Text, nullable=True,
        comment="What changed? Useful for deep attribution analysis."
    )
    is_major_update = Column(
        Boolean, default=False, nullable=False,
        comment="True if X.0.0 or semantic major bump"
    )

    # --- Constraints & Indexes ---
    __table_args__ = (
        Index("uix_app_platform_version", "app_name", "platform", "version", unique=True),
    )

    def __repr__(self) -> str:
        return f"<AppRelease(app='{self.app_name}', v='{self.version}', date='{self.release_date}')>"
