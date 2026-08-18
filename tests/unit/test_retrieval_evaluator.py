from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.evaluation.retrieval import (
    DEV_QUESTIONS_PATH,
    DevRetrievalEvaluator,
    EvaluationContractError,
    RetrievalSystem,
    load_question_artifact,
    render_query,
)
from app.retrieval.bm25 import BM25SearchResult
from app.retrieval.dense import DenseSearchResult
from app.retrieval.hybrid import (
    HYBRID_FINAL_TOP_K,
    HybridSearchResponse,
    HybridSearchResult,
)


def _provenance(identifier: int, heading: tuple[str, ...]) -> dict[str, object]:
    return {
        "chunk_id": f"sha256:{identifier:064x}",
        "heading_path": heading,
        "text": f"text {identifier}",
        "content_sha256": f"{identifier:064x}",
        "source_id": "pydantic-v2-migration",
        "source_url": "https://example.test/migration.md",
        "git_ref": "v2.13.4",
        "resolved_commit_sha": "a" * 40,
        "source_path": "docs/migration.md",
        "source_snapshot_sha256": "b" * 64,
    }


class RecordingBM25:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int = 8) -> tuple[BM25SearchResult, ...]:
        self.calls.append((query, top_k))
        if self.error is not None:
            raise self.error
        return (
            BM25SearchResult(
                rank=1,
                score=1.0,
                **_provenance(1, ("Other",)),
            ),
        )


class RecordingDense:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, top_k: int = 8) -> tuple[DenseSearchResult, ...]:
        self.calls.append((query, top_k))
        if self.error is not None:
            raise self.error
        return (
            DenseSearchResult(
                rank=1,
                score=0.9,
                **_provenance(2, ("Other",)),
            ),
        )


class RecordingHybrid:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    async def search(self, query: str) -> HybridSearchResponse:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        results = tuple(
            HybridSearchResult(
                rank=rank,
                rrf_score=1 / (60 + rank),
                bm25_rank=rank if rank <= 8 else None,
                bm25_score=float(9 - rank) if rank <= 8 else None,
                dense_rank=None,
                dense_score=None,
                **_provenance(rank + 10, ("Other", str(rank))),
            )
            for rank in range(1, 6)
        )
        return HybridSearchResponse(
            query=query,
            rrf_k=60,
            results=results,
            top_results=results[:HYBRID_FINAL_TOP_K],
        )


@pytest.mark.asyncio
async def test_three_systems_receive_the_same_query_once_per_question() -> None:
    dev = load_question_artifact(DEV_QUESTIONS_PATH)
    bm25 = RecordingBM25()
    dense = RecordingDense()
    hybrid = RecordingHybrid()
    evaluator = DevRetrievalEvaluator(bm25=bm25, dense=dense, hybrid=hybrid)

    run = await evaluator.evaluate(dev)

    expected_queries = [render_query(question) for question in dev.questions]
    assert bm25.calls == [(query, 8) for query in expected_queries]
    assert dense.calls == [(query, 8) for query in expected_queries]
    assert hybrid.calls == expected_queries
    assert [aggregate.system for aggregate in run.aggregates] == list(RetrievalSystem)
    assert len(run.details) == 12 * 3


@pytest.mark.asyncio
async def test_hybrid_evaluation_uses_full_results_beyond_top_three() -> None:
    dev = load_question_artifact(DEV_QUESTIONS_PATH)
    gold = dev.questions[0].gold_heading_path

    class GoldAtFiveHybrid(RecordingHybrid):
        async def search(self, query: str) -> HybridSearchResponse:
            response = await super().search(query)
            if len(self.calls) == 1:
                fifth = response.results[4].model_copy(update={"heading_path": gold})
                results = (*response.results[:4], fifth)
                return response.model_copy(
                    update={
                        "results": results,
                        "top_results": results[:HYBRID_FINAL_TOP_K],
                    }
                )
            return response

    evaluator = DevRetrievalEvaluator(
        bm25=RecordingBM25(),
        dense=RecordingDense(),
        hybrid=GoldAtFiveHybrid(),
    )

    run = await evaluator.evaluate(dev)
    detail = next(
        item
        for item in run.details
        if item.question_id == dev.questions[0].question_id
        and item.system is RetrievalSystem.HYBRID
    )

    assert detail.first_gold_rank == 5
    assert detail.reciprocal_rank_at_5 == 0.2


