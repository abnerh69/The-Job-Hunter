import streamlit as st
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from jobhunter.onboarding.resume_ingestor import ResumeData, ParsedExperience
from jobhunter.onboarding.profile_generator import ProfileUserInputs
from jobhunter.onboarding.cv_variant_generator import VariantSpec
from jobhunter.onboarding.salary_proposer import SalaryProposal
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.dashboard.auth import require_auth
from jobhunter.db.session import get_session
from jobhunter.db.repos.candidate_profile import CandidateProfileRepo

# Page configuration
st.set_page_config(
    page_title="Onboarding Wizard",
    page_icon="🎯",
    layout="wide",
)

# Authentication
require_auth()


class OnboardingState(BaseModel):
    step: int = 1
    resume_data: Optional[ResumeData] = None
    user_inputs: Optional[ProfileUserInputs] = None
    profile_draft: Optional[Dict[str, Any]] = (
        None  # Using dict because CandidateProfile is not easily serializable in session_state
    )
    salary_proposal: Optional[SalaryProposal] = None
    variant_specs: List[VariantSpec] = Field(default_factory=list)
    generated_variants: List[Dict[str, Any]] = Field(default_factory=list)
    llm_costs: float = 0.0
    profile_id: Optional[uuid.UUID] = None
    is_edit_mode: bool = False


def init_state() -> None:
    if "onboarding_state" not in st.session_state:
        st.session_state.onboarding_state = OnboardingState()

    state = st.session_state.onboarding_state

    # Handle Edit Mode from query params
    params = st.query_params
    if "profile_id" in params and not state.is_edit_mode:
        profile_id = uuid.UUID(str(params["profile_id"]))
        with get_session() as session:
            repo = CandidateProfileRepo(session)
            profile = repo.get(profile_id)
            if profile:
                state.profile_id = profile.id
                state.is_edit_mode = True
                state.profile_draft = {
                    "name": profile.name,
                    "seniority": profile.seniority,
                    "years_experience": profile.years_experience,
                    "primary_stack": profile.primary_stack,
                    "secondary_stack": profile.secondary_stack,
                    "domains": profile.domains,
                    "positive_signals": profile.positive_signals,
                    "soft_negatives": profile.soft_negatives,
                }
                state.user_inputs = ProfileUserInputs(
                    country=profile.country or "",
                    work_authorization=profile.work_authorization or "",
                    timezone_home=profile.timezone_home or "CET",
                    overlap_max_hours_cet=profile.overlap_max_hours_cet or 8,
                    contract_preferences=profile.contract_preferences or [],
                    hard_blockers=profile.hard_blockers or [],
                    payment_methods_ok=profile.payment_methods_ok or [],
                    profile_name=profile.name,
                )
                if profile.compensation:
                    state.salary_proposal = SalaryProposal(**profile.compensation)

                # Load variants
                from jobhunter.db.repos.cv_variant import CVVariantRepo

                cv_repo = CVVariantRepo(session)
                variants = cv_repo.list_by_profile(profile.id)
                state.generated_variants = []
                state.variant_specs = []
                for v in variants:
                    state.variant_specs.append(
                        VariantSpec(
                            name=v.name,
                            display_name=v.display_name or v.name,
                            target_role_keywords=v.target_role_keywords or [],
                            target_stack=v.target_stack or [],
                            target_seniority=v.target_seniority,
                            angle_description="",  # Not stored in DB
                        )
                    )
                    state.generated_variants.append(
                        {
                            "name": v.name,
                            "display_name": v.display_name,
                            "raw_markdown": v.raw_markdown,
                            "target_role_keywords": v.target_role_keywords,
                            "target_stack": v.target_stack,
                            "target_seniority": v.target_seniority,
                            "summary": v.summary,
                            "skills": v.skills,
                            "experiences": [
                                {
                                    "role": exp.role,
                                    "company": exp.company,
                                    "start_date": exp.start_date,
                                    "end_date": exp.end_date,
                                    "bullets": exp.bullets,
                                }
                                for exp in v.experiences
                            ],
                        }
                    )
                # In edit mode, we can allow skipping to specific steps
                # but let's keep it sequential for now or allow jumps via a sidebar if needed.


