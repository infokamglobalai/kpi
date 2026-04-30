import streamlit as st


def apply_branding() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background: linear-gradient(180deg, #f7faff 0%, #eef4ff 100%);
            }
            [data-testid="stMetricValue"] {
                color: #1c3faa;
            }
            [data-testid="stSidebar"] {
                background: #0b1a4a;
            }
            [data-testid="stSidebar"] * {
                color: #ffffff !important;
            }
            .brand-title {
                font-size: 2.0rem;
                font-weight: 700;
                color: #0d2f8b;
                margin-bottom: 0.2rem;
            }
            .brand-subtitle {
                font-size: 1rem;
                color: #4d5e8b;
                margin-bottom: 1rem;
            }
            div[data-testid="stTabs"] button[p-baseweb="tab"] {
                font-weight: 600;
            }
            .kpi-mgmt-header {
                background: linear-gradient(90deg, #ffffff 0%, #f0f5ff 100%);
                border-radius: 12px;
                padding: 1rem 1.25rem;
                border: 1px solid #dbe4ff;
                margin-bottom: 1rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
