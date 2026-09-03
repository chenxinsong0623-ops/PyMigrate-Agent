"""基于 low-level StateGraph 的有界、可降级 Day 19 Agent。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from app.agent.graph_models import (
    MAX_AGENT_VALIDATION_ERRORS,
    MAX_FINDINGS_PER_GROUP,
    AgentDecision,
    AgentDegradedReason,
    AgentDraft,
    AgentNode,
    AgentRunRequest,
    AgentRunResult,
    AgentRuntimeLimits,
    AgentStep,
    AgentStepStatus,
    AgentTerminalStatus,
    AgentValidationError,
    AmbiguousGroup,
    CallToolDecision,
    ExplanationCandidate,
    FinishGroupDecision,
    HumanReviewItem,
    RepositorySummary,
    RequestHumanReviewDecision,
    RetrievalBinding,
    SearchOfficialDocsCall,
    SelectedDocCandidate,
    finding_identity,
    parse_agent_decision,
    prepare_ambiguous_groups,
)
from app.agent.tool_models import (
    AgentToolError,
    GetFindingsResult,
    GetLocalImportersResult,
    GetSourceContextResult,
    LookupRuleSpecResult,
    OfficialDocChunk,
    SearchOfficialDocsResult,
    ToolName,
)
from app.agent.tools import AnalysisToolSet
from app.core.llm import LLMClient, LLMClientError, LLMMessage, LLMRequest
from app.scanner import Finding, OneHopImporter, get_rule_spec

_SYSTEM_PROMPT = """你是 MigrationLens 的有界解释编排器。
AST findings 是不可删除、不可新增、不可改写的确定性事实。
你只能选择五个只读工具、完成当前组的解释候选，或请求人工复核。
不要编造 finding、引用有效性或工具。只返回一个严格 JSON decision。"""

AgentToolResult = (
    GetFindingsResult
    | GetSourceContextResult
    | GetLocalImportersResult
    | SearchOfficialDocsResult
    | LookupRuleSpecResult
)


class AgentLLMError(LLMClientError):
    """LLM adapter 应映射的预期调用失败；消息不进入 Agent state。"""


class AnalysisState(TypedDict):
    """LangGraph 内部 mutable state；公共 action/result 仍使用 strict model。"""

    analysis_id: str
    repo_summary: RepositorySummary
    findings: tuple[Finding, ...]
    finding_ids: tuple[str, ...]
    one_hop_importers: tuple[OneHopImporter, ...]
    ambiguous_groups: tuple[AmbiguousGroup, ...]
    overflow_finding_ids: tuple[str, ...]
    retrieved_chunks: tuple[OfficialDocChunk, ...]
    retrieval_bindings: tuple[RetrievalBinding, ...]
    agent_steps: tuple[AgentStep, ...]
    draft_report: AgentDraft
    validation_errors: tuple[AgentValidationError, ...]
    degraded_reason: AgentDegradedReason | None
    tool_calls_used: int
    llm_calls_used: int
    reviewed_finding_ids: tuple[str, ...]
    retry_count: int
    llm_review: bool
    current_group_index: int
    pending_decision: AgentDecision | None
    pending_model: str | None
    finished: bool
    started_monotonic: float
    deadline_monotonic: float


async def dispatch_tool_call(
    tools: AnalysisToolSet,
    decision: CallToolDecision,
) -> AgentToolResult:
    """只用显式 isinstance mapping 调用五工具；不使用 model-supplied getattr。"""
    if not isinstance(tools, AnalysisToolSet):
        raise TypeError("tools 必须是 AnalysisToolSet")
    call = decision.call
    from app.agent.graph_models import (  # noqa: PLC0415 - 避免重复 runtime alias
        GetFindingsCall,
        GetLocalImportersCall,
        GetSourceContextCall,
        LookupRuleSpecCall,
        SearchOfficialDocsCall,
    )

    if isinstance(call, GetFindingsCall):
        return await tools.get_findings(call.request)
    if isinstance(call, GetSourceContextCall):
        return await tools.get_source_context(call.request)
    if isinstance(call, GetLocalImportersCall):
        return await tools.get_local_importers(call.request)
    if isinstance(call, SearchOfficialDocsCall):
        return await tools.search_official_docs(call.request)
    if isinstance(call, LookupRuleSpecCall):
        return await tools.lookup_rule_spec(call.request)
    raise TypeError("unsupported typed Agent tool call")


class BoundedAnalysisAgent:
    """注入 Day 18 tools/既有 LLMClient，执行一次有限 StateGraph。"""

    def __init__(
        self,
        *,
        tools: AnalysisToolSet,
        llm_client: LLMClient | None,
        limits: AgentRuntimeLimits | None = None,
    ) -> None:
        if not isinstance(tools, AnalysisToolSet):
            raise TypeError("tools 必须是 AnalysisToolSet")
        if llm_client is not None and not isinstance(llm_client, LLMClient):
            raise TypeError("llm_client 必须满足 LLMClient protocol")
        self._tools = tools
        self._llm_client = llm_client
        selected_limits = limits or AgentRuntimeLimits()
        if not isinstance(selected_limits, AgentRuntimeLimits):
            raise TypeError("limits 必须是 AgentRuntimeLimits")
        self._limits = AgentRuntimeLimits.model_validate(
            selected_limits.model_dump(mode="python")
        )
        self._compiled_graph = self._build_graph()

    @property
    def compiled_graph(self) -> CompiledStateGraph:
        """暴露已 compile 的 low-level graph，便于离线结构验收。"""
        return self._compiled_graph

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        """在共享总 deadline 内执行 graph；timeout 后确定性回退。"""
        checked = AgentRunRequest.model_validate(request.model_dump(mode="python"))
        started = time.monotonic()
        initial = self._initial_state(checked, started)
        try:
            async with asyncio.timeout(self._limits.total_timeout_seconds):
                final_state = await self._compiled_graph.ainvoke(
                    initial,
                    config={"recursion_limit": self._limits.max_steps * 2 + 16},
                )
        except TimeoutError:
            return self._timeout_result(checked)
        if final_state["findings"] != checked.rule_result.findings:
            raise RuntimeError("deterministic findings changed during Agent run")
        return _state_to_result(final_state, checked.rule_result.findings)

    def _build_graph(self) -> CompiledStateGraph:
        builder = StateGraph(AnalysisState)
        builder.add_node("prepare", self._prepare)
        builder.add_node("llm_decide", self._llm_decide)
        builder.add_node("validate_action", self._validate_action)
        builder.add_node("execute_tool", self._execute_tool)
        builder.add_node("complete_group", self._complete_group)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "prepare")
        builder.add_conditional_edges(
            "prepare",
            self._route_after_group,
            {"review": "llm_decide", "finalize": "finalize"},
        )
        builder.add_edge("llm_decide", "validate_action")
        builder.add_conditional_edges(
            "validate_action",
            self._route_after_validation,
            {
                "execute_tool": "execute_tool",
                "complete_group": "complete_group",
                "finalize": "finalize",
            },
        )
        builder.add_conditional_edges(
            "execute_tool",
            self._route_after_group,
            {"review": "llm_decide", "finalize": "finalize"},
        )
        builder.add_conditional_edges(
            "complete_group",
            self._route_after_group,
            {"review": "llm_decide", "finalize": "finalize"},
        )
        builder.add_edge("finalize", END)
        return builder.compile()

    def _initial_state(
        self,
        request: AgentRunRequest,
        started: float,
    ) -> AnalysisState:
        findings = request.rule_result.findings
        return AnalysisState(
            analysis_id=request.analysis_id,
            repo_summary=request.repo_summary,
            findings=findings,
            finding_ids=tuple(finding_identity(item) for item in findings),
            one_hop_importers=request.one_hop_importers,
            ambiguous_groups=(),
            overflow_finding_ids=(),
            retrieved_chunks=(),
            retrieval_bindings=(),
            agent_steps=(),
            draft_report=_empty_draft(),
            validation_errors=(),
            degraded_reason=None,
            tool_calls_used=0,
            llm_calls_used=0,
            reviewed_finding_ids=(),
            retry_count=0,
            llm_review=request.llm_review,
            current_group_index=0,
            pending_decision=None,
            pending_model=None,
            finished=False,
            started_monotonic=started,
            deadline_monotonic=started + self._limits.total_timeout_seconds,
        )

    async def _prepare(self, state: AnalysisState) -> dict[str, object]:
        steps = self._begin_step(state, AgentNode.PREPARE)
        if steps is None:
            return self._degraded_update(state, AgentDegradedReason.STEP_LIMIT)
        preparation = prepare_ambiguous_groups(
            state["findings"],
            max_groups=self._limits.max_ambiguous_groups,
        )
        draft = state["draft_report"]
        reason = state["degraded_reason"]
        if preparation.overflow_finding_ids:
            reason = AgentDegradedReason.AMBIGUOUS_GROUP_LIMIT
            draft = _add_human_finding_ids(
                draft,
                preparation.overflow_finding_ids,
                AgentDegradedReason.AMBIGUOUS_GROUP_LIMIT.value,
            )

        finished = not preparation.groups
        if preparation.groups and not state["llm_review"]:
            reason = AgentDegradedReason.LLM_REVIEW_DISABLED
            draft = _add_human_groups(
                draft,
                preparation.groups,
                AgentDegradedReason.LLM_REVIEW_DISABLED.value,
            )
            finished = True
        elif preparation.groups and self._llm_client is None:
            reason = AgentDegradedReason.NO_MODEL
            draft = _add_human_groups(
                draft,
                preparation.groups,
                AgentDegradedReason.NO_MODEL.value,
            )
            finished = True
        return {
            "ambiguous_groups": preparation.groups,
            "overflow_finding_ids": preparation.overflow_finding_ids,
            "agent_steps": steps,
            "draft_report": draft,
            "degraded_reason": reason,
            "finished": finished,
        }

    async def _llm_decide(self, state: AnalysisState) -> dict[str, object]:
        if state["finished"]:
            return {"pending_decision": None, "pending_model": None}
        steps = self._begin_step(state, AgentNode.LLM_DECIDE)
        if steps is None:
            return self._degraded_update(
                state,
                AgentDegradedReason.STEP_LIMIT,
                errors=_limit_error(
                    state,
                    AgentNode.LLM_DECIDE,
                    AgentDegradedReason.STEP_LIMIT,
                ),
            )
        group = _current_group(state)
        if any(
            finding_id in state["reviewed_finding_ids"]
            for finding_id in group.finding_ids
        ):
            raise RuntimeError("finding entered model review more than once")
        reviewed = (*state["reviewed_finding_ids"], *group.finding_ids)
        request = _llm_request(state, group)
        llm_calls = state["llm_calls_used"]
        retry_count = state["retry_count"]
        errors = state["validation_errors"]
        last_reason = AgentDegradedReason.LLM_ERROR

        for attempt in range(self._limits.max_retries + 1):
            remaining = state["deadline_monotonic"] - time.monotonic()
            if remaining <= 0:
                return self._degraded_update(
                    state,
                    AgentDegradedReason.AGENT_TIMEOUT,
                    steps=steps,
                    reviewed=reviewed,
                    llm_calls=llm_calls,
                    retry_count=retry_count,
                    errors=_append_validation_error(
                        errors,
                        AgentValidationError(
                            node=AgentNode.LLM_DECIDE,
                            error_type=AgentDegradedReason.AGENT_TIMEOUT.value,
                            group_id=group.group_id,
                        ),
                    ),
                )
            call_timeout = min(self._limits.llm_timeout_seconds, remaining)
            llm_calls += 1
            try:
                if self._llm_client is None:
                    raise RuntimeError("LLM client disappeared during run")
                async with asyncio.timeout(call_timeout):
                    response = await self._llm_client.complete(
                        request,
                        timeout_seconds=call_timeout,
                    )
                decision = parse_agent_decision(response.content)
                if decision.group_id != group.group_id:
                    raise ValueError("decision group mismatch")
            except TimeoutError:
                last_reason = AgentDegradedReason.LLM_TIMEOUT
                error_type = AgentDegradedReason.LLM_TIMEOUT.value
            except LLMClientError:
                last_reason = AgentDegradedReason.LLM_ERROR
                error_type = AgentDegradedReason.LLM_ERROR.value
            except (ValidationError, TypeError, ValueError):
                last_reason = AgentDegradedReason.LLM_INVALID_RESPONSE
                error_type = AgentDegradedReason.LLM_INVALID_RESPONSE.value
            else:
                return {
                    "agent_steps": steps,
                    "pending_decision": decision,
                    "pending_model": response.model,
                    "reviewed_finding_ids": reviewed,
                    "llm_calls_used": llm_calls,
                    "retry_count": retry_count,
                    "validation_errors": errors,
                }

            errors = _append_validation_error(
                errors,
                AgentValidationError(
                    node=AgentNode.LLM_DECIDE,
                    error_type=error_type,
                    group_id=group.group_id,
                ),
            )
            if attempt < self._limits.max_retries:
                remaining = state["deadline_monotonic"] - time.monotonic()
                if remaining > 0:
                    retry_count += 1
                    continue
            break

        return self._degraded_update(
            state,
            last_reason,
            steps=steps,
            reviewed=reviewed,
            llm_calls=llm_calls,
            retry_count=retry_count,
            errors=errors,
        )

    async def _validate_action(self, state: AnalysisState) -> dict[str, object]:
        decision = state["pending_decision"]
        if state["finished"] or decision is None:
            return {"pending_decision": None}
        steps = self._begin_step(state, AgentNode.VALIDATE_ACTION)
        if steps is None:
            return self._degraded_update(
                state,
                AgentDegradedReason.STEP_LIMIT,
                errors=_limit_error(
                    state,
                    AgentNode.VALIDATE_ACTION,
                    AgentDegradedReason.STEP_LIMIT,
                ),
            )
        if state["deadline_monotonic"] - time.monotonic() <= 0:
            return self._degraded_update(
                state,
                AgentDegradedReason.AGENT_TIMEOUT,
                steps=steps,
                errors=_limit_error(
                    state,
                    AgentNode.VALIDATE_ACTION,
                    AgentDegradedReason.AGENT_TIMEOUT,
                ),
            )
        if isinstance(decision, CallToolDecision) and (
            state["tool_calls_used"] >= self._limits.max_tool_calls
        ):
            return self._degraded_update(
                state,
                AgentDegradedReason.TOOL_CALL_LIMIT,
                steps=steps,
                errors=_limit_error(
                    state,
                    AgentNode.VALIDATE_ACTION,
                    AgentDegradedReason.TOOL_CALL_LIMIT,
                ),
            )
        return {"agent_steps": steps}

    async def _execute_tool(self, state: AnalysisState) -> dict[str, object]:
        decision = state["pending_decision"]
        if not isinstance(decision, CallToolDecision):
            raise RuntimeError("execute_tool received a non-tool decision")
        steps = self._begin_step(
            state,
            AgentNode.EXECUTE_TOOL,
            tool_name=ToolName(decision.call.tool),
        )
        if steps is None:
            return self._degraded_update(
                state,
                AgentDegradedReason.STEP_LIMIT,
                errors=_limit_error(
                    state,
                    AgentNode.EXECUTE_TOOL,
                    AgentDegradedReason.STEP_LIMIT,
                ),
            )
        tool_calls = state["tool_calls_used"] + 1
        group = _current_group(state)
        try:
            result = await dispatch_tool_call(self._tools, decision)
        except AgentToolError as error:
            errors = _append_validation_error(
                state["validation_errors"],
                AgentValidationError(
                    node=AgentNode.EXECUTE_TOOL,
                    error_type=error.error_type.value,
                    group_id=group.group_id,
                ),
            )
            return self._degraded_update(
                state,
                AgentDegradedReason.TOOL_ERROR,
                steps=steps,
                tool_calls=tool_calls,
                errors=errors,
            )

        retrieved = state["retrieved_chunks"]
        retrieval_bindings = state["retrieval_bindings"]
        draft = state["draft_report"]
        if isinstance(result, SearchOfficialDocsResult):
            if not isinstance(decision.call, SearchOfficialDocsCall):
                raise RuntimeError("docs result has no typed search request")
            existing = {item.chunk_id for item in retrieved}
            new_chunks = tuple(
                item for item in result.results if item.chunk_id not in existing
            )
            retrieved = (*retrieved, *new_chunks)
            for item in result.results:
                draft = _add_doc_candidate(
                    draft,
                    SelectedDocCandidate(
                        analysis_id=state["analysis_id"],
                        group_id=group.group_id,
                        finding_ids=group.finding_ids,
                        chunk_id=item.chunk_id,
                        validated=False,
                    ),
                )
            query = decision.call.request.query
            if result.results:
                retrieval_bindings = (
                    *retrieval_bindings,
                    RetrievalBinding(
                        group_id=group.group_id,
                        rule_id=group.rule_id,
                        finding_ids=group.finding_ids,
                        query_sha256=(
                            "sha256:"
                            + hashlib.sha256(query.encode("utf-8")).hexdigest()
                        ),
                        matched_query_terms=_matched_query_terms(state, group, query),
                        chunk_ids=tuple(item.chunk_id for item in result.results),
                    ),
                )
        else:
            draft = _add_human_item(
                draft,
                HumanReviewItem(
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    reason="tool_observation",
                ),
            )
        return {
            "agent_steps": steps,
            "tool_calls_used": tool_calls,
            "retrieved_chunks": retrieved,
            "retrieval_bindings": retrieval_bindings,
            "draft_report": draft,
            "current_group_index": state["current_group_index"] + 1,
            "pending_decision": None,
            "pending_model": None,
        }

    async def _complete_group(self, state: AnalysisState) -> dict[str, object]:
        decision = state["pending_decision"]
        if not isinstance(decision, (FinishGroupDecision, RequestHumanReviewDecision)):
            raise RuntimeError("complete_group received an unsupported decision")
        steps = self._begin_step(state, AgentNode.COMPLETE_GROUP)
        if steps is None:
            return self._degraded_update(
                state,
                AgentDegradedReason.STEP_LIMIT,
                errors=_limit_error(
                    state,
                    AgentNode.COMPLETE_GROUP,
                    AgentDegradedReason.STEP_LIMIT,
                ),
            )
        group = _current_group(state)
        draft = state["draft_report"]
        if isinstance(decision, FinishGroupDecision):
            if state["pending_model"] is None:
                raise RuntimeError("finish decision has no model identity")
            draft = _add_explanation(
                draft,
                ExplanationCandidate(
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    text=decision.explanation,
                    model=state["pending_model"],
                ),
            )
        else:
            draft = _add_human_item(
                draft,
                HumanReviewItem(
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    reason="requested_by_model",
                    detail=decision.reason,
                ),
            )
        return {
            "agent_steps": steps,
            "draft_report": draft,
            "current_group_index": state["current_group_index"] + 1,
            "pending_decision": None,
            "pending_model": None,
        }

    async def _finalize(self, state: AnalysisState) -> dict[str, object]:
        return {"finished": True, "pending_decision": None, "pending_model": None}

    def _route_after_group(
        self,
        state: AnalysisState,
    ) -> Literal["review", "finalize"]:
        if state["finished"]:
            return "finalize"
        if state["degraded_reason"] not in {
            None,
            AgentDegradedReason.AMBIGUOUS_GROUP_LIMIT,
        }:
            return "finalize"
        if state["current_group_index"] >= len(state["ambiguous_groups"]):
            return "finalize"
        return "review"

    def _route_after_validation(
        self,
        state: AnalysisState,
    ) -> Literal["execute_tool", "complete_group", "finalize"]:
        if state["finished"] or state["pending_decision"] is None:
            return "finalize"
        if isinstance(state["pending_decision"], CallToolDecision):
            return "execute_tool"
        return "complete_group"

    def _begin_step(
        self,
        state: AnalysisState,
        node: AgentNode,
        *,
        tool_name: ToolName | None = None,
    ) -> tuple[AgentStep, ...] | None:
        if len(state["agent_steps"]) >= self._limits.max_steps:
            return None
        group_id = (
            _current_group(state).group_id
            if state["current_group_index"] < len(state["ambiguous_groups"])
            else None
        )
        step = AgentStep(
            sequence=len(state["agent_steps"]) + 1,
            node=node,
            status=AgentStepStatus.SUCCESS,
            group_id=group_id,
            tool_name=tool_name,
        )
        return (*state["agent_steps"], step)

    def _degraded_update(
        self,
        state: AnalysisState,
        reason: AgentDegradedReason,
        *,
        steps: tuple[AgentStep, ...] | None = None,
        reviewed: tuple[str, ...] | None = None,
        llm_calls: int | None = None,
        retry_count: int | None = None,
        tool_calls: int | None = None,
        errors: tuple[AgentValidationError, ...] | None = None,
    ) -> dict[str, object]:
        draft = _add_remaining_human_groups(
            state["draft_report"],
            state["ambiguous_groups"],
            state["current_group_index"],
            reason.value,
        )
        current_reason = state["degraded_reason"]
        if current_reason is AgentDegradedReason.AMBIGUOUS_GROUP_LIMIT:
            current_reason = reason
        return {
            "agent_steps": state["agent_steps"] if steps is None else steps,
            "reviewed_finding_ids": (
                state["reviewed_finding_ids"] if reviewed is None else reviewed
            ),
            "llm_calls_used": (
                state["llm_calls_used"] if llm_calls is None else llm_calls
            ),
            "retry_count": state["retry_count"] if retry_count is None else retry_count,
            "tool_calls_used": (
                state["tool_calls_used"] if tool_calls is None else tool_calls
            ),
            "validation_errors": (
                state["validation_errors"] if errors is None else errors
            ),
            "draft_report": draft,
            "degraded_reason": current_reason or reason,
            "pending_decision": None,
            "pending_model": None,
            "finished": True,
        }

    def _timeout_result(self, request: AgentRunRequest) -> AgentRunResult:
        preparation = prepare_ambiguous_groups(
            request.rule_result.findings,
            max_groups=self._limits.max_ambiguous_groups,
        )
        draft = _add_human_groups(
            _empty_draft(),
            preparation.groups,
            AgentDegradedReason.AGENT_TIMEOUT.value,
        )
        if preparation.overflow_finding_ids:
            draft = _add_human_finding_ids(
                draft,
                preparation.overflow_finding_ids,
                AgentDegradedReason.AMBIGUOUS_GROUP_LIMIT.value,
            )
        findings = request.rule_result.findings
        return AgentRunResult(
            analysis_id=request.analysis_id,
            repo_summary=request.repo_summary,
            findings=findings,
            finding_ids=tuple(finding_identity(item) for item in findings),
            one_hop_importers=request.one_hop_importers,
            ambiguous_groups=preparation.groups,
            retrieved_chunks=(),
            retrieval_bindings=(),
            agent_steps=(),
            draft_report=draft,
            validation_errors=(
                AgentValidationError(
                    node=AgentNode.LLM_DECIDE,
                    error_type=AgentDegradedReason.AGENT_TIMEOUT.value,
                ),
            ),
            degraded_reason=AgentDegradedReason.AGENT_TIMEOUT,
            terminal_status=AgentTerminalStatus.DEGRADED,
            tool_calls_used=0,
            llm_calls_used=0,
            reviewed_finding_ids=(),
            retry_count=0,
        )


def _current_group(state: AnalysisState) -> AmbiguousGroup:
    index = state["current_group_index"]
    if not 0 <= index < len(state["ambiguous_groups"]):
        raise RuntimeError("Agent current group is out of range")
    return state["ambiguous_groups"][index]


def _llm_request(state: AnalysisState, group: AmbiguousGroup) -> LLMRequest:
    finding_by_id = {
        finding_identity(finding): finding for finding in state["findings"]
    }
    finding_summaries = tuple(
        {
            "finding_id": finding_id,
            "old_api": finding_by_id[finding_id].old_api,
            "matched_construct": finding_by_id[finding_id].matched_construct.value,
            "line": finding_by_id[finding_id].location.start_line,
        }
        for finding_id in group.finding_ids
    )
    payload = {
        "group": group.model_dump(mode="json"),
        "findings": finding_summaries,
        "allowed_tools": [tool.value for tool in ToolName],
    }
    return LLMRequest(
        messages=(
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
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


def _empty_draft() -> AgentDraft:
    return AgentDraft(
        explanations=(),
        selected_doc_candidates=(),
        human_review_items=(),
    )


def _add_explanation(draft: AgentDraft, item: ExplanationCandidate) -> AgentDraft:
    return draft.model_copy(update={"explanations": (*draft.explanations, item)})


def _add_doc_candidate(draft: AgentDraft, item: SelectedDocCandidate) -> AgentDraft:
    key = (item.group_id, item.chunk_id)
    if key in {
        (existing.group_id, existing.chunk_id)
        for existing in draft.selected_doc_candidates
    }:
        return draft
    return draft.model_copy(
        update={
            "selected_doc_candidates": (*draft.selected_doc_candidates, item),
        }
    )


def _add_human_item(draft: AgentDraft, item: HumanReviewItem) -> AgentDraft:
    key = (item.group_id, item.finding_ids, item.reason)
    if key in {
        (existing.group_id, existing.finding_ids, existing.reason)
        for existing in draft.human_review_items
    }:
        return draft
    return draft.model_copy(
        update={"human_review_items": (*draft.human_review_items, item)}
    )


def _add_human_groups(
    draft: AgentDraft,
    groups: tuple[AmbiguousGroup, ...],
    reason: str,
) -> AgentDraft:
    for group in groups:
        draft = _add_human_item(
            draft,
            HumanReviewItem(
                group_id=group.group_id,
                finding_ids=group.finding_ids,
                reason=reason,
            ),
        )
    return draft


def _add_human_finding_ids(
    draft: AgentDraft,
    finding_ids: tuple[str, ...],
    reason: str,
) -> AgentDraft:
    for offset in range(0, len(finding_ids), MAX_FINDINGS_PER_GROUP):
        draft = _add_human_item(
            draft,
            HumanReviewItem(
                group_id=None,
                finding_ids=finding_ids[offset : offset + MAX_FINDINGS_PER_GROUP],
                reason=reason,
            ),
        )
    return draft


def _add_remaining_human_groups(
    draft: AgentDraft,
    groups: tuple[AmbiguousGroup, ...],
    start_index: int,
    reason: str,
) -> AgentDraft:
    return _add_human_groups(draft, groups[start_index:], reason)


def _append_validation_error(
    errors: tuple[AgentValidationError, ...],
    error: AgentValidationError,
) -> tuple[AgentValidationError, ...]:
    if len(errors) >= MAX_AGENT_VALIDATION_ERRORS:
        return errors
    return (*errors, error)


def _limit_error(
    state: AnalysisState,
    node: AgentNode,
    reason: AgentDegradedReason,
) -> tuple[AgentValidationError, ...]:
    group_id = (
        _current_group(state).group_id
        if state["current_group_index"] < len(state["ambiguous_groups"])
        else None
    )
    return _append_validation_error(
        state["validation_errors"],
        AgentValidationError(
            node=node,
            error_type=reason.value,
            group_id=group_id,
        ),
    )


def _state_to_result(
    state: AnalysisState,
    original_findings: tuple[Finding, ...],
) -> AgentRunResult:
    degraded_reason = state["degraded_reason"]
    terminal = (
        AgentTerminalStatus.COMPLETED
        if degraded_reason is None
        else AgentTerminalStatus.DEGRADED
    )
    return AgentRunResult(
        analysis_id=state["analysis_id"],
        repo_summary=state["repo_summary"],
        findings=original_findings,
        finding_ids=tuple(finding_identity(item) for item in original_findings),
        one_hop_importers=state["one_hop_importers"],
        ambiguous_groups=state["ambiguous_groups"],
        retrieved_chunks=state["retrieved_chunks"],
        retrieval_bindings=state["retrieval_bindings"],
        agent_steps=state["agent_steps"],
        draft_report=state["draft_report"],
        validation_errors=state["validation_errors"],
        degraded_reason=degraded_reason,
        terminal_status=terminal,
        tool_calls_used=state["tool_calls_used"],
        llm_calls_used=state["llm_calls_used"],
        reviewed_finding_ids=state["reviewed_finding_ids"],
        retry_count=state["retry_count"],
    )


def _matched_query_terms(
    state: AnalysisState,
    group: AmbiguousGroup,
    query: str,
) -> tuple[str, ...]:
    """只保留命中的可信 rule terms，不把 raw query 写入稳定结果。"""
    finding_by_id = {
        finding_identity(finding): finding for finding in state["findings"]
    }
    rule_spec = get_rule_spec(group.rule_id)
    candidates = {
        group.rule_id.value,
        group.rule_id.value.removeprefix("pydantic_v1_"),
        rule_spec.category.value,
        rule_spec.category.value.replace("_", " "),
        *rule_spec.old_apis,
        *(finding_by_id[item].old_api for item in group.finding_ids),
    }
    folded_query = query.casefold()
    return tuple(
        sorted(
            {term for term in candidates if term.casefold() in folded_query},
            key=str.casefold,
        )
    )