def render_step_indicator(current_step: int) -> None:
    steps = [
        "Upload Resume",
        "Review Extraction",
        "Personal Context",
        "Career Angle",
        "Salary Proposal",
        "CV Variants",
        "Confirm & Save",
    ]

    state = st.session_state.onboarding_state

    if state.is_edit_mode:
        # In edit mode, allow jumping between steps
        st.markdown("### 🛠 Edit Mode: Jump to Step")
        cols = st.columns(len(steps))
        for i, step_name in enumerate(steps):
            if cols[i].button(f"{i + 1}", key=f"jump_step_{i}", help=step_name):
                state.step = i + 1
                st.rerun()
    else:
        cols = st.columns(len(steps))
        for i, step_name in enumerate(steps):
            step_num = i + 1
            with cols[i]:
                if step_num == current_step:
                    st.markdown(f"**Step {step_num}: {step_name}**")
                    st.progress(1.0)
                elif step_num < current_step:
                    st.markdown(f"✅ Step {step_num}")
                    st.progress(1.0)
                else:
                    st.markdown(f"Step {step_num}: {step_name}")
                    st.progress(0.0)


def main() -> None:
    init_state()
    state = st.session_state.onboarding_state

    render_header()
    render_sidebar()

    st.title("🎯 Onboarding Wizard")

    render_step_indicator(state.step)
    st.divider()

    # Step content placeholders
    if state.step == 1:
        st.subheader("Step 1: Upload Resume")
        st.write("Upload your resume (PDF, MD, DOCX) to pre-fill your profile via AI extraction.")

        uploaded_file = st.file_uploader("Choose a file", type=["pdf", "md", "docx", "txt"])

        if uploaded_file is not None:
            if st.button("Ingest Resume"):
                with st.spinner("Extracting data with Claude Opus..."):
                    try:
                        import asyncio
                        from jobhunter.onboarding.resume_ingestor import ingest_resume

                        file_bytes = uploaded_file.read()
                        mime_type = uploaded_file.type

                        # In Streamlit we often need to run async in a sync context
                        resume_data = asyncio.run(ingest_resume(file_bytes, mime_type))
                        state.resume_data = resume_data
                        state.llm_costs += 0.015  # Estimated cost for Claude Opus
                        st.success("Resume ingested successfully!")
                        state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error ingesting resume: {e}")

        st.divider()
        if st.button("Skip and fill manually"):
            state.resume_data = ResumeData(
                name="",
                experiences=[],
                educations=[],
                skills=[],
                languages=[],
                raw_text="Manual entry",
            )
            state.step = 2
            st.rerun()

    elif state.step == 2:
        st.subheader("Step 2: Review Extraction")
        render_resume_review_form(state)

    elif state.step == 3:
        st.subheader("Step 3: Personal Context")
        st.write("Provide additional context that isn't in your resume.")

        with st.form("personal_context_form"):
            if state.user_inputs is None:
                state.user_inputs = ProfileUserInputs(
                    country="",
                    work_authorization="",
                    timezone_home="CET",
                    overlap_max_hours_cet=8,
                    profile_name=f"{state.resume_data.name}'s Profile"
                    if state.resume_data
                    else "My Profile",
                )

            ui = state.user_inputs
            ui.country = st.text_input("Country", ui.country)
            ui.work_authorization = st.text_input("Work Authorization", ui.work_authorization)
            ui.timezone_home = st.text_input("Timezone Home (e.g. CET, EST)", ui.timezone_home)
            ui.overlap_max_hours_cet = st.slider(
                "Max overlap hours with CET", 0, 12, ui.overlap_max_hours_cet
            )

            ui.contract_preferences = st.multiselect(
                "Contract Preferences",
                ["Full-time", "Contract", "Part-time", "Freelance"],
                default=ui.contract_preferences,
            )

            ui.payment_methods_ok = st.multiselect(
                "Acceptable Payment Methods",
                ["Bank Transfer", "Deel", "Remote.com", "Crypto", "Invoice"],
                default=ui.payment_methods_ok,
            )

            hard_blockers_text = st.text_area(
                "Hard Blockers (one per line)", "\n".join(ui.hard_blockers)
            )
            ui.hard_blockers = [b.strip() for b in hard_blockers_text.split("\n") if b.strip()]

            ui.profile_name = st.text_input("Profile Name (e.g. Python AI Senior)", ui.profile_name)

            if st.form_submit_button("Save Context"):
                state.user_inputs = ui
                st.success("Context saved!")

    elif state.step == 4:
        st.subheader("Step 4: Career Angle")
        if not state.resume_data or not state.user_inputs:
            st.warning("Please complete previous steps first.")
            state.step = 3
            st.rerun()

        if state.profile_draft is None:
            if st.button("Generate Profile Draft with Claude"):
                with st.spinner("Synthesizing profile..."):
                    try:
                        import asyncio
                        from jobhunter.onboarding.profile_generator import generate_profile
                        from jobhunter.llm.anthropic_client import AnthropicLLMClient
                        from jobhunter.config import Settings
                        from jobhunter.db.session import get_session

                        settings = Settings()  # type: ignore[call-arg]
                        client = AnthropicLLMClient(
                            api_key=settings.ANTHROPIC_API_KEY.get_secret_value()
                        )

                        with get_session() as session:
                            profile = asyncio.run(
                                generate_profile(
                                    resume_data=state.resume_data,
                                    user_inputs=state.user_inputs,
                                    session=session,
                                    llm_client=client,
                                )
                            )
                            # Convert to dict for session state
                            state.profile_draft = {
                                "name": profile.name,
                                "seniority": profile.seniority,
                                "years_experience": profile.years_experience,
                                "primary_stack": profile.primary_stack,
                                "secondary_stack": profile.secondary_stack,
                                "domains": profile.domains,
                                "positive_signals": profile.positive_signals,
                                "soft_negatives": profile.soft_negatives,
                            }
                            state.llm_costs += 0.003  # Estimated cost for Claude Sonnet
                            st.success("Profile synthesized!")
                            import time

                            time.sleep(2)  # Give time for user to see success
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error generating profile: {e}")

        if state.profile_draft:
            with st.form("career_angle_form"):
                pd = state.profile_draft
                pd["name"] = st.text_input("Profile Name", pd["name"])
                pd["seniority"] = st.text_input("Seniority", pd["seniority"])
                pd["years_experience"] = st.number_input(
                    "Years of Experience", value=pd["years_experience"] or 0
                )

                pd["primary_stack"] = st.text_area(
                    "Primary Stack (comma separated)", ", ".join(pd["primary_stack"] or [])
                ).split(",")
                pd["primary_stack"] = [s.strip() for s in pd["primary_stack"] if s.strip()]

                pd["secondary_stack"] = st.text_area(
                    "Secondary Stack (comma separated)", ", ".join(pd["secondary_stack"] or [])
                ).split(",")
                pd["secondary_stack"] = [s.strip() for s in pd["secondary_stack"] if s.strip()]

                pd["domains"] = st.text_area(
                    "Domains (comma separated)", ", ".join(pd["domains"] or [])
                ).split(",")
                pd["domains"] = [s.strip() for s in pd["domains"] if s.strip()]

                pd["positive_signals"] = st.text_area(
                    "Positive Signals (one per line)", "\n".join(pd["positive_signals"] or [])
                ).split("\n")
                pd["positive_signals"] = [s.strip() for s in pd["positive_signals"] if s.strip()]

                pd["soft_negatives"] = st.text_area(
                    "Soft Negatives (one per line)", "\n".join(pd["soft_negatives"] or [])
                ).split("\n")
                pd["soft_negatives"] = [s.strip() for s in pd["soft_negatives"] if s.strip()]

                if st.form_submit_button("Update Draft"):
                    state.profile_draft = pd
                    st.success("Draft updated!")

    elif state.step == 5:
        st.subheader("Step 5: Salary Proposal")
        if not state.profile_draft:
            st.warning("Please complete Step 4 first.")
            state.step = 4
            st.rerun()

        if state.salary_proposal is None:
            if st.button("Generate Salary Proposal with Claude"):
                with st.spinner("Calculating market ranges..."):
                    try:
                        import asyncio
                        from jobhunter.onboarding.salary_proposer import propose_salary
                        from jobhunter.llm.anthropic_client import AnthropicLLMClient
                        from jobhunter.config import Settings
                        from jobhunter.db.session import get_session
                        from jobhunter.db.models import CandidateProfile

                        settings = Settings()  # type: ignore[call-arg]
                        client = AnthropicLLMClient(
                            api_key=settings.ANTHROPIC_API_KEY.get_secret_value()
                        )

                        # Reconstruct temp profile for the service
                        temp_profile = CandidateProfile(
                            name=state.profile_draft["name"],
                            seniority=state.profile_draft["seniority"],
                            years_experience=state.profile_draft["years_experience"],
                            country=state.user_inputs.country,
                            primary_stack=state.profile_draft["primary_stack"],
                            contract_preferences=state.user_inputs.contract_preferences,
                        )

                        with get_session() as session:
                            proposal = asyncio.run(
                                propose_salary(
                                    profile=temp_profile,
                                    resume_data=state.resume_data,
                                    llm_client=client,
                                    session=session,
                                )
                            )
                            state.salary_proposal = proposal
                            state.llm_costs += 0.003  # Estimated cost for Claude Sonnet
                            st.success("Proposal generated!")
                            import time

                            time.sleep(2)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error generating salary proposal: {e}")

        if state.salary_proposal:
            sp = state.salary_proposal
            with st.expander("Rationale", expanded=True):
                st.write(sp.rationale)
                st.write(f"Confidence: {sp.confidence}")
                st.write(f"Data sources: {', '.join(sp.data_sources)}")

            with st.form("salary_form"):
                sp.currency = st.selectbox(
                    "Currency", ["USD", "EUR"], index=["USD", "EUR"].index(sp.currency)
                )
                sp.period = st.selectbox(
                    "Period", ["month", "year"], index=["month", "year"].index(sp.period)
                )
                sp.floor = st.number_input("Floor", value=sp.floor)
                sp.target = st.number_input("Target", value=sp.target)
                sp.stretch = st.number_input("Stretch", value=sp.stretch)

                if st.form_submit_button("Update Proposal"):
                    state.salary_proposal = sp
                    st.success("Proposal updated!")

    elif state.step == 7:
        st.subheader("Step 7: Confirm & Save")
        if not state.profile_draft:
            st.warning("Please complete Step 4 first.")
            state.step = 4
            st.rerun()

        st.write("Review your profile and variants before saving.")

        with st.expander("Profile Details", expanded=True):
            st.json(state.profile_draft)
            st.json(state.user_inputs.model_dump() if state.user_inputs else {})
            if state.salary_proposal:
                st.json(state.salary_proposal.model_dump())

        st.write(f"Generated Variants: {len(state.generated_variants)}")
        for gv in state.generated_variants:
            with st.expander(f"Variant: {gv['display_name'] or gv['name']}"):
                st.markdown(gv["raw_markdown"])

        st.divider()
        # Query total LLM costs from the session/calls repo could be complex here,
        # but we can show at least what we tracked in state if we had tracked it.
        st.info(f"Total Estimated LLM Costs for this wizard session: ${state.llm_costs:.4f}")

        if st.button("🚀 ACTIVATE PROFILE", type="primary"):
            with st.spinner("Saving profile and variants..."):
                try:
                    from jobhunter.db.session import get_session
                    from jobhunter.db.repos.candidate_profile import CandidateProfileRepo
                    from jobhunter.db.repos.cv_variant import CVVariantRepo
                    from jobhunter.db.models import CandidateProfile, CVVariant, CVVariantExperience

                    with get_session() as session:
                        # Transactional save
                        repo = CandidateProfileRepo(session)
                        cv_repo = CVVariantRepo(session)

                        pd = state.profile_draft
                        ui = state.user_inputs
                        sp = state.salary_proposal

                        profile = CandidateProfile(
                            name=pd["name"],
                            seniority=pd["seniority"],
                            years_experience=pd["years_experience"],
                            country=ui.country,
                            work_authorization=ui.work_authorization,
                            timezone_home=ui.timezone_home,
                            overlap_max_hours_cet=ui.overlap_max_hours_cet,
                            primary_stack=pd["primary_stack"],
                            secondary_stack=pd["secondary_stack"],
                            domains=pd["domains"],
                            contract_preferences=ui.contract_preferences,
                            hard_blockers=ui.hard_blockers,
                            payment_methods_ok=ui.payment_methods_ok,
                            positive_signals=pd["positive_signals"],
                            soft_negatives=pd["soft_negatives"],
                            compensation=sp.model_dump() if sp else None,
                            is_active=True,
                        )

                        if state.is_edit_mode and state.profile_id:
                            # If edit mode, we might want to deactivate the old one or update it.
                            # Requirement says "Atomic transaction (perfil + N variants)".
                            # Let's deactivate existing ones first if editing.
                            old_profile = repo.get(state.profile_id)
                            if old_profile:
                                old_profile.is_active = False
                                session.add(old_profile)

                        repo.create(profile)
                        session.flush()  # Get profile ID

                        for gv in state.generated_variants:
                            variant = CVVariant(
                                profile_id=profile.id,
                                name=gv["name"],
                                display_name=gv["display_name"],
                                target_role_keywords=gv["target_role_keywords"],
                                target_stack=gv["target_stack"],
                                target_seniority=gv["target_seniority"],
                                summary=gv["summary"],
                                skills=gv["skills"],
                                raw_markdown=gv["raw_markdown"],
                            )

                            experiences = [
                                CVVariantExperience(
                                    role=e["role"],
                                    company=e["company"],
                                    start_date=e["start_date"],
                                    end_date=e["end_date"],
                                    bullets=e["bullets"],
                                    sort_order=i,
                                )
                                for i, e in enumerate(gv["experiences"])
                            ]
                            cv_repo.create_with_experiences(variant, experiences)

                        session.commit()
                        st.success("Profile and variants activated successfully!")
                        # Reset state
                        st.session_state.onboarding_state = OnboardingState()
                        st.balloons()
                        if st.button("Go to Dashboard"):
                            st.switch_page("streamlit_app.py")

                except Exception as e:
                    st.error(f"Error saving profile: {e}")

    elif state.step == 6:
        st.subheader("Step 6: CV Variants")
        render_variant_form(state)

    # Navigation
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    with col1:
        if state.step > 1:
            if st.button("Back"):
                state.step -= 1
                st.rerun()
    with col3:
        if state.step < 7:
            if st.button("Next"):
                state.step += 1
                st.rerun()


