import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar

st.set_page_config(page_title="Metrics", page_icon="📊", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("📊 Metrics & Insights")
st.write("System performance and job market trends.")
st.info("Placeholder: Implementation coming in next stories.")
