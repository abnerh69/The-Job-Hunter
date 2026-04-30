import streamlit as st
import time
from datetime import datetime, timezone
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.dashboard.components import render_application_card, render_application_detail_modal
from jobhunter.db.session import get_session
from jobhunter.db.repos.application import ApplicationRepo
from jobhunter.db.enums import ApplicationStatus
from jobhunter.db.models import Application

st.set_page_config(page_title="Pipeline", page_icon="📋", layout="wide")
require_auth()
render_header()
render_sidebar()

# Initialize session state for modals
if "show_app_modal" not in st.session_state:
    st.session_state.show_app_modal = False
if "app_id_to_show" not in st.session_state:
    st.session_state.app_id_to_show = None

# Sidebar Filters
st.sidebar.divider()
st.sidebar.subheader("Filtros")


@st.cache_data(ttl=60)
def get_available_methods() -> list[str]:
    with get_session() as session:
        methods = session.query(Application.application_method).distinct().all()
        return [m[0] for m in methods if m[0]]


available_methods = get_available_methods()
selected_methods = st.sidebar.multiselect(
    "Método de Aplicación", options=available_methods, default=available_methods
)

# Application Month Filter
current_year = datetime.now(timezone.utc).year
current_month = datetime.now(timezone.utc).month

months = [
    (1, "Enero"),
    (2, "Febrero"),
    (3, "Marzo"),
    (4, "Abril"),
    (5, "Mayo"),
    (6, "Junio"),
    (7, "Julio"),
    (8, "Agosto"),
    (9, "Septiembre"),
    (10, "Octubre"),
    (11, "Noviembre"),
    (12, "Diciembre"),
]
month_options = ["Todos"] + [m[1] for m in months]
selected_month_name = st.sidebar.selectbox("Mes de Aplicación", options=month_options, index=0)

selected_month = None
if selected_month_name != "Todos":
    selected_month = [m[0] for m in months if m[1] == selected_month_name][0]

show_terminal = st.sidebar.toggle("Mostrar rechazados/ghosted", value=False)

# Header
st.header("📋 Application Pipeline")

# Metrics
with get_session() as session:
    repo = ApplicationRepo(session)
    metrics = repo.get_pipeline_metrics()

col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("Apps Activas", metrics["total_active"])
col_m2.metric("Edad Media (días)", metrics["mean_age_days"])

with col_m3:
    st.write("**Próximas Acciones:**")
    for action in metrics["urgent_actions"]:
        st.caption(f"• {action['company']}: {action['action']} ({action['due']})")

st.divider()


# Actions Handlers
def handle_app_click(app: Application) -> None:
    st.session_state.show_app_modal = True
    st.session_state.app_id_to_show = app.id
    st.rerun()


def handle_move_next(app: Application) -> None:
    # Deterministic next step logic for the quick button
    next_map = {
        ApplicationStatus.APPLIED: ApplicationStatus.SCREENING,
        ApplicationStatus.SCREENING: ApplicationStatus.INTERVIEW_1,
        ApplicationStatus.INTERVIEW_1: ApplicationStatus.INTERVIEW_N,
        ApplicationStatus.INTERVIEW_N: ApplicationStatus.OFFER,
    }
    new_status = next_map.get(app.status)
    if new_status:
        with get_session() as session:
            repo = ApplicationRepo(session)
            repo.transition_status(app.id, new_status, note="Quick move from Pipeline")
            session.commit()
        st.success(f"Movido a {new_status}")
        time.sleep(0.5)
        st.rerun()


# Kanban Board
statuses_to_show = [
    ApplicationStatus.APPLIED,
    ApplicationStatus.SCREENING,
    ApplicationStatus.INTERVIEW_1,
    ApplicationStatus.INTERVIEW_N,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
    ApplicationStatus.GHOSTED,
]

# Create exactly 7 columns
cols = st.columns(7)
status_to_col = {status: cols[i] for i, status in enumerate(statuses_to_show)}

# Header for each column
for status, col in status_to_col.items():
    col.markdown(f"### {status.value.upper()}")

# Fetch Applications
with get_session() as session:
    repo = ApplicationRepo(session)
    apps = repo.list_pipeline(
        methods=selected_methods, month=selected_month, include_terminal=show_terminal
    )

    # Organize apps by status
    for app in apps:
        if app.status in status_to_col:
            with status_to_col[app.status]:
                render_application_card(
                    app, on_click=handle_app_click, on_move_next=handle_move_next
                )


# Action handler for closing modal
def handle_modal_close() -> None:
    st.session_state.show_app_modal = False
    st.session_state.app_id_to_show = None


# Show modal if requested
if st.session_state.show_app_modal and st.session_state.app_id_to_show:
    render_application_detail_modal(st.session_state.app_id_to_show, on_close=handle_modal_close)
