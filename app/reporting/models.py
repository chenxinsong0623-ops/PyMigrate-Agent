"""Day 20 Citation Guard 与最终报告的严格类型边界。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent import (
    AgentDegradedReason,
    HumanReviewItem,
    RepositorySummary,
    finding_identity,
)
from app.scanner import Finding, OneHopImporter, RuleId
from app.scanner.import_graph import one_hop_importer_sort_key
from app.scanner.rule_models import finding_sort_key

REPORT_SCHEMA_VERSION = "1"
MAX_REPORT_CITATIONS = 40
MAX_CITATION_VALIDATION_ITEMS = 80
MAX_REPORT_HUMAN_REVIEW_ITEMS = 700


class _StrictFrozenModel(BaseModel):
    """报告边界统一使用 strict、frozen、extra-forbid。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


class CitationValidity(StrEnum):
    """Day 20 可自动判定的引用身份与来源有效性。"""

    VALID = "valid"
    INVALID = "invalid"


class CitationSupportStatus(StrEnum):
    """语义支持度留给后续人工抽样，不由 Day 20 自动推断。"""

    NOT_EVALUATED = "not_evaluated"


class CitationErrorType(StrEnum):
    """不包含异常正文的稳定 Citation Guard 错误类型。"""

    TRUSTED_SOURCE_INVALID = "trusted_source_invalid"
    NO_CANDIDATE = "no_candidate"
    FORGED_CHUNK_ID = "forged_chunk_id"
    CROSS_ANALYSIS_CHUNK = "cross_analysis_chunk"
    UNKNOWN_GROUP = "unknown_group"
    UNKNOWN_FINDING = "unknown_finding"
    FINDING_GROUP_MISMATCH = "finding_group_mismatch"
    DUPLICATE_CITATION = "duplicate_citation"
    URL_MISMATCH = "url_mismatch"
    REF_MISMATCH = "ref_mismatch"
    COMMIT_MISMATCH = "commit_mismatch"
    HEADING_MISMATCH = "heading_mismatch"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    SOURCE_HASH_MISMATCH = "source_hash_mismatch"
    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    TEXT_MISMATCH = "text_mismatch"
    RULE_MISMATCH = "rule_mismatch"
    QUERY_BINDING_MISSING = "query_binding_missing"
    QUERY_BINDING_MISMATCH = "query_binding_mismatch"
    KEYWORD_MISMATCH = "keyword_mismatch"


class ValidatedCitation(_StrictFrozenModel):
    """只由可信本地 chunk 构造的 current-analysis 有效引用。"""

    analysis_id: str = Field(min_length=1, max_length=128)
    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    finding_ids: tuple[str, ...] = Field(min_length=1)
    rule_id: RuleId
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    git_ref: str = Field(min_length=1)
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str = Field(min_length=1)
    heading_path: tuple[str, ...]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validity: Literal[CitationValidity.VALID] = CitationValidity.VALID
    support_status: Literal[CitationSupportStatus.NOT_EVALUATED] = (
        CitationSupportStatus.NOT_EVALUATED
    )

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.finding_ids != tuple(sorted(self.finding_ids)) or len(
            set(self.finding_ids)
        ) != len(self.finding_ids):
            raise ValueError("citation finding IDs 必须稳定排序且唯一")
        return self


class CitationValidationItem(_StrictFrozenModel):
    """一次候选校验的稳定审计结果，不保存正文或 raw query。"""

    analysis_id: str = Field(min_length=1, max_length=128)
    group_id: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    finding_ids: tuple[str, ...] = ()
    chunk_id: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    validity: CitationValidity
    error_type: CitationErrorType | None
    retry_eligible: bool

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if len(set(self.finding_ids)) != len(self.finding_ids):
            raise ValueError("citation validation finding IDs 不得重复")
        if self.validity is CitationValidity.VALID:
            if self.error_type is not None or self.retry_eligible:
                raise ValueError("valid citation 不得包含错误或 retry 标记")
        elif self.error_type is None:
            raise ValueError("invalid citation 必须包含稳定错误类型")
        return self


class CitationGuardResult(_StrictFrozenModel):
    """Citation Guard 的可信 allowlist、有效引用与审计项。"""

    schema_version: Literal["1"] = REPORT_SCHEMA_VERSION
    analysis_id: str = Field(min_length=1, max_length=128)
    trust_available: bool
    allowlisted_chunk_ids: tuple[str, ...]
    valid_citations: tuple[ValidatedCitation, ...] = Field(
        max_length=MAX_REPORT_CITATIONS
    )
    items: tuple[CitationValidationItem, ...] = Field(
        max_length=MAX_CITATION_VALIDATION_ITEMS
    )

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.allowlisted_chunk_ids != tuple(sorted(self.allowlisted_chunk_ids)):
            raise ValueError("citation allowlist 必须稳定排序")
        if len(set(self.allowlisted_chunk_ids)) != len(self.allowlisted_chunk_ids):
            raise ValueError("citation allowlist 不得重复")
        if any(
            item.chunk_id not in self.allowlisted_chunk_ids
            for item in self.valid_citations
        ):
            raise ValueError("valid citation 必须来自 current-analysis allowlist")
        citation_keys = tuple(
            (item.group_id, item.chunk_id, item.finding_ids)
            for item in self.valid_citations
        )
        if citation_keys != tuple(sorted(citation_keys)) or len(
            set(citation_keys)
        ) != len(citation_keys):
            raise ValueError("valid citations 必须稳定排序且唯一")
        if any(
            item.analysis_id != self.analysis_id
            for item in (*self.valid_citations, *self.items)
        ):
            raise ValueError("citation result analysis identity 不一致")
        if not self.trust_available and self.valid_citations:
            raise ValueError("trusted source 不可用时不得产生有效引用")
        return self


