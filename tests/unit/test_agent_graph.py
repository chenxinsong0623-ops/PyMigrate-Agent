from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent import (
    MAX_AGENT_TOOL_CALLS,
    MAX_AMBIGUOUS_GROUPS,
    AgentDegradedReason,
    AgentLLMError,
    AgentRunRequest,
    AgentRuntimeLimits,
    AnalysisToolContext,
    AnalysisToolSet,
    BoundedAnalysisAgent,
    CallToolDecision,
    GetFindingsCall,
    GetFindingsRequest,
    GetLocalImportersCall,
    GetLocalImportersRequest,
    GetSourceContextCall,
    GetSourceContextRequest,
    InMemoryToolAuditSink,
    LookupRuleSpecCall,
    LookupRuleSpecRequest,
    RepositorySummary,
    SearchOfficialDocsCall,
    SearchOfficialDocsRequest,
    dispatch_tool_call,
    finding_identity,
    prepare_ambiguous_groups,
)
from app.core.llm import FakeLLM, LLMClient, LLMRequest, LLMResponse
from app.retrieval.hybrid import HybridSearchResponse, HybridSearchResult
from app.scanner import (
    ASTScanner,
    FindingLocation,
    ImportGraphBuilder,
    RuleId,
    RuleScanner,
    RuleScanResult,
)
from app.security import ValidatedPythonFile, ZipGuardResult


