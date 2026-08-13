from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

import pytest
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ApiException

from app.core.embedding import EMBEDDING_DIMENSION
from app.retrieval.qdrant import (
    QDRANT_BACKEND_NAME,
    QdrantBackend,
    QdrantBackendState,
    QdrantClientAdapter,
    QdrantClientProtocol,
    QdrantCollectionConfig,
    QdrantCollectionConfigurationError,
    QdrantDistance,
    QdrantInfrastructureError,
    QdrantPoint,
    QdrantScoredPoint,
)


class FakeQdrantClient:
    def __init__(
        self,
        *,
        exists: bool = False,
        config: QdrantCollectionConfig | None = None,
    ) -> None:
        self.exists = exists
        self.config = config or expected_config()
        self.ping_result = True
        self.collection_exists_calls = 0
        self.get_config_calls = 0
        self.create_calls: list[tuple[str, QdrantCollectionConfig]] = []
        self.ping_calls = 0
        self.close_calls = 0
        self.collection_exists_error: BaseException | None = None
        self.get_config_error: BaseException | None = None
        self.create_error: BaseException | None = None
        self.ping_error: BaseException | None = None
        self.close_error: BaseException | None = None
        self.hang_operation: str | None = None

    async def collection_exists(self, collection_name: str) -> bool:
        self.collection_exists_calls += 1
        await self._maybe_hang("collection_exists")
        if self.collection_exists_error is not None:
            raise self.collection_exists_error
        return self.exists

    async def get_collection_config(
        self,
        collection_name: str,
    ) -> QdrantCollectionConfig:
        self.get_config_calls += 1
        await self._maybe_hang("get_collection_config")
        if self.get_config_error is not None:
            raise self.get_config_error
        return self.config

    async def create_collection(
        self,
        collection_name: str,
        config: QdrantCollectionConfig,
    ) -> None:
        self.create_calls.append((collection_name, config))
        await self._maybe_hang("create_collection")
        if self.create_error is not None:
            raise self.create_error

    async def ping(self) -> bool:
        self.ping_calls += 1
        await self._maybe_hang("ping")
        if self.ping_error is not None:
            raise self.ping_error
        return self.ping_result

    async def upsert_points(
        self,
        collection_name: str,
        points: tuple[QdrantPoint, ...],
    ) -> None:
        return None

    async def query_points(
        self,
        collection_name: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        return ()

    async def count_points(self, collection_name: str, source_id: str) -> int:
        return 0

    async def source_point_ids(
        self,
        collection_name: str,
        source_id: str,
    ) -> frozenset[str]:
        return frozenset()

    async def close(self) -> None:
        self.close_calls += 1
        await self._maybe_hang("close")
        if self.close_error is not None:
            raise self.close_error

    async def _maybe_hang(self, operation: str) -> None:
        if self.hang_operation == operation:
            await asyncio.Event().wait()


def expected_config() -> QdrantCollectionConfig:
    return QdrantCollectionConfig(
        vector_size=EMBEDDING_DIMENSION,
        distance=QdrantDistance.COSINE,
    )


def build_backend(
    client: FakeQdrantClient,
    *,
    timeout_seconds: float = 0.01,
) -> QdrantBackend:
    return QdrantBackend(
        client=client,
        collection_name="migrationlens-documents",
        timeout_seconds=timeout_seconds,
    )


def test_fake_client_satisfies_minimal_protocol() -> None:
    assert isinstance(FakeQdrantClient(), QdrantClientProtocol)


def test_backend_constructor_performs_no_client_io() -> None:
    client = FakeQdrantClient()
    backend = build_backend(client)

    assert backend.state is QdrantBackendState.NEW
    assert backend.backend_name == QDRANT_BACKEND_NAME
    assert client.collection_exists_calls == 0
    assert client.create_calls == []
    assert client.ping_calls == 0
    assert client.close_calls == 0


@pytest.mark.asyncio
async def test_initialize_creates_missing_collection_with_fixed_contract() -> None:
    client = FakeQdrantClient(exists=False)
    backend = build_backend(client)

    assert await backend.initialize() is True
    assert client.create_calls == [("migrationlens-documents", expected_config())]
    assert client.create_calls[0][1].vector_size == 384
    assert client.create_calls[0][1].distance is QdrantDistance.COSINE
    assert backend.state is QdrantBackendState.INITIALIZED


@pytest.mark.asyncio
async def test_initialize_validates_existing_collection_without_creating() -> None:
    client = FakeQdrantClient(exists=True, config=expected_config())
    backend = build_backend(client)

    assert await backend.initialize() is True
    assert client.get_config_calls == 1
    assert client.create_calls == []


@pytest.mark.parametrize(
    "invalid_config",
    [
        QdrantCollectionConfig(383, QdrantDistance.COSINE),
        QdrantCollectionConfig(384, QdrantDistance.DOT),
    ],
)
@pytest.mark.asyncio
async def test_initialize_rejects_existing_collection_mismatch_without_recreate(
    invalid_config: QdrantCollectionConfig,
) -> None:
    client = FakeQdrantClient(exists=True, config=invalid_config)
    backend = build_backend(client)

    assert await backend.initialize() is False
    assert backend.state is QdrantBackendState.FAILED
    assert client.create_calls == []
    assert client.close_calls == 1
    assert not hasattr(client, "delete_collection")


@pytest.mark.asyncio
async def test_initialize_is_idempotent_after_success() -> None:
    client = FakeQdrantClient(exists=False)
    backend = build_backend(client)

    assert await backend.initialize() is True
    assert await backend.initialize() is True
    assert client.collection_exists_calls == 1
    assert len(client.create_calls) == 1


@pytest.mark.asyncio
async def test_initialize_does_not_retry_after_expected_failure() -> None:
    client = FakeQdrantClient()
    client.collection_exists_error = QdrantInfrastructureError("token=secret")
    backend = build_backend(client)

    assert await backend.initialize() is False
    assert await backend.initialize() is False
    assert client.collection_exists_calls == 1
    assert client.close_calls == 1


@pytest.mark.parametrize(
    ("error_field", "error_factory"),
    [
        ("collection_exists", lambda: QdrantInfrastructureError("unavailable")),
        ("create", lambda: QdrantInfrastructureError("unavailable")),
    ],
)
@pytest.mark.asyncio
async def test_initialize_converts_expected_infrastructure_errors(
    error_field: str,
    error_factory: Callable[[], BaseException],
) -> None:
    client = FakeQdrantClient(exists=False)
    setattr(client, f"{error_field}_error", error_factory())
    backend = build_backend(client)

    assert await backend.initialize() is False
    assert backend.state is QdrantBackendState.FAILED
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_initialize_times_out_quickly_and_cleans_up() -> None:
    client = FakeQdrantClient()
    client.hang_operation = "collection_exists"
    backend = build_backend(client, timeout_seconds=0.001)

    assert await backend.initialize() is False
    assert backend.state is QdrantBackendState.FAILED
    assert client.close_calls == 1

    await backend.close()
    assert client.close_calls == 1
    assert backend.state is QdrantBackendState.CLOSED


@pytest.mark.asyncio
async def test_initialize_propagates_programming_error_after_cleanup() -> None:
    client = FakeQdrantClient()
    client.collection_exists_error = TypeError("programming defect")
    backend = build_backend(client)

    with pytest.raises(TypeError, match="programming defect"):
        await backend.initialize()

    assert backend.state is QdrantBackendState.FAILED
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_ping_requires_successful_initialization() -> None:
    client = FakeQdrantClient()
    backend = build_backend(client)

    assert await backend.ping() is False
    assert client.ping_calls == 0


@pytest.mark.asyncio
async def test_ping_returns_client_result_after_initialization() -> None:
    client = FakeQdrantClient(exists=True)
    backend = build_backend(client)
    assert await backend.initialize() is True

    assert await backend.ping() is True
    client.ping_result = False
    assert await backend.ping() is False
    assert client.ping_calls == 2


@pytest.mark.asyncio
async def test_ping_converts_expected_infrastructure_error() -> None:
    client = FakeQdrantClient(exists=True)
    backend = build_backend(client)
    assert await backend.initialize() is True
    client.ping_error = QdrantInfrastructureError("http://user:secret@host")

    assert await backend.ping() is False


@pytest.mark.asyncio
async def test_ping_timeout_returns_false_without_long_wait() -> None:
    client = FakeQdrantClient(exists=True)
    backend = build_backend(client, timeout_seconds=0.001)
    assert await backend.initialize() is True
    client.hang_operation = "ping"

    assert await backend.ping() is False


@pytest.mark.asyncio
async def test_ping_propagates_programming_error() -> None:
    client = FakeQdrantClient(exists=True)
    backend = build_backend(client)
    assert await backend.initialize() is True
    client.ping_error = AttributeError("programming defect")

    with pytest.raises(AttributeError, match="programming defect"):
        await backend.ping()


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    client = FakeQdrantClient(exists=True)
    backend = build_backend(client)
    assert await backend.initialize() is True

    await backend.close()
    await backend.close()

    assert client.close_calls == 1
    assert backend.state is QdrantBackendState.CLOSED


@pytest.mark.asyncio
async def test_close_before_initialize_closes_owned_client_once() -> None:
    client = FakeQdrantClient()
    backend = build_backend(client)

    await backend.close()
    assert await backend.initialize() is False

    assert client.close_calls == 1
    assert backend.state is QdrantBackendState.CLOSED


@pytest.mark.asyncio
async def test_close_expected_error_is_safe_and_not_retried() -> None:
    client = FakeQdrantClient()
    client.close_error = QdrantInfrastructureError("api_key=secret")
    backend = build_backend(client)

    await backend.close()
    await backend.close()

    assert client.close_calls == 1
    assert backend.state is QdrantBackendState.CLOSED


@pytest.mark.asyncio
async def test_close_timeout_is_safe_and_not_retried() -> None:
    client = FakeQdrantClient()
    client.hang_operation = "close"
    backend = build_backend(client, timeout_seconds=0.001)

    await backend.close()
    await backend.close()

    assert client.close_calls == 1
    assert backend.state is QdrantBackendState.CLOSED


@pytest.mark.asyncio
async def test_close_programming_error_propagates() -> None:
    client = FakeQdrantClient()
    client.close_error = RuntimeError("programming defect")
    backend = build_backend(client)

    with pytest.raises(RuntimeError, match="programming defect"):
        await backend.close()

    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_safe_log_does_not_expose_exception_text_or_internal_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeQdrantClient()
    client.collection_exists_error = QdrantInfrastructureError(
        "http://user:password@localhost?api_key=top-secret"
    )
    backend = build_backend(client)

    with caplog.at_level(logging.WARNING):
        assert await backend.initialize() is False

    output = caplog.text
    assert "password" not in output
    assert "api_key" not in output
    assert "top-secret" not in output
    assert "migrationlens-documents" not in output


def test_backend_exposes_no_search_or_write_api() -> None:
    backend = build_backend(FakeQdrantClient())

    assert not hasattr(backend, "search")
    assert not hasattr(backend, "upsert")
    assert not hasattr(backend, "delete_collection")


class FakeRawQdrantClient:
    def __init__(self) -> None:
        self.exists = True
        self.created: tuple[str, models.VectorParams] | None = None
        self.closed = False
        self.api_error: ApiException | None = None

    async def collection_exists(self, collection_name: str) -> bool:
        if self.api_error:
            raise self.api_error
        return self.exists

    async def get_collection(self, collection_name: str) -> object:
        if self.api_error:
            raise self.api_error
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=models.VectorParams(
                        size=EMBEDDING_DIMENSION,
                        distance=models.Distance.COSINE,
                    )
                )
            )
        )

    async def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: models.VectorParams,
    ) -> bool:
        if self.api_error:
            raise self.api_error
        self.created = (collection_name, vectors_config)
        return True

    async def get_collections(self) -> object:
        if self.api_error:
            raise self.api_error
        return object()

    async def close(self) -> None:
        if self.api_error:
            raise self.api_error
        self.closed = True


