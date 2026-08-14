"""编排 BM25 top-8、Dense top-8 与确定性 Reciprocal Rank Fusion。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import Settings
from app.core.embedding import E5Embedding, EmbeddingInfrastructureError
from app.ingestion.markdown_chunker import CHUNK_ARTIFACT_PATH
from app.retrieval.bm25 import (
    BM25ArtifactError,
    BM25Retriever,
    BM25SearchResult,
    tokenize_for_bm25,
    validate_raw_query,
)
from app.retrieval.dense import DenseRetrievalError, DenseRetriever, DenseSearchResult
from app.retrieval.qdrant import QdrantInfrastructureError, build_qdrant_backend

HYBRID_CANDIDATE_TOP_K = 8
HYBRID_FINAL_TOP_K = 3

_PROVENANCE_FIELDS = (
    "chunk_id",
    "heading_path",
    "text",
    "content_sha256",
    "source_id",
    "source_url",
    "git_ref",
    "resolved_commit_sha",
    "source_path",
    "source_snapshot_sha256",
)


class HybridFusionContractError(RuntimeError):
    """组件结果无法满足 RRF 的排名、去重或 provenance 契约。"""


class BM25SearchProtocol(Protocol):
    def search(
        self, query: str, top_k: int = HYBRID_CANDIDATE_TOP_K
    ) -> tuple[BM25SearchResult, ...]: ...


class DenseSearchProtocol(Protocol):
    async def search(
        self, query: str, top_k: int = HYBRID_CANDIDATE_TOP_K
    ) -> tuple[DenseSearchResult, ...]: ...


class HybridSearchResult(BaseModel):
    """保留融合排名、两路排名/原始分数与完整引用 provenance。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int = Field(gt=0)
    rrf_score: float = Field(gt=0)
    bm25_rank: int | None = Field(default=None, gt=0, le=HYBRID_CANDIDATE_TOP_K)
    dense_rank: int | None = Field(default=None, gt=0, le=HYBRID_CANDIDATE_TOP_K)
    bm25_score: float | None = None
    dense_score: float | None = None
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

    @model_validator(mode="after")
    def validate_component_evidence(self) -> Self:
        if not math.isfinite(self.rrf_score):
            raise ValueError("RRF score 必须是有限数值")
        for name, rank, score in (
            ("BM25", self.bm25_rank, self.bm25_score),
            ("Dense", self.dense_rank, self.dense_score),
        ):
            if (rank is None) != (score is None):
                raise ValueError(f"{name} rank 与 score 必须同时存在或同时缺失")
            if score is not None and not math.isfinite(score):
                raise ValueError(f"{name} score 必须是有限数值")
        if self.bm25_rank is None and self.dense_rank is None:
            raise ValueError("融合结果必须来自至少一个组件")
        return self


