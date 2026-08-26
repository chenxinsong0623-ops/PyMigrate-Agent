"""Day 19 有界 Agent 的严格边界模型与确定性分组。"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.agent.tool_models import (
    GetFindingsRequest,
    GetLocalImportersRequest,
    GetSourceContextRequest,
    LookupRuleSpecRequest,
    OfficialDocChunk,
    SearchOfficialDocsRequest,
    ToolName,
)
from app.scanner import Finding, OneHopImporter, RuleId, RuleScanResult
from app.scanner.rule_models import finding_sort_key

AGENT_GRAPH_SCHEMA_VERSION = "1"
MAX_AMBIGUOUS_GROUPS = 8
MAX_AGENT_TOOL_CALLS = 8
MAX_AGENT_STEPS = 32
MAX_LLM_TIMEOUT_SECONDS = 20.0
MAX_AGENT_TIMEOUT_SECONDS = 45.0
MAX_AGENT_RETRIES = 1
MAX_FINDINGS_PER_GROUP = 100
MAX_RETRIEVED_CHUNKS = MAX_AMBIGUOUS_GROUPS * 5
MAX_AGENT_VALIDATION_ERRORS = 32


class _StrictFrozenModel(BaseModel):
    """Graph 边界统一使用 strict/frozen/extra-forbid。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


class AgentDegradedReason(StrEnum):
    """不包含底层异常正文的稳定降级原因。"""

    NO_MODEL = "no_model"
    LLM_REVIEW_DISABLED = "llm_review_disabled"
    AMBIGUOUS_GROUP_LIMIT = "ambiguous_group_limit"
    LLM_TIMEOUT = "llm_timeout"
    LLM_INVALID_RESPONSE = "llm_invalid_response"
    LLM_ERROR = "llm_error"
    TOOL_ERROR = "tool_error"
    TOOL_CALL_LIMIT = "tool_call_limit"
    STEP_LIMIT = "step_limit"
    AGENT_TIMEOUT = "agent_timeout"


class AgentTerminalStatus(StrEnum):
    """一次 graph run 的显式 terminal state。"""

    COMPLETED = "completed"
    DEGRADED = "degraded"


class AgentNode(StrEnum):
    """允许进入 deterministic trace 的 graph node 名称。"""

    PREPARE = "prepare"
    LLM_DECIDE = "llm_decide"
    VALIDATE_ACTION = "validate_action"
    EXECUTE_TOOL = "execute_tool"
    COMPLETE_GROUP = "complete_group"


class AgentStepStatus(StrEnum):
    """不记录 duration 或正文的节点执行状态。"""

    SUCCESS = "success"
    DEGRADED = "degraded"


class AgentRuntimeLimits(_StrictFrozenModel):
    """生产上限只能保持或收紧，不能通过注入放宽。"""

    max_ambiguous_groups: int = Field(
        default=MAX_AMBIGUOUS_GROUPS,
        ge=1,
        le=MAX_AMBIGUOUS_GROUPS,
    )
    max_tool_calls: int = Field(
        default=MAX_AGENT_TOOL_CALLS,
        ge=1,
        le=MAX_AGENT_TOOL_CALLS,
    )
    max_steps: int = Field(default=MAX_AGENT_STEPS, ge=1, le=MAX_AGENT_STEPS)
    llm_timeout_seconds: float = Field(
        default=MAX_LLM_TIMEOUT_SECONDS,
        gt=0,
        le=MAX_LLM_TIMEOUT_SECONDS,
    )
    total_timeout_seconds: float = Field(
        default=MAX_AGENT_TIMEOUT_SECONDS,
        gt=0,
        le=MAX_AGENT_TIMEOUT_SECONDS,
    )
    max_retries: int = Field(default=MAX_AGENT_RETRIES, ge=0, le=MAX_AGENT_RETRIES)


class RepositorySummary(_StrictFrozenModel):
    """不含 task root 或宿主路径的确定性仓库摘要。"""

    python_files: int = Field(ge=0, le=200)
    python_loc: int = Field(ge=0, le=50_000)
    direct_finding_count: int = Field(ge=0)
    directly_affected_files: int = Field(ge=0, le=200)
    one_hop_dependent_files: int = Field(ge=0, le=200)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.directly_affected_files > self.python_files:
            raise ValueError("directly affected files 不得超过 Python files")
        if self.one_hop_dependent_files > self.python_files:
            raise ValueError("one-hop dependent files 不得超过 Python files")
        if self.direct_finding_count == 0 and self.directly_affected_files != 0:
            raise ValueError("zero finding 时 direct file count 必须为 0")
        return self


