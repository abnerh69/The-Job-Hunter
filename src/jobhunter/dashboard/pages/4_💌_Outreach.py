import streamlit as st
import pandas as pd
import io
import time
from datetime import date
from typing import Sequence

from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.db.session import get_session
import asyncio
from jobhunter.db.repos.outreach import OutreachRepo
from jobhunter.db.repos.outreach_messages import OutreachMessageRepo
from jobhunter.db.enums import (
    OutreachStatus,
    OutreachMarket,
    OutreachTemplateType,
    OutreachMessageStatus,
)
from jobhunter.db.models import OutreachContact
from jobhunter.config import Settings
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.outreach.generator import generate_message

st.set_page_config(page_title="Outreach", page_icon="💌", layout="wide")
require_auth()
render_header()
render_sidebar()

# Initialize session state for modals
if "show_import_modal" not in st.session_state:
    st.session_state.show_import_modal = False
if "show_note_modal" not in st.session_state:
    st.session_state.show_note_modal = False
if "contact_for_note" not in st.session_state:
    st.session_state.contact_for_note = None
if "show_gen_modal" not in st.session_state:
    st.session_state.show_gen_modal = False
if "contact_for_gen" not in st.session_state:
    st.session_state.contact_for_gen = None
if "gen_message_result" not in st.session_state:
    st.session_state.gen_message_result = None

# --- Sidebar Filters ---
st.sidebar.divider()
st.sidebar.subheader("Filtros")

selected_statuses = st.sidebar.multiselect(
    "Status",
    options=list(OutreachStatus),
    default=[
        OutreachStatus.NEW,
        OutreachStatus.CONTACTED,
        OutreachStatus.WARM,
        OutreachStatus.REPLIED,
    ],
)

selected_markets = st.sidebar.multiselect(
    "Market",
    options=list(OutreachMarket),
    default=list(OutreachMarket),
)

selected_stacks = st.sidebar.multiselect(
    "Specialty Stack",
    options=["Python", "Flutter", "AI/ML", "Backend", "Frontend", "Fullstack", "DevOps"],
    default=[],
)

due_only = st.sidebar.toggle("Due for follow-up", value=False)


# --- Metrics ---
@st.cache_data(ttl=60)
def fetch_metrics() -> dict[str, int]:
    """
    Fetches outreach metrics from the repository.

    Returns:
        dict[str, int]: A dictionary containing outreach metrics.
    """
    with get_session() as session:
        repo = OutreachRepo(session)
        return repo.get_outreach_metrics()


metrics = fetch_metrics()


# --- Query Contacts ---
@st.cache_data(ttl=60)
def fetch_contacts(
    statuses: list[OutreachStatus],
    markets: list[OutreachMarket],
    stacks: list[str],
    due_for_followup: bool,
) -> Sequence[OutreachContact]:
    """
    Fetches filtered outreach contacts from the repository.

    Args:
        statuses (list[OutreachStatus]): List of statuses to filter by.
        markets (list[OutreachMarket]): List of markets to filter by.
        stacks (list[str]): List of stacks to filter by.
        due_for_followup (bool): Whether to filter by due for follow-up.

    Returns:
        Sequence[OutreachContact]: A sequence of filtered outreach contacts.
    """
    with get_session() as session:
        repo = OutreachRepo(session)
        return repo.list_contacts(
            statuses=statuses,
            markets=markets,
            stacks=stacks,
            due_for_followup=due_for_followup,
        )


contacts = fetch_contacts(
    statuses=selected_statuses,
    markets=selected_markets,
    stacks=selected_stacks,
    due_for_followup=due_only,
)


@st.dialog("Añadir Nota")
def add_note_dialog(contact: OutreachContact) -> None:
    st.write(f"### Contacto: {contact.name}")
    new_note = st.text_area("Nota", value=contact.notes or "", height=200)

    if st.button("Guardar Nota", type="primary"):
        with get_session() as session:
            repo = OutreachRepo(session)
            repo.update(contact.id, notes=new_note)
            session.commit()
            st.success("Nota guardada.")
            st.cache_data.clear()
            st.session_state.show_note_modal = False
            st.session_state.contact_for_note = None
            time.sleep(0.5)
            st.rerun()

    if st.button("Cancelar"):
        st.session_state.show_note_modal = False
        st.session_state.contact_for_note = None
        st.rerun()


