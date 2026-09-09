"""Streamlit multipage entry for HITL approvals."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from ui_hitl import render_hitl_tab

st.set_page_config(page_title="HITL Pending Approvals", layout="wide")
st.title("HITL Pending Approvals")
render_hitl_tab()
