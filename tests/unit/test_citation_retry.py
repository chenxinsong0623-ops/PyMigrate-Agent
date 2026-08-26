from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent import AgentLLMError
from app.core.llm import LLMRequest, LLMResponse
from app.reporting import CitationGuard, FinalReportBuilder
from tests.reporting_fixtures import make_agent_result


class RetryLLM:
    def __init__(self, responses: tuple[dict[str, object], ...]) -> None:
        self.responses = responses
        self.calls: list[tuple[LLMRequest, float]] = []

    async def complete(
        self, request: LLMRequest, timeout_seconds: float
    ) -> LLMResponse:
        self.calls.append((request, timeout_seconds))
        payload = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        return LLMResponse(
            model="fake-citation-retry",
            content=json.dumps(payload),
            finish_reason="stop",
        )


class FailingRetryLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[LLMRequest, float]] = []

    async def complete(
        self, request: LLMRequest, timeout_seconds: float
    ) -> LLMResponse:
        self.calls.append((request, timeout_seconds))
        raise AgentLLMError("provider detail must not enter report")


def _valid_retry_payload(source) -> dict[str, object]:
    group = source.ambiguous_groups[0]
    return {
        "action": "select_citation",
        "group_id": group.group_id,
        "finding_ids": list(group.finding_ids),
        "chunk_id": source.retrieved_chunks[0].chunk_id,
    }


@pytest.mark.asyncio
async def test_first_invalid_retry_once_then_valid() -> None:
    source = make_agent_result(include_candidate=False)
    llm = RetryLLM((_valid_retry_payload(source),))

    report = await FinalReportBuilder(
        CitationGuard.from_repository(Path.cwd()),
        llm_client=llm,
        llm_review=True,
    ).build(source)

    assert report.citation_retry_count == 1
    assert len(llm.calls) == 1
    assert (
        report.findings[0].citations[0].chunk_id == source.retrieved_chunks[0].chunk_id
    )


@pytest.mark.asyncio
async def test_retry_still_invalid_falls_back_and_never_calls_third_time() -> None:
    source = make_agent_result(include_candidate=False)
    invalid = _valid_retry_payload(source) | {"chunk_id": "sha256:" + "f" * 64}
    llm = RetryLLM((invalid, invalid, invalid))

    report = await FinalReportBuilder(
        CitationGuard.from_repository(Path.cwd()),
        llm_client=llm,
        llm_review=True,
    ).build(source)

    assert report.citation_retry_count == 1
    assert len(llm.calls) == 1
    assert report.findings[0].citations == ()
    assert report.findings[0].citation_status == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(("llm", "enabled"), [(None, True), (RetryLLM(({},)), False)])
async def test_no_model_or_disabled_review_never_retries(llm, enabled: bool) -> None:
    source = make_agent_result(include_candidate=False)

    report = await FinalReportBuilder(
        CitationGuard.from_repository(Path.cwd()),
        llm_client=llm,
        llm_review=enabled,
    ).build(source)

    assert report.citation_retry_count == 0
    assert not getattr(llm, "calls", [])
    assert report.findings[0].citations == ()


@pytest.mark.asyncio
async def test_expected_llm_failure_retries_once_then_uses_template() -> None:
    source = make_agent_result(include_candidate=False)
    llm = FailingRetryLLM()

    report = await FinalReportBuilder(
        CitationGuard.from_repository(Path.cwd()),
        llm_client=llm,
    ).build(source)

    assert report.citation_retry_count == 1
    assert len(llm.calls) == 1
    assert llm.calls[0][1] <= 20.0
    assert report.findings[0].citations == ()


@pytest.mark.asyncio
async def test_no_current_allowlist_never_calls_retry_model() -> None:
    source = make_agent_result(include_candidate=False)
    no_retrieval = source.model_copy(
        update={"retrieved_chunks": (), "retrieval_bindings": ()}
    )
    llm = RetryLLM((_valid_retry_payload(source),))

    report = await FinalReportBuilder(
        CitationGuard.from_repository(Path.cwd()),
        llm_client=llm,
    ).build(no_retrieval)

    assert report.citation_retry_count == 0
    assert llm.calls == []
    assert report.findings[0].citations == ()


@pytest.mark.asyncio
async def test_trusted_source_failure_never_calls_retry_model(tmp_path: Path) -> None:
    source = make_agent_result()
    llm = RetryLLM((_valid_retry_payload(source),))

    report = await FinalReportBuilder(
        CitationGuard.from_repository(tmp_path),
        llm_client=llm,
    ).build(source)

    assert report.citation_retry_count == 0
    assert llm.calls == []
    assert report.findings[0].citations == ()


@pytest.mark.asyncio
async def test_unknown_group_safety_error_never_calls_retry_model() -> None:
    source = make_agent_result()
    candidate = source.draft_report.selected_doc_candidates[0].model_copy(
        update={"group_id": "sha256:" + "e" * 64}
    )
    unsafe = source.model_copy(
        update={
            "draft_report": source.draft_report.model_copy(
                update={"selected_doc_candidates": (candidate,)}
            )
        }
    )
    llm = RetryLLM((_valid_retry_payload(source),))

    report = await FinalReportBuilder(
        CitationGuard.from_repository(Path.cwd()),
        llm_client=llm,
    ).build(unsafe)

    assert report.citation_retry_count == 0
    assert llm.calls == []