def render_resume_review_form(state: OnboardingState) -> None:
    """Renders the editable form for ResumeData review."""
    if not state.resume_data:
        return

    with st.form("resume_review_form"):
        rd = state.resume_data
        rd.name = st.text_input("Name", rd.name)
        rd.email = st.text_input("Email", rd.email or "")
        rd.phone = st.text_input("Phone", rd.phone or "")
        rd.location_raw = st.text_input("Location (Raw)", rd.location_raw or "")
        rd.summary = st.text_area("Summary", rd.summary or "")

        st.markdown("### Experiences")
        new_exps = []
        for i, exp in enumerate(rd.experiences):
            with st.expander(f"Experience {i + 1}: {exp.company}", expanded=False):
                role = st.text_input(f"Role {i}", exp.role, key=f"role_{i}")
                company = st.text_input(f"Company {i}", exp.company, key=f"company_{i}")
                dates = st.text_input(f"Dates {i}", exp.dates, key=f"dates_{i}")
                bullets = st.text_area(
                    f"Bullets {i} (one per line)", "\n".join(exp.bullets), key=f"bullets_{i}"
                )
                new_exps.append(
                    ParsedExperience(
                        role=role,
                        company=company,
                        dates=dates,
                        bullets=[b.strip() for b in bullets.split("\n") if b.strip()],
                    )
                )
        rd.experiences = new_exps

        st.markdown("### Skills & Languages")
        rd.skills = st.text_area("Skills (comma separated)", ", ".join(rd.skills)).split(",")
        rd.skills = [s.strip() for s in rd.skills if s.strip()]

        rd.languages = st.text_area("Languages (comma separated)", ", ".join(rd.languages)).split(
            ","
        )
        rd.languages = [lang.strip() for lang in rd.languages if lang.strip()]

        st.markdown("### Detection Info")
        rd.detected_seniority = st.selectbox(
            "Seniority",
            ["junior", "mid", "senior", "staff"],
            index=(
                ["junior", "mid", "senior", "staff"].index(rd.detected_seniority)
                if rd.detected_seniority in ["junior", "mid", "senior", "staff"]
                else 0
            ),
        )
        rd.detected_years_experience = st.number_input(
            "Years of Experience", value=rd.detected_years_experience or 0
        )
        rd.detected_primary_stack = st.text_area(
            "Primary Stack (comma separated)", ", ".join(rd.detected_primary_stack or [])
        ).split(",")
        rd.detected_primary_stack = [s.strip() for s in rd.detected_primary_stack if s.strip()]

        if st.form_submit_button("Save Changes"):
            state.resume_data = rd
            st.success("Changes saved!")


