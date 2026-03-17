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
    
    # Navigation Selector
    st.sidebar.markdown("### 🧭 导航 (Navigation)")
    page_selection = st.sidebar.radio(
        "选择分析模块",
        ["📊 版本质量基准 (Quality Benchmark)", "🧠 深度洞察 (Deep Insights)"],
        label_visibility="collapsed"
    )
    st.sidebar.markdown("---")

    filtered = df.copy()

    # Only show filters if on the Benchmark page
    if "Quality Benchmark" in page_selection:
        st.sidebar.markdown("### ⏳ Time Window")
        time_preset = st.sidebar.selectbox(
            "Quick Select",
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
        selected_apps = st.sidebar.multiselect("🏢 App Filter", apps, default=apps)
        filtered = filtered[filtered["app_name"].isin(selected_apps)]
        filtered = None # Deep Insights doesn't need filters yet

    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    ### 🎯 项目初衷 (Motivation) 
    **SolarWatch** 利用 Gemini 2.5 Flash 语义能力，将数千条混沌语料转化为可量化的对标刻度，旨在揭示厂商在数字化转型中的真实研发响应速度。
    
    """)
    
    st.sidebar.info("""
    **⚖️ 合规声明 (Compliance Disclaimer)**：
    本看板所展示数据均为应用商店（App Store & Google Play）公开评论。系统已通过 AI 自动脱敏技术屏蔽潜在的个人隐私信息（PII）。分析结论仅供行业研究参考，不代表品牌官方立场。
    """)

    return page_selection, filtered

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

def render_kpis(df: pd.DataFrame, vers_df: pd.DataFrame):
    if df.empty or vers_df.empty:
        return
        
    ios_count = len(df[df['source_platform'] == 'app_store'])
    android_count = len(df[df['source_platform'] == 'google_play'])
    
    avg_active_days = vers_df['Active Days'].mean()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("iOS 分析样本量", f"{ios_count:,}")
    col2.metric("Android 分析样本量（缺失Huawei FusionSolar）", f"{android_count:,}")
    col3.metric("平均版本活跃周期", f"{avg_active_days:.1f} 天")


def render_module_a(vers_df: pd.DataFrame):
    """Module A: Weighted Health Leaderboard (Top 3 per app)"""
    st.subheader("🏆 软件质量红黑榜：谁在定义行业标杆？")
    st.info(
    "* **标杆效应：** 榜单顶部通常由长期维持在 **$S_{weighted}$ > 0.1** 分值的品牌占据，这表明其软件迭代已进入“正向口碑循环”。\n"
    "* **风险阈值：** 处于红色区域底部（$S_{weighted}$ <-0.5）的版本通常伴随着 **Critical (致命阻断)** 问题的集中爆发。若某品牌连续三个版本处于该区间，往往预示着该品牌正在经历大规模的底层架构调整或严重的交付质量危机。\n\n"
    )
    
    
    if vers_df.empty:
        st.info("无满足条件的发版记录。")
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

def render_module_b(df: pd.DataFrame, vers_df: pd.DataFrame):
    """Module B: 4-Version Drift Analysis"""
    st.subheader("🧬 病灶演进：最近四个版本，他们在修 Bug 还是制造 Bug？")
    st.info("📊 **洞察提示**：如果某类 Critical 级别的痛点在连续四个版本中占比均未下降，通常意味着该问题已从“偶发 Bug”演变为“架构性顽疾”，建议作为季度核心技术攻坚目标。")
    
    if vers_df.empty:
        return
        
    apps = sorted(vers_df['app_name'].unique())
    selected_app = st.selectbox("选择目标品牌进行深潜 (Deep Dive):", apps)
    
    app_vers = vers_df[vers_df['app_name'] == selected_app].sort_values(by='T_max', ascending=False)
    latest_4 = app_vers.head(4)['version'].tolist()
    
    if not latest_4:
        st.info("该品牌版本数据不足。")
        return
        
    st.markdown(f"追踪 **{selected_app}** 最近的 4 个活跃版本: `{', '.join(latest_4)}`")
    
    # Filter raw reviews to these 4 versions
    drift_df = df[(df['app_name'] == selected_app) & (df['version'].isin(latest_4))].copy()
    drift_df = drift_df[(drift_df['root_cause_tag'].notna()) & (drift_df['root_cause_tag'] != 'N/A')]
    
    if drift_df.empty:
        st.info("这些版本内没有被标记的具体痛点 (root_cause_tag)。")
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
        labels={"root_cause_tag": "核心痛点", "count": "曝出频次", "version": "版本代号"},
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
    
   

def render_module_c(vers_df: pd.DataFrame):
    """Module C: Iteration Cadence Timeline"""
    st.subheader("📈 迭代脉搏：谁在快速响应欧洲市场？")
    
    st.info(
        "**图例洞察**：横坐标为时间线，色块跨度代表版本的市场存活期。**色块深浅映射 $S_{weighted}$**：深红 = 口碑崩塌，深绿 = 质量稳健。\n"
        "发版密度高（色块紧凑）且颜色翠绿，代表该品牌在数字战场上的敏捷修复与作战能力处于统治地位。"
    )
    
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
        labels={"app_name": "品牌阵营"}
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


def render_module_d(df: pd.DataFrame):
    """Module D: Data Detail Explorer (Real-time Raw Data Drill-down)"""
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🔍 数据穿透探索器：原始评论与 AI 诊断明细")
    
    # 📖 字段定义与解读指南
    with st.expander("📖 字段定义与解读指南 (Field Definition Guide)", expanded=False):
        st.markdown("""
- **App 名称**：品牌标准名称。
- **平台**：数据的抓取渠道（🍎 iOS 或 🤖 Android）。
- **版本**：用户评论时对应的软件版本号。
- **日期**：评论提交的原始时间（UTC）。
- **严重程度**：🔴 Critical (致命) / 🟡 Major (严重) / 🟢 Minor (轻微)。
- **AI 核心诊断**：Gemini 解析出的核心痛点标签。
- **用户原声**：用户提交的原始多语言文本。
- **AI 证据提取**：AI 从原文中逐字摘录的判定依据，确保分析可回溯。
- **个体情感分**：量化评分（-1.0 至 1.0）。
        """)
    
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
    cols_def = {
        'app_name': 'App 名称',
        'source_platform': '平台',
        'version': '版本',
        'review_date': '日期',
        'impact_severity': '严重程度',
        'root_cause_tag': 'AI 核心诊断',
        'content': '用户原声',
        'evidence_quote': 'AI 证据提取',
        'sentiment_score': '个体情感分'
    }
    
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

    if '用户原声' in display_df.columns:
        display_df['用户原声'] = display_df['用户原声'].apply(mask_pii)
    
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
    page_name, filtered_df = render_sidebar(df)
    
    if "Deep Insights" in page_name:
        # Render the Advanced Insights Placeholder Page
        st.markdown("## 🧠 深度洞察 (Advanced Insights) — Coming Soon")
        st.info("本模块旨在通过更细颗粒度的维度，解码品牌背后的核心竞争力。")
        
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
        st.warning("🚀 目前这些功能处于 Beta 内部测试阶段。")
        
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
        st.markdown("### 🧬 数据基因 (Data DNA)：多维语义解析与量化标准")
        st.markdown("""
        SolarWatch 系统的分析基础源于对海量非结构化文本的量化处理。
        每一条原始评论均经过 **Gemini 2.5 Flash** 的深度语义解析，提取出以下核心维度：
        """)
        
        # --- 子部分 1 ---
        with st.expander("1. 个体情感分 (Sentiment_Score)"):
            st.write("""
            是对单条评论文本的语境、语气及情绪强度进行的定量分析。Gemini 将主观描述转化为 **-1.0 至 1.0** 之间的连续数值：
            - **1.0 (极度正面)**：表示用户对产品表现出极高的满意度与品牌忠诚度。
            - **0.0 (中性)**：表示评论仅包含事实陈述，不具备明显的情绪倾向。
            - **-1.0 (极度负面)**：表示用户对产品体验表现出极度的不满或业务遭受了实质性损失。
        
            **分析样例：**
            - 样例 1: *"App crashing every time I open settings."* → **-0.85**
            - 样例 2: *"Installation was smooth, highly recommend."* → **+0.92**
            """)
        
        # --- 子部分 2 ---
        with st.expander("2. 业务影响等级 (Severity Categories)"):
            st.write("""
            评论描述的问题对用户业务运营的影响程度，Gemini将评论分为Critical，Major，Minor三个等级：
            - 🔴 **Critical (致命)**：核心业务流程中断。如：无法登录、App 持续崩溃、或电站实时监控数据丢失。
            - 🟡 **Major (严重)**：核心功能受损或体验显著下降。如：数据刷新严重延迟、复杂的配网逻辑错误、或核心交互功能失效。
            - 🟢 **Minor (轻微)**：非核心功能的优化建议。如：界面语言翻译误差、UI 审美偏好、或辅助性的功能改进提议。
        """)
        
        # --- 子部分 3 ---
        with st.expander("3. 惩罚性加权健康分算法 (Severity-Weighted Scoring)"):
            st.latex(r"S_{weighted} = \frac{\sum (Sentiment\_Score_i \times W_i)}{\sum W_i}")
            st.write("""
            **权重矩阵 ($W_i$) 定义：**
            为区分不同严重程度问题的负面影响，系统设定了权重系数：
            - **Critical = 5**：致命问题的权重是基准权重的 5 倍。
            - **Major = 2**：严重缺陷的权重是基准权重的 2 倍。
            - **Minor = 1**：轻微建议按基准权重计算。
    
            **逻辑解释：**
            - **加权求和 ($\sum (S_i \times W_i)$)**：通过权重放大 Critical 负评的影响。确保少数致命 Bug 不会被海量轻微好评所掩盖。
            - **归一化处理 ($\sum W_i$)**：将结果映射回 -1.0 至 1.0 标准区间，消除不同品牌、不同版本之间评论样本量差异带来的统计偏见，确保品牌间公平对标。
    
            **分析结论导向：**
            当得分 < **-0.15** 时，代表“致命 Bug”的伤害已超过正面收益，研发团队需立即介入。
            *注：系统将 -0.15 设定为行业健康基准线，以对冲公开市场的负向反馈偏见。（即满意用户评价动机低于不满意用户）*
            """)
        
        st.markdown("<br>", unsafe_allow_html=True)
    
        # Top Level
        render_kpis(filtered_df, vers_df)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Middle Level (1-2-1 Flow)
        colA, colB = st.columns([1, 1])
        with colA:
            render_module_a(vers_df)
        with colB:
            render_module_b(filtered_df, vers_df)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Bottom Level
        render_module_c(vers_df)
        
        # Data Drilldown Level
        render_module_d(filtered_df)
    

if __name__ == "__main__":
    main()
