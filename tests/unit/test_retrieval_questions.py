from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.retrieval import (
    DEV_QUESTIONS_PATH,
    LOCKED_CANDIDATES_PATH,
    RETRIEVAL_QUESTION_SCHEMA_VERSION,
    RetrievalBenchmarkContaminationError,
    RetrievalQuestion,
    RetrievalQuestionArtifact,
    RetrievalRuleCategory,
    load_question_artifact,
    load_retrieval_benchmark,
    normalize_question_text,
    render_query,
    serialize_question_artifact,
    validate_retrieval_benchmark,
)


def _question(**updates: object) -> RetrievalQuestion:
    payload: dict[str, object] = {
        "schema_version": RETRIEVAL_QUESTION_SCHEMA_VERSION,
        "question_id": "dev-methods-export",
        "split": "dev",
        "rule_category": "base_model_methods",
        "old_api": "BaseModel.dict()",
        "ast_context": "result = user.dict()",
        "user_question": "升级到 Pydantic V2 时如何替换这个模型导出调用？",
        "gold_heading_path": (
            "Migration guide",
            "Changes to `pydantic.BaseModel`",
        ),
        "template_family": "dev_upgrade_review",
    }
    payload.update(updates)
    return RetrievalQuestion.model_validate(payload)


def test_question_schema_is_frozen_strict_and_accepts_empty_ast_context() -> None:
    question = _question(ast_context="")

    assert question.schema_version == 1
    assert question.ast_context == ""
    assert question.rule_category is RetrievalRuleCategory.BASE_MODEL_METHODS
    with pytest.raises(ValidationError):
        question.user_question = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        RetrievalQuestion.model_validate(
            {**question.model_dump(mode="json"), "unexpected": True}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("split", "test"),
        ("question_id", "locked-wrong-prefix"),
        ("user_question", "   "),
        ("old_api", ""),
        ("gold_heading_path", ()),
        ("gold_heading_path", ("Migration guide", " ")),
    ],
)
def test_question_schema_rejects_invalid_contract(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _question(**{field: value})


def test_formal_benchmark_has_twelve_dev_twenty_locked_and_four_per_rule() -> None:
    benchmark = load_retrieval_benchmark()

    assert len(benchmark.dev.questions) == 12
    assert len(benchmark.locked_candidates.questions) == 20
    assert benchmark.dev.split == "dev"
    assert benchmark.locked_candidates.split == "locked_candidate"
    counts = Counter(
        question.rule_category
        for artifact in (benchmark.dev, benchmark.locked_candidates)
        for question in artifact.questions
    )
    assert counts == Counter({category: 4 for category in RetrievalRuleCategory})


def test_question_artifacts_are_physically_separate_and_deterministic() -> None:
    dev_path = Path(DEV_QUESTIONS_PATH)
    locked_path = Path(LOCKED_CANDIDATES_PATH)

    assert dev_path != locked_path
    assert dev_path.is_file()
    assert locked_path.is_file()
    for path in (dev_path, locked_path):
        artifact = load_question_artifact(path)
        assert serialize_question_artifact(artifact) == path.read_bytes()


def test_benchmark_rejects_duplicate_id_across_splits() -> None:
    benchmark = load_retrieval_benchmark()
    locked = benchmark.locked_candidates.model_copy(
        update={
            "questions": (
                benchmark.locked_candidates.questions[0].model_copy(
                    update={"question_id": benchmark.dev.questions[0].question_id}
                ),
                *benchmark.locked_candidates.questions[1:],
            )
        }
    )

    with pytest.raises(RetrievalBenchmarkContaminationError, match="question_id"):
        validate_retrieval_benchmark(benchmark.dev, locked)


def test_benchmark_rejects_normalized_text_contamination() -> None:
    benchmark = load_retrieval_benchmark()
    duplicate_text = "  " + benchmark.dev.questions[0].user_question.upper() + "  "
    locked = benchmark.locked_candidates.model_copy(
        update={
            "questions": (
                benchmark.locked_candidates.questions[0].model_copy(
                    update={"user_question": duplicate_text}
                ),
                *benchmark.locked_candidates.questions[1:],
            )
        }
    )

    with pytest.raises(RetrievalBenchmarkContaminationError, match="question text"):
        validate_retrieval_benchmark(benchmark.dev, locked)


def test_benchmark_rejects_template_family_contamination() -> None:
    benchmark = load_retrieval_benchmark()
    locked = benchmark.locked_candidates.model_copy(
        update={
            "questions": (
                benchmark.locked_candidates.questions[0].model_copy(
                    update={
                        "template_family": benchmark.dev.questions[0].template_family
                    }
                ),
                *benchmark.locked_candidates.questions[1:],
            )
        }
    )

    with pytest.raises(RetrievalBenchmarkContaminationError, match="template family"):
        validate_retrieval_benchmark(benchmark.dev, locked)


def test_normalized_question_text_handles_unicode_case_and_whitespace() -> None:
    assert (
        normalize_question_text("  ＢａｓｅＭｏｄｅｌ\n\tＤＩＣＴ  ")
        == "basemodel dict"
    )


def test_query_renderer_is_deterministic_raw_unicode_and_normalizes_whitespace() -> (
    None
):
    question = _question(
        old_api="  BaseModel.dict()  ",
        ast_context="result  =\n user.dict()",
        user_question="如何  迁移 café  字段？",
    )

    first = render_query(question)
    second = render_query(question)

    assert first == second
    assert "BaseModel.dict()" in first
    assert "result = user.dict()" in first
    assert "如何 迁移 café 字段?" in first
    assert not first.casefold().startswith(("query:", "passage:"))
    assert "query:" not in first.casefold()
    assert "passage:" not in first.casefold()


def test_query_renderer_omits_empty_ast_context_without_empty_label() -> None:
    rendered = render_query(_question(ast_context=""))

    assert "AST context" not in rendered
    assert "  " not in rendered


def test_artifact_rejects_duplicate_question_ids() -> None:
    question = _question()

    with pytest.raises(ValidationError, match="question_id"):
        RetrievalQuestionArtifact(
            schema_version=1,
            split="dev",
            gold_source="official_snapshot_heading_review",
            questions=(question, question),
        )


def test_benchmark_rejects_dev_count_drift() -> None:
    benchmark = load_retrieval_benchmark()
    shortened = benchmark.dev.model_copy(
        update={"questions": benchmark.dev.questions[:-1]}
    )

    with pytest.raises(
        RetrievalBenchmarkContaminationError, match="dev question count"
    ):
        validate_retrieval_benchmark(shortened, benchmark.locked_candidates)


def test_benchmark_rejects_locked_count_drift() -> None:
    benchmark = load_retrieval_benchmark()
    shortened = benchmark.locked_candidates.model_copy(
        update={"questions": benchmark.locked_candidates.questions[:-1]}
    )

    with pytest.raises(RetrievalBenchmarkContaminationError, match="locked candidate"):
        validate_retrieval_benchmark(benchmark.dev, shortened)


def test_benchmark_rejects_rule_category_count_drift() -> None:
    benchmark = load_retrieval_benchmark()
    replacement = benchmark.locked_candidates.questions[0].model_copy(
        update={"rule_category": RetrievalRuleCategory.ROOT_MODEL}
    )
    changed = benchmark.locked_candidates.model_copy(
        update={"questions": (replacement, *benchmark.locked_candidates.questions[1:])}
    )

    with pytest.raises(RetrievalBenchmarkContaminationError, match="rule category"):
        validate_retrieval_benchmark(benchmark.dev, changed)


@pytest.mark.parametrize("field", ["old_api", "ast_context", "user_question"])
def test_query_renderer_rejects_reserved_prefix_in_any_component(field: str) -> None:
    question = _question(**{field: "query: injected"})

    with pytest.raises(ValueError, match="prefix"):
        render_query(question)


def test_query_renderer_changes_when_ast_context_changes() -> None:
    first = render_query(_question(ast_context="model.dict()"))
    second = render_query(_question(ast_context="other.dict()"))

    assert first != second


def test_formal_gold_headings_exist_before_retrieval() -> None:
    benchmark = load_retrieval_benchmark()
    all_questions = (*benchmark.dev.questions, *benchmark.locked_candidates.questions)

    assert all(question.gold_heading_path for question in all_questions)
    assert all(
        question.gold_heading_path[0] == "Migration guide" for question in all_questions
    )
