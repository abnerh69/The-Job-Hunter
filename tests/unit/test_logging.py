import json
import os
import asyncio
from typing import Any
import structlog
from _pytest.capture import CaptureFixture
from jobhunter.log_config import configure_logging, with_correlation_id, get_logger

def test_log_structure_and_redaction(capsys: CaptureFixture[Any]) -> None:
    os.environ["LOG_FORMAT"] = "json"
    configure_logging()

    logger = get_logger("test_module")
    logger.info("test_event", password="secret_password", token="secret_token", api_key="secret_key", other="public")

    captured = capsys.readouterr()
    log_entry = json.loads(captured.out)

    assert log_entry["event"] == "test_event"
    assert log_entry["module"] == "test_module"
    assert log_entry["password"] == "****"
    assert log_entry["token"] == "****"
    assert log_entry["api_key"] == "****"
    assert log_entry["other"] == "public"
    assert "timestamp" in log_entry
    assert log_entry["level"] == "info"

def test_correlation_id_propagation(capsys: CaptureFixture[Any]) -> None:
    os.environ["LOG_FORMAT"] = "json"
    configure_logging()

    logger = get_logger("test_module")

    with with_correlation_id("test_cid"):
        logger.info("event_with_cid")

    captured = capsys.readouterr()
    log_entry = json.loads(captured.out)
    assert log_entry["correlation_id"] == "test_cid"

    logger.info("event_without_cid")
    captured = capsys.readouterr()
    log_entry = json.loads(captured.out)
    assert "correlation_id" not in log_entry

async def async_log(logger: Any) -> None:
    logger.info("async_event")

def test_correlation_id_async_propagation(capsys: CaptureFixture[Any]) -> None:
    os.environ["LOG_FORMAT"] = "json"
    configure_logging()

    logger = get_logger("test_module")

    async def main() -> None:
        with with_correlation_id("async_cid"):
            await async_log(logger)

    asyncio.run(main())

    captured = capsys.readouterr()
    log_entry = json.loads(captured.out)
    assert log_entry["correlation_id"] == "async_cid"

def test_correlation_id_from_env(capsys: CaptureFixture[Any]) -> None:
    os.environ["LOG_FORMAT"] = "json"
    os.environ["JOBHUNTER_CORRELATION_ID"] = "env_cid"
    configure_logging()

    logger = get_logger("test_module")
    logger.info("env_event")

    captured = capsys.readouterr()
    log_entry = json.loads(captured.out)
    assert log_entry["correlation_id"] == "env_cid"

    # Cleanup env for other tests if needed
    del os.environ["JOBHUNTER_CORRELATION_ID"]
