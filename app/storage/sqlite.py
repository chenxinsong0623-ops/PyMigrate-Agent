"""应用生命周期内的 SQLite 基础设施与分析报告持久化。"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.logging import LOGGER_NAME

_CREATE_SYSTEM_METADATA = """
CREATE TABLE IF NOT EXISTS system_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
)
"""
_INSERT_SYSTEM_METADATA = """
INSERT OR IGNORE INTO system_metadata (key, value, updated_at_utc)
VALUES (?, ?, ?)
"""
_UPDATE_SYSTEM_METADATA = """
UPDATE system_metadata
SET value = ?, updated_at_utc = ?
WHERE key = ?
"""
_CREATE_ANALYSES = """
CREATE TABLE analyses (
    analysis_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('completed', 'degraded')),
    report_language TEXT NOT NULL CHECK (report_language = 'zh-CN'),
    scanner_version TEXT NOT NULL,
    document_ref TEXT NOT NULL,
    model TEXT NOT NULL,
    llm_review INTEGER NOT NULL CHECK (llm_review IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    response_json TEXT NOT NULL
)
"""
_CREATE_REPORTS = """
CREATE TABLE reports (
    analysis_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK (schema_version = '1'),
    json_report TEXT NOT NULL,
    markdown_report TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
)
"""
_INSERT_ANALYSIS = """
INSERT INTO analyses (
    analysis_id, status, report_language, scanner_version, document_ref,
    model, llm_review, created_at_utc, response_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_INSERT_REPORT = """
INSERT INTO reports (
    analysis_id, schema_version, json_report, markdown_report, created_at_utc
) VALUES (?, ?, ?, ?, ?)
"""

_CURRENT_SCHEMA_VERSION = "2"

DocumentIndexStatus = Literal["not_built", "ready"]


class StoredAnalysis(BaseModel):
    """一次已完成业务调用的原子持久化载荷。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )

    analysis_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    status: Literal["completed", "degraded"]
    report_language: Literal["zh-CN"]
    scanner_version: str = Field(min_length=1, max_length=64)
    document_ref: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    llm_review: bool
    created_at_utc: str = Field(min_length=1, max_length=64)
    response_json: str = Field(min_length=2, max_length=5_000_000)
    report_json: str = Field(min_length=2, max_length=5_000_000)
    report_markdown: str = Field(min_length=1, max_length=5_000_000)

    @model_validator(mode="after")
    def validate_serialized_identity(self) -> StoredAnalysis:
        try:
            response = json.loads(self.response_json)
            report = json.loads(self.report_json)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("持久化 JSON 必须是合法 JSON") from None
        if not isinstance(response, dict) or not isinstance(report, dict):
            raise ValueError("持久化 JSON 必须是 object")
        expected_response = {
            "analysis_id": self.analysis_id,
            "status": self.status,
            "report_language": self.report_language,
            "scanner_version": self.scanner_version,
            "document_ref": self.document_ref,
            "model": self.model,
        }
        if any(response.get(key) != value for key, value in expected_response.items()):
            raise ValueError("API JSON identity 与审计列不一致")
        if (
            report.get("analysis_id") != self.analysis_id
            or report.get("schema_version") != "1"
        ):
            raise ValueError("report JSON identity 或 schema 不一致")
        if f"`{self.analysis_id}`" not in self.report_markdown:
            raise ValueError("Markdown report identity 不一致")
        return self


class SQLiteSchemaVersionError(RuntimeError):
    """数据库 schema 版本未知或与声明不一致。"""


class AnalysisStorageError(RuntimeError):
    """不暴露 SQLite 原文的分析持久化错误。"""

    def __init__(self, _unsafe_detail: str | None = None) -> None:
        super().__init__("分析结果持久化失败")


class AnalysisAlreadyExistsError(AnalysisStorageError):
    """analysis_id 已存在且不得覆盖。"""

    def __init__(self) -> None:
        super().__init__()
        self.args = ("analysis_id 已存在",)


class SQLiteInitializationState(StrEnum):
    """SQLite 连接的生命周期状态。"""

    NEW = "new"
    INITIALIZED = "initialized"
    FAILED = "failed"
    CLOSED = "closed"


class SQLiteNotInitializedError(RuntimeError):
    """在 SQLite 未初始化时读取元数据。"""


class SQLiteDatabase:
    """管理单个应用生命周期内的异步 SQLite 连接。"""

    def __init__(
        self,
        path: Path,
        *,
        timeout_seconds: float,
        logger: logging.Logger | None = None,
    ) -> None:
        self._path = path
        self._timeout_seconds = timeout_seconds
        self._logger = logger or logging.getLogger(LOGGER_NAME)
        self._connection: aiosqlite.Connection | None = None
        self._initialization_state = SQLiteInitializationState.NEW
        self._initialization_error_type: str | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def initialization_state(self) -> SQLiteInitializationState:
        """返回当前 SQLite 生命周期状态。"""
        return self._initialization_state

    @property
    def initialization_error_type(self) -> str | None:
        """返回安全保存的初始化异常类型。"""
        return self._initialization_error_type

    async def initialize(self) -> bool:
        """事务化初始化或迁移 schema；预期基础设施失败时返回 ``False``。"""
        async with self._lifecycle_lock:
            if self._initialization_state is SQLiteInitializationState.INITIALIZED:
                return True
            if self._initialization_state in {
                SQLiteInitializationState.FAILED,
                SQLiteInitializationState.CLOSED,
            }:
                return False

            connection: aiosqlite.Connection | None = None
            initialization_succeeded = False
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                connection = await aiosqlite.connect(
                    str(self._path),
                    timeout=self._timeout_seconds,
                )
                await connection.execute("PRAGMA foreign_keys = ON")
                await connection.execute(
                    f"PRAGMA busy_timeout = {int(self._timeout_seconds * 1000)}"
                )
                await self._initialize_schema(connection)
                initialization_succeeded = True
            except (sqlite3.Error, OSError, SQLiteSchemaVersionError) as error:
                self._connection = None
                self._initialization_state = SQLiteInitializationState.FAILED
                self._initialization_error_type = type(error).__name__
                self._logger.error(
                    "sqlite_initialization_failed",
                    extra={
                        "component": "sqlite",
                        "error_type": self._initialization_error_type,
                    },
                )
                return False
            finally:
                if not initialization_succeeded and connection is not None:
                    try:
                        await connection.close()
                    except (sqlite3.Error, OSError):
                        pass

            self._connection = connection
            self._initialization_state = SQLiteInitializationState.INITIALIZED
            self._initialization_error_type = None
            return True

    async def _initialize_schema(self, connection: aiosqlite.Connection) -> None:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            metadata_existed = await _table_exists(connection, "system_metadata")
            await connection.execute(_CREATE_SYSTEM_METADATA)
            schema_version = await _read_metadata_value(connection, "schema_version")
            now = datetime.now(tz=UTC).isoformat()

            if not metadata_existed:
                if schema_version is not None:
                    raise SQLiteSchemaVersionError()
                await connection.execute(_CREATE_ANALYSES)
                await connection.execute(_CREATE_REPORTS)
                await connection.executemany(
                    _INSERT_SYSTEM_METADATA,
                    (
                        ("schema_version", _CURRENT_SCHEMA_VERSION, now),
                        ("document_index_status", "not_built", now),
                    ),
                )
            elif schema_version == "1":
                await connection.execute(_CREATE_ANALYSES)
                await connection.execute(_CREATE_REPORTS)
                cursor = await connection.execute(
                    _UPDATE_SYSTEM_METADATA,
                    (_CURRENT_SCHEMA_VERSION, now, "schema_version"),
                )
                try:
                    if cursor.rowcount != 1:
                        raise SQLiteSchemaVersionError()
                finally:
                    await cursor.close()
                await connection.execute(
                    _INSERT_SYSTEM_METADATA,
                    ("document_index_status", "not_built", now),
                )
            elif schema_version == _CURRENT_SCHEMA_VERSION:
                if not await _table_exists(
                    connection, "analyses"
                ) or not await _table_exists(connection, "reports"):
                    raise SQLiteSchemaVersionError()
            else:
                raise SQLiteSchemaVersionError()
            await connection.commit()
        except BaseException:
            try:
                await connection.rollback()
            except (sqlite3.Error, OSError):
                pass
            raise

    async def ping(self) -> bool:
        """通过 ``SELECT 1`` 检查当前连接是否可用。"""
        async with self._lifecycle_lock:
            connection = self._connection
            if (
                self._initialization_state is not SQLiteInitializationState.INITIALIZED
                or connection is None
            ):
                return False

            try:
                async with connection.execute("SELECT 1") as cursor:
                    row = await cursor.fetchone()
            except (sqlite3.Error, OSError):
                return False
            return row == (1,)

    async def read_metadata(self, key: str) -> str | None:
        """读取一个元数据值；键不存在时返回 ``None``。"""
        async with self._lifecycle_lock:
            connection = self._connection
            if (
                self._initialization_state is not SQLiteInitializationState.INITIALIZED
                or connection is None
            ):
                raise SQLiteNotInitializedError("SQLite 尚未初始化")

            async with connection.execute(
                "SELECT value FROM system_metadata WHERE key = ?",
                (key,),
            ) as cursor:
                row = await cursor.fetchone()
            return None if row is None else str(row[0])

    async def write_document_index_status(
        self,
        status: DocumentIndexStatus,
    ) -> None:
        """参数化更新文档索引状态，并在返回前提交。"""
        if status not in {"not_built", "ready"}:
            raise ValueError("document_index_status 不受支持")
        async with self._lifecycle_lock:
            connection = self._connection
            if (
                self._initialization_state is not SQLiteInitializationState.INITIALIZED
                or connection is None
            ):
                raise SQLiteNotInitializedError("SQLite 尚未初始化")

            cursor = await connection.execute(
                _UPDATE_SYSTEM_METADATA,
                (
                    status,
                    datetime.now(tz=UTC).isoformat(),
                    "document_index_status",
                ),
            )
            try:
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        "document_index_status metadata row is missing"
                    )
            finally:
                await cursor.close()
            await connection.commit()

    async def save_analysis(self, record: StoredAnalysis) -> None:
        """在单一事务中写入分析行及 JSON/Markdown 报告。"""
        async with self._lifecycle_lock:
            connection = self._require_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                if await _analysis_exists(connection, record.analysis_id):
                    raise AnalysisAlreadyExistsError()
                await connection.execute(
                    _INSERT_ANALYSIS,
                    (
                        record.analysis_id,
                        record.status,
                        record.report_language,
                        record.scanner_version,
                        record.document_ref,
                        record.model,
                        int(record.llm_review),
                        record.created_at_utc,
                        record.response_json,
                    ),
                )
                await connection.execute(
                    _INSERT_REPORT,
                    (
                        record.analysis_id,
                        "1",
                        record.report_json,
                        record.report_markdown,
                        record.created_at_utc,
                    ),
                )
                await connection.commit()
            except AnalysisAlreadyExistsError:
                await _safe_rollback(connection)
                raise
            except (sqlite3.Error, OSError) as error:
                await _safe_rollback(connection)
                if await _analysis_exists_safely(connection, record.analysis_id):
                    raise AnalysisAlreadyExistsError() from None
                raise AnalysisStorageError(type(error).__name__) from None
            except BaseException:
                await _safe_rollback(connection)
                raise

    async def read_analysis_response_json(self, analysis_id: str) -> str | None:
        """按 ID 读取原样持久化的 API JSON，不重跑分析。"""
        return await self._read_text(
            "SELECT response_json FROM analyses WHERE analysis_id = ?",
            analysis_id,
        )

    async def read_report_json(self, analysis_id: str) -> str | None:
        """按 ID 读取 Day 20 canonical JSON report。"""
        return await self._read_text(
            "SELECT json_report FROM reports WHERE analysis_id = ?",
            analysis_id,
        )

    async def read_report_markdown(self, analysis_id: str) -> str | None:
        """按 ID 读取 Day 20 Markdown report。"""
        return await self._read_text(
            "SELECT markdown_report FROM reports WHERE analysis_id = ?",
            analysis_id,
        )

    async def _read_text(self, query: str, analysis_id: str) -> str | None:
        async with self._lifecycle_lock:
            connection = self._require_connection()
            try:
                async with connection.execute(query, (analysis_id,)) as cursor:
                    row = await cursor.fetchone()
            except (sqlite3.Error, OSError) as error:
                raise AnalysisStorageError(type(error).__name__) from None
            return None if row is None else str(row[0])

    def _require_connection(self) -> aiosqlite.Connection:
        connection = self._connection
        if (
            self._initialization_state is not SQLiteInitializationState.INITIALIZED
            or connection is None
        ):
            raise SQLiteNotInitializedError("SQLite 尚未初始化")
        return connection

    async def close(self) -> None:
        """关闭连接；在任意生命周期状态下都可安全重复调用。"""
        async with self._lifecycle_lock:
            connection = self._connection
            self._connection = None
            self._initialization_state = SQLiteInitializationState.CLOSED

            if connection is None:
                return

            try:
                await connection.close()
            except (sqlite3.Error, OSError) as error:
                self._logger.error(
                    "sqlite_close_failed",
                    extra={
                        "component": "sqlite",
                        "error_type": type(error).__name__,
                    },
                )


async def _table_exists(connection: aiosqlite.Connection, name: str) -> bool:
    cursor = await connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    )
    try:
        return await cursor.fetchone() == (1,)
    finally:
        await cursor.close()


async def _read_metadata_value(
    connection: aiosqlite.Connection,
    key: str,
) -> str | None:
    cursor = await connection.execute(
        "SELECT value FROM system_metadata WHERE key = ?",
        (key,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return None if row is None else str(row[0])


async def _analysis_exists(
    connection: aiosqlite.Connection,
    analysis_id: str,
) -> bool:
    cursor = await connection.execute(
        "SELECT 1 FROM analyses WHERE analysis_id = ?",
        (analysis_id,),
    )
    try:
        return await cursor.fetchone() == (1,)
    finally:
        await cursor.close()


async def _analysis_exists_safely(
    connection: aiosqlite.Connection,
    analysis_id: str,
) -> bool:
    try:
        return await _analysis_exists(connection, analysis_id)
    except (sqlite3.Error, OSError):
        return False


async def _safe_rollback(connection: aiosqlite.Connection) -> None:
    try:
        await connection.rollback()
    except (sqlite3.Error, OSError):
        pass