def adapter_for(raw: FakeRawQdrantClient) -> QdrantClientAdapter:
    return QdrantClientAdapter(cast(AsyncQdrantClient, raw))


@pytest.mark.asyncio
async def test_adapter_maps_public_qdrant_collection_api() -> None:
    raw = FakeRawQdrantClient()
    adapter = adapter_for(raw)

    assert await adapter.collection_exists("documents") is True
    assert await adapter.get_collection_config("documents") == expected_config()
    await adapter.create_collection("documents", expected_config())
    assert raw.created is not None
    assert raw.created[0] == "documents"
    assert raw.created[1].size == EMBEDDING_DIMENSION
    assert raw.created[1].distance is models.Distance.COSINE
    assert await adapter.ping() is True
    await adapter.close()
    assert raw.closed is True


@pytest.mark.asyncio
async def test_adapter_rejects_named_vectors() -> None:
    raw = FakeRawQdrantClient()

    async def named_collection(collection_name: str) -> object:
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={
                        "dense": models.VectorParams(
                            size=384,
                            distance=models.Distance.COSINE,
                        )
                    }
                )
            )
        )

    raw.get_collection = named_collection  # type: ignore[method-assign]
    adapter = adapter_for(raw)

    with pytest.raises(QdrantCollectionConfigurationError):
        await adapter.get_collection_config("documents")


@pytest.mark.asyncio
async def test_adapter_hides_qdrant_api_exception_text() -> None:
    raw = FakeRawQdrantClient()
    raw.api_error = ApiException("http://user:password@host?api_key=secret")
    adapter = adapter_for(raw)

    with pytest.raises(QdrantInfrastructureError) as captured:
        await adapter.collection_exists("documents")

    assert "password" not in str(captured.value)
    assert "api_key" not in str(captured.value)
    assert captured.value.__cause__ is None
