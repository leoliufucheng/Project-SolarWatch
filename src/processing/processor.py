from __future__ import annotations

"""
SolarWatch Cognitive Processor — Free-Tier Batch Mode
=======================================================
Designed for Gemini free-tier rate limits with circuit breaker.

Architecture:
  - Batch 50 reviews into ONE prompt → 1 API call per batch
  - Synchronous processing with time.sleep(15) between calls
  - Circuit breaker: 3 consecutive 429s → fuse → safe stop
  - Auto interim summary on completion or fuse trip

Processing flow per batch:
  1. Query 50 unanalyzed reviews from DB
  2. Build batch prompt (all 50 in one prompt)
  3. Call LLM API (single request)
  4. Parse JSON array response → map by review_index
  5. Validate each evidence_quote (hallucination guard)
  6. Apply sarcasm correction
  7. Write ProcessedReview records + mark is_analyzed
  8. Commit batch
  9. time.sleep(15) → next batch
"""
import time
from typing import List, Optional

from sqlalchemy import func, text

from src.config.settings import load_settings
from src.models.database import ProcessedReview, RawReview
from src.processing.hallucination_guard import validate_evidence_quote
# from src.processing.llm_client import (
#     LLMClient,
#     LLMClientError,
#     QuotaExhaustedError,
#     RateLimitError,
# )
from src.processing.prompt_templates import BATCH_SYSTEM_PROMPT, build_batch_prompt
from src.processing.response_parser import parse_batch_response
from src.utils.db import get_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ─── Gemini 2.5 Flash Pricing (USD per 1M tokens) ──────────
PRICING = {
    "input_per_1m": 0.15,    # $0.15 / 1M input tokens
    "output_per_1m": 0.60,   # $0.60 / 1M output tokens
}


class ProcessingStats:
    """Track processing statistics."""

    def __init__(self):
        self.total_processed = 0
        self.parse_success = 0
        self.parse_failure = 0
        self.hallucination_pass = 0
        self.hallucination_fail = 0
        self.sarcasm_corrected = 0
        self.api_calls = 0
        self.errors = 0
        self.fused = False          # True if circuit breaker tripped
        self.fuse_reason = ""
        self.consecutive_429s = 0   # Counter for circuit breaker

    def summary(self) -> str:
        total = self.parse_success + self.parse_failure
        parse_rate = (
            f"{self.parse_success / total * 100:.1f}%"
            if total > 0
            else "N/A"
        )
        hall_total = self.hallucination_pass + self.hallucination_fail
        hall_rate = (
            f"{self.hallucination_pass / hall_total * 100:.1f}%"
            if hall_total > 0
            else "N/A"
        )
        return (
            f"Processed: {self.total_processed} | "
            f"API Calls: {self.api_calls} | "
            f"Parse OK: {self.parse_success} ({parse_rate}) | "
            f"Guard Pass: {self.hallucination_pass} ({hall_rate}) | "
            f"Sarcasm: {self.sarcasm_corrected} | "
            f"Errors: {self.errors}"
        )


# ─── Circuit Breaker Config ──────────────────────────────
CONSEC_429_FUSE_LIMIT = 3
POST_CALL_DELAY_SECONDS = 15


