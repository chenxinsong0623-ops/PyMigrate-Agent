import asyncio
from collections.abc import Iterator
from pathlib import Path
from time import monotonic
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import Settings
from app.core.dependencies import ApplicationDependencies
from app.core.readiness import (
    ReadinessProbeError,
    ReadinessService,
)
from app.main import create_app


class FakeApplicationSQLite:
    def __init__(
        self,
        *,
        ping: bool = True,
        metadata: str | None = "ready",
    ) -> None:
        self.ping_result = ping
        self.metadata_result = metadata
        self.initialize_calls = 0
        self.close_calls = 0
        self.ping_calls = 0
        self.metadata_calls = 0

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    async def close(self) -> None:
        self.close_calls += 1

    async def ping(self) -> bool:
        self.ping_calls += 1
        return self.ping_result

    async def read_metadata(self, key: str) -> str | None:
        self.metadata_calls += 1
        assert key == "document_index_status"
        return self.metadata_result


class FakeRetrieverProbe:
    def __init__(
        self,
        *,
        backend_name: str = "injected-backend",
        available: bool | BaseException = True,
    ) -> None:
        self._backend_name = backend_name
        self._available = available
        self.initialize_calls = 0
        self.close_calls = 0
        self.ping_calls = 0

    @property
    def backend_name(self) -> str:
        return self._backend_name

    async def ping(self) -> bool:
        self.ping_calls += 1
        if isinstance(self._available, BaseException):
            raise self._available
        return self._available

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    async def close(self) -> None:
        self.close_calls += 1


def _settings(path: Path, *, readiness_timeout_seconds: float = 0.05) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        sqlite_path=path,
        readiness_timeout_seconds=readiness_timeout_seconds,
    )


def _injected_application(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    *,
    sqlite: FakeApplicationSQLite,
    probe: FakeRetrieverProbe | None,
) -> FastAPI:
    dependencies = ApplicationDependencies(
        sqlite=sqlite,
        retriever_backend=probe,
        readiness=ReadinessService(
            sqlite=sqlite,
            retriever_backend=probe,
            timeout_seconds=settings.readiness_timeout_seconds,
        ),
    )
    monkeypatch.setattr(
        main_module,
        "build_application_dependencies",
        lambda _settings: dependencies,
    )
    return create_app(settings)


@pytest.fixture
def default_application(tmp_path: Path) -> FastAPI:
    return create_app(_settings(tmp_path / "default.sqlite3"))


@pytest.fixture
def default_client(default_application: FastAPI) -> Iterator[TestClient]:
    with TestClient(default_application) as client:
        yield client


def test_default_application_is_live_but_honestly_not_ready(
    default_client: TestClient,
) -> None:
    live_response = default_client.get("/health/live")
    ready_response = default_client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json() == {
        "status": "ok",
        "service": "MigrationLens",
        "version": "0.1.0",
    }
    assert ready_response.status_code == 503
    assert ready_response.json() == {
        "status": "not_ready",
        "checks": {
            "sqlite": {"status": "ok"},
            "document_index": {"status": "not_built"},
            "retriever_backend": {
                "status": "ok",
                "backend": "qdrant",
            },
        },
    }


def test_all_healthy_injected_dependencies_return_200(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "unused.sqlite3")
    application = _injected_application(
        monkeypatch,
        settings,
        sqlite=FakeApplicationSQLite(),
        probe=FakeRetrieverProbe(backend_name="healthy-backend"),
    )

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "sqlite": {"status": "ok"},
            "document_index": {"status": "ready"},
            "retriever_backend": {
                "status": "ok",
                "backend": "healthy-backend",
            },
        },
    }


def test_unavailable_sqlite_returns_503_without_internal_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "secret.sqlite3")
    application = _injected_application(
        monkeypatch,
        settings,
        sqlite=FakeApplicationSQLite(ping=False),
        probe=FakeRetrieverProbe(),
    )

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["sqlite"] == {"status": "error"}
    assert str(settings.sqlite_path) not in response.text


def test_not_built_document_index_returns_503(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "unused.sqlite3")
    application = _injected_application(
        monkeypatch,
        settings,
        sqlite=FakeApplicationSQLite(metadata="not_built"),
        probe=FakeRetrieverProbe(),
    )

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["document_index"] == {"status": "not_built"}


def test_unavailable_retriever_returns_503_with_its_safe_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "unused.sqlite3")
    probe = FakeRetrieverProbe(
        backend_name="unavailable-backend",
        available=ReadinessProbeError("internal endpoint and credentials"),
    )
    application = _injected_application(
        monkeypatch,
        settings,
        sqlite=FakeApplicationSQLite(),
        probe=probe,
    )

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["retriever_backend"] == {
        "status": "error",
        "backend": "unavailable-backend",
    }
    assert "internal endpoint and credentials" not in response.text


def test_single_probe_timeout_returns_503_without_hanging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def never_returns() -> bool:
        await asyncio.Event().wait()
        return True

    settings = _settings(
        tmp_path / "unused.sqlite3",
        readiness_timeout_seconds=0.001,
    )
    probe = FakeRetrieverProbe()
    probe.ping = never_returns
    application = _injected_application(
        monkeypatch,
        settings,
        sqlite=FakeApplicationSQLite(),
        probe=probe,
    )

    started = monotonic()
    with TestClient(application) as client:
        response = client.get("/health/ready")
    elapsed = monotonic() - started

    assert response.status_code == 503
    assert response.json()["checks"]["retriever_backend"] == {
        "status": "timeout",
        "backend": "injected-backend",
    }
    assert elapsed < 1.0


def test_openapi_exposes_live_and_ready_with_structured_responses(
    default_application: FastAPI,
) -> None:
    openapi = default_application.openapi()
    paths = openapi["paths"]
    ready_responses = paths["/health/ready"]["get"]["responses"]

    assert "get" in paths["/health/live"]
    assert "get" in paths["/health/ready"]
    assert "200" in ready_responses
    assert "503" in ready_responses
    assert "ReadinessResult" in openapi["components"]["schemas"]


def test_live_isolated_from_every_readiness_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "unused.sqlite3")
    sqlite = FakeApplicationSQLite()
    sqlite.ping = AsyncMock(side_effect=AssertionError("live 不得调用 sqlite ping"))
    sqlite.read_metadata = AsyncMock(
        side_effect=AssertionError("live 不得读取 metadata")
    )
    probe = FakeRetrieverProbe()
    probe.ping = AsyncMock(side_effect=AssertionError("live 不得调用 retriever"))
    application = _injected_application(
        monkeypatch,
        settings,
        sqlite=sqlite,
        probe=probe,
    )
    application.state.dependencies.readiness.check = AsyncMock(
        side_effect=AssertionError("live 不得调用 readiness")
    )

    with TestClient(application) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "MigrationLens",
        "version": "0.1.0",
    }
    application.state.dependencies.readiness.check.assert_not_awaited()
    sqlite.ping.assert_not_awaited()
    sqlite.read_metadata.assert_not_awaited()
    probe.ping.assert_not_awaited()