class ReportLanguage(StrEnum):
    """P0 报告只支持简体中文。"""

    ZH_CN = "zh-CN"


class ReportStatus(StrEnum):
    """继承 Day 19 terminal/degraded 状态。"""

    COMPLETED = "completed"
    DEGRADED = "degraded"


class ReportExplanationSource(StrEnum):
    """解释只能来自合法候选或确定性模板。"""

    AGENT_CANDIDATE = "agent_candidate"
    TEMPLATE_FALLBACK = "template_fallback"


class ReportCitationStatus(StrEnum):
    """finding 是否拥有已通过 validity 校验的引用。"""

    VALID = "valid"
    UNAVAILABLE = "unavailable"


class ReportExplanation(_StrictFrozenModel):
    """报告中的有来源解释。"""

    source: ReportExplanationSource
    text: str = Field(min_length=1, max_length=1200)
    model: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if self.source is ReportExplanationSource.AGENT_CANDIDATE:
            if self.model is None:
                raise ValueError("agent explanation 必须保留模型 identity")
        elif self.model is not None:
            raise ValueError("template explanation 不得声明模型")
        return self


class ReportFinding(_StrictFrozenModel):
    """原始 deterministic Finding 加解释和已验证引用的只读视图。"""

    finding_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    finding: Finding
    explanation: ReportExplanation
    citations: tuple[ValidatedCitation, ...] = Field(max_length=5)
    citation_status: ReportCitationStatus

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.finding_id != finding_identity(self.finding):
            raise ValueError("report finding identity 与 deterministic Finding 不一致")
        if any(self.finding_id not in item.finding_ids for item in self.citations):
            raise ValueError("report citation 必须绑定当前 finding")
        if any(item.rule_id is not self.finding.rule_id for item in self.citations):
            raise ValueError("report citation rule 必须绑定当前 finding rule")
        citation_ids = tuple(item.chunk_id for item in self.citations)
        if citation_ids != tuple(sorted(citation_ids)) or len(set(citation_ids)) != len(
            citation_ids
        ):
            raise ValueError("report finding citations 必须稳定排序且唯一")
        expected_status = (
            ReportCitationStatus.VALID
            if self.citations
            else ReportCitationStatus.UNAVAILABLE
        )
        if self.citation_status is not expected_status:
            raise ValueError("citation status 与 citations 不一致")
        return self


class FinalReport(_StrictFrozenModel):
    """JSON 与 Markdown renderer 共同消费的唯一最终报告真源。"""

    schema_version: Literal["1"] = REPORT_SCHEMA_VERSION
    analysis_id: str = Field(min_length=1, max_length=128)
    language: Literal[ReportLanguage.ZH_CN] = ReportLanguage.ZH_CN
    status: ReportStatus
    degraded_reason: AgentDegradedReason | None
    repo_summary: RepositorySummary
    findings: tuple[ReportFinding, ...]
    one_hop_importers: tuple[OneHopImporter, ...]
    citation_retry_count: int = Field(ge=0, le=1)
    citation_validation: tuple[CitationValidationItem, ...] = Field(
        max_length=MAX_CITATION_VALIDATION_ITEMS
    )
    human_review_items: tuple[HumanReviewItem, ...] = Field(
        max_length=MAX_REPORT_HUMAN_REVIEW_ITEMS
    )
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        finding_ids = tuple(item.finding_id for item in self.findings)
        findings = tuple(item.finding for item in self.findings)
        if findings != tuple(sorted(findings, key=finding_sort_key)):
            raise ValueError("report findings 必须保持 production 稳定顺序")
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("report findings 不得重复")
        if self.repo_summary.direct_finding_count != len(self.findings):
            raise ValueError("report finding count 与 repository summary 不一致")
        if self.repo_summary.directly_affected_files != len(
            {item.finding.relative_path for item in self.findings}
        ):
            raise ValueError("report affected file count 与 findings 不一致")
        if self.one_hop_importers != tuple(
            sorted(self.one_hop_importers, key=one_hop_importer_sort_key)
        ) or len(set(self.one_hop_importers)) != len(self.one_hop_importers):
            raise ValueError("report one-hop relations 必须稳定排序且唯一")
        if self.repo_summary.one_hop_dependent_files != len(
            {item.importer_relative_path for item in self.one_hop_importers}
        ):
            raise ValueError("report one-hop count 与 repository summary 不一致")
        if any(
            citation.analysis_id != self.analysis_id
            for item in self.findings
            for citation in item.citations
        ):
            raise ValueError("report citation analysis identity 不一致")
        if self.status is ReportStatus.COMPLETED:
            if self.degraded_reason is not None:
                raise ValueError("completed report 不得包含 degraded reason")
        elif self.degraded_reason is None:
            raise ValueError("degraded report 必须包含 degraded reason")
        known_ids = set(finding_ids)
        if any(
            not set(item.finding_ids).issubset(known_ids)
            for item in self.human_review_items
        ):
            raise ValueError("human review IDs 必须来自 report findings")
        if len(set(self.limitations)) != len(self.limitations):
            raise ValueError("report limitations 不得重复")
        return self
