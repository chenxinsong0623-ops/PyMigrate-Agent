from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import Settings
from app.core.dependencies import ApplicationDependencies
from app.core.readiness import ReadinessService
from app.main import ApplicationStartupError, create_app
from app.storage.sqlite import SQLiteDatabase, SQLiteInitializationState


def _settings(path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        sqlite_path=path,
        sqlite_timeout_seconds=2.0,
    )


def test_lifespan_initializes_and_closes_its_sqlite_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "application.sqlite3"
    application = create_app(_settings(database_path))
    database = application.state.dependencies.sqlite

    assert isinstance(database, SQLiteDatabase)
    assert database.initialization_state is SQLiteInitializationState.NEW

    with TestClient(application) as client:
        assert database.initialization_state is SQLiteInitializationState.INITIALIZED
        assert client.get("/health/live").json() == {
            "status": "ok",
            "service": "MigrationLens",
            "version": "0.1.0",
        }
        readiness_response = client.get("/health/ready")
        assert readiness_response.status_code == 503
        assert readiness_response.json()["checks"] == {
            "sqlite": {"status": "ok"},
            "document_index": {"status": "not_built"},
            "retriever_backend": {
                "status": "ok",
                "backend": "qdrant",
            },
        }

    assert database.initialization_state is SQLiteInitializationState.CLOSED
    assert database_path.is_file()


def test_two_applications_have_isolated_dependencies_and_lifecycles(
    tmp_path: Path,
) -> None:
    first_settings = _settings(tmp_path / "first.sqlite3")
    second_settings = _settings(tmp_path / "second.sqlite3")
    first = create_app(first_settings)
    second = create_app(second_settings)
    first_database = first.state.dependencies.sqlite
    second_database = second.state.dependencies.sqlite
    first_retriever = first.state.dependencies.retriever_backend
    second_retriever = second.state.dependencies.retriever_backend

    assert first is not second
    assert first.state.settings is first_settings
    assert second.state.settings is second_settings
    assert first.state.dependencies is not second.state.dependencies
    assert first_database is not second_database
    assert first_retriever is not second_retriever
    assert first.state.dependencies.readiness is not second.state.dependencies.readiness
    assert first_database.initialization_state is SQLiteInitializationState.NEW
    assert second_database.initialization_state is SQLiteInitializationState.NEW

    with TestClient(first) as client:
        assert (
            first_database.initialization_state is SQLiteInitializationState.INITIALIZED
        )
        assert second_database.initialization_state is SQLiteInitializationState.NEW
        first_readiness = client.get("/health/ready")
        assert first_readiness.status_code == 503
        assert first_readiness.json()["checks"]["sqlite"] == {"status": "ok"}
        assert second_database.initialization_state is SQLiteInitializationState.NEW

    assert first_database.initialization_state is SQLiteInitializationState.CLOSED
    assert second_database.initialization_state is SQLiteInitializationState.NEW

    with TestClient(second):
        assert (
            second_database.initialization_state
            is SQLiteInitializationState.INITIALIZED
        )

    assert second_database.initialization_state is SQLiteInitializationState.CLOSED


def test_expected_sqlite_failure_blocks_startup_and_cleans_resources(
    tmp_path: Path,
) -> None:
    blocking_parent = tmp_path / "blocking_parent"
    blocking_parent.write_text("普通文件不能作为数据库目录", encoding="utf-8")
    database_path = blocking_parent / "application.sqlite3"
    application = create_app(_settings(database_path))
    database = application.state.dependencies.sqlite

    with pytest.raises(ApplicationStartupError) as raised:
        with TestClient(application):
            pass

    assert str(raised.value) == "应用基础设施初始化失败"
    assert str(database_path) not in str(raised.value)
    assert "普通文件不能作为数据库目录" not in str(raised.value)
    assert database.initialization_state is SQLiteInitializationState.CLOSED
    assert database.initialization_error_type


class _UnexpectedFailureSQLite:
    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.initialize_calls = 0
        self.close_calls = 0

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        raise self._error

    async def close(self) -> None:
        self.close_calls += 1


