"""
SolarWatch Visual Dashboard (Endogenous Version Analysis)
=========================================================
Strict 1-2-1 Executive Minimalist (McKinsey White) Layout.
Completely decoupled from external app_releases. Relies solely on 
raw_reviews.app_version to track lifecycles.
"""

import sqlite3
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Support relative imports for Python execution as standalone script
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.dashboard.styles import inject_custom_css

# ─── Page config ─────────────────────────────────────────
st.set_page_config(
    page_title="SolarWatch CI Radar",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Paths & Colors ──────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "solarwatch.db"

COLORS = {
    "bg_light": "#FFFFFF",
    "positive": "#10B981", # Business Green 
    "negative": "#EF4444", # Deep Red
    "neutral": "#9CA3AF",
    "text": "#1E3A8A", # Deep Blue
    "warning": "#F59E0B"
}

# ─── Language Pack ─────────────────────────────────────────
LANGS = {
    "zh": {
        "sidebar_lang": "### 🌐 Language",
        "sidebar_nav": "### 🧭 导航 (Navigation)",
        "sidebar_time": "### ⏳ 时间窗口 (Time Window)",
        "sidebar_filter": "### 🏢 品牌过滤 (App Filter)",
        "nav_options": ["版本质量基准 (Quality Benchmark)", "深度洞察 (Deep Insights)"],
        "quick_select": "快速预设",
        "motivation_title": "### 🎯 项目初衷 (Motivation)",
        "motivation_text": "**SolarWatch** 利用 Gemini 2.5 Flash 语义能力，将数千条混沌语料转化为可量化的对标刻度，旨在揭示厂商在数字化转型中的真实研发响应速度。",
        "compliance_title": "### ⚖️ 合规声明 (Compliance Disclaimer)",
        "compliance_text": "本看板所展示数据均为应用商店（App Store & Google Play）公开评论。系统已通过自动脱敏技术屏蔽潜在的个人隐私信息。分析结论仅供行业研究参考，不代表品牌官方立场。",
        "kpi_ios": "iOS 分析样本量",
        "kpi_android": "Android 分析样本量（缺失Huawei FusionSolar）",
        "kpi_days": "平均版本活跃周期",
        "mod_a_title": "🏆 软件质量红黑榜：谁在定义行业标杆？",
        "mod_a_info": "* **标杆效应：** 榜单顶部通常由长期维持在 **$S_{weighted}$ > 0.1** 分值的品牌占据，这表明其软件迭代已进入“正向口碑循环”。\n* **风险阈值：** 处于红色区域底部（$S_{weighted}$ <-0.5）的版本通常伴随着 **Critical (致命阻断)** 问题的集中爆发。若某品牌连续三个版本处于该区间，往往预示着该品牌正在经历大规模的底层架构调整或严重的交付质量危机。\n\n",
        "mod_b_title": "🧬 病灶演进：最近四个版本，他们在修 Bug 还是制造 Bug？",
        "mod_b_info": "📊 **洞察提示**：如果某类 Critical 级别的痛点在连续四个版本中占比均未下降，通常意味着该问题已从“偶发 Bug”演变为“架构性顽疾”，建议作为季度核心技术攻坚目标。",
        "mod_b_select": "选择目标品牌进行深潜 (Deep Dive):",
        "mod_c_title": "📈 迭代脉搏：谁在快速响应欧洲市场？",
        "mod_c_info": "**图例洞察**：横坐标为时间线，色块跨度代表版本的市场存活期。**色块深浅映射 $S_{weighted}$**：深红 = 口碑崩塌，深绿 = 质量稳健。\n发版密度高（色块紧凑）且颜色翠绿，代表该品牌在数字战场上的敏捷修复与作战能力处于统治地位。",
        "mod_d_title": "🔍 原始评论与 AI 分析明细",
        "mod_d_expander": "📖 字段定义与解读指南 (Field Definition Guide)",
        "mod_d_guide": "- **App 名称**：品牌标准名称。\n- **平台**：数据的抓取渠道（🍎 iOS 或 🤖 Android）。\n- **版本**：用户评论时对应的软件版本号。\n- **日期**：评论提交的原始时间（UTC）。\n- **严重程度**：🔴 Critical (致命) / 🟡 Major (严重) / 🟢 Minor (轻微)。\n- **AI 核心诊断**：Gemini 解析出的核心痛点标签。\n- **用户原声**：用户提交的原始多语言文本。\n- **AI 证据提取**：AI 从原文中逐字摘录的判定依据，确保分析可回溯。\n- **个体情感分**：量化评分（-1.0 至 1.0）。",
        "cols": {
            'app_name': 'App 名称', 'source_platform': '平台', 'version': '版本',
            'review_date': '日期', 'impact_severity': '严重程度', 'root_cause_tag': 'AI 核心诊断',
            'content': '用户原声', 'evidence_quote': 'AI 证据提取', 'sentiment_score': '个体情感分'
        },
        "deep_insights_title": "## 🧠 深度洞察 (Advanced Insights) — Coming Soon",
        "deep_insights_desc": "本模块旨在通过更细颗粒度的维度，解码品牌背后的核心竞争力。",
        "beta_warning": "🚀 目前这些功能处于 Beta 内部测试阶段。",
        "dna_title": "### 🧬 数据基因 (Data DNA)：多维语义解析与量化标准",
        "dna_desc": "SolarWatch 系统的分析基础源于对海量非结构化文本的量化处理。每一条原始评论均经过 **Gemini 2.5 Flash** 的深度语义解析，提取出以下核心维度：",
        "dna_exp1_title": "1. Sentiment_Score (个体情感分)",
        "dna_exp1_text": "是对单条评论文本的语境、语气及情绪强度进行的定量分析。Gemini 将主观描述转化为 **-1.0 至 1.0** 之间的连续数值：\n- **1.0 (极度正面)**：表示用户对产品表现出极高的满意度与品牌忠诚度。\n- **0.0 (中性)**：表示评论仅包含事实陈述，不具备明显情绪倾向。\n- **-1.0 (极度负面)**：表示用户对产品体验表现出极度的不满或业务遭受了实质性损失。\n\n**分析样例：**\n- 样例 1: *\"App crashing every time I open settings.\"* → **-0.85**\n- 样例 2: *\"Installation was smooth, highly recommend.\"* → **+0.92**",
        "dna_exp2_title": "2. Severity Categories (业务影响等级)",
        "dna_exp2_text": "评论描述的问题对用户业务运营的影响程度，Gemini将评论分为Critical，Major，Minor三个等级：\n- 🔴 **Critical (致命)**：核心业务流程中断。如：无法登录、App 持续崩溃、或电站实时监控数据丢失。\n- 🟡 **Major (严重)**：核心功能受损或体验显著下降。如：数据刷新严重延迟、复杂的配网逻辑错误、或核心交互功能失效。\n- 🟢 **Minor (轻微)**：非核心功能的优化建议。如：界面语言翻译误差、UI 审美偏好、或辅助性的功能改进提议。",
        "dna_exp3_title": "3. Severity-Weighted Scoring (惩罚性加权得分)",
        "dna_exp3_text": "**权重矩阵 ($W_i$) 定义：**\n为区分不同严重程度问题的负面影响，系统设定了权重系数：\n- **Critical = 5**：致命问题的权重是基准权重的 5 倍。\n- **Major = 2**：严重缺陷的权重是基准权重的 2 倍。\n- **Minor = 1**：轻微建议按基准权重计算。\n\n**逻辑解释：**\n- **加权求和 ($\\sum (S_i \\times W_i)$)**：通过权重放大 Critical 负评的影响。确保少数致命 Bug 不会被海量轻微好评所掩盖。\n- **归一化处理 ($\\sum W_i$)**：将结果映射回 -1.0 至 1.0 标准区间，消除不同品牌、不同版本之间评论样本量差异带来的统计偏见，确保品牌间公平对标。\n\n**分析结论导向：**\n当得分 < **-0.15** 时，代表“致命 Bug”的伤害已超过正面收益，研发团队需立即介入。\n*注：系统将 -0.15 设定为行业健康基准线，以对冲公开市场的负向反馈偏见。（即满意用户评价动机低于不满意用户）*",
        "mod_b_tracking": "追踪 **{brand}** 最近的 4 个活跃版本: `{versions}`",
        "mod_b_no_data": "该品牌版本数据不足。",
        "mod_b_no_tags": "这些版本内没有被标记的具体痛点 (root_cause_tag)。",
        "deep_insights_item1": "### 📍 区域体感差异 (Regional Variance)\n- 探索同一版本在德国、意大利、英国等不同电网环境下的表现差异，识别本地化适配痛点。",
        "deep_insights_item2": "### 📱 平台性能鸿沟 (Platform Delta)\n- **iOS vs Android 深度对标**：分析同一品牌在不同系统架构下的研发资源倾斜与稳定性差异。",
        "deep_insights_item3": "### 💎 需求挖掘机 (Feature Request Mining)\n- 利用 AI 对用户建议进行聚类分析，识别光伏用户最渴望的“杀手级”功能趋势。",
        "deep_insights_item4": "### ⏱️ 修复时延分析 (Bug Fix Lead Time)\n- 追踪核心 Bug 从首次曝光到彻底修复的平均生命周期，量化各厂家的敏捷开发效能。",
        "warning_no_data": "⚠️ 没有查找到任何有效分析数据，请调宽时间窗口。",
        "warning_no_baseline": "⚠️ 未能探测到拥有连续样本 ($N \\ge 5$) 的有效版本基线。",
        "rv_title": "### 📍 区域体感差异 (Regional Variance)",
        "rv_desc": "通过计算各国加权情感分与全球基准的**偏离度 ($\\Delta S_{region}$)**，精准定位品牌在不同电网环境下的适配差异。",
        "rv_brand_select": "选择分析品牌",
        "rv_map_title": "🗺️ 欧洲体感热力图",
        "rv_map_hover_n": "样本量",
        "rv_map_hover_tag": "Top 1 根因",
        "rv_leaderboard_title": "🏅 偏差排行榜",
        "rv_leaderboard_best": "✅ 适配标杆 Top 3",
        "rv_leaderboard_worst": "🚨 适配重灾区 Top 3",
        "rv_drilldown_title": "🔬 根因下钻面板",
        "rv_drilldown_select": "选择关注国家",
        "rv_methodology_title": "📐 计算逻辑说明书 (Methodology)",
        "rv_methodology": "### 核心指标体系 (KPI Methodology)\n为了精准量化全球各市场的“体感差异”，我们建立了三层加权指标模型：\n\n---\n\n#### **A. 区域加权健康分 ($S_{country}$)**\n$$S_{country} = \\frac{\\sum (Sentiment\\_Score_i \\times W_i)}{\\sum W_i}$$\n* **$S_i$ (情感分)**：由 Gemini 对单条评论生成的语义得分（-1.0 到 1.0）。\n* **$W_i$ (惩罚性权重)**：基于严重程度映射：**Critical (致命)=5, Major (严重)=2, Minor (轻微)=1**。\n* **逻辑解析**：采用**“故障放大模型”**。我们认为一个致命 Bug（如：德国区无法配网）对品牌造成的杀伤力等同于 5 个轻微吐槽。\n\n#### **B. 全球基准线 ($S_{global}$)**\n$$S_{global} = \\frac{\\sum_{\\text{All Regions}} (S_i \\times W_i)}{\\sum_{\\text{All Regions}} W_i}$$\n* **逻辑解析**：代表该品牌软件版本在所有抓取地域的“基本盘”表现，用于消除品牌本身的基准分差异。\n\n#### **C. 区域偏离度 ($\\Delta S_{region}$)**\n$$\\Delta S_{region} = S_{country} - S_{global}$$\n* **核心意义**：这是衡量**“水土不服”**最有效的指标。它剔除了“品牌自带流量”的影响，直击地域性差异（如电网合规、服务器延迟）。\n\n---\n> **💡 洞察提示**：当 $\\Delta S_{region} < -0.2$ 时，通常意味着该地区存在严重的本地化适配痛点或区域基础设施不稳。",
        "rv_no_data": "该品牌在当前时间窗口内无足够区域数据 (N≥5)。",
        "rv_delta_label": "偏离度 ΔS",
        "pd_title": "### 📱 平台性能鸿沟 (Platform Delta)",
        "pd_desc": "通过计算 **$\\Delta S_{platform} = S_{iOS} - S_{Android}$** 级差，透视厂商在两大生态下的研发资源分配差异。",
        "pd_tornado_title": "🌪️ iOS vs Android 龙卷风对比图",
        "pd_ios": "🍏 iOS",
        "pd_android": "🤖 Android",
        "pd_delta": "ΔS (平台偏差)",
        "pd_rootcause_title": "🔬 根因对比矩阵",
        "pd_rootcause_select": "选择品牌深入对比",
        "pd_top_issues": "Top 3 负面标签",
        "pd_balanced": "⚖️ **双端体验一致性极佳** ($|\\Delta S| < 0.1$)",
        "pd_bias": "🚨 **发现研发偏见 (R&D Bias Detected)** ($|\\Delta S| > 0.2$)",
        "pd_no_data": "该品牌缺少某个平台的数据，无法进行跨平台对标。",
        "pd_excluded": "⚠️ 以下品牌因单平台数据不足 (N<5) 而未参与对标："
    },
    "en": {
        "sidebar_lang": "### 🌐 Language",
        "sidebar_nav": "### 🧭 Navigation",
        "sidebar_time": "### ⏳ Time Window",
        "sidebar_filter": "### 🏢 App Filter",
        "nav_options": ["Quality Benchmark", "Deep Insights"],
        "quick_select": "Quick Select",
        "motivation_title": "### 🎯 Motivation",
        "motivation_text": "**SolarWatch** leverages Gemini 2.5 Flash semantics to translate thousands of chaotic user quotes into quantifiable benchmarks, revealing true R&D agility during digital transformation.",
        "compliance_title": "### ⚖️ Compliance Disclaimer",
        "compliance_text": "Data displayed is entirely sourced from public App Store & Google Play reviews. An automated algorithm masks PII dynamically. Findings are for industry research only and do not represent official brand stances.",
        "kpi_ios": "iOS Sample Size",
        "kpi_android": "Android Sample Size (No Huawei)",
        "kpi_days": "Avg. Version Lifespan (Days)",
        "mod_a_title": "🏆 Software Health Leaderboard: Defining the Benchmark",
        "mod_a_info": "* **Benchmark Effect:** Brands dominating the top (maintaining **$S_{weighted}$ > 0.1**) indicate a positive iteration loop.\n* **Risk Threshold:** Versions falling into the red zone ($S_{weighted}$ <-0.5) correlate with concentrated **Critical** issues. Three consecutive versions in this zone warn of deep architectural instability.\n\n",
        "mod_b_title": "🧬 Issue Evolution: Are they fixing or creating bugs?",
        "mod_b_info": "📊 **Insight Tip**: If a Critical pain point's frequency remains undiminished across 4 versions, the issue has morphed from an 'occasional bug' into an 'architectural flaw', requiring strategic intervention.",
        "mod_b_select": "Select target brand for Deep Dive:",
        "mod_c_title": "📈 Iteration Cadence Timeline",
        "mod_c_info": "**Legend Insight**: X-axis is time, block width is market lifespan. **Color maps to $S_{weighted}$**: Dark Red = Collapse, Green = Stable.\nDense blocks with solid green represent dominant agile delivery capabilities.",
        "mod_d_title": "🔍 Raw Reviews & AI Analysis Details",
        "mod_d_expander": "📖 Field Definition Guide",
        "mod_d_guide": "- **App**: Standardized brand name.\n- **Platform**: Data source (🍎 iOS or 🤖 Android).\n- **Version**: Software version during the review.\n- **Date**: Original UTC submission time.\n- **Severity**: 🔴 Critical / 🟡 Major / 🟢 Minor.\n- **AI Tag**: Core complaint tag parsed by Gemini.\n- **Original Voice**: Multilingual user text.\n- **AI Evidence**: Exact quote extracted by AI to guarantee traceability.\n- **Sentiment**: Quantified score (-1.0 to 1.0).",
        "cols": {
            'app_name': 'App Name', 'source_platform': 'Platform', 'version': 'Version',
            'review_date': 'Date', 'impact_severity': 'Severity', 'root_cause_tag': 'AI Root Cause',
            'content': 'Original Voice', 'evidence_quote': 'AI Evidence Quote', 'sentiment_score': 'Sentiment Score'
        },
        "deep_insights_title": "## 🧠 Advanced Insights — Coming Soon",
        "deep_insights_desc": "This module is designed to decode the core competitiveness behind brands through highly granular dimensions.",
        "beta_warning": "🚀 These features are currently in closed Beta testing.",
        "dna_title": "### 🧬 Data DNA: Semantic Parsing & Scoring",
        "dna_desc": "SolarWatch analysis stems from quantifying vast unstructured text. Every raw review undergoes **Gemini 2.5 Flash** parsing to extract core dimensions:",
        "dna_exp1_title": "1. Sentiment_Score",
        "dna_exp1_text": "A quantitative analysis of the context, tone, and emotional intensity of a single review. Gemini translates subjective descriptions into continuous values between **-1.0 and 1.0**:\n- **1.0 (Extremely Positive)**: High user satisfaction and brand loyalty.\n- **0.0 (Neutral)**: Factual statements without obvious emotional bias.\n- **-1.0 (Extremely Negative)**: Extreme dissatisfaction or material loss due to product experience.\n\n**Analysis Examples:**\n- Ex 1: *\"App crashing every time I open settings.\"* → **-0.85**\n- Ex 2: *\"Installation was smooth, highly recommend.\"* → **+0.92**",
        "dna_exp2_title": "2. Severity Categories",
        "dna_exp2_text": "The degree to which the problem impacts the user's business operations. Gemini classifies reviews into 3 tiers:\n- 🔴 **Critical**: Core business interruption (e.g., login failures, persistent crashes, missing real-time plant data).\n- 🟡 **Major**: Core functions damaged or notably degraded (e.g., delayed data refresh, complex networking logic errors, UI interaction failures).\n- 🟢 **Minor**: Optimization suggestions for non-core functions (e.g., translation errors, aesthetic preferences, minor UI improvements).",
        "dna_exp3_title": "3. Severity-Weighted Scoring",
        "dna_exp3_text": "**Weight Matrix ($W_i$) Definition:**\nTo distinguish the negative impact of different severities, the system applies multipliers:\n- **Critical = 5**: 5x the baseline weight.\n- **Major = 2**: 2x the baseline weight.\n- **Minor = 1**: 1x baseline weight.\n\n**Logical Explanation:**\n- **Weighted Sum ($\\sum (S_i \\times W_i)$)**: Amplifies the impact of Critical negative reviews to ensure fatal bugs aren't buried by a volume of minor praise.\n- **Normalization ($\\sum W_i$)**  : Maps the score back to a -1.0 to 1.0 metric, eliminating statistical bias caused by varying review sample sizes across brands, ensuring fair benchmarking.\n\n**Actionable Insight:**\nA score < **-0.15** indicates that the damage from \"Critical Bugs\" outweighs positive gains, requiring immediate R&D intervention.\n*Note: -0.15 is set as the industry health baseline to offset the negative feedback bias typical of public app stores.*",
        "mod_b_tracking": "Tracking **{brand}**'s latest 4 active releases: `{versions}`",
        "mod_b_no_data": "Insufficient version data for this brand.",
        "mod_b_no_tags": "No specific root_cause_tag identified in these versions.",
        "deep_insights_item1": "### 📍 Regional Variance\n- Explore performance differences of the same version across different grid environments (e.g., Germany, Italy, UK) to identify localization pain points.",
        "deep_insights_item2": "### 📱 Platform Delta\n- **iOS vs Android Deep Benchmark**: Analyze R&D resource allocation and stability differences across operating systems for the same brand.",
        "deep_insights_item3": "### 💎 Feature Request Mining\n- Utilize AI to cluster user suggestions and identify the 'killer feature' trends most desired by PV users.",
        "deep_insights_item4": "### ⏱️ Bug Fix Lead Time\n- Track the average lifecycle of critical bugs from first exposure to complete resolution, quantifying the agile development efficiency of each manufacturer.",
        "warning_no_data": "⚠️ No valid analysis data found. Please expand the time window.",
        "warning_no_baseline": "⚠️ Failed to detect a valid version baseline with continuous samples ($N \\ge 5$).",
        "rv_title": "### 📍 Regional Variance",
        "rv_desc": "Pinpoint brand adaptation gaps by computing the **deviation ($\\Delta S_{region}$)** of each country's weighted sentiment from the global baseline.",
        "rv_brand_select": "Select brand for analysis",
        "rv_map_title": "🗺️ EU Sentiment Heatmap",
        "rv_map_hover_n": "Sample Size",
        "rv_map_hover_tag": "Top 1 Root Cause",
        "rv_leaderboard_title": "🏅 Regional Leaderboard",
        "rv_leaderboard_best": "✅ Adaptation Benchmark Top 3",
        "rv_leaderboard_worst": "🚨 Adaptation Risk Zone Top 3",
        "rv_drilldown_title": "🔬 Root Cause Deep Dive",
        "rv_drilldown_select": "Select country to inspect",
        "rv_methodology_title": "📐 Methodology",
        "rv_methodology": "### KPI Methodology\nTo precisely quantify the \"experience gap\" across global markets, we built a three-layer weighted KPI model:\n\n---\n\n#### **A. Regional Weighted Health Score ($S_{country}$)**\n$$S_{country} = \\frac{\\sum (Sentiment\\_Score_i \\times W_i)}{\\sum W_i}$$\n* **$S_i$ (Sentiment Score)**: Semantic score generated by Gemini for each review (-1.0 to 1.0).\n* **$W_i$ (Penalty Weight)**: Severity-based mapping: **Critical=5, Major=2, Minor=1**.\n* **Rationale**: A **\"fault amplification model\"** — a single Critical bug (e.g., commissioning failure in Germany) deals 5× the impact of a Minor complaint.\n\n#### **B. Global Baseline ($S_{global}$)**\n$$S_{global} = \\frac{\\sum_{\\text{All Regions}} (S_i \\times W_i)}{\\sum_{\\text{All Regions}} W_i}$$\n* **Rationale**: Represents the brand's \"baseline\" performance across all scraped regions, eliminating inter-brand scoring bias.\n\n#### **C. Regional Deviation ($\\Delta S_{region}$)**\n$$\\Delta S_{region} = S_{country} - S_{global}$$\n* **Core Insight**: The most effective metric for measuring **\"localization mismatch\"**. It strips away brand-level noise and targets regional-specific issues (grid compliance, server latency, etc.).\n\n---\n> **💡 Insight Tip**: When $\\Delta S_{region} < -0.2$, it typically indicates severe localization pain points or unstable regional infrastructure.",
        "rv_no_data": "Insufficient regional data (N≥5) for this brand in the current time window.",
        "rv_delta_label": "Deviation ΔS",
        "pd_title": "### 📱 Platform Delta",
        "pd_desc": "Reveal R&D resource allocation gaps by computing the **$\\Delta S_{platform} = S_{iOS} - S_{Android}$** differential.",
        "pd_tornado_title": "🌪️ iOS vs Android Tornado Chart",
        "pd_ios": "🍏 iOS",
        "pd_android": "🤖 Android",
        "pd_delta": "ΔS (Platform Bias)",
        "pd_rootcause_title": "🔬 Root Cause Comparison Matrix",
        "pd_rootcause_select": "Select brand for deep comparison",
        "pd_top_issues": "Top 3 Negative Tags",
        "pd_balanced": "⚖️ **Dual-platform consistency is excellent** ($|\\Delta S| < 0.1$)",
        "pd_bias": "🚨 **R&D Bias Detected** ($|\\Delta S| > 0.2$)",
        "pd_no_data": "This brand lacks data on one platform and cannot be benchmarked.",
        "pd_excluded": "⚠️ The following brands are excluded due to insufficient single-platform data (N<5):"
    }
}

# ═══════════════════════════════════════════════════════════
# DATA LOADING (cached)
# ═══════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    """Load all valid processed reviews with full JOIN to raw_reviews."""
    conn = sqlite3.connect(str(DB_PATH))
    query = """
        SELECT 
            rr.review_id,
            rr.app_name,
            rr.version,
            rr.source_platform,
            rr.region_iso,
            rr.rating,
            rr.review_date,
            rr.content,
            pr.primary_category,
            pr.user_persona,
            pr.impact_severity,
            pr.sentiment_score,
            pr.root_cause_tag,
            pr.evidence_quote
        FROM processed_reviews pr
        JOIN raw_reviews rr ON pr.raw_id = rr.review_id
        WHERE pr.hallucination_check_passed = 1
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df["review_date"] = pd.to_datetime(df["review_date"])
    df["date"] = df["review_date"].dt.date
    
    # Filter out empty versions
    df = df[df['version'].notna()]
    df['version'] = df['version'].astype(str).str.strip()
    df = df[df['version'] != '']
    df = df[df['version'] != 'Unknown']
    
    return df

def get_severity_weight(sev: str) -> float:
    if sev == 'Critical': return 5.0
    if sev == 'Major': return 2.0
    if sev == 'Minor': return 1.0
    return 1.0

# ═══════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════

def render_sidebar(df: pd.DataFrame) -> tuple[str, Optional[pd.DataFrame]]:
    st.sidebar.markdown(
        "<h1 style='text-align:center;'>☀️ SolarWatch<br>CI Radar</h1>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")
    
    # Initial Language Switcher (Bootstrap to get L_dict)
    st.sidebar.markdown(LANGS[st.session_state.get('lang', 'zh')]["sidebar_lang"])
    lang_sel = st.sidebar.radio(
        "Language", 
        ["中文", "English"], 
        horizontal=True, 
        label_visibility="collapsed"
    )
    st.session_state.lang = "en" if lang_sel == "English" else "zh"
    L_dict = LANGS[st.session_state.lang]
    st.sidebar.markdown("---")

    # Navigation Selector
    st.sidebar.markdown(L_dict["sidebar_nav"])
    page_selection = st.sidebar.radio(
        "Navigation",
        L_dict["nav_options"],
        label_visibility="collapsed"
    )
    st.sidebar.markdown("---")

    filtered = df.copy()

    # ── Primary Filters (Global — always visible on all pages) ──
    st.sidebar.markdown(L_dict["sidebar_time"])
    time_preset = st.sidebar.selectbox(
        L_dict["quick_select"],
        ["All (180 days)", "Last 90 days", "Last 30 days", "Custom"],
        index=0,
        label_visibility="collapsed"
    )

    if not df.empty:
        min_date = df["review_date"].min().date()
        max_date = df["review_date"].max().date()

        if time_preset == "Last 90 days":
            start = max_date - timedelta(days=90)
            end = max_date
        elif time_preset == "Last 30 days":
            start = max_date - timedelta(days=30)
            end = max_date
        elif time_preset == "Custom":
            start, end = st.sidebar.date_input("Date Range", value=(min_date, max_date))
        else:
            start, end = min_date, max_date

        filtered = df[(df["review_date"].dt.date >= start) & (df["review_date"].dt.date <= end)]

    st.sidebar.markdown("---")
    st.sidebar.markdown(L_dict["sidebar_filter"])
    apps = sorted(df["app_name"].unique())
    selected_apps = st.sidebar.multiselect(
        "App Filter", 
        apps, 
        default=apps, 
        label_visibility="collapsed"
    )
    filtered = filtered[filtered["app_name"].isin(selected_apps)]

    st.sidebar.markdown("---")
    st.sidebar.markdown(L_dict["motivation_title"])
    st.sidebar.markdown(L_dict["motivation_text"])

    st.sidebar.markdown(L_dict["compliance_title"])
    st.sidebar.markdown(L_dict["compliance_text"])

    return page_selection, filtered, L_dict

# ═══════════════════════════════════════════════════════════
# ENDOGENOUS PROCESSING
# ═══════════════════════════════════════════════════════════

def compute_endogenous_versions(df: pd.DataFrame) -> pd.DataFrame:
    """Group by app_name and version, calculate weighted health and timeline."""
    records = []
    
    # Calculate weights row by row first to speed up groupby logic
    df_copy = df.copy()
    df_copy['weight'] = df_copy['impact_severity'].apply(get_severity_weight)
    df_copy['weighted_score_contrib'] = df_copy['sentiment_score'] * df_copy['weight']
    
    grouped = df_copy.groupby(['app_name', 'version'])
    
    for (app_name, version), group in grouped:
        count = len(group)
        if count < 5:
            continue # Filter out orphan versions
            
        t_min = group['review_date'].min()
        t_max = group['review_date'].max()
        
        total_weight = group['weight'].sum()
        s_weighted = group['weighted_score_contrib'].sum() / total_weight if total_weight > 0 else 0
        
        # Get top complaint
        tags = group[group['root_cause_tag'].notna() & (group['root_cause_tag'] != 'N/A')]['root_cause_tag']
        top_complaint = tags.value_counts().idxmax() if not tags.empty else "No major issues"
        
        records.append({
            "app_name": app_name,
            "version": version,
            "Review Count": count,
            "T_min": t_min,
            "T_max": t_max,
            "Active Days": (t_max - t_min).days + 1,
            "S_weighted": s_weighted,
            "Top Complaint": top_complaint
        })
        
    return pd.DataFrame(records)

# ═══════════════════════════════════════════════════════════
# MODULE RENDERING
# ═══════════════════════════════════════════════════════════

def render_kpis(df: pd.DataFrame, vers_df: pd.DataFrame, L_dict: dict):
    if df.empty or vers_df.empty:
        return
        
    ios_count = len(df[df['source_platform'] == 'app_store'])
    android_count = len(df[df['source_platform'] == 'google_play'])
    
    avg_active_days = vers_df['Active Days'].mean()
    
    col1, col2, col3 = st.columns(3)
    col1.metric(L_dict["kpi_ios"], f"{ios_count:,}")
    col2.metric(L_dict["kpi_android"], f"{android_count:,}")
    col3.metric(L_dict["kpi_days"], f"{avg_active_days:.1f}")


def render_module_a(vers_df: pd.DataFrame, L_dict: dict):
    """Module A: Weighted Health Leaderboard (Top 3 per app)"""
    st.subheader(L_dict["mod_a_title"])
    st.info(L_dict["mod_a_info"])
    
    
    if vers_df.empty:
        return
        
    # Sort and pick top 3 per app
    top3_vers = vers_df.sort_values(['app_name', 'S_weighted'], ascending=[True, False])
    top3_vers = top3_vers.groupby('app_name').head(3).reset_index(drop=True)
    
    # Sort globally for the chart
    top3_vers = top3_vers.sort_values(by='S_weighted', ascending=True)
    top3_vers['Label'] = top3_vers['app_name'] + " | " + top3_vers['version']
    top3_vers['Color'] = top3_vers['S_weighted'].apply(lambda x: COLORS['positive'] if x >= -0.15 else COLORS['negative'])
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=top3_vers['S_weighted'],
        y=top3_vers['Label'],
        orientation='h',
        marker_color=top3_vers['Color'],
        text=[f"{val:+.2f}" for val in top3_vers['S_weighted']],
        textposition="outside",
        hovertext=[f"Reviews: {c} | {t}" for c, t in zip(top3_vers['Review Count'], top3_vers['Top Complaint'])],
        hoverinfo="y+x+text"
    ))
    
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="#111827", showgrid=True, gridcolor="#E5E7EB"),
        yaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig, use_container_width=True)

def render_module_b(df: pd.DataFrame, vers_df: pd.DataFrame, L_dict: dict):
    """Module B: 4-Version Drift Analysis"""
    st.subheader(L_dict["mod_b_title"])
    st.info(L_dict["mod_b_info"])
    
    if vers_df.empty:
        return
        
    apps = sorted(vers_df['app_name'].unique())
    selected_app = st.selectbox(L_dict["mod_b_select"], apps)
    
    app_vers = vers_df[vers_df['app_name'] == selected_app].sort_values(by='T_max', ascending=False)
    latest_4 = app_vers.head(4)['version'].tolist()
    
    if not latest_4:
        st.info(L_dict["mod_b_no_data"])
        return
        
    st.markdown(L_dict["mod_b_tracking"].format(brand=selected_app, versions=', '.join(latest_4)))
    
    # Filter raw reviews to these 4 versions
    drift_df = df[(df['app_name'] == selected_app) & (df['version'].isin(latest_4))].copy()
    drift_df = drift_df[(drift_df['root_cause_tag'].notna()) & (drift_df['root_cause_tag'] != 'N/A')]
    
    if drift_df.empty:
        st.info(L_dict["mod_b_no_tags"])
        return
        
    # Get Top 5 global tags for these 4 versions
    top5_tags = drift_df['root_cause_tag'].value_counts().head(5).index.tolist()
    drift_top5 = drift_df[drift_df['root_cause_tag'].isin(top5_tags)]
    
    # Count occurrences per version per tag
    grouped = drift_top5.groupby(['root_cause_tag', 'version']).size().reset_index(name='count')
    
    color_scale = px.colors.sequential.Blues[::-1] # Darkest for newest
    color_map = {v: color_scale[i % len(color_scale)] for i, v in enumerate(latest_4)}
    
    fig = px.bar(
        grouped,
        x="root_cause_tag",
        y="count",
        color="version",
        barmode="group",
        category_orders={"version": latest_4},
        color_discrete_map=color_map,
        labels={"root_cause_tag": "Root Cause", "count": "Count", "version": "Version"},
        height=350
    )
    
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)
    
   

def render_module_c(vers_df: pd.DataFrame, L_dict: dict):
    """Module C: Iteration Cadence Timeline"""
    st.subheader(L_dict["mod_c_title"])
    st.info(L_dict["mod_c_info"])
    
    if vers_df.empty:
        return
        
    df_gantt = vers_df.sort_values(by=['app_name', 'T_min'])
    df_gantt['Hover_Text'] = df_gantt.apply(
        lambda r: f"Version: {r['version']}<br>Score: {r['S_weighted']:+.2f}<br>Reviews: {r['Review Count']}<br>Top Bug: {r['Top Complaint']}", 
        axis=1
    )
    
    fig = px.timeline(
        df_gantt, 
        x_start="T_min", 
        x_end="T_max", 
        y="app_name",
        color="S_weighted",
        color_continuous_scale=[COLORS['negative'], COLORS['neutral'], COLORS['positive']],
        color_continuous_midpoint=-0.15,
        hover_name="version",
        hover_data={"S_weighted": ':.2f', "Hover_Text": True, "T_min": False, "T_max": False, "app_name": False},
        labels={"app_name": "Brand"}
    )
    
    # Custom hover template
    fig.update_traces(hovertemplate="%{customdata[1]}<extra></extra>")
    
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin=dict(l=0, r=0, t=10, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)


def render_module_d(df: pd.DataFrame, L_dict: dict):
    """Module D: Data Detail Explorer (Real-time Raw Data Drill-down)"""
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader(L_dict["mod_d_title"])
    
    # 📖 字段定义与解读指南
    with st.expander(L_dict["mod_d_expander"], expanded=False):
        st.markdown(L_dict["mod_d_guide"])
    
    if df.empty:
        st.info("数据为空，调整过滤条件。")
        return
    
    # --- Brand Metadata Mapping ---
    brand_mapping = {
        '1105054117': 'Huawei FusionSolar', 'com.huawei.smartpv': 'Huawei FusionSolar',
        '1530232432': 'SMA Energy', 'com.sma.energy': 'SMA Energy',
        '1551061321': 'Fronius Solar.web', 'com.fronius.solarweb': 'Fronius Solar.web',
        '1134260021': 'Sungrow iSolarCloud', 'com.isolarcloud.sunnypv': 'Sungrow iSolarCloud',
        '1121029283': 'Enphase Enlighten', 'com.enphaseenergy.enlighten': 'Enphase Enlighten',
        '1004652277': 'SolarEdge', 'com.solaredge.onestop': 'SolarEdge'
    }
    
    display_df = df.copy()
    display_df['app_name'] = display_df['app_name'].apply(lambda x: brand_mapping.get(str(x), x))
    
    # Format Data
    display_df = display_df.sort_values(by='review_date', ascending=False)
    
    if pd.api.types.is_datetime64_any_dtype(display_df['review_date']):
        display_df['review_date'] = display_df['review_date'].dt.strftime('%Y-%m-%d %H:%M')
    
    # Platform mapping
    plat_map = {
        'app_store': '🍎 iOS',
        'google_play': '🤖 Android'
    }
    display_df['source_platform'] = display_df['source_platform'].map(plat_map).fillna(display_df['source_platform'])
    
    # Severity Emoji Mapping
    sev_map = {
        'Critical': '🔴 Critical',
        'Major': '🟡 Major',
        'Minor': '🟢 Minor'
    }
    display_df['impact_severity'] = display_df['impact_severity'].map(sev_map).fillna(display_df['impact_severity'])
    
    # Column definitions and ordering
    cols_def = L_dict["cols"]
    
    available_cols_keys = [k for k in cols_def.keys() if k in display_df.columns]
    display_df = display_df[available_cols_keys].rename(columns=cols_def)
    
    # --- Data Privacy / PII Masking ---
    def mask_pii(text):
        if not isinstance(text, str):
            return text
        # 屏蔽邮箱
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***', text)
        # 屏蔽疑似手机号 (匹配连续 8 位及以上的数字)
        text = re.sub(r'\+?\d{8,15}', '+***-****-****', text)
        return text

    if L_dict["cols"]['content'] in display_df.columns:
        display_df[L_dict["cols"]['content']] = display_df[L_dict["cols"]['content']].apply(mask_pii)
    
    # DataFrame Interactive Rendering
    st.dataframe(
        display_df.head(500),
        use_container_width=True,
        hide_index=True,
        height=500
    )

# ═══════════════════════════════════════════════════════════
# REGIONAL VARIANCE ENGINE (Sprint 5)
# ═══════════════════════════════════════════════════════════

# ISO-2 → ISO-3 for Plotly Choropleth + bilingual country names
COUNTRY_META = {
    "DE": {"iso3": "DEU", "zh": "德国 (Germany)", "en": "Germany"},
    "IT": {"iso3": "ITA", "zh": "意大利 (Italy)", "en": "Italy"},
    "ES": {"iso3": "ESP", "zh": "西班牙 (Spain)", "en": "Spain"},
    "RO": {"iso3": "ROU", "zh": "罗马尼亚 (Romania)", "en": "Romania"},
    "AT": {"iso3": "AUT", "zh": "奥地利 (Austria)", "en": "Austria"},
    "CH": {"iso3": "CHE", "zh": "瑞士 (Switzerland)", "en": "Switzerland"},
    "PL": {"iso3": "POL", "zh": "波兰 (Poland)", "en": "Poland"},
}

MIN_SAMPLE = 5  # N≥5 guardrail


def compute_regional_variance(df: pd.DataFrame, brand: str) -> pd.DataFrame:
    """
    For a given brand, compute per-country weighted sentiment and its
    deviation from the global weighted baseline.
    Returns a DataFrame with columns:
        region_iso, country_name, iso3, N, S_country, S_global, delta_S, top_tag
    Rows with N < MIN_SAMPLE are included but flagged.
    """
    brand_df = df[df["app_name"] == brand].copy()
    if brand_df.empty:
        return pd.DataFrame()

    brand_df["weight"] = brand_df["impact_severity"].apply(get_severity_weight)
    brand_df["weighted_score"] = brand_df["sentiment_score"] * brand_df["weight"]

    # Global weighted baseline
    total_w = brand_df["weight"].sum()
    S_global = brand_df["weighted_score"].sum() / total_w if total_w > 0 else 0.0

    # Per-country aggregation
    records = []
    lang = st.session_state.get("lang", "zh")
    for region, grp in brand_df.groupby("region_iso"):
        n = len(grp)
        w_sum = grp["weight"].sum()
        s_country = grp["weighted_score"].sum() / w_sum if w_sum > 0 else 0.0
        delta = s_country - S_global

        # Top root cause tag
        tags = grp[grp["root_cause_tag"].notna() & (grp["root_cause_tag"] != "N/A")]["root_cause_tag"]
        top_tag = tags.value_counts().index[0] if not tags.empty else "—"

        meta = COUNTRY_META.get(region, {"iso3": region, "zh": region, "en": region})
        records.append({
            "region_iso": region,
            "country_name": meta[lang],
            "iso3": meta["iso3"],
            "N": n,
            "S_country": round(s_country, 3),
            "S_global": round(S_global, 3),
            "delta_S": round(delta, 3),
            "top_tag": top_tag,
            "reliable": n >= MIN_SAMPLE,
        })

    return pd.DataFrame(records).sort_values("delta_S", ascending=True)


def render_regional_variance(df: pd.DataFrame, L_dict: dict):
    """Render the full Regional Variance module with 3 visual components."""
    st.markdown(L_dict["rv_title"])
    st.info(L_dict["rv_desc"])

    # Methodology expander
    with st.expander(L_dict["rv_methodology_title"]):
        st.markdown(L_dict["rv_methodology"])

    # Brand selector
    brands = sorted(df["app_name"].unique())
    st.markdown(f"**{L_dict['rv_brand_select']}**")
    selected_brand = st.selectbox(
        L_dict["rv_brand_select"], brands,
        label_visibility="collapsed"
    )

    rv_df = compute_regional_variance(df, selected_brand)

    if rv_df.empty or rv_df[rv_df["reliable"]].empty:
        st.warning(L_dict["rv_no_data"])
        return

    # ── Row: Choropleth Map (left) + Root Cause Deep Dive (right) ──
    reliable_df = rv_df[rv_df["reliable"]].copy()
    col_map, col_drill = st.columns([6, 4])

    with col_map:
        st.markdown(f"#### {L_dict['rv_map_title']}")
        fig_map = px.choropleth(
            reliable_df,
            locations="iso3",
            color="delta_S",
            hover_name="country_name",
            hover_data={
                "N": True,
                "delta_S": ":.3f",
                "top_tag": True,
                "iso3": False,
            },
            color_continuous_scale=["#EF4444", "#FCD34D", "#10B981"],
            color_continuous_midpoint=0.0,
            scope="europe",
            labels={
                "delta_S": L_dict["rv_delta_label"],
                "N": L_dict["rv_map_hover_n"],
                "top_tag": L_dict["rv_map_hover_tag"],
            },
        )
        fig_map.update_layout(
            geo=dict(
                showframe=False,
                showcoastlines=True,
                projection_type="natural earth",
                bgcolor="rgba(0,0,0,0)",
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
            height=420,
            coloraxis_colorbar=dict(title=L_dict["rv_delta_label"]),
        )
        st.plotly_chart(fig_map, use_container_width=True)

    with col_drill:
        st.markdown(f"#### {L_dict['rv_drilldown_title']}")
        country_options = reliable_df["country_name"].tolist()
        st.markdown(f"**{L_dict['rv_drilldown_select']}**")
        selected_country_name = st.selectbox(
            L_dict["rv_drilldown_select"],
            country_options,
            label_visibility="collapsed",
        )

        # Reverse-map country_name back to region_iso
        selected_iso = reliable_df[reliable_df["country_name"] == selected_country_name]["region_iso"].iloc[0]
        country_df = df[(df["app_name"] == selected_brand) & (df["region_iso"] == selected_iso)].copy()
        country_df = country_df[country_df["root_cause_tag"].notna() & (country_df["root_cause_tag"] != "N/A")]

        if country_df.empty:
            st.info(L_dict["rv_no_data"])
        else:
            tag_counts = country_df["root_cause_tag"].value_counts().head(8).reset_index()
            tag_counts.columns = ["Root Cause", "Count"]

            fig_tags = px.bar(
                tag_counts,
                x="Count",
                y="Root Cause",
                orientation="h",
                color="Count",
                color_continuous_scale=["#93C5FD", "#1E3A8A"],
                labels={"Root Cause": "Root Cause Tag", "Count": "Count"},
                height=350,
            )
            fig_tags.update_layout(
                template="plotly_white",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                showlegend=False,
                yaxis=dict(autorange="reversed"),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_tags, use_container_width=True)

    # ── Component B: Regional Leaderboard ────────────────
    st.markdown(f"#### {L_dict['rv_leaderboard_title']}")

    col_best, col_worst = st.columns(2)
    with col_best:
        st.markdown(f"**{L_dict['rv_leaderboard_best']}**")
        top3 = reliable_df.sort_values("delta_S", ascending=False).head(3)
        for _, row in top3.iterrows():
            st.metric(
                label=row["country_name"],
                value=f"{row['delta_S']:+.3f}",
                delta=f"N={row['N']}",
            )

    with col_worst:
        st.markdown(f"**{L_dict['rv_leaderboard_worst']}**")
        bottom3 = reliable_df.sort_values("delta_S", ascending=True).head(3)
        for _, row in bottom3.iterrows():
            st.metric(
                label=row["country_name"],
                value=f"{row['delta_S']:+.3f}",
                delta=f"N={row['N']}",
                delta_color="inverse",
            )


# ═══════════════════════════════════════════════════════════
# PLATFORM DELTA ENGINE (Sprint 5.2)
# ═══════════════════════════════════════════════════════════

PLATFORM_LABELS = {"app_store": "iOS", "google_play": "Android"}


def compute_platform_delta(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each brand, compute severity-weighted sentiment per platform
    and the iOS-vs-Android delta.
    Returns DataFrame: app_name, S_ios, S_android, N_ios, N_android, delta_S, eligible
    """
    records = []
    for brand, grp in df.groupby("app_name"):
        row = {"app_name": brand}
        eligible = True
        for plat, plat_label in [("app_store", "ios"), ("google_play", "android")]:
            sub = grp[grp["source_platform"] == plat]
            n = len(sub)
            row[f"N_{plat_label}"] = n
            if n < MIN_SAMPLE:
                row[f"S_{plat_label}"] = None
                eligible = False
            else:
                weights = sub["impact_severity"].apply(get_severity_weight)
                w_sum = weights.sum()
                row[f"S_{plat_label}"] = round(
                    (sub["sentiment_score"] * weights).sum() / w_sum, 3
                ) if w_sum > 0 else 0.0
        if eligible:
            row["delta_S"] = round(row["S_ios"] - row["S_android"], 3)
        else:
            row["delta_S"] = None
        row["eligible"] = eligible
        records.append(row)
    return pd.DataFrame(records)


def render_platform_delta(df: pd.DataFrame, L_dict: dict):
    """Render the Platform Delta module: Tornado Chart + Root Cause Matrix."""
    st.markdown(L_dict["pd_title"])
    st.info(L_dict["pd_desc"])

    pd_df = compute_platform_delta(df)
    eligible_df = pd_df[pd_df["eligible"]].copy()
    excluded_df = pd_df[~pd_df["eligible"]].copy()

    # Show excluded brands warning
    if not excluded_df.empty:
        excluded_names = ", ".join(excluded_df["app_name"].tolist())
        st.warning(f"{L_dict['pd_excluded']} **{excluded_names}**")

    if eligible_df.empty:
        st.warning(L_dict["pd_no_data"])
        return

    # Sort by delta for visual impact
    eligible_df = eligible_df.sort_values("delta_S", ascending=True)

    # ── Row: Tornado Chart (left) + Root Cause Matrix (right) ──
    col_tornado, col_roots = st.columns([6, 4])

    with col_tornado:
        st.markdown(f"#### {L_dict['pd_tornado_title']}")

        fig = go.Figure()
        # Android bars (extend left = negative x)
        fig.add_trace(go.Bar(
            y=eligible_df["app_name"],
            x=eligible_df["S_android"],
            name=L_dict["pd_android"],
            orientation="h",
            marker_color="#3DDC84",
            customdata=eligible_df["N_android"],
            hovertemplate="%{y}<br>Score: %{x:.3f}<br>N=%{customdata}<extra></extra>",
        ))
        # iOS bars (extend right = positive x)
        fig.add_trace(go.Bar(
            y=eligible_df["app_name"],
            x=eligible_df["S_ios"],
            name=L_dict["pd_ios"],
            orientation="h",
            marker_color="#007AFF",
            customdata=eligible_df["N_ios"],
            hovertemplate="%{y}<br>Score: %{x:.3f}<br>N=%{customdata}<extra></extra>",
        ))
        fig.update_layout(
            barmode="group",
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
            height=max(250, len(eligible_df) * 70),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            xaxis_title="Severity-Weighted Score",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_roots:
        st.markdown(f"#### {L_dict['pd_rootcause_title']}")
        brand_options = eligible_df["app_name"].tolist()
        st.markdown(f"**{L_dict['pd_rootcause_select']}**")
        selected_brand = st.selectbox(
            L_dict["pd_rootcause_select"],
            brand_options,
            label_visibility="collapsed",
            key="pd_brand_select",
        )

        brand_data = df[df["app_name"] == selected_brand].copy()
        brand_data = brand_data[brand_data["root_cause_tag"].notna() & (brand_data["root_cause_tag"] != "N/A")]

        col_a, col_i = st.columns(2)
        with col_a:
            st.markdown(f"**{L_dict['pd_android']}** — {L_dict['pd_top_issues']}")
            android_tags = brand_data[brand_data["source_platform"] == "google_play"]["root_cause_tag"]
            if not android_tags.empty:
                for i, (tag, cnt) in enumerate(android_tags.value_counts().head(3).items()):
                    st.markdown(f"{i+1}. `{tag}` ({cnt})")
            else:
                st.caption("—")

        with col_i:
            st.markdown(f"**{L_dict['pd_ios']}** — {L_dict['pd_top_issues']}")
            ios_tags = brand_data[brand_data["source_platform"] == "app_store"]["root_cause_tag"]
            if not ios_tags.empty:
                for i, (tag, cnt) in enumerate(ios_tags.value_counts().head(3).items()):
                    st.markdown(f"{i+1}. `{tag}` ({cnt})")
            else:
                st.caption("—")

    # ── Insight threshold badges (full width, below both panels) ──
    #st.markdown("---")
    for _, row in eligible_df.iterrows():
        delta = abs(row["delta_S"])
        label = f"**{row['app_name']}**: ΔS = {row['delta_S']:+.3f}"
        if delta < 0.1:
            st.success(f"{label} — {L_dict['pd_balanced']}")
        elif delta > 0.2:
            st.error(f"{label} — {L_dict['pd_bias']}")
        else:
            st.info(f"{label}")


# ═══════════════════════════════════════════════════════════
# MAIN APP EXECUTION
# ═══════════════════════════════════════════════════════════

def main():
    inject_custom_css()

    df = load_data()
    page_name, filtered_df, L_dict = render_sidebar(df)
    
    is_deep_insights = (page_name == LANGS["zh"]["nav_options"][1] or page_name == LANGS["en"]["nav_options"][1])
    
    if is_deep_insights:
        # ── Module 1: Regional Variance (LIVE) ──────────
        render_regional_variance(filtered_df, L_dict)

        st.markdown("---")

        # ── Module 2: Platform Delta (LIVE) ─────────────
        render_platform_delta(filtered_df, L_dict)

        st.markdown("---")

        # ── Remaining Modules (Placeholder) ─────────────
        st.markdown(L_dict["deep_insights_title"])
        st.info(L_dict["deep_insights_desc"])
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(L_dict["deep_insights_item3"])
        with col2:
            st.markdown(L_dict["deep_insights_item4"])
            
        st.markdown("---")
        st.warning(L_dict["beta_warning"])
        
    else:
        # Render the existing Dashboard (Quality Benchmark)
        if filtered_df is None or filtered_df.empty:
            st.warning(L_dict["warning_no_data"])
            return

        vers_df = compute_endogenous_versions(filtered_df)
        
        if vers_df.empty:
            st.warning(L_dict["warning_no_baseline"])
            return

        # Data DNA Preamble
        st.markdown(L_dict["dna_title"])
        st.markdown(L_dict["dna_desc"])
        
        # --- 子部分 1 ---
        with st.expander(L_dict["dna_exp1_title"]):
            st.write(L_dict["dna_exp1_text"])
        
        # --- 子部分 2 ---
        with st.expander(L_dict["dna_exp2_title"]):
            st.write(L_dict["dna_exp2_text"])
        
        # --- 子部分 3 ---
        with st.expander(L_dict["dna_exp3_title"]):
            st.latex(r"S_{weighted} = \frac{\sum (Sentiment\_Score_i \times W_i)}{\sum W_i}")
            st.write(L_dict["dna_exp3_text"])
        
        st.markdown("<br>", unsafe_allow_html=True)
    
        # Top Level
        render_kpis(filtered_df, vers_df, L_dict)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Middle Level (1-2-1 Flow)
        colA, colB = st.columns([1, 1])
        with colA:
            render_module_a(vers_df, L_dict)
        with colB:
            render_module_b(filtered_df, vers_df, L_dict)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Bottom Level
        render_module_c(vers_df, L_dict)
        
        # Data Drilldown Level
        render_module_d(filtered_df, L_dict)
    

if __name__ == "__main__":
    main()