@st.dialog("Generar Mensaje")
def generate_message_dialog(contact: OutreachContact) -> None:
    st.write(f"### Contacto: {contact.name} @ {contact.company or '?'}")

    # Use a container for the form
    form_container = st.container()

    if st.session_state.gen_message_result is None:
        with form_container:
            template_type = st.radio(
                "Template type",
                options=[
                    OutreachTemplateType.A_INHOUSE,
                    OutreachTemplateType.B_BOUTIQUE,
                    OutreachTemplateType.C_SENIOR,
                    OutreachTemplateType.D_FOLLOWUP,
                ],
                index=0,
            )
            research_notes = st.text_area(
                "Research notes (min 20 chars)",
                help="Add specific details about the contact or company to personalize the message.",
            )
            language = st.radio("Language", options=["en", "es"], index=0)

            if st.button("Generar", type="primary"):
                if len(research_notes) < 20:
                    st.error("Research notes must be at least 20 characters long.")
                else:
                    with st.spinner("Generando mensaje con Claude Sonnet..."):
                        settings = Settings()  # type: ignore[call-arg]
                        llm_client = AnthropicLLMClient(
                            api_key=settings.ANTHROPIC_API_KEY.get_secret_value()
                        )
                        try:
                            with get_session() as session:
                                # Fetch parent message if follow-up
                                parent_message = None
                                if template_type == OutreachTemplateType.D_FOLLOWUP:
                                    msg_repo = OutreachMessageRepo(session)
                                    messages = msg_repo.list_by_contact(contact.id)
                                    # Find latest sent message
                                    parent_message = next(
                                        (
                                            m
                                            for m in messages
                                            if m.status == OutreachMessageStatus.SENT
                                        ),
                                        None,
                                    )

                                message = asyncio.run(
                                    generate_message(
                                        contact=contact,
                                        template_type=template_type,
                                        research_notes=research_notes,
                                        llm_client=llm_client,
                                        session=session,
                                        target_language=language,
                                        parent_message=parent_message,
                                    )
                                )
                                # Store only ID and body to avoid session state issues with SQLAlchemy objects
                                st.session_state.gen_message_result = {
                                    "id": message.id,
                                    "body": message.body,
                                }
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error generating message: {e}")

    else:
        # Show result
        result = st.session_state.gen_message_result
        st.write("### Mensaje Generado")
        edited_body = st.text_area("Cuerpo del mensaje", value=result["body"], height=300)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Marcar como Enviado", type="primary"):
                with get_session() as session:
                    repo = OutreachMessageRepo(session)
                    # Update body if edited
                    repo.update_body(result["id"], edited_body)
                    repo.mark_sent(result["id"])
                    session.commit()
                st.success("Marcado como enviado.")
                st.cache_data.clear()
                st.session_state.show_gen_modal = False
                st.session_state.gen_message_result = None
                time.sleep(1)
                st.rerun()

        with c2:
            # Note: streamlit doesn't have a direct copy button,
            # but we can use st.code which has a copy button.
            st.write("Para copiar:")
            st.code(edited_body, language="text")

        with c3:
            if st.button("Descartar"):
                with get_session() as session:
                    repo = OutreachMessageRepo(session)
                    repo.mark_discarded(result["id"])
                    session.commit()
                st.info("Mensaje descartado.")
                st.session_state.show_gen_modal = False
                st.session_state.gen_message_result = None
                st.rerun()

    if st.button("Cerrar"):
        st.session_state.show_gen_modal = False
        st.session_state.gen_message_result = None
        st.rerun()


@st.dialog("Importar Contactos desde CSV")
def import_csv_dialog() -> None:
    uploaded_file = st.file_uploader("Elige un archivo CSV", type="csv")
    if uploaded_file is not None:
        try:
            # Read first few lines for preview
            df_preview = pd.read_csv(uploaded_file)
            st.write("### Vista previa (primeras 5 filas)")
            st.dataframe(df_preview.head(5))

            if st.button("Confirmar Importación", type="primary"):
                # We need to save the file temporarily or pass the content
                # OutreachRepo.bulk_import_from_csv expects a path.
                # For simplicity in this dashboard, let's write to a temp file
                import tempfile
                import os

                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    # Seek back to start
                    uploaded_file.seek(0)
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name

                try:
                    with get_session() as session:
                        repo = OutreachRepo(session)
                        imported, duplicates = repo.bulk_import_from_csv(tmp_path)
                        session.commit()
                        st.success(f"Importados: {imported}, Duplicados omitidos: {duplicates}")
                        st.cache_data.clear()
                        time.sleep(2)
                        st.session_state.show_import_modal = False
                        st.rerun()
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")

    if st.button("Cancelar"):
        st.session_state.show_import_modal = False
        st.rerun()


