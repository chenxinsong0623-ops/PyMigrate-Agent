from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def application() -> FastAPI:
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="INFO",
        llm_backend="fake",
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


def test_health_ready_is_not_implemented(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 404


def test_application_starts_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, environment="test")

    application = create_app(settings)

    with TestClient(application) as client:
        assert client.get("/health/live").status_code == 200
