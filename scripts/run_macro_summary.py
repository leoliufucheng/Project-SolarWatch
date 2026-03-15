#!/usr/bin/env python3
"""
SolarWatch Macro Aggregation Summary
========================================
Outputs structured Markdown tables optimized for LLM comprehension.

Usage:
    python scripts/run_macro_summary.py
    python scripts/run_macro_summary.py > data/macro_summary.md
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
DB_PATH = Path(__file__).parent.parent / "data" / "solarwatch.db"


def get_conn():
    if not DB_PATH.exists():
        print(f"ERROR: Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


def meta_summary(conn):
    row = conn.execute("""
        SELECT 
            (SELECT COUNT(*) FROM raw_reviews) as total_raw,
            (SELECT COUNT(*) FROM raw_reviews WHERE is_analyzed = 1) as analyzed,
            (SELECT COUNT(*) FROM processed_reviews) as total_processed,
            (SELECT COUNT(*) FROM processed_reviews WHERE hallucination_check_passed = 1) as valid
    """).fetchone()
    total_raw, analyzed, total_processed, valid = row
    pct = f"{valid/total_processed*100:.1f}%" if total_processed else "N/A"

    print("# SolarWatch Cognitive Pipeline — Macro Aggregation Report\n")
    print("## Pipeline Overview\n")
    print(f"- **Raw Reviews**: {total_raw}")
    print(f"- **Sent to LLM**: {analyzed}")
    print(f"- **Processed Records**: {total_processed}")
    print(f"- **Valid (hallucination guard passed)**: {valid} ({pct})")
    print(f"- **Remaining**: {total_raw - analyzed}")
    print()


def table1_android_penalty(conn):
    rows = conn.execute("""
        SELECT 
            r.app_name,
            r.source_platform,
            COUNT(*) as review_count,
            ROUND(AVG(p.sentiment_score), 2) as avg_sentiment,
            ROUND(AVG(r.rating), 2) as avg_rating
        FROM processed_reviews p
        JOIN raw_reviews r ON p.raw_id = r.review_id
        WHERE p.hallucination_check_passed = 1
          AND p.sentiment_score IS NOT NULL
        GROUP BY r.app_name, r.source_platform
        ORDER BY r.app_name, r.source_platform
    """).fetchall()

    print("## Table 1: Android Penalty Effect (安卓惩罚效应验证)\n")
    print("**Purpose**: Verify hypothesis that Android reviews are more negative than iOS for the same brand.\n")
    print("| App | Platform | Count | Avg Sentiment | Avg Rating |")
    print("|-----|----------|------:|:-------------:|:----------:|")
    for app, platform, count, sentiment, rating in rows:
        sent_str = f"+{sentiment:.2f}" if sentiment >= 0 else f"{sentiment:.2f}"
        print(f"| {app} | {platform} | {count} | {sent_str} | {rating:.2f} |")

    # Delta analysis
    apps = {}
    for app, platform, count, sentiment, rating in rows:
        if app not in apps:
            apps[app] = {}
        apps[app][platform] = {"count": count, "sentiment": sentiment, "rating": rating}

    print("\n### Android vs iOS Sentiment Delta\n")
    print("| App | Δ Sentiment (Android − iOS) | Δ Rating | Verdict |")
    print("|-----|:---------------------------:|:--------:|---------|")
    for app in sorted(apps.keys()):
        platforms = apps[app]
        android = platforms.get("google_play")
        ios = platforms.get("app_store")
        if android and ios:
            ds = android["sentiment"] - ios["sentiment"]
            dr = android["rating"] - ios["rating"]
            verdict = "Android worse" if ds < -0.05 else ("Android better" if ds > 0.05 else "No significant difference")
            print(f"| {app} | {ds:+.2f} | {dr:+.2f} | {verdict} |")
        elif ios and not android:
            print(f"| {app} | N/A (iOS only, {ios['count']} reviews) | N/A | No Android data |")
        elif android and not ios:
            print(f"| {app} | N/A (Android only, {android['count']} reviews) | N/A | No iOS data |")
    print()


def table2_installer_density(conn):
    rows = conn.execute("""
        SELECT 
            r.app_name,
            COUNT(*) as total,
            SUM(CASE WHEN p.user_persona = 'Installer' THEN 1 ELSE 0 END) as installers,
            ROUND(
                100.0 * SUM(CASE WHEN p.user_persona = 'Installer' THEN 1 ELSE 0 END) / COUNT(*),
                1
            ) as installer_pct
        FROM processed_reviews p
        JOIN raw_reviews r ON p.raw_id = r.review_id
        WHERE p.hallucination_check_passed = 1
        GROUP BY r.app_name
        ORDER BY installer_pct DESC
    """).fetchall()

    total_all = sum(r[1] for r in rows)
    total_inst = sum(r[2] for r in rows)
    global_pct = total_inst / total_all * 100 if total_all else 0

    print("## Table 2: Installer Density (安装商浓度)\n")
    print(f"**Purpose**: Detect B2B installer personas hidden among B2C homeowner reviews.")
    print(f"**Global installer rate**: {total_inst}/{total_all} ({global_pct:.1f}%)\n")
    print("| App | Total Valid | Installers | Installer % |")
    print("|-----|:----------:|:----------:|:-----------:|")
    for app, total, inst, pct in rows:
        print(f"| {app} | {total} | {inst} | {pct}% |")
    print()


def table3_top10_root_causes(conn):
    rows = conn.execute("""
        SELECT 
            p.root_cause_tag,
            COUNT(*) as occurrences,
            ROUND(AVG(p.sentiment_score), 2) as avg_sentiment,
            GROUP_CONCAT(DISTINCT r.app_name) as affected_apps
        FROM processed_reviews p
        JOIN raw_reviews r ON p.raw_id = r.review_id
        WHERE p.hallucination_check_passed = 1
          AND p.root_cause_tag IS NOT NULL
          AND p.root_cause_tag != 'N/A'
          AND p.root_cause_tag != 'null'
          AND p.root_cause_tag NOT LIKE '%N/A%'
          AND p.impact_severity IN ('Major', 'Critical')
        GROUP BY p.root_cause_tag
        ORDER BY occurrences DESC
        LIMIT 10
    """).fetchall()

    print("## Table 3: Top 10 Critical Root Causes (全局致命痛点)\n")
    print("**Purpose**: Identify the most impactful system-level issues across the European PV app market.")
    print("**Filter**: Only Major or Critical severity.\n")
    print("| Rank | Root Cause | Occurrences | Avg Sentiment | Affected Apps |")
    print("|:----:|-----------|:-----------:|:-------------:|---------------|")
    for i, (tag, count, sentiment, apps) in enumerate(rows, 1):
        print(f"| {i} | {tag} | {count} | {sentiment:.2f} | {apps} |")
    print()


def table4_category_heatmap(conn):
    rows = conn.execute("""
        SELECT 
            p.primary_category,
            COUNT(*) as count,
            ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM processed_reviews 
                WHERE hallucination_check_passed = 1 
                AND primary_category IS NOT NULL), 1) as pct,
            ROUND(AVG(p.sentiment_score), 2) as avg_sentiment,
            SUM(CASE WHEN p.impact_severity = 'Critical' THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN p.impact_severity = 'Major' THEN 1 ELSE 0 END) as major,
            SUM(CASE WHEN p.impact_severity = 'Minor' THEN 1 ELSE 0 END) as minor
        FROM processed_reviews p
        WHERE p.hallucination_check_passed = 1
          AND p.primary_category IS NOT NULL
        GROUP BY p.primary_category
        ORDER BY count DESC
    """).fetchall()

    print("## Table 4: Category Heatmap (4+1 业务域火力分布)\n")
    print("**Purpose**: Distribution of review complaints across the 5 business domains.\n")
    print("| Category | Count | Share % | Avg Sentiment | Critical | Major | Minor |")
    print("|----------|------:|:-------:|:-------------:|:--------:|:-----:|:-----:|")
    for cat, count, pct, sentiment, crit, major, minor in rows:
        sent_str = f"+{sentiment:.2f}" if sentiment >= 0 else f"{sentiment:.2f}"
        print(f"| {cat} | {count} | {pct}% | {sent_str} | {crit} | {major} | {minor} |")
    print()


def main():
    conn = get_conn()
    meta_summary(conn)
    table1_android_penalty(conn)
    table2_installer_density(conn)
    table3_top10_root_causes(conn)
    table4_category_heatmap(conn)
    conn.close()


if __name__ == "__main__":
    main()