def render_variant_form(state: OnboardingState) -> None:
    """Renders the form for CV variants specification and generation."""
    if not state.profile_draft or not state.user_inputs or not state.resume_data:
        return

    st.write(
        "Define the CV variants you want to generate (e.g. Fullstack, Backend-only, Management)."
    )

    # Number of variants
    num_variants = st.number_input(
        "How many variants?", min_value=1, max_value=10, value=len(state.variant_specs) or 1
    )

    # Adjust variant_specs list size
    while len(state.variant_specs) < num_variants:
        state.variant_specs.append(
            VariantSpec(
                name=f"variant_{len(state.variant_specs) + 1}",
                display_name="",
                angle_description="",
                target_seniority=None,
            )
        )
    while len(state.variant_specs) > num_variants:
        state.variant_specs.pop()

    for i in range(num_variants):
        with st.expander(
            f"Variant {i + 1}: {state.variant_specs[i].display_name or 'Untitled'}",
            expanded=(i == 0),
        ):
            v = state.variant_specs[i]
            v.display_name = st.text_input(
                f"Display Name {i}", v.display_name, key=f"v_display_{i}"
            )
            v.name = v.display_name.lower().replace(" ", "_")
            v.target_role_keywords = st.text_area(
                f"Target Keywords {i} (comma separated)",
                ", ".join(v.target_role_keywords),
                key=f"v_keywords_{i}",
            ).split(",")
            v.target_role_keywords = [k.strip() for k in v.target_role_keywords if k.strip()]

            v.target_stack = st.text_area(
                f"Target Stack {i} (comma separated)",
                ", ".join(v.target_stack),
                key=f"v_stack_{i}",
            ).split(",")
            v.target_stack = [s.strip() for s in v.target_stack if s.strip()]

            v.angle_description = st.text_area(
                f"Angle Description {i}", v.angle_description, key=f"v_angle_{i}"
            )

            if st.button(f"Generate Variant {i + 1} with Claude", key=f"v_gen_btn_{i}"):
                with st.spinner(f"Generating variant {i + 1}..."):
                    try:
                        import asyncio
                        from jobhunter.onboarding.cv_variant_generator import generate_variant
                        from jobhunter.llm.anthropic_client import AnthropicLLMClient
                        from jobhunter.config import Settings
                        from jobhunter.db.session import get_session
                        from jobhunter.db.models import CandidateProfile

                        settings = Settings()  # type: ignore[call-arg]
                        client = AnthropicLLMClient(
                            api_key=settings.ANTHROPIC_API_KEY.get_secret_value()
                        )

                        # Reconstruct temp profile
                        temp_profile = CandidateProfile(
                            name=state.profile_draft["name"],
                            seniority=state.profile_draft["seniority"],
                            years_experience=state.profile_draft["years_experience"],
                            country=state.user_inputs.country,
                            primary_stack=state.profile_draft["primary_stack"],
                        )

                        with get_session() as session:
                            variant = asyncio.run(
                                generate_variant(
                                    profile=temp_profile,
                                    resume_data=state.resume_data,
                                    variant_spec=v,
                                    session=session,
                                    llm_client=client,
                                )
                            )

                            # Store generated variant in state
                            found = False
                            for gv in state.generated_variants:
                                if gv["name"] == variant.name:
                                    gv["raw_markdown"] = variant.raw_markdown
                                    found = True
                                    break
                            if not found:
                                state.generated_variants.append(
                                    {
                                        "name": variant.name,
                                        "display_name": variant.display_name,
                                        "raw_markdown": variant.raw_markdown,
                                        "target_role_keywords": variant.target_role_keywords,
                                        "target_stack": variant.target_stack,
                                        "target_seniority": variant.target_seniority,
                                        "summary": variant.summary,
                                        "skills": variant.skills,
                                        "experiences": [
                                            {
                                                "role": exp.role,
                                                "company": exp.company,
                                                "start_date": exp.start_date,
                                                "end_date": exp.end_date,
                                                "bullets": exp.bullets,
                                            }
                                            for exp in variant.experiences
                                        ],
                                    }
                                )
                            state.llm_costs += 0.003  # Estimated cost for Claude Sonnet
                            st.success(f"Variant {i + 1} generated!")
                            import time

                            time.sleep(2)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error generating variant: {e}")

            # Preview and Edit Markdown
            for gv in state.generated_variants:
                if gv["name"] == v.name:
                    gv["raw_markdown"] = st.text_area(
                        f"Markdown Preview {i}", gv["raw_markdown"], height=300, key=f"v_md_{i}"
                    )
                    break


if __name__ == "__main__":
    main()
