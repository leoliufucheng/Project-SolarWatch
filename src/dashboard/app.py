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
        "nav_title": "### 🧭 导航 (Navigation)",
        "nav_options": ["版本质量基准 (Quality Benchmark)", "深度洞察 (Deep Insights)"],
        "time_window": "### ⏳ Time Window",
        "quick_select": "Quick Select",
        "app_filter": "🏢 App Filter",
        "motivation_title": "### 🎯 项目初衷 (Motivation)",
        "motivation_text": "**SolarWatch** 利用 Gemini 2.5 Flash 语义能力，将数千条混沌语料转化为可量化的对标刻度，旨在揭示厂商在数字化转型中的真实研发响应速度。",
        "compliance_title": "### ⚖️ 合规声明 (Compliance Disclaimer)**：",
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
        "mod_b_no_tags": "这些版本内没有被标记的具体痛点 (root_cause_tag)。"
    },
    "en": {
        "nav_title": "### 🧭 Navigation",
        "nav_options": ["Quality Benchmark", "Deep Insights"],
        "time_window": "### ⏳ Time Window",
        "quick_select": "Quick Select",
        "app_filter": "🏢 App Filter",
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
        "mod_b_no_tags": "No specific root_cause_tag identified in these versions."
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
    
    # Language Switcher
    lang_sel = st.sidebar.radio("🌐 Language", ["中文", "English"], horizontal=True)
    st.session_state.lang = "en" if lang_sel == "English" else "zh"
    L_dict = LANGS[st.session_state.lang]

    # Navigation Selector
    st.sidebar.markdown(L_dict["nav_title"])
    page_selection = st.sidebar.radio(
        "选择分析模块",
        L_dict["nav_options"],
        label_visibility="collapsed"
    )
    st.sidebar.markdown("---")

    filtered = df.copy()

    # Only show filters if on the Benchmark page
    is_benchmark = (page_selection == LANGS["zh"]["nav_options"][0] or page_selection == LANGS["en"]["nav_options"][0])
    
    if is_benchmark:
        st.sidebar.markdown(L_dict["time_window"])
        time_preset = st.sidebar.selectbox(
            L_dict["quick_select"],
            ["All (180 days)", "Last 90 days", "Last 30 days", "Custom"],
            index=0,
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
        apps = sorted(df["app_name"].unique())
        selected_apps = st.sidebar.multiselect(L_dict["app_filter"], apps, default=apps)
        filtered = filtered[filtered["app_name"].isin(selected_apps)]
    else:
        filtered = None # Deep Insights doesn't need filters yet

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
# MAIN APP EXECUTION
# ═══════════════════════════════════════════════════════════

def main():
    inject_custom_css()

    df = load_data()
    page_name, filtered_df, L_dict = render_sidebar(df)
    
    is_deep_insights = (page_name == LANGS["zh"]["nav_options"][1] or page_name == LANGS["en"]["nav_options"][1])
    
    if is_deep_insights:
        # Render the Advanced Insights Placeholder Page
        st.markdown(L_dict["deep_insights_title"])
        st.info(L_dict["deep_insights_desc"])
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            ### 📍 区域体感差异 (Regional Variance)
            - 探索同一版本在德国、意大利、英国等不同电网环境下的表现差异，识别本地化适配痛点。
            
            ### 📱 平台性能鸿沟 (Platform Delta)
            - **iOS vs Android 深度对标**：分析同一品牌在不同系统架构下的研发资源倾斜与稳定性差异。
            """)
            
        with col2:
            st.markdown("""
            ### 💎 需求挖掘机 (Feature Request Mining)
            - 利用 AI 对用户建议进行聚类分析，识别光伏用户最渴望的“杀手级”功能趋势。
            
            ### ⏱️ 修复时延分析 (Bug Fix Lead Time)
            - 追踪核心 Bug 从首次曝光到彻底修复的平均生命周期，量化各厂家的敏捷开发效能。
            """)
            
        st.markdown("---")
        st.warning(L_dict["beta_warning"])
        
    else:
        # Render the existing Dashboard (Quality Benchmark)
        if filtered_df is None or filtered_df.empty:
            st.warning("⚠️ 没有查找到任何有效分析数据，请调宽时间窗口。")
            return

        vers_df = compute_endogenous_versions(filtered_df)
        
        if vers_df.empty:
            st.warning("⚠️ 未能探测到拥有连续样本 ($N \ge 5$) 的有效版本基线。")
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