class _FakeRetrieverLifecycle:
    backend_name = "qdrant"

    def __init__(
        self,
        *,
        initialize_result: bool = True,
        initialize_error: BaseException | None = None,
        close_error: BaseException | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.initialize_result = initialize_result
        self.initialize_error = initialize_error
        self.close_error = close_error
        self.events = events
        self.initialize_calls = 0
        self.ping_calls = 0
        self.close_calls = 0

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        if self.events is not None:
            self.events.append("qdrant.initialize")
        if self.initialize_error is not None:
            raise self.initialize_error
        return self.initialize_result

    async def ping(self) -> bool:
        self.ping_calls += 1
        return self.initialize_result

    async def close(self) -> None:
        self.close_calls += 1
        if self.events is not None:
            self.events.append("qdrant.close")
        if self.close_error is not None:
            raise self.close_error


class _OrderedSQLite(_UnexpectedFailureSQLite):
    def __init__(self, events: list[str]) -> None:
        super().__init__(RuntimeError("unused"))
        self.events = events

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        self.events.append("sqlite.initialize")
        return True

    async def close(self) -> None:
        self.close_calls += 1
        self.events.append("sqlite.close")

    async def ping(self) -> bool:
        return True

    async def read_metadata(self, key: str) -> str | None:
        assert key == "document_index_status"
        return "not_built"


def _injected_dependencies(
    settings: Settings,
    sqlite: object,
    retriever: _FakeRetrieverLifecycle,
) -> ApplicationDependencies:
    return ApplicationDependencies(
        sqlite=sqlite,  # type: ignore[arg-type]
        retriever_backend=retriever,
        readiness=ReadinessService(
            sqlite=sqlite,  # type: ignore[arg-type]
            retriever_backend=retriever,
            timeout_seconds=settings.readiness_timeout_seconds,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unexpected_error",
    [
        RuntimeError("未预期的编程错误"),
        KeyboardInterrupt(),
        SystemExit(),
    ],
)
async def test_unexpected_startup_error_propagates_after_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unexpected_error: BaseException,
) -> None:
    database = _UnexpectedFailureSQLite(unexpected_error)
    dependencies = ApplicationDependencies(
        sqlite=database,
        retriever_backend=_FakeRetrieverLifecycle(),
        readiness=AsyncMock(spec=ReadinessService),
    )
    monkeypatch.setattr(
        main_module,
        "build_application_dependencies",
        lambda _settings: dependencies,
    )
    application = create_app(_settings(tmp_path / "unused.sqlite3"))

    with pytest.raises(type(unexpected_error)):
        async with application.router.lifespan_context(application):
            pass

    assert database.initialize_calls == 1
    assert database.close_calls == 1


@pytest.mark.asyncio
async def test_lifespan_initializes_in_order_and_closes_in_reverse_order(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    settings = _settings(tmp_path / "unused.sqlite3")
    sqlite = _OrderedSQLite(events)
    retriever = _FakeRetrieverLifecycle(events=events)
    application = create_app(
        settings,
        dependencies=_injected_dependencies(settings, sqlite, retriever),
    )

    async with application.router.lifespan_context(application):
        events.append("application.running")

    assert events == [
        "sqlite.initialize",
        "qdrant.initialize",
        "application.running",
        "qdrant.close",
        "sqlite.close",
    ]


@pytest.mark.asyncio
async def test_qdrant_initialization_failure_blocks_startup_and_cleans_both_resources(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    settings = _settings(tmp_path / "unused.sqlite3")
    sqlite = _OrderedSQLite(events)
    retriever = _FakeRetrieverLifecycle(initialize_result=False, events=events)
    application = create_app(
        settings,
        dependencies=_injected_dependencies(settings, sqlite, retriever),
    )

    with pytest.raises(ApplicationStartupError, match="应用基础设施初始化失败"):
        async with application.router.lifespan_context(application):
            pass

    assert events == [
        "sqlite.initialize",
        "qdrant.initialize",
        "qdrant.close",
        "sqlite.close",
    ]
    assert retriever.close_calls == 1
    assert sqlite.close_calls == 1


@pytest.mark.asyncio
async def test_qdrant_programming_error_propagates_after_reverse_cleanup(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    settings = _settings(tmp_path / "unused.sqlite3")
    sqlite = _OrderedSQLite(events)
    retriever = _FakeRetrieverLifecycle(
        initialize_error=TypeError("programming defect"),
        events=events,
    )
    application = create_app(
        settings,
        dependencies=_injected_dependencies(settings, sqlite, retriever),
    )

    with pytest.raises(TypeError, match="programming defect"):
        async with application.router.lifespan_context(application):
            pass

    assert events[-2:] == ["qdrant.close", "sqlite.close"]


@pytest.mark.asyncio
async def test_qdrant_close_programming_error_still_closes_sqlite(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    settings = _settings(tmp_path / "unused.sqlite3")
    sqlite = _OrderedSQLite(events)
    retriever = _FakeRetrieverLifecycle(
        close_error=RuntimeError("close defect"),
        events=events,
    )
    application = create_app(
        settings,
        dependencies=_injected_dependencies(settings, sqlite, retriever),
    )

    with pytest.raises(RuntimeError, match="close defect"):
        async with application.router.lifespan_context(application):
            pass

    assert events[-2:] == ["qdrant.close", "sqlite.close"]


def test_health_live_does_not_probe_sqlite(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path / "health.sqlite3"))
    database = application.state.dependencies.sqlite
    retriever = application.state.dependencies.retriever_backend
    database.ping = AsyncMock(side_effect=AssertionError("live 不得调用 ping"))
    database.read_metadata = AsyncMock(
        side_effect=AssertionError("live 不得读取 metadata")
    )

    with TestClient(application) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "MigrationLens",
        "version": "0.1.0",
    }
    database.ping.assert_not_awaited()
    database.read_metadata.assert_not_awaited()
    assert retriever.ping_calls == 0
