from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

import pytest

from app.core.embedding import (
    E5_MODEL_ID,
    E5_MODEL_REVISION,
    EMBEDDING_DIMENSION,
    EmbeddingRequest,
    EmbeddingResponse,
)
from app.ingestion.dense_index import (
    DenseIndexBuilder,
    DenseIndexBuildError,
    DenseIndexConflictError,
    chunk_to_qdrant_point,
    stable_qdrant_point_id,
)
from app.ingestion.markdown_chunker import ChunkArtifact, MarkdownChunk
from app.retrieval.qdrant import QdrantPoint, QdrantScoredPoint


def chunk(number: int, start: int) -> MarkdownChunk:
    text = f"chunk {number} official migration text"
    return MarkdownChunk(
        chunk_id=f"sha256:{number:064x}",
        text=text,
        heading_path=("Migration guide", f"Section {number}"),
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        char_length=len(text),
        source_id="pydantic-v2-migration",
        source_url="https://example.test/migration.md",
        git_ref="v2.13.4",
        resolved_commit_sha="a" * 40,
        source_path="docs/migration.md",
        source_snapshot_sha256="b" * 64,
        source_start_char=start,
        source_end_char=start + len(text),
        continuation_index=0,
        overlap_chars=0,
        identity_occurrence=0,
    )


def artifact() -> ChunkArtifact:
    chunks = (chunk(1, 0), chunk(2, 100), chunk(3, 200))
    return ChunkArtifact(
        schema_version=1,
        source_id="pydantic-v2-migration",
        source_url="https://example.test/migration.md",
        git_ref="v2.13.4",
        resolved_commit_sha="a" * 40,
        source_path="docs/migration.md",
        source_snapshot_path="data/snapshots/pydantic-v2-migration/migration.md",
        source_snapshot_sha256="b" * 64,
        source_snapshot_byte_length=999,
        source_retrieved_at_utc="2026-08-12T00:00:00Z",
        min_chars=500,
        max_chars=1200,
        overlap_chars=120,
        chunks=chunks,
    )


def write_artifact(path: Path) -> None:
    path.write_text(artifact().model_dump_json(indent=2) + "\n", encoding="utf-8")


class NormalizedEmbedding:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []
        self.fail_on_call: int | None = None

    async def embed(
        self,
        request: EmbeddingRequest,
        timeout_seconds: float,
    ) -> EmbeddingResponse:
        self.requests.append(request)
        if self.fail_on_call == len(self.requests):
            raise OSError("embedding unavailable")
        vectors = []
        for index, _text in enumerate(request.texts):
            vector = [0.0] * EMBEDDING_DIMENSION
            vector[index] = 1.0
            vectors.append(tuple(vector))
        return EmbeddingResponse(
            model=f"{E5_MODEL_ID}@{E5_MODEL_REVISION}",
            vectors=tuple(vectors),
            input_count=len(request.texts),
        )


