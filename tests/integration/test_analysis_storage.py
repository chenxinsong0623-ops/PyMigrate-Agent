from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from pydantic import ValidationError

import app.storage.sqlite as sqlite_module
from app.storage.sqlite import (
    AnalysisAlreadyExistsError,
    AnalysisStorageError,
    SQLiteDatabase,
    SQLiteInitializationState,
    StoredAnalysis,
)


def _record(analysis_id: str = "analysis-1") -> StoredAnalysis:
    return StoredAnalysis(
        analysis_id=analysis_id,
        status="degraded",
        report_language="zh-CN",
        scanner_version="0.1.0",
        document_ref="pydantic-v2.13.4",
        model="deterministic-fallback",
        llm_review=False,
        created_at_utc="2026-08-26T01:02:03+00:00",
        response_json=json.dumps(
            {
                "analysis_id": analysis_id,
                "status": "degraded",
                "report_language": "zh-CN",
                "scanner_version": "0.1.0",
                "document_ref": "pydantic-v2.13.4",
                "model": "deterministic-fallback",
            },
            separators=(",", ":"),
        ),
        report_json=json.dumps(
            {"analysis_id": analysis_id, "schema_version": "1"},
            separators=(",", ":"),
        ),
        report_markdown=f"# MigrationLens 报告\n\n- 分析 ID：`{analysis_id}`\n",
    )


def test_stored_analysis_rejects_mismatched_serialized_identity() -> None:
    values = _record().model_dump()
    values["response_json"] = values["response_json"].replace(
        "analysis-1", "analysis-forged"
    )

    with pytest.raises(ValidationError, match="identity"):
        StoredAnalysis.model_validate(values)


def _create_v1_database(path: Path, *, version: str = "1") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE system_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO system_metadata VALUES (?, ?, ?)",
            (
                ("schema_version", version, "2026-08-25T00:00:00+00:00"),
                ("document_index_status", "ready", "2026-08-25T00:00:00+00:00"),
            ),
        )


async def _table_names(path: Path) -> set[str]:
    async with aiosqlite.connect(path) as connection:
        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return {str(row[0]) for row in rows}


@pytest.mark.asyncio
async def test_new_database_initializes_directly_at_schema_v2(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "new.sqlite3", timeout_seconds=2.0)

    assert await database.initialize() is True
    assert await database.read_metadata("schema_version") == "2"
    assert await _table_names(tmp_path / "new.sqlite3") == {
        "analyses",
        "reports",
        "system_metadata",
    }
    await database.close()


@pytest.mark.asyncio
async def test_v1_database_migrates_to_v2_and_preserves_existing_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    _create_v1_database(path)
    database = SQLiteDatabase(path, timeout_seconds=2.0)

    assert await database.initialize() is True
    assert await database.read_metadata("schema_version") == "2"
    assert await database.read_metadata("document_index_status") == "ready"
    assert await _table_names(path) == {"analyses", "reports", "system_metadata"}
    await database.close()


@pytest.mark.asyncio
async def test_unknown_future_schema_version_fails_closed_without_upgrade(
    tmp_path: Path,
) -> None:
    path = tmp_path / "future.sqlite3"
    _create_v1_database(path, version="999")
    database = SQLiteDatabase(path, timeout_seconds=2.0)

    assert await database.initialize() is False
    assert database.initialization_error_type == "SQLiteSchemaVersionError"
    assert await _table_names(path) == {"system_metadata"}


@pytest.mark.asyncio
async def test_failed_migration_rolls_back_ddl_and_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "rollback.sqlite3"
    _create_v1_database(path)
    monkeypatch.setattr(sqlite_module, "_CREATE_REPORTS", "INVALID SQL")
    database = SQLiteDatabase(path, timeout_seconds=2.0)

    assert await database.initialize() is False
    assert await _table_names(path) == {"system_metadata"}
    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "SELECT value FROM system_metadata WHERE key='schema_version'"
        ).fetchone()
    assert version == ("1",)


@pytest.mark.asyncio
async def test_analysis_and_both_reports_commit_atomically_and_survive_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.sqlite3"
    database = SQLiteDatabase(path, timeout_seconds=2.0)
    assert await database.initialize() is True
    record = _record()

    await database.save_analysis(record)
    assert await database.read_analysis_response_json(record.analysis_id) == (
        record.response_json
    )
    assert await database.read_report_json(record.analysis_id) == record.report_json
    assert await database.read_report_markdown(record.analysis_id) == (
        record.report_markdown
    )
    await database.close()

    reopened = SQLiteDatabase(path, timeout_seconds=2.0)
    assert await reopened.initialize() is True
    assert await reopened.read_analysis_response_json(record.analysis_id) == (
        record.response_json
    )
    assert await reopened.read_report_json(record.analysis_id) == record.report_json
    await reopened.close()


@pytest.mark.asyncio
async def test_duplicate_analysis_id_never_overwrites_history(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "duplicate.sqlite3", timeout_seconds=2.0)
    assert await database.initialize() is True
    original = _record()
    await database.save_analysis(original)

    with pytest.raises(AnalysisAlreadyExistsError):
        await database.save_analysis(
            original.model_copy(update={"response_json": '{"forged":true}'})
        )

    assert await database.read_analysis_response_json(original.analysis_id) == (
        original.response_json
    )
    await database.close()


@pytest.mark.asyncio
async def test_report_insert_failure_rolls_back_analysis_row(tmp_path: Path) -> None:
    path = tmp_path / "atomic.sqlite3"
    database = SQLiteDatabase(path, timeout_seconds=2.0)
    assert await database.initialize() is True
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            """
            CREATE TRIGGER reject_reports BEFORE INSERT ON reports
            BEGIN SELECT RAISE(ABORT, 'reject'); END
            """
        )
        await connection.commit()

    with pytest.raises(AnalysisStorageError):
        await database.save_analysis(_record())

    assert await database.read_analysis_response_json("analysis-1") is None
    assert await database.read_report_json("analysis-1") is None
    await database.close()


@pytest.mark.asyncio
async def test_unexpected_save_failure_rolls_back_then_propagates(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "unused.sqlite3", timeout_seconds=2.0)
    connection = SimpleNamespace(
        execute=AsyncMock(side_effect=(None, RuntimeError("programmer failure"))),
        rollback=AsyncMock(),
    )
    database._connection = connection  # type: ignore[assignment]
    database._initialization_state = SQLiteInitializationState.INITIALIZED

    with pytest.raises(RuntimeError, match="programmer failure"):
        await database.save_analysis(_record())

    connection.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_reports_foreign_key_rejects_orphan_rows(tmp_path: Path) -> None:
    path = tmp_path / "foreign-key.sqlite3"
    database = SQLiteDatabase(path, timeout_seconds=2.0)
    assert await database.initialize() is True
    async with aiosqlite.connect(path) as connection:
        await connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(
                """
                INSERT INTO reports (
                    analysis_id, schema_version, json_report,
                    markdown_report, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("missing", "1", "{}", "# report", "2026-08-26T00:00:00+00:00"),
            )
    await database.close()
