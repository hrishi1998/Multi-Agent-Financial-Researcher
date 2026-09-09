"""Streamlit multipage entry for New Research."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from ui_research import render_research_tab

st.set_page_config(page_title="New Research", layout="wide")
st.title("New Research")
render_research_tab()
