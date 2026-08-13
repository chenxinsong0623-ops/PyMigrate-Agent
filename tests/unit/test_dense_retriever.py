from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.core.embedding import (
    E5_MODEL_ID,
    E5_MODEL_REVISION,
    EMBEDDING_DIMENSION,
    EmbeddingRequest,
    EmbeddingResponse,
)
from app.retrieval.dense import (
    DENSE_TOP_K_MAX,
    DenseRetriever,
    DenseSearchResult,
)
from app.retrieval.qdrant import QdrantPointPayload, QdrantScoredPoint


def payload(number: int) -> QdrantPointPayload:
    return QdrantPointPayload(
        chunk_id=f"sha256:{number:064x}",
        heading_path=("Migration guide", f"Section {number}"),
        text=f"official text {number}",
        content_sha256=f"{number + 10:064x}",
        source_id="pydantic-v2-migration",
        source_url="https://example.test/migration.md",
        git_ref="v2.13.4",
        resolved_commit_sha="a" * 40,
        source_path="docs/migration.md",
        source_snapshot_sha256="b" * 64,
        source_start_char=number * 100,
        source_end_char=number * 100 + 15,
        continuation_index=0,
        overlap_chars=0,
        identity_occurrence=0,
        embedding_model=E5_MODEL_ID,
        embedding_revision=E5_MODEL_REVISION,
    )


class QueryEmbedding:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []

    async def embed(
        self,
        request: EmbeddingRequest,
        timeout_seconds: float,
    ) -> EmbeddingResponse:
        self.requests.append(request)
        vector = (1.0,) + (0.0,) * (EMBEDDING_DIMENSION - 1)
        return EmbeddingResponse(
            model=f"{E5_MODEL_ID}@{E5_MODEL_REVISION}",
            vectors=(vector,),
            input_count=1,
        )


class QueryQdrant:
    def __init__(self, results: tuple[QdrantScoredPoint, ...]) -> None:
        self.results = results
        self.calls: list[tuple[tuple[float, ...], int]] = []

    async def query_points(
        self,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        self.calls.append((vector, limit))
        return self.results


def scored(number: int, score: float) -> QdrantScoredPoint:
    return QdrantScoredPoint(
        point_id=f"00000000-0000-5000-8000-{number:012d}",
        score=score,
        payload=payload(number),
    )


def retriever(
    results: tuple[QdrantScoredPoint, ...],
) -> tuple[DenseRetriever, QueryEmbedding, QueryQdrant]:
    embedding = QueryEmbedding()
    qdrant = QueryQdrant(results)
    return (
        DenseRetriever(
            embedding_client=embedding,
            qdrant_backend=qdrant,
            embedding_timeout_seconds=1.0,
        ),
        embedding,
        qdrant,
    )


@pytest.mark.asyncio
async def test_dense_search_embeds_raw_query_and_returns_contiguous_typed_ranks() -> (
    None
):
    service, embedding, qdrant = retriever((scored(1, 0.91), scored(2, 0.81)))

    results = await service.search("BaseModel.dict() migration", top_k=8)

    assert embedding.requests == [
        EmbeddingRequest(
            input_type="query",
            texts=("BaseModel.dict() migration",),
        )
    ]
    assert embedding.requests[0].model_inputs == ("query: BaseModel.dict() migration",)
    assert qdrant.calls[0][1] == DENSE_TOP_K_MAX == 8
    assert all(isinstance(result, DenseSearchResult) for result in results)
    assert [result.rank for result in results] == [1, 2]
    assert [result.score for result in results] == [0.91, 0.81]
    assert results[0].chunk_id == payload(1).chunk_id
    assert results[0].heading_path == payload(1).heading_path
    assert results[0].text == payload(1).text
    assert results[0].source_url == payload(1).source_url
    assert results[0].resolved_commit_sha == payload(1).resolved_commit_sha
    assert math.isfinite(results[0].score)


@pytest.mark.asyncio
async def test_dense_search_empty_index_returns_empty_tuple() -> None:
    service, _embedding, qdrant = retriever(())

    assert await service.search("validator migration") == ()
    assert qdrant.calls[0][1] == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k", [0, -1, 9, True, 1.5])
async def test_dense_search_rejects_top_k_outside_one_to_eight(top_k: object) -> None:
    service, embedding, qdrant = retriever(())

    with pytest.raises((TypeError, ValueError)):
        await service.search("query", top_k=top_k)  # type: ignore[arg-type]

    assert embedding.requests == []
    assert qdrant.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "   ", "query: already prefixed"])
async def test_dense_search_rejects_invalid_raw_query(query: str) -> None:
    service, _embedding, qdrant = retriever(())

    with pytest.raises((ValueError, ValidationError)):
        await service.search(query)

    assert qdrant.calls == []


def test_dense_result_is_frozen_strict_and_has_no_hybrid_fields() -> None:
    result = DenseSearchResult(
        rank=1,
        score=0.9,
        chunk_id=payload(1).chunk_id,
        heading_path=payload(1).heading_path,
        text=payload(1).text,
        content_sha256=payload(1).content_sha256,
        source_id=payload(1).source_id,
        source_url=payload(1).source_url,
        git_ref=payload(1).git_ref,
        resolved_commit_sha=payload(1).resolved_commit_sha,
        source_path=payload(1).source_path,
        source_snapshot_sha256=payload(1).source_snapshot_sha256,
    )

    assert not hasattr(result, "bm25_rank")
    assert not hasattr(result, "rrf_score")
    assert not hasattr(result, "hybrid_rank")
    with pytest.raises(ValidationError):
        result.rank = 2  # type: ignore[misc]
    with pytest.raises(ValidationError):
        DenseSearchResult.model_validate(
            {**result.model_dump(), "unexpected": "forbidden"}
        )
