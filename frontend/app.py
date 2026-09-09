import os

import streamlit as st

from ui_hitl import render_hitl_tab
from ui_research import render_research_tab

st.set_page_config(
    page_title="Financial Research Console",
    page_icon="📈",
    layout="wide",
)

st.title("Quantitative Research Console")
st.caption(
    f"Backend `{os.getenv('API_BASE_URL', 'http://localhost:8000')}` · "
    "HTTP client only — no LangGraph imports."
)

research_tab, hitl_tab = st.tabs(["New Research", "HITL Pending Approvals"])
with research_tab:
    render_research_tab()
with hitl_tab:
    render_hitl_tab()