class AgentRunRequest(_StrictFrozenModel):
    """未来 API 无需理解 LangGraph 内部 node 的应用级入口。"""

    analysis_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    repo_summary: RepositorySummary
    rule_result: RuleScanResult
    one_hop_importers: tuple[OneHopImporter, ...]
    llm_review: bool = True

    @model_validator(mode="after")
    def validate_finding_summary(self) -> Self:
        if self.repo_summary.direct_finding_count != len(self.rule_result.findings):
            raise ValueError("repo summary finding count 与 RuleScanResult 不一致")
        affected = {finding.relative_path for finding in self.rule_result.findings}
        if self.repo_summary.directly_affected_files != len(affected):
            raise ValueError("repo summary direct file count 与 findings 不一致")
        dependent_files = {
            item.importer_relative_path for item in self.one_hop_importers
        }
        if self.repo_summary.one_hop_dependent_files != len(dependent_files):
            raise ValueError("repo summary one-hop count 与 importer relations 不一致")
        if any(
            item.direct_relative_path not in affected for item in self.one_hop_importers
        ):
            raise ValueError("one-hop relation 必须指向 deterministic finding file")
        return self


class AmbiguousGroup(_StrictFrozenModel):
    """对确定性 finding 做证据/解释编排；不表示 AST 事实可被改写。"""

    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=1024)
    rule_id: RuleId
    finding_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_FINDINGS_PER_GROUP,
    )
    reason: Literal["evidence_selection"] = "evidence_selection"

    @field_validator("finding_ids")
    @classmethod
    def validate_finding_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(value)) or len(set(value)) != len(value):
            raise ValueError("group finding IDs 必须稳定排序且唯一")
        return value


class AmbiguityPreparation(_StrictFrozenModel):
    """最多八组与确定性 overflow 的准备结果。"""

    groups: tuple[AmbiguousGroup, ...] = Field(max_length=MAX_AMBIGUOUS_GROUPS)
    overflow_finding_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_preparation(self) -> Self:
        keys = tuple(
            (item.relative_path, item.rule_id.value, item.finding_ids[0])
            for item in self.groups
        )
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("ambiguous groups 必须稳定排序且唯一")
        grouped_ids = {
            finding_id for group in self.groups for finding_id in group.finding_ids
        }
        if len(grouped_ids) != sum(len(group.finding_ids) for group in self.groups):
            raise ValueError("一个 finding 不得进入多个 group")
        if len(set(self.overflow_finding_ids)) != len(self.overflow_finding_ids):
            raise ValueError("overflow finding IDs 不得重复")
        if grouped_ids.intersection(self.overflow_finding_ids):
            raise ValueError("group 与 overflow finding IDs 必须隔离")
        return self


class AgentStep(_StrictFrozenModel):
    """不含 timing、源码、query 或 raw model output 的业务步骤。"""

    sequence: int = Field(ge=1, le=MAX_AGENT_STEPS)
    node: AgentNode
    status: AgentStepStatus
    group_id: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    tool_name: ToolName | None = None


class AgentValidationError(_StrictFrozenModel):
    """只保留稳定错误类型，不复制底层 exception 或 LLM content。"""

    node: AgentNode
    error_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    group_id: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )


class ExplanationCandidate(_StrictFrozenModel):
    """LLM 仅可添加的解释候选。"""

    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    finding_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_FINDINGS_PER_GROUP,
    )
    text: str = Field(min_length=1, max_length=1000)
    model: str = Field(min_length=1, max_length=128)

    @field_validator("text", "model")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("candidate text 不得包含首尾空白")
        return value


class SelectedDocCandidate(_StrictFrozenModel):
    """Day 20 尚未校验的引用候选关联。"""

    analysis_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    finding_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_FINDINGS_PER_GROUP,
    )
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    validated: Literal[False] = False


class RetrievalBinding(_StrictFrozenModel):
    """不保存 raw query 的 group/rule/query/chunk 安全绑定。"""

    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    rule_id: RuleId
    finding_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_FINDINGS_PER_GROUP,
    )
    query_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    matched_query_terms: tuple[str, ...]
    chunk_ids: tuple[str, ...] = Field(min_length=1, max_length=5)

    @field_validator("finding_ids", "matched_query_terms", "chunk_ids")
    @classmethod
    def validate_unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("retrieval binding values 不得重复")
        return value

    @field_validator("matched_query_terms")
    @classmethod
    def validate_matched_terms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item or item != item.strip() for item in value):
            raise ValueError("matched query terms 必须是无首尾空白的非空字符串")
        if value != tuple(sorted(value, key=str.casefold)):
            raise ValueError("matched query terms 必须稳定排序")
        return value


