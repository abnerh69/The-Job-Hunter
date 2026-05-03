import streamlit as st
import uuid
import asyncio
import time
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.db.session import get_session
from jobhunter.db.models import Job, Application
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.repos.application import ApplicationRepo
from jobhunter.db.repos.candidate_profile import CandidateProfileRepo
from jobhunter.db.repos.cv_variant import CVVariantRepo
from jobhunter.db.enums import JobStatus, ApplicationStatus
from jobhunter.config import Settings
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.application.assistant import ApplicationPackage
from jobhunter.application.variant_selector import recommend_cv_variant
from jobhunter.application.cv import load_cv
from jobhunter.application.ats_keywords import extract_ats_keywords
from jobhunter.application.cv_tweaks import suggest_cv_tweaks
from jobhunter.application.cover_letter import generate_cover_letter
from sqlalchemy import select

st.set_page_config(page_title="Job Assist", page_icon="🛠", layout="wide")
require_auth()
render_header()
render_sidebar()

# Get job_id from query params or session state
job_id_str = st.query_params.get("job_id") or st.session_state.get("job_id")

if not job_id_str:
    st.info(
        "Por favor, selecciona un job desde la página de 'New Matches' para comenzar la asistencia."
    )
    st.stop()

try:
    job_id = uuid.UUID(job_id_str)
except ValueError:
    st.error(f"ID de job inválido: {job_id_str}")
    st.stop()

# Fetch Job and initialize session state
if "current_job" not in st.session_state or st.session_state.current_job.id != job_id:
    with get_session() as session:
        job_repo = JobRepo(session)
        job = job_repo.get(job_id)
        if not job:
            st.error(f"Job con ID {job_id} no encontrado.")
            st.stop()
        st.session_state.current_job = job
        # Clear previous assistance data when job changes
        if "assist_package" in st.session_state:
            del st.session_state.assist_package

job = st.session_state.current_job

st.header(f"🛠 Asistencia para {job.title}")
st.subheader(f"{job.company}")

col1, col2 = st.columns([0.7, 0.3])
with col1:
    st.markdown(f"**URL:** [{job.url}]({job.url})")
    st.markdown(f"**Tier:** `{job.tier}` | **Fit Score:** `{job.fit_score}%`")
with col2:
    if st.button("🔄 Volver a New Matches", use_container_width=True):
        st.switch_page("pages/1_📥_New_Matches.py")

st.divider()

if job.tier not in ["A", "B"]:
    st.warning(
        f"Este job es Tier {job.tier}. La asistencia completa (LLM) solo está disponible para Tiers A y B."
    )
    if st.button("Continuar de todas formas (Expert Mode)"):
        pass
    else:
        st.stop()

# Assistance Orchestration
settings = Settings()  # type: ignore[call-arg]
llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())


async def run_assistance() -> None:
    with st.status("Preparando asistencia...", expanded=True) as status:
        with get_session() as session:
            # Re-fetch to ensure we have a fresh object in this session
            job_repo = JobRepo(session)
            db_job = job_repo.get(job_id)
            if not db_job:
                st.error("Error al recuperar el job.")
                return

            status.write("🔍 Selecting CV variant...")
            # Load variants from DB
            profile_repo = CandidateProfileRepo(session)
            profiles = profile_repo.list_active()
            if not profiles:
                st.error("No active candidate profile found.")
                return
            profile = profiles[0]

            variant_repo = CVVariantRepo(session)
            available_variants = variant_repo.list_by_profile(profile.id)

            cv_recommendation = await recommend_cv_variant(
                db_job, available_variants=available_variants, llm_client=llm_client
            )
            cv_variant = load_cv(cv_recommendation.variant_name, settings=settings)

            status.write("✉️ Generating cover letter (Opus)...")
            cover_letter_task = generate_cover_letter(
                job=db_job,
                cv_variant=cv_variant,
                llm_client=llm_client,
                model=settings.COVER_LETTER_MODEL,
                session=session,
            )

            status.write("🏷️ Extracting ATS keywords...")
            keywords_task = extract_ats_keywords(
                job=db_job,
                llm_client=llm_client,
                cv_variant=cv_variant,
                session=session,
            )

            # Wait for keywords to suggest tweaks
            ats_keywords = await keywords_task

            status.write("💡 Suggesting CV tweaks...")
            cv_tweaks = await suggest_cv_tweaks(
                job=db_job,
                cv_variant=cv_variant,
                ats_keywords=ats_keywords,
                llm_client=llm_client,
                session=session,
            )

            cover_letter = await cover_letter_task

            status.write("✅ All steps completed!")

            # Calculate totals
            total_duration_ms = int(0)  # We could track this if needed
            total_cost = ats_keywords.cost_usd + cv_tweaks.cost_usd + cover_letter.cost_usd

            # Estimated time heuristic
            estimated_time = 8 + len(cv_tweaks.tweaks)
            all_keywords = ats_keywords.must_have + ats_keywords.nice_to_have
            if all_keywords and all(kw.present_in_cv for kw in all_keywords):
                estimated_time -= 2
            estimated_time = max(1, estimated_time)

            package = ApplicationPackage(
                job_id=job_id,
                cv_variant=cv_recommendation,
                cover_letter=cover_letter,
                ats_keywords=ats_keywords,
                cv_tweaks=cv_tweaks,
                total_cost_usd=total_cost,
                total_duration_ms=total_duration_ms,
                estimated_apply_time_min=estimated_time,
            )

            # Persist to assistant_cache
            new_score_data = dict(db_job.score_data or {})
            new_score_data["assistant_cache"] = {
                "cv_variant": cv_recommendation.variant_name,
                "cover_letter_text": cover_letter.text,
                "cover_letter_model": cover_letter.model,
                "estimated_apply_time_min": estimated_time,
            }
            db_job.score_data = new_score_data
            session.commit()

            st.session_state.assist_package = package
            status.update(label="Asistencia completada!", state="complete", expanded=False)


