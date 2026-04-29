import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar

st.set_page_config(page_title="Manual Review", page_icon="🔍", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("🔍 Manual Review (Tier C)")
st.write("Jobs that might be interesting but need human eyes.")
st.info("Placeholder: Implementation coming in next stories.")