class CognitiveProcessor:
    """
    Orchestrates LLM analysis in free-tier-friendly batch mode
    with quota circuit breaker.
    """

    def __init__(self):
        self._settings = load_settings()
        self._batch_size = self._settings.llm.batch_size
        # self._llm_client = LLMClient()

    def run(
        self,
        limit: Optional[int] = None,
        app_filter: Optional[str] = None,
    ) -> ProcessingStats:
        """
        Process all unanalyzed reviews in batch mode.

        Circuit breaker: stops after 3 consecutive 429s or QuotaExhaustedError.
        Always commits successfully processed data before stopping.
        """
        stats = ProcessingStats()

        with get_session() as session:
            # Count total unprocessed
            query = session.query(RawReview).filter(
                RawReview.is_analyzed == False  # noqa: E712
            )
            if app_filter:
                query = query.filter(RawReview.app_name == app_filter)

            total_unprocessed = query.count()
            if limit:
                total_unprocessed = min(total_unprocessed, limit)

            logger.info(
                f"🧠 Starting batch processing: {total_unprocessed} reviews "
                f"(batch_size={self._batch_size}, delay={POST_CALL_DELAY_SECONDS}s, "
                f"fuse_limit={CONSECUTIVE_429_FUSE_LIMIT})"
            )

            processed_count = 0
            batch_num = 0

            while True:
                # ── Circuit breaker check ──
                if stats.fused:
                    logger.warning(
                        f"🔌 CIRCUIT BREAKER TRIPPED: {stats.fuse_reason}"
                    )
                    break

                # Check limit
                remaining = (
                    (limit - processed_count) if limit else self._batch_size
                )
                if limit and remaining <= 0:
                    break

                batch_limit = min(self._batch_size, remaining)

                # Fetch batch
                batch_query = session.query(RawReview).filter(
                    RawReview.is_analyzed == False  # noqa: E712
                )
                if app_filter:
                    batch_query = batch_query.filter(
                        RawReview.app_name == app_filter
                    )
                batch: List[RawReview] = batch_query.limit(batch_limit).all()

                if not batch:
                    break

                batch_num += 1
                logger.info(
                    f"📦 Batch {batch_num}: {len(batch)} reviews "
                    f"({processed_count}/{total_unprocessed})"
                )

                # Process entire batch in ONE API call
                try:
                    self._process_batch(session, batch, stats)
                    # Reset 429 counter on success
                    stats.consecutive_429s = 0

                except QuotaExhaustedError as e:
                    # ── FUSE: daily quota gone ──
                    logger.error(f"🚨 QUOTA EXHAUSTED: {e}")
                    stats.fused = True
                    stats.fuse_reason = f"Daily quota exhausted: {e}"
                    # Mark batch as analyzed to prevent re-processing
                    for review in batch:
                        review.is_analyzed = True
                        stats.errors += 1

                except (RateLimitError, LLMClientError) as e:
                    stats.consecutive_429s += 1
                    logger.warning(
                        f"⚠️ 429 #{stats.consecutive_429s}/{CONSECUTIVE_429_FUSE_LIMIT}: {e}"
                    )

                    if stats.consecutive_429s >= CONSECUTIVE_429_FUSE_LIMIT:
                        stats.fused = True
                        stats.fuse_reason = (
                            f"{CONSECUTIVE_429_FUSE_LIMIT} consecutive 429s "
                            f"— likely quota exhausted"
                        )
                    else:
                        # Mark batch to skip, continue trying
                        for review in batch:
                            review.is_analyzed = True
                            stats.errors += 1

                except Exception as e:
                    logger.error(f"Batch {batch_num} unexpected error: {e}")
                    for review in batch:
                        review.is_analyzed = True
                        stats.errors += 1

                processed_count += len(batch)
                stats.total_processed = processed_count

                # Batch commit — ensures NO data loss before fuse
                session.commit()
                logger.info(
                    f"✅ Batch {batch_num} committed. "
                    f"Progress: {processed_count}/{total_unprocessed}. "
                    f"{stats.summary()}"
                )

                # ⏱ Speed bump (skip if fused — we're stopping)
                if not stats.fused and processed_count < total_unprocessed:
                    logger.info(
                        f"⏳ Sleeping {POST_CALL_DELAY_SECONDS}s..."
                    )
                    time.sleep(POST_CALL_DELAY_SECONDS)

        # ── Final log ──
        status_emoji = "🔌 FUSED" if stats.fused else "🏁 COMPLETE"
        logger.info(f"{status_emoji} — {stats.summary()}")
        return stats

    def _process_batch(
        self,
        session,
        batch: List[RawReview],
        stats: ProcessingStats,
    ) -> None:
        """Process a batch of reviews via a single LLM API call."""
        # 1. Build batch prompt
        user_prompt = build_batch_prompt(batch)

        # 2. Call LLM (single API call for entire batch)
        raw_response = self._llm_client.analyze(
            BATCH_SYSTEM_PROMPT, user_prompt
        )
        stats.api_calls += 1

        # 3. Parse batch response → Dict[index, Schema]
        parsed_results = parse_batch_response(
            raw_response, expected_count=len(batch)
        )

        # 4. Process each result
        for i, review in enumerate(batch):
            parsed = parsed_results.get(i)

            if parsed is None:
                stats.parse_failure += 1
                processed = ProcessedReview(
                    raw_id=review.review_id,
                    hallucination_check_passed=False,
                    llm_model_version=self._llm_client.model_version,
                )
                session.add(processed)
                review.is_analyzed = True
                continue

            stats.parse_success += 1

            # 5. Hallucination guard
            validation = validate_evidence_quote(
                raw_content=review.content,
                evidence_quote=parsed.evidence_quote,
                strict_mode=True,
            )

            if validation.is_valid:
                stats.hallucination_pass += 1
            else:
                stats.hallucination_fail += 1
                logger.debug(
                    f"Hallucination: review {review.review_id}: "
                    f"{validation.failure_reason}"
                )

            # 6. Sarcasm correction
            sentiment = parsed.sentiment_score
            if validation.is_valid and parsed.is_sarcasm and sentiment > 0:
                sentiment = -abs(sentiment)
                stats.sarcasm_corrected += 1

            # 7. Build ProcessedReview
            if validation.is_valid:
                processed = ProcessedReview(
                    raw_id=review.review_id,
                    primary_category=parsed.primary_category,
                    user_persona=parsed.user_persona,
                    impact_severity=parsed.impact_severity,
                    is_sarcasm=parsed.is_sarcasm,
                    evidence_quote=parsed.evidence_quote,
                    sentiment_score=sentiment,
                    root_cause_tag=parsed.root_cause_tag,
                    hallucination_check_passed=True,
                    llm_model_version=self._llm_client.model_version,
                )
            else:
                processed = ProcessedReview(
                    raw_id=review.review_id,
                    hallucination_check_passed=False,
                    llm_model_version=self._llm_client.model_version,
                )

            session.add(processed)
            review.is_analyzed = True


