import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar

st.set_page_config(page_title="Pipeline", page_icon="📋", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("📋 Application Pipeline")
st.write("Track the status of your active applications.")
st.info("Placeholder: Implementation coming in next stories.")
