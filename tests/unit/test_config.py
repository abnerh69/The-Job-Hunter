import os
from unittest import mock

import pytest
from pydantic import SecretStr, ValidationError

from jobhunter.config import Settings


def test_settings_parsing_from_env() -> None:
    """Verify that environment variables correctly override defaults and are parsed."""
    env_vars = {
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "ANTHROPIC_API_KEY": "test-key",
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_CHAT_ID": "12345",
        "SMTP_USER": "smtp-user",
        "SMTP_PASSWORD": "smtp-password",
        "DIGEST_TO_EMAIL": "digest@example.com",
        "DASHBOARD_PASSWORD": "dash-password",
    }
    with mock.patch.dict(os.environ, env_vars):
        # We clear the env_file in model_config for testing to ensure it only reads from env
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.DATABASE_URL == env_vars["DATABASE_URL"]
        assert settings.ANTHROPIC_API_KEY.get_secret_value() == env_vars["ANTHROPIC_API_KEY"]
        assert settings.TELEGRAM_BOT_TOKEN is not None
        assert settings.TELEGRAM_BOT_TOKEN.get_secret_value() == env_vars["TELEGRAM_BOT_TOKEN"]
        assert settings.TELEGRAM_CHAT_ID == env_vars["TELEGRAM_CHAT_ID"]
        assert settings.SMTP_USER == env_vars["SMTP_USER"]
        assert settings.SMTP_PASSWORD is not None
        assert settings.SMTP_PASSWORD.get_secret_value() == env_vars["SMTP_PASSWORD"]
        assert settings.DIGEST_TO_EMAIL == env_vars["DIGEST_TO_EMAIL"]


def test_settings_missing_required() -> None:
    """Verify that missing required fields raise ValidationError."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_default_values() -> None:
    """Verify that default values are used when not provided in env."""
    with mock.patch.dict(
        os.environ, {"ANTHROPIC_API_KEY": "some-key", "DASHBOARD_PASSWORD": "some-password"}, clear=True
    ):
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.DATABASE_URL == "sqlite:///./jobhunter.db"
        assert settings.TELEGRAM_BOT_TOKEN is None
        assert settings.TELEGRAM_CHAT_ID is None


def test_safe_dict_masks_secrets() -> None:
    """Verify that safe_dict() masks sensitive information."""
    settings = Settings(
        ANTHROPIC_API_KEY=SecretStr("secret-api-key"),
        TELEGRAM_BOT_TOKEN=SecretStr("secret-bot-token"),
        SMTP_PASSWORD=SecretStr("secret-smtp-password"),
        DASHBOARD_PASSWORD=SecretStr("secret-dash-password"),
    )
    safe_settings = settings.safe_dict()
    assert safe_settings["ANTHROPIC_API_KEY"] == "***"
    assert safe_settings["TELEGRAM_BOT_TOKEN"] == "***"
    assert safe_settings["SMTP_PASSWORD"] == "***"
    assert safe_settings["DASHBOARD_PASSWORD"] == "***"
    assert "secret" not in str(safe_settings)
