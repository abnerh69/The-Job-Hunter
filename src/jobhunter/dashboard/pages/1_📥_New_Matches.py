import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar

st.set_page_config(page_title="New Matches", page_icon="📥", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("📥 New Matches (Tier A)")
st.write("Jobs that perfectly match your profile and require immediate action.")
st.info("Placeholder: Implementation coming in next stories.")
