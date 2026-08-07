"""应用基础设施就绪状态的类型化聚合服务。"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.storage.sqlite import SQLiteNotInitializedError

SQLiteCheckStatus = Literal["ok", "error", "timeout"]
DocumentIndexCheckStatus = Literal[
    "ready",
    "not_built",
    "missing",
    "error",
    "timeout",
]
RetrieverBackendCheckStatus = Literal[
    "ok",
    "not_configured",
    "error",
    "timeout",
]
ReadinessStatus = Literal["ready", "not_ready"]


class SQLiteReadinessProtocol(Protocol):
    """readiness 所需的最小 SQLite 公共接口。"""

    async def ping(self) -> bool:
        """返回当前 SQLite 连接是否可用。"""
        ...

    async def read_metadata(self, key: str) -> str | None:
        """读取指定元数据；键不存在时返回 ``None``。"""
        ...


class RetrieverReadinessProbe(Protocol):
    """检索后端必须提供的最小、与具体产品无关的探针接口。"""

    @property
    def backend_name(self) -> str:
        """返回可安全公开的稳定后端名称。"""
        ...

    async def ping(self) -> bool:
        """返回当前检索后端是否可用。"""
        ...


class ReadinessProbeError(RuntimeError):
    """检索探针可公开归类、但不可公开原文的预期基础设施错误。"""


class SQLiteCheck(BaseModel):
    """SQLite 就绪检查结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SQLiteCheckStatus


class DocumentIndexCheck(BaseModel):
    """文档索引元数据检查结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DocumentIndexCheckStatus


class RetrieverBackendCheck(BaseModel):
    """实际配置的检索后端检查结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RetrieverBackendCheckStatus
    backend: str | None


class ReadinessChecks(BaseModel):
    """组成应用 readiness 的三个检查。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sqlite: SQLiteCheck
    document_index: DocumentIndexCheck
    retriever_backend: RetrieverBackendCheck


class ReadinessResult(BaseModel):
    """与 HTTP 无关的聚合 readiness 结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReadinessStatus
    checks: ReadinessChecks


class ReadinessService:
    """每次调用时重新检查当前应用拥有的基础设施。"""

    def __init__(
        self,
        *,
        sqlite: SQLiteReadinessProtocol,
        retriever_backend: RetrieverReadinessProbe | None,
        timeout_seconds: float,
    ) -> None:
        self._sqlite = sqlite
        self._retriever_backend = retriever_backend
        self._timeout_seconds = timeout_seconds

    async def check(self) -> ReadinessResult:
        """独立执行各项短超时检查并聚合当前就绪状态。"""
        sqlite = await self._check_sqlite()
        document_index = await self._check_document_index()
        retriever_backend = await self._check_retriever_backend()
        checks = ReadinessChecks(
            sqlite=sqlite,
            document_index=document_index,
            retriever_backend=retriever_backend,
        )
        is_ready = (
            sqlite.status == "ok"
            and document_index.status == "ready"
            and retriever_backend.status == "ok"
        )
        return ReadinessResult(
            status="ready" if is_ready else "not_ready",
            checks=checks,
        )

    async def _check_sqlite(self) -> SQLiteCheck:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                available = await self._sqlite.ping()
        except TimeoutError:
            return SQLiteCheck(status="timeout")
        except (sqlite3.Error, OSError, SQLiteNotInitializedError):
            return SQLiteCheck(status="error")
        return SQLiteCheck(status="ok" if available else "error")

    async def _check_document_index(self) -> DocumentIndexCheck:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                index_status = await self._sqlite.read_metadata("document_index_status")
        except TimeoutError:
            return DocumentIndexCheck(status="timeout")
        except (sqlite3.Error, OSError, SQLiteNotInitializedError):
            return DocumentIndexCheck(status="error")

        if index_status == "ready":
            return DocumentIndexCheck(status="ready")
        if index_status == "not_built":
            return DocumentIndexCheck(status="not_built")
        if index_status is None:
            return DocumentIndexCheck(status="missing")
        return DocumentIndexCheck(status="error")

    async def _check_retriever_backend(self) -> RetrieverBackendCheck:
        probe = self._retriever_backend
        if probe is None:
            return RetrieverBackendCheck(
                status="not_configured",
                backend=None,
            )

        backend_name = probe.backend_name
        try:
            async with asyncio.timeout(self._timeout_seconds):
                available = await probe.ping()
        except TimeoutError:
            return RetrieverBackendCheck(
                status="timeout",
                backend=backend_name,
            )
        except ReadinessProbeError:
            return RetrieverBackendCheck(
                status="error",
                backend=backend_name,
            )
        return RetrieverBackendCheck(
            status="ok" if available else "error",
            backend=backend_name,
        )
