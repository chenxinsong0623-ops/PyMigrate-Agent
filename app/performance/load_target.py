"""FakeLLM application load 专用 HTTP target；不代表真实 Qdrant/E5。"""

from __future__ import annotations

import os
from pathlib import Path

from app.application import AnalysisService
from app.core.config import Settings
from app.core.dependencies import ApplicationDependencies, build_llm_client
from app.core.readiness import ReadinessService
from app.main import create_app
from app.performance.load_gate import validate_load_mode
from app.retrieval.hybrid import HybridSearchResponse
from app.storage.sqlite import SQLiteDatabase


class _OfflineRetrieverBackend:
    backend_name = "qdrant-load-double"

    async def initialize(self) -> bool:
        return True

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class _EmptyOfficialDocsRetriever:
    async def search(self, query: str) -> HybridSearchResponse:
        return HybridSearchResponse(
            query=query,
            rrf_k=60,
            results=(),
            top_results=(),
        )


def create_fake_load_app():
    settings = Settings(
        _env_file=None,
        environment="test",
        llm_backend="fake",
        sqlite_path=Path(
            os.environ.get(
                "MIGRATIONLENS_LOADTEST_SQLITE_PATH",
                "var/tmp/day26-fake-load.sqlite3",
            )
        ),
    )
    validate_load_mode("fake", None, settings)
    sqlite = SQLiteDatabase(
        settings.sqlite_path,
        timeout_seconds=settings.sqlite_timeout_seconds,
    )
    retriever_backend = _OfflineRetrieverBackend()
    llm_client = build_llm_client(settings)
    repository_root = Path(__file__).resolve().parents[2]
    dependencies = ApplicationDependencies(
        sqlite=sqlite,
        retriever_backend=retriever_backend,
        readiness=ReadinessService(
            sqlite=sqlite,
            retriever_backend=retriever_backend,
            timeout_seconds=settings.readiness_timeout_seconds,
        ),
        llm_client=llm_client,
        analysis_service=AnalysisService(
            storage=sqlite,
            official_docs_retriever=_EmptyOfficialDocsRetriever(),
            llm_client=llm_client,
            repository_root=repository_root,
            temp_parent=repository_root / "var" / "tmp",
        ),
    )
    return create_app(settings, dependencies)


app = create_fake_load_app()