class HumanReviewItem(_StrictFrozenModel):
    """无模型、失败、overflow 或模型显式请求产生的人工复核项。"""

    group_id: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    finding_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_FINDINGS_PER_GROUP,
    )
    reason: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    detail: str | None = Field(default=None, min_length=1, max_length=500)


class AgentDraft(_StrictFrozenModel):
    """仅作为 Day 20 输入，不是最终 JSON/Markdown report。"""

    explanations: tuple[ExplanationCandidate, ...] = Field(
        max_length=MAX_AMBIGUOUS_GROUPS
    )
    selected_doc_candidates: tuple[SelectedDocCandidate, ...] = Field(
        max_length=MAX_RETRIEVED_CHUNKS
    )
    human_review_items: tuple[HumanReviewItem, ...] = Field(max_length=600)


class AgentRunResult(_StrictFrozenModel):
    """稳定、无 timing 的 Day 19 typed result。"""

    schema_version: Literal["1"] = AGENT_GRAPH_SCHEMA_VERSION
    analysis_id: str = Field(min_length=1, max_length=128)
    repo_summary: RepositorySummary
    findings: tuple[Finding, ...]
    finding_ids: tuple[str, ...]
    one_hop_importers: tuple[OneHopImporter, ...]
    ambiguous_groups: tuple[AmbiguousGroup, ...] = Field(
        max_length=MAX_AMBIGUOUS_GROUPS
    )
    retrieved_chunks: tuple[OfficialDocChunk, ...] = Field(
        max_length=MAX_RETRIEVED_CHUNKS
    )
    retrieval_bindings: tuple[RetrievalBinding, ...] = Field(
        max_length=MAX_AMBIGUOUS_GROUPS
    )
    agent_steps: tuple[AgentStep, ...] = Field(max_length=MAX_AGENT_STEPS)
    draft_report: AgentDraft
    validation_errors: tuple[AgentValidationError, ...] = Field(
        max_length=MAX_AGENT_VALIDATION_ERRORS
    )
    degraded_reason: AgentDegradedReason | None
    terminal_status: AgentTerminalStatus
    tool_calls_used: int = Field(ge=0, le=MAX_AGENT_TOOL_CALLS)
    llm_calls_used: int = Field(ge=0, le=MAX_AMBIGUOUS_GROUPS * 2)
    reviewed_finding_ids: tuple[str, ...]
    retry_count: int = Field(ge=0, le=MAX_AGENT_RETRIES)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        expected_findings = tuple(sorted(self.findings, key=finding_sort_key))
        if self.findings != expected_findings or len(set(self.findings)) != len(
            self.findings
        ):
            raise ValueError("Agent findings 必须保持稳定排序且唯一")
        expected_ids = tuple(finding_identity(item) for item in self.findings)
        if self.finding_ids != expected_ids:
            raise ValueError("Agent finding IDs 必须与 deterministic findings 对齐")
        if len(set(self.reviewed_finding_ids)) != len(self.reviewed_finding_ids):
            raise ValueError("每个 finding 最多进入一次模型审查")
        if not set(self.reviewed_finding_ids).issubset(self.finding_ids):
            raise ValueError("reviewed IDs 必须来自 deterministic findings")
        retrieved_ids = tuple(item.chunk_id for item in self.retrieved_chunks)
        if len(set(retrieved_ids)) != len(retrieved_ids):
            raise ValueError("retrieved chunks 不得重复")
        groups = {item.group_id: item for item in self.ambiguous_groups}
        binding_keys: set[tuple[str, str]] = set()
        for binding in self.retrieval_bindings:
            group = groups.get(binding.group_id)
            if group is None:
                raise ValueError("retrieval binding 必须属于当前 group")
            if (
                binding.rule_id is not group.rule_id
                or binding.finding_ids != group.finding_ids
            ):
                raise ValueError("retrieval binding 必须与 group identity 对齐")
            if not set(binding.chunk_ids).issubset(retrieved_ids):
                raise ValueError(
                    "retrieval binding chunks 必须来自当前 retrieved chunks"
                )
            key = (binding.group_id, binding.query_sha256)
            if key in binding_keys:
                raise ValueError("retrieval binding 不得重复")
            binding_keys.add(key)
        if self.terminal_status is AgentTerminalStatus.COMPLETED:
            if self.degraded_reason is not None:
                raise ValueError("completed result 不得包含 degraded reason")
        elif self.degraded_reason is None:
            raise ValueError("degraded result 必须包含 degraded reason")
        return self


