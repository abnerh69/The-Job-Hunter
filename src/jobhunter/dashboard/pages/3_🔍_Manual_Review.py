import streamlit as st
import time
import asyncio
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.dashboard.components import render_manual_review_card
from jobhunter.db.session import get_session
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.models import Job
from jobhunter.config import Settings
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.scoring.scorer import JobScorer
from typing import Any
from jobhunter.scoring.schema import ScoringResult

st.set_page_config(page_title="Manual Review", page_icon="🔍", layout="wide")
require_auth()
render_header()
render_sidebar()

# Initialize session state
if "show_reject_modal" not in st.session_state:
    st.session_state.show_reject_modal = False
if "job_to_reject" not in st.session_state:
    st.session_state.job_to_reject = None

# Side-bar Filters
st.sidebar.divider()
st.sidebar.subheader("Filtros")

antiquity_filter = st.sidebar.slider("Antigüedad mínima (días)", 0, 30, 0)


@st.dialog("Confirmar Rechazo")
def reject_dialog(job: Job) -> None:
    st.write(f"¿Por qué deseas rechazar el job: **{job.title}** en **{job.company}**?")
    reason = st.text_area(
        "Razón del rechazo", placeholder="Ej: No es remoto real, salario muy bajo..."
    )

    if st.button("Confirmar Rechazo", type="primary"):
        if not reason:
            st.error("Por favor, ingresa una razón.")
            return
        with get_session() as session:
            repo = JobRepo(session)
            # Update status and reason
            job_db = repo.get(job.id)
            if job_db:
                job_db.status = JobStatus.REJECTED
                job_db.manually_promoted_reason = f"Manual Reject: {reason}"
                session.commit()
            st.cache_data.clear()
        st.session_state.show_reject_modal = False
        st.session_state.job_to_reject = None
        st.success("Job rechazado correctamente.")
        time.sleep(1)
        st.rerun()

    if st.button("Cancelar"):
        st.session_state.show_reject_modal = False
        st.session_state.job_to_reject = None
        st.rerun()


# Handlers
def handle_promote(job: Job) -> None:
    with get_session() as session:
        repo = JobRepo(session)
        repo.mark_status(job.id, JobStatus.QUEUED)
        # Record manual promotion
        job_db = repo.get(job.id)
        if job_db:
            from datetime import datetime, timezone

            job_db.manually_promoted_at = datetime.now(timezone.utc)
            job_db.manually_promoted_reason = "Manual promotion from Manual Review page"
            session.commit()
        st.cache_data.clear()
    st.success(f"Job {job.company} promovido a la cola.")
    time.sleep(0.5)
    st.rerun()


def handle_reject(job: Job) -> None:
    st.session_state.show_reject_modal = True
    st.session_state.job_to_reject = job
    st.rerun()


@st.dialog("Resultado Re-scoring")
def show_rescore_result(old_score: int, outcome: Any) -> None:
    new_score = outcome.result.fit_score if isinstance(outcome.result, ScoringResult) else 0
    diff = new_score - old_score

    st.subheader(f"Nuevo Fit Score: {new_score}%")

    if diff > 10:
        st.success(f"🚀 Mejora significativa detectada: +{diff} puntos.")
    elif diff < -10:
        st.error(f"📉 Empeoramiento significativo: {diff} puntos.")
    else:
        st.info(f"⚖️ Diferencia menor: {diff:+} puntos.")

    st.write(
        f"**Nuevo Tier:** {outcome.result.tier if isinstance(outcome.result, ScoringResult) else 'REJECT'}"
    )

    if st.button("Cerrar y Actualizar"):
        st.rerun()


async def run_rescore(job: Job) -> None:
    settings = Settings()  # type: ignore[call-arg]
    llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
    # Re-score with Sonnet 4.6 as requested
    scorer = JobScorer(llm_client=llm_client, model="claude-sonnet-4-6")

    with st.status("Re-ejecutando scoring con Sonnet 4.6...") as status:
        with get_session() as session:
            from jobhunter.db.repos.candidate_profile import CandidateProfileRepo

            profile_repo = CandidateProfileRepo(session)
            profiles = profile_repo.list_active()
            if not profiles:
                st.error("No hay perfiles activos para realizar el scoring.")
                return
            profile = profiles[0]

            outcome = await scorer.score(job, profile=profile, session=session)

            # Persist if better or just to update
            job_db = session.get(Job, job.id)
            if job_db:
                job_db.score_model = outcome.model
                job_db.score_version = outcome.prompt_version
                job_db.score_data = outcome.result.model_dump()
                if isinstance(outcome.result, ScoringResult):
                    job_db.fit_score = outcome.result.fit_score
                    job_db.tier = JobTier(outcome.result.tier.value)
                session.commit()

            status.update(label="Scoring completado", state="complete")
            st.session_state.rescore_outcome = (job.fit_score, outcome)


def handle_rescore(job: Job) -> None:
    asyncio.run(run_rescore(job))
    st.rerun()


# Main Content
st.header("🔍 Manual Review (Tier C)")


@st.cache_data(ttl=60)
def get_mr_metrics() -> dict[str, int]:
    with get_session() as session:
        repo = JobRepo(session)
        return repo.get_manual_review_metrics()


metrics = get_mr_metrics()

m_col1, m_col2 = st.columns(2)
with m_col1:
    st.metric("Jobs esperando review", metrics["total_pending"])
with m_col2:
    color = "normal"
    if metrics["old_pending"] > 0:
        st.metric("Antiguos (> 7 días)", metrics["old_pending"], delta_color="inverse")
        if metrics["old_pending"] > 5:
            st.error(f"⚠️ ¡Atención! Hay {metrics['old_pending']} jobs acumulando polvo.")
    else:
        st.metric("Antiguos (> 7 días)", 0)

# Query Jobs
page_size = 10
if "mr_page_num" not in st.session_state:
    st.session_state.mr_page_num = 1

offset = (st.session_state.mr_page_num - 1) * page_size


@st.cache_data(ttl=60)
def fetch_mr_jobs(min_age: int, limit: int, offset: int) -> list[Job]:
    with get_session() as session:
        repo = JobRepo(session)
        return list(repo.list_manual_review(min_age_days=min_age, limit=limit, offset=offset))


jobs = fetch_mr_jobs(antiquity_filter, page_size, offset)

if st.session_state.show_reject_modal and st.session_state.job_to_reject:
    reject_dialog(st.session_state.job_to_reject)

if "rescore_outcome" in st.session_state:
    old_score, outcome = st.session_state.rescore_outcome
    del st.session_state.rescore_outcome
    show_rescore_result(old_score, outcome)

if not jobs:
    st.info("No hay jobs en Manual Review que coincidan con los filtros.")
else:
    for job in jobs:
        render_manual_review_card(
            job, on_promote=handle_promote, on_reject=handle_reject, on_rescore=handle_rescore
        )

    # Pagination
    st.divider()
    p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
    with p_col1:
        if st.session_state.mr_page_num > 1:
            if st.button("Anterior"):
                st.session_state.mr_page_num -= 1
                st.rerun()
    with p_col2:
        st.write(f"Página {st.session_state.mr_page_num}")
    with p_col3:
        if len(jobs) == page_size:
            if st.button("Siguiente"):
                st.session_state.mr_page_num += 1
                st.rerun()
