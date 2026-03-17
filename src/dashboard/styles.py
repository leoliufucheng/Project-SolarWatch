import streamlit as st

def inject_custom_css():
    """Injects custom CSS to style Streamlit like a professional dashboard (agent-skills style)."""
    st.markdown(
        """
        <style>
        /* Global Background & Typography */
        .stApp {
            background-color: #F8F9FA;
            color: #212529;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E9ECEF;
        }
        
        /* Metric Cards Simulation */
        div[data-testid="stMetric"] {
            background-color: #FFFFFF;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.03);
            border: 1px solid #F1F3F5;
            transition: transform 0.2s ease-in-out;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.06);
        }
        [data-testid="stMetricValue"] {
            font-size: 2.2rem !important;
            font-weight: 700;
            color: #111827;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.95rem !important;
            font-weight: 600;
            color: #6B7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        /* Headers */
        h1, h2, h3 {
            font-weight: 700 !important;
            color: #111827 !important;
        }
        
        /* Tabs (if used) */
        div[data-testid="stTabs"] button {
            font-size: 1.05rem !important;
            font-weight: 600;
            padding: 0.75rem 1.5rem;
            color: #6B7280;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            border-bottom: 3px solid #1f77b4;
            color: #1f77b4;
        }
        
        /* Dataframes */
        .stDataFrame {
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #E5E7EB;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
