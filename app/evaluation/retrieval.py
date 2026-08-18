"""检索题隔离、确定性 query、纯指标与三路 dev evaluator。"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    load_chunk_artifact,
)
from app.retrieval.bm25 import BM25SearchResult
from app.retrieval.dense import DenseSearchResult
from app.retrieval.hybrid import HybridSearchResponse

RETRIEVAL_QUESTION_SCHEMA_VERSION = 1
RETRIEVAL_EVALUATOR_SCHEMA_VERSION = 1
DEV_QUESTION_COUNT = 12
LOCKED_CANDIDATE_COUNT = 20
DEV_QUESTIONS_PATH = "data/evaluation/retrieval/dev.json"
LOCKED_CANDIDATES_PATH = "data/evaluation/retrieval/locked_candidates.json"

_QUESTION_ID_PATTERN = re.compile(r"^(?:dev|locked)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_TEMPLATE_FAMILY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class RetrievalRuleCategory(StrEnum):
    """只用于 retrieval benchmark 的八类稳定 key，不是未来 scanner rule ID。"""

    BASE_MODEL_METHODS = "base_model_methods"
    DATA_LOADING = "data_loading"
    CONFIG = "config"
    VALIDATORS = "validators"
    FIELD_ARGUMENTS = "field_arguments"
    SETTINGS = "settings"
    GENERIC_MODEL = "generic_model"
    ROOT_MODEL = "root_model"


class RetrievalSplit(StrEnum):
    """Day 12 允许建立的物理数据分割。"""

    DEV = "dev"
    LOCKED_CANDIDATE = "locked_candidate"


class RetrievalSystem(StrEnum):
    """必须独立报告的三路检索系统。"""

    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"


class RetrievalBenchmarkContaminationError(RuntimeError):
    """Dev/locked benchmark 数量、类别或无污染边界不成立。"""


class EvaluationContractError(RuntimeError):
    """Evaluator 收到非 dev 数据或不一致的检索响应。"""


class _EvaluationModel(BaseModel):
    """Day 12 数据和结果使用的严格不可变模型。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class RetrievalQuestion(_EvaluationModel):
    """一条与未来 AST query 结构对齐的 retrieval evaluation question。"""

    schema_version: Literal[1] = RETRIEVAL_QUESTION_SCHEMA_VERSION
    question_id: str
    split: RetrievalSplit
    rule_category: RetrievalRuleCategory
    old_api: str
    ast_context: str
    user_question: str
    gold_heading_path: tuple[str, ...] = Field(min_length=1)
    template_family: str

    @field_validator("question_id")
    @classmethod
    def validate_question_id(cls, value: str) -> str:
        if _QUESTION_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("question_id 格式无效")
        return value

    @field_validator("old_api", "user_question")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("检索题必需文本不能为空")
        return value.strip()

    @field_validator("ast_context")
    @classmethod
    def normalize_optional_context(cls, value: str) -> str:
        return value.strip()

    @field_validator("gold_heading_path")
    @classmethod
    def validate_gold_heading(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not heading.strip() for heading in value):
            raise ValueError("gold heading entries 不能为空")
        return value

    @field_validator("template_family")
    @classmethod
    def validate_template_family(cls, value: str) -> str:
        if _TEMPLATE_FAMILY_PATTERN.fullmatch(value) is None:
            raise ValueError("template_family 格式无效")
        return value

    @model_validator(mode="after")
    def validate_id_matches_split(self) -> Self:
        expected_prefix = "dev-" if self.split is RetrievalSplit.DEV else "locked-"
        if not self.question_id.startswith(expected_prefix):
            raise ValueError("question_id 前缀必须与 split 一致")
        return self