# Trigger assistance
if "assist_package" not in st.session_state:
    if st.button("🚀 Generar Asistencia Completa", type="primary"):
        asyncio.run(run_assistance())
        st.rerun()
else:
    if st.button("🔄 Regenerar Asistencia"):
        del st.session_state.assist_package
        st.rerun()

if "assist_package" in st.session_state:
    package = st.session_state.assist_package
    st.success("Asistencia generada con éxito.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Costo LLM", f"${package.total_cost_usd:.4f}")
    m2.metric("Tiempo Estimado", f"{package.estimated_apply_time_min} min")
    m3.metric("Confianza CV", f"{int(package.cv_variant.confidence * 100)}%")

    tabs = st.tabs(["✉️ Cover Letter", "🏷️ ATS Keywords", "💡 CV Tweaks", "📄 CV Variant"])

    with tabs[0]:
        st.subheader("Cover Letter")
        if "edited_cover_letter" not in st.session_state:
            st.session_state.edited_cover_letter = (
                package.cover_letter.text if package.cover_letter else ""
            )

        edited_cl = st.text_area(
            "Edita tu cover letter antes de aplicar",
            value=st.session_state.edited_cover_letter,
            height=400,
        )
        st.session_state.edited_cover_letter = edited_cl

        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Save edits", use_container_width=True):
                with get_session() as session:
                    db_job = session.get(Job, job_id)
                    if db_job:
                        new_score_data = dict(db_job.score_data or {})
                        if "assistant_cache" not in new_score_data:
                            new_score_data["assistant_cache"] = {}
                        new_score_data["assistant_cache"]["cover_letter_text"] = (
                            st.session_state.edited_cover_letter
                        )
                        db_job.score_data = new_score_data

                        # Also update application if it exists
                        stmt = select(Application).where(Application.job_id == job_id)
                        app = session.execute(stmt).scalar_one_or_none()
                        if app:
                            app.cover_letter_text = st.session_state.edited_cover_letter

                        session.commit()
                        st.success("Cambios guardados en la base de datos.")
        with c2:
            st.button("📋 Copy to clipboard (Coming soon)", use_container_width=True, disabled=True)

    with tabs[1]:
        st.subheader("ATS Keywords")
        st.write("Keywords extraídas del job description y su presencia en tu CV.")

        col_must, col_nice = st.columns(2)
        with col_must:
            st.markdown("**Must Have**")
            for kw in package.ats_keywords.must_have:
                emoji = "✅" if kw.present_in_cv else "❌"
                st.write(f"{emoji} {kw.term} ({kw.weight}/10)")
        with col_nice:
            st.markdown("**Nice to Have**")
            for kw in package.ats_keywords.nice_to_have:
                emoji = "✅" if kw.present_in_cv else "❌"
                st.write(f"{emoji} {kw.term} ({kw.weight}/10)")

    with tabs[2]:
        st.subheader("CV Tweaks Sugeridos")
        st.write("Acciones recomendadas para mejorar tu fit con esta vacante.")
        for i, tweak in enumerate(package.cv_tweaks.tweaks):
            with st.container(border=True):
                st.checkbox(
                    f"**{tweak.type.replace('_', ' ').title()}**: {tweak.target}", key=f"tweak_{i}"
                )
                st.write(f"*Razón:* {tweak.rationale}")
                if tweak.suggested:
                    st.info(f"Sugerencia: {tweak.suggested}")

    with tabs[3]:
        st.subheader(f"Variante Recomendada: `{package.cv_variant.variant_name}`")
        st.write(f"**Razón:** {package.cv_variant.reasoning}")

        try:
            cv_variant = load_cv(package.cv_variant.variant_name, settings=settings)
            with st.expander("Ver CV actual"):
                st.markdown(cv_variant.raw_markdown)
        except Exception as e:
            st.error(f"No se pudo cargar el CV: {e}")

    st.divider()
    st.subheader("🚀 Marcar como Aplicado")
    with st.form("mark_applied_form"):
        method = st.selectbox(
            "Método de aplicación", ["LinkedIn", "Direct", "Indeed", "Ottoneu", "Other"]
        )
        notes = st.text_area("Notas adicionales")
        submit_applied = st.form_submit_button("✅ Mark Applied & Register", type="primary")

        if submit_applied:
            with get_session() as session:
                job_repo = JobRepo(session)
                app_repo = ApplicationRepo(session)

                # Check if application already exists
                stmt = select(Application).where(Application.job_id == job_id)
                app = session.execute(stmt).scalar_one_or_none()

                if app:
                    app.application_method = method
                    app.notes = (app.notes or "") + "\n" + notes
                    app.status = ApplicationStatus.APPLIED
                    app.cover_letter_text = st.session_state.edited_cover_letter
                    app.cv_variant = package.cv_variant.variant_name
                else:
                    app_repo.create_for_job(
                        job_id=job_id,
                        application_method=method,
                        cv_variant=package.cv_variant.variant_name,
                        notes=notes,
                        status=ApplicationStatus.APPLIED,
                        cover_letter_text=st.session_state.edited_cover_letter,
                        cover_letter_model=package.cover_letter.model
                        if package.cover_letter
                        else None,
                    )

                job_repo.mark_status(job_id, JobStatus.APPLIED)
                session.commit()

            st.success("Aplicación registrada correctamente!")
            time.sleep(1)
            st.switch_page("pages/2_📋_Pipeline.py")