class InMemoryQdrant:
    def __init__(self) -> None:
        self.points: dict[str, QdrantPoint] = {}
        self.upsert_calls: list[tuple[QdrantPoint, ...]] = []
        self.fail_on_upsert_call: int | None = None
        self.force_count: int | None = None

    async def upsert_points(self, points: tuple[QdrantPoint, ...]) -> None:
        self.upsert_calls.append(points)
        if self.fail_on_upsert_call == len(self.upsert_calls):
            raise OSError("qdrant unavailable")
        for value in points:
            self.points[value.point_id] = value

    async def query_points(
        self,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        return ()

    async def count_points(self, source_id: str) -> int:
        if self.force_count is not None:
            return self.force_count
        return sum(
            point.payload.source_id == source_id for point in self.points.values()
        )

    async def source_point_ids(self, source_id: str) -> frozenset[str]:
        return frozenset(
            point_id
            for point_id, value in self.points.items()
            if value.payload.source_id == source_id
        )


class MetadataStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {"document_index_status": "ready"}
        self.writes: list[tuple[str, str]] = []

    async def write_document_index_status(self, value: str) -> None:
        self.writes.append(("document_index_status", value))
        self.values["document_index_status"] = value


def builder(
    path: Path,
    *,
    embedding: NormalizedEmbedding | None = None,
    qdrant: InMemoryQdrant | None = None,
    metadata: MetadataStore | None = None,
) -> tuple[DenseIndexBuilder, NormalizedEmbedding, InMemoryQdrant, MetadataStore]:
    resolved_embedding = embedding or NormalizedEmbedding()
    resolved_qdrant = qdrant or InMemoryQdrant()
    resolved_metadata = metadata or MetadataStore()
    return (
        DenseIndexBuilder(
            artifact_path=path,
            embedding_client=resolved_embedding,
            qdrant_backend=resolved_qdrant,
            metadata_store=resolved_metadata,
            batch_size=2,
            embedding_timeout_seconds=1.0,
        ),
        resolved_embedding,
        resolved_qdrant,
        resolved_metadata,
    )


def test_stable_point_id_is_a_locked_deterministic_uuid_mapping() -> None:
    chunk_id = "sha256:" + "1" * 64

    first = stable_qdrant_point_id(chunk_id)
    second = stable_qdrant_point_id(chunk_id)
    other = stable_qdrant_point_id("sha256:" + "2" * 64)

    assert first == second == "a0bffe98-d780-55c9-b7a2-cb6d3698bab4"
    assert UUID(first).version == 5
    assert other != first


def test_chunk_to_point_preserves_full_provenance_without_local_path() -> None:
    source = chunk(1, 0)
    vector = (1.0,) + (0.0,) * 383

    value = chunk_to_qdrant_point(source, vector)

    assert value.point_id == stable_qdrant_point_id(source.chunk_id)
    assert value.payload.chunk_id == source.chunk_id
    assert value.payload.heading_path == source.heading_path
    assert value.payload.text == source.text
    assert value.payload.content_sha256 == source.content_sha256
    assert value.payload.source_id == source.source_id
    assert value.payload.source_url == source.source_url
    assert value.payload.git_ref == source.git_ref
    assert value.payload.resolved_commit_sha == source.resolved_commit_sha
    assert value.payload.source_path == source.source_path
    assert value.payload.source_snapshot_sha256 == source.source_snapshot_sha256
    assert value.payload.source_start_char == source.source_start_char
    assert value.payload.source_end_char == source.source_end_char
    assert value.payload.embedding_model == E5_MODEL_ID
    assert value.payload.embedding_revision == E5_MODEL_REVISION
    assert "D:\\" not in value.payload.model_dump_json()


@pytest.mark.asyncio
async def test_build_batches_passages_upserts_all_points_then_marks_ready(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "chunks.json"
    write_artifact(artifact_path)
    indexer, embedding, qdrant, metadata = builder(artifact_path)

    result = await indexer.build()

    assert [request.input_type for request in embedding.requests] == [
        "passage",
        "passage",
    ]
    assert embedding.requests[0].texts == tuple(
        value.text for value in artifact().chunks[:2]
    )
    assert embedding.requests[1].texts == (artifact().chunks[2].text,)
    assert [len(batch) for batch in qdrant.upsert_calls] == [2, 1]
    assert len(qdrant.points) == result.point_count == 3
    assert result.batch_count == 2
    assert metadata.writes == [
        ("document_index_status", "not_built"),
        ("document_index_status", "ready"),
    ]
    assert metadata.values["document_index_status"] == "ready"


@pytest.mark.asyncio
async def test_repeated_build_upserts_same_ids_without_duplicate_points(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "chunks.json"
    write_artifact(artifact_path)
    indexer, _embedding, qdrant, _metadata = builder(artifact_path)

    first = await indexer.build()
    first_ids = frozenset(qdrant.points)
    second = await indexer.build()

    assert first.point_count == second.point_count == 3
    assert frozenset(qdrant.points) == first_ids
    assert len(qdrant.points) == 3


@pytest.mark.asyncio
async def test_partial_upsert_failure_never_leaves_ready_status(tmp_path: Path) -> None:
    artifact_path = tmp_path / "chunks.json"
    write_artifact(artifact_path)
    qdrant = InMemoryQdrant()
    qdrant.fail_on_upsert_call = 2
    indexer, _embedding, _qdrant, metadata = builder(
        artifact_path,
        qdrant=qdrant,
    )

    with pytest.raises(OSError, match="qdrant unavailable"):
        await indexer.build()

    assert len(qdrant.points) == 2
    assert metadata.values["document_index_status"] == "not_built"
    assert metadata.writes == [("document_index_status", "not_built")]


@pytest.mark.asyncio
async def test_embedding_failure_never_leaves_ready_status(tmp_path: Path) -> None:
    artifact_path = tmp_path / "chunks.json"
    write_artifact(artifact_path)
    embedding = NormalizedEmbedding()
    embedding.fail_on_call = 2
    indexer, _embedding, _qdrant, metadata = builder(
        artifact_path,
        embedding=embedding,
    )

    with pytest.raises(OSError, match="embedding unavailable"):
        await indexer.build()

    assert metadata.values["document_index_status"] == "not_built"


@pytest.mark.asyncio
async def test_post_write_count_mismatch_does_not_mark_ready(tmp_path: Path) -> None:
    artifact_path = tmp_path / "chunks.json"
    write_artifact(artifact_path)
    qdrant = InMemoryQdrant()
    qdrant.force_count = 2
    indexer, _embedding, _qdrant, metadata = builder(
        artifact_path,
        qdrant=qdrant,
    )

    with pytest.raises(DenseIndexBuildError, match="count"):
        await indexer.build()

    assert metadata.values["document_index_status"] == "not_built"


@pytest.mark.asyncio
async def test_stale_same_source_points_fail_without_deletion(tmp_path: Path) -> None:
    artifact_path = tmp_path / "chunks.json"
    write_artifact(artifact_path)
    qdrant = InMemoryQdrant()
    stale = chunk_to_qdrant_point(chunk(99, 900), (1.0,) + (0.0,) * 383)
    qdrant.points[stale.point_id] = stale
    indexer, _embedding, _qdrant, metadata = builder(
        artifact_path,
        qdrant=qdrant,
    )

    with pytest.raises(DenseIndexConflictError, match="stale"):
        await indexer.build()

    assert stale.point_id in qdrant.points
    assert metadata.values["document_index_status"] == "not_built"


@pytest.mark.asyncio
async def test_build_does_not_modify_day_nine_artifact(tmp_path: Path) -> None:
    artifact_path = tmp_path / "chunks.json"
    write_artifact(artifact_path)
    before = artifact_path.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    indexer, _embedding, _qdrant, _metadata = builder(artifact_path)

    await indexer.build()

    assert artifact_path.read_bytes() == before
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == before_hash
