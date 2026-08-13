from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ApiException

from app.retrieval.qdrant import (
    QdrantBackend,
    QdrantClientAdapter,
    QdrantCollectionConfig,
    QdrantDistance,
    QdrantInfrastructureError,
    QdrantPayloadError,
    QdrantPoint,
    QdrantPointPayload,
    QdrantScoredPoint,
)


def payload(chunk_id: str = "sha256:" + "1" * 64) -> QdrantPointPayload:
    return QdrantPointPayload(
        chunk_id=chunk_id,
        heading_path=("Migration guide", "BaseModel"),
        text="BaseModel.dict() becomes model_dump().",
        content_sha256="2" * 64,
        source_id="pydantic-v2-migration",
        source_url="https://example.test/migration.md",
        git_ref="v2.13.4",
        resolved_commit_sha="3" * 40,
        source_path="docs/migration.md",
        source_snapshot_sha256="4" * 64,
        source_start_char=10,
        source_end_char=53,
        continuation_index=0,
        overlap_chars=0,
        identity_occurrence=0,
        embedding_model="intfloat/multilingual-e5-small",
        embedding_revision="5" * 40,
    )


def point(point_id: str = "b4a6516d-0b4a-52ac-a64b-052ec59d16f0") -> QdrantPoint:
    vector = [0.0] * 384
    vector[0] = 1.0
    return QdrantPoint(point_id=point_id, vector=tuple(vector), payload=payload())


class DenseProtocolClient:
    def __init__(self) -> None:
        self.upsert_calls: list[tuple[QdrantPoint, ...]] = []
        self.query_calls: list[tuple[tuple[float, ...], int]] = []
        self.count_calls: list[str] = []
        self.ids_calls: list[str] = []
        self.query_result: tuple[QdrantScoredPoint, ...] = ()
        self.count_result = 0
        self.ids_result: frozenset[str] = frozenset()
        self.hang_operation: str | None = None
        self.error: BaseException | None = None

    async def collection_exists(self, collection_name: str) -> bool:
        return True

    async def get_collection_config(
        self,
        collection_name: str,
    ) -> QdrantCollectionConfig:
        return QdrantCollectionConfig(384, QdrantDistance.COSINE)

    async def create_collection(
        self,
        collection_name: str,
        config: QdrantCollectionConfig,
    ) -> None:
        raise AssertionError("existing collection must not be recreated")

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def upsert_points(
        self,
        collection_name: str,
        points: tuple[QdrantPoint, ...],
    ) -> None:
        self.upsert_calls.append(points)
        await self._gate("upsert")

    async def query_points(
        self,
        collection_name: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        self.query_calls.append((vector, limit))
        await self._gate("query")
        return self.query_result

    async def count_points(self, collection_name: str, source_id: str) -> int:
        self.count_calls.append(source_id)
        await self._gate("count")
        return self.count_result

    async def source_point_ids(
        self,
        collection_name: str,
        source_id: str,
    ) -> frozenset[str]:
        self.ids_calls.append(source_id)
        await self._gate("ids")
        return self.ids_result

    async def _gate(self, operation: str) -> None:
        if self.hang_operation == operation:
            await asyncio.Event().wait()
        if self.error is not None:
            raise self.error


async def initialized_backend(
    client: DenseProtocolClient,
    timeout: float = 0.01,
) -> QdrantBackend:
    backend = QdrantBackend(
        client=cast(Any, client),
        collection_name="documents",
        timeout_seconds=timeout,
    )
    assert await backend.initialize() is True
    return backend


def test_qdrant_dense_models_are_strict_and_validate_vectors_and_scores() -> None:
    value = point()

    assert str(UUID(value.point_id)) == value.point_id
    assert len(value.vector) == 384
    assert math.isclose(sum(component * component for component in value.vector), 1.0)
    with pytest.raises(ValueError):
        QdrantPoint(point_id=value.point_id, vector=(0.0,) * 383, payload=value.payload)
    with pytest.raises(ValueError):
        QdrantScoredPoint(
            point_id=value.point_id,
            score=float("nan"),
            payload=value.payload,
        )


@pytest.mark.asyncio
async def test_backend_upsert_query_count_and_source_ids_use_timeout_boundary() -> None:
    client = DenseProtocolClient()
    scored = QdrantScoredPoint(
        point_id=point().point_id,
        score=0.91,
        payload=payload(),
    )
    client.query_result = (scored,)
    client.count_result = 1
    client.ids_result = frozenset({point().point_id})
    backend = await initialized_backend(client)

    await backend.upsert_points((point(),))
    result = await backend.query_points(point().vector, limit=8)
    count = await backend.count_points("pydantic-v2-migration")
    ids = await backend.source_point_ids("pydantic-v2-migration")

    assert result == (scored,)
    assert count == 1
    assert ids == frozenset({point().point_id})
    assert client.upsert_calls == [(point(),)]
    assert client.query_calls == [(point().vector, 8)]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upsert", "query", "count", "ids"])
async def test_backend_dense_operations_timeout_without_fake_success(
    operation: str,
) -> None:
    client = DenseProtocolClient()
    client.hang_operation = operation
    backend = await initialized_backend(client, timeout=0.001)

    with pytest.raises(QdrantInfrastructureError, match="timed out"):
        if operation == "upsert":
            await backend.upsert_points((point(),))
        elif operation == "query":
            await backend.query_points(point().vector, limit=8)
        elif operation == "count":
            await backend.count_points("pydantic-v2-migration")
        else:
            await backend.source_point_ids("pydantic-v2-migration")


@pytest.mark.asyncio
async def test_backend_dense_programming_error_propagates() -> None:
    client = DenseProtocolClient()
    client.error = TypeError("programming defect")
    backend = await initialized_backend(client)

    with pytest.raises(TypeError, match="programming defect"):
        await backend.query_points(point().vector, limit=8)


class RawDenseClient:
    def __init__(self) -> None:
        self.upsert_kwargs: dict[str, Any] | None = None
        self.query_kwargs: dict[str, Any] | None = None
        self.count_kwargs: dict[str, Any] | None = None
        self.scroll_kwargs: list[dict[str, Any]] = []
        self.api_error: ApiException | None = None

    async def upsert(self, **kwargs: Any) -> object:
        if self.api_error is not None:
            raise self.api_error
        self.upsert_kwargs = kwargs
        return SimpleNamespace(status=models.UpdateStatus.COMPLETED)

    async def query_points(self, **kwargs: Any) -> object:
        if self.api_error is not None:
            raise self.api_error
        self.query_kwargs = kwargs
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id=point().point_id,
                    score=0.92,
                    payload=payload().model_dump(mode="json"),
                )
            ]
        )

    async def count(self, **kwargs: Any) -> object:
        if self.api_error is not None:
            raise self.api_error
        self.count_kwargs = kwargs
        return SimpleNamespace(count=1)

    async def scroll(self, **kwargs: Any) -> tuple[list[object], object | None]:
        if self.api_error is not None:
            raise self.api_error
        self.scroll_kwargs.append(kwargs)
        return ([SimpleNamespace(id=point().point_id)], None)


