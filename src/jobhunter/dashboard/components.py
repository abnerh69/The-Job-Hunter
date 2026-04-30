import streamlit as st
from datetime import date, datetime, timezone
from typing import Any, Callable
from jobhunter.db.models import Job, Application
from jobhunter.db.enums import JobTier, ApplicationStatus, ApplicationEventType
from jobhunter.db.session import get_session
from jobhunter.db.repos.application import ApplicationRepo
import time


def format_relative_time(dt: datetime | date) -> str:
    """
    Returns a human-readable relative time string in Spanish.
    """
    if not dt:
        return ""

    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt

    seconds = diff.total_seconds()
    if seconds < 60:
        return "hace unos segundos"

    minutes = seconds // 60
    if minutes < 60:
        return f"hace {int(minutes)}m"

    hours = minutes // 60
    if hours < 24:
        return f"hace {int(hours)}h"

    days = hours // 24
    if days == 1:
        return "ayer"

    return f"hace {int(days)}d"


def render_job_card(
    job: Job, on_skip: Callable[[Job], None], on_apply: Callable[[Job], None]
) -> None:
    """
    Renders a visual card for a job match.
    """
    tier_emoji = {
        JobTier.A: "🔥",
        JobTier.B: "✅",
        JobTier.C: "⚖️",
        JobTier.REJECT: "❌",
    }.get(job.tier if job.tier else JobTier.C, "❓")

    is_focused = st.query_params.get("focus") == str(job.id)
    border_style = "2px solid #ff4b4b" if is_focused else None

    with st.container(border=True):
        st.markdown(
            f'<div data-testid="job-card" data-job-id="{job.id}"></div>', unsafe_allow_html=True
        )
        if is_focused:
            st.markdown(
                f"""
                <div style="border: {border_style}; border-radius: 0.5rem; padding: 1px; margin-bottom: -1px;">
                """,
                unsafe_allow_html=True,
            )
        col1, col2 = st.columns([0.8, 0.2])

        with col1:
            st.subheader(f"{tier_emoji} {job.title}")
            st.write(f"**{job.company}**")

        with col2:
            st.metric("Fit Score", f"{job.fit_score}%")

        # Salary and metadata
        salary_info = "Salario no especificado"
        if job.score_data and "compensation" in job.score_data:
            comp = job.score_data["compensation"]
            s_min = comp.get("salary_min_usd_month")
            s_max = comp.get("salary_max_usd_month")
            if s_min and s_max:
                salary_info = f"💰 ${s_min:,.0f} - ${s_max:,.0f} / mes"
            elif s_max:
                salary_info = f"💰 hasta ${s_max:,.0f} / mes"

        st.write(salary_info)

        # Match Points
        if job.score_data and "match_analysis" in job.score_data:
            points = job.score_data["match_analysis"].get("key_match_points", [])[:3]
            if points:
                st.write("**Top Match Points:**")
                for p in points:
                    st.write(f"• {p}")

        # Flags
        if job.score_data:
            red_flags = job.score_data.get("red_flags", [])
            yellow_flags = job.score_data.get("yellow_flags", [])

            if red_flags:
                st.warning(f"🚩 **Red Flags:** {', '.join(red_flags)}")
            if yellow_flags:
                st.info(f"⚠️ **Yellow Flags:** {', '.join(yellow_flags)}")

        # Footer
        st.divider()
        f_col1, f_col2 = st.columns([0.5, 0.5])

        with f_col1:
            st.caption(f"Fuente: {job.source} | {format_relative_time(job.scraped_at)}")

        with f_col2:
            btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

            with btn_col1:
                # Green button for assist
                if st.button("🚀 Assist", key=f"assist_{job.id}", type="primary"):
                    st.query_params["job_id"] = str(job.id)
                    st.session_state["job_id"] = str(job.id)
                    st.switch_page("pages/7_🛠_Assist.py")

            with btn_col2:
                if st.button("⏭️ Skip", key=f"skip_{job.id}"):
                    on_skip(job)

            with btn_col3:
                if st.button("📝 Apply", key=f"apply_{job.id}"):
                    on_apply(job)

            with btn_col4:
                st.link_button("🌐 View", job.url)

        if is_focused:
            st.markdown("</div>", unsafe_allow_html=True)