class RetrievalQuestionArtifact(_EvaluationModel):
    """一个物理 split 的 deterministic question artifact。"""

    schema_version: Literal[1] = RETRIEVAL_QUESTION_SCHEMA_VERSION
    split: RetrievalSplit
    gold_source: Literal["official_snapshot_heading_review"]
    questions: tuple[RetrievalQuestion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_artifact_questions(self) -> Self:
        identifiers = [question.question_id for question in self.questions]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("artifact question_id 必须唯一")
        if any(question.split is not self.split for question in self.questions):
            raise ValueError("question split 必须与 artifact split 一致")
        if any(
            question.schema_version != self.schema_version
            for question in self.questions
        ):
            raise ValueError("question schema version 必须与 artifact 一致")
        return self


@dataclass(frozen=True, slots=True)
class RetrievalBenchmark:
    """已经通过 12/20、八类与 contamination 校验的 benchmark design。"""

    dev: RetrievalQuestionArtifact
    locked_candidates: RetrievalQuestionArtifact


def normalize_question_text(text: str) -> str:
    """用 Unicode NFKC、casefold 与单空格建立跨 split 精确文本签名。"""
    if not isinstance(text, str):
        raise TypeError("question text 必须是字符串")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def _normalize_query_component(text: str) -> str:
    normalized = _WHITESPACE_PATTERN.sub(
        " ", unicodedata.normalize("NFKC", text)
    ).strip()
    if normalized.casefold().startswith(("query:", "passage:")):
        raise ValueError("query component 不得预加 embedding prefix")
    return normalized


_RULE_QUERY_LABELS = {
    RetrievalRuleCategory.BASE_MODEL_METHODS: "BaseModel method migration",
    RetrievalRuleCategory.DATA_LOADING: "Pydantic model data loading migration",
    RetrievalRuleCategory.CONFIG: "Pydantic model configuration migration",
    RetrievalRuleCategory.VALIDATORS: "Pydantic validator migration",
    RetrievalRuleCategory.FIELD_ARGUMENTS: "Pydantic Field argument migration",
    RetrievalRuleCategory.SETTINGS: "Pydantic settings migration",
    RetrievalRuleCategory.GENERIC_MODEL: "Pydantic generic model migration",
    RetrievalRuleCategory.ROOT_MODEL: "Pydantic root model migration",
}


def render_query(question: RetrievalQuestion) -> str:
    """按固定字段顺序渲染供三路检索共同消费的未加 prefix 原始 query。"""
    old_api = _normalize_query_component(question.old_api)
    context = _normalize_query_component(question.ast_context)
    user_question = _normalize_query_component(question.user_question)
    parts = [
        "Pydantic v1 to v2 migration.",
        f"Rule category: {_RULE_QUERY_LABELS[question.rule_category]}.",
        f"Legacy API or concept: {old_api}.",
    ]
    if context:
        parts.append(f"AST context: {context}.")
    parts.append(f"Question: {user_question}")
    rendered = " ".join(parts)
    if rendered.casefold().startswith(("query:", "passage:")):
        raise AssertionError("rendered query must remain raw")
    return rendered


def serialize_question_artifact(artifact: RetrievalQuestionArtifact) -> bytes:
    """生成稳定 UTF-8、排序 key、缩进 2 空格且末尾换行的 JSON bytes。"""
    return (
        json.dumps(
            artifact.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def load_question_artifact(path: str | Path) -> RetrievalQuestionArtifact:
    """严格加载一个 question artifact，不执行任何检索。"""
    try:
        return RetrievalQuestionArtifact.model_validate_json(Path(path).read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise RetrievalBenchmarkContaminationError(
            "retrieval question artifact is missing or invalid"
        ) from error


def validate_retrieval_benchmark(
    dev: RetrievalQuestionArtifact,
    locked_candidates: RetrievalQuestionArtifact,
) -> None:
    """验证数量、八类覆盖、ID/文本和模板族跨 split 隔离。"""
    if dev.split is not RetrievalSplit.DEV:
        raise RetrievalBenchmarkContaminationError("dev artifact split is invalid")
    if locked_candidates.split is not RetrievalSplit.LOCKED_CANDIDATE:
        raise RetrievalBenchmarkContaminationError("locked artifact split is invalid")
    if len(dev.questions) != DEV_QUESTION_COUNT:
        raise RetrievalBenchmarkContaminationError("dev question count must be 12")
    if len(locked_candidates.questions) != LOCKED_CANDIDATE_COUNT:
        raise RetrievalBenchmarkContaminationError(
            "locked candidate question count must be 20"
        )

    all_questions = (*dev.questions, *locked_candidates.questions)
    identifiers = [question.question_id for question in all_questions]
    if len(set(identifiers)) != len(identifiers):
        raise RetrievalBenchmarkContaminationError(
            "question_id contamination exists across splits"
        )
    category_counts = Counter(question.rule_category for question in all_questions)
    expected_counts = Counter({category: 4 for category in RetrievalRuleCategory})
    if category_counts != expected_counts:
        raise RetrievalBenchmarkContaminationError(
            "each rule category must have exactly four questions"
        )

    dev_texts = {
        normalize_question_text(question.user_question) for question in dev.questions
    }
    locked_texts = {
        normalize_question_text(question.user_question)
        for question in locked_candidates.questions
    }
    if dev_texts & locked_texts:
        raise RetrievalBenchmarkContaminationError(
            "normalized question text contamination exists across splits"
        )
    dev_families = {question.template_family for question in dev.questions}
    locked_families = {
        question.template_family for question in locked_candidates.questions
    }
    if dev_families & locked_families:
        raise RetrievalBenchmarkContaminationError(
            "template family contamination exists across splits"
        )


def _validate_gold_headings(
    benchmark: RetrievalBenchmark,
    chunk_artifact_path: str | Path,
) -> None:
    artifact = load_chunk_artifact(Path(chunk_artifact_path))
    available_headings = {chunk.heading_path for chunk in artifact.chunks}
    for question_artifact in (benchmark.dev, benchmark.locked_candidates):
        for question in question_artifact.questions:
            if question.gold_heading_path not in available_headings:
                raise RetrievalBenchmarkContaminationError(
                    "gold heading does not exist in the formal chunk artifact"
                )


def load_retrieval_benchmark(
    dev_path: str | Path = DEV_QUESTIONS_PATH,
    locked_path: str | Path = LOCKED_CANDIDATES_PATH,
    chunk_artifact_path: str | Path = CHUNK_ARTIFACT_PATH,
) -> RetrievalBenchmark:
    """只读加载两个物理 split，并在检索前验证 benchmark 与 gold headings。"""
    benchmark = RetrievalBenchmark(
        dev=load_question_artifact(dev_path),
        locked_candidates=load_question_artifact(locked_path),
    )
    validate_retrieval_benchmark(benchmark.dev, benchmark.locked_candidates)
    _validate_gold_headings(benchmark, chunk_artifact_path)
    return benchmark


class RankedReference(_EvaluationModel):
    """评测 artifact 需要的最小检索引用，不复制官方 chunk 正文。"""

    rank: int = Field(gt=0)
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    heading_path: tuple[str, ...]


class RankedHeading(Protocol):
    """BM25、Dense、Hybrid result 共有的纯指标输入。"""

    rank: int
    chunk_id: str
    heading_path: tuple[str, ...]


class RetrievalQuestionScore(_EvaluationModel):
    """单题单系统的固定 Recall/MRR 结果。"""

    first_gold_rank: int | None = Field(default=None, gt=0)
    recall_at_1: Literal[0, 1]
    recall_at_3: Literal[0, 1]
    reciprocal_rank_at_5: float = Field(ge=0, le=1)
    returned_count: int = Field(ge=0)


class RetrievalAggregate(_EvaluationModel):
    """同一路系统对全部 dev 题的算术平均。"""

    system: RetrievalSystem | None = None
    question_count: int = Field(gt=0)
    recall_at_1: float = Field(ge=0, le=1)
    recall_at_3: float = Field(ge=0, le=1)
    mrr_at_5: float = Field(ge=0, le=1)


def score_heading_ranking(
    gold_heading_path: tuple[str, ...],
    results: Sequence[RankedHeading],
) -> RetrievalQuestionScore:
    """以精确 heading_path 相等计算首个相关排名与三项固定指标。"""
    if not gold_heading_path or any(
        not heading.strip() for heading in gold_heading_path
    ):
        raise ValueError("gold heading path 不能为空")
    ranks = [result.rank for result in results]
    if ranks != list(range(1, len(results) + 1)):
        raise ValueError("result ranks must be continuous from 1")

    first_gold_rank = next(
        (
            result.rank
            for result in results
            if tuple(result.heading_path) == gold_heading_path
        ),
        None,
    )
    return RetrievalQuestionScore(
        first_gold_rank=first_gold_rank,
        recall_at_1=int(first_gold_rank == 1),
        recall_at_3=int(first_gold_rank is not None and first_gold_rank <= 3),
        reciprocal_rank_at_5=(
            1 / first_gold_rank
            if first_gold_rank is not None and first_gold_rank <= 5
            else 0.0
        ),
        returned_count=len(results),
    )


def aggregate_question_scores(
    scores: Sequence[RetrievalQuestionScore],
) -> RetrievalAggregate:
    """分别求 Recall@1、Recall@3 与 MRR@5；不制造 overall accuracy。"""
    if not scores:
        raise ValueError("scores 不能为空")
    count = len(scores)
    return RetrievalAggregate(
        question_count=count,
        recall_at_1=sum(score.recall_at_1 for score in scores) / count,
        recall_at_3=sum(score.recall_at_3 for score in scores) / count,
        mrr_at_5=sum(score.reciprocal_rank_at_5 for score in scores) / count,
    )


class RetrievalEvaluationDetail(_EvaluationModel):
    """机器可读的单题单系统结果与最小 ranked references。"""

    question_id: str
    system: RetrievalSystem
    rendered_query: str = Field(min_length=1)
    gold_heading_path: tuple[str, ...] = Field(min_length=1)
    first_gold_rank: int | None = Field(default=None, gt=0)
    recall_at_1: Literal[0, 1]
    recall_at_3: Literal[0, 1]
    reciprocal_rank_at_5: float = Field(ge=0, le=1)
    returned_count: int = Field(ge=0)
    results: tuple[RankedReference, ...]


class DevRetrievalEvaluationRun(_EvaluationModel):
    """一次完整、未捕获基础设施失败的 12 题三路 dev 运行。"""

    evaluator_schema_version: Literal[1] = RETRIEVAL_EVALUATOR_SCHEMA_VERSION
    split: Literal["dev"] = "dev"
    question_count: Literal[12] = DEV_QUESTION_COUNT
    aggregates: tuple[RetrievalAggregate, ...] = Field(min_length=3, max_length=3)
    details: tuple[RetrievalEvaluationDetail, ...] = Field(
        min_length=DEV_QUESTION_COUNT * 3,
        max_length=DEV_QUESTION_COUNT * 3,
    )


class BM25EvaluationProtocol(Protocol):
    def search(self, query: str, top_k: int = 8) -> tuple[BM25SearchResult, ...]: ...


class DenseEvaluationProtocol(Protocol):
    async def search(
        self, query: str, top_k: int = 8
    ) -> tuple[DenseSearchResult, ...]: ...


class HybridEvaluationProtocol(Protocol):
    async def search(self, query: str) -> HybridSearchResponse: ...


def _references(results: Sequence[RankedHeading]) -> tuple[RankedReference, ...]:
    return tuple(
        RankedReference(
            rank=result.rank,
            chunk_id=result.chunk_id,
            heading_path=result.heading_path,
        )
        for result in results
    )


def _detail(
    *,
    question: RetrievalQuestion,
    system: RetrievalSystem,
    rendered_query: str,
    results: Sequence[RankedHeading],
) -> RetrievalEvaluationDetail:
    references = _references(results)
    score = score_heading_ranking(question.gold_heading_path, references)
    return RetrievalEvaluationDetail(
        question_id=question.question_id,
        system=system,
        rendered_query=rendered_query,
        gold_heading_path=question.gold_heading_path,
        first_gold_rank=score.first_gold_rank,
        recall_at_1=score.recall_at_1,
        recall_at_3=score.recall_at_3,
        reciprocal_rank_at_5=score.reciprocal_rank_at_5,
        returned_count=score.returned_count,
        results=references,
    )


class DevRetrievalEvaluator:
    """只接受 12 条 dev artifact，并让三路接收完全相同的 raw query。"""

    def __init__(
        self,
        *,
        bm25: BM25EvaluationProtocol,
        dense: DenseEvaluationProtocol,
        hybrid: HybridEvaluationProtocol,
    ) -> None:
        self._bm25 = bm25
        self._dense = dense
        self._hybrid = hybrid

    async def evaluate(
        self, artifact: RetrievalQuestionArtifact
    ) -> DevRetrievalEvaluationRun:
        if artifact.split is not RetrievalSplit.DEV:
            raise EvaluationContractError("Day 12 evaluator only accepts dev")
        if len(artifact.questions) != DEV_QUESTION_COUNT:
            raise EvaluationContractError("Day 12 evaluator requires 12 dev questions")

        details: list[RetrievalEvaluationDetail] = []
        for question in artifact.questions:
            query = render_query(question)
            bm25_results = self._bm25.search(query, top_k=8)
            dense_results = await self._dense.search(query, top_k=8)
            hybrid_response = await self._hybrid.search(query)
            if hybrid_response.query != query:
                raise EvaluationContractError(
                    "hybrid response query does not match rendered query"
                )
            for system, results in (
                (RetrievalSystem.BM25, bm25_results),
                (RetrievalSystem.DENSE, dense_results),
                (RetrievalSystem.HYBRID, hybrid_response.results),
            ):
                details.append(
                    _detail(
                        question=question,
                        system=system,
                        rendered_query=query,
                        results=results,
                    )
                )

        aggregates: list[RetrievalAggregate] = []
        for system in RetrievalSystem:
            scores = tuple(
                RetrievalQuestionScore(
                    first_gold_rank=detail.first_gold_rank,
                    recall_at_1=detail.recall_at_1,
                    recall_at_3=detail.recall_at_3,
                    reciprocal_rank_at_5=detail.reciprocal_rank_at_5,
                    returned_count=detail.returned_count,
                )
                for detail in details
                if detail.system is system
            )
            aggregate = aggregate_question_scores(scores)
            aggregates.append(aggregate.model_copy(update={"system": system}))
        return DevRetrievalEvaluationRun(
            aggregates=tuple(aggregates),
            details=tuple(details),
        )
