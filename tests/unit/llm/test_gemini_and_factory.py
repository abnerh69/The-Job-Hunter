import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

import jobhunter.sources  # noqa: F401
from jobhunter.config import Settings
from jobhunter.db.enums import LLMPurpose
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.llm.factory import create_llm_client
from jobhunter.llm.gemini_client import AgyCLILLMClient, GeminiLLMClient
from jobhunter.scoring.prompt import load_prompt
from jobhunter.sources.registry import get_all_sources


def test_sources_auto_registered() -> None:
    sources = get_all_sources()
    names = {cls.__name__ for cls in sources}
    assert {
        "ArbeitnowSource",
        "FourDayWeekSource",
        "RemoteOKSource",
        "WeWorkRemotelySource",
    }.issubset(names)


def test_create_llm_client_providers() -> None:
    s_gemini = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY=SecretStr("gem-key"),
        DASHBOARD_PASSWORD=SecretStr("pw"),
    )
    assert isinstance(create_llm_client(s_gemini), GeminiLLMClient)

    s_agy = Settings(
        LLM_PROVIDER="agy_cli",
        DASHBOARD_PASSWORD=SecretStr("pw"),
    )
    assert isinstance(create_llm_client(s_agy), AgyCLILLMClient)

    s_mock = Settings(
        LLM_PROVIDER="mock",
        DASHBOARD_PASSWORD=SecretStr("pw"),
    )
    client_mock = create_llm_client(s_mock)
    assert isinstance(client_mock, AnthropicLLMClient)
    assert client_mock._mock_mode is True


@pytest.mark.asyncio
async def test_gemini_client_complete_strips_fences() -> None:
    client = GeminiLLMClient(api_key="test-key", default_model="gemini-2.5-flash")
    fake_payload = {
        "candidates": [
            {
                "content": {"parts": [{"text": '```json\n{"fit_score": 85}\n```'}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30},
    }
    mock_response = MagicMock()
    mock_response.json.return_value = fake_payload
    mock_response.raise_for_status.return_value = None

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("jobhunter.llm.gemini_client.httpx.AsyncClient", return_value=mock_cm):
        res = await client.complete(
            system="sys",
            user="usr",
            model="claude-sonnet-4-6",
            purpose=LLMPurpose.SCORING,
        )

    assert res.model == "gemini-2.5-flash"
    assert res.text == '{"fit_score": 85}'
    assert res.input_tokens == 120
    assert res.output_tokens == 30
    assert res.cost_usd == 0.0


@pytest.mark.asyncio
async def test_agy_cli_client_complete() -> None:
    client = AgyCLILLMClient(cli_bin="agy", default_model="gemini-4-hydrogen-medium")
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b'```json\n{"ok": true}\n```', b""))

    with patch(
        "jobhunter.llm.gemini_client.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ) as exec_mock:
        res = await client.complete(
            system="sys",
            user="usr",
            model="claude-opus-4-7",
            purpose=LLMPurpose.SCORING,
        )

    assert res.model == "gemini-4-hydrogen-medium"
    assert json.loads(res.text) == {"ok": True}
    assert exec_mock.call_args.args[0] == "agy"


def test_load_prompt_with_external_profile(tmp_path: Path) -> None:
    profile = tmp_path / "client.yaml"
    profile.write_text("candidate_profile:\n  name: Test Client\n", encoding="utf-8")
    prompt = load_prompt(version="v1", profile_path=profile)
    assert "Test Client" in prompt.system_prompt
    assert "Abner Hernández" not in prompt.system_prompt
    assert asyncio.iscoroutinefunction(GeminiLLMClient.complete)
