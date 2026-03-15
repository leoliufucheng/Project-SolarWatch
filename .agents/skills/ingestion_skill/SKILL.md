---
name: SolarWatch Ingestion Skill
description: Guide for implementing incremental review scraping from Google Play and App Store with multi-region support
---

# SolarWatch Ingestion Skill

## Scope

This skill covers **Step 2 (Incremental Ingestion)** of the SolarWatch pipeline — scraping app reviews from Google Play and App Store, per-region, with incremental logic.

## Architecture

```
src/ingestion/
├── base_scraper.py          # ABC (already implemented in Sprint 1)
├── google_play_scraper.py   # Google Play implementation
├── app_store_scraper.py     # App Store implementation (iTunes RSS API)
└── ingestion_manager.py     # Orchestrator: coordinates multi-app × multi-region scraping
```

## Core Interface

All scrapers inherit from `BaseScraper` and implement:

```python
def fetch_reviews(
    self,
    app_id: str,
    region_iso: str,        # CRITICAL: multi-region scraping, never default to one country
    since_date: datetime,
) -> List[RawReview]:
```

## Implementation Rules

### Google Play Scraper
- Library: `google-play-scraper` (`google_play_scraper.reviews`)
- Pass `country=region_iso.lower()` and `lang` from `REGION_LANG_MAP` (AT→de, CH→de)
- Sort by `Sort.NEWEST` for incremental efficiency
- Pagination: use `continuation_token` to fetch all pages
- Map fields: `reviewId` → `review_id`, `content` → `content`, `score` → `rating`, `appVersion` → `version`, `at` → `review_date`

### App Store Scraper — iTunes RSS API (纯 requests 实现)

> **⚠️ 绝对禁止使用任何第三方 App Store 爬虫库（如 `app-store-scraper`）。**
> 必须使用纯 `requests` 直接调用 Apple iTunes RSS JSON API。

**API 端点:**
```
https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json
```

**关键规则:**
- `country` = `region_iso.lower()` (e.g., `de`, `at`, `it`)
- 遍历 `page=1` 到 `page=10` (Apple RSS 最多支持 10 页 × 50 条 = 500 条)
- 解析路径: `response.json()['feed']['entry']` — 注意第一条是 App 元数据，需跳过
- 字段映射: `entry['id']['label']` → `review_id`, `entry['content']['label']` → `content`, `entry['im:rating']['label']` → `rating`, `entry['im:version']['label']` → `version`, `entry['updated']['label']` → `review_date`
- 当某页返回无 `entry` 或不足 50 条时，停止分页
- `review_language` 必须通过 `REGION_LANG_MAP` 从 `region_iso` 推断
- 必须包含 `User-Agent` 伪装和请求重试机制

### Ingestion Manager
- For each target in `settings.yaml`, iterate `app × region × platform` combinations
- **Incremental logic:** Query `SELECT MAX(review_date) FROM raw_reviews WHERE app_name=? AND region_iso=? AND source_platform=?` as `last_fetched_date`
- **Cold start:** If no prior data exists, use `settings.scraping.initial_lookback_days` (default 180 days) to compute `since_date`
- **Deduplication:** `INSERT OR IGNORE` based on `review_id` primary key
- Rate limiting: sleep `rate_limit_google` / `rate_limit_appstore` seconds between requests
- Retry: exponential backoff, up to `max_retries` attempts

### Text Cleaning
- Apply `clean_review_text()` from `src/utils/text_utils.py` to all `content` before storage
- Preserve original language — do NOT translate

## Constraints

- **Rate Limits:** Google Play = 1 req/s, App Store = 0.5s between requests
- **Retry:** 3 attempts, exponential backoff (1s, 2s, 4s)
- **Logging:** Use `src/utils/logger.py` for all operations
- **Error Isolation:** One failed `(app, region)` pair must NOT block other pairs
- **Platform Field:** Set `source_platform` to `SourcePlatform.GOOGLE_PLAY` or `SourcePlatform.APP_STORE`
- **is_analyzed:** Always set to `False` on insert

## Acceptance Criteria

