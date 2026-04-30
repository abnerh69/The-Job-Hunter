import streamlit as st
import time
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.dashboard.components import render_job_card
from jobhunter.db.session import get_session
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.repos.application import ApplicationRepo
from jobhunter.db.enums import JobTier, JobStatus, ApplicationStatus
from jobhunter.db.models import Job

st.set_page_config(page_title="New Matches", page_icon="📥", layout="wide")
require_auth()
render_header()
render_sidebar()

# Initialize session state for modals and auto-refresh
if "show_skip_modal" not in st.session_state:
    st.session_state.show_skip_modal = False
if "job_to_skip" not in st.session_state:
    st.session_state.job_to_skip = None
if "show_apply_modal" not in st.session_state:
    st.session_state.show_apply_modal = False
if "job_to_apply" not in st.session_state:
    st.session_state.job_to_apply = None

# Side-bar Filters
st.sidebar.divider()
st.sidebar.subheader("Filtros")

selected_tiers = st.sidebar.multiselect(
    "Tier",
    options=[JobTier.A, JobTier.B],
    default=[JobTier.A, JobTier.B]
)

@st.cache_data(ttl=60)
def get_available_sources() -> list[str]:
    with get_session() as session:
        available_sources = session.query(Job.source).distinct().all()
        return [s[0] for s in available_sources]

available_sources = get_available_sources()

selected_sources = st.sidebar.multiselect(
    "Source",
    options=available_sources,
    default=available_sources
)

min_score = st.sidebar.slider("Min fit score", 50, 100, 70)

selected_stacks = st.sidebar.multiselect(
    "Stack predominante",
    options=["Python", "Flutter", "AI/ML", "Backend"],
    default=[]
)

min_salary = st.sidebar.number_input("Salario mínimo (USD/mes)", min_value=0, value=0, step=500)

# Auto-refresh logic
auto_refresh = st.sidebar.toggle("Auto-refresh (5 min)", value=True)
modal_open = st.session_state.show_skip_modal or st.session_state.show_apply_modal

if auto_refresh and not modal_open:
    # We use st.empty and a custom component-like approach for auto-refresh
    # Since we can't easily import streamlit_autorefresh, we'll use a hidden JS approach
    # or just a placeholder for now.
    # Sticking to the requirement of "auto-refresh every 5 min"
    st.components.v1.html(
        """
        <script>
            setTimeout(function() {
                window.parent.location.reload();
            }, 300000);
        </script>
        """,
        height=0,
    )

@st.dialog("Confirmar Skip")
def skip_dialog(job: Job) -> None:
    st.write(f"¿Estás seguro de que deseas archivar el job: **{job.title}** en **{job.company}**?")
    if st.button("Sí, archivar", type="primary"):
        with get_session() as session:
            repo = JobRepo(session)
            repo.mark_status(job.id, JobStatus.ARCHIVED)
            session.commit()
        st.session_state.show_skip_modal = False
        st.session_state.job_to_skip = None
        st.success("Job archivado correctamente.")
        time.sleep(1)
        st.rerun()
    if st.button("Cancelar"):
        st.session_state.show_skip_modal = False
        st.session_state.job_to_skip = None
        st.rerun()

@st.dialog("Mark as Applied")
def apply_dialog(job: Job) -> None:
    st.write(f"Registrar aplicación para: **{job.title}**")
    method = st.selectbox("Método", ["LinkedIn", "Direct", "Ottoneu", "Indeed", "Other"])
    cv_variant = st.selectbox("CV Variant", ["ai_python", "flutter", "fullstack", "general"])
    notes = st.text_area("Notas")

    if st.button("Registrar Aplicación", type="primary"):
        with get_session() as session:
            job_repo = JobRepo(session)
            app_repo = ApplicationRepo(session)

            # Create Application
            app_repo.create_for_job(
                job_id=job.id,
                application_method=method,
                cv_variant=cv_variant,
                notes=notes,
                status=ApplicationStatus.APPLIED
            )

            # Transition Job status
            job_repo.mark_status(job.id, JobStatus.APPLIED)
            session.commit()

        st.session_state.show_apply_modal = False
        st.session_state.job_to_apply = None
        st.success("Aplicación registrada.")
        time.sleep(1)
        st.rerun()

    if st.button("Cancelar"):
        st.session_state.show_apply_modal = False
        st.session_state.job_to_apply = None
        st.rerun()

# Actions Handlers
def handle_skip(job: Job) -> None:
    st.session_state.show_skip_modal = True
    st.session_state.job_to_skip = job
    st.rerun()

def handle_apply(job: Job) -> None:
    st.session_state.show_apply_modal = True
    st.session_state.job_to_apply = job
    st.rerun()

# Show dialogs if requested
if st.session_state.show_skip_modal and st.session_state.job_to_skip:
    skip_dialog(st.session_state.job_to_skip)

if st.session_state.show_apply_modal and st.session_state.job_to_apply:
    apply_dialog(st.session_state.job_to_apply)

# Main Content
st.header("📥 New Matches")

# Metrics
@st.cache_data(ttl=60)
def get_metrics() -> dict[str, int]:
    with get_session() as session:
        repo = JobRepo(session)
        return repo.get_dashboard_metrics()

metrics = get_metrics()

col_m1, col_m2 = st.columns(2)
col_m1.metric("Nuevos hoy", metrics["jobs_today"])
col_m2.metric("Tier-A pendientes", metrics["pending_a"])

# Query Jobs
page_size = 20
if "page_num" not in st.session_state:
    st.session_state.page_num = 1

offset = (st.session_state.page_num - 1) * page_size

@st.cache_data(ttl=60)
def fetch_jobs(tiers, sources, min_score, stacks, min_salary, limit, offset):
    with get_session() as session:
        repo = JobRepo(session)
        return repo.list_new_matches(
            tiers=tiers,
            sources=sources,
            min_score=min_score,
            stacks=stacks,
            min_salary=min_salary,
            limit=limit,
            offset=offset
        )

jobs = fetch_jobs(
    tiers=selected_tiers,
    sources=selected_sources,
    min_score=min_score,
    stacks=selected_stacks,
    min_salary=min_salary,
    limit=page_size,
    offset=offset
)

if not jobs:
    st.info("No se encontraron nuevos matches con los filtros actuales.")
else:
    for job in jobs:
        render_job_card(job, on_skip=handle_skip, on_apply=handle_apply)

    # Pagination
    st.divider()
    p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
    with p_col1:
        if st.session_state.page_num > 1:
            if st.button("Anterior"):
                st.session_state.page_num -= 1
                st.rerun()
    with p_col2:
        st.write(f"Página {st.session_state.page_num}")
    with p_col3:
        if len(jobs) == page_size:
            if st.button("Siguiente"):
                st.session_state.page_num += 1
                st.rerun()
