from pathlib import Path
from unittest.mock import Mock

import pytest

import app.core.dependencies as dependencies_module
from app.core.config import Settings
from app.core.dependencies import (
    ApplicationDependencies,
    build_application_dependencies,
)
from app.core.readiness import ReadinessService
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
    monkeypatch.setattr(
        dependencies_module,
        "SQLiteDatabase",
        database_factory,
    )

    dependencies = build_application_dependencies(settings)

    assert isinstance(dependencies, ApplicationDependencies)
    assert dependencies.sqlite is database
    assert isinstance(dependencies.readiness, ReadinessService)
    database_factory.assert_called_once_with(
        settings.sqlite_path,
        timeout_seconds=settings.sqlite_timeout_seconds,
    )


def test_build_application_dependencies_returns_independent_containers(
    tmp_path: Path,
) -> None:
    first = build_application_dependencies(_settings(tmp_path / "first.sqlite3"))
    second = build_application_dependencies(_settings(tmp_path / "second.sqlite3"))

    assert first is not second
    assert first.sqlite is not second.sqlite
    assert first.readiness is not second.readiness
    assert isinstance(first.sqlite, SQLiteDatabase)
    assert isinstance(second.sqlite, SQLiteDatabase)


def test_building_dependencies_does_not_initialize_sqlite_or_require_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    database_path = tmp_path / "not_initialized.sqlite3"

    dependencies = build_application_dependencies(_settings(database_path))

    assert isinstance(dependencies.sqlite, SQLiteDatabase)
    assert isinstance(dependencies.readiness, ReadinessService)
    assert dependencies.sqlite.initialization_state is SQLiteInitializationState.NEW
    assert not database_path.exists()
