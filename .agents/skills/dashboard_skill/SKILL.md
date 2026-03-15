---
name: SolarWatch Dashboard Skill
description: Guide for building the Streamlit reporting dashboard with competitive benchmarking visualizations
---

# SolarWatch Dashboard Skill

## Scope

This skill covers **Step 5 (Reporting)** — building a Streamlit dashboard and PDF export for the final competitive analysis report.

## Architecture

```
src/reporting/
├── dashboard.py             # Streamlit app main entry point
├── charts.py                # Plotly/Altair chart components
└── pdf_export.py            # PDF report generation
```

## Dashboard Pages (5 Views)

### Page 1: Overview — Red vs Blue Radar
- **Chart:** Radar/Spider chart comparing Red Team vs Blue Team
- **Axes:** 5 dimensions from 4+1 framework (Commissioning, O&M, Localization, DevOps, Ecosystem)
- **Values:** Severity-Adjusted Score per category (inverted — lower is better)
- **Filters:** Region group selector, time range slider

### Page 2: Version Timeline
- **Chart:** Line chart with dual y-axis
- **Primary axis:** Average rating per app version (over time)
- **Secondary axis:** Review volume (bar overlay)
- **Highlight:** Version regression points (VRR < 0) marked in red
- **Filters:** App selector, region group

### Page 3: Category Deep-Dive
- **Chart:** Stacked bar chart per app showing category distribution
- **Table:** Top issues per category with evidence_quote excerpts
- **Filters:** Category selector, severity filter, persona filter (Installer/Homeowner)

### Page 4: Regional Heatmap
- **Chart:** Choropleth map of Europe colored by sentiment score or SAS
- **Granularity:** Country-level (7 countries)
- **Comparison:** Toggle between Red and Blue team
- **Table:** Regional metrics summary (DACH / South / Emerging)

### Page 5: Evidence Browser
- **Component:** Searchable, sortable data table
- **Columns:** App, Region, Rating, Category, Severity, Persona, Sentiment, evidence_quote
- **Filters:** Full-text search, category, severity, persona, sarcasm flag
- **Purpose:** Allow manual review of LLM analysis quality

## Implementation Rules

### Dashboard (`dashboard.py`)
- Use `st.set_page_config(layout="wide")` for full-width layout
- Implement sidebar navigation with `st.sidebar.radio` for page switching
- Load data once per session using `@st.cache_data`
- Connect to DB via `src/utils/db.py → get_session()`

### Charts (`charts.py`)
- Use **Plotly** for interactive charts (radar, line, bar, choropleth)
- Use **Altair** for small multiples if needed
- Color scheme: Red team = `#E74C3C` / Blue team = `#3498DB`
- All charts must have clear titles, axis labels, and legends
- Responsive design — charts should scale with container width

### PDF Export (`pdf_export.py`)
- Generate a static report with key findings
- Include: Executive summary, radar chart, top 5 issues per app, regional comparison
- Use a Python PDF library (e.g., `reportlab` or `fpdf2`)
- Export via a Streamlit download button

## Design Guidelines

- **Color Palette:**
  - Red Team: `#E74C3C` (primary), `#C0392B` (dark)
  - Blue Team: `#3498DB` (primary), `#2980B9` (dark)
  - Neutral: `#2C3E50` (dark), `#ECF0F1` (light)
  - Severity: Critical=`#E74C3C`, Major=`#F39C12`, Minor=`#27AE60`
- **Typography:** Clean sans-serif (Streamlit default is fine)
- **Layout:** Cards/containers for metric KPIs at the top of each page

## Constraints

- **Data integrity:** Only display records where `hallucination_check_passed = TRUE`
- **Performance:** Cache DB queries; dashboard should load < 3 seconds
- **Accessibility:** All charts must have text alternatives in tables
- **No hardcoded app names:** Read from `settings.yaml → targets` for dynamic rendering

## Acceptance Criteria

1. All 5 pages render without errors
2. Radar chart correctly shows Red vs Blue comparison on 5 axes
3. Version timeline highlights regression points
4. Evidence browser supports full-text search
5. PDF export generates a downloadable report
6. `streamlit run src/reporting/dashboard.py` launches successfully

## 💻 Code Examples & Anti-Patterns (CRITICAL FOR AI)

### 🚫 Anti-Patterns
- **NO:** 绝对不要在绘图函数 (`charts.py`) 里面写 SQL 查询。数据加载必须与 UI 渲染完全解耦。
- **NO:** **严禁展示 `hallucination_check_passed=False` 的数据！** 任何 SQL 查询必须带 `WHERE pr.hallucination_check_passed = TRUE`。
- **NO:** 不要在每个 Streamlit 回调中重新创建 DB Engine，使用 `get_engine()` 单例。
- **NO:** 不要硬编码 App 名称列表，必须从 `settings.yaml → targets` 动态读取。

### ✅ Caching & Query Standard

在 `dashboard.py` 中，必须使用 `@st.cache_data` 配合 SQLAlchemy：

```python
import pandas as pd
import streamlit as st
from sqlalchemy import text
from src.utils.db import get_engine

@st.cache_data(ttl=3600)  # 缓存 1 小时
def load_version_regression_data(app_name: str) -> pd.DataFrame:
    engine = get_engine()
    query = text("""
        SELECT pr.sentiment_score, pr.primary_category, pr.impact_severity,
               rr.version, rr.review_date, rr.rating, rr.region_iso
        FROM processed_reviews pr
        JOIN raw_reviews rr ON pr.raw_id = rr.review_id
        WHERE pr.hallucination_check_passed = TRUE
          AND rr.app_name = :app_name
    """)
    return pd.read_sql(query, engine, params={"app_name": app_name})
```

### ✅ Charts 与数据分离

```python
# charts.py — 只接收 DataFrame，不做任何 DB 操作
import plotly.graph_objects as go

def create_radar_chart(df_red: pd.DataFrame, df_blue: pd.DataFrame) -> go.Figure:
    # ... 纯绘图逻辑
    pass

# dashboard.py — 负责数据加载 + 调用 charts
df = load_version_regression_data("Huawei FusionSolar")
fig = create_radar_chart(df_red, df_blue)
st.plotly_chart(fig, use_container_width=True)
```

### ✅ 页面导航标准

```python
st.set_page_config(page_title="SolarWatch", layout="wide")
page = st.sidebar.radio("Navigation", [
    "Overview", "Version Timeline", "Category Deep-Dive",
    "Regional Heatmap", "Evidence Browser"
])
if page == "Overview":
    render_overview()
# ...
```
