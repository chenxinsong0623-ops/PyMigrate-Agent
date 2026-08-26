"""Day 21 HTTP 与应用服务共享的严格业务模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent import AgentDegradedReason, HumanReviewItem, RepositorySummary
from app.reporting import (
    CitationValidationItem,
    ReportFinding,
    ReportStatus,
)
from app.scanner import OneHopImporter, RuleSpec

ANALYSIS_API_SCHEMA_VERSION = "1"


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


class AnalysisTimings(_StrictFrozenModel):
    """只记录稳定阶段名与毫秒数；未调用阶段严格为零。"""

    extract: int = Field(ge=0)
    scan: int = Field(ge=0)
    retrieve: int = Field(ge=0)
    llm: int = Field(ge=0)
    total: int = Field(ge=0)


class AnalysisSummary(_StrictFrozenModel):
    """从 FinalReport 直接计数的业务摘要。"""

    high: int = Field(ge=0)
    medium: int = Field(ge=0)
    low: int = Field(ge=0)
    human_review: int = Field(ge=0)


class AnalysisResponse(_StrictFrozenModel):
    """独立于 Day 20 schema、但只消费 Day 20 真源的 API envelope。"""

    schema_version: Literal["1"] = ANALYSIS_API_SCHEMA_VERSION
    analysis_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    status: ReportStatus
    degraded_reason: AgentDegradedReason | None
    scanner_version: str = Field(min_length=1, max_length=64)
    document_ref: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    report_language: Literal["zh-CN"] = "zh-CN"
    repository: RepositorySummary
    summary: AnalysisSummary
    findings: tuple[ReportFinding, ...]
    one_hop_importers: tuple[OneHopImporter, ...]
    citation_retry_count: int = Field(ge=0, le=1)
    citation_validation: tuple[CitationValidationItem, ...]
    human_review_items: tuple[HumanReviewItem, ...]
    limitations: tuple[str, ...]
    timings_ms: AnalysisTimings
    created_at_utc: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_report_view(self) -> AnalysisResponse:
        if self.repository.direct_finding_count != len(self.findings):
            raise ValueError("API finding count 与 repository summary 不一致")
        if self.summary.high + self.summary.medium + self.summary.low != len(
            self.findings
        ):
            raise ValueError("API severity summary 与 findings 不一致")
        if self.summary.human_review != len(self.human_review_items):
            raise ValueError("API human-review summary 与列表不一致")
        if self.status is ReportStatus.COMPLETED and self.degraded_reason is not None:
            raise ValueError("completed API response 不得包含降级原因")
        if self.status is ReportStatus.DEGRADED and self.degraded_reason is None:
            raise ValueError("degraded API response 必须包含降级原因")
        return self


class ZipLimitsResponse(_StrictFrozenModel):
    max_upload_bytes: int = Field(gt=0)
    max_zip_members: int = Field(gt=0)
    max_member_uncompressed_bytes: int = Field(gt=0)
    max_total_uncompressed_bytes: int = Field(gt=0)
    max_compression_ratio: int = Field(gt=0)
    max_python_files: int = Field(gt=0)
    max_python_loc: int = Field(gt=0)


class AgentLimitsResponse(_StrictFrozenModel):
    max_ambiguous_groups: int = Field(gt=0)
    max_agent_tool_calls: int = Field(gt=0)
    max_agent_steps: int = Field(gt=0)
    max_llm_timeout_seconds: float = Field(gt=0)
    max_agent_timeout_seconds: float = Field(gt=0)
    max_agent_retries: int = Field(ge=0)


class RulesResponse(_StrictFrozenModel):
    schema_version: Literal["1"] = ANALYSIS_API_SCHEMA_VERSION
    report_languages: tuple[Literal["zh-CN"], ...] = ("zh-CN",)
    rules: tuple[RuleSpec, ...]
    zip_limits: ZipLimitsResponse
    agent_limits: AgentLimitsResponse
