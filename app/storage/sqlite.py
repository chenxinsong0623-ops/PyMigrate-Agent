"""应用生命周期内使用的最小 SQLite 基础设施。"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import aiosqlite

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
        """创建连接和最小元数据表；预期基础设施失败时返回 ``False``。"""
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
                await connection.execute(_CREATE_SYSTEM_METADATA)

                now = datetime.now(tz=UTC).isoformat()
                await connection.executemany(
                    _INSERT_SYSTEM_METADATA,
                    (
                        ("schema_version", "1", now),
                        ("document_index_status", "not_built", now),
                    ),
                )
                await connection.commit()
                initialization_succeeded = True
            except (sqlite3.Error, OSError) as error:
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
