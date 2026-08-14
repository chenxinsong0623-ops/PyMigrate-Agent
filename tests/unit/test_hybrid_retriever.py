from collections.abc import Sequence

import pytest

from app.retrieval.bm25 import BM25SearchResult
from app.retrieval.dense import DenseRetrievalError, DenseSearchResult
from app.retrieval.hybrid import HybridRetriever


def _provenance(identifier: int) -> dict[str, object]:
    return {
        "chunk_id": f"sha256:{identifier:064x}",
        "heading_path": (f"Section {identifier}",),
        "text": f"text {identifier}",
        "content_sha256": f"{identifier:064x}",
        "source_id": "pydantic-v2-migration",
        "source_url": "https://example.test/migration.md",
        "git_ref": "v2.12.5",
        "resolved_commit_sha": "a" * 40,
        "source_path": "docs/migration.md",
        "source_snapshot_sha256": "b" * 64,
    }


class RecordingBM25:
    def __init__(
        self,
        results: Sequence[BM25SearchResult],
        error: Exception | None = None,
    ) -> None:
        self.results = tuple(results)
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int = 8) -> tuple[BM25SearchResult, ...]:
        self.calls.append((query, top_k))
        if self.error is not None:
            raise self.error
        return self.results


class RecordingDense:
    def __init__(
        self,
        results: Sequence[DenseSearchResult] = (),
        error: Exception | None = None,
    ) -> None:
        self.results = tuple(results)
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, top_k: int = 8) -> tuple[DenseSearchResult, ...]:
        self.calls.append((query, top_k))
        if self.error is not None:
            raise self.error
        return self.results


@pytest.mark.asyncio
async def test_hybrid_search_calls_both_top_eight_and_returns_top_three() -> None:
    bm25 = RecordingBM25(
        tuple(
            BM25SearchResult(rank=rank, score=9 - rank, **_provenance(rank))
            for rank in range(1, 9)
        )
    )
    dense = RecordingDense(
        tuple(
            DenseSearchResult(rank=rank, score=1 - rank / 10, **_provenance(rank))
            for rank in range(1, 9)
        )
    )
    retriever = HybridRetriever(bm25_retriever=bm25, dense_retriever=dense, rrf_k=60)

    response = await retriever.search("model_dump migration")

    assert bm25.calls == [("model_dump migration", 8)]
    assert dense.calls == [("model_dump migration", 8)]
    assert response.query == "model_dump migration"
    assert response.bm25_top_k == 8
    assert response.dense_top_k == 8
    assert response.final_top_k == 3
    assert len(response.results) == 8
    assert len(response.top_results) == 3


@pytest.mark.asyncio
async def test_hybrid_search_rejects_invalid_query_before_calling_components() -> None:
    bm25 = RecordingBM25(())
    dense = RecordingDense()
    retriever = HybridRetriever(bm25_retriever=bm25, dense_retriever=dense, rrf_k=60)

    with pytest.raises(ValueError):
        await retriever.search("query: model_dump")

    assert bm25.calls == []
    assert dense.calls == []


@pytest.mark.asyncio
async def test_hybrid_search_does_not_hide_dense_failure() -> None:
    bm25 = RecordingBM25(())
    dense = RecordingDense(error=DenseRetrievalError("qdrant failed"))
    retriever = HybridRetriever(bm25_retriever=bm25, dense_retriever=dense, rrf_k=60)

    with pytest.raises(DenseRetrievalError, match="qdrant failed"):
        await retriever.search("model_dump migration")

    assert bm25.calls == [("model_dump migration", 8)]
    assert dense.calls == [("model_dump migration", 8)]


@pytest.mark.asyncio
async def test_hybrid_search_does_not_hide_bm25_failure() -> None:
    bm25 = RecordingBM25((), error=RuntimeError("artifact failed"))
    dense = RecordingDense()
    retriever = HybridRetriever(bm25_retriever=bm25, dense_retriever=dense, rrf_k=60)

    with pytest.raises(RuntimeError, match="artifact failed"):
        await retriever.search("model_dump migration")

    assert bm25.calls == [("model_dump migration", 8)]
    assert dense.calls == []