class HybridSearchResponse(BaseModel):
    """一个 query 的完整融合证据与最终 top-3。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1)
    bm25_top_k: int = Field(default=HYBRID_CANDIDATE_TOP_K, frozen=True)
    dense_top_k: int = Field(default=HYBRID_CANDIDATE_TOP_K, frozen=True)
    final_top_k: int = Field(default=HYBRID_FINAL_TOP_K, frozen=True)
    rrf_k: int = Field(gt=0, le=1000)
    results: tuple[HybridSearchResult, ...] = Field(max_length=16)
    top_results: tuple[HybridSearchResult, ...] = Field(max_length=HYBRID_FINAL_TOP_K)

    @model_validator(mode="after")
    def validate_ranked_views(self) -> Self:
        expected_ranks = list(range(1, len(self.results) + 1))
        if [result.rank for result in self.results] != expected_ranks:
            raise ValueError("融合 results rank 必须连续并按排名排列")
        if self.top_results != self.results[:HYBRID_FINAL_TOP_K]:
            raise ValueError("top_results 必须是 results 的前 3 项")
        if self.bm25_top_k != HYBRID_CANDIDATE_TOP_K:
            raise ValueError("bm25_top_k 必须固定为 8")
        if self.dense_top_k != HYBRID_CANDIDATE_TOP_K:
            raise ValueError("dense_top_k 必须固定为 8")
        if self.final_top_k != HYBRID_FINAL_TOP_K:
            raise ValueError("final_top_k 必须固定为 3")
        return self


@dataclass(slots=True)
class _FusionCandidate:
    provenance: dict[str, object]
    bm25_rank: int | None = None
    dense_rank: int | None = None
    bm25_score: float | None = None
    dense_score: float | None = None
    rrf_score: float = 0.0


def _provenance(result: BM25SearchResult | DenseSearchResult) -> dict[str, object]:
    return {field: getattr(result, field) for field in _PROVENANCE_FIELDS}


def _validate_component(
    name: str,
    results: Sequence[BM25SearchResult] | Sequence[DenseSearchResult],
) -> None:
    if len(results) > HYBRID_CANDIDATE_TOP_K:
        raise HybridFusionContractError(f"{name} returned more than top-8")
    chunk_ids = [result.chunk_id for result in results]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise HybridFusionContractError(f"{name} contains duplicate chunk_id")
    ranks = sorted(result.rank for result in results)
    if ranks != list(range(1, len(results) + 1)):
        raise HybridFusionContractError(f"{name} ranks must be continuous from 1")


def reciprocal_rank_fusion(
    query: str,
    bm25_results: Sequence[BM25SearchResult],
    dense_results: Sequence[DenseSearchResult],
    *,
    rrf_k: int,
) -> HybridSearchResponse:
    """按 chunk_id 去重并计算 ``sum(1 / (rrf_k + component_rank))``。"""
    normalized_query = validate_raw_query(query)
    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int):
        raise TypeError("rrf_k 必须是整数")
    if not 1 <= rrf_k <= 1000:
        raise ValueError("rrf_k 必须位于 1..1000")
    _validate_component("BM25", bm25_results)
    _validate_component("Dense", dense_results)

    candidates: dict[str, _FusionCandidate] = {}
    for component, results in (("bm25", bm25_results), ("dense", dense_results)):
        for result in sorted(results, key=lambda item: item.rank):
            provenance = _provenance(result)
            candidate = candidates.get(result.chunk_id)
            if candidate is None:
                candidate = _FusionCandidate(provenance=provenance)
                candidates[result.chunk_id] = candidate
            elif candidate.provenance != provenance:
                raise HybridFusionContractError(
                    "same chunk_id has inconsistent provenance across components"
                )
            if component == "bm25":
                candidate.bm25_rank = result.rank
                candidate.bm25_score = result.score
            else:
                candidate.dense_rank = result.rank
                candidate.dense_score = result.score
            candidate.rrf_score += 1 / (rrf_k + result.rank)

    missing_rank = HYBRID_CANDIDATE_TOP_K + 1

    def ranking_key(item: tuple[str, _FusionCandidate]) -> tuple[float, int, int, str]:
        chunk_id, candidate = item
        ranks = tuple(
            rank
            for rank in (candidate.bm25_rank, candidate.dense_rank)
            if rank is not None
        )
        best_rank = min(ranks)
        total_rank = (candidate.bm25_rank or missing_rank) + (
            candidate.dense_rank or missing_rank
        )
        return (-candidate.rrf_score, best_rank, total_rank, chunk_id)

    ranked_candidates = sorted(candidates.items(), key=ranking_key)
    results = tuple(
        HybridSearchResult(
            rank=rank,
            rrf_score=candidate.rrf_score,
            bm25_rank=candidate.bm25_rank,
            dense_rank=candidate.dense_rank,
            bm25_score=candidate.bm25_score,
            dense_score=candidate.dense_score,
            **candidate.provenance,
        )
        for rank, (_chunk_id, candidate) in enumerate(ranked_candidates, start=1)
    )
    return HybridSearchResponse(
        query=normalized_query,
        rrf_k=rrf_k,
        results=results,
        top_results=results[:HYBRID_FINAL_TOP_K],
    )


class HybridRetriever:
    """组合两个可独立替换的检索接口；任一路失败时显式向调用方传播。"""

    def __init__(
        self,
        *,
        bm25_retriever: BM25SearchProtocol,
        dense_retriever: DenseSearchProtocol,
        rrf_k: int,
    ) -> None:
        if isinstance(rrf_k, bool) or not isinstance(rrf_k, int):
            raise TypeError("rrf_k 必须是整数")
        if not 1 <= rrf_k <= 1000:
            raise ValueError("rrf_k 必须位于 1..1000")
        self._bm25 = bm25_retriever
        self._dense = dense_retriever
        self._rrf_k = rrf_k

    async def search(self, query: str) -> HybridSearchResponse:
        normalized_query = validate_raw_query(query)
        if not tokenize_for_bm25(normalized_query):
            raise ValueError("query 必须至少包含一个可检索 token")
        bm25_results = self._bm25.search(normalized_query, top_k=HYBRID_CANDIDATE_TOP_K)
        dense_results = await self._dense.search(
            normalized_query, top_k=HYBRID_CANDIDATE_TOP_K
        )
        return reciprocal_rank_fusion(
            normalized_query,
            bm25_results,
            dense_results,
            rrf_k=self._rrf_k,
        )


async def _run_queries(
    settings: Settings,
    queries: tuple[str, ...],
    artifact_path: Path,
    rrf_k: int,
) -> int:
    qdrant = build_qdrant_backend(settings)
    embedding = E5Embedding(
        cache_folder=settings.embedding_cache_path,
        batch_size=settings.embedding_batch_size,
    )
    try:
        bm25 = BM25Retriever.from_artifact(artifact_path)
        if not await qdrant.initialize():
            raise DenseRetrievalError("Qdrant initialization failed")
        await embedding.load(settings.embedding_timeout_seconds)
        dense = DenseRetriever(
            embedding_client=embedding,
            qdrant_backend=qdrant,
            embedding_timeout_seconds=settings.embedding_timeout_seconds,
        )
        retriever = HybridRetriever(
            bm25_retriever=bm25,
            dense_retriever=dense,
            rrf_k=rrf_k,
        )
        for query in queries:
            response = await retriever.search(query)
            print(
                json.dumps(
                    response.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    except (
        BM25ArtifactError,
        DenseRetrievalError,
        EmbeddingInfrastructureError,
        HybridFusionContractError,
        QdrantInfrastructureError,
        TypeError,
        ValueError,
    ) as error:
        print(f"hybrid_query_failed error_type={type(error).__name__}", file=sys.stderr)
        return 1
    finally:
        await qdrant.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="执行 BM25 top-8 + Dense top-8 + RRF + final top-3。"
    )
    parser.add_argument(
        "queries", nargs="+", help="一个或多个未加 prefix 的原始 query。"
    )
    parser.add_argument("--artifact-path", type=Path, default=Path(CHUNK_ARTIFACT_PATH))
    parser.add_argument("--rrf-k", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """只在显式 CLI 调用时加载真实 E5、Qdrant 与本地 BM25。"""
    args = _build_parser().parse_args(argv)
    settings = Settings()
    rrf_k = settings.rrf_k if args.rrf_k is None else args.rrf_k
    return asyncio.run(
        _run_queries(settings, tuple(args.queries), args.artifact_path, rrf_k)
    )


if __name__ == "__main__":
    raise SystemExit(main())