@pytest.mark.asyncio
async def test_component_failure_propagates_and_publishes_no_partial_run() -> None:
    dev = load_question_artifact(DEV_QUESTIONS_PATH)
    error = RuntimeError("qdrant failed")
    evaluator = DevRetrievalEvaluator(
        bm25=RecordingBM25(),
        dense=RecordingDense(error=error),
        hybrid=RecordingHybrid(),
    )

    with pytest.raises(RuntimeError, match="qdrant failed"):
        await evaluator.evaluate(dev)


@pytest.mark.asyncio
async def test_evaluator_rejects_locked_artifact_before_any_retriever_call() -> None:
    locked = load_question_artifact("data/evaluation/retrieval/locked_candidates.json")
    bm25 = RecordingBM25()
    dense = RecordingDense()
    hybrid = RecordingHybrid()
    evaluator = DevRetrievalEvaluator(bm25=bm25, dense=dense, hybrid=hybrid)

    with pytest.raises(EvaluationContractError, match="dev"):
        await evaluator.evaluate(locked)

    assert bm25.calls == []
    assert dense.calls == []
    assert hybrid.calls == []


@pytest.mark.asyncio
async def test_evaluator_rejects_hybrid_query_mismatch() -> None:
    dev = load_question_artifact(DEV_QUESTIONS_PATH)

    class MismatchedHybrid(RecordingHybrid):
        async def search(self, query: str) -> HybridSearchResponse:
            response = await super().search(query)
            return response.model_copy(update={"query": "different"})

    evaluator = DevRetrievalEvaluator(
        bm25=RecordingBM25(),
        dense=RecordingDense(),
        hybrid=MismatchedHybrid(),
    )

    with pytest.raises(EvaluationContractError, match="query"):
        await evaluator.evaluate(dev)


@pytest.mark.asyncio
async def test_normal_empty_results_are_scored_as_misses_not_failures() -> None:
    dev = load_question_artifact(DEV_QUESTIONS_PATH)

    class EmptyBM25(RecordingBM25):
        def search(self, query: str, top_k: int = 8) -> tuple[BM25SearchResult, ...]:
            self.calls.append((query, top_k))
            return ()

    class EmptyDense(RecordingDense):
        async def search(
            self, query: str, top_k: int = 8
        ) -> tuple[DenseSearchResult, ...]:
            self.calls.append((query, top_k))
            return ()

    class EmptyHybrid(RecordingHybrid):
        async def search(self, query: str) -> HybridSearchResponse:
            self.calls.append(query)
            return HybridSearchResponse(
                query=query,
                rrf_k=60,
                results=(),
                top_results=(),
            )

    run = await DevRetrievalEvaluator(
        bm25=EmptyBM25(),
        dense=EmptyDense(),
        hybrid=EmptyHybrid(),
    ).evaluate(dev)

    assert all(detail.first_gold_rank is None for detail in run.details)
    assert all(aggregate.recall_at_3 == 0 for aggregate in run.aggregates)


@pytest.mark.asyncio
async def test_details_keep_question_then_system_deterministic_order() -> None:
    dev = load_question_artifact(DEV_QUESTIONS_PATH)
    run = await DevRetrievalEvaluator(
        bm25=RecordingBM25(),
        dense=RecordingDense(),
        hybrid=RecordingHybrid(),
    ).evaluate(dev)

    assert [detail.system for detail in run.details[:3]] == list(RetrievalSystem)
    assert {detail.question_id for detail in run.details[:3]} == {
        dev.questions[0].question_id
    }


def test_cli_parser_has_no_split_or_locked_question_argument() -> None:
    from app.evaluation.retrieval_dev import build_parser

    destinations = {action.dest for action in build_parser()._actions}
    option_strings: Sequence[str] = tuple(
        option for action in build_parser()._actions for option in action.option_strings
    )

    assert "split" not in destinations
    assert "questions_path" not in destinations
    assert all("locked" not in option for option in option_strings)
