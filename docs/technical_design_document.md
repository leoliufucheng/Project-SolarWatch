# Project SolarWatch — 技术架构与实施白皮书

> **版本:** v1.0 | **日期:** 2026-03-09 | **作者:** Chief Architect & Senior Business Analyst

---

## 目录

1. [Executive Summary](#1-executive-summary)
2. [Project Structure](#2-project-structure)
3. [Database DDL — SQLAlchemy Models](#3-database-ddl)
4. [Core Logic: LLM Processing & Anti-Hallucination](#4-core-logic)
5. [System Prompt Template](#5-system-prompt-template)
6. [Skills Template Design](#6-skills-template-design)
7. [Development Roadmap (4 Sprints)](#7-development-roadmap)

---

## 1. Executive Summary

### 1.1 战略定位

Project SolarWatch 通过挖掘 Google Play / App Store 的公开评论数据，量化欧洲光伏厂商的**数字化体验隐性成本**。核心价值主张：

| 维度 | 传统方法 | SolarWatch 方法 |
|------|---------|----------------|
| 数据来源 | 问卷调研、NPS | 真实用户评论（180天滚动窗口） |
| 分析粒度 | 整体满意度 | 4+1 垂直分类 × 用户画像 × 版本回归 |
| 防偏差 | 无 | 防幻觉校验层 + 反讽检测 |

### 1.2 分析框架

- **Red Team (红方):** Huawei FusionSolar, Sungrow iSolarCloud
- **Blue Team (蓝方):** SMA Sunny Portal, Fronius Solar.web, SolarEdge, Enphase
- **Geo Regions:** DACH (DE/AT/CH), South Europe (IT/ES), Emerging (PL/RO)

### 1.3 核心数据流 — 五步生命周期

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐    ┌─────────────┐    ┌───────────┐
│ Step 1      │    │ Step 2       │    │ Step 3              │    │ Step 4      │    │ Step 5    │
│ Config &    │───▶│ Incremental  │───▶│ Cognitive Process   │───▶│ Aggregation │───▶│ Reporting │
│ Target Def  │    │ Ingestion    │    │ + Anti-Hallucination│    │ Engine      │    │ Dashboard │
└─────────────┘    └──────────────┘    └─────────────────────┘    └─────────────┘    └───────────┘
 settings.yaml      Scraper API         LLM API + Python          SQL Aggregate     Streamlit
                     → raw_reviews       Validation Layer          → metrics cache   → Charts/PDF
                                         → processed_reviews
```

**防幻觉校验位置:** Step 3 的 Python Validation 子步骤，介于 LLM 响应解析与 `processed_reviews` 写入之间。

---

## 2. Project Structure

```
Project-SolarWatch/
├── README.md
├── LICENSE
├── pyproject.toml                    # 项目依赖 & 元数据 (Poetry/PDM)
├── settings.yaml                     # 监测目标池配置 (Step 1)
│
├── src/
│   ├── __init__.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py               # settings.yaml 解析 & Pydantic 校验
│   │   └── constants.py              # 枚举/常量 (平台、区域、分类框架)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py               # SQLAlchemy ORM 模型 (raw_reviews + processed_reviews)
│   │
│   ├── ingestion/                    # Step 2: 增量抓取
│   │   ├── __init__.py
│   │   ├── base_scraper.py           # 抽象基类 BaseScraper
│   │   ├── google_play_scraper.py    # Google Play 实现
│   │   ├── app_store_scraper.py      # App Store 实现
│   │   └── ingestion_manager.py      # 增量协调器 (last_fetched_date 管理)
│   │
│   ├── processing/                   # Step 3: 认知处理 + 防幻觉
│   │   ├── __init__.py
│   │   ├── llm_client.py             # LLM API 封装 (Gemini/OpenAI)
│   │   ├── prompt_templates.py       # System Prompt & User Prompt 模板
│   │   ├── response_parser.py        # JSON 响应解析 & Pydantic 校验
│   │   ├── hallucination_guard.py    # 防幻觉校验层 (evidence_quote 比对)
│   │   └── processor.py              # 主处理编排器
│   │
│   ├── analytics/                    # Step 4: 聚合引擎
│   │   ├── __init__.py
│   │   ├── aggregator.py             # SQL 聚合查询 (版本回撤率、情感趋势等)
│   │   ├── version_regression.py     # 动态版本回归分析
│   │   └── metrics.py                # 指标计算 (CSAT, NPS proxy, Severity Distribution)
│   │
│   ├── reporting/                    # Step 5: 报告引擎
│   │   ├── __init__.py
│   │   ├── dashboard.py              # Streamlit Dashboard 主入口
│   │   ├── charts.py                 # Plotly/Altair 图表组件
│   │   └── pdf_export.py             # PDF 报告导出
│   │
│   └── utils/
│       ├── __init__.py
│       ├── db.py                     # DB 连接/Session 管理
│       ├── logger.py                 # 统一日志
│       └── text_utils.py             # 文本清洗/归一化工具
│
├── data/
│   └── solarwatch.db                 # SQLite 数据库文件
│
├── tests/
│   ├── __init__.py
│   ├── test_ingestion.py
│   ├── test_processing.py
│   ├── test_hallucination_guard.py   # 防幻觉校验专项测试
│   ├── test_aggregator.py
│   └── fixtures/                     # 测试固件 (mock reviews, LLM responses)
│       ├── sample_reviews.json
│       └── sample_llm_responses.json
│
├── scripts/
│   ├── init_db.py                    # 数据库初始化
│   ├── run_ingestion.py              # CLI: 执行抓取
│   ├── run_processing.py             # CLI: 执行 LLM 分析
│   └── run_full_pipeline.py          # CLI: 端到端执行
│
├── .agents/
│   └── workflows/
│       ├── run_pipeline.md           # 全流程执行 workflow
│       └── add_new_app.md            # 新增监测目标 workflow
│
└── docs/
    ├── technical_design_document.md  # 本文档
    └── analysis_report_template.md   # 报告输出模板
```

### 关键设计决策

| 决策 | 理由 |
|------|------|
| `src/` 扁平包结构 | 降低复杂度；团队规模小，无需微服务 |
| Scraper 抽象基类 | Google Play 与 App Store API 差异大，需独立实现 |
| `hallucination_guard.py` 独立模块 | 核心质控逻辑，需要独立测试和迭代 |
| `settings.yaml` 外置配置 | 新增 App 无需改代码，满足可扩展性 |
| SQLite 单文件 | 数据量 <100K 条，无并发写入压力 |
## 3. Database DDL — SQLAlchemy Models

> **文件路径:** `src/models/database.py`

```python
"""
Project SolarWatch — ORM Models
================================
两张核心表构成数据基座:
  - raw_reviews:   数据原貌层 (ETL 起点)
  - processed_reviews: 认知分析层 (核心资产)
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    Enum, ForeignKey, CheckConstraint, Index, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


# ─── 枚举定义 ─────────────────────────────────────────────

class SourcePlatform(enum.Enum):
    """数据来源平台"""
    GOOGLE_PLAY = "google_play"
    APP_STORE = "app_store"


class PrimaryCategory(enum.Enum):
    """
    4+1 分析框架
    - Commissioning: 调试安装流程 (配网、设备添加)
    - O_AND_M:       运维监控 (告警、远程诊断)
    - Localization:  本地化体验 (多语言、合规)
    - DevOps:        软件工程质量 (崩溃、卡顿、版本回退)
    - Ecosystem:     生态兼容性 (电池、充电桩、第三方)
    """
    COMMISSIONING = "Commissioning"
    O_AND_M = "O&M"
    LOCALIZATION = "Localization"
    DEVOPS = "DevOps"
    ECOSYSTEM = "Ecosystem"


class UserPersona(enum.Enum):
    """
    用户画像 — 区分 B2B vs B2C 反馈
    - Installer: 安装商/集成商 (高价值 B2B 反馈)
    - Homeowner: 业主/终端用户 (B2C 噪声较多)
    """
    INSTALLER = "Installer"
    HOMEOWNER = "Homeowner"


class ImpactSeverity(enum.Enum):
    """
    严重等级 — 区分问题权重
    - Critical: 系统瘫痪 (e.g., 逆变器离线, 数据丢失)
    - Major:    核心功能失效 (e.g., 无法添加设备, 监控异常)
    - Minor:    体验不佳 (e.g., UI 不美观, 加载慢)
    """
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"


# ─── Table A: raw_reviews (原始评论表) ────────────────────

class RawReview(Base):
    """
    原始评论表 — 完整保留数据原貌
    ================================
    设计原则: 只做清洗(去重/编码), 不做任何语义变换。
    作为 ETL 起点, 所有下游分析均从此表派生。
    """
    __tablename__ = "raw_reviews"

    # --- 主键 ---
    review_id = Column(String(255), primary_key=True, comment="平台原生唯一 ID")

    # --- 来源元数据 ---
    source_platform = Column(
        Enum(SourcePlatform), nullable=False,
        comment="数据来源: google_play | app_store"
    )
    region_iso = Column(
        String(5), nullable=False,
        comment="ISO 3166-1 alpha-2 国家码 (e.g., DE/AT/PL). 用于区域聚合"
    )
    app_name = Column(
        String(100), nullable=False,
        comment="标的 App 标准名称 (与 settings.yaml 一致)"
    )

    # --- 评论内容 ---
    content = Column(Text, nullable=False, comment="原始多语言评论文本")
    rating = Column(
        Integer, nullable=False,
        comment="用户评分 1-5 星"
    )
    version = Column(
        String(50), nullable=True,
        comment="App 版本号 (e.g., 5.3.21). 用于【动态版本回归分析】"
    )
    review_date = Column(
        DateTime, nullable=False,
        comment="评论发布时间 (UTC)"
    )

    # --- 处理状态 ---
    is_analyzed = Column(
        Boolean, default=False, nullable=False,
        comment="是否已通过 Step 3 认知处理"
    )
    fetched_at = Column(
        DateTime, default=datetime.utcnow, nullable=False,
        comment="数据抓取时间"
    )

    # --- 关联 ---
    processed_review = relationship(
        "ProcessedReview", back_populates="raw_review", uselist=False
    )

    # --- 约束 ---
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
        CheckConstraint("length(content) > 0", name="ck_content_not_empty"),
        Index("ix_raw_reviews_app_date", "app_name", "review_date"),
        Index("ix_raw_reviews_unanalyzed", "is_analyzed",
              sqlite_where=Column("is_analyzed") == False),
        Index("ix_raw_reviews_region", "region_iso"),
    )


# ─── Table B: processed_reviews (认知分析表) ─────────────

class ProcessedReview(Base):
    """
    认知分析表 — 核心数据资产
    ================================
    存储 LLM 深度分析结果。每个字段都有明确业务含义:
    - primary_category: 用于垂直领域切片分析
    - user_persona:     过滤 B2B 硬核反馈 vs B2C 噪声
    - impact_severity:  加权计算 Severity-Adjusted Score
    - is_sarcasm:       修正欧洲用户反讽导致的情感偏差
    - evidence_quote:   防幻觉校验锚点
    """
    __tablename__ = "processed_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_id = Column(
        String(255), ForeignKey("raw_reviews.review_id"),
        nullable=False, unique=True,
        comment="关联原始表 FK"
    )

    # --- LLM 分析结果 ---
    primary_category = Column(
        Enum(PrimaryCategory), nullable=False,
        comment="4+1 框架分类"
    )
    user_persona = Column(
        Enum(UserPersona), nullable=False,
        comment="用户画像: Installer(B2B) vs Homeowner(B2C)"
    )
    impact_severity = Column(
        Enum(ImpactSeverity), nullable=False,
        comment="严重等级: Critical > Major > Minor"
    )
    is_sarcasm = Column(
        Boolean, default=False, nullable=False,
        comment="反讽标记. True 时 sentiment 需修正为负面"
    )
    evidence_quote = Column(
        Text, nullable=False,
        comment="LLM 从原文逐字摘录的证据. 防幻觉校验锚点"
    )
    sentiment_score = Column(
        Float, nullable=False,
        comment="情感得分 [-1.0, 1.0]. 若 is_sarcasm=True 则为修正后值"
    )
    root_cause_tag = Column(
        Text, nullable=True,
        comment="根因标签 (e.g., WiFi Handshake Timeout, OTA Bricked)"
    )

    # --- 防幻觉校验元数据 ---
    hallucination_check_passed = Column(
        Boolean, nullable=False,
        comment="evidence_quote 字符串比对结果. False = 幻觉"
    )
    processed_at = Column(
        DateTime, default=datetime.utcnow, nullable=False,
        comment="分析完成时间"
    )
    llm_model_version = Column(
        String(50), nullable=True,
        comment="LLM 模型版本 (可复现性)"
    )

    # --- 关联 ---
    raw_review = relationship("RawReview", back_populates="processed_review")

    # --- 约束 ---
    __table_args__ = (
        CheckConstraint(
            "sentiment_score >= -1.0 AND sentiment_score <= 1.0",
            name="ck_sentiment_range"
        ),
        Index("ix_processed_app_category", "primary_category"),
        Index("ix_processed_severity", "impact_severity"),
        Index("ix_processed_persona", "user_persona"),
        Index("ix_processed_hallucination", "hallucination_check_passed"),
    )
```

```python
# ─── Table C: app_releases (官方发版记录表) ────────────────────
class AppRelease(Base):
    """
    提供“零时刻 ($T$)”用于精准的爆炸半径分析。
    解决因设备网络延迟或静默更新导致的“评论存在时间滞后偏差”。
    """
    __tablename__ = "app_releases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_name = Column(String(100), nullable=False, index=True)
    platform = Column(Enum(SourcePlatform), nullable=False)
    version = Column(String(50), nullable=False)
    
    release_date = Column(
        DateTime, nullable=False, index=True,
        comment="官方发版日 $T$"
    )
    changelog = Column(Text, nullable=True)
    is_major_update = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("uix_app_platform_version", "app_name", "platform", "version", unique=True),
    )
```

### DDL 设计要点

| 字段 | 业务价值 (Why) |
|------|--------------|
| `region_iso` | GROUP BY 区域 → DACH/South/Emerging 聚合，提高统计显著性 |
| `version` | 计算**更新回撤率** = `(v_new_avg_rating - v_old_avg_rating) / v_old` |
| `user_persona` | 过滤安装商视角 → 暴露 B2B 交付痛点（配网超时 vs "界面丑"） |
| `impact_severity` | 加权公式: `Critical×3 + Major×2 + Minor×1` → Severity-Adjusted Score |
| `is_sarcasm` | 德语区 "Wunderbar, funktioniert gar nicht" → 强制修正为负面 |
| `evidence_quote` | **防幻觉核心**: Python 端 `quote in content` 断言 |
| `hallucination_check_passed` | 标记幻觉记录，不参与聚合计算但保留用于审计 |

---

## 4. Core Logic: LLM Processing & Anti-Hallucination

### 4.1 处理流程全景图

```
                    Step 3 内部流程 (processor.py 编排)
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  raw_reviews ───▶ [Batch Loader] ───▶ [Prompt Builder]          │
│  (is_analyzed=    (50条/批)          (构造 System + User Prompt)  │
│   False)                                                         │
│                         │                                        │
│                         ▼                                        │
│                  [LLM API Call]                                   │
│                  (llm_client.py)                                  │
│                         │                                        │
│                         ▼                                        │
│                  [Response Parser]     ◀── Pydantic 强制校验      │
│                  (response_parser.py)      JSON Schema 合规性     │
│                         │                                        │
│                         ▼                                        │
│              ┌──────────────────────┐                             │
│              │ Hallucination Guard  │  ◀── 核心防幻觉层           │
│              │ (hallucination_      │                             │
│              │  guard.py)           │                             │
│              └──────┬───────────────┘                             │
│                     │                                            │
│            ┌────────┴────────┐                                   │
│            ▼                 ▼                                   │
│     [PASS: Write to    [FAIL: Mark as                            │
│      processed_reviews  Hallucination,                           │
│      + set is_analyzed  log & skip]                              │
│      = True]                                                     │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 hallucination_guard.py — 防幻觉校验层

```python
"""
防幻觉校验模块
===============
核心职责: 验证 LLM 输出的 evidence_quote 确实存在于原始 content 中。
设计原则: 宁可漏判, 不可误放 (高召回率容忍度, 零容忍假通过)。
"""
import re
from dataclasses import dataclass
from src.utils.text_utils import normalize_text


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    raw_content: str
    evidence_quote: str
    similarity_score: float       # 0.0 - 1.0
    failure_reason: str | None = None


def validate_evidence_quote(
    raw_content: str,
    evidence_quote: str,
    strict_mode: bool = True,
    similarity_threshold: float = 0.85
) -> ValidationResult:
    """
    三级校验策略:
      Level 1 — 精确子串匹配 (归一化后)
      Level 2 — 模糊匹配 (SequenceMatcher, threshold=0.85)
      Level 3 — Token 重叠率 (应对 LLM 轻微改写)

    Args:
        raw_content:         原始评论文本
        evidence_quote:      LLM 返回的证据引用
        strict_mode:         严格模式 (仅 Level 1 通过)
        similarity_threshold: Level 2/3 通过阈值
    """
    # --- 预处理 ---
    norm_content = normalize_text(raw_content)
    norm_quote = normalize_text(evidence_quote)

    # --- Level 1: 精确子串匹配 ---
    if norm_quote in norm_content:
        return ValidationResult(
            is_valid=True, raw_content=raw_content,
            evidence_quote=evidence_quote, similarity_score=1.0
        )

    if strict_mode:
        return ValidationResult(
            is_valid=False, raw_content=raw_content,
            evidence_quote=evidence_quote, similarity_score=0.0,
            failure_reason="STRICT: Exact substring match failed"
        )

    # --- Level 2: 模糊匹配 ---
    from difflib import SequenceMatcher
    # 滑动窗口: 在 content 中找最相似的片段
    quote_len = len(norm_quote)
    best_ratio = 0.0
    for i in range(len(norm_content) - quote_len + 1):
        window = norm_content[i:i + quote_len]
        ratio = SequenceMatcher(None, norm_quote, window).ratio()
        best_ratio = max(best_ratio, ratio)
        if best_ratio >= similarity_threshold:
            return ValidationResult(
                is_valid=True, raw_content=raw_content,
                evidence_quote=evidence_quote, similarity_score=best_ratio
            )

    # --- Level 3: Token 重叠率 ---
    quote_tokens = set(norm_quote.split())
    content_tokens = set(norm_content.split())
    if quote_tokens:
        overlap = len(quote_tokens & content_tokens) / len(quote_tokens)
        if overlap >= similarity_threshold:
            return ValidationResult(
                is_valid=True, raw_content=raw_content,
                evidence_quote=evidence_quote, similarity_score=overlap
            )

    return ValidationResult(
        is_valid=False, raw_content=raw_content,
        evidence_quote=evidence_quote, similarity_score=best_ratio,
        failure_reason=f"All levels failed. Best similarity: {best_ratio:.2f}"
    )
```

### 4.3 processor.py — 主编排器核心逻辑

```python
"""
认知处理编排器
==============
协调: 批量加载 → Prompt 构造 → LLM 调用 → 响应解析 → 防幻觉 → 持久化
"""

async def process_batch(session, batch_size: int = 50):
    """处理一批未分析的评论"""
    # 1. 加载未处理评论
    unprocessed = session.query(RawReview).filter(
        RawReview.is_analyzed == False
    ).limit(batch_size).all()

    for review in unprocessed:
        try:
            # 2. 构造 Prompt
            prompt = build_analysis_prompt(review.content, review.rating)

            # 3. 调用 LLM
            llm_response = await llm_client.analyze(prompt)

            # 4. 解析 & Pydantic 校验
            parsed = ResponseParser.parse(llm_response)

            # 5. 防幻觉校验 ← 关键步骤
            validation = validate_evidence_quote(
                raw_content=review.content,
                evidence_quote=parsed.evidence_quote,
                strict_mode=True
            )

            # 6. 反讽修正
            sentiment = parsed.sentiment_score
            if parsed.is_sarcasm and sentiment > 0:
                sentiment = -abs(sentiment)  # 强制修正为负面

            # 7. 持久化
            processed = ProcessedReview(
                raw_id=review.review_id,
                primary_category=parsed.primary_category,
                user_persona=parsed.user_persona,
                impact_severity=parsed.impact_severity,
                is_sarcasm=parsed.is_sarcasm,
                evidence_quote=parsed.evidence_quote,
                sentiment_score=sentiment,
                root_cause_tag=parsed.root_cause_tag,
                hallucination_check_passed=validation.is_valid,
            )
            session.add(processed)
            review.is_analyzed = True

        except Exception as e:
            logger.error(f"Failed to process {review.review_id}: {e}")
            continue

    session.commit()
```
## 5. System Prompt Template

> **文件路径:** `src/processing/prompt_templates.py`

### 5.1 System Prompt (角色定义 & 输出约束)

```python
SYSTEM_PROMPT = """
You are an expert analyst specializing in European photovoltaic (solar) industry software.
Your task is to analyze user reviews of solar monitoring/management apps and extract structured insights.

## Your Analysis Framework: "4+1" Categories

Classify each review into EXACTLY ONE primary category:
1. **Commissioning** - Installation, device pairing, WiFi/network setup, initial configuration
2. **O&M** (Operations & Maintenance) - Monitoring, alerts, remote diagnostics, data accuracy
3. **Localization** - Multi-language support, regional compliance, local grid codes
4. **DevOps** - App crashes, performance, update quality, version regressions, UI/UX bugs
5. **Ecosystem** - Battery integration, EV charger compatibility, third-party device support

## User Persona Classification

Determine who wrote the review:
- **Installer**: Professional solar installer/integrator. Clues: technical terminology,
  mentions of commissioning multiple systems, fleet management, professional workflows.
- **Homeowner**: End-user/residential customer. Clues: mentions "my house", "my panels",
  basic feature complaints, UI aesthetics.

## Impact Severity Assessment

Rate the severity of the issue described:
- **Critical**: System down, data loss, inverter offline, safety concerns
- **Major**: Core feature broken, cannot add device, monitoring inaccurate
- **Minor**: UI complaints, slow loading, cosmetic issues

## Sarcasm Detection (CRITICAL for European reviews)

European users, especially German-speaking, frequently use sarcasm/irony.
Examples: "Toll, nach dem Update geht gar nichts mehr" (Great, after the update nothing works)
If sarcasm is detected, set is_sarcasm=true and adjust sentiment to NEGATIVE.

## Evidence Quote Rule (MANDATORY)

You MUST extract a VERBATIM quote from the original review text as evidence.
- Copy the exact characters from the review — DO NOT paraphrase or translate.
- The quote must directly support your classification.
- If the review is in German/French/Italian etc., quote in the original language.

## Output Format

Respond with ONLY a valid JSON object (no markdown, no explanation):
{
  "primary_category": "Commissioning|O&M|Localization|DevOps|Ecosystem",
  "user_persona": "Installer|Homeowner",
  "impact_severity": "Critical|Major|Minor",
  "is_sarcasm": false,
  "evidence_quote": "<verbatim quote from original text>",
  "sentiment_score": 0.0,
  "root_cause_tag": "<concise technical root cause or null>"
}

CRITICAL RULES:
- sentiment_score: float between -1.0 (very negative) and 1.0 (very positive)
- If is_sarcasm is true, sentiment_score MUST be negative
- evidence_quote MUST be an exact substring of the original review text
- root_cause_tag examples: "WiFi Handshake Timeout", "OTA Update Bricked", "CT Clamp Incompatible"
"""
```

### 5.2 User Prompt Template

```python
USER_PROMPT_TEMPLATE = """
Analyze the following app review:

**App:** {app_name}
**Platform:** {source_platform}
**Country:** {region_iso}
**Rating:** {rating}/5 stars
**Version:** {version}
**Date:** {review_date}

**Review Text:**
---
{content}
---

Provide your analysis as a JSON object following the system instructions.
"""
```

### 5.3 Prompt 设计要点

| 设计决策 | 理由 |
|---------|------|
| 强制 JSON-only 输出 | 消除 LLM "解释性废话"，便于 `json.loads()` 直接解析 |
| 枚举值内联到 Prompt | 避免 LLM 发明新类别，Pydantic 可做二次校验 |
| Evidence Quote 规则加粗 + 大写 | 经验: LLM 对 **MANDATORY** / **CRITICAL** 标记的遵从度更高 |
| 传入 `rating` 作为上下文 | 帮助 LLM 校准 sentiment (1星+正面文字 → 反讽信号) |
| 不翻译原文 | 保留多语言原貌，evidence_quote 才能做子串匹配 |

---

## 6. Skills Template Design

> **技能模板设计:** 为项目不同阶段提供标准化的开发指导

### 6.1 Skills 目录结构

```
.agents/
├── workflows/
│   ├── run_pipeline.md           # 全流程执行
│   └── add_new_app.md            # 新增监测目标
└── skills/
    ├── ingestion_skill/
    │   └── SKILL.md              # Scraper 开发指导
    ├── llm_processing_skill/
    │   └── SKILL.md              # LLM 处理 + 防幻觉
    ├── analytics_skill/
    │   └── SKILL.md              # 聚合分析指导
    └── dashboard_skill/
        └── SKILL.md              # Streamlit Dashboard 开发
```

### 6.2 Skill: Ingestion (数据抓取)

```yaml
---
name: SolarWatch Ingestion Skill
description: Guide for implementing incremental review scraping from Google Play and App Store
---
```

**核心职责:**
- 实现 `BaseScraper` 抽象接口 (`fetch_reviews(app_id, region_iso, since_date) → List[RawReview]`)
- Google Play: 使用 `google-play-scraper` 库, 按 country code + `REGION_LANG_MAP` 过滤
- App Store: 使用纯 `requests` 调用 Apple iTunes RSS JSON API (禁止第三方库)
- 增量逻辑: 查询 `MAX(review_date)` 作为 `last_fetched_date`
- 去重: 基于 `review_id` 的 `INSERT OR IGNORE`

**约束:**
- 遵守速率限制 (1 req/s Google Play, 0.5 req/s App Store)
- 所有日志使用 `src/utils/logger.py`
- 失败重试 3 次, 指数退避

### 6.3 Skill: LLM Processing (认知处理)

```yaml
---
name: SolarWatch LLM Processing Skill
description: Guide for implementing cognitive analysis with anti-hallucination validation
---
```

**核心职责:**
- 使用 `src/processing/prompt_templates.py` 中的模板
- 批量处理 (50 条/批), 异步调用
- **必须执行防幻觉校验** (调用 `hallucination_guard.validate_evidence_quote`)
- 反讽修正: `if is_sarcasm and sentiment > 0 → sentiment = -abs(sentiment)`
- 校验失败的记录: `hallucination_check_passed=False`, 仍写入但排除在聚合之外

**关键规则:**
- 永远不要跳过防幻觉校验步骤
- 每次 LLM 调用必须记录 `llm_model_version`
- 解析失败要有详细日志, 包含原始 LLM 响应

### 6.4 Skill: Analytics (聚合分析)

```yaml
---
name: SolarWatch Analytics Skill
description: Guide for implementing aggregation metrics and version regression analysis
---
```

**核心指标:**
1. **Severity-Adjusted Score** = `(Critical×3 + Major×2 + Minor×1) / total_count`
2. **Version Regression Rate** = `Δ(avg_rating_new - avg_rating_old) / avg_rating_old`
3. **B2B Pain Index** = `Installer 的 Critical+Major 评论占比`
4. **Sarcasm-Corrected Sentiment** = 修正后的平均情感得分
5. **Category Distribution** = 各 4+1 类别的占比

**区域聚合规则:**
- DACH = `region_iso IN ('DE', 'AT', 'CH')`
- South Europe = `region_iso IN ('IT', 'ES')`
- Emerging = `region_iso IN ('PL', 'RO')`

### 6.5 Skill: Dashboard (报告展示)

```yaml
---
name: SolarWatch Dashboard Skill
description: Guide for building the Streamlit reporting dashboard
---
```

**页面结构:**
1. **Overview**: 红蓝对标雷达图 (6 App × 5 维度)
2. **Version Timeline**: 版本迭代 + 评分趋势折线图
3. **Category Deep-Dive**: 4+1 分类下钻分析
4. **Regional Heatmap**: 欧洲三区域热力图
5. **Evidence Browser**: 可搜索的 evidence_quote 表格

---

## 7. Development Roadmap

### Sprint 1: Foundation (Week 1-2)

**目标:** 数据基座 + 配置系统

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| 项目骨架搭建 | `pyproject.toml`, 目录结构 | `pip install -e .` 成功 |
| SQLAlchemy Models | `src/models/database.py` | `init_db.py` 创建表, schema 完全匹配 DDL |
| 配置系统 | `settings.yaml` + `settings.py` | Pydantic 校验通过, 含 6+ App 定义 |
| 工具层 | `db.py`, `logger.py`, `text_utils.py` | 单元测试覆盖 |
| 常量定义 | `constants.py` | 所有枚举值与 DB Enum 一致 |

**Sprint 1 验收:** `python scripts/init_db.py` 成功创建 SQLite DB, 两张表 schema 正确

---

### Sprint 2: Ingestion Pipeline (Week 3-4)

**目标:** 增量数据抓取体系

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| BaseScraper 抽象 | `base_scraper.py` | 接口定义清晰, ABC enforced |
| Google Play 实现 | `google_play_scraper.py` | 抓取 FusionSolar DE 评论 ≥50 条 |
| App Store 实现 | `app_store_scraper.py` | 抓取 SMA DE 评论 ≥30 条 |
| 增量管理器 | `ingestion_manager.py` | 二次运行仅拉取新数据 |
| 集成测试 | `test_ingestion.py` | Mock API + 真实 DB 写入 |

**Sprint 2 验收:** `python scripts/run_ingestion.py` 对 6 个 App × 8 个国家完成首次全量抓取

---

### Sprint 3: Cognitive Processing (Week 5-6)

**目标:** LLM 分析 + 防幻觉体系

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| LLM Client | `llm_client.py` | 支持 Gemini/OpenAI 切换 |
| Prompt 模板 | `prompt_templates.py` | 输出 JSON 通过 Pydantic 解析率 ≥95% |
| 响应解析器 | `response_parser.py` | Pydantic model 覆盖所有字段 |
| 防幻觉校验 | `hallucination_guard.py` | 三级校验, 单元测试 ≥10 case |
| 主编排器 | `processor.py` | 端到端处理 100 条, 幻觉率 <5% |
| 反讽修正 | 集成在 processor | 德语反讽 case 修正正确 |

**Sprint 3 验收:** `python scripts/run_processing.py` 处理 500+ 条评论, `hallucination_check_passed` 通过率 ≥95%

---

### Sprint 4: Analytics & Reporting (Week 7-8)

**目标:** 指标聚合 + 可视化交付

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| 聚合引擎 | `aggregator.py` | 5 大指标计算正确 |
| 版本回归 | `version_regression.py` | 识别出至少 1 个回归案例 |
| 指标计算 | `metrics.py` | 红蓝对标数据完整 |
| Streamlit Dashboard | `dashboard.py`, `charts.py` | 5 个页面均可运行 |
| PDF 导出 | `pdf_export.py` | 一键生成分析报告 |

**Sprint 4 验收:** `streamlit run src/reporting/dashboard.py` 展示完整红蓝对标分析, PDF 可导出

---

## 附录: settings.yaml 示例

```yaml
project:
  name: "SolarWatch"
  time_window_days: 180

targets:
  - name: "Huawei FusionSolar"
    team: "red"
    google_play_id: "com.huawei.smartpvms"
    app_store_id: "1529080383"
    regions: ["DE", "AT", "CH", "IT", "ES", "PL", "RO"]

  - name: "Sungrow iSolarCloud"
    team: "red"
    google_play_id: "com.isolarcloud.manager"
    app_store_id: "1050077439"
    regions: ["DE", "AT", "CH", "IT", "ES", "PL", "RO"]

  - name: "SMA Energy"
    team: "blue"
    google_play_id: "de.sma.energy"
    app_store_id: "1476822720"
    regions: ["DE", "AT", "CH", "IT", "ES", "PL", "RO"]

  - name: "Fronius Solar.web"
    team: "blue"
    google_play_id: "com.fronius.solarweb"
    app_store_id: "1528302827"
    regions: ["DE", "AT", "CH", "IT", "ES", "PL", "RO"]

  - name: "SolarEdge"
    team: "blue"
    google_play_id: "com.solaredge.homeowner"
    app_store_id: "1473952773"
    regions: ["DE", "AT", "CH", "IT", "ES", "PL", "RO"]

  - name: "Enphase Enlighten"
    team: "blue"
    google_play_id: "com.enphaseenergy.myenlighten"
    app_store_id: "787415770"
    regions: ["DE", "AT", "CH", "IT", "ES", "PL", "RO"]

llm:
  provider: "gemini"         # gemini | openai
  model: "gemini-2.5-pro"
  batch_size: 50
  temperature: 0.1           # 低温度 = 高确定性
  max_retries: 3

database:
  path: "data/solarwatch.db"

scraping:
  rate_limit_google: 1.0     # seconds between requests
  rate_limit_appstore: 0.5
  max_retries: 3
```
