"""同步编排 Day 13–20 链路并原子持久化唯一最终报告。"""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app import __version__
from app.agent import (
    AgentRunRequest,
    AnalysisToolContext,
    AnalysisToolSet,
    BoundedAnalysisAgent,
    InMemoryToolAuditSink,
    OfficialDocsRetriever,
    RepositorySummary,
)
from app.application.models import (
    AnalysisResponse,
    AnalysisSummary,
    AnalysisTimings,
)
from app.core.embedding import E5Embedding
from app.core.llm import LLMClient, LLMRequest, LLMResponse
from app.ingestion.markdown_chunker import CHUNK_ARTIFACT_PATH
from app.ingestion.pydantic_snapshot import MANIFEST_PATH, SnapshotManifest
from app.reporting import (
    CitationGuard,
    FinalReport,
    FinalReportBuilder,
    ReportExplanationSource,
    render_report_json,
    render_report_markdown,
)
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseQueryQdrant, DenseRetriever
from app.retrieval.hybrid import HybridRetriever, HybridSearchResponse
from app.scanner import (
    ASTScanner,
    ImportGraphBuilder,
    OneHopImpactAnalyzer,
    RuleScanner,
    Severity,
)
from app.security import ZipGuard
from app.storage.sqlite import StoredAnalysis


class _AnalysisStorage(Protocol):
    async def save_analysis(self, record: StoredAnalysis) -> None: ...


class _TimingAccumulator:
    def __init__(self) -> None:
        self.retrieve = 0
        self.llm = 0


class _TimedRetriever:
    def __init__(
        self, base: OfficialDocsRetriever, timings: _TimingAccumulator
    ) -> None:
        self._base = base
        self._timings = timings

    async def search(self, query: str) -> HybridSearchResponse:
        started = time.perf_counter()
        try:
            return await self._base.search(query)
        finally:
            self._timings.retrieve += _called_elapsed_ms(started)


class _TimedLLM:
    def __init__(self, base: LLMClient, timings: _TimingAccumulator) -> None:
        self._base = base
        self._timings = timings

    async def complete(
        self,
        request: LLMRequest,
        timeout_seconds: float,
    ) -> LLMResponse:
        started = time.perf_counter()
        try:
            return await self._base.complete(request, timeout_seconds)
        finally:
            self._timings.llm += _called_elapsed_ms(started)


class LazyOfficialDocsRetriever:
    """首次真正检索时才加载本地 BM25 与 E5 adapter。"""

    def __init__(
        self,
        *,
        repository_root: Path,
        qdrant_backend: DenseQueryQdrant,
        embedding_cache_path: Path,
        embedding_batch_size: int,
        embedding_timeout_seconds: float,
        rrf_k: int,
    ) -> None:
        self._repository_root = repository_root
        self._qdrant_backend = qdrant_backend
        self._embedding_cache_path = embedding_cache_path
        self._embedding_batch_size = embedding_batch_size
        self._embedding_timeout_seconds = embedding_timeout_seconds
        self._rrf_k = rrf_k
        self._retriever: HybridRetriever | None = None
        self._lock = asyncio.Lock()

    async def search(self, query: str) -> HybridSearchResponse:
        retriever = await self._get_retriever()
        return await retriever.search(query)

    async def _get_retriever(self) -> HybridRetriever:
        if self._retriever is not None:
            return self._retriever
        async with self._lock:
            if self._retriever is None:
                embedding = E5Embedding(
                    cache_folder=self._embedding_cache_path,
                    batch_size=self._embedding_batch_size,
                )
                dense = DenseRetriever(
                    embedding_client=embedding,
                    qdrant_backend=self._qdrant_backend,
                    embedding_timeout_seconds=self._embedding_timeout_seconds,
                )
                self._retriever = HybridRetriever(
                    bm25_retriever=BM25Retriever.from_artifact(
                        self._repository_root / CHUNK_ARTIFACT_PATH
                    ),
                    dense_retriever=dense,
                    rrf_k=self._rrf_k,
                )
        return self._retriever


