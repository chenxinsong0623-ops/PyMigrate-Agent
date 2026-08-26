from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reporting import (
    CitationGuard,
    FinalReportBuilder,
    render_report_json,
    render_report_markdown,
)
from tests.reporting_fixtures import make_agent_result, make_multi_agent_result


@pytest.mark.asyncio
@pytest.mark.parametrize("include_candidate", [True, False])
async def test_json_and_markdown_are_stable_and_share_finding_citation_identity(
    include_candidate: bool,
) -> None:
    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        make_agent_result(include_candidate=include_candidate)
    )
    json_one = render_report_json(report)
    json_two = render_report_json(report)
    markdown_one = render_report_markdown(report)
    markdown_two = render_report_markdown(report)
    payload = json.loads(json_one)

    assert json_one == json_two
    assert markdown_one == markdown_two
    assert [item["finding_id"] for item in payload["findings"]] == [
        item.finding_id for item in report.findings
    ]
    for finding in report.findings:
        assert markdown_one.count(f"Finding ID：`{finding.finding_id}`") == 1
        for citation in finding.citations:
            assert citation.chunk_id in markdown_one
    assert markdown_one.count("### Finding ") == len(report.findings)


@pytest.mark.asyncio
async def test_renderer_excludes_path_query_traceback_and_secret() -> None:
    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        make_agent_result(include_candidate=False)
    )
    rendered = render_report_json(report) + render_report_markdown(report)

    assert str(Path.cwd()) not in rendered
    assert "raw_query" not in rendered
    assert "raw model output" not in rendered
    assert "Traceback (most recent call last)" not in rendered
    assert "sk-secret-token" not in rendered


@pytest.mark.asyncio
async def test_zero_finding_report_renders_without_inventing_sections() -> None:
    source = make_agent_result()
    empty = source.model_copy(
        update={
            "repo_summary": source.repo_summary.model_copy(
                update={
                    "direct_finding_count": 0,
                    "directly_affected_files": 0,
                    "one_hop_dependent_files": 0,
                }
            ),
            "findings": (),
            "finding_ids": (),
            "one_hop_importers": (),
            "ambiguous_groups": (),
            "retrieved_chunks": (),
            "retrieval_bindings": (),
            "draft_report": source.draft_report.model_copy(
                update={"selected_doc_candidates": ()}
            ),
            "reviewed_finding_ids": (),
            "tool_calls_used": 0,
            "llm_calls_used": 0,
        }
    )
    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        empty
    )

    assert report.findings == ()
    assert "### Finding " not in render_report_markdown(report)


@pytest.mark.asyncio
async def test_multi_finding_one_hop_and_human_review_render_consistently() -> None:
    report = await FinalReportBuilder(CitationGuard.from_repository(Path.cwd())).build(
        make_multi_agent_result()
    )
    payload = json.loads(render_report_json(report))
    markdown = render_report_markdown(report)

    assert len(report.findings) == 2
    assert markdown.count("### Finding ") == 2
    assert [item["finding_id"] for item in payload["findings"]] == [
        item.finding_id for item in report.findings
    ]
    assert "pkg/service.py" in markdown
    assert "pkg/models.py" in markdown
    assert payload["human_review_items"]
