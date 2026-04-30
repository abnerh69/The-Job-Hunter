from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings managed by Pydantic.
    Environment variables can override these values.
    """

    LOG_FORMAT: Literal["json", "pretty"] = "pretty"
    DATABASE_URL: str = "sqlite:///./jobhunter.db"
    ANTHROPIC_API_KEY: SecretStr
    TELEGRAM_BOT_TOKEN: SecretStr | None = None
    TELEGRAM_CHAT_ID: str | None = None
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    DIGEST_TO_EMAIL: str | None = None

    LLM_MONTHLY_BUDGET_USD: float = 25.0
    COVER_LETTER_MODEL: str = "claude-opus-4-7"
    OUTREACH_MODEL: str = "claude-sonnet-4-6"
    CV_VARIANTS_DIR: Path = Path(".local/cv_variants")

    DASHBOARD_PASSWORD: SecretStr
    DASHBOARD_SESSION_TIMEOUT_MINUTES: int = 60

    GMAIL_CLIENT_ID: SecretStr | None = None
    GMAIL_CLIENT_SECRET: SecretStr | None = None
    GMAIL_REDIRECT_URI: str = "http://localhost:8765/oauth/callback"
    OAUTH_ENCRYPTION_KEY: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def safe_dict(self) -> dict[str, str | int | float | None]:
        """Returns a dictionary with sensitive values masked."""
        return {
            "LOG_FORMAT": self.LOG_FORMAT,
            "DATABASE_URL": self.DATABASE_URL,
            "ANTHROPIC_API_KEY": "***" if self.ANTHROPIC_API_KEY else None,
            "TELEGRAM_BOT_TOKEN": "***" if self.TELEGRAM_BOT_TOKEN else None,
            "TELEGRAM_CHAT_ID": self.TELEGRAM_CHAT_ID,
            "SMTP_HOST": self.SMTP_HOST,
            "SMTP_PORT": self.SMTP_PORT,
            "SMTP_USER": self.SMTP_USER,
            "SMTP_PASSWORD": "***" if self.SMTP_PASSWORD else None,
            "DIGEST_TO_EMAIL": self.DIGEST_TO_EMAIL,
            "LLM_MONTHLY_BUDGET_USD": self.LLM_MONTHLY_BUDGET_USD,
            "COVER_LETTER_MODEL": self.COVER_LETTER_MODEL,
            "OUTREACH_MODEL": self.OUTREACH_MODEL,
            "DASHBOARD_PASSWORD": "***" if self.DASHBOARD_PASSWORD else None,
            "DASHBOARD_SESSION_TIMEOUT_MINUTES": self.DASHBOARD_SESSION_TIMEOUT_MINUTES,
            "GMAIL_CLIENT_ID": "***" if self.GMAIL_CLIENT_ID else None,
            "GMAIL_CLIENT_SECRET": "***" if self.GMAIL_CLIENT_SECRET else None,
            "GMAIL_REDIRECT_URI": self.GMAIL_REDIRECT_URI,
            "OAUTH_ENCRYPTION_KEY": "***" if self.OAUTH_ENCRYPTION_KEY else None,
        }