st.header("💌 Outreach")

# --- Bulk Actions Buttons ---
col_a1, col_a2, col_a3 = st.columns([0.2, 0.2, 0.6])
with col_a1:
    if st.button("📥 Importar CSV"):
        st.session_state.show_import_modal = True
        st.rerun()

with col_a2:
    if contacts:
        # Generate CSV for download
        output = io.StringIO()
        writer = pd.DataFrame(
            [
                {
                    "name": c.name,
                    "company": c.company,
                    "role": c.role,
                    "linkedin_url": c.linkedin_url,
                    "email": c.email,
                    "market": c.market,
                    "specialty_stack": c.specialty_stack,
                    "quality_score": c.quality_score,
                    "status": c.status,
                    "notes": c.notes,
                }
                for c in contacts
            ]
        ).to_csv(index=False)
        st.download_button(
            label="📤 Exportar CSV",
            data=writer,
            file_name=f"outreach_contacts_{date.today()}.csv",
            mime="text/csv",
        )

if st.session_state.show_import_modal:
    import_csv_dialog()

if st.session_state.show_note_modal and st.session_state.contact_for_note:
    add_note_dialog(st.session_state.contact_for_note)

if st.session_state.show_gen_modal and st.session_state.contact_for_gen:
    generate_message_dialog(st.session_state.contact_for_gen)

col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
col_m1.metric("New", metrics.get("status_new", 0))
col_m2.metric("Contacted", metrics.get("status_contacted", 0))
col_m3.metric("Warm", metrics.get("status_warm", 0))
col_m4.metric("Replied", metrics.get("status_replied", 0))
col_m5.metric("Pending Follow-ups", metrics.get("pending_followups", 0), delta_color="inverse")


if not contacts:
    st.info("No se encontraron contactos con los filtros actuales.")
