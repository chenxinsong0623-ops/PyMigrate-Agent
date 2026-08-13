"""从 Day 9 chunk artifact 显式构建真实 Qdrant dense index。"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid5

from app.core.config import Settings
from app.core.embedding import (
    E5_MODEL_ID,
    E5_MODEL_REVISION,
    E5Embedding,
    EmbeddingClient,
    EmbeddingInfrastructureError,
    EmbeddingRequest,
    EmbeddingVector,
)
from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    MarkdownChunk,
    MarkdownChunkingError,
    load_chunk_artifact,
)
from app.retrieval.qdrant import (
    QdrantInfrastructureError,
    QdrantPoint,
    QdrantPointPayload,
    build_qdrant_backend,
)
from app.storage.sqlite import SQLiteDatabase

QDRANT_POINT_NAMESPACE = UUID("9202dd18-24a1-5d8e-9bf1-626c51c77d1d")
_CHUNK_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class DenseIndexBuildError(RuntimeError):
    """Dense index 没有通过完整写入与 post-write verification。"""


class DenseIndexConflictError(DenseIndexBuildError):
    """当前 source 存在不属于本 artifact 的 stale points。"""


class DocumentIndexMetadataStore(Protocol):
    """索引构建只需要的最小 SQLite metadata 写边界。"""

    async def write_document_index_status(self, status: str) -> None:
        """把索引状态更新为 not_built 或 ready。"""
        ...


class DenseIndexQdrant(Protocol):
    """索引构建所需的最小 Qdrant point 能力。"""

    async def upsert_points(self, points: tuple[QdrantPoint, ...]) -> None:
        """等待一批稳定 IDs 完成 upsert。"""
        ...

    async def count_points(self, source_id: str) -> int:
        """精确统计 source point 数量。"""
        ...

    async def source_point_ids(self, source_id: str) -> frozenset[str]:
        """读取 source 的全部 point IDs。"""
        ...


@dataclass(frozen=True, slots=True)
class DenseIndexBuildResult:
    """一次完整 dense index 构建的工程结果。"""

    source_id: str
    point_count: int
    batch_count: int
    embedding_model: str
    embedding_revision: str


def stable_qdrant_point_id(chunk_id: str) -> str:
    """把 Day 9 content-addressed chunk ID 映射为固定 namespace UUIDv5。"""
    if not isinstance(chunk_id, str) or _CHUNK_ID_PATTERN.fullmatch(chunk_id) is None:
        raise ValueError("chunk_id 不满足 Day 9 identity 契约")
    return str(uuid5(QDRANT_POINT_NAMESPACE, chunk_id))


def chunk_to_qdrant_point(
    chunk: MarkdownChunk,
    vector: EmbeddingVector,
) -> QdrantPoint:
    """无损映射 chunk provenance、模型身份和 normalized vector。"""
    return QdrantPoint(
        point_id=stable_qdrant_point_id(chunk.chunk_id),
        vector=vector,
        payload=QdrantPointPayload(
            chunk_id=chunk.chunk_id,
            heading_path=chunk.heading_path,
            text=chunk.text,
            content_sha256=chunk.content_sha256,
            source_id=chunk.source_id,
            source_url=chunk.source_url,
            git_ref=chunk.git_ref,
            resolved_commit_sha=chunk.resolved_commit_sha,
            source_path=chunk.source_path,
            source_snapshot_sha256=chunk.source_snapshot_sha256,
            source_start_char=chunk.source_start_char,
            source_end_char=chunk.source_end_char,
            continuation_index=chunk.continuation_index,
            overlap_chars=chunk.overlap_chars,
            identity_occurrence=chunk.identity_occurrence,
            embedding_model=E5_MODEL_ID,
            embedding_revision=E5_MODEL_REVISION,
        ),
    )


class DenseIndexBuilder:
    """显式、可重复地把一个严格 chunk artifact 建成 dense index。"""

    def __init__(
        self,
        *,
        artifact_path: Path,
        embedding_client: EmbeddingClient,
        qdrant_backend: DenseIndexQdrant,
        metadata_store: DocumentIndexMetadataStore,
        batch_size: int,
        embedding_timeout_seconds: float,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size 必须是整数")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        if (
            isinstance(embedding_timeout_seconds, bool)
            or not isinstance(embedding_timeout_seconds, (int, float))
            or embedding_timeout_seconds <= 0
        ):
            raise ValueError("embedding_timeout_seconds 必须大于 0")
        self._artifact_path = artifact_path
        self._embedding_client = embedding_client
        self._qdrant = qdrant_backend
        self._metadata_store = metadata_store
        self._batch_size = batch_size
        self._embedding_timeout_seconds = float(embedding_timeout_seconds)

    async def build(self) -> DenseIndexBuildResult:
        """完成全部 upsert 和 read verification 后才发布 ready。"""
        artifact = load_chunk_artifact(self._artifact_path)
        expected_ids = frozenset(
            stable_qdrant_point_id(chunk.chunk_id) for chunk in artifact.chunks
        )
        if len(expected_ids) != len(artifact.chunks):
            raise DenseIndexBuildError("Qdrant point ID collision detected")

        await self._metadata_store.write_document_index_status("not_built")
        existing_ids = await self._qdrant.source_point_ids(artifact.source_id)
        stale_ids = existing_ids - expected_ids
        if stale_ids:
            raise DenseIndexConflictError(
                "stale points exist for the current source; no data was deleted"
            )

        batch_count = 0
        expected_model = f"{E5_MODEL_ID}@{E5_MODEL_REVISION}"
        for start in range(0, len(artifact.chunks), self._batch_size):
            chunk_batch = artifact.chunks[start : start + self._batch_size]
            request = EmbeddingRequest(
                input_type="passage",
                texts=tuple(chunk.text for chunk in chunk_batch),
            )
            response = await self._embedding_client.embed(
                request,
                timeout_seconds=self._embedding_timeout_seconds,
            )
            if response.model != expected_model:
                raise DenseIndexBuildError("embedding model identity changed")
            points = tuple(
                chunk_to_qdrant_point(chunk, vector)
                for chunk, vector in zip(
                    chunk_batch,
                    response.vectors,
                    strict=True,
                )
            )
            await self._qdrant.upsert_points(points)
            batch_count += 1

        actual_count = await self._qdrant.count_points(artifact.source_id)
        actual_ids = await self._qdrant.source_point_ids(artifact.source_id)
        if actual_count != len(artifact.chunks):
            raise DenseIndexBuildError("post-write point count verification failed")
        if actual_ids != expected_ids:
            raise DenseIndexBuildError("post-write point ID verification failed")

        await self._metadata_store.write_document_index_status("ready")
        return DenseIndexBuildResult(
            source_id=artifact.source_id,
            point_count=actual_count,
            batch_count=batch_count,
            embedding_model=E5_MODEL_ID,
            embedding_revision=E5_MODEL_REVISION,
        )


async def _run_build(settings: Settings, artifact_path: Path) -> int:
    sqlite = SQLiteDatabase(
        settings.sqlite_path,
        timeout_seconds=settings.sqlite_timeout_seconds,
    )
    qdrant = build_qdrant_backend(settings)
    embedding = E5Embedding(
        cache_folder=settings.embedding_cache_path,
        batch_size=settings.embedding_batch_size,
    )
    try:
        if not await sqlite.initialize():
            raise DenseIndexBuildError("SQLite initialization failed")
        if not await qdrant.initialize():
            raise DenseIndexBuildError("Qdrant initialization failed")
        metadata = await embedding.load(settings.embedding_timeout_seconds)
        result = await DenseIndexBuilder(
            artifact_path=artifact_path,
            embedding_client=embedding,
            qdrant_backend=qdrant,
            metadata_store=sqlite,
            batch_size=settings.embedding_batch_size,
            embedding_timeout_seconds=settings.embedding_timeout_seconds,
        ).build()
    except (
        DenseIndexBuildError,
        EmbeddingInfrastructureError,
        MarkdownChunkingError,
        QdrantInfrastructureError,
        OSError,
    ) as error:
        print(f"dense_index_failed error_type={type(error).__name__}", file=sys.stderr)
        return 1
    finally:
        try:
            await qdrant.close()
        finally:
            await sqlite.close()

    print(f"model_id={metadata.model_id}")
    print(f"model_revision={metadata.revision}")
    print(f"device={metadata.device}")
    print(f"dimension={metadata.dimension}")
    print(f"max_sequence_length={metadata.max_sequence_length}")
    print(f"source_id={result.source_id}")
    print(f"point_count={result.point_count}")
    print(f"batch_count={result.batch_count}")
    print("document_index_status=ready")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用真实 multilingual-e5-small 构建 Qdrant dense index。"
    )
    parser.add_argument(
        "--artifact-path",
        type=Path,
        default=Path(CHUNK_ARTIFACT_PATH),
        help="严格 Day 9 chunk artifact 路径。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """只在显式 CLI 调用时加载模型、连接 Qdrant 并构建索引。"""
    args = _build_parser().parse_args(argv)
    return asyncio.run(_run_build(Settings(), args.artifact_path))


if __name__ == "__main__":
    raise SystemExit(main())
