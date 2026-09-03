"""应用实例独立拥有的基础设施依赖。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.application import AnalysisService, LazyOfficialDocsRetriever
from app.core.config import Settings
from app.core.llm import FakeLLM, LLMClient, RealLLMClient
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
    llm_client: LLMClient = field(default_factory=FakeLLM)
    analysis_service: AnalysisService | None = None


def build_llm_client(settings: Settings) -> LLMClient:
    """只构造所选 LLM client；不执行 provider 网络请求。"""
    if settings.llm_backend == "fake":
        return FakeLLM()
    if (
        settings.llm_base_url is None
        or settings.llm_model is None
        or settings.llm_api_key is None
    ):
        raise ValueError("真实 LLM 配置不完整")
    return RealLLMClient(
        base_url=str(settings.llm_base_url),
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value(),
        max_output_tokens=settings.llm_max_output_tokens,
    )


def build_application_dependencies(settings: Settings) -> ApplicationDependencies:
    """根据当前应用配置组装依赖，但不提前初始化外部资源。"""
    sqlite = SQLiteDatabase(
        settings.sqlite_path,
        timeout_seconds=settings.sqlite_timeout_seconds,
    )
    retriever_backend = build_qdrant_backend(settings)
    llm_client = build_llm_client(settings)
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
        llm_client=llm_client,
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
        llm_client=llm_client,
        analysis_service=analysis_service,
    )
