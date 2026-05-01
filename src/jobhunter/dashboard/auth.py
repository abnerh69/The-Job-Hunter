import asyncio
import streamlit as st
from jobhunter.config import Settings
from datetime import datetime, timedelta
from jobhunter.db.session import get_session
from jobhunter.db.repos.security import SecurityRepo
from jobhunter.notify.telegram import TelegramNotifier
from jobhunter.notify.base import NotificationMessage
import structlog

logger = structlog.get_logger(__name__)


def get_remote_ip() -> str:
    """
    Retrieves the remote IP address from Streamlit headers.
    """
    # Streamlit context contains headers
    headers = st.context.headers

    # Try common proxy headers first
    if "X-Forwarded-For" in headers:
        return headers["X-Forwarded-For"].split(",")[0].strip()
    if "X-Real-Ip" in headers:
        return headers["X-Real-Ip"]

    # Fallback to remote_ip if available (depending on streamlit version/config)
    # In recent versions st.context.headers might not have it if not behind proxy
    # but we don't have many options here.
    return "127.0.0.1"


async def send_security_alert(message: str) -> None:
    """
    Sends a security alert via Telegram.
    """
    notifier = TelegramNotifier()
    settings = Settings()  # type: ignore[call-arg]
    if notifier.is_enabled(settings):
        notification = NotificationMessage(
            channel="telegram", subject="🛡️ Security Alert", body_text=message
        )
        await notifier.send(notification)


def check_password() -> bool:
    """Returns `True` if the user had the correct password."""

    remote_ip = get_remote_ip()
    user_agent = st.context.headers.get("User-Agent")

    with get_session() as session:
        repo = SecurityRepo(session)

        # 1. Check if IP is currently blocked
        if repo.is_ip_blocked(remote_ip):
            st.error("🚫 Access denied. Too many failed attempts. Try again later.")
            return False

        def password_entered() -> None:
            """Checks whether a password entered by the user is correct."""
            settings = Settings()  # type: ignore[call-arg]

            with get_session() as session_inner:
                repo_inner = SecurityRepo(session_inner)

                # Double check block inside callback
                if repo_inner.is_ip_blocked(remote_ip):
                    return

                if st.session_state["password"] == settings.DASHBOARD_PASSWORD.get_secret_value():
                    # Check for new IP before recording success
                    is_new = repo_inner.is_new_ip(remote_ip)

                    repo_inner.record_attempt(remote_ip, "success", user_agent)

                    st.session_state["password_correct"] = True
                    st.session_state["last_login"] = datetime.now()
                    del st.session_state["password"]  # don't store password

                    if is_new:
                        logger.warning(
                            "security_event", event_type="login_from_new_ip", ip_address=remote_ip
                        )
                        asyncio.run(
                            send_security_alert(f"🔓 Successful login from new IP: {remote_ip}")
                        )
                else:
                    repo_inner.record_attempt(remote_ip, "failure", user_agent)
                    st.session_state["password_correct"] = False

                    # Check rate limits
                    # 5 failures in 15 mins -> 1h block
                    fail_15m = repo_inner.get_failed_attempts_count(remote_ip, 15)
                    if fail_15m >= 5:
                        repo_inner.block_ip(remote_ip, 1, "Max 5 failures in 15m")
                        asyncio.run(
                            send_security_alert(
                                f"🚫 IP Blocked (1h): {remote_ip} after {fail_15m} failed attempts."
                            )
                        )

                    # 3 failures in 1 hour (aggregate) -> longer block if repeat?
                    # Requirement says: "Max 3 intentos fallidos en 1 hora -> CAPTCHA o bloqueo más largo."
                    # Let's say 24h block for 10 failures in 1h or just follow the requirement strictly:
                    fail_1h = repo_inner.get_failed_attempts_count(remote_ip, 60)
                    if fail_1h >= 10:  # Using 10 as "longer" threshold or just escalating
                        repo_inner.block_ip(remote_ip, 24, "Max 10 failures in 1h")
                        asyncio.run(
                            send_security_alert(
                                f"🚨 IP Blocked (24h): {remote_ip} after {fail_1h} failed attempts."
                            )
                        )
                    elif fail_1h >= 3:
                        # For 3 failures in 1h, requirement says "CAPTCHA or longer block"
                        # Since we don't have CAPTCHA easily, let's block for 3h
                        repo_inner.block_ip(remote_ip, 3, "Max 3 failures in 1h")
                        asyncio.run(
                            send_security_alert(
                                f"⚠️ IP Blocked (3h): {remote_ip} after {fail_1h} failed attempts."
                            )
                        )

                    # Multi-IP scan detection
                    distinct_ips = repo_inner.get_distinct_failed_ips_count(60)
                    if distinct_ips >= 10:
                        asyncio.run(
                            send_security_alert(
                                f"🚨 Possible distributed scan detected: {distinct_ips} distinct IPs with failed attempts in the last hour."
                            )
                        )

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