def render_application_card(
    app: Application,
    on_click: Callable[[Application], None],
    on_move_next: Callable[[Application], None],
) -> None:
    """
    Renders a compact card for an application in the Kanban board.
    """
    is_focused = st.query_params.get("focus") == str(app.id)
    border_style = "2px solid #ff4b4b" if is_focused else None

    with st.container(border=True):
        st.markdown(
            f'<div data-testid="application-card" data-app-id="{app.id}"></div>',
            unsafe_allow_html=True,
        )
        if is_focused:
            st.markdown(
                f"""
                <div style="border: {border_style}; border-radius: 0.5rem; padding: 1px; margin-bottom: -1px;">
                """,
                unsafe_allow_html=True,
            )
        st.markdown(f"**{app.job.company}**")
        st.caption(app.job.title)

        # Status age
        age_str = format_relative_time(app.status_updated_at)
        st.caption(f"⏱️ {age_str}")

        # Next action badge
        if app.next_action_due:
            today = datetime.now(timezone.utc).date()
            if app.next_action_due <= today:
                st.error(f"🚨 {app.next_action}")
            else:
                st.info(f"📅 {app.next_action}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("👁️ Detalle", key=f"det_{app.id}", use_container_width=True):
                on_click(app)
        with col2:
            # Only show move button if not in terminal state
            terminal_states = [
                ApplicationStatus.OFFER,
                ApplicationStatus.REJECTED,
                ApplicationStatus.GHOSTED,
                ApplicationStatus.WITHDRAWN,
            ]
            if app.status not in terminal_states:
                if st.button("➡️", key=f"move_{app.id}", use_container_width=True):
                    on_move_next(app)

        if is_focused:
            st.markdown("</div>", unsafe_allow_html=True)


@st.dialog("Detalle de Aplicación")
def render_application_detail_modal(
    app_id: Any, on_close: Callable[[], None] | None = None
) -> None:
    """
    Renders the detail modal for an application.
    """
    with get_session() as session:
        repo = ApplicationRepo(session)
        app = repo.get(app_id)

        if not app:
            st.error("Aplicación no encontrada.")
            return

        st.subheader(f"{app.job.title} @ {app.job.company}")
        st.caption(
            f"Aplicado el {app.applied_at.strftime('%Y-%m-%d')} via {app.application_method}"
        )

        tabs = st.tabs(["📋 Info", "✉️ Cover Letter", "📝 Notas", "🕒 Historial", "👤 Contacto"])

        with tabs[0]:
            st.write(f"**URL:** [Link]({app.job.url})")
            st.write(f"**Status Actual:** `{app.status}`")
            if app.salary_currency:
                st.write(
                    f"**Oferta:** {app.salary_currency} {app.salary_offered_min} - {app.salary_offered_max}"
                )

            st.divider()
            st.write("### Próxima Acción")
            new_action = st.text_input("Acción", value=app.next_action or "")
            new_due = st.date_input("Fecha", value=app.next_action_due)

            if st.button("Actualizar Acción"):
                repo.update(app.id, next_action=new_action, next_action_due=new_due)
                session.commit()
                st.success("Acción actualizada.")
                time.sleep(0.5)
                st.rerun()

        with tabs[1]:
            if app.cover_letter_text:
                st.text_area(
                    "Cover Letter (read-only)",
                    value=app.cover_letter_text,
                    height=300,
                    disabled=True,
                )
            else:
                st.info("No hay cover letter registrada.")

        with tabs[2]:
            new_notes = st.text_area("Notas", value=app.notes or "", height=200)
            if st.button("Guardar Notas"):
                repo.update(app.id, notes=new_notes)
                session.commit()
                st.success("Notas guardadas.")
                time.sleep(0.5)
                st.rerun()

        with tabs[3]:
            # Events history
            # Sort events by occurred_at desc
            sorted_events = sorted(app.events, key=lambda x: x.occurred_at, reverse=True)
            for event in sorted_events:
                with st.container():
                    st.write(
                        f"**{event.occurred_at.strftime('%Y-%m-%d %H:%M')}** - {event.event_type}"
                    )
                    if event.event_data:
                        if event.event_type == ApplicationEventType.STATUS_CHANGE:
                            st.write(
                                f"Cambio: `{event.event_data.get('old_status')}` → `{event.event_data.get('new_status')}`"
                            )
                        if "note" in event.event_data:
                            st.write(f"Nota: {event.event_data['note']}")
                    st.divider()

        with tabs[4]:
            st.write(f"**Nombre:** {app.contact_name or 'N/A'}")
            st.write(f"**Email:** {app.contact_email or 'N/A'}")
            st.write(f"**LinkedIn:** {app.contact_linkedin or 'N/A'}")

        st.divider()
        st.write("### Transiciones de Estado")

        note = st.text_input("Nota de transición (opcional)", key=f"note_input_{app.id}")

        cols = st.columns(4)

        # Determine logical next statuses based on current
        next_map = {
            ApplicationStatus.APPLIED: [
                ApplicationStatus.SCREENING,
                ApplicationStatus.REJECTED,
                ApplicationStatus.GHOSTED,
            ],
            ApplicationStatus.SCREENING: [
                ApplicationStatus.INTERVIEW_1,
                ApplicationStatus.REJECTED,
            ],
            ApplicationStatus.INTERVIEW_1: [
                ApplicationStatus.INTERVIEW_N,
                ApplicationStatus.REJECTED,
            ],
            ApplicationStatus.INTERVIEW_N: [ApplicationStatus.OFFER, ApplicationStatus.REJECTED],
        }

        possible_next = next_map.get(
            app.status, [ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]
        )

        for i, status in enumerate(possible_next):
            with cols[i % 4]:
                if st.button(f"Mover a {status.value}", key=f"trans_{status}_{app.id}"):
                    repo.transition_status(app.id, status, note=note)
                    session.commit()
                    st.success(f"Movido a {status}")
                    time.sleep(0.5)
                    st.rerun()

        st.divider()
        if st.button("Cerrar", key=f"close_modal_{app.id}"):
            if on_close:
                on_close()
            st.rerun()
