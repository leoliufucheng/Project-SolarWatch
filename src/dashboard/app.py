"""
SolarWatch Executive Dashboard
================================
Sprint 4: Interactive competitive intelligence radar.

Run: streamlit run src/dashboard/app.py
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─── Page config (must be first) ──────────────────────────
st.set_page_config(
    page_title="SolarWatch CI Radar",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Paths ────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "solarwatch.db"

# ─── Premium Color Palette ────────────────────────────────
COLORS = {
    "bg_dark": "#0E1117",
    "card_bg": "#1E2130",
    "accent": "#F7B731",
    "positive": "#2ECC71",
    "negative": "#E74C3C",
    "neutral": "#95A5A6",
    "text": "#ECF0F1",
    "blue": "#3498DB",
    "purple": "#9B59B6",
}

APP_COLORS = {
    "Huawei FusionSolar": "#E74C3C",
    "Sungrow iSolarCloud": "#E67E22",
    "SMA Energy": "#3498DB",
    "Fronius Solar.web": "#2ECC71",
    "SolarEdge": "#9B59B6",
    "Enphase Enlighten": "#1ABC9C",
}

SEVERITY_COLORS = {
    "Critical": "#E74C3C",
    "Major": "#F39C12",
    "Minor": "#27AE60",
}

CATEGORY_COLORS = {
    "O&M": "#3498DB",
    "DevOps": "#E74C3C",
    "Ecosystem": "#2ECC71",
    "Localization": "#F39C12",
    "Commissioning": "#9B59B6",
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
            rr.source_platform,
            rr.region_iso,
            rr.rating,
            rr.version,
            rr.review_date,
            rr.review_language,
            rr.content,
            pr.primary_category,
            pr.user_persona,
            pr.impact_severity,
            pr.is_sarcasm,
            pr.evidence_quote,
            pr.sentiment_score,
            pr.root_cause_tag,
            pr.hallucination_check_passed
        FROM processed_reviews pr
        JOIN raw_reviews rr ON pr.raw_id = rr.review_id
        WHERE pr.hallucination_check_passed = 1
          AND pr.primary_category IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df["review_date"] = pd.to_datetime(df["review_date"])
    df["date"] = df["review_date"].dt.date
    df["week"] = df["review_date"].dt.to_period("W").apply(lambda r: r.start_time)
    df["month"] = df["review_date"].dt.to_period("M").apply(lambda r: r.start_time)
    return df


# ═══════════════════════════════════════════════════════════
# SIDEBAR (Control Center)
# ═══════════════════════════════════════════════════════════

def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    """Render sidebar filters and return filtered DataFrame."""
    st.sidebar.markdown(
        "<h1 style='text-align:center;'>☀️ SolarWatch<br>CI Radar</h1>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")

    # Platform mode
    platform_mode = st.sidebar.radio(
        "🔬 Platform Mode",
        ["🌍 Global Blended (全部)", "🍏 Apple-to-Apples (仅 iOS)"],
        index=0,
    )

    filtered = df.copy()
    if "Apple" in platform_mode:
        filtered = filtered[filtered["source_platform"] == "app_store"]

    # Time slider
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⏳ Time Window")
    time_preset = st.sidebar.selectbox(
        "Quick Select",
        ["All (180 days)", "Last 90 days", "Last 30 days", "Custom"],
        index=0,
    )

    if filtered.empty:
        return filtered

    min_date = filtered["review_date"].min().date()
    max_date = filtered["review_date"].max().date()

    if time_preset == "Last 90 days":
        start = max_date - timedelta(days=90)
        end = max_date
    elif time_preset == "Last 30 days":
        start = max_date - timedelta(days=30)
        end = max_date
    elif time_preset == "Custom":
        start, end = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
    else:
        start, end = min_date, max_date

    filtered = filtered[
        (filtered["review_date"].dt.date >= start)
        & (filtered["review_date"].dt.date <= end)
    ]

    # App filter
    st.sidebar.markdown("---")
    apps = sorted(df["app_name"].unique())
    selected_apps = st.sidebar.multiselect(
        "🏢 App Filter",
        apps,
        default=apps,
    )
    filtered = filtered[filtered["app_name"].isin(selected_apps)]

    # Persona filter
    st.sidebar.markdown("---")
    persona_mode = st.sidebar.radio(
        "👤 Persona",
        ["All", "👷 Installers Only", "🏠 Homeowners Only"],
        index=0,
    )
    if "Installer" in persona_mode:
        filtered = filtered[filtered["user_persona"] == "Installer"]
    elif "Homeowner" in persona_mode:
        filtered = filtered[filtered["user_persona"] == "Homeowner"]

    # Stats
    st.sidebar.markdown("---")
    st.sidebar.metric("Filtered Reviews", f"{len(filtered):,}")
    is_ios_only = "Apple" in platform_mode
    st.sidebar.caption(
        "🍏 iOS Only" if is_ios_only else "🌍 Global (All Platforms)"
    )

    return filtered


# ═══════════════════════════════════════════════════════════
# TAB 1: Macro & Trends
# ═══════════════════════════════════════════════════════════

def render_tab_macro(df: pd.DataFrame, is_ios_only: bool):
    """Tab 1: macro KPIs + brand sentiment comparison + time trends."""

    # ── KPI Row ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Total Reviews", f"{len(df):,}")
    with col2:
        avg_sentiment = df["sentiment_score"].mean() if not df.empty else 0
        emoji = "🟢" if avg_sentiment > 0 else "🔴"
        st.metric(f"{emoji} Avg Sentiment", f"{avg_sentiment:+.2f}")
    with col3:
        critical_count = len(df[df["impact_severity"].isin(["Major", "Critical"])])
        st.metric("🚨 Critical+Major", f"{critical_count:,}")
    with col4:
        installer_count = len(df[df["user_persona"] == "Installer"])
        st.metric("👷 Installers", f"{installer_count}")

    st.markdown("---")

    # ── Brand Sentiment Bar Chart ──
    st.subheader("📊 Brand Sentiment Comparison")

    if not is_ios_only:
        huawei_mask = df["app_name"] == "Huawei FusionSolar"
        if huawei_mask.any():
            huawei_platforms = df.loc[huawei_mask, "source_platform"].unique()
            if len(huawei_platforms) == 1 and "app_store" in huawei_platforms:
                st.warning(
                    "⚠️ **Huawei FusionSolar** 仅有 iOS 数据！"
                    "在 Global Blended 模式下可能造成比较偏差。"
                    "建议切换到 🍏 Apple-to-Apples 模式进行公平对比。"
                )

    if not df.empty:
        brand_stats = (
            df.groupby("app_name")
            .agg(
                avg_sentiment=("sentiment_score", "mean"),
                avg_rating=("rating", "mean"),
                count=("review_id", "count"),
            )
            .reset_index()
            .sort_values("avg_sentiment")
        )
        color_map = {app: APP_COLORS.get(app, "#888") for app in brand_stats["app_name"]}

        fig_bar = px.bar(
            brand_stats,
            x="app_name",
            y="avg_sentiment",
            color="app_name",
            color_discrete_map=color_map,
            text=brand_stats["avg_sentiment"].apply(lambda v: f"{v:+.2f}"),
            labels={"app_name": "App", "avg_sentiment": "Avg Sentiment Score"},
            hover_data=["avg_rating", "count"],
        )
        fig_bar.update_layout(
            template="plotly_dark",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            xaxis_title="",
            yaxis_title="Avg Sentiment",
            yaxis=dict(range=[-1, 1], zeroline=True, zerolinecolor="#555"),
            height=400,
        )
        fig_bar.update_traces(textposition="outside")
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No data to display with current filters.")

    st.markdown("---")

    # ── Weekly Sentiment Trend Line ──
    st.subheader("📈 Weekly Sentiment Trend")

    if not df.empty:
        weekly = (
            df.groupby(["week", "app_name"])
            .agg(avg_sentiment=("sentiment_score", "mean"), count=("review_id", "count"))
            .reset_index()
        )
        weekly["week"] = pd.to_datetime(weekly["week"])

        fig_line = px.line(
            weekly,
            x="week",
            y="avg_sentiment",
            color="app_name",
            color_discrete_map=APP_COLORS,
            markers=True,
            labels={
                "week": "Week",
                "avg_sentiment": "Avg Sentiment",
                "app_name": "App",
            },
        )
        fig_line.update_layout(
            template="plotly_dark",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(range=[-1, 1], zeroline=True, zerolinecolor="#555"),
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        )
        fig_line.add_hline(y=0, line_dash="dash", line_color="#555", opacity=0.5)
        st.plotly_chart(fig_line, use_container_width=True)

    # ── Weekly Negative Review Count ──
    st.subheader("🔥 Weekly Negative Review Volume (Sentiment < 0)")

    if not df.empty:
        neg = df[df["sentiment_score"] < 0].copy()
        if not neg.empty:
            neg_weekly = (
                neg.groupby(["week", "app_name"])
                .size()
                .reset_index(name="negative_count")
            )
            neg_weekly["week"] = pd.to_datetime(neg_weekly["week"])

            fig_neg = px.bar(
                neg_weekly,
                x="week",
                y="negative_count",
                color="app_name",
                color_discrete_map=APP_COLORS,
                barmode="stack",
                labels={
                    "week": "Week",
                    "negative_count": "Negative Reviews",
                    "app_name": "App",
                },
            )
            fig_neg.update_layout(
                template="plotly_dark",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=400,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            )
            st.plotly_chart(fig_neg, use_container_width=True)
        else:
            st.info("No negative reviews in current filter.")


# ═══════════════════════════════════════════════════════════
# TAB 2: Pain Point Matrix
# ═══════════════════════════════════════════════════════════

def render_tab_painpoints(df: pd.DataFrame):
    """Tab 2: category donut + root cause bar chart."""

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("🗂️ Category Distribution")
        if not df.empty:
            cat_counts = df["primary_category"].value_counts().reset_index()
            cat_counts.columns = ["category", "count"]

            fig_donut = px.pie(
                cat_counts,
                values="count",
                names="category",
                color="category",
                color_discrete_map=CATEGORY_COLORS,
                hole=0.5,
            )
            fig_donut.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                height=450,
                legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
            )
            fig_donut.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_donut, use_container_width=True)

            # Category sentiment table
            cat_stats = (
                df.groupby("primary_category")
                .agg(
                    count=("review_id", "count"),
                    avg_sentiment=("sentiment_score", "mean"),
                    critical=("impact_severity", lambda x: (x == "Critical").sum()),
                    major=("impact_severity", lambda x: (x == "Major").sum()),
                )
                .reset_index()
                .sort_values("count", ascending=False)
            )
            cat_stats["avg_sentiment"] = cat_stats["avg_sentiment"].apply(lambda v: f"{v:+.2f}")
            st.dataframe(cat_stats, hide_index=True, use_container_width=True)
        else:
            st.info("No data.")

    with col_right:
        st.subheader("🔥 Top 10 Root Causes (Major + Critical)")

        if not df.empty:
            severe = df[
                (df["impact_severity"].isin(["Major", "Critical"]))
                & (df["root_cause_tag"].notna())
                & (df["root_cause_tag"] != "N/A")
                & (~df["root_cause_tag"].str.contains("N/A", na=False))
            ]

            if not severe.empty:
                root_counts = (
                    severe.groupby("root_cause_tag")
                    .agg(
                        count=("review_id", "count"),
                        avg_sentiment=("sentiment_score", "mean"),
                    )
                    .reset_index()
                    .sort_values("count", ascending=True)
                    .tail(10)
                )

                fig_root = px.bar(
                    root_counts,
                    x="count",
                    y="root_cause_tag",
                    orientation="h",
                    color="avg_sentiment",
                    color_continuous_scale=["#E74C3C", "#F39C12", "#27AE60"],
                    range_color=[-1, 0],
                    text="count",
                    labels={
                        "root_cause_tag": "Root Cause",
                        "count": "Occurrences",
                        "avg_sentiment": "Avg Sentiment",
                    },
                )
                fig_root.update_layout(
                    template="plotly_dark",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=500,
                    yaxis_title="",
                    coloraxis_colorbar=dict(title="Sentiment"),
                )
                fig_root.update_traces(textposition="outside")
                st.plotly_chart(fig_root, use_container_width=True)
            else:
                st.info("No Major/Critical root causes found with current filters.")

        # Severity breakdown
        st.subheader("⚡ Severity Breakdown by App")
        if not df.empty:
            sev_counts = (
                df.groupby(["app_name", "impact_severity"])
                .size()
                .reset_index(name="count")
            )
            fig_sev = px.bar(
                sev_counts,
                x="app_name",
                y="count",
                color="impact_severity",
                color_discrete_map=SEVERITY_COLORS,
                barmode="stack",
                labels={"app_name": "App", "count": "Reviews", "impact_severity": "Severity"},
            )
            fig_sev.update_layout(
                template="plotly_dark",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=400,
                xaxis_title="",
            )
            st.plotly_chart(fig_sev, use_container_width=True)


# ═══════════════════════════════════════════════════════════
# TAB 3: Evidence Court
# ═══════════════════════════════════════════════════════════

def render_tab_evidence(df: pd.DataFrame):
    """Tab 3: interactive filterable data table."""

    st.subheader("🔎 Evidence Browser")

    # Quick filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        severe_only = st.checkbox("🚨 Major/Critical Only", value=False)
    with col2:
        sarcasm_only = st.checkbox("🎭 Sarcasm Only", value=False)
    with col3:
        installer_only = st.checkbox("👷 Installers Only", value=False)
    with col4:
        search_text = st.text_input("🔍 Search text", "")

    filtered = df.copy()

    if severe_only:
        filtered = filtered[filtered["impact_severity"].isin(["Major", "Critical"])]
    if sarcasm_only:
        filtered = filtered[filtered["is_sarcasm"] == 1]
    if installer_only:
        filtered = filtered[filtered["user_persona"] == "Installer"]
    if search_text:
        mask = (
            filtered["content"].str.contains(search_text, case=False, na=False)
            | filtered["evidence_quote"].str.contains(search_text, case=False, na=False)
            | filtered["root_cause_tag"].str.contains(search_text, case=False, na=False)
        )
        filtered = mask_df if (mask_df := filtered[mask]) is not None else filtered

    st.caption(f"Showing {len(filtered):,} reviews")

    if not filtered.empty:
        display_cols = [
            "date",
            "app_name",
            "source_platform",
            "rating",
            "primary_category",
            "impact_severity",
            "user_persona",
            "is_sarcasm",
            "sentiment_score",
            "root_cause_tag",
            "evidence_quote",
            "content",
        ]
        display_df = filtered[display_cols].copy()
        display_df = display_df.sort_values("date", ascending=False)
        display_df["sentiment_score"] = display_df["sentiment_score"].apply(
            lambda v: f"{v:+.2f}" if pd.notna(v) else ""
        )
        display_df["is_sarcasm"] = display_df["is_sarcasm"].apply(
            lambda v: "🎭 Yes" if v else ""
        )

        display_df.columns = [
            "Date", "App", "Platform", "⭐", "Category", "Severity",
            "Persona", "Sarcasm", "Sentiment", "Root Cause", "Evidence Quote", "Full Text",
        ]

        st.dataframe(
            display_df,
            use_container_width=True,
            height=600,
            column_config={
                "Full Text": st.column_config.TextColumn(width="large"),
                "Evidence Quote": st.column_config.TextColumn(width="medium"),
            },
        )
    else:
        st.info("No reviews match current filters.")


# ═══════════════════════════════════════════════════════════
# CUSTOM CSS
# ═══════════════════════════════════════════════════════════

def inject_css():
    st.markdown(
        """
        <style>
        /* Dark premium theme overrides */
        .stApp {
            background: linear-gradient(180deg, #0E1117 0%, #1A1D2E 100%);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #141824 0%, #1E2130 100%);
            border-right: 1px solid #2D3250;
        }
        [data-testid="stMetricValue"] {
            font-size: 2rem !important;
            font-weight: 700;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.9rem !important;
            color: #95A5A6;
        }
        div[data-testid="stTabs"] button {
            font-size: 1rem !important;
            font-weight: 600;
            padding: 0.75rem 1.5rem;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            border-bottom: 3px solid #F7B731;
            color: #F7B731;
        }
        .stDataFrame {
            border-radius: 8px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    inject_css()

    # Load data
    if not DB_PATH.exists():
        st.error(f"Database not found: {DB_PATH}")
        st.stop()

    df = load_data()

    if df.empty:
        st.error("No processed reviews found in database.")
        st.stop()

    # Sidebar filters
    filtered = render_sidebar(df)
    is_ios_only = len(filtered["source_platform"].unique()) == 1 and "app_store" in filtered["source_platform"].values

    # Tabs
    tab1, tab2, tab3 = st.tabs([
        "📊 Macro & Trends",
        "🔥 Pain Point Matrix",
        "⚖️ Evidence Court",
    ])

    with tab1:
        render_tab_macro(filtered, is_ios_only)

    with tab2:
        render_tab_painpoints(filtered)

    with tab3:
        render_tab_evidence(filtered)


if __name__ == "__main__":
    main()