class AnalysisService:
    """应用拥有的同步分析边界；请求间只共享只读 adapter 与存储连接。"""

    def __init__(
        self,
        *,
        storage: _AnalysisStorage,
        official_docs_retriever: OfficialDocsRetriever,
        llm_client: LLMClient | None,
        repository_root: Path,
        temp_parent: Path | None = None,
    ) -> None:
        self._storage = storage
        self._official_docs_retriever = official_docs_retriever
        self._llm_client = llm_client
        self._repository_root = repository_root
        self._temp_parent = temp_parent
        self._citation_guard: CitationGuard | None = None
        self._document_ref: str | None = None
        self._artifact_lock = asyncio.Lock()

    async def analyze(
        self,
        archive_bytes: bytes,
        *,
        report_language: str,
        llm_review: bool,
    ) -> AnalysisResponse:
        if report_language != "zh-CN":
            raise ValueError("report_language 不受支持")
        if not isinstance(llm_review, bool):
            raise TypeError("llm_review 必须是 bool")

        analysis_id = f"analysis-{uuid.uuid4().hex}"
        started_total = time.perf_counter()
        phase_timings = _TimingAccumulator()
        timed_retriever = _TimedRetriever(
            self._official_docs_retriever,
            phase_timings,
        )
        timed_llm = (
            _TimedLLM(self._llm_client, phase_timings)
            if llm_review and self._llm_client is not None
            else None
        )

        started_extract = time.perf_counter()
        with ZipGuard(
            archive_bytes,
            temp_parent=self._temp_parent,
        ) as validated:
            extract_ms = _called_elapsed_ms(started_extract)
            started_scan = time.perf_counter()
            ast_result = ASTScanner().scan(validated)
            rule_result = RuleScanner().scan(ast_result)
            graph = ImportGraphBuilder().build(ast_result.registry)
            impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
            scan_ms = _called_elapsed_ms(started_scan)

            repository = RepositorySummary(
                python_files=validated.python_file_count,
                python_loc=validated.python_total_lines,
                direct_finding_count=len(rule_result.findings),
                directly_affected_files=len(impact.direct_files),
                one_hop_dependent_files=len(
                    {item.importer_relative_path for item in impact.one_hop_importers}
                ),
            )
            tools = AnalysisToolSet(
                AnalysisToolContext(
                    validated=validated,
                    rule_result=rule_result,
                    import_graph=graph,
                    official_docs_retriever=timed_retriever,
                    trace_sink=InMemoryToolAuditSink(),
                )
            )
            agent_result = await BoundedAnalysisAgent(
                tools=tools,
                llm_client=timed_llm,
            ).run(
                AgentRunRequest(
                    analysis_id=analysis_id,
                    repo_summary=repository,
                    rule_result=rule_result,
                    one_hop_importers=impact.one_hop_importers,
                    llm_review=llm_review,
                )
            )
            citation_guard, document_ref = await self._trusted_artifacts()
            report = await FinalReportBuilder(
                citation_guard,
                llm_client=timed_llm,
                llm_review=llm_review,
            ).build(agent_result)

        report_json = render_report_json(report)
        report_markdown = render_report_markdown(report)
        wall_total_ms = _called_elapsed_ms(started_total)
        timings = AnalysisTimings(
            extract=extract_ms,
            scan=scan_ms,
            retrieve=phase_timings.retrieve,
            llm=phase_timings.llm,
            total=max(
                wall_total_ms,
                extract_ms + scan_ms + phase_timings.retrieve + phase_timings.llm,
            ),
        )
        created_at_utc = datetime.now(tz=UTC).isoformat()
        response = _build_response(
            report,
            document_ref=document_ref,
            model=_model_identity(report),
            timings=timings,
            created_at_utc=created_at_utc,
        )
        response_json = json.dumps(
            response.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        await self._storage.save_analysis(
            StoredAnalysis(
                analysis_id=analysis_id,
                status=report.status.value,
                report_language="zh-CN",
                scanner_version=__version__,
                document_ref=document_ref,
                model=response.model,
                llm_review=llm_review,
                created_at_utc=created_at_utc,
                response_json=response_json,
                report_json=report_json,
                report_markdown=report_markdown,
            )
        )
        return response

    async def _trusted_artifacts(self) -> tuple[CitationGuard, str]:
        if self._citation_guard is not None and self._document_ref is not None:
            return self._citation_guard, self._document_ref
        async with self._artifact_lock:
            if self._citation_guard is None or self._document_ref is None:
                guard = CitationGuard.from_repository(self._repository_root)
                manifest = SnapshotManifest.model_validate_json(
                    (self._repository_root / MANIFEST_PATH).read_bytes()
                )
                self._citation_guard = guard
                self._document_ref = (
                    f"{manifest.source_id}:{manifest.git_ref}"
                    f"@{manifest.resolved_commit_sha}"
                )
        return self._citation_guard, self._document_ref


def _called_elapsed_ms(started: float) -> int:
    return max(1, math.ceil((time.perf_counter() - started) * 1000))


def _model_identity(report: FinalReport) -> str:
    identities = {
        item.explanation.model
        for item in report.findings
        if item.explanation.source is ReportExplanationSource.AGENT_CANDIDATE
        and item.explanation.model is not None
    }
    if not identities:
        return "deterministic-fallback"
    if len(identities) != 1:
        raise RuntimeError("最终报告包含不一致的模型 identity")
    return next(iter(identities))


def _build_response(
    report: FinalReport,
    *,
    document_ref: str,
    model: str,
    timings: AnalysisTimings,
    created_at_utc: str,
) -> AnalysisResponse:
    counts = {severity: 0 for severity in Severity}
    for item in report.findings:
        counts[item.finding.severity] += 1
    return AnalysisResponse(
        analysis_id=report.analysis_id,
        status=report.status,
        degraded_reason=report.degraded_reason,
        scanner_version=__version__,
        document_ref=document_ref,
        model=model,
        report_language=report.language.value,
        repository=report.repo_summary,
        summary=AnalysisSummary(
            high=counts[Severity.HIGH],
            medium=counts[Severity.MEDIUM],
            low=counts[Severity.LOW],
            human_review=len(report.human_review_items),
        ),
        findings=report.findings,
        one_hop_importers=report.one_hop_importers,
        citation_retry_count=report.citation_retry_count,
        citation_validation=report.citation_validation,
        human_review_items=report.human_review_items,
        limitations=report.limitations,
        timings_ms=timings,
        created_at_utc=created_at_utc,
    )
