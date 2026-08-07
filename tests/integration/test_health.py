from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def application(tmp_path: Path) -> FastAPI:
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="INFO",
        llm_backend="fake",
        sqlite_path=tmp_path / "health.sqlite3",
    )
    return create_app(settings)


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application) as test_client:
        yield test_client


def test_application_factory_returns_independent_apps() -> None:
    settings = Settings(_env_file=None, environment="test")

    first = create_app(settings)
    second = create_app(settings)

    assert isinstance(first, FastAPI)
    assert isinstance(second, FastAPI)
    assert first is not second
    assert first.state.settings is settings
    assert second.state.settings is settings


def test_health_live_returns_exact_contract(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "MigrationLens",
        "version": "0.1.0",
    }


def test_openapi_exposes_health_live(application: FastAPI) -> None:
    paths = application.openapi()["paths"]

    assert "/health/live" in paths
    assert "get" in paths["/health/live"]


def test_health_ready_reports_default_not_ready_state(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "sqlite": {"status": "ok"},
            "document_index": {"status": "not_built"},
            "retriever_backend": {
                "status": "not_configured",
                "backend": None,
            },
        },
    }


def test_application_starts_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        environment="test",
        sqlite_path=tmp_path / "health.sqlite3",
    )

    application = create_app(settings)

    with TestClient(application) as client:
        assert client.get("/health/live").status_code == 200
