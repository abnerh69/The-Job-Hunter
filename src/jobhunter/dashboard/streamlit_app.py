import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar

# Page configuration
st.set_page_config(
    page_title="Job Hunter EU Dashboard",
    page_icon="🎯",
    layout="wide",
)

# Authentication
require_auth()

# Main Layout
render_header()
render_sidebar()

st.write("Welcome to the Job Hunter EU Dashboard. Select a page from the sidebar to begin.")

# Quick stats or overview could go here
st.info("System is operational. Monitoring job sources...")
