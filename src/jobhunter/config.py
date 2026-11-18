"""
Application configuration.

This module deliberately does NOT export a `settings = Settings()` singleton.
Each call-site instantiates `Settings()` locally when it needs config. See
`docs/adr/ADR-006-no-settings-singleton.md` for the rationale (test isolation,
fail-fast validation at the CLI boundary, distinct entry-point profiles).

Note: this is a known deviation from acceptance criterion E01-S05 in
`docs/Plan automatizado.../E_Backlog_Nivel_2_E1.md`. The underlying goal of
that story — a single typed config surface, no direct `os.environ` reads — is
still met.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings managed by Pydantic.
    Environment variables can override these values.
    """

    LOG_FORMAT: Literal["json", "pretty"] = "pretty"
    DATABASE_URL: str = "sqlite:///./jobhunter.db"
    LLM_PROVIDER: Literal["anthropic", "gemini", "agy_cli", "mock"] = "anthropic"
    ANTHROPIC_API_KEY: SecretStr | None = None
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    AGY_CLI_BIN: str = "agy"
    AGY_MODEL: str = "gemini-4-hydrogen-medium"
    CANDIDATE_PROFILE_PATH: Path | None = None
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

    BACKUP_STORAGE_PROVIDER: Literal["b2", "s3", "local"] = "local"
    BACKUP_STORAGE_BUCKET: str | None = None
    BACKUP_ACCESS_KEY: SecretStr | None = None
    BACKUP_SECRET_KEY: SecretStr | None = None
    BACKUP_ENDPOINT_URL: str | None = None
    BACKUP_RETENTION_WEEKS: int = 12

    GMAIL_CLIENT_ID: SecretStr | None = None
    GMAIL_CLIENT_SECRET: SecretStr | None = None
    GMAIL_REDIRECT_URI: str = "http://localhost:8765/oauth/callback"
    OAUTH_ENCRYPTION_KEY: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> Self:
        """Ensure required API key is set for the active LLM_PROVIDER."""
        if self.LLM_PROVIDER == "anthropic" and self.ANTHROPIC_API_KEY is None:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER='anthropic'")
        if self.LLM_PROVIDER == "gemini" and self.GEMINI_API_KEY is None:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER='gemini'")
        return self

    def safe_dict(self) -> dict[str, str | int | float | None]:
        """Returns a dictionary with sensitive values masked."""
        return {
            "LOG_FORMAT": self.LOG_FORMAT,
            "DATABASE_URL": self.DATABASE_URL,
            "LLM_PROVIDER": self.LLM_PROVIDER,
            "ANTHROPIC_API_KEY": "***" if self.ANTHROPIC_API_KEY else None,
            "GEMINI_API_KEY": "***" if self.GEMINI_API_KEY else None,
            "GEMINI_MODEL": self.GEMINI_MODEL,
            "AGY_MODEL": self.AGY_MODEL,
            "CANDIDATE_PROFILE_PATH": (
                str(self.CANDIDATE_PROFILE_PATH) if self.CANDIDATE_PROFILE_PATH else None
            ),
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
            "BACKUP_STORAGE_PROVIDER": self.BACKUP_STORAGE_PROVIDER,
            "BACKUP_STORAGE_BUCKET": self.BACKUP_STORAGE_BUCKET,
            "BACKUP_ACCESS_KEY": "***" if self.BACKUP_ACCESS_KEY else None,
            "BACKUP_SECRET_KEY": "***" if self.BACKUP_SECRET_KEY else None,
            "BACKUP_ENDPOINT_URL": self.BACKUP_ENDPOINT_URL,
            "BACKUP_RETENTION_WEEKS": self.BACKUP_RETENTION_WEEKS,
        }
