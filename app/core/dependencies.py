"""应用实例独立拥有的基础设施依赖。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.application import AnalysisService, LazyOfficialDocsRetriever
from app.core.config import Settings
from app.core.llm import FakeLLM
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
    analysis_service: AnalysisService | None = None


def build_application_dependencies(settings: Settings) -> ApplicationDependencies:
    """根据当前应用配置组装依赖，但不提前初始化外部资源。"""
    sqlite = SQLiteDatabase(
        settings.sqlite_path,
        timeout_seconds=settings.sqlite_timeout_seconds,
    )
    retriever_backend = build_qdrant_backend(settings)
    repository_root = Path(__file__).resolve().parents[2]
    analysis_service = AnalysisService(
        storage=sqlite,
        official_docs_retriever=LazyOfficialDocsRetriever(
            repository_root=repository_root,
            qdrant_backend=retriever_backend,
            embedding_cache_path=settings.embedding_cache_path,
            embedding_batch_size=settings.embedding_batch_size,
            embedding_timeout_seconds=settings.embedding_timeout_seconds,
            rrf_k=settings.rrf_k,
        ),
        llm_client=FakeLLM(),
        repository_root=repository_root,
    )
    return ApplicationDependencies(
        sqlite=sqlite,
        retriever_backend=retriever_backend,
        readiness=ReadinessService(
            sqlite=sqlite,
            retriever_backend=retriever_backend,
            timeout_seconds=settings.readiness_timeout_seconds,
        ),
        analysis_service=analysis_service,
    )
