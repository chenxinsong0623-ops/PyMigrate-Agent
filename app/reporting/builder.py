"""从 Day 19 稳定结果构造 Day 20 单一 typed final report。"""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.agent import (
    AgentLLMError,
    AgentRunResult,
    AgentTerminalStatus,
    HumanReviewItem,
    SelectedDocCandidate,
)
from app.core.llm import LLMClient, LLMClientError, LLMMessage, LLMRequest
from app.scanner import get_rule_spec

from .citation import CitationGuard
from .models import (
    CitationGuardResult,
    CitationValidity,
    FinalReport,
    ReportCitationStatus,
    ReportExplanation,
    ReportExplanationSource,
    ReportFinding,
    ReportLanguage,
    ReportStatus,
)

MAX_CITATION_RETRY_TIMEOUT_SECONDS = 20.0
_UNSAFE_EXPLANATION_PATTERNS = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"(?i)(?:api[_-]?key|token|secret)\s*[:=]"),
    re.compile(r"(?i)sk-[a-z0-9_-]{8,}"),
    re.compile(r"(?i)(?:[A-Z]:\\|/home/|/Users/|/tmp/)"),
)


class _RetrySelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["select_citation"]
    group_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    finding_ids: tuple[str, ...] = Field(min_length=1)
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


_RETRY_ADAPTER: TypeAdapter[_RetrySelection] = TypeAdapter(_RetrySelection)