def generate_interim_report() -> str:
    """
    Generate a formatted interim report with progress, insights, and cost forecast.

    Called after the processor finishes (either naturally or via fuse).
    """
    lines = []
    lines.append("\n" + "=" * 65)
    lines.append("📊 INTERIM REPORT — SolarWatch Cognitive Pipeline")
    lines.append("=" * 65)

    with get_session() as session:
        # ── Progress ──
        total = session.query(func.count(RawReview.review_id)).scalar()
        processed = session.query(func.count(RawReview.review_id)).filter(
            RawReview.is_analyzed == True  # noqa: E712
        ).scalar()
        remaining = total - processed

        # Count valid processed reviews (with category)
        valid_processed = session.execute(text(
            "SELECT COUNT(*) FROM processed_reviews WHERE hallucination_check_passed = 1"
        )).scalar()

        lines.append(f"\n📈 Progress:")
        lines.append(f"   Total in DB:         {total}")
        lines.append(f"   Processed (sent):    {processed}")
        lines.append(f"   Valid (parsed + OK):  {valid_processed}")
        lines.append(f"   Remaining:           {remaining}")

        pct = processed / total * 100 if total else 0
        lines.append(f"   Completion:          {pct:.1f}%")

        # ── Top Categories ──
        if valid_processed and valid_processed > 0:
            top_cats = session.execute(text("""
                SELECT primary_category, COUNT(*) as cnt
                FROM processed_reviews
                WHERE hallucination_check_passed = 1 AND primary_category IS NOT NULL
                GROUP BY primary_category
                ORDER BY cnt DESC
                LIMIT 5
            """)).fetchall()

            lines.append(f"\n🏷️  Category Distribution:")
            for cat, cnt in top_cats:
                bar = "█" * min(cnt, 30)
                lines.append(f"   {cat:20s}  {cnt:4d}  {bar}")

            # ── Top Root Causes ──
            top_roots = session.execute(text("""
                SELECT root_cause_tag, COUNT(*) as cnt
                FROM processed_reviews
                WHERE hallucination_check_passed = 1
                  AND root_cause_tag IS NOT NULL
                  AND root_cause_tag != 'N/A'
                  AND root_cause_tag != 'null'
                GROUP BY root_cause_tag
                ORDER BY cnt DESC
                LIMIT 3
            """)).fetchall()

            if top_roots:
                lines.append(f"\n🔥 Top 3 Root Causes:")
                for i, (root, cnt) in enumerate(top_roots, 1):
                    lines.append(f"   {i}. {root} ({cnt}x)")

            # ── Installer Spotlight ──
            installer = session.execute(text("""
                SELECT r.app_name, r.content, p.evidence_quote
                FROM processed_reviews p
                JOIN raw_reviews r ON p.raw_id = r.review_id
                WHERE p.user_persona = 'Installer'
                  AND p.hallucination_check_passed = 1
                LIMIT 1
            """)).fetchone()

            if installer:
                lines.append(f"\n👷 Installer Spotlight:")
                lines.append(f"   App: {installer[0]}")
                content_preview = installer[1][:120] + "..." if len(installer[1]) > 120 else installer[1]
                lines.append(f'   Text: "{content_preview}"')
                lines.append(f'   Quote: "{installer[2]}"')
            else:
                lines.append(f"\n👷 Installer: None detected yet")

        # ── Cost Forecast ──
        lines.append(f"\n💰 Cost Forecast (Gemini 2.5 Flash):")

        # Estimate tokens based on processed data
        # Average review ~80 tokens input, system prompt ~500 tokens, output ~100 tokens/review
        # Batch of 50: ~4500 input tokens + 5000 output tokens
        avg_input_per_review = 90    # review text + metadata
        system_prompt_tokens = 800   # one-time per batch
        avg_output_per_review = 120  # JSON output per review

        batch_size = 50
        batches_done = max(1, (processed + batch_size - 1) // batch_size) if processed else 0
        batches_remaining = (remaining + batch_size - 1) // batch_size if remaining else 0

        input_tokens_per_batch = system_prompt_tokens + (avg_input_per_review * batch_size)
        output_tokens_per_batch = avg_output_per_review * batch_size

        remaining_input_tokens = batches_remaining * input_tokens_per_batch
        remaining_output_tokens = batches_remaining * output_tokens_per_batch

        input_cost = remaining_input_tokens / 1_000_000 * PRICING["input_per_1m"]
        output_cost = remaining_output_tokens / 1_000_000 * PRICING["output_per_1m"]
        total_cost = input_cost + output_cost

        lines.append(f"   Remaining reviews:    {remaining}")
        lines.append(f"   Remaining batches:    {batches_remaining}")
        lines.append(f"   Est. input tokens:    {remaining_input_tokens:,}")
        lines.append(f"   Est. output tokens:   {remaining_output_tokens:,}")
        lines.append(f"   Input cost:           ${input_cost:.4f}")
        lines.append(f"   Output cost:          ${output_cost:.4f}")
        lines.append(f"   ─────────────────────────────")
        lines.append(f"   TOTAL ESTIMATED:      ${total_cost:.4f} USD")

        est_minutes = batches_remaining * POST_CALL_DELAY_SECONDS / 60
        lines.append(f"   Est. time remaining:  ~{est_minutes:.0f} minutes")

    lines.append("\n" + "=" * 65)
    return "\n".join(lines)