else:
    st.write(f"Mostrando {len(contacts)} contactos.")

    # Prepare data for editor
    contact_rows = []
    for c in contacts:
        # Get last message status
        last_msg_info = "-"
        if c.messages:
            # Sort messages by created_at
            sorted_msgs = sorted(c.messages, key=lambda x: x.created_at, reverse=True)
            last_msg = sorted_msgs[0]
            last_msg_info = f"{last_msg.status.upper()} ({last_msg.created_at.strftime('%m-%d')})"

        contact_rows.append(
            {
                "id": c.id,
                "Name": c.name,
                "Company": c.company or "",
                "Role": c.role or "",
                "Market": c.market or "",
                "Status": c.status,
                "Last Message": last_msg_info,
                "Score": c.quality_score or 0,
                "Notes": c.notes or "",
                "Last Contact": c.last_contacted_at.strftime("%Y-%m-%d")
                if c.last_contacted_at
                else "-",
                "Count": c.contact_count,
                "LinkedIn": c.linkedin_url or "",
            }
        )
    df_contacts = pd.DataFrame(contact_rows)

    edited_df = st.data_editor(
        df_contacts,
        column_config={
            "id": None,  # Hide ID
            "LinkedIn": st.column_config.LinkColumn("LinkedIn"),
            "Score": st.column_config.NumberColumn(
                "Score",
                help="Quality score (1-10)",
                min_value=0,
                max_value=10,
                step=1,
            ),
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=[s.value for s in OutreachStatus],
            ),
        },
        disabled=[
            "Name",
            "Company",
            "Role",
            "Market",
            "Last Message",
            "Last Contact",
            "Count",
            "LinkedIn",
        ],
        hide_index=True,
        use_container_width=True,
        key="outreach_editor",
    )

    if st.button("Guardar Cambios Inline"):
        with get_session() as session:
            repo = OutreachRepo(session)
            changes_count = 0
            # Identify changes by comparing with original list
            for _, row in edited_df.iterrows():
                contact_id = row["id"]
                # Find original contact
                original = next((c for c in contacts if c.id == contact_id), None)
                if original:
                    has_changes = False
                    if original.notes != row["Notes"]:
                        original.notes = row["Notes"]
                        has_changes = True
                    if original.quality_score != row["Score"]:
                        original.quality_score = row["Score"]
                        has_changes = True
                    if str(original.status) != str(row["Status"]):
                        original.status = row["Status"]
                        has_changes = True

                    if has_changes:
                        session.merge(original)
                        changes_count += 1

            if changes_count > 0:
                session.commit()
                st.success(f"Se actualizaron {changes_count} contactos.")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()
            else:
                st.info("No se detectaron cambios.")

    st.divider()
    st.subheader("Acciones Rápidas")

    # We'll use a selection mechanism or just buttons for each contact in a list
    # for individual actions that are not notes/score.
    for contact in contacts:
        is_focused = st.query_params.get("focus") == str(contact.id)
        border_style = "2px solid #ff4b4b" if is_focused else None

        with st.container(border=True):
            if is_focused:
                st.markdown(
                    f"""
                    <div style="border: {border_style}; border-radius: 0.5rem; padding: 1px; margin-bottom: -1px;">
                    """,
                    unsafe_allow_html=True,
                )
            c1, c2, c3 = st.columns([0.4, 0.4, 0.2])
            with c1:
                st.write(f"**{contact.name}** @ {contact.company or '?'}")
                st.caption(
                    f"{contact.role or ''} | {contact.status} | Score: {contact.quality_score or '?'}"
                )
            with c2:
                # Per-contact action buttons
                b_col1, b_col2, b_col3, b_col4 = st.columns(4)

                with b_col1:
                    if st.button("📞", key=f"cnt_{contact.id}", help="Mark Contacted"):
                        with get_session() as session:
                            repo = OutreachRepo(session)
                            repo.mark_contacted(contact.id)
                            session.commit()
                            st.cache_data.clear()
                            st.success("Marcado como contactado.")
                            time.sleep(0.5)
                            st.rerun()

                with b_col2:
                    if st.button("💬", key=f"replied_{contact.id}", help="Mark Replied"):
                        with get_session() as session:
                            repo = OutreachRepo(session)
                            repo.update(contact.id, status=OutreachStatus.REPLIED)
                            session.commit()
                            st.cache_data.clear()
                            st.rerun()

                with b_col3:
                    if st.button("🔥", key=f"warm_{contact.id}", help="Mark Warm"):
                        with get_session() as session:
                            repo = OutreachRepo(session)
                            repo.update(contact.id, status=OutreachStatus.WARM)
                            session.commit()
                            st.cache_data.clear()
                            st.rerun()

                with b_col4:
                    if st.button("📝", key=f"note_{contact.id}", help="Add Note"):
                        st.session_state.show_note_modal = True
                        st.session_state.contact_for_note = contact
                        st.rerun()

            with c3:
                l_col1, l_col2 = st.columns(2)
                with l_col1:
                    if contact.linkedin_url:
                        st.link_button("🔗", contact.linkedin_url, help="Open LinkedIn")
                    else:
                        st.button("🔗", disabled=True)
                with l_col2:
                    if st.button("🤖", key=f"gen_{contact.id}", help="Generate Message"):
                        st.session_state.show_gen_modal = True
                        st.session_state.contact_for_gen = contact
                        st.session_state.gen_message_result = None
                        st.rerun()

            with st.expander("Ver Cronograma de Mensajes"):
                if not contact.messages:
                    st.info("No hay mensajes registrados para este contacto.")
                else:
                    # Sort messages by created_at desc
                    sorted_messages = sorted(
                        contact.messages, key=lambda x: x.created_at, reverse=True
                    )
                    for msg in sorted_messages:
                        with st.container(border=True):
                            m_col1, m_col2 = st.columns([0.8, 0.2])
                            with m_col1:
                                st.write(f"**{msg.created_at.strftime('%Y-%m-%d %H:%M')}**")
                                st.caption(
                                    f"Tipo: {msg.template_type} | Version: {msg.template_version or '?'}"
                                )
                                status_color = {
                                    OutreachMessageStatus.DRAFT: "gray",
                                    OutreachMessageStatus.SENT: "blue",
                                    OutreachMessageStatus.REPLIED: "green",
                                    OutreachMessageStatus.GHOSTED: "red",
                                    OutreachMessageStatus.DISCARDED: "orange",
                                }.get(msg.status, "black")
                                st.markdown(f"Status: :{status_color}[{msg.status.upper()}]")
                            with m_col2:
                                if msg.cost_usd:
                                    st.caption(f"Cost: ${msg.cost_usd:.4f}")

                            st.text_area(
                                "Contenido",
                                value=msg.body,
                                height=150,
                                key=f"msg_body_{msg.id}",
                                disabled=True,
                            )
                            if msg.research_notes:
                                with st.expander("Research Notes"):
                                    st.write(msg.research_notes)

            if is_focused:
                st.markdown("</div>", unsafe_allow_html=True)
