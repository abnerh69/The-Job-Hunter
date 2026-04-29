import streamlit as st
from jobhunter.config import Settings
from datetime import datetime, timedelta


def check_password() -> bool:
    """Returns `True` if the user had the correct password."""

    def password_entered() -> None:
        """Checks whether a password entered by the user is correct."""
        settings = Settings()  # type: ignore[call-arg]
        if st.session_state["password"] == settings.DASHBOARD_PASSWORD.get_secret_value():
            st.session_state["password_correct"] = True
            st.session_state["last_login"] = datetime.now()
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct, check timeout
        settings = Settings()  # type: ignore[call-arg]
        last_login = st.session_state.get("last_login")
        if last_login:
            if datetime.now() - last_login > timedelta(
                minutes=settings.DASHBOARD_SESSION_TIMEOUT_MINUTES
            ):
                st.session_state["password_correct"] = False
                st.rerun()
                return False
        return True


def require_auth() -> None:
    """Redirects to login if not authenticated."""
    if not check_password():
        st.stop()


def logout() -> None:
    """Logs out the user."""
    st.session_state["password_correct"] = False
    st.rerun()
