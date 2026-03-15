---
name: SolarWatch Analytics Skill
description: Guide for implementing aggregation metrics, version regression analysis, and competitive benchmarking
---

# SolarWatch Analytics Skill

## Scope

This skill covers **Step 4 (Aggregation Engine)** — computing strategic metrics from processed reviews for the Red vs Blue competitive analysis.

## Architecture

```
src/analytics/
├── aggregator.py            # SQL-based aggregation queries
├── version_regression.py    # Dynamic Version Regression analysis
└── metrics.py               # Metric calculation formulas
```

## Core Metrics (5 Key Indicators)

### 1. Severity-Adjusted Score (SAS)
```
SAS = (count_critical × 3 + count_major × 2 + count_minor × 1) / total_count
```
- Use weights from `src/config/constants.py → SEVERITY_WEIGHTS`
- **Filter:** `WHERE hallucination_check_passed = TRUE`
- Higher SAS = more severe issues = worse digital experience

### 2. Version Regression Rate (VRR)
```
VRR = (avg_rating_new_version - avg_rating_old_version) / avg_rating_old_version
```
- Computed in `version_regression.py`
- Groups reviews by `app_name + version`, orders by version release date
- Negative VRR = rating dropped after update = regression detected
- Must have ≥ 10 reviews per version to be statistically significant

### 3. B2B Pain Index
```
B2B_Pain = count(user_persona='Installer' AND impact_severity IN ('Critical','Major')) / count(user_persona='Installer')
```
- Isolates professional installer pain points from homeowner noise
- Higher index = more critical B2B issues

### 4. Sarcasm-Corrected Sentiment
```
Avg_Sentiment = AVG(sentiment_score) WHERE hallucination_check_passed = TRUE
```
- `sentiment_score` is already sarcasm-corrected in Step 3
- Range: [-1.0, 1.0] — compare across apps and regions

### 5. Category Distribution
```
For each category in (Commissioning, O&M, Localization, DevOps, Ecosystem):
    percentage = count(primary_category = category) / total_count
```
- Shows which problem areas dominate per app
- Used in radar chart visualization

## Regional Aggregation Rules

All metrics can be sliced by geo-region using `region_iso`:

| Region Group | Countries | SQL Filter |
|-------------|-----------|------------|
| DACH | Germany, Austria, Switzerland | `region_iso IN ('DE', 'AT', 'CH')` |
| South Europe | Italy, Spain | `region_iso IN ('IT', 'ES')` |
| Emerging | Poland, Romania | `region_iso IN ('PL', 'RO')` |

Use `src/config/constants.py → REGION_GROUPS` for these mappings.

## Implementation Rules

### Aggregator (`aggregator.py`)
- All queries MUST include `WHERE hallucination_check_passed = TRUE`
- Join `processed_reviews` with `raw_reviews` for access to `app_name`, `region_iso`, `version`, `rating`
- Support filtering by: app_name, team (red/blue), region group, time window
- Return results as pandas DataFrames for easy visualization

### Version Regression (`version_regression.py`)
- Parse version strings using semantic versioning where possible
- Handle non-standard version formats gracefully (log a warning, skip)
- Minimum sample size: 10 reviews per version
- Output: list of `(app_name, old_version, new_version, VRR, sample_size)` tuples

### Metrics (`metrics.py`)
- Provide high-level functions: `compute_sas()`, `compute_vrr()`, `compute_b2b_pain()`, etc.
- Each function accepts optional filters (app, region, time range)
- Cache results when appropriate (metrics don't change between pipeline runs)

## Constraints

- **Always filter** `hallucination_check_passed = TRUE` — hallucinated records must never participate in aggregation
- **Statistical significance:** Flag metrics computed from < 30 reviews as "low confidence"
- **Time window:** Default to `project.time_window_days` (180 days) unless overridden
- **Red vs Blue comparison:** Every metric must be computable per-team for competitive benchmarking

## Acceptance Criteria

1. All 5 core metrics compute correctly on test data
2. Version regression analysis identifies at least 1 regression case
3. Red vs Blue comparison data is complete for all apps
4. Regional aggregation works for all 3 geo-groups

## 💻 Code Examples & Anti-Patterns (CRITICAL FOR AI)

### 🚫 Anti-Patterns
- **NO:** 绝对不要直接查询 `processed_reviews` 单表。必须 JOIN `raw_reviews` 才能获取 `app_name`, `region_iso`, `version`, `rating`。
- **NO:** 不要忘记 `WHERE pr.hallucination_check_passed = TRUE`。**每一个聚合查询都必须有这个过滤条件。**
- **NO:** 不要直接用 `AVG(rr.rating)` 做版本回归，必须先按版本分组再计算差值。
- **NO:** 不要在 `metrics.py` 中直接实例化 DB Session，应该接收 DataFrame 作为输入。

### ✅ 标准 JOIN 查询模板

所有聚合查询必须遵循以下模式：

```python
from sqlalchemy import text
from src.utils.db import get_engine

def get_base_query(extra_where: str = "") -> str:
    """所有分析查询的基础模板"""
    return f"""
        SELECT pr.*, rr.app_name, rr.region_iso, rr.version,
               rr.rating, rr.review_date, rr.source_platform
        FROM processed_reviews pr
        JOIN raw_reviews rr ON pr.raw_id = rr.review_id
        WHERE pr.hallucination_check_passed = TRUE
        {extra_where}
    """
```

### ✅ Severity-Adjusted Score 计算

```python
from src.config.constants import SEVERITY_WEIGHTS, ImpactSeverity

def compute_sas(df: pd.DataFrame) -> float:
    """
    SAS = (Critical×3 + Major×2 + Minor×1) / total
    Higher = worse digital experience
    """
    total = len(df)
    if total == 0:
        return 0.0
    weighted = sum(
        SEVERITY_WEIGHTS[ImpactSeverity(row.impact_severity)]
        for _, row in df.iterrows()
        if row.impact_severity is not None
    )
    return weighted / total
```

### ✅ 区域聚合标准

```python
from src.config.constants import REGION_GROUPS

def aggregate_by_region(df: pd.DataFrame) -> dict:
    """按三大区域聚合指标"""
    results = {}
    for group_name, countries in REGION_GROUPS.items():
        region_df = df[df['region_iso'].isin(countries)]
        results[group_name] = {
            'count': len(region_df),
            'avg_sentiment': region_df['sentiment_score'].mean(),
            'sas': compute_sas(region_df),
        }
    return results
```

### ✅ 版本回归检测

```python
def detect_regressions(df: pd.DataFrame, min_sample: int = 10) -> list:
    """
    检测版本更新后评分下降的案例
    返回: [(app, old_ver, new_ver, VRR, sample_size), ...]
    """
    results = []
    for app in df['app_name'].unique():
        app_df = df[df['app_name'] == app].sort_values('review_date')
        versions = app_df.groupby('version').agg(
            avg_rating=('rating', 'mean'),
            count=('rating', 'count'),
            first_date=('review_date', 'min')
        ).reset_index()
        versions = versions[versions['count'] >= min_sample]
        versions = versions.sort_values('first_date')

        for i in range(1, len(versions)):
            old = versions.iloc[i-1]
            new = versions.iloc[i]
            if old['avg_rating'] > 0:
                vrr = (new['avg_rating'] - old['avg_rating']) / old['avg_rating']
                if vrr < -0.05:  # 5% 以上下降才算回归
                    results.append((app, old['version'], new['version'],
                                   round(vrr, 4), int(new['count'])))
    return results
```
