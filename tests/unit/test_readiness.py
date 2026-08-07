import asyncio
import sqlite3
from collections.abc import Awaitable, Callable

import pytest
from pydantic import ValidationError

from app.core.readiness import (
    ReadinessProbeError,
    ReadinessResult,
    ReadinessService,
)


class FakeSQLite:
    def __init__(
        self,
        *,
        ping: bool | BaseException | Callable[[], Awaitable[bool]] = True,
        metadata: (
            str | None | BaseException | Callable[[], Awaitable[str | None]]
        ) = "ready",
    ) -> None:
        self._ping = ping
        self._metadata = metadata
        self.ping_calls = 0
        self.metadata_calls = 0
        self.metadata_keys: list[str] = []

    async def ping(self) -> bool:
        self.ping_calls += 1
        if isinstance(self._ping, BaseException):
            raise self._ping
        if callable(self._ping):
            return await self._ping()
        return self._ping

    async def read_metadata(self, key: str) -> str | None:
        self.metadata_calls += 1
        self.metadata_keys.append(key)
        if isinstance(self._metadata, BaseException):
            raise self._metadata
        if callable(self._metadata):
            return await self._metadata()
        return self._metadata


class FakeRetrieverProbe:
    def __init__(
        self,
        *,
        backend_name: str = "injected-backend",
        available: bool | BaseException | Callable[[], Awaitable[bool]] = True,
    ) -> None:
        self._backend_name = backend_name
        self._available = available
        self.ping_calls = 0

    @property
    def backend_name(self) -> str:
        return self._backend_name

    async def ping(self) -> bool:
        self.ping_calls += 1
        if isinstance(self._available, BaseException):
            raise self._available
        if callable(self._available):
            return await self._available()
        return self._available


def _service(
    sqlite: FakeSQLite,
    *,
    probe: FakeRetrieverProbe | None = None,
    timeout_seconds: float = 0.05,
) -> ReadinessService:
    return ReadinessService(
        sqlite=sqlite,
        retriever_backend=probe,
        timeout_seconds=timeout_seconds,
    )


async def _never_bool() -> bool:
    await asyncio.Event().wait()
    return True


async def _never_metadata() -> str | None:
    await asyncio.Event().wait()
    return "ready"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("available", "expected_status"),
    [(True, "ok"), (False, "error")],
)
async def test_sqlite_ping_result_is_mapped_to_a_stable_status(
    available: bool,
    expected_status: str,
) -> None:
    result = await _service(FakeSQLite(ping=available)).check()

    assert result.checks.sqlite.status == expected_status


@pytest.mark.asyncio
async def test_sqlite_ping_timeout_is_reported_without_a_long_wait() -> None:
    result = await _service(
        FakeSQLite(ping=_never_bool),
        timeout_seconds=0.001,
    ).check()

    assert result.status == "not_ready"
    assert result.checks.sqlite.status == "timeout"


@pytest.mark.asyncio
async def test_expected_sqlite_error_is_safely_reported() -> None:
    secret = r"C:\private\migrationlens.sqlite3"
    result = await _service(FakeSQLite(ping=sqlite3.OperationalError(secret))).check()

    assert result.checks.sqlite.status == "error"
    assert secret not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metadata", "expected_status"),
    [
        ("ready", "ready"),
        ("not_built", "not_built"),
        (None, "missing"),
        ("unexpected-value", "error"),
    ],
)
async def test_document_index_metadata_is_mapped_to_a_stable_status(
    metadata: str | None,
    expected_status: str,
) -> None:
    result = await _service(FakeSQLite(metadata=metadata)).check()

    assert result.checks.document_index.status == expected_status


@pytest.mark.asyncio
async def test_document_index_timeout_is_reported() -> None:
    result = await _service(
        FakeSQLite(metadata=_never_metadata),
        timeout_seconds=0.001,
    ).check()

    assert result.status == "not_ready"
    assert result.checks.document_index.status == "timeout"


@pytest.mark.asyncio
async def test_expected_metadata_error_is_safely_reported() -> None:
    secret = r"C:\private\metadata.sqlite3"
    result = await _service(
        FakeSQLite(metadata=sqlite3.OperationalError(secret))
    ).check()

    assert result.checks.document_index.status == "error"
    assert secret not in result.model_dump_json()