1. `python scripts/run_ingestion.py` completes without errors
2. `raw_reviews` table contains data for all 6 apps × 7 regions (42 combinations per platform)
3. Second run only fetches reviews newer than the last run (incremental)
4. Integration tests pass with mocked API responses

## 💻 Code Examples & Anti-Patterns (CRITICAL FOR AI)

### 🚫 Anti-Patterns
- **NO:** 绝对不要使用 `app-store-scraper` 第三方库。该库已弃用，解析失败率极高。
- **NO:** 绝对不要一次性抓取所有历史数据，必须结合 `since_date` 尽早 `break` 循环。
- **NO:** 不要在 Scraper 类中实例化 DB Session。Scraper 只负责 `return` RawReview 对象，DB 写入由 `ingestion_manager.py` 负责。
- **NO:** 不要忘记传 `country` 参数。如果不传，Google Play 默认返回美国数据。
- **NO:** 不要把 `lang` 和 `country` 搞混。`country` 控制商店区域，`lang` 控制评论语言。
- **NO:** 不要用 `region_iso.lower()` 作为 `lang`。必须查 `REGION_LANG_MAP`：AT→de, CH→de。

### ✅ Google Play API Standard

```python
from google_play_scraper import reviews, Sort
from src.config.constants import REGION_LANG_MAP

# 必须使用 REGION_LANG_MAP 映射语言
lang = REGION_LANG_MAP.get(region_iso, region_iso.lower())
result, continuation_token = reviews(
    app_id,
    lang=lang,                       # 从 REGION_LANG_MAP 查询
    country=region_iso.lower(),      # 直接小写
    sort=Sort.NEWEST,                # 必须是最新的，用于增量判定
    count=100                        # 每页数量
)

# 增量分页循环 — 遇到旧数据立即停止
for review in result:
    if review['at'] <= since_date:
        break  # ← 关键：不要继续抓旧数据
    # ... 构造 RawReview 对象
```

### ✅ App Store iTunes RSS API Standard

```python
import requests
from datetime import datetime
from src.config.constants import REGION_LANG_MAP

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_itunes_reviews(app_id: str, region_iso: str, since_date: datetime):
    country = region_iso.lower()
    collected = []

    for page in range(1, 11):  # Apple RSS 最多 10 页
        url = (
            f"https://itunes.apple.com/{country}/rss/customerreviews"
            f"/page={page}/id={app_id}/sortBy=mostRecent/json"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            break

        for entry in entries:
            # 跳过 App 元数据条目（没有 im:rating 字段）
            if "im:rating" not in entry:
                continue

            review_date = datetime.fromisoformat(
                entry["updated"]["label"].replace("T", " ").split("+")[0]
            )
            if review_date <= since_date:
                continue  # 跳过旧评论

            review = RawReview(
                review_id=entry["id"]["label"],
                source_platform=SourcePlatform.APP_STORE,
                region_iso=region_iso,
                content=clean_review_text(entry["content"]["label"]),
                rating=int(entry["im:rating"]["label"]),
                review_language=REGION_LANG_MAP.get(region_iso, country),  # 从区域推断
                version=entry.get("im:version", {}).get("label"),
                review_date=review_date,
                is_analyzed=False,
            )
            collected.append(review)

        if len(entries) < 50:
            break  # 不足一整页，说明已到末尾

    return collected
```

### ✅ RawReview 构造标准

```python
from src.models.database import RawReview
from src.config.constants import SourcePlatform
from src.utils.text_utils import clean_review_text

review = RawReview(
    review_id=str(raw["reviewId"]),          # 必须转字符串
    source_platform=SourcePlatform.GOOGLE_PLAY,
    region_iso=region_iso,                    # 原始大写: "DE"
    app_name=app_name,                        # 与 settings.yaml 一致
    content=clean_review_text(raw["content"]),# 必须清洗
    rating=raw["score"],
    review_language=REGION_LANG_MAP.get(region_iso, region_iso.lower()),
    version=raw.get("appVersion"),            # 可能为 None
    review_date=raw["at"],
    is_analyzed=False,                        # 永远初始为 False
)
```
