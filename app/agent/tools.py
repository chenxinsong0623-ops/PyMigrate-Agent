"""Framework-neutral 的 Day 18 五工具只读执行边界。"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.agent.tool_models import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    MAX_DOC_CHUNK_CHARACTERS,
    MAX_FINDINGS_RETURNED,
    MAX_IMPORTERS_RETURNED,
    MAX_SOURCE_CONTEXT_CHARACTERS,
    MAX_TOOL_TIMEOUT_SECONDS,
    AgentToolError,
    GetFindingsRequest,
    GetFindingsResult,
    GetLocalImportersRequest,
    GetLocalImportersResult,
    GetSourceContextRequest,
    GetSourceContextResult,
    LocalImporter,
    LookupRuleSpecRequest,
    LookupRuleSpecResult,
    OfficialDocChunk,
    SearchOfficialDocsRequest,
    SearchOfficialDocsResult,
    SourceContextLine,
    ToolAuditEvent,
    ToolErrorType,
    ToolName,
    ToolStatus,
)
from app.core.embedding import EmbeddingInfrastructureError
from app.retrieval.bm25 import BM25ArtifactError
from app.retrieval.dense import DenseRetrievalError
from app.retrieval.hybrid import (
    HybridFusionContractError,
    HybridSearchResponse,
    HybridSearchResult,
)
from app.retrieval.qdrant import QdrantInfrastructureError
from app.scanner import (
    LocalImportGraph,
    RuleId,
    RuleRegistryError,
    RuleScanResult,
    ScannerError,
    ScannerErrorType,
    get_rule_spec,
    read_validated_python_source,
)
from app.security import ZipGuardResult


class OfficialDocsRetriever(Protocol):
    """Day 18 只需要既有 HybridRetriever 的只读 search。"""

    async def search(self, query: str) -> HybridSearchResponse:
        """返回 Day 11 完整融合排名。"""
        ...


class ToolAuditSink(Protocol):
    """每次调用接收一个不含敏感输入正文的 typed trace event。"""

    def record(self, event: ToolAuditEvent) -> None:
        """记录一个 audit event。"""
        ...


class InMemoryToolAuditSink:
    """由单次分析 context 独占的最小内存审计 collector。"""

    def __init__(self) -> None:
        self._events: list[ToolAuditEvent] = []

    @property
    def events(self) -> tuple[ToolAuditEvent, ...]:
        return tuple(self._events)

    def record(self, event: ToolAuditEvent) -> None:
        if not isinstance(event, ToolAuditEvent):
            raise TypeError("audit sink 只接受 ToolAuditEvent")
        self._events.append(event)


@dataclass(frozen=True, slots=True)
class AnalysisToolContext:
    """单次 ZipGuard 生命周期内五工具共享的只读依赖。"""

    validated: ZipGuardResult
    rule_result: RuleScanResult
    import_graph: LocalImportGraph
    official_docs_retriever: OfficialDocsRetriever
    trace_sink: ToolAuditSink

    def __post_init__(self) -> None:
        if not isinstance(self.validated, ZipGuardResult):
            raise TypeError("validated 必须是 ZipGuardResult")
        if not isinstance(self.rule_result, RuleScanResult):
            raise TypeError("rule_result 必须是 RuleScanResult")
        if not isinstance(self.import_graph, LocalImportGraph):
            raise TypeError("import_graph 必须是 LocalImportGraph")
        if not callable(getattr(self.official_docs_retriever, "search", None)):
            raise TypeError("official docs retriever 必须提供 search")
        if not callable(getattr(self.trace_sink, "record", None)):
            raise TypeError("trace sink 必须提供 record")


RequestT = TypeVar("RequestT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class AnalysisToolSet:
    """五个公开 async tool，共用 timeout、validation、error 与 trace runner。"""

    def __init__(
        self,
        context: AnalysisToolContext,
        *,
        timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(context, AnalysisToolContext):
            raise TypeError("context 必须是 AnalysisToolContext")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or timeout_seconds <= 0
            or timeout_seconds > MAX_TOOL_TIMEOUT_SECONDS
        ):
            raise ValueError("tool timeout 必须位于 (0, 30] 秒")
        self._context = context
        self._timeout_seconds = float(timeout_seconds)
        self._trace_sequence = 0

    async def get_findings(self, request: GetFindingsRequest) -> GetFindingsResult:
        """只过滤当前 RuleScanResult.findings。"""
        return await self._execute(
            ToolName.GET_FINDINGS,
            request,
            GetFindingsRequest,
            self._get_findings_impl,
        )

    async def get_source_context(
        self,
        request: GetSourceContextRequest,
    ) -> GetSourceContextResult:
        """只读取 validated inventory 中通过身份复核的局部源码。"""
        return await self._execute(
            ToolName.GET_SOURCE_CONTEXT,
            request,
            GetSourceContextRequest,
            self._get_source_context_impl,
        )

    async def get_local_importers(
        self,
        request: GetLocalImportersRequest,
    ) -> GetLocalImportersResult:
        """直接复用 LocalImportGraph.get_importers 的严格一跳结果。"""
        return await self._execute(
            ToolName.GET_LOCAL_IMPORTERS,
            request,
            GetLocalImportersRequest,
            self._get_local_importers_impl,
        )

    async def search_official_docs(
        self,
        request: SearchOfficialDocsRequest,
    ) -> SearchOfficialDocsResult:
        """只查询固定官方文档 HybridRetriever，不访问 Web。"""
        return await self._execute(
            ToolName.SEARCH_OFFICIAL_DOCS,
            request,
            SearchOfficialDocsRequest,
            self._search_official_docs_impl,
        )

    async def lookup_rule_spec(
        self,
        request: LookupRuleSpecRequest,
    ) -> LookupRuleSpecResult:
        """只查询 production rule metadata registry。"""
        return await self._execute(
            ToolName.LOOKUP_RULE_SPEC,
            request,
            LookupRuleSpecRequest,
            self._lookup_rule_spec_impl,
        )

    async def _execute(
        self,
        tool_name: ToolName,
        request: object,
        request_type: type[RequestT],
        implementation: Callable[[RequestT], Awaitable[ResultT]],
    ) -> ResultT:
        started = time.perf_counter()
        try:
            checked_request = _validate_request(request, request_type)
        except (ValidationError, TypeError, ValueError) as error:
            error_type = _request_error_type(tool_name, error)
            self._record_failure(tool_name, error_type, started)
            raise AgentToolError(tool_name, error_type) from None

        input_characters = _input_characters(checked_request)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                result = await implementation(checked_request)
        except TimeoutError:
            self._record_failure(
                tool_name,
                ToolErrorType.TIMEOUT,
                started,
                input_characters=input_characters,
                status=ToolStatus.TIMEOUT,
            )
            raise AgentToolError(tool_name, ToolErrorType.TIMEOUT) from None
        except AgentToolError as error:
            self._record_failure(
                tool_name,
                error.error_type,
                started,
                input_characters=input_characters,
            )
            raise
        except Exception:
            self._record_failure(
                tool_name,
                ToolErrorType.INFRASTRUCTURE_FAILURE,
                started,
                input_characters=input_characters,
            )
            raise

        returned_count = int(result.returned_count)  # type: ignore[attr-defined]
        truncated = bool(result.truncated)  # type: ignore[attr-defined]
        status = ToolStatus.EMPTY if returned_count == 0 else ToolStatus.SUCCESS
        self._record(
            tool_name=tool_name,
            status=status,
            error_type=None,
            input_characters=input_characters,
            returned_count=returned_count,
            truncated=truncated,
            started=started,
        )
        return result

    async def _get_findings_impl(
        self,
        request: GetFindingsRequest,
    ) -> GetFindingsResult:
        await asyncio.sleep(0)
        try:
            checked = RuleScanResult(
                schema_version=self._context.rule_result.schema_version,
                findings=self._context.rule_result.findings,
            )
        except (ValidationError, ValueError):
            raise AgentToolError(
                ToolName.GET_FINDINGS,
                ToolErrorType.INFRASTRUCTURE_FAILURE,
            ) from None
        matches = tuple(
            finding
            for finding in checked.findings
            if (request.rule_id is None or finding.rule_id is request.rule_id)
            and (request.severity is None or finding.severity is request.severity)
        )
        returned = matches[:MAX_FINDINGS_RETURNED]
        await asyncio.sleep(0)
        return GetFindingsResult(
            findings=returned,
            total_count=len(matches),
            returned_count=len(returned),
            truncated=len(returned) < len(matches),
        )

    async def _get_source_context_impl(
        self,
        request: GetSourceContextRequest,
    ) -> GetSourceContextResult:
        inventory = next(
            (
                item
                for item in self._context.validated.python_files
                if item.relative_path == request.path
            ),
            None,
        )
        if inventory is None:
            raise AgentToolError(
                ToolName.GET_SOURCE_CONTEXT,
                ToolErrorType.UNKNOWN_PATH,
            )
        await asyncio.sleep(0)
        try:
            source_text = read_validated_python_source(
                self._context.validated,
                inventory,
            )
        except ScannerError as error:
            error_type = (
                ToolErrorType.INFRASTRUCTURE_FAILURE
                if error.error_type is ScannerErrorType.INVALID_INVENTORY
                else ToolErrorType.SOURCE_IDENTITY_MISMATCH
            )
            raise AgentToolError(ToolName.GET_SOURCE_CONTEXT, error_type) from None

        all_lines = source_text.splitlines()
        if not all_lines:
            return GetSourceContextResult(
                path=request.path,
                requested_line=request.line,
                radius=request.radius,
                file_line_count=0,
                start_line=None,
                end_line=None,
                source_lines=(),
                total_characters=0,
                returned_characters=0,
                total_count=0,
                returned_count=0,
                truncated=False,
            )

        center_line = min(request.line, len(all_lines))
        start_line = max(1, center_line - request.radius)
        end_line = min(len(all_lines), center_line + request.radius)
        window = tuple(
            (line_number, all_lines[line_number - 1])
            for line_number in range(start_line, end_line + 1)
        )
        total_characters = sum(len(text) for _line, text in window)
        remaining = MAX_SOURCE_CONTEXT_CHARACTERS
        returned_lines: list[SourceContextLine] = []
        for line_number, text in window:
            if remaining == 0:
                break
            returned_text = text[:remaining]
            line_truncated = len(returned_text) < len(text)
            returned_lines.append(
                SourceContextLine(
                    line=line_number,
                    text=returned_text,
                    truncated=line_truncated,
                )
            )
            remaining -= len(returned_text)
            if line_truncated:
                break
        returned_characters = sum(len(item.text) for item in returned_lines)
        truncated = (
            len(returned_lines) < len(window) or returned_characters < total_characters
        )
        await asyncio.sleep(0)
        return GetSourceContextResult(
            path=request.path,
            requested_line=request.line,
            radius=request.radius,
            file_line_count=len(all_lines),
            start_line=start_line,
            end_line=end_line,
            source_lines=tuple(returned_lines),
            total_characters=total_characters,
            returned_characters=returned_characters,
            total_count=len(window),
            returned_count=len(returned_lines),
            truncated=truncated,
        )

    async def _get_local_importers_impl(
        self,
        request: GetLocalImportersRequest,
    ) -> GetLocalImportersResult:
        await asyncio.sleep(0)
        try:
            graph = LocalImportGraph(
                schema_version=self._context.import_graph.schema_version,
                modules=self._context.import_graph.modules,
                edges=self._context.import_graph.edges,
            )
        except (ValidationError, ValueError):
            raise AgentToolError(
                ToolName.GET_LOCAL_IMPORTERS,
                ToolErrorType.INFRASTRUCTURE_FAILURE,
            ) from None
        if request.path not in {module.relative_path for module in graph.modules}:
            raise AgentToolError(
                ToolName.GET_LOCAL_IMPORTERS,
                ToolErrorType.UNKNOWN_PATH,
            )
        edges = graph.get_importers(request.path)
        returned_edges = edges[:MAX_IMPORTERS_RETURNED]
        importers = tuple(
            LocalImporter(
                path=edge.importer_relative_path,
                module=edge.importer_module,
            )
            for edge in returned_edges
        )
        await asyncio.sleep(0)
        return GetLocalImportersResult(
            path=request.path,
            importers=importers,
            total_count=len(edges),
            returned_count=len(importers),
            truncated=len(importers) < len(edges),
        )

    async def _search_official_docs_impl(
        self,
        request: SearchOfficialDocsRequest,
    ) -> SearchOfficialDocsResult:
        try:
            raw_response = await self._context.official_docs_retriever.search(
                request.query
            )
            response = HybridSearchResponse.model_validate(
                raw_response.model_dump(mode="python")
            )
        except (
            BM25ArtifactError,
            DenseRetrievalError,
            EmbeddingInfrastructureError,
            HybridFusionContractError,
            QdrantInfrastructureError,
            ValidationError,
            ValueError,
        ):
            raise AgentToolError(
                ToolName.SEARCH_OFFICIAL_DOCS,
                ToolErrorType.RETRIEVAL_FAILURE,
            ) from None

        selected = response.results[: request.top_k]
        docs = tuple(_bounded_doc_chunk(item) for item in selected)
        text_truncated = any(item.text_truncated for item in docs)
        count_truncated = len(selected) < len(response.results)
        return SearchOfficialDocsResult(
            query_characters=len(request.query),
            requested_top_k=request.top_k,
            results=docs,
            returned_text_characters=sum(len(item.text) for item in docs),
            total_count=len(response.results),
            returned_count=len(docs),
            truncated=count_truncated or text_truncated,
        )

    async def _lookup_rule_spec_impl(
        self,
        request: LookupRuleSpecRequest,
    ) -> LookupRuleSpecResult:
        await asyncio.sleep(0)
        try:
            rule_id = RuleId(request.rule_id)
        except ValueError:
            raise AgentToolError(
                ToolName.LOOKUP_RULE_SPEC,
                ToolErrorType.UNKNOWN_RULE,
            ) from None
        try:
            rule_spec = get_rule_spec(rule_id)
        except RuleRegistryError:
            raise AgentToolError(
                ToolName.LOOKUP_RULE_SPEC,
                ToolErrorType.INFRASTRUCTURE_FAILURE,
            ) from None
        return LookupRuleSpecResult(
            rule_spec=rule_spec,
            total_count=1,
            returned_count=1,
            truncated=False,
        )

    def _record_failure(
        self,
        tool_name: ToolName,
        error_type: ToolErrorType,
        started: float,
        *,
        input_characters: int = 0,
        status: ToolStatus = ToolStatus.ERROR,
    ) -> None:
        self._record(
            tool_name=tool_name,
            status=status,
            error_type=error_type,
            input_characters=input_characters,
            returned_count=0,
            truncated=False,
            started=started,
        )

    def _record(
        self,
        *,
        tool_name: ToolName,
        status: ToolStatus,
        error_type: ToolErrorType | None,
        input_characters: int,
        returned_count: int,
        truncated: bool,
        started: float,
    ) -> None:
        self._trace_sequence += 1
        duration_ms = max((time.perf_counter() - started) * 1000, 0.0)
        event = ToolAuditEvent(
            sequence=self._trace_sequence,
            tool_name=tool_name,
            status=status,
            error_type=error_type,
            input_characters=input_characters,
            returned_count=returned_count,
            truncated=truncated,
            duration_ms=round(duration_ms, 3),
        )
        self._context.trace_sink.record(event)


def _validate_request(
    request: object,
    request_type: type[RequestT],
) -> RequestT:
    if isinstance(request, request_type):
        payload = request.model_dump(mode="python")
    else:
        payload = request
    return request_type.model_validate(payload)


def _request_error_type(
    tool_name: ToolName,
    error: ValidationError | TypeError | ValueError,
) -> ToolErrorType:
    if tool_name in {ToolName.GET_SOURCE_CONTEXT, ToolName.GET_LOCAL_IMPORTERS}:
        if isinstance(error, ValidationError) and any(
            item.get("loc", ())[:1] == ("path",) and item.get("type") == "value_error"
            for item in error.errors()
        ):
            return ToolErrorType.PATH_NOT_ALLOWED
    return ToolErrorType.INVALID_ARGUMENT


def _input_characters(request: BaseModel) -> int:
    if isinstance(request, GetFindingsRequest):
        return sum(
            len(value.value)
            for value in (request.rule_id, request.severity)
            if value is not None
        )
    if isinstance(request, (GetSourceContextRequest, GetLocalImportersRequest)):
        return len(request.path)
    if isinstance(request, SearchOfficialDocsRequest):
        return len(request.query)
    if isinstance(request, LookupRuleSpecRequest):
        return len(request.rule_id)
    return 0


def _bounded_doc_chunk(result: HybridSearchResult) -> OfficialDocChunk:
    full_text = result.text
    returned_text = full_text[:MAX_DOC_CHUNK_CHARACTERS]
    return OfficialDocChunk(
        rank=result.rank,
        rrf_score=result.rrf_score,
        bm25_rank=result.bm25_rank,
        dense_rank=result.dense_rank,
        bm25_score=result.bm25_score,
        dense_score=result.dense_score,
        chunk_id=result.chunk_id,
        heading_path=result.heading_path,
        text=returned_text,
        full_text_characters=len(full_text),
        text_truncated=len(returned_text) < len(full_text),
        content_sha256=result.content_sha256,
        source_id=result.source_id,
        source_url=result.source_url,
        git_ref=result.git_ref,
        resolved_commit_sha=result.resolved_commit_sha,
        source_path=result.source_path,
        source_snapshot_sha256=result.source_snapshot_sha256,
    )
