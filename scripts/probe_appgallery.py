#!/usr/bin/env python3
"""
AppGallery Probe Script
=========================
Independent exploration script to determine the feasibility of scraping
Huawei AppGallery reviews.

Target: FusionSolar (AppGallery ID: C100863653)
URL:    https://appgallery.huawei.com/app/C100863653

Probe Strategy:
  1. Fetch the main app page HTML — check if reviews are embedded
  2. Look for XHR/JSON API endpoints in the page source
  3. Try known AppGallery API patterns (reverse-engineered from web)
  4. Test anti-bot protections (headers, cookies, JS requirements)

This script does NOT modify any project code or database.
"""
import json
import re
import sys
from datetime import datetime

import requests

APP_ID = "C100863653"  # FusionSolar
BASE_URL = "https://appgallery.huawei.com"
APP_PAGE_URL = f"{BASE_URL}/app/{APP_ID}"

# Realistic browser headers to avoid instant blocking
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}

JSON_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}


def probe_1_app_page():
    """Probe 1: Fetch the main app page and analyze its structure."""
    print("=" * 60)
    print("PROBE 1: Fetching App Page HTML")
    print("=" * 60)

    try:
        resp = requests.get(APP_PAGE_URL, headers=HEADERS, timeout=15)
        print(f"  Status:       {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
        print(f"  Body Length:  {len(resp.text)} chars")

        # Check for anti-bot signals
        if resp.status_code == 403:
            print("  ❌ BLOCKED: 403 Forbidden — strong anti-bot protection")
            return None
        if resp.status_code == 503:
            print("  ❌ BLOCKED: 503 — likely Cloudflare/WAF challenge")
            return None
        if "captcha" in resp.text.lower() or "challenge" in resp.text.lower():
            print("  ⚠️  Captcha/challenge detected in response body")

        # Check if it's a JS-rendered SPA
        if len(resp.text) < 5000 and "<noscript>" in resp.text:
            print("  ⚠️  Appears to be a JS SPA (minimal HTML, requires browser rendering)")
        elif "<div id=\"app\"" in resp.text or "window.__INITIAL_STATE__" in resp.text:
            print("  ⚠️  Vue/React SPA detected — reviews likely loaded via XHR")

        # Look for embedded review data
        if "review" in resp.text.lower() or "comment" in resp.text.lower():
            print("  ✅ Found 'review'/'comment' keywords in HTML")
        else:
            print("  ℹ️  No review/comment keywords found in static HTML")

        # Look for API endpoints in page source
        api_patterns = re.findall(r'https?://[^\s"\']+api[^\s"\']*', resp.text, re.IGNORECASE)
        if api_patterns:
            print(f"  ✅ Found {len(api_patterns)} potential API URLs:")
            for url in set(api_patterns[:10]):
                print(f"      → {url}")

        # Look for JSON data blobs
        json_blobs = re.findall(r'window\.__\w+__\s*=\s*({.+?});', resp.text, re.DOTALL)
        if json_blobs:
            print(f"  ✅ Found {len(json_blobs)} embedded JSON blobs (SSR data)")
            for i, blob in enumerate(json_blobs[:3]):
                print(f"      Blob {i+1}: {len(blob)} chars")

        # Save first 2000 chars for manual inspection
        print(f"\n  --- First 500 chars of HTML ---")
        print(f"  {resp.text[:500]}")
        print(f"  --- End ---")

        return resp.text

    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request failed: {e}")
        return None


def probe_2_known_api_patterns():
    """Probe 2: Try known AppGallery API patterns."""
    print("\n" + "=" * 60)
    print("PROBE 2: Testing Known API Patterns")
    print("=" * 60)

    # Known API endpoints (reverse-engineered from various sources)
    api_candidates = [
        # Pattern 1: Web API v2
        {
            "name": "Web API v2 — App Detail",
            "url": f"https://web-dre.hispace.dbankcloud.cn/uowap/index",
            "method": "POST",
            "payload": {
                "method": "internal.getTabDetail",
                "serviceType": 20,
                "reqPageNum": 1,
                "uri": f"app|{APP_ID}",
                "maxResults": 25,
                "zone": "",
                "locale": "de_DE",
            },
        },
        # Pattern 2: Comment API
        {
            "name": "Comment API — Reviews",
            "url": f"https://web-dre.hispace.dbankcloud.cn/uowap/index",
            "method": "POST",
            "payload": {
                "method": "internal.user.commen498",
                "serviceType": 20,
                "reqPageNum": 1,
                "maxResults": 10,
                "appid": APP_ID,
                "zone": "",
                "locale": "de_DE",
            },
        },
        # Pattern 3: Direct comment endpoint
        {
            "name": "Direct Comment Endpoint",
            "url": f"https://web-dre.hispace.dbankcloud.cn/uowap/index",
            "method": "POST",
            "payload": {
                "method": "internal.user.comment",
                "serviceType": 20,
                "reqPageNum": 1,
                "maxResults": 10,
                "appid": APP_ID,
                "zone": "",
                "locale": "de_DE",
            },
        },
        # Pattern 4: Alternative API host
        {
            "name": "Alt API — Comment List",
            "url": "https://store-dre.hispace.dbankcloud.com/hwmarket/api/comment/list",
            "method": "GET",
            "params": {"appId": APP_ID, "page": 1, "pageSize": 10},
        },
    ]

    for api in api_candidates:
        print(f"\n  Testing: {api['name']}")
        print(f"  URL:     {api['url']}")
        try:
            if api.get("method") == "POST":
                resp = requests.post(
                    api["url"],
                    json=api.get("payload"),
                    headers=JSON_HEADERS,
                    timeout=15,
                )
            else:
                resp = requests.get(
                    api["url"],
                    params=api.get("params"),
                    headers=JSON_HEADERS,
                    timeout=15,
                )

            print(f"  Status:  {resp.status_code}")
            print(f"  Type:    {resp.headers.get('Content-Type', 'N/A')}")

            if resp.status_code == 200:
                # Try to parse as JSON
                try:
                    data = resp.json()
                    print(f"  ✅ JSON Response! Keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")

                    # Pretty print first 500 chars
                    json_str = json.dumps(data, indent=2, ensure_ascii=False)
                    print(f"  Data preview ({len(json_str)} chars):")
                    print(f"  {json_str[:800]}")

                    # Check for review/comment data
                    json_lower = json_str.lower()
                    if any(k in json_lower for k in ["comment", "review", "rating", "score"]):
                        print(f"  🎯 FOUND REVIEW DATA!")
                except json.JSONDecodeError:
                    print(f"  ℹ️  Not JSON. Body preview: {resp.text[:200]}")
            else:
                print(f"  Body: {resp.text[:200]}")

        except requests.exceptions.RequestException as e:
            print(f"  ❌ Failed: {e}")


def probe_3_alternate_sources():
    """Probe 3: Check alternative review sources for FusionSolar."""
    print("\n" + "=" * 60)
    print("PROBE 3: Alternative Review Sources")
    print("=" * 60)

    # Check if Google Play page exists but just has no reviews API
    gp_url = "https://play.google.com/store/apps/details?id=com.huawei.smartpvms&gl=de&hl=de"
    print(f"\n  Checking Google Play web page...")
    try:
        resp = requests.get(gp_url, headers=HEADERS, timeout=15)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            print("  ✅ GP web page exists (app is listed, just API returns 0)")
        elif resp.status_code == 404:
            print("  ❌ GP page 404 — app truly delisted from Google Play")
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Failed: {e}")


def main():
    print("🔍 AppGallery Probe — FusionSolar (C100863653)")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print()

    # Run all probes
    html = probe_1_app_page()
    probe_2_known_api_patterns()
    probe_3_alternate_sources()

    # Summary
    print("\n" + "=" * 60)
    print("PROBE SUMMARY")
    print("=" * 60)
    print("Review the output above to determine:")
    print("  1. Is AppGallery web page accessible? (Probe 1)")
    print("  2. Are there usable JSON APIs? (Probe 2)")
    print("  3. Is the GP web page still live? (Probe 3)")
    print("  4. What anti-bot measures exist?")


if __name__ == "__main__":
    main()
