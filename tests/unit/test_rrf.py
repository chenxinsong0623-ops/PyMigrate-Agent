import math

import pytest
from pydantic import ValidationError

from app.retrieval.bm25 import BM25SearchResult
from app.retrieval.dense import DenseSearchResult
from app.retrieval.hybrid import HybridFusionContractError, reciprocal_rank_fusion


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


def _bm25(identifier: int, rank: int, score: float) -> BM25SearchResult:
    return BM25SearchResult(rank=rank, score=score, **_provenance(identifier))


def _dense(identifier: int, rank: int, score: float) -> DenseSearchResult:
    return DenseSearchResult(rank=rank, score=score, **_provenance(identifier))


def test_rrf_deduplicates_chunk_id_and_keeps_component_evidence() -> None:
    response = reciprocal_rank_fusion(
        "model_dump migration",
        (_bm25(1, 1, 4.2), _bm25(2, 2, 2.1)),
        (_dense(2, 1, 0.92), _dense(3, 2, 0.81)),
        rrf_k=60,
    )

    assert len(response.results) == 3
    assert len(response.top_results) == 3
    overlap = next(item for item in response.results if item.chunk_id.endswith("2"))
    assert overlap.bm25_rank == 2
    assert overlap.dense_rank == 1
    assert overlap.bm25_score == 2.1
    assert overlap.dense_score == 0.92
    assert math.isclose(overlap.rrf_score, 1 / 62 + 1 / 61)
    assert response.results[0] == overlap


def test_rrf_retains_full_union_but_returns_only_final_top_three() -> None:
    response = reciprocal_rank_fusion(
        "migration",
        tuple(
            _bm25(identifier, identifier, 9 - identifier) for identifier in range(1, 9)
        ),
        tuple(
            _dense(identifier, identifier - 8, 18 - identifier)
            for identifier in range(9, 17)
        ),
        rrf_k=60,
    )

    assert len(response.results) == 16
    assert [item.rank for item in response.results] == list(range(1, 17))
    assert len(response.top_results) == 3
    assert response.top_results == response.results[:3]


def test_rrf_is_stable_when_component_input_order_changes() -> None:
    bm25 = (_bm25(1, 1, 2.0), _bm25(2, 2, 1.0))
    dense = (_dense(3, 1, 0.9), _dense(4, 2, 0.8))

    first = reciprocal_rank_fusion("migration", bm25, dense, rrf_k=60)
    second = reciprocal_rank_fusion(
        "migration", tuple(reversed(bm25)), tuple(reversed(dense)), rrf_k=60
    )

    assert first == second


def test_rrf_k_is_configurable_and_recorded() -> None:
    response = reciprocal_rank_fusion("migration", (_bm25(1, 1, 1.0),), (), rrf_k=10)

    assert response.rrf_k == 10
    assert math.isclose(response.results[0].rrf_score, 1 / 11)


def test_rrf_empty_components_return_empty_rankings() -> None:
    response = reciprocal_rank_fusion("migration", (), (), rrf_k=60)

    assert response.results == ()
    assert response.top_results == ()


@pytest.mark.parametrize("component", ["bm25", "dense"])
def test_rrf_accepts_one_empty_component(component: str) -> None:
    bm25 = () if component == "bm25" else (_bm25(1, 1, 1.0),)
    dense = () if component == "dense" else (_dense(2, 1, 0.8),)

    response = reciprocal_rank_fusion("migration", bm25, dense, rrf_k=60)

    assert len(response.results) == 1
    assert response.results[0].bm25_rank == (None if component == "bm25" else 1)
    assert response.results[0].dense_rank == (None if component == "dense" else 1)


def test_rrf_rejects_duplicate_component_chunk_ids() -> None:
    with pytest.raises(HybridFusionContractError, match="duplicate"):
        reciprocal_rank_fusion(
            "migration", (_bm25(1, 1, 2.0), _bm25(1, 2, 1.0)), (), rrf_k=60
        )


def test_rrf_rejects_non_contiguous_component_ranks() -> None:
    with pytest.raises(HybridFusionContractError, match="continuous"):
        reciprocal_rank_fusion("migration", (_bm25(1, 2, 1.0),), (), rrf_k=60)


def test_rrf_rejects_provenance_mismatch_for_same_chunk_id() -> None:
    dense = _dense(1, 1, 0.9).model_copy(update={"text": "changed text"})

    with pytest.raises(HybridFusionContractError, match="provenance"):
        reciprocal_rank_fusion("migration", (_bm25(1, 1, 1.0),), (dense,), rrf_k=60)


@pytest.mark.parametrize("component", ["bm25", "dense"])
def test_component_schema_rejects_non_finite_raw_score(component: str) -> None:
    constructor = BM25SearchResult if component == "bm25" else DenseSearchResult

    with pytest.raises(ValidationError):
        constructor(rank=1, score=float("nan"), **_provenance(1))


def test_hybrid_schema_forbids_day12_or_reranker_fields() -> None:
    response = reciprocal_rank_fusion("migration", (_bm25(1, 1, 1.0),), (), rrf_k=60)

    fields = type(response.results[0]).model_fields
    assert "reranker_score" not in fields
    assert "recall" not in fields
    assert "mrr" not in fields


@pytest.mark.parametrize("rrf_k", [0, -1, True, 1.5])
def test_rrf_rejects_invalid_k(rrf_k: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        reciprocal_rank_fusion(
            "migration",
            (),
            (),
            rrf_k=rrf_k,  # type: ignore[arg-type]
        )
