from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

import app.core.dependencies as dependencies_module
import app.retrieval.qdrant as qdrant_module
from app.core.config import Settings
from app.core.dependencies import (
    ApplicationDependencies,
    build_application_dependencies,
)
from app.core.readiness import ReadinessService
from app.retrieval.qdrant import QdrantBackend, QdrantBackendState
from app.storage.sqlite import SQLiteDatabase, SQLiteInitializationState


def _settings(path: Path, *, timeout_seconds: float = 2.0) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        sqlite_path=path,
        sqlite_timeout_seconds=timeout_seconds,
    )


def test_build_application_dependencies_uses_the_app_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "configured.sqlite3", timeout_seconds=3.5)
    database = Mock(spec=SQLiteDatabase)
    database_factory = Mock(return_value=database)
    retriever_backend = Mock(spec=QdrantBackend)
    retriever_factory = Mock(return_value=retriever_backend)
    monkeypatch.setattr(
        dependencies_module,
        "SQLiteDatabase",
        database_factory,
    )
    monkeypatch.setattr(
        dependencies_module,
        "build_qdrant_backend",
        retriever_factory,
    )

    dependencies = build_application_dependencies(settings)

    assert isinstance(dependencies, ApplicationDependencies)
    assert dependencies.sqlite is database
    assert dependencies.retriever_backend is retriever_backend
    assert isinstance(dependencies.readiness, ReadinessService)
    database_factory.assert_called_once_with(
        settings.sqlite_path,
        timeout_seconds=settings.sqlite_timeout_seconds,
    )
    retriever_factory.assert_called_once_with(settings)


def test_build_application_dependencies_returns_independent_containers(
    tmp_path: Path,
) -> None:
    first = build_application_dependencies(_settings(tmp_path / "first.sqlite3"))
    second = build_application_dependencies(_settings(tmp_path / "second.sqlite3"))

    assert first is not second
    assert first.sqlite is not second.sqlite
    assert first.retriever_backend is not second.retriever_backend
    assert first.readiness is not second.readiness
    assert isinstance(first.sqlite, SQLiteDatabase)
    assert isinstance(second.sqlite, SQLiteDatabase)


def test_building_dependencies_does_not_initialize_external_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    database_path = tmp_path / "not_initialized.sqlite3"

    dependencies = build_application_dependencies(_settings(database_path))

    assert isinstance(dependencies.sqlite, SQLiteDatabase)
    assert isinstance(dependencies.readiness, ReadinessService)
    assert dependencies.sqlite.initialization_state is SQLiteInitializationState.NEW
    assert dependencies.retriever_backend.initialize_calls == 0
    assert dependencies.retriever_backend.ping_calls == 0
    assert dependencies.retriever_backend.close_calls == 0
    assert not database_path.exists()


def test_real_qdrant_builder_only_constructs_the_client_without_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_client = Mock()
    raw_client.collection_exists = AsyncMock(
        side_effect=AssertionError("dependency builder 不得访问 collection")
    )
    raw_client.get_collections = AsyncMock(
        side_effect=AssertionError("dependency builder 不得 ping")
    )
    raw_client.close = AsyncMock(
        side_effect=AssertionError("dependency builder 不得提前 close")
    )
    raw_client_factory = Mock(return_value=raw_client)
    monkeypatch.setattr(qdrant_module, "AsyncQdrantClient", raw_client_factory)
    monkeypatch.setattr(
        dependencies_module,
        "build_qdrant_backend",
        qdrant_module.build_qdrant_backend,
    )
    settings = _settings(tmp_path / "not_initialized.sqlite3")

    dependencies = build_application_dependencies(settings)

    assert isinstance(dependencies.retriever_backend, QdrantBackend)
    assert dependencies.retriever_backend.state is QdrantBackendState.NEW
    raw_client_factory.assert_called_once_with(
        url=str(settings.qdrant_url),
        timeout=settings.qdrant_timeout_seconds,
        prefer_grpc=False,
    )
    raw_client.collection_exists.assert_not_awaited()
    raw_client.get_collections.assert_not_awaited()
    raw_client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_readiness_uses_the_same_retriever_owned_by_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Mock(spec=SQLiteDatabase)
    database.ping = AsyncMock(return_value=True)
    database.read_metadata = AsyncMock(return_value="not_built")
    retriever_backend = Mock(spec=QdrantBackend)
    retriever_backend.backend_name = "qdrant"
    retriever_backend.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(
        dependencies_module,
        "SQLiteDatabase",
        Mock(return_value=database),
    )
    monkeypatch.setattr(
        dependencies_module,
        "build_qdrant_backend",
        Mock(return_value=retriever_backend),
    )

    dependencies = build_application_dependencies(
        _settings(tmp_path / "configured.sqlite3")
    )
    result = await dependencies.readiness.check()

    assert dependencies.retriever_backend is retriever_backend
    retriever_backend.ping.assert_awaited_once_with()
    assert result.status == "not_ready"
    assert result.checks.retriever_backend.status == "ok"
    assert result.checks.retriever_backend.backend == "qdrant"
