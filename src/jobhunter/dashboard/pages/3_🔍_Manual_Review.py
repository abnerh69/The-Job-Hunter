import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar

st.set_page_config(page_title="Manual Review", page_icon="🔍", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("🔍 Manual Review (Tier C)")
st.write("Jobs that might be interesting but need human eyes.")
st.warning(
    "Esta página fue movida a la **Épica 13: QA Humana** (story `E13-S01`). "
    "La implementación quedó diferida durante la verificación de la Épica 7. "
    "Ver `docs/Plan automatizado para búsqueda de trabajo remoto en Europa/"
    "Q_Backlog_Nivel2_E13.md` para los acceptance criteria y el plan de "
    "implementación."
)
