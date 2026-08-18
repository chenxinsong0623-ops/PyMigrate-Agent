from __future__ import annotations

import math

import pytest

from app.evaluation.retrieval import (
    RankedReference,
    RetrievalQuestionScore,
    aggregate_question_scores,
    score_heading_ranking,
)

GOLD = ("Migration guide", "Changes to validators")


def _ranking(*headings: tuple[str, ...]) -> tuple[RankedReference, ...]:
    return tuple(
        RankedReference(
            rank=rank,
            chunk_id=f"sha256:{rank:064x}",
            heading_path=heading,
        )
        for rank, heading in enumerate(headings, start=1)
    )


@pytest.mark.parametrize(
    ("rank", "recall_at_1", "recall_at_3", "reciprocal_rank"),
    [
        (1, 1, 1, 1.0),
        (2, 0, 1, 0.5),
        (3, 0, 1, 1 / 3),
        (5, 0, 0, 0.2),
        (6, 0, 0, 0.0),
    ],
)
def test_score_heading_ranking_at_exact_boundaries(
    rank: int,
    recall_at_1: int,
    recall_at_3: int,
    reciprocal_rank: float,
) -> None:
    headings = [("Other", str(index)) for index in range(1, 7)]
    headings[rank - 1] = GOLD

    score = score_heading_ranking(GOLD, _ranking(*headings))

    assert score.first_gold_rank == rank
    assert score.recall_at_1 == recall_at_1
    assert score.recall_at_3 == recall_at_3
    assert math.isclose(score.reciprocal_rank_at_5, reciprocal_rank)


@pytest.mark.parametrize("ranking", [(), _ranking(("Other",))])
def test_score_heading_ranking_handles_empty_or_no_hit(
    ranking: tuple[RankedReference, ...],
) -> None:
    score = score_heading_ranking(GOLD, ranking)

    assert score.first_gold_rank is None
    assert score.recall_at_1 == 0
    assert score.recall_at_3 == 0
    assert score.reciprocal_rank_at_5 == 0.0


def test_score_heading_ranking_rejects_missing_gold() -> None:
    with pytest.raises(ValueError, match="gold"):
        score_heading_ranking((), ())


def test_duplicate_gold_heading_uses_first_relevant_rank() -> None:
    score = score_heading_ranking(
        GOLD,
        _ranking(("Other",), GOLD, GOLD),
    )

    assert score.first_gold_rank == 2
    assert score.reciprocal_rank_at_5 == 0.5


def test_metric_rejects_non_contiguous_or_misordered_ranks() -> None:
    invalid = RankedReference(
        rank=2,
        chunk_id=f"sha256:{1:064x}",
        heading_path=GOLD,
    )

    with pytest.raises(ValueError, match="continuous"):
        score_heading_ranking(GOLD, (invalid,))


def test_aggregate_is_arithmetic_mean_and_requires_scores() -> None:
    scores = (
        RetrievalQuestionScore(
            first_gold_rank=1,
            recall_at_1=1,
            recall_at_3=1,
            reciprocal_rank_at_5=1.0,
            returned_count=3,
        ),
        RetrievalQuestionScore(
            first_gold_rank=None,
            recall_at_1=0,
            recall_at_3=0,
            reciprocal_rank_at_5=0.0,
            returned_count=0,
        ),
    )

    aggregate = aggregate_question_scores(scores)

    assert aggregate.question_count == 2
    assert aggregate.recall_at_1 == 0.5
    assert aggregate.recall_at_3 == 0.5
    assert aggregate.mrr_at_5 == 0.5
    with pytest.raises(ValueError, match="scores"):
        aggregate_question_scores(())


def test_metric_result_is_deterministic_for_same_ordered_ranking() -> None:
    ranking = _ranking(("Other",), GOLD, ("Another",))

    assert score_heading_ranking(GOLD, ranking) == score_heading_ranking(GOLD, ranking)


def test_same_heading_with_different_chunk_ids_remains_one_relevance_target() -> None:
    ranking = _ranking(GOLD, GOLD, ("Other",))

    score = score_heading_ranking(GOLD, ranking)

    assert score.first_gold_rank == 1
    assert score.recall_at_1 == 1
    assert score.returned_count == 3


def test_preamble_candidate_with_empty_heading_is_a_valid_non_hit() -> None:
    ranking = _ranking((), GOLD)

    score = score_heading_ranking(GOLD, ranking)

    assert score.first_gold_rank == 2
    assert score.recall_at_1 == 0
    assert score.reciprocal_rank_at_5 == 0.5