def adapter(raw: RawDenseClient) -> QdrantClientAdapter:
    return QdrantClientAdapter(cast(AsyncQdrantClient, raw))


@pytest.mark.asyncio
async def test_adapter_maps_upsert_with_wait_and_query_with_payload() -> None:
    raw = RawDenseClient()
    client = adapter(raw)

    await client.upsert_points("documents", (point(),))
    scored = await client.query_points("documents", point().vector, limit=8)

    assert raw.upsert_kwargs is not None
    assert raw.upsert_kwargs["collection_name"] == "documents"
    assert raw.upsert_kwargs["wait"] is True
    raw_point = raw.upsert_kwargs["points"][0]
    assert isinstance(raw_point, models.PointStruct)
    assert str(raw_point.id) == point().point_id
    assert raw_point.payload == payload().model_dump(mode="json")
    assert raw.query_kwargs == {
        "collection_name": "documents",
        "query": list(point().vector),
        "limit": 8,
        "with_payload": True,
        "with_vectors": False,
    }
    assert scored[0].score == 0.92
    assert scored[0].payload == payload()


@pytest.mark.asyncio
async def test_adapter_count_and_scroll_use_exact_source_filter() -> None:
    raw = RawDenseClient()
    client = adapter(raw)

    assert await client.count_points("documents", "pydantic-v2-migration") == 1
    assert await client.source_point_ids(
        "documents", "pydantic-v2-migration"
    ) == frozenset({point().point_id})

    assert raw.count_kwargs is not None
    condition = raw.count_kwargs["count_filter"].must[0]
    assert condition.key == "source_id"
    assert condition.match.value == "pydantic-v2-migration"
    assert raw.count_kwargs["exact"] is True
    assert raw.scroll_kwargs[0]["with_payload"] is False
    assert raw.scroll_kwargs[0]["with_vectors"] is False


@pytest.mark.asyncio
async def test_adapter_empty_query_is_a_real_empty_result() -> None:
    raw = RawDenseClient()

    async def empty_query(**_kwargs: Any) -> object:
        return SimpleNamespace(points=[])

    raw.query_points = empty_query  # type: ignore[method-assign]

    assert await adapter(raw).query_points("documents", point().vector, limit=8) == ()


@pytest.mark.asyncio
async def test_adapter_rejects_malformed_payload() -> None:
    raw = RawDenseClient()

    async def malformed_query(**_kwargs: Any) -> object:
        return SimpleNamespace(
            points=[SimpleNamespace(id=point().point_id, score=0.9, payload={})]
        )

    raw.query_points = malformed_query  # type: ignore[method-assign]

    with pytest.raises(QdrantPayloadError):
        await adapter(raw).query_points("documents", point().vector, limit=8)


@pytest.mark.asyncio
async def test_adapter_sanitizes_dense_api_errors() -> None:
    raw = RawDenseClient()
    raw.api_error = ApiException("http://user:password@host?api_key=secret")

    with pytest.raises(QdrantInfrastructureError) as captured:
        await adapter(raw).upsert_points("documents", (point(),))

    assert "password" not in str(captured.value)
    assert "api_key" not in str(captured.value)