def _validated_result(tmp_path: Path, files: dict[str, str]) -> ZipGuardResult:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    inventory: list[ValidatedPythonFile] = []
    for relative_path, source in files.items():
        payload = source.encode("utf-8")
        target = task_root.joinpath(*relative_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        inventory.append(
            ValidatedPythonFile(
                relative_path=relative_path,
                size_bytes=len(payload),
                line_count=len(source.splitlines()),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    ordered = tuple(sorted(inventory, key=lambda item: item.relative_path))
    return ZipGuardResult(
        task_root=task_root.resolve(),
        python_files=ordered,
        archive_member_count=len(ordered),
        regular_file_count=len(ordered),
        directory_count=0,
        total_uncompressed_bytes=sum(item.size_bytes for item in ordered),
        python_file_count=len(ordered),
        python_total_lines=sum(item.line_count for item in ordered),
        ignored_python_file_count=0,
        ignored_non_python_file_count=0,
    )


def _hybrid_result(identifier: int = 1) -> HybridSearchResult:
    return HybridSearchResult(
        rank=identifier,
        rrf_score=1 / (60 + identifier),
        bm25_rank=identifier,
        bm25_score=2.0,
        dense_rank=None,
        dense_score=None,
        chunk_id=f"sha256:{identifier:064x}",
        heading_path=("Changes to pydantic.BaseModel",),
        text="Fixed official migration evidence.",
        content_sha256=f"{identifier + 10:064x}",
        source_id="pydantic-v2-migration",
        source_url="https://docs.example.test/migration.md",
        git_ref="v2.13.4",
        resolved_commit_sha="a" * 40,
        source_path="docs/migration.md",
        source_snapshot_sha256="b" * 64,
    )


class OfflineRetriever:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query: str) -> HybridSearchResponse:
        self.calls.append(query)
        result = _hybrid_result()
        return HybridSearchResponse(
            query=query,
            rrf_k=60,
            results=(result,),
            top_results=(result,),
        )


class SequenceLLM:
    def __init__(
        self,
        responses: Sequence[LLMResponse | BaseException],
        *,
        repeat_last: bool = False,
    ) -> None:
        self.responses = tuple(responses)
        self.repeat_last = repeat_last
        self.calls: list[tuple[LLMRequest, float]] = []

    async def complete(
        self,
        request: LLMRequest,
        timeout_seconds: float,
    ) -> LLMResponse:
        self.calls.append((request, timeout_seconds))
        index = len(self.calls) - 1
        if index >= len(self.responses):
            if not self.repeat_last or not self.responses:
                raise AssertionError("unexpected LLM call")
            response = self.responses[-1]
        else:
            response = self.responses[index]
        if isinstance(response, BaseException):
            raise response
        return response


class WaitingLLM:
    def __init__(self) -> None:
        self.call_count = 0

    async def complete(
        self,
        request: LLMRequest,
        timeout_seconds: float,
    ) -> LLMResponse:
        del request, timeout_seconds
        self.call_count += 1
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _tool_fixture(
    tmp_path: Path,
    *,
    files: dict[str, str] | None = None,
) -> tuple[AnalysisToolSet, RuleScanResult, OfflineRetriever]:
    validated = _validated_result(
        tmp_path,
        files
        or {
            "pkg/models.py": (
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n"
            ),
            "pkg/service.py": "from .models import User\n",
        },
    )
    ast_result = ASTScanner().scan(validated)
    rule_result = RuleScanner().scan(ast_result)
    retriever = OfflineRetriever()
    tools = AnalysisToolSet(
        AnalysisToolContext(
            validated=validated,
            rule_result=rule_result,
            import_graph=ImportGraphBuilder().build(ast_result.registry),
            official_docs_retriever=retriever,
            trace_sink=InMemoryToolAuditSink(),
        ),
        timeout_seconds=0.1,
    )
    return tools, rule_result, retriever


def _summary(rule_result: RuleScanResult) -> RepositorySummary:
    affected_files = len({finding.relative_path for finding in rule_result.findings})
    return RepositorySummary(
        python_files=max(2, affected_files),
        python_loc=max(4, len(rule_result.findings)),
        direct_finding_count=len(rule_result.findings),
        directly_affected_files=affected_files,
        one_hop_dependent_files=0,
    )


def _request(
    rule_result: RuleScanResult,
    *,
    llm_review: bool = True,
) -> AgentRunRequest:
    return AgentRunRequest(
        analysis_id="analysis-day19",
        repo_summary=_summary(rule_result),
        rule_result=rule_result,
        one_hop_importers=(),
        llm_review=llm_review,
    )


def _response(payload: dict[str, object]) -> LLMResponse:
    return LLMResponse(
        model="fake-agent",
        content=json.dumps(payload, ensure_ascii=False),
        finish_reason="stop",
    )


def _finish(group_id: str, explanation: str = "需要按 v2 API 迁移。") -> LLMResponse:
    return _response(
        {
            "action": "finish_group",
            "group_id": group_id,
            "explanation": explanation,
        }
    )


def _tool_response(group_id: str, tool: str, request: dict[str, object]) -> LLMResponse:
    return _response(
        {
            "action": "call_tool",
            "group_id": group_id,
            "call": {"tool": tool, "request": request},
        }
    )


def _many_group_result(rule_result: RuleScanResult, count: int) -> RuleScanResult:
    base = rule_result.findings[0]
    findings = tuple(
        base.model_copy(
            update={
                "relative_path": f"pkg/model_{index:02d}.py",
                "location": FindingLocation(
                    start_line=index + 1,
                    start_column=0,
                    end_line=index + 1,
                    end_column=8,
                ),
            }
        )
        for index in range(count)
    )
    return RuleScanResult(findings=findings)


def test_analysis_state_models_are_strict_frozen_and_have_bounded_defaults(
    tmp_path: Path,
) -> None:
    _tools, rule_result, _retriever = _tool_fixture(tmp_path)
    request = _request(rule_result)
    limits = AgentRuntimeLimits()

    assert request.rule_result.findings == rule_result.findings
    assert limits.max_ambiguous_groups == MAX_AMBIGUOUS_GROUPS
    assert limits.max_tool_calls == MAX_AGENT_TOOL_CALLS
    assert limits.llm_timeout_seconds == 20.0
    assert limits.total_timeout_seconds == 45.0
    assert limits.max_retries == 1
    with pytest.raises(ValidationError):
        request.llm_review = False
    with pytest.raises(ValidationError):
        AgentRuntimeLimits(max_tool_calls=9)


def test_zero_finding_and_zero_ambiguity_preparation_is_valid(tmp_path: Path) -> None:
    del tmp_path
    preparation = prepare_ambiguous_groups(())

    assert preparation.groups == ()
    assert preparation.overflow_finding_ids == ()


def test_ambiguous_grouping_is_stable_content_addressed_and_capped(
    tmp_path: Path,
) -> None:
    _tools, rule_result, _retriever = _tool_fixture(tmp_path)
    many = _many_group_result(rule_result, MAX_AMBIGUOUS_GROUPS + 2)

    first = prepare_ambiguous_groups(many.findings)
    second = prepare_ambiguous_groups(tuple(reversed(many.findings)))

    assert first == second
    assert len(first.groups) == MAX_AMBIGUOUS_GROUPS
    assert len(first.overflow_finding_ids) == 2
    assert all(group.group_id.startswith("sha256:") for group in first.groups)
    assert [group.relative_path for group in first.groups] == sorted(
        group.relative_path for group in first.groups
    )


def test_finding_identity_is_stable_and_sensitive_to_location(tmp_path: Path) -> None:
    _tools, rule_result, _retriever = _tool_fixture(tmp_path)
    finding = rule_result.findings[0]
    changed = finding.model_copy(
        update={
            "location": FindingLocation(
                start_line=99,
                start_column=0,
                end_line=99,
                end_column=8,
            )
        }
    )

    assert finding_identity(finding) == finding_identity(finding)
    assert finding_identity(finding) != finding_identity(changed)


def test_large_same_rule_file_is_split_into_bounded_stable_groups(
    tmp_path: Path,
) -> None:
    _tools, rule_result, _retriever = _tool_fixture(tmp_path)
    base = rule_result.findings[0]
    findings = tuple(
        base.model_copy(
            update={
                "location": FindingLocation(
                    start_line=line,
                    start_column=0,
                    end_line=line,
                    end_column=8,
                )
            }
        )
        for line in range(1, 106)
    )

    preparation = prepare_ambiguous_groups(RuleScanResult(findings=findings).findings)

    assert [len(group.finding_ids) for group in preparation.groups] == [100, 5]
    assert preparation.overflow_finding_ids == ()


def test_low_level_state_graph_compiles_with_explicit_terminal_node(
    tmp_path: Path,
) -> None:
    tools, _rule_result, _retriever = _tool_fixture(tmp_path)
    agent = BoundedAnalysisAgent(tools=tools, llm_client=None)

    graph = agent.compiled_graph.get_graph()

    assert {"prepare", "llm_decide", "validate_action", "execute_tool"}.issubset(
        graph.nodes
    )
    assert "finalize" in graph.nodes


@pytest.mark.asyncio
async def test_graph_real_async_invoke_handles_zero_findings(tmp_path: Path) -> None:
    tools, _rule_result, _retriever = _tool_fixture(tmp_path)
    empty = RuleScanResult(findings=())

    result = await BoundedAnalysisAgent(tools=tools, llm_client=None).run(
        _request(empty)
    )

    assert result.findings == ()
    assert result.ambiguous_groups == ()
    assert result.degraded_reason is None
    assert result.terminal_status == "completed"
    assert result.llm_calls_used == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("llm_client", "llm_review", "reason"),
    [
        (None, True, AgentDegradedReason.NO_MODEL),
        (FakeLLM(), False, AgentDegradedReason.LLM_REVIEW_DISABLED),
    ],
)
async def test_no_model_and_disabled_review_use_deterministic_fallback(
    tmp_path: Path,
    llm_client: LLMClient | None,
    llm_review: bool,
    reason: AgentDegradedReason,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)

    result = await BoundedAnalysisAgent(
        tools=tools,
        llm_client=llm_client,
    ).run(_request(rule_result, llm_review=llm_review))

    assert result.findings == rule_result.findings
    assert result.degraded_reason is reason
    assert result.llm_calls_used == 0
    assert result.draft_report.explanations == ()
    assert len(result.draft_report.human_review_items) == 1


@pytest.mark.asyncio
async def test_fake_llm_finish_adds_candidate_without_changing_facts(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    fake = FakeLLM(response=_finish(group.group_id))

    result = await BoundedAnalysisAgent(tools=tools, llm_client=fake).run(
        _request(rule_result)
    )

    assert result.findings == rule_result.findings
    assert result.finding_ids == tuple(
        finding_identity(finding) for finding in rule_result.findings
    )
    assert result.draft_report.explanations[0].group_id == group.group_id
    assert result.draft_report.explanations[0].text == "需要按 v2 API 迁移。"
    assert result.reviewed_finding_ids == group.finding_ids
    assert result.llm_calls_used == 1
    assert result.retry_count == 0


@pytest.mark.asyncio
async def test_model_can_request_human_review_without_inventing_a_finding(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    fake = FakeLLM(
        response=_response(
            {
                "action": "request_human_review",
                "group_id": group.group_id,
                "reason": "需要人工确认迁移语义。",
            }
        )
    )

    result = await BoundedAnalysisAgent(tools=tools, llm_client=fake).run(
        _request(rule_result)
    )

    assert result.findings == rule_result.findings
    assert result.draft_report.explanations == ()
    assert result.draft_report.human_review_items[0].reason == "requested_by_model"
    assert result.draft_report.human_review_items[0].detail == "需要人工确认迁移语义。"
    assert result.degraded_reason is None


@pytest.mark.asyncio
async def test_llm_cannot_delete_or_rewrite_deterministic_finding(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    malicious = _response(
        {
            "action": "finish_group",
            "group_id": group.group_id,
            "explanation": "attempt",
            "findings": [],
            "severity": "low",
        }
    )
    llm = SequenceLLM((malicious, malicious))

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert result.findings == rule_result.findings
    assert result.degraded_reason is AgentDegradedReason.LLM_INVALID_RESPONSE
    assert result.retry_count == 1
    assert result.draft_report.explanations == ()


@pytest.mark.asyncio
async def test_invalid_structured_output_retries_once_then_can_succeed(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    llm = SequenceLLM(
        (
            LLMResponse(model="fake", content="not-json", finish_reason="stop"),
            _finish(group.group_id),
        )
    )

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert result.degraded_reason is None
    assert result.retry_count == 1
    assert result.llm_calls_used == 2
    assert result.reviewed_finding_ids == group.finding_ids
    assert len(set(result.reviewed_finding_ids)) == len(result.reviewed_finding_ids)


@pytest.mark.asyncio
async def test_wrong_group_identity_is_retryable_structured_failure(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    wrong_group = "sha256:" + "f" * 64
    llm = SequenceLLM((_finish(wrong_group), _finish(group.group_id)))

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert result.degraded_reason is None
    assert result.retry_count == 1
    assert result.llm_calls_used == 2
    assert result.draft_report.explanations[0].group_id == group.group_id


@pytest.mark.asyncio
async def test_arbitrary_tool_name_is_rejected_before_dispatch(tmp_path: Path) -> None:
    tools, rule_result, retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    unsafe = _tool_response(group.group_id, "run_shell", {"command": "whoami"})
    llm = SequenceLLM((unsafe, unsafe))

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert result.degraded_reason is AgentDegradedReason.LLM_INVALID_RESPONSE
    assert result.tool_calls_used == 0
    assert retriever.calls == []


@pytest.mark.asyncio
async def test_explicit_dispatcher_calls_each_of_the_five_day18_tools(
    tmp_path: Path,
) -> None:
    tools, rule_result, retriever = _tool_fixture(tmp_path)
    group_id = prepare_ambiguous_groups(rule_result.findings).groups[0].group_id
    calls = (
        GetFindingsCall(tool="get_findings", request=GetFindingsRequest()),
        GetSourceContextCall(
            tool="get_source_context",
            request=GetSourceContextRequest(
                path="pkg/models.py",
                line=2,
                radius=1,
            ),
        ),
        GetLocalImportersCall(
            tool="get_local_importers",
            request=GetLocalImportersRequest(path="pkg/models.py"),
        ),
        SearchOfficialDocsCall(
            tool="search_official_docs",
            request=SearchOfficialDocsRequest(query="root model migration", top_k=1),
        ),
        LookupRuleSpecCall(
            tool="lookup_rule_spec",
            request=LookupRuleSpecRequest(rule_id=RuleId.PYDANTIC_V1_ROOT_MODEL.value),
        ),
    )

    results = [
        await dispatch_tool_call(
            tools,
            CallToolDecision(
                action="call_tool",
                group_id=group_id,
                call=call,
            ),
        )
        for call in calls
    ]

    assert len(results) == 5
    assert retriever.calls == ["root model migration"]


@pytest.mark.asyncio
async def test_at_most_eight_groups_mean_a_ninth_tool_call_is_never_made(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    many = _many_group_result(rule_result, MAX_AMBIGUOUS_GROUPS + 1)
    groups = prepare_ambiguous_groups(many.findings).groups
    llm = SequenceLLM(
        tuple(_tool_response(group.group_id, "get_findings", {}) for group in groups),
    )
    actual_calls = 0
    original = tools.get_findings

    async def counted(request: GetFindingsRequest):
        nonlocal actual_calls
        actual_calls += 1
        return await original(request)

    monkeypatch.setattr(tools, "get_findings", counted)

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(_request(many))

    assert actual_calls == MAX_AGENT_TOOL_CALLS
    assert result.tool_calls_used == MAX_AGENT_TOOL_CALLS
    assert result.llm_calls_used == MAX_AMBIGUOUS_GROUPS
    assert result.degraded_reason is AgentDegradedReason.AMBIGUOUS_GROUP_LIMIT
    assert len(result.findings) == MAX_AMBIGUOUS_GROUPS + 1


@pytest.mark.asyncio
async def test_tightened_tool_limit_stops_before_the_next_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    many = _many_group_result(rule_result, 2)
    groups = prepare_ambiguous_groups(many.findings).groups
    llm = SequenceLLM(
        tuple(_tool_response(group.group_id, "get_findings", {}) for group in groups)
    )
    actual_calls = 0
    original = tools.get_findings

    async def counted(request: GetFindingsRequest):
        nonlocal actual_calls
        actual_calls += 1
        return await original(request)

    monkeypatch.setattr(tools, "get_findings", counted)
    limits = AgentRuntimeLimits(max_tool_calls=1)

    result = await BoundedAnalysisAgent(
        tools=tools,
        llm_client=llm,
        limits=limits,
    ).run(_request(many))

    assert actual_calls == 1
    assert result.degraded_reason is AgentDegradedReason.TOOL_CALL_LIMIT
    assert result.tool_calls_used == 1


@pytest.mark.asyncio
async def test_search_tool_result_becomes_unvalidated_day20_candidate(
    tmp_path: Path,
) -> None:
    tools, rule_result, retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    llm = SequenceLLM(
        (
            _tool_response(
                group.group_id,
                "search_official_docs",
                {"query": "root model migration", "top_k": 1},
            ),
        )
    )

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert retriever.calls == ["root model migration"]
    assert result.retrieved_chunks[0].chunk_id == _hybrid_result().chunk_id
    candidate = result.draft_report.selected_doc_candidates[0]
    assert candidate.validated is False
    assert candidate.analysis_id == result.analysis_id
    assert candidate.group_id == group.group_id
    assert result.retrieval_bindings[0].group_id == group.group_id
    assert result.retrieval_bindings[0].rule_id is group.rule_id
    assert result.retrieval_bindings[0].finding_ids == group.finding_ids
    assert result.retrieval_bindings[0].matched_query_terms == ("root model",)
    assert result.retrieval_bindings[0].chunk_ids == (candidate.chunk_id,)
    assert "citation_valid" not in result.model_dump(mode="json")


@pytest.mark.asyncio
async def test_importer_tool_observation_never_becomes_a_new_finding(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    llm = SequenceLLM(
        (
            _tool_response(
                group.group_id,
                "get_local_importers",
                {"path": "pkg/models.py"},
            ),
        )
    )

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert result.findings == rule_result.findings
    assert {finding.relative_path for finding in result.findings} == {"pkg/models.py"}
    assert all(finding.relative_path != "pkg/service.py" for finding in result.findings)


@pytest.mark.asyncio
async def test_llm_timeout_is_real_retries_once_and_falls_back(tmp_path: Path) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    llm = WaitingLLM()
    limits = AgentRuntimeLimits(
        llm_timeout_seconds=0.01,
        total_timeout_seconds=0.1,
    )
    started = time.monotonic()

    result = await BoundedAnalysisAgent(
        tools=tools,
        llm_client=llm,
        limits=limits,
    ).run(_request(rule_result))

    elapsed = time.monotonic() - started
    assert elapsed < 0.1
    assert llm.call_count == 2
    assert result.retry_count == 1
    assert result.degraded_reason is AgentDegradedReason.LLM_TIMEOUT
    assert result.findings == rule_result.findings


@pytest.mark.asyncio
async def test_day18_tool_timeout_is_safe_and_never_triggers_llm_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    llm = SequenceLLM((_tool_response(group.group_id, "get_findings", {}),))

    async def wait_forever(_request: GetFindingsRequest):
        await asyncio.Event().wait()

    monkeypatch.setattr(tools, "_get_findings_impl", wait_forever)

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert result.degraded_reason is AgentDegradedReason.TOOL_ERROR
    assert result.validation_errors[-1].error_type == "timeout"
    assert result.retry_count == 0
    assert len(llm.calls) == 1
    assert result.findings == rule_result.findings


@pytest.mark.asyncio
async def test_agent_total_timeout_wraps_the_entire_graph(tmp_path: Path) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    llm = WaitingLLM()
    limits = AgentRuntimeLimits(
        llm_timeout_seconds=0.08,
        total_timeout_seconds=0.015,
    )
    started = time.monotonic()

    result = await BoundedAnalysisAgent(
        tools=tools,
        llm_client=llm,
        limits=limits,
    ).run(_request(rule_result))

    elapsed = time.monotonic() - started
    assert elapsed < 0.08
    assert result.degraded_reason is AgentDegradedReason.AGENT_TIMEOUT
    assert result.findings == rule_result.findings
    assert result.tool_calls_used == 0


@pytest.mark.asyncio
async def test_typed_llm_error_retries_once_then_falls_back(tmp_path: Path) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    llm = SequenceLLM(
        (
            AgentLLMError("transient"),
            AgentLLMError("transient"),
        )
    )

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert result.degraded_reason is AgentDegradedReason.LLM_ERROR
    assert result.retry_count == 1
    assert result.llm_calls_used == 2
    assert result.findings == rule_result.findings


@pytest.mark.asyncio
async def test_programmer_error_is_not_swallowed_as_model_fallback(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    llm = SequenceLLM((RuntimeError("programmer bug"),))

    with pytest.raises(RuntimeError, match="programmer bug"):
        await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
            _request(rule_result)
        )


@pytest.mark.asyncio
async def test_step_limit_is_product_state_not_only_recursion_limit(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    llm = SequenceLLM((_finish(group.group_id),))

    result = await BoundedAnalysisAgent(
        tools=tools,
        llm_client=llm,
        limits=AgentRuntimeLimits(max_steps=1),
    ).run(_request(rule_result))

    assert len(result.agent_steps) == 1
    assert result.degraded_reason is AgentDegradedReason.STEP_LIMIT
    assert result.llm_calls_used == 0
    assert result.findings == rule_result.findings


@pytest.mark.asyncio
async def test_tool_safety_error_is_not_retried(tmp_path: Path) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    llm = SequenceLLM(
        (
            _tool_response(
                group.group_id,
                "get_source_context",
                {"path": "pkg/unknown.py", "line": 1, "radius": 0},
            ),
        )
    )

    result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(
        _request(rule_result)
    )

    assert len(llm.calls) == 1
    assert result.retry_count == 0
    assert result.degraded_reason is AgentDegradedReason.TOOL_ERROR
    assert result.validation_errors[-1].error_type == "unknown_path"


@pytest.mark.asyncio
async def test_two_no_model_runs_have_identical_business_results(
    tmp_path: Path,
) -> None:
    tools, rule_result, _retriever = _tool_fixture(tmp_path)
    agent = BoundedAnalysisAgent(tools=tools, llm_client=None)

    first = await agent.run(_request(rule_result))
    second = await agent.run(_request(rule_result))

    assert first == second
    assert "deadline" not in first.model_dump(mode="json")
    assert "duration" not in first.model_dump(mode="json")


@pytest.mark.asyncio
async def test_two_agent_instances_do_not_share_mutable_analysis_state(
    tmp_path: Path,
) -> None:
    tools_one, rule_result, _retriever = _tool_fixture(tmp_path / "one")
    tools_two, _same_rules, _retriever = _tool_fixture(tmp_path / "two")
    group = prepare_ambiguous_groups(rule_result.findings).groups[0]
    with_model = BoundedAnalysisAgent(
        tools=tools_one,
        llm_client=FakeLLM(response=_finish(group.group_id)),
    )
    without_model = BoundedAnalysisAgent(tools=tools_two, llm_client=None)

    model_result, fallback_result = await asyncio.gather(
        with_model.run(_request(rule_result)),
        without_model.run(_request(rule_result)),
    )

    assert len(model_result.draft_report.explanations) == 1
    assert model_result.draft_report.human_review_items == ()
    assert fallback_result.draft_report.explanations == ()
    assert len(fallback_result.draft_report.human_review_items) == 1
