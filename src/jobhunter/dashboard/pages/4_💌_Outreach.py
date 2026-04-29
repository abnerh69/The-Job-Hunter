import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar

st.set_page_config(page_title="Outreach", page_icon="💌", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("💌 Outreach")
st.write("Manage proactive contacts and networking.")
st.info("Placeholder: Implementation coming in next stories.")