class GetFindingsCall(_StrictFrozenModel):
    tool: Literal["get_findings"]
    request: GetFindingsRequest


class GetSourceContextCall(_StrictFrozenModel):
    tool: Literal["get_source_context"]
    request: GetSourceContextRequest


class GetLocalImportersCall(_StrictFrozenModel):
    tool: Literal["get_local_importers"]
    request: GetLocalImportersRequest


class SearchOfficialDocsCall(_StrictFrozenModel):
    tool: Literal["search_official_docs"]
    request: SearchOfficialDocsRequest


class LookupRuleSpecCall(_StrictFrozenModel):
    tool: Literal["lookup_rule_spec"]
    request: LookupRuleSpecRequest


AgentToolCall: TypeAlias = Annotated[
    GetFindingsCall
    | GetSourceContextCall
    | GetLocalImportersCall
    | SearchOfficialDocsCall
    | LookupRuleSpecCall,
    Field(discriminator="tool"),
]


class CallToolDecision(_StrictFrozenModel):
    action: Literal["call_tool"]
    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    call: AgentToolCall


class FinishGroupDecision(_StrictFrozenModel):
    action: Literal["finish_group"]
    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    explanation: str = Field(min_length=1, max_length=1000)

    @field_validator("explanation")
    @classmethod
    def validate_explanation(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("explanation 不得包含首尾空白")
        return value


class RequestHumanReviewDecision(_StrictFrozenModel):
    action: Literal["request_human_review"]
    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("human review reason 不得包含首尾空白")
        return value


AgentDecision: TypeAlias = Annotated[
    CallToolDecision | FinishGroupDecision | RequestHumanReviewDecision,
    Field(discriminator="action"),
]

_AGENT_DECISION_ADAPTER = TypeAdapter(AgentDecision)


def parse_agent_decision(content: str) -> AgentDecision:
    """把 model content 当 JSON 校验；绝不把字符串直接当 executable action。"""
    if not isinstance(content, str):
        raise TypeError("LLM content 必须是字符串")
    return _AGENT_DECISION_ADAPTER.validate_json(content, strict=True)


def finding_identity(finding: Finding) -> str:
    """只基于 Finding 业务字段产生稳定内容 identity。"""
    if not isinstance(finding, Finding):
        raise TypeError("finding 必须是 Finding")
    canonical = json.dumps(
        finding.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def prepare_ambiguous_groups(
    findings: tuple[Finding, ...],
    *,
    max_groups: int = MAX_AMBIGUOUS_GROUPS,
) -> AmbiguityPreparation:
    """按 path/rule 稳定分组，最多八组；不改变或新增 Finding。"""
    if isinstance(max_groups, bool) or not isinstance(max_groups, int):
        raise TypeError("max_groups 必须是整数")
    if not 1 <= max_groups <= MAX_AMBIGUOUS_GROUPS:
        raise ValueError("max_groups 必须位于 1..8")
    checked = RuleScanResult(findings=tuple(sorted(findings, key=finding_sort_key)))
    grouped: dict[tuple[str, RuleId], list[Finding]] = {}
    for finding in checked.findings:
        grouped.setdefault((finding.relative_path, finding.rule_id), []).append(finding)

    all_groups: list[AmbiguousGroup] = []
    for (relative_path, rule_id), items in sorted(
        grouped.items(),
        key=lambda item: (item[0][0], item[0][1].value),
    ):
        all_finding_ids = tuple(sorted(finding_identity(item) for item in items))
        for offset in range(0, len(all_finding_ids), MAX_FINDINGS_PER_GROUP):
            finding_ids = all_finding_ids[offset : offset + MAX_FINDINGS_PER_GROUP]
            canonical = json.dumps(
                {
                    "finding_ids": finding_ids,
                    "relative_path": relative_path,
                    "rule_id": rule_id.value,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            all_groups.append(
                AmbiguousGroup(
                    group_id=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
                    relative_path=relative_path,
                    rule_id=rule_id,
                    finding_ids=finding_ids,
                )
            )

    selected = tuple(all_groups[:max_groups])
    overflow = tuple(
        finding_id
        for group in all_groups[max_groups:]
        for finding_id in group.finding_ids
    )
    return AmbiguityPreparation(
        groups=selected,
        overflow_finding_ids=overflow,
    )