@pytest.mark.asyncio
async def test_missing_retriever_backend_is_not_configured() -> None:
    result = await _service(FakeSQLite()).check()

    assert result.checks.retriever_backend.status == "not_configured"
    assert result.checks.retriever_backend.backend is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("available", "expected_status"),
    [(True, "ok"), (False, "error")],
)
async def test_retriever_probe_result_includes_the_injected_backend_name(
    available: bool,
    expected_status: str,
) -> None:
    probe = FakeRetrieverProbe(
        backend_name="configured-backend",
        available=available,
    )

    result = await _service(FakeSQLite(), probe=probe).check()

    assert result.checks.retriever_backend.status == expected_status
    assert result.checks.retriever_backend.backend == "configured-backend"


@pytest.mark.asyncio
async def test_retriever_probe_timeout_is_reported() -> None:
    probe = FakeRetrieverProbe(available=_never_bool)

    result = await _service(
        FakeSQLite(),
        probe=probe,
        timeout_seconds=0.001,
    ).check()

    assert result.status == "not_ready"
    assert result.checks.retriever_backend.status == "timeout"


@pytest.mark.asyncio
async def test_expected_retriever_error_does_not_leak_its_message() -> None:
    secret = "api-key=should-not-leak"
    probe = FakeRetrieverProbe(available=ReadinessProbeError(secret))

    result = await _service(FakeSQLite(), probe=probe).check()

    assert result.checks.retriever_backend.status == "error"
    assert secret not in result.model_dump_json()


@pytest.mark.asyncio
async def test_all_checks_must_pass_for_the_application_to_be_ready() -> None:
    ready = await _service(
        FakeSQLite(ping=True, metadata="ready"),
        probe=FakeRetrieverProbe(available=True),
    ).check()
    not_ready = await _service(
        FakeSQLite(ping=True, metadata="not_built"),
        probe=FakeRetrieverProbe(available=True),
    ).check()

    assert ready.status == "ready"
    assert not_ready.status == "not_ready"


@pytest.mark.asyncio
async def test_constructor_does_not_probe_and_check_uses_the_same_sqlite() -> None:
    sqlite = FakeSQLite()
    probe = FakeRetrieverProbe()

    service = _service(sqlite, probe=probe)

    assert sqlite.ping_calls == 0
    assert sqlite.metadata_calls == 0
    assert probe.ping_calls == 0

    await service.check()

    assert sqlite.ping_calls == 1
    assert sqlite.metadata_calls == 1
    assert sqlite.metadata_keys == ["document_index_status"]
    assert probe.ping_calls == 1


@pytest.mark.asyncio
async def test_repeated_checks_read_fresh_state_without_a_cache() -> None:
    metadata_values = iter(["not_built", "ready"])

    async def changing_metadata() -> str | None:
        return next(metadata_values)

    sqlite = FakeSQLite(metadata=changing_metadata)
    service = _service(sqlite, probe=FakeRetrieverProbe())

    first = await service.check()
    second = await service.check()

    assert first.status == "not_ready"
    assert first.checks.document_index.status == "not_built"
    assert second.status == "ready"
    assert second.checks.document_index.status == "ready"
    assert sqlite.ping_calls == 2
    assert sqlite.metadata_calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sqlite", "probe"),
    [
        (FakeSQLite(ping=TypeError("programming error")), None),
        (
            FakeSQLite(),
            FakeRetrieverProbe(available=RuntimeError("programming error")),
        ),
    ],
)
async def test_unexpected_programming_errors_propagate(
    sqlite: FakeSQLite,
    probe: FakeRetrieverProbe | None,
) -> None:
    with pytest.raises((TypeError, RuntimeError)):
        await _service(sqlite, probe=probe).check()


def test_readiness_result_models_are_frozen_and_typed() -> None:
    result = ReadinessResult.model_validate(
        {
            "status": "ready",
            "checks": {
                "sqlite": {"status": "ok"},
                "document_index": {"status": "ready"},
                "retriever_backend": {
                    "status": "ok",
                    "backend": "configured-backend",
                },
            },
        }
    )

    with pytest.raises(ValidationError):
        result.status = "not_ready"
    with pytest.raises(ValidationError):
        ReadinessResult.model_validate(
            {
                "status": "unknown",
                "checks": result.checks.model_dump(),
            }
        )
