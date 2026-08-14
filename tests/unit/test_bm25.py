import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    MarkdownChunk,
    calculate_text_sha256,
)
from app.retrieval.bm25 import (
    BM25_TOP_K_MAX,
    BM25Retriever,
    BM25SearchResult,
    tokenize_for_bm25,
)


def _chunk(index: int, text: str) -> MarkdownChunk:
    content_sha256 = calculate_text_sha256(text)
    return MarkdownChunk(
        chunk_id=f"sha256:{index:064x}",
        text=text,
        heading_path=(f"Section {index}",),
        content_sha256=content_sha256,
        char_length=len(text),
        source_id="pydantic-v2-migration",
        source_url="https://example.test/migration.md",
        git_ref="v2.12.5",
        resolved_commit_sha="a" * 40,
        source_path="docs/migration.md",
        source_snapshot_sha256="b" * 64,
        source_start_char=index * 1000,
        source_end_char=index * 1000 + len(text),
        continuation_index=0,
        overlap_chars=0,
        identity_occurrence=0,
    )


def test_tokenizer_preserves_python_api_identity_and_components() -> None:
    assert tokenize_for_bm25(
        "BaseModel.dict() model_dump root_validator "
        "allow_population_by_field_name pydantic-settings"
    ) == (
        "basemodel.dict",
        "basemodel",
        "dict",
        "model_dump",
        "model",
        "dump",
        "root_validator",
        "root",
        "validator",
        "allow_population_by_field_name",
        "allow",
        "population",
        "by",
        "field",
        "name",
        "pydantic-settings",
        "pydantic",
        "settings",
    )


def test_tokenizer_normalizes_case_and_supports_unicode_words() -> None:
    assert tokenize_for_bm25("CAFÉ 模型 BaseSettings") == (
        "café",
        "模型",
        "basesettings",
    )


def test_bm25_ranks_lexical_hits_and_preserves_provenance() -> None:
    retriever = BM25Retriever(
        (
            _chunk(1, "Use model_dump to export a model in Pydantic V2."),
            _chunk(2, "BaseModel.dict is deprecated; migrate to model_dump."),
            _chunk(3, "Unrelated serialization notes."),
        )
    )

    results = retriever.search("BaseModel.dict migration", top_k=BM25_TOP_K_MAX)

    assert [result.rank for result in results] == [1]
    assert results[0].chunk_id == f"sha256:{2:064x}"
    assert results[0].score > 0
    assert results[0].heading_path == ("Section 2",)
    assert results[0].source_url == "https://example.test/migration.md"
    assert results[0].resolved_commit_sha == "a" * 40
    assert results[0].source_snapshot_sha256 == "b" * 64


def test_bm25_zero_hit_returns_empty_tuple() -> None:
    retriever = BM25Retriever((_chunk(1, "model_dump migration"),))

    assert retriever.search("completely_absent_api", top_k=8) == ()


def test_bm25_ties_follow_document_order_deterministically() -> None:
    retriever = BM25Retriever(
        (
            _chunk(2, "root_validator"),
            _chunk(1, "root_validator"),
        )
    )

    first = retriever.search("root_validator", top_k=8)
    second = retriever.search("root_validator", top_k=8)

    assert [item.chunk_id for item in first] == [
        f"sha256:{2:064x}",
        f"sha256:{1:064x}",
    ]
    assert first == second


@pytest.mark.parametrize("top_k", [0, 9, True, 1.5])
def test_bm25_rejects_invalid_top_k(top_k: object) -> None:
    retriever = BM25Retriever((_chunk(1, "model_dump"),))

    with pytest.raises((TypeError, ValueError)):
        retriever.search("model_dump", top_k=top_k)  # type: ignore[arg-type]


@pytest.mark.parametrize("query", ["", "   ", "query: model_dump", "!!!"])
def test_bm25_rejects_invalid_raw_query(query: str) -> None:
    retriever = BM25Retriever((_chunk(1, "model_dump"),))

    with pytest.raises(ValueError):
        retriever.search(query)


def test_bm25_from_artifact_rejects_invalid_artifact(tmp_path: Path) -> None:
    invalid_artifact = tmp_path / "chunks.json"
    invalid_artifact.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing or invalid"):
        BM25Retriever.from_artifact(invalid_artifact)


def test_bm25_loads_formal_day9_artifact_and_limits_real_corpus_top_eight() -> None:
    retriever = BM25Retriever.from_artifact(Path(CHUNK_ARTIFACT_PATH))

    results = retriever.search("model_dump migration", top_k=8)

    assert 1 <= len(results) <= 8
    assert [result.rank for result in results] == list(range(1, len(results) + 1))
    assert all(result.score > 0 for result in results)
    assert results[0].heading_path[-1] == "Changes to `pydantic.BaseModel`"


@pytest.mark.parametrize("score", [0, -1, float("nan"), float("inf")])
def test_bm25_result_rejects_non_positive_or_non_finite_score(score: float) -> None:
    with pytest.raises(ValidationError):
        BM25SearchResult(
            rank=1,
            score=score,
            **{
                "chunk_id": f"sha256:{1:064x}",
                "heading_path": ("Section",),
                "text": "text",
                "content_sha256": f"{1:064x}",
                "source_id": "pydantic-v2-migration",
                "source_url": "https://example.test/migration.md",
                "git_ref": "v2.12.5",
                "resolved_commit_sha": "a" * 40,
                "source_path": "docs/migration.md",
                "source_snapshot_sha256": "b" * 64,
            },
        )
