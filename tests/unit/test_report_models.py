from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent import AgentDegradedReason, ExplanationCandidate
from app.reporting import (
    CitationGuard,
    FinalReportBuilder,
    ReportExplanationSource,
    ReportLanguage,
    ReportStatus,
)
from tests.reporting_fixtures import make_agent_result


@pytest.mark.asyncio
async def test_typed_report_preserves_findings_and_one_hop_exactly() -> None:
    source = make_agent_result()
    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        source
    )

    assert tuple(item.finding for item in report.findings) == source.findings
    assert tuple(item.finding_id for item in report.findings) == source.finding_ids
    assert report.one_hop_importers == source.one_hop_importers
    assert report.language is ReportLanguage.ZH_CN
    assert report.status is ReportStatus.COMPLETED
    assert (
        report.findings[0].explanation.source
        is ReportExplanationSource.TEMPLATE_FALLBACK
    )


@pytest.mark.asyncio
async def test_degraded_no_model_result_still_builds_deterministic_report() -> None:
    source = make_agent_result(degraded_reason=AgentDegradedReason.NO_MODEL)
    builder = FinalReportBuilder(CitationGuard.from_repository(Path.cwd()))

    first = await builder.build(source)
    second = await builder.build(source)

    assert first == second
    assert first.status is ReportStatus.DEGRADED
    assert first.degraded_reason == "no_model"
    assert first.findings == second.findings


@pytest.mark.asyncio
async def test_report_models_are_frozen_extra_forbid_and_language_is_zh_cn() -> None:
    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        make_agent_result()
    )

    with pytest.raises(ValidationError):
        report.language = "en"
    with pytest.raises(ValidationError):
        type(report)(**report.model_dump(mode="python"), raw_query="secret")


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", list(AgentDegradedReason))
async def test_every_day19_degraded_reason_still_builds_report(
    reason: AgentDegradedReason,
) -> None:
    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        make_agent_result(degraded_reason=reason)
    )

    assert report.status is ReportStatus.DEGRADED
    assert report.degraded_reason is reason
    assert len(report.findings) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected_source"),
    [
        (
            "该候选解释仅描述当前旧 API，需人工确认迁移方式。",
            ReportExplanationSource.AGENT_CANDIDATE,
        ),
        (
            "Traceback (most recent call last): secret",
            ReportExplanationSource.TEMPLATE_FALLBACK,
        ),
    ],
)
async def test_only_identity_bound_and_safe_explanation_candidate_is_used(
    text: str,
    expected_source: ReportExplanationSource,
) -> None:
    source = make_agent_result()
    group = source.ambiguous_groups[0]
    explanation = ExplanationCandidate(
        group_id=group.group_id,
        finding_ids=group.finding_ids,
        text=text,
        model="fake-agent",
    )
    with_explanation = source.model_copy(
        update={
            "draft_report": source.draft_report.model_copy(
                update={"explanations": (explanation,)}
            )
        }
    )

    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        with_explanation
    )

    assert report.findings[0].explanation.source is expected_source
