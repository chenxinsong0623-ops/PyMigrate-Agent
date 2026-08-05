import io
import json
import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.core.logging import configure_logging


@pytest.fixture
def restore_migrationlens_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("migrationlens")
    handler_marker = "_migrationlens_json_handler"
    original_owned_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, handler_marker, False)
    ]
    original_level = logger.level
    original_propagate = logger.propagate
    original_disabled = logger.disabled
    for handler in original_owned_handlers:
        logger.removeHandler(handler)

    yield logger

    for handler in list(logger.handlers):
        if getattr(handler, handler_marker, False):
            logger.removeHandler(handler)
            handler.close()
    for handler in original_owned_handlers:
        logger.addHandler(handler)
    logger.setLevel(original_level)
    logger.propagate = original_propagate
    logger.disabled = original_disabled


def _records(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_configured_logger_emits_parseable_json_with_common_fields(
    restore_migrationlens_logger: logging.Logger,
) -> None:
    stream = io.StringIO()
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="INFO",
    )

    logger = configure_logging(settings, stream=stream)
    logger.info("服务已启动")

    records = _records(stream)
    assert logger is restore_migrationlens_logger
    assert len(records) == 1

    record = records[0]
    assert {
        "timestamp",
        "level",
        "logger",
        "event",
        "service",
        "environment",
    } <= record.keys()
    assert record["level"] == "INFO"
    assert record["logger"] == "migrationlens"
    assert record["event"] == "服务已启动"
    assert record["service"] == "MigrationLens"
    assert record["environment"] == "test"
    datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))


def test_reconfiguring_logging_keeps_one_handler_and_one_record(
    restore_migrationlens_logger: logging.Logger,
) -> None:
    stream = io.StringIO()
    settings = Settings(_env_file=None, environment="test")

    first_logger = configure_logging(settings, stream=stream)
    second_logger = configure_logging(settings, stream=stream)
    second_logger.warning("日志仅配置一次")

    assert first_logger is second_logger
    assert first_logger is restore_migrationlens_logger
    owned_handlers = [
        handler
        for handler in second_logger.handlers
        if getattr(handler, "_migrationlens_json_handler", False)
    ]
    assert len(owned_handlers) == 1
    assert [record["event"] for record in _records(stream)] == ["日志仅配置一次"]


def test_structured_logging_only_adds_safe_sqlite_failure_context(
    restore_migrationlens_logger: logging.Logger,
) -> None:
    stream = io.StringIO()
    settings = Settings(_env_file=None, environment="test")

    logger = configure_logging(settings, stream=stream)
    logger.error(
        "sqlite_initialization_failed",
        extra={
            "component": "sqlite",
            "error_type": "OperationalError",
            "database_path": "不应出现在日志中的路径",
        },
    )

    record = _records(stream)[0]
    assert record["event"] == "sqlite_initialization_failed"
    assert record["component"] == "sqlite"
    assert record["error_type"] == "OperationalError"
    assert "database_path" not in record
    assert "exception" not in record
    assert "traceback" not in record