class FinalReportBuilder:
    """引用先 fail-closed 校验，再以确定性方式构造最终报告。"""

    def __init__(
        self,
        citation_guard: CitationGuard,
        *,
        llm_client: LLMClient | None = None,
        llm_review: bool = True,
    ) -> None:
        if not isinstance(citation_guard, CitationGuard):
            raise TypeError("citation_guard 必须是 CitationGuard")
        if llm_client is not None and not isinstance(llm_client, LLMClient):
            raise TypeError("llm_client 必须满足 LLMClient protocol")
        if not isinstance(llm_review, bool):
            raise TypeError("llm_review 必须是 bool")
        self._citation_guard = citation_guard
        self._llm_client = llm_client
        self._llm_review = llm_review

    async def build(self, source: AgentRunResult) -> FinalReport:
        """即使模型、引用或 Day 19 已降级，也返回完整 deterministic report。"""
        if not isinstance(source, AgentRunResult):
            raise TypeError("source 必须是 AgentRunResult")
        checked = self._citation_guard.validate(source)
        retry_count = 0
        if self._should_retry(checked):
            retry_count = 1
            retried = await self._retry_once(source, checked)
            if retried is not None:
                source = retried
                checked = self._citation_guard.validate(source)

        citations_by_finding: dict[str, list] = defaultdict(list)
        for citation in checked.valid_citations:
            for finding_id in citation.finding_ids:
                citations_by_finding[finding_id].append(citation)

        explanation_by_finding = _validated_explanations(source)
        report_findings = tuple(
            ReportFinding(
                finding_id=finding_id,
                finding=finding,
                explanation=explanation_by_finding.get(finding_id)
                or _template_explanation(finding.rule_id, finding.old_api),
                citations=tuple(
                    sorted(
                        citations_by_finding.get(finding_id, ()),
                        key=lambda item: item.chunk_id,
                    )
                ),
                citation_status=(
                    ReportCitationStatus.VALID
                    if citations_by_finding.get(finding_id)
                    else ReportCitationStatus.UNAVAILABLE
                ),
            )
            for finding_id, finding in zip(
                source.finding_ids,
                source.findings,
                strict=True,
            )
        )
        human_review = _merged_human_review(source, report_findings)
        status = (
            ReportStatus.COMPLETED
            if source.terminal_status is AgentTerminalStatus.COMPLETED
            else ReportStatus.DEGRADED
        )
        return FinalReport(
            analysis_id=source.analysis_id,
            language=ReportLanguage.ZH_CN,
            status=status,
            degraded_reason=source.degraded_reason,
            repo_summary=source.repo_summary,
            findings=report_findings,
            one_hop_importers=source.one_hop_importers,
            citation_retry_count=retry_count,
            citation_validation=checked.items,
            human_review_items=human_review,
            limitations=(
                "引用有效性仅验证来源、身份、当前分析隔离与关键词条件。",
                "引用语义支持度尚未人工评估。",
                "报告不修改用户源码，也不生成迁移补丁。",
            ),
        )

    def _should_retry(self, checked: CitationGuardResult) -> bool:
        invalid_items = tuple(
            item for item in checked.items if item.validity is CitationValidity.INVALID
        )
        return bool(
            checked.trust_available
            and checked.allowlisted_chunk_ids
            and self._llm_review
            and self._llm_client is not None
            and invalid_items
            and all(item.retry_eligible for item in invalid_items)
        )

    async def _retry_once(
        self,
        source: AgentRunResult,
        checked: CitationGuardResult,
    ) -> AgentRunResult | None:
        retry_item = next(
            item
            for item in checked.items
            if item.retry_eligible and item.group_id is not None
        )
        group = next(
            item
            for item in source.ambiguous_groups
            if item.group_id == retry_item.group_id
        )
        finding_by_id = dict(zip(source.finding_ids, source.findings, strict=True))
        chunk_by_id = {item.chunk_id: item for item in source.retrieved_chunks}
        payload = {
            "action_required": "select one citation from current_analysis_allowlist",
            "analysis_id": source.analysis_id,
            "group": {
                "group_id": group.group_id,
                "rule_id": group.rule_id.value,
                "finding_ids": list(group.finding_ids),
                "old_apis": [finding_by_id[item].old_api for item in group.finding_ids],
            },
            "allowed_chunks": [
                {
                    "chunk_id": chunk_id,
                    "heading_path": list(chunk_by_id[chunk_id].heading_path),
                }
                for chunk_id in checked.allowlisted_chunk_ids
            ],
        }
        request = LLMRequest(
            messages=(
                LLMMessage(
                    role="system",
                    content=(
                        "你只能从 current-analysis allowlist 选择一个 chunk；"
                        "不得修改 group 或 finding identity。只返回严格 JSON。"
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
        )
        try:
            response = await asyncio.wait_for(
                self._llm_client.complete(
                    request,
                    timeout_seconds=MAX_CITATION_RETRY_TIMEOUT_SECONDS,
                ),
                timeout=MAX_CITATION_RETRY_TIMEOUT_SECONDS,
            )
            selection = _RETRY_ADAPTER.validate_json(response.content, strict=True)
        except (
            AgentLLMError,
            LLMClientError,
            TimeoutError,
            ValidationError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None
        if (
            selection.group_id != group.group_id
            or selection.finding_ids != group.finding_ids
        ):
            return None
        candidate = SelectedDocCandidate(
            analysis_id=source.analysis_id,
            group_id=selection.group_id,
            finding_ids=selection.finding_ids,
            chunk_id=selection.chunk_id,
        )
        retained = tuple(
            item
            for item in source.draft_report.selected_doc_candidates
            if item.group_id != group.group_id
        )
        draft = source.draft_report.model_copy(
            update={"selected_doc_candidates": (*retained, candidate)}
        )
        return source.model_copy(update={"draft_report": draft})


def _validated_explanations(
    source: AgentRunResult,
) -> dict[str, ReportExplanation]:
    group_by_id = {item.group_id: item for item in source.ambiguous_groups}
    result: dict[str, ReportExplanation] = {}
    for candidate in source.draft_report.explanations:
        group = group_by_id.get(candidate.group_id)
        if (
            group is None
            or candidate.finding_ids != group.finding_ids
            or not _safe_explanation(candidate.text)
        ):
            continue
        explanation = ReportExplanation(
            source=ReportExplanationSource.AGENT_CANDIDATE,
            text=candidate.text,
            model=candidate.model,
        )
        for finding_id in group.finding_ids:
            result.setdefault(finding_id, explanation)
    return result


def _safe_explanation(text: str) -> bool:
    return all(pattern.search(text) is None for pattern in _UNSAFE_EXPLANATION_PATTERNS)


def _template_explanation(rule_id, old_api: str) -> ReportExplanation:
    spec = get_rule_spec(rule_id)
    return ReportExplanation(
        source=ReportExplanationSource.TEMPLATE_FALLBACK,
        text=(
            f"{spec.summary}{spec.scope}检测到旧 API `{old_api}`。"
            "当前未提供未经验证的模型迁移说明，请结合已固定的官方文档人工确认。"
        ),
        model=None,
    )


def _merged_human_review(
    source: AgentRunResult,
    report_findings: tuple[ReportFinding, ...],
) -> tuple[HumanReviewItem, ...]:
    items = list(source.draft_report.human_review_items)
    group_by_finding: dict[str, str | None] = {}
    for group in source.ambiguous_groups:
        for finding_id in group.finding_ids:
            group_by_finding[finding_id] = group.group_id
    for item in report_findings:
        if item.explanation.source is ReportExplanationSource.TEMPLATE_FALLBACK:
            items.append(
                HumanReviewItem(
                    group_id=group_by_finding.get(item.finding_id),
                    finding_ids=(item.finding_id,),
                    reason="explanation_template_fallback",
                )
            )
        if item.citation_status is ReportCitationStatus.UNAVAILABLE:
            items.append(
                HumanReviewItem(
                    group_id=group_by_finding.get(item.finding_id),
                    finding_ids=(item.finding_id,),
                    reason="citation_unavailable",
                )
            )
        else:
            items.append(
                HumanReviewItem(
                    group_id=group_by_finding.get(item.finding_id),
                    finding_ids=(item.finding_id,),
                    reason="citation_support_not_evaluated",
                )
            )
    unique: dict[tuple[str | None, tuple[str, ...], str], HumanReviewItem] = {}
    for item in items:
        unique.setdefault((item.group_id, item.finding_ids, item.reason), item)
    return tuple(
        unique[key]
        for key in sorted(
            unique, key=lambda value: (value[0] or "", value[1], value[2])
        )
    )
