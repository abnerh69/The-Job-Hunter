from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings managed by Pydantic.
    Environment variables can override these values.
    """

    DATABASE_URL: str = "sqlite:///./jobhunter.db"
    ANTHROPIC_API_KEY: SecretStr
    TELEGRAM_BOT_TOKEN: SecretStr | None = None
    TELEGRAM_CHAT_ID: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    DIGEST_TO_EMAIL: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def safe_dict(self) -> dict[str, str | None]:
        """Returns a dictionary with sensitive values masked."""
        return {
            "DATABASE_URL": self.DATABASE_URL,
            "ANTHROPIC_API_KEY": "***" if self.ANTHROPIC_API_KEY else None,
            "TELEGRAM_BOT_TOKEN": "***" if self.TELEGRAM_BOT_TOKEN else None,
            "TELEGRAM_CHAT_ID": self.TELEGRAM_CHAT_ID,
            "SMTP_USER": self.SMTP_USER,
            "SMTP_PASSWORD": "***" if self.SMTP_PASSWORD else None,
            "DIGEST_TO_EMAIL": self.DIGEST_TO_EMAIL,
        }
