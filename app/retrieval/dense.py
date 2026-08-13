"""独立的 multilingual-e5-small + Qdrant dense retrieval 服务。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
from app.retrieval.qdrant import (
    QdrantInfrastructureError,
    QdrantScoredPoint,
    build_qdrant_backend,
)

DENSE_TOP_K_MAX = 8


class DenseRetrievalError(RuntimeError):
    """Dense query 结果与固定模型或 provenance 契约不一致。"""


class DenseQueryQdrant(Protocol):
    """DenseRetriever 所需的最小 Qdrant query 能力。"""

    async def query_points(
        self,
        vector: EmbeddingVector,
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        """返回按 score 排序的 dense points。"""
        ...


class DenseSearchResult(BaseModel):
    """供 Day 11 融合继续消费的严格 dense result。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int = Field(gt=0)
    score: float
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    heading_path: tuple[str, ...]
    text: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    git_ref: str = Field(min_length=1)
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str = Field(min_length=1)
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("score")
    @classmethod
    def validate_score(cls, score: float) -> float:
        if not math.isfinite(score):
            raise ValueError("dense score 必须是有限数值")
        return score


class DenseRetriever:
    """把原始 query 映射为 normalized vector 和 typed Qdrant results。"""

    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        qdrant_backend: DenseQueryQdrant,
        embedding_timeout_seconds: float,
    ) -> None:
        if (
            isinstance(embedding_timeout_seconds, bool)
            or not isinstance(embedding_timeout_seconds, (int, float))
            or embedding_timeout_seconds <= 0
        ):
            raise ValueError("embedding_timeout_seconds 必须大于 0")
        self._embedding_client = embedding_client
        self._qdrant = qdrant_backend
        self._embedding_timeout_seconds = float(embedding_timeout_seconds)

    async def search(
        self,
        query: str,
        top_k: int = DENSE_TOP_K_MAX,
    ) -> tuple[DenseSearchResult, ...]:
        """执行 query embedding 和 Qdrant top-k；0 命中返回空 tuple。"""
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k 必须是整数")
        if not 1 <= top_k <= DENSE_TOP_K_MAX:
            raise ValueError("top_k 必须位于 1..8")
        request = EmbeddingRequest(input_type="query", texts=(query,))
        embedding = await self._embedding_client.embed(
            request,
            timeout_seconds=self._embedding_timeout_seconds,
        )
        expected_model = f"{E5_MODEL_ID}@{E5_MODEL_REVISION}"
        if embedding.model != expected_model:
            raise DenseRetrievalError("query embedding model identity changed")
        points = await self._qdrant.query_points(embedding.vectors[0], top_k)

        results: list[DenseSearchResult] = []
        for rank, point in enumerate(points, start=1):
            payload = point.payload
            if (
                payload.embedding_model != E5_MODEL_ID
                or payload.embedding_revision != E5_MODEL_REVISION
            ):
                raise DenseRetrievalError("indexed embedding identity changed")
            results.append(
                DenseSearchResult(
                    rank=rank,
                    score=point.score,
                    chunk_id=payload.chunk_id,
                    heading_path=payload.heading_path,
                    text=payload.text,
                    content_sha256=payload.content_sha256,
                    source_id=payload.source_id,
                    source_url=payload.source_url,
                    git_ref=payload.git_ref,
                    resolved_commit_sha=payload.resolved_commit_sha,
                    source_path=payload.source_path,
                    source_snapshot_sha256=payload.source_snapshot_sha256,
                )
            )
        return tuple(results)


async def _run_queries(settings: Settings, queries: tuple[str, ...], top_k: int) -> int:
    qdrant = build_qdrant_backend(settings)
    embedding = E5Embedding(
        cache_folder=settings.embedding_cache_path,
        batch_size=settings.embedding_batch_size,
    )
    try:
        if not await qdrant.initialize():
            raise DenseRetrievalError("Qdrant initialization failed")
        metadata = await embedding.load(settings.embedding_timeout_seconds)
        retriever = DenseRetriever(
            embedding_client=embedding,
            qdrant_backend=qdrant,
            embedding_timeout_seconds=settings.embedding_timeout_seconds,
        )
        for query in queries:
            results = await retriever.search(query, top_k=top_k)
            print(
                json.dumps(
                    {
                        "query": query,
                        "model_id": metadata.model_id,
                        "model_revision": metadata.revision,
                        "top_k": top_k,
                        "results": [
                            result.model_dump(mode="json") for result in results
                        ],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    except (
        DenseRetrievalError,
        EmbeddingInfrastructureError,
        QdrantInfrastructureError,
        ValueError,
    ) as error:
        print(f"dense_query_failed error_type={type(error).__name__}", file=sys.stderr)
        return 1
    finally:
        await qdrant.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用真实 multilingual-e5-small 查询 Qdrant dense index。"
    )
    parser.add_argument(
        "queries", nargs="+", help="一个或多个未加 prefix 的原始 query。"
    )
    parser.add_argument("--top-k", type=int, default=DENSE_TOP_K_MAX)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """只在显式 CLI 调用时加载模型并执行 dense queries。"""
    args = _build_parser().parse_args(argv)
    return asyncio.run(_run_queries(Settings(), tuple(args.queries), args.top_k))


if __name__ == "__main__":
    raise SystemExit(main())
