#!/usr/bin/env python3
"""
SolarWatch Cognitive Processing CLI
======================================
Command-line interface for running LLM-based review analysis.

Features:
  - Batch mode: 50 reviews per API call
  - Circuit breaker: auto-stops on quota exhaustion
  - Interim report: auto-generated on completion or fuse

Usage:
    python scripts/run_processing.py                     # Process all
    python scripts/run_processing.py --limit 50          # Process 50
    python scripts/run_processing.py --app "Huawei FusionSolar"

Background execution:
    nohup python3 scripts/run_processing.py > processing.log 2>&1 &
"""
import argparse
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.processor import CognitiveProcessor, generate_interim_report
from src.utils.db import init_database
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="SolarWatch Cognitive Processing — LLM Batch Pipeline"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max number of reviews to process (default: all)",
    )
    parser.add_argument(
        "--app", type=str, default=None,
        help='Filter by app name (e.g., "Huawei FusionSolar")',
    )

    args = parser.parse_args()

    # Ensure DB is initialized
    init_database()

    print("\n🧠 SolarWatch Cognitive Processing Pipeline")
    print("   Mode: Batch (50 reviews/request, 15s delay)")
    print(f"   Limit:  {args.limit or 'All unprocessed'}")
    print(f"   App:    {args.app or 'All'}")
    print(f"   Fuse:   3 consecutive 429s → auto-stop")
    print()

    # Run synchronous processor
    processor = CognitiveProcessor()
    stats = processor.run(limit=args.limit, app_filter=args.app)

    # Print processing summary
    print("\n" + "=" * 60)
    if stats.fused:
        print("🔌 CIRCUIT BREAKER TRIPPED")
        print(f"   Reason: {stats.fuse_reason}")
    else:
        print("🏁 PROCESSING COMPLETE")
    print("=" * 60)
    print(f"  Total Sent to LLM:    {stats.total_processed}")
    print(f"  API Calls Made:       {stats.api_calls}")
    print(f"  Parse Success:        {stats.parse_success}")
    print(f"  Parse Failure:        {stats.parse_failure}")
    print(f"  Hallucination Pass:   {stats.hallucination_pass}")
    print(f"  Hallucination Fail:   {stats.hallucination_fail}")
    print(f"  Sarcasm Corrected:    {stats.sarcasm_corrected}")
    print(f"  Errors:               {stats.errors}")

    total_attempted = stats.parse_success + stats.parse_failure
    if total_attempted > 0:
        parse_rate = stats.parse_success / total_attempted * 100
        print(f"\n  Parse Success Rate:       {parse_rate:.1f}%")

    if stats.parse_success > 0:
        hall_total = stats.hallucination_pass + stats.hallucination_fail
        hall_rate = stats.hallucination_pass / hall_total * 100 if hall_total else 0
        print(f"  Hallucination Pass Rate:  {hall_rate:.1f}%")

    # ── Always print interim report ──
    report = generate_interim_report()
    print(report)


if __name__ == "__main__":
    main()
