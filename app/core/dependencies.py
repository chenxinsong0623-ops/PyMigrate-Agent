"""应用实例独立拥有的基础设施依赖。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.core.readiness import (
    ReadinessService,
    RetrieverReadinessProbe,
    SQLiteReadinessProtocol,
)
from app.retrieval.qdrant import build_qdrant_backend
from app.storage.sqlite import SQLiteDatabase


class SQLiteLifecycle(SQLiteReadinessProtocol, Protocol):
    """FastAPI lifespan 所需的最小 SQLite 生命周期边界。"""

    async def initialize(self) -> bool:
        """初始化 SQLite；预期基础设施失败时返回 ``False``。"""
        ...

    async def close(self) -> None:
        """安全关闭当前应用拥有的 SQLite 资源。"""
        ...


class RetrieverLifecycle(RetrieverReadinessProbe, Protocol):
    """FastAPI lifespan 所需的最小检索后端生命周期。"""

    async def initialize(self) -> bool:
        """初始化后端；预期基础设施失败时返回 ``False``。"""
        ...

    async def close(self) -> None:
        """安全关闭当前应用拥有的检索后端资源。"""
        ...


@dataclass(frozen=True, slots=True)
class ApplicationDependencies:
    """一个 FastAPI 应用实例独立拥有的依赖集合。"""

    sqlite: SQLiteLifecycle
    retriever_backend: RetrieverLifecycle
    readiness: ReadinessService


def build_application_dependencies(settings: Settings) -> ApplicationDependencies:
    """根据当前应用配置组装依赖，但不提前初始化外部资源。"""
    sqlite = SQLiteDatabase(
        settings.sqlite_path,
        timeout_seconds=settings.sqlite_timeout_seconds,
    )
    retriever_backend = build_qdrant_backend(settings)
    return ApplicationDependencies(
        sqlite=sqlite,
        retriever_backend=retriever_backend,
        readiness=ReadinessService(
            sqlite=sqlite,
            retriever_backend=retriever_backend,
            timeout_seconds=settings.readiness_timeout_seconds,
        ),
    )
