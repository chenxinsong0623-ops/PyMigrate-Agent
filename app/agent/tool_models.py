"""Day 18 五个只读 Agent tool 的严格输入、输出、错误与审计模型。"""

from __future__ import annotations

import math
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.retrieval.bm25 import tokenize_for_bm25, validate_raw_query
from app.scanner import Finding, RuleId, RuleSpec, Severity
from app.scanner.rule_models import finding_sort_key
from app.security import ZipGuardError, canonicalize_member_path

AGENT_TOOL_SCHEMA_VERSION = "1"
DEFAULT_TOOL_TIMEOUT_SECONDS = 10.0
MAX_TOOL_TIMEOUT_SECONDS = 30.0
MAX_FINDINGS_RETURNED = 100
MAX_SOURCE_CONTEXT_RADIUS = 15
MAX_SOURCE_CONTEXT_CHARACTERS = 8192
MAX_IMPORTERS_RETURNED = 50
MAX_DOC_RESULTS = 5
MAX_DOC_QUERY_CHARACTERS = 1000
MAX_DOC_CHUNK_CHARACTERS = 2000
MAX_DOC_TOTAL_CHARACTERS = MAX_DOC_RESULTS * MAX_DOC_CHUNK_CHARACTERS


class _StrictFrozenModel(BaseModel):
    """Tool boundary 统一使用 strict/frozen/extra-forbid。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ToolName(StrEnum):
    """冻结 SPEC 允许的五个应用 Agent tool。"""

    GET_FINDINGS = "get_findings"
    GET_SOURCE_CONTEXT = "get_source_context"
    GET_LOCAL_IMPORTERS = "get_local_importers"
    SEARCH_OFFICIAL_DOCS = "search_official_docs"
    LOOKUP_RULE_SPEC = "lookup_rule_spec"


class ToolStatus(StrEnum):
    """业务结果与运行失败分离的审计状态。"""

    SUCCESS = "success"
    EMPTY = "empty"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolErrorType(StrEnum):
    """可安全暴露且不包含底层异常正文的稳定错误类型。"""

    INVALID_ARGUMENT = "invalid_argument"
    PATH_NOT_ALLOWED = "path_not_allowed"
    UNKNOWN_PATH = "unknown_path"
    UNKNOWN_RULE = "unknown_rule"
    TIMEOUT = "timeout"
    RETRIEVAL_FAILURE = "retrieval_failure"
    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"


class AgentToolError(RuntimeError):
    """不泄露源码、宿主路径、query 或底层异常原文的公共错误。"""

    def __init__(self, tool_name: ToolName, error_type: ToolErrorType) -> None:
        self.tool_name = tool_name
        self.error_type = error_type
        super().__init__("Agent tool call failed")


class ToolAuditEvent(_StrictFrozenModel):
    """不记录输入正文的最小运行 trace；不属于确定性业务结果。"""

    schema_version: Literal["1"] = AGENT_TOOL_SCHEMA_VERSION
    sequence: int = Field(ge=1)
    tool_name: ToolName
    status: ToolStatus
    error_type: ToolErrorType | None = None
    input_characters: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    truncated: bool
    duration_ms: float = Field(ge=0)

    @field_validator("duration_ms")
    @classmethod
    def validate_duration(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("tool duration 必须是有限数值")
        return value

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status in {ToolStatus.ERROR, ToolStatus.TIMEOUT}:
            if self.error_type is None or self.returned_count != 0 or self.truncated:
                raise ValueError("失败 trace 的 error/count/truncation 不一致")
        elif self.error_type is not None:
            raise ValueError("成功或空结果 trace 不得包含 error_type")
        if self.status is ToolStatus.EMPTY and self.returned_count != 0:
            raise ValueError("empty trace returned_count 必须为 0")
        if (
            self.status is ToolStatus.TIMEOUT
            and self.error_type is not ToolErrorType.TIMEOUT
        ):
            raise ValueError("timeout trace 必须使用 timeout error type")
        return self


class GetFindingsRequest(_StrictFrozenModel):
    """按可选 production rule/severity 过滤当前 RuleScanResult。"""

    rule_id: RuleId | None = None
    severity: Severity | None = None


class GetSourceContextRequest(_StrictFrozenModel):
    """请求 validated Python inventory 中一段有界源码上下文。"""

    path: str = Field(min_length=1, max_length=1024)
    line: int = Field(ge=1)
    radius: int = Field(default=3, ge=0, le=MAX_SOURCE_CONTEXT_RADIUS)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_canonical_python_path(value)


class GetLocalImportersRequest(_StrictFrozenModel):
    """请求 Day 17 graph 中某个本地 Python path 的严格一跳 importer。"""

    path: str = Field(min_length=1, max_length=1024)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_canonical_python_path(value)


class SearchOfficialDocsRequest(_StrictFrozenModel):
    """请求固定官方文档 HybridRetriever；不是 Web search。"""

    query: str = Field(min_length=1, max_length=MAX_DOC_QUERY_CHARACTERS)
    top_k: int = Field(default=3, ge=1, le=MAX_DOC_RESULTS)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = validate_raw_query(value)
        if len(normalized) > MAX_DOC_QUERY_CHARACTERS:
            raise ValueError("query 超过工具上限")
        if not tokenize_for_bm25(normalized):
            raise ValueError("query 必须至少包含一个可检索 token")
        return normalized


class LookupRuleSpecRequest(_StrictFrozenModel):
    """按稳定字符串 identity 查询 production rule metadata。"""

    rule_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_]+$")

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("rule_id 不得包含首尾空白")
        return value


class _CountedResult(_StrictFrozenModel):
    """所有工具统一公开 count 与显式 truncation metadata。"""

    schema_version: Literal["1"] = AGENT_TOOL_SCHEMA_VERSION
    total_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    truncated: bool

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.returned_count > self.total_count:
            raise ValueError("returned_count 不得超过 total_count")
        if self.returned_count < self.total_count and not self.truncated:
            raise ValueError("丢弃结果时必须显式标记 truncated")
        return self


class GetFindingsResult(_CountedResult):
    """保持原 Finding，不重新扫描或创造结果。"""

    findings: tuple[Finding, ...] = Field(max_length=MAX_FINDINGS_RETURNED)

    @model_validator(mode="after")
    def validate_findings(self) -> Self:
        if len(self.findings) != self.returned_count:
            raise ValueError("finding count 与返回值不一致")
        if self.findings != tuple(sorted(self.findings, key=finding_sort_key)):
            raise ValueError("tool findings 必须保持 production 稳定排序")
        if len(set(self.findings)) != len(self.findings):
            raise ValueError("tool findings 不得重复")
        return self


class SourceContextLine(_StrictFrozenModel):
    """源码结果中的一个显式行号与有界文本。"""

    line: int = Field(ge=1)
    text: str = Field(max_length=MAX_SOURCE_CONTEXT_CHARACTERS)
    truncated: bool


class GetSourceContextResult(_CountedResult):
    """不返回 task root 的局部 source lines 与字符上限 metadata。"""

    path: str = Field(min_length=1, max_length=1024)
    requested_line: int = Field(ge=1)
    radius: int = Field(ge=0, le=MAX_SOURCE_CONTEXT_RADIUS)
    file_line_count: int = Field(ge=0)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    source_lines: tuple[SourceContextLine, ...] = Field(
        max_length=MAX_SOURCE_CONTEXT_RADIUS * 2 + 1
    )
    total_characters: int = Field(ge=0)
    returned_characters: int = Field(ge=0, le=MAX_SOURCE_CONTEXT_CHARACTERS)

    @model_validator(mode="after")
    def validate_source_context(self) -> Self:
        validate_canonical_python_path(self.path)
        if len(self.source_lines) != self.returned_count:
            raise ValueError("source line count 与返回值不一致")
        if self.total_count != len(self.source_lines) and not self.truncated:
            raise ValueError("source line 丢弃时必须显式标记 truncated")
        if self.returned_characters != sum(
            len(item.text) for item in self.source_lines
        ):
            raise ValueError("source returned characters 不一致")
        if self.returned_characters > self.total_characters:
            raise ValueError("source returned characters 不得超过完整窗口")
        line_numbers = tuple(item.line for item in self.source_lines)
        if line_numbers != tuple(sorted(line_numbers)) or len(set(line_numbers)) != len(
            line_numbers
        ):
            raise ValueError("source lines 必须按行号排序且唯一")
        if self.file_line_count == 0:
            if self.start_line is not None or self.end_line is not None:
                raise ValueError("空文件不得声明 source range")
        elif self.start_line is None or self.end_line is None:
            raise ValueError("非空文件必须声明 source range")
        elif self.end_line < self.start_line:
            raise ValueError("source range 结束不得早于开始")
        return self


class LocalImporter(_StrictFrozenModel):
    """Day 17 reverse lookup 返回的一个直接本地 importer。"""

    path: str = Field(min_length=1, max_length=1024)
    module: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_canonical_python_path(value)


class GetLocalImportersResult(_CountedResult):
    """不包含 transitive relation 或伪造 Finding 的一跳结果。"""

    path: str = Field(min_length=1, max_length=1024)
    importers: tuple[LocalImporter, ...] = Field(max_length=MAX_IMPORTERS_RETURNED)

    @model_validator(mode="after")
    def validate_importers(self) -> Self:
        validate_canonical_python_path(self.path)
        if len(self.importers) != self.returned_count:
            raise ValueError("importer count 与返回值不一致")
        keys = tuple((item.path, item.module) for item in self.importers)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("importers 必须稳定排序且唯一")
        if any(item.path == self.path for item in self.importers):
            raise ValueError("importer 结果不得包含 target 自身")
        return self


class OfficialDocChunk(_StrictFrozenModel):
    """保留 Hybrid provenance，并显式说明工具层文本截断。"""

    rank: int = Field(gt=0)
    rrf_score: float = Field(gt=0)
    bm25_rank: int | None = Field(default=None, gt=0, le=8)
    dense_rank: int | None = Field(default=None, gt=0, le=8)
    bm25_score: float | None = None
    dense_score: float | None = None
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    heading_path: tuple[str, ...]
    text: str = Field(min_length=1, max_length=MAX_DOC_CHUNK_CHARACTERS)
    full_text_characters: int = Field(ge=1)
    text_truncated: bool
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    git_ref: str = Field(min_length=1)
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str = Field(min_length=1)
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_chunk(self) -> Self:
        scores = (self.rrf_score, self.bm25_score, self.dense_score)
        if any(score is not None and not math.isfinite(score) for score in scores):
            raise ValueError("doc scores 必须是有限数值")
        if (self.bm25_rank is None) != (self.bm25_score is None):
            raise ValueError("BM25 rank/score 必须同时存在或缺失")
        if (self.dense_rank is None) != (self.dense_score is None):
            raise ValueError("Dense rank/score 必须同时存在或缺失")
        if self.bm25_rank is None and self.dense_rank is None:
            raise ValueError("doc chunk 必须来自至少一个检索组件")
        if self.full_text_characters < len(self.text):
            raise ValueError("full text length 不得小于返回文本")
        if self.text_truncated != (self.full_text_characters > len(self.text)):
            raise ValueError("doc text truncation metadata 不一致")
        return self


class SearchOfficialDocsResult(_CountedResult):
    """基于 Hybrid 完整 ranking 的最多五条固定官方文档结果。"""

    query_characters: int = Field(ge=1, le=MAX_DOC_QUERY_CHARACTERS)
    requested_top_k: int = Field(ge=1, le=MAX_DOC_RESULTS)
    results: tuple[OfficialDocChunk, ...] = Field(max_length=MAX_DOC_RESULTS)
    returned_text_characters: int = Field(ge=0, le=MAX_DOC_TOTAL_CHARACTERS)

    @model_validator(mode="after")
    def validate_results(self) -> Self:
        if len(self.results) != self.returned_count:
            raise ValueError("docs count 与返回值不一致")
        if self.returned_count > self.requested_top_k:
            raise ValueError("docs 返回数不得超过 requested top_k")
        ranks = tuple(item.rank for item in self.results)
        if ranks != tuple(sorted(ranks)) or len(set(ranks)) != len(ranks):
            raise ValueError("docs 必须保持 Hybrid 稳定排序")
        if self.returned_text_characters != sum(
            len(item.text) for item in self.results
        ):
            raise ValueError("docs returned text characters 不一致")
        if any(item.text_truncated for item in self.results) and not self.truncated:
            raise ValueError("chunk 文本截断必须向 tool result 传播")
        return self


class LookupRuleSpecResult(_CountedResult):
    """单条 production rule metadata；未知 ID 使用显式错误。"""

    rule_spec: RuleSpec

    @model_validator(mode="after")
    def validate_single_result(self) -> Self:
        if self.total_count != 1 or self.returned_count != 1 or self.truncated:
            raise ValueError("rule lookup 成功结果必须恰好返回一条且不截断")
        return self


def validate_canonical_python_path(value: str) -> str:
    """复用 ZIP Guard canonicalizer，并要求输入本身已是 canonical POSIX path。"""
    if not isinstance(value, str):
        raise TypeError("path 必须是字符串")
    try:
        canonical = canonicalize_member_path(value).as_posix()
    except ZipGuardError:
        raise ValueError("path 不在允许范围") from None
    path = PurePosixPath(value)
    if (
        canonical != value
        or path.is_absolute()
        or path.suffix.casefold() != ".py"
        or ".." in path.parts
    ):
        raise ValueError("path 必须是 canonical POSIX relative Python path")
    return value
