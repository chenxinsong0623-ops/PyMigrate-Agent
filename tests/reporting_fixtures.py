from __future__ import annotations

import hashlib
from pathlib import Path

from app.agent import (
    AgentDraft,
    AgentRunResult,
    AgentTerminalStatus,
    OfficialDocChunk,
    RepositorySummary,
    RetrievalBinding,
    SelectedDocCandidate,
    finding_identity,
    prepare_ambiguous_groups,
)
from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    MarkdownChunk,
    load_chunk_artifact,
)
from app.scanner import (
    Confidence,
    EvidenceFact,
    EvidenceKey,
    Finding,
    FindingLocation,
    MatchedConstruct,
    OneHopImporter,
    RuleCategory,
    RuleId,
    Severity,
)


def trusted_chunk_containing(term: str) -> MarkdownChunk:
    artifact = load_chunk_artifact(Path(CHUNK_ARTIFACT_PATH))
    return next(
        chunk for chunk in artifact.chunks if term.casefold() in chunk.text.casefold()
    )


def official_chunk(chunk: MarkdownChunk) -> OfficialDocChunk:
    return OfficialDocChunk(
        rank=1,
        rrf_score=1 / 61,
        bm25_rank=1,
        bm25_score=2.0,
        dense_rank=None,
        dense_score=None,
        chunk_id=chunk.chunk_id,
        heading_path=chunk.heading_path,
        text=chunk.text,
        full_text_characters=len(chunk.text),
        text_truncated=False,
        content_sha256=chunk.content_sha256,
        source_id=chunk.source_id,
        source_url=chunk.source_url,
        git_ref=chunk.git_ref,
        resolved_commit_sha=chunk.resolved_commit_sha,
        source_path=chunk.source_path,
        source_snapshot_sha256=chunk.source_snapshot_sha256,
    )


def root_finding(*, old_api: str = "__root__", line: int = 3) -> Finding:
    return Finding(
        rule_id=RuleId.PYDANTIC_V1_ROOT_MODEL,
        category=RuleCategory.ROOT_MODEL,
        relative_path="pkg/models.py",
        location=FindingLocation(
            start_line=line,
            start_column=4,
            end_line=line,
            end_column=12,
        ),
        old_api=old_api,
        matched_construct=MatchedConstruct.ROOT_FIELD,
        evidence=(EvidenceFact(key=EvidenceKey.MODEL_EVIDENCE, value="direct"),),
        confidence=Confidence.HIGH,
        severity=Severity.MEDIUM,
        requires_manual_review=False,
    )


def make_agent_result(
    *,
    analysis_id: str = "analysis-day20",
    chunk: MarkdownChunk | None = None,
    retrieved: OfficialDocChunk | None = None,
    candidate_chunk_id: str | None = None,
    include_candidate: bool = True,
    include_binding: bool = True,
    matched_query_terms: tuple[str, ...] = ("__root__",),
    old_api: str = "__root__",
    degraded_reason=None,
) -> AgentRunResult:
    selected_chunk = chunk or trusted_chunk_containing("__root__")
    selected_retrieved = retrieved or official_chunk(selected_chunk)
    finding = root_finding(old_api=old_api)
    group = prepare_ambiguous_groups((finding,)).groups[0]
    finding_id = finding_identity(finding)
    candidates = (
        (
            SelectedDocCandidate(
                analysis_id=analysis_id,
                group_id=group.group_id,
                finding_ids=group.finding_ids,
                chunk_id=candidate_chunk_id or selected_chunk.chunk_id,
            ),
        )
        if include_candidate
        else ()
    )
    bindings = (
        (
            RetrievalBinding(
                group_id=group.group_id,
                rule_id=group.rule_id,
                finding_ids=group.finding_ids,
                query_sha256="sha256:"
                + hashlib.sha256(b"__root__ migration").hexdigest(),
                matched_query_terms=matched_query_terms,
                chunk_ids=(selected_retrieved.chunk_id,),
            ),
        )
        if include_binding
        else ()
    )
    one_hop = (
        OneHopImporter(
            direct_relative_path="pkg/models.py",
            direct_module="pkg.models",
            importer_relative_path="pkg/service.py",
            importer_module="pkg.service",
        ),
    )
    return AgentRunResult(
        analysis_id=analysis_id,
        repo_summary=RepositorySummary(
            python_files=2,
            python_loc=5,
            direct_finding_count=1,
            directly_affected_files=1,
            one_hop_dependent_files=1,
        ),
        findings=(finding,),
        finding_ids=(finding_id,),
        one_hop_importers=one_hop,
        ambiguous_groups=(group,),
        retrieved_chunks=(selected_retrieved,),
        retrieval_bindings=bindings,
        agent_steps=(),
        draft_report=AgentDraft(
            explanations=(),
            selected_doc_candidates=candidates,
            human_review_items=(),
        ),
        validation_errors=(),
        degraded_reason=degraded_reason,
        terminal_status=(
            AgentTerminalStatus.COMPLETED
            if degraded_reason is None
            else AgentTerminalStatus.DEGRADED
        ),
        tool_calls_used=1,
        llm_calls_used=1,
        reviewed_finding_ids=group.finding_ids,
        retry_count=0,
    )


def make_multi_agent_result() -> AgentRunResult:
    """构造同一 rule/group 下的两个 deterministic findings。"""
    chunk = trusted_chunk_containing("__root__")
    retrieved = official_chunk(chunk)
    findings = (root_finding(line=3), root_finding(line=4))
    finding_ids = tuple(finding_identity(item) for item in findings)
    group = prepare_ambiguous_groups(findings).groups[0]
    return AgentRunResult(
        analysis_id="analysis-day20-multi",
        repo_summary=RepositorySummary(
            python_files=2,
            python_loc=6,
            direct_finding_count=2,
            directly_affected_files=1,
            one_hop_dependent_files=1,
        ),
        findings=findings,
        finding_ids=finding_ids,
        one_hop_importers=(
            OneHopImporter(
                direct_relative_path="pkg/models.py",
                direct_module="pkg.models",
                importer_relative_path="pkg/service.py",
                importer_module="pkg.service",
            ),
        ),
        ambiguous_groups=(group,),
        retrieved_chunks=(retrieved,),
        retrieval_bindings=(
            RetrievalBinding(
                group_id=group.group_id,
                rule_id=group.rule_id,
                finding_ids=group.finding_ids,
                query_sha256="sha256:"
                + hashlib.sha256(b"__root__ migration").hexdigest(),
                matched_query_terms=("__root__",),
                chunk_ids=(chunk.chunk_id,),
            ),
        ),
        agent_steps=(),
        draft_report=AgentDraft(
            explanations=(),
            selected_doc_candidates=(
                SelectedDocCandidate(
                    analysis_id="analysis-day20-multi",
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    chunk_id=chunk.chunk_id,
                ),
            ),
            human_review_items=(),
        ),
        validation_errors=(),
        degraded_reason=None,
        terminal_status=AgentTerminalStatus.COMPLETED,
        tool_calls_used=1,
        llm_calls_used=1,
        reviewed_finding_ids=group.finding_ids,
        retry_count=0,
    )
