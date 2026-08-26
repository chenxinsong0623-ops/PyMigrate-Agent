import io
import json
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from app import SERVICE_NAME
from app.core.logging import JsonFormatter
from app.storage.sqlite import (
    SQLiteDatabase,
    SQLiteInitializationState,
    SQLiteNotInitializedError,
)


async def _table_names(path: Path) -> set[str]:
    async with aiosqlite.connect(path) as connection:
        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return {str(row[0]) for row in rows}


async def _metadata_rows(path: Path) -> dict[str, tuple[str, str]]:
    async with aiosqlite.connect(path) as connection:
        cursor = await connection.execute(
            """
            SELECT key, value, updated_at_utc
            FROM system_metadata
            ORDER BY key
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return {str(key): (str(value), str(updated_at)) for key, value, updated_at in rows}


def _json_logger(stream: io.StringIO) -> logging.Logger:
    logger = logging.Logger("migrationlens.sqlite.test", level=logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service=SERVICE_NAME, environment="test"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _json_records(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


@pytest.mark.asyncio
async def test_initialize_creates_v2_schema_metadata_and_ping_works(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "migrationlens.sqlite3"
    database = SQLiteDatabase(database_path, timeout_seconds=2.0)

    assert database.initialization_state is SQLiteInitializationState.NEW
    assert await database.initialize() is True
    assert database.initialization_state is SQLiteInitializationState.INITIALIZED
    assert database.initialization_error_type is None
    assert await database.ping() is True
    assert await database.read_metadata("schema_version") == "2"
    assert await database.read_metadata("document_index_status") == "not_built"
    assert await database.read_metadata("unknown_key") is None

    assert await database.initialize() is True
    assert await _table_names(database_path) == {
        "analyses",
        "reports",
        "system_metadata",
    }
    first_rows = await _metadata_rows(database_path)
    assert first_rows.keys() == {"document_index_status", "schema_version"}
    assert first_rows["document_index_status"][0] == "not_built"
    assert first_rows["schema_version"][0] == "2"
    assert all(updated_at for _, updated_at in first_rows.values())

    await database.close()
    await database.close()
    assert database.initialization_state is SQLiteInitializationState.CLOSED
    assert await _metadata_rows(database_path) == first_rows

    reopened_database = SQLiteDatabase(database_path, timeout_seconds=2.0)
    assert await reopened_database.initialize() is True
    assert await _metadata_rows(database_path) == first_rows
    await reopened_database.close()


@pytest.mark.asyncio
async def test_close_is_safe_before_initialization(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "unused.sqlite3", timeout_seconds=2.0)

    await database.close()
    await database.close()

    assert database.initialization_state is SQLiteInitializationState.CLOSED
    assert database.initialization_error_type is None
    assert await database.initialize() is False
    assert await database.ping() is False
    with pytest.raises(SQLiteNotInitializedError):
        await database.read_metadata("schema_version")


@pytest.mark.asyncio
async def test_initialization_failure_is_safe_and_cross_platform(
    tmp_path: Path,
) -> None:
    blocking_parent = tmp_path / "blocking_parent"
    original_contents = "这是普通文件，不是目录。"
    blocking_parent.write_text(original_contents, encoding="utf-8")
    database_path = blocking_parent / "migrationlens.sqlite3"
    stream = io.StringIO()
    database = SQLiteDatabase(
        database_path,
        timeout_seconds=2.0,
        logger=_json_logger(stream),
    )

    assert await database.initialize() is False
    assert blocking_parent.is_file()
    assert blocking_parent.read_text(encoding="utf-8") == original_contents
    assert database.initialization_state is SQLiteInitializationState.FAILED
    assert database.initialization_error_type
    assert await database.ping() is False
    with pytest.raises(SQLiteNotInitializedError):
        await database.read_metadata("document_index_status")

    records = _json_records(stream)
    assert len(records) == 1
    record = records[0]
    assert record["event"] == "sqlite_initialization_failed"
    assert record["component"] == "sqlite"
    assert record["error_type"] == database.initialization_error_type
    assert str(blocking_parent) not in stream.getvalue()
    assert "这是普通文件" not in stream.getvalue()
    assert "exception" not in record
    assert "traceback" not in record

    await database.close()
    await database.close()
    assert database.initialization_state is SQLiteInitializationState.CLOSED
    assert database.initialization_error_type == record["error_type"]


@pytest.mark.asyncio
async def test_sqlite_error_after_connect_is_safe_and_closes_partial_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "不应写入日志的 SQLite 异常原文"
    connection = SimpleNamespace(
        execute=AsyncMock(side_effect=sqlite3.OperationalError(sensitive_message)),
        close=AsyncMock(),
    )

    async def connect(*_args: object, **_kwargs: object) -> object:
        return connection

    monkeypatch.setattr(aiosqlite, "connect", connect)
    stream = io.StringIO()
    database = SQLiteDatabase(
        tmp_path / "migrationlens.sqlite3",
        timeout_seconds=2.0,
        logger=_json_logger(stream),
    )

    assert await database.initialize() is False
    assert database.initialization_state is SQLiteInitializationState.FAILED
    assert database.initialization_error_type == "OperationalError"
    connection.close.assert_awaited_once()

    record = _json_records(stream)[0]
    assert record["event"] == "sqlite_initialization_failed"
    assert record["component"] == "sqlite"
    assert record["error_type"] == "OperationalError"
    assert sensitive_message not in stream.getvalue()
    assert "exception" not in record

    assert await database.initialize() is False
    await database.close()
    await database.close()
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unexpected_failure_after_connect_propagates_and_closes_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = SimpleNamespace(
        execute=AsyncMock(side_effect=RuntimeError("未预期的编程错误")),
        close=AsyncMock(),
    )

    async def connect(*_args: object, **_kwargs: object) -> object:
        return connection

    monkeypatch.setattr(aiosqlite, "connect", connect)
    database = SQLiteDatabase(tmp_path / "migrationlens.sqlite3", timeout_seconds=2.0)

    with pytest.raises(RuntimeError, match="未预期的编程错误"):
        await database.initialize()

    assert database.initialization_state is SQLiteInitializationState.NEW
    assert database.initialization_error_type is None
    connection.close.assert_awaited_once()
    await database.close()
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_only_closes_initialized_connection_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table_cursor = SimpleNamespace(
        fetchone=AsyncMock(return_value=None),
        close=AsyncMock(),
    )
    metadata_cursor = SimpleNamespace(
        fetchone=AsyncMock(return_value=None),
        close=AsyncMock(),
    )
    connection = SimpleNamespace(
        execute=AsyncMock(
            side_effect=(
                None,
                None,
                None,
                table_cursor,
                None,
                metadata_cursor,
                None,
                None,
            )
        ),
        executemany=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        close=AsyncMock(),
    )

    async def connect(*_args: object, **_kwargs: object) -> object:
        return connection

    monkeypatch.setattr(aiosqlite, "connect", connect)
    database = SQLiteDatabase(tmp_path / "migrationlens.sqlite3", timeout_seconds=2.0)

    assert await database.initialize() is True
    await database.close()
    await database.close()

    connection.close.assert_awaited_once()
    assert database.initialization_state is SQLiteInitializationState.CLOSED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unexpected_error",
    [
        RuntimeError("未预期的编程错误"),
        KeyboardInterrupt(),
        SystemExit(),
    ],
)
async def test_initialize_does_not_swallow_unexpected_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unexpected_error: BaseException,
) -> None:
    def raise_unexpected(*_args: object, **_kwargs: object) -> None:
        raise unexpected_error

    monkeypatch.setattr(aiosqlite, "connect", raise_unexpected)
    database = SQLiteDatabase(tmp_path / "migrationlens.sqlite3", timeout_seconds=2.0)

    with pytest.raises(type(unexpected_error)):
        await database.initialize()

    assert database.initialization_state is SQLiteInitializationState.NEW
    assert database.initialization_error_type is None
    await database.close()


@pytest.mark.asyncio
async def test_document_index_status_write_commits_and_survives_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "index-status.sqlite3"
    database = SQLiteDatabase(database_path, timeout_seconds=2.0)
    assert await database.initialize() is True

    await database.write_document_index_status("ready")

    assert await database.read_metadata("document_index_status") == "ready"
    await database.close()

    reopened = SQLiteDatabase(database_path, timeout_seconds=2.0)
    assert await reopened.initialize() is True
    assert await reopened.read_metadata("document_index_status") == "ready"
    await reopened.close()


@pytest.mark.asyncio
async def test_document_index_status_write_requires_initialized_database(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "unused.sqlite3", timeout_seconds=2.0)

    with pytest.raises(SQLiteNotInitializedError):
        await database.write_document_index_status("ready")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["", "building", "READY", "ready'; DROP TABLE x"])
async def test_document_index_status_write_rejects_unknown_values(
    tmp_path: Path,
    status: str,
) -> None:
    database = SQLiteDatabase(tmp_path / "status.sqlite3", timeout_seconds=2.0)
    assert await database.initialize() is True

    with pytest.raises(ValueError):
        await database.write_document_index_status(status)  # type: ignore[arg-type]

    assert await database.read_metadata("document_index_status") == "not_built"
    await database.close()
