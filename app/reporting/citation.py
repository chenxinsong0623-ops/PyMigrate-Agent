"""基于固定本地 artifact 与当前分析交集的 Citation Guard。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from app.agent import AgentRunResult, OfficialDocChunk, SelectedDocCandidate
from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    ChunkError,
    MarkdownChunk,
    audit_chunk_artifact,
    calculate_chunk_id,
    load_chunk_artifact,
)
from app.ingestion.pydantic_snapshot import (
    MANIFEST_PATH,
    SOURCE_UPSTREAM_REPO,
    SnapshotError,
    SnapshotManifest,
    calculate_sha256,
)
from app.scanner import Finding, get_rule_spec

from .models import (
    CitationErrorType,
    CitationGuardResult,
    CitationSupportStatus,
    CitationValidationItem,
    CitationValidity,
    ValidatedCitation,
)


class CitationGuard:
    """离线、fail-closed 地校验 Day 19 未验证引用候选。"""

    def __init__(
        self,
        *,
        trusted_chunks: tuple[MarkdownChunk, ...],
        trust_available: bool,
    ) -> None:
        self._trusted_chunks = {item.chunk_id: item for item in trusted_chunks}
        self._trust_available = trust_available

    @classmethod
    def from_repository(cls, repo_root: Path) -> CitationGuard:
        """只读加载并独立验证 Day 8/9 正式本地来源；不访问网络。"""
        try:
            root = repo_root.resolve()
            manifest = SnapshotManifest.model_validate_json(
                (root / MANIFEST_PATH).read_bytes()
            )
            artifact = load_chunk_artifact(root / CHUNK_ARTIFACT_PATH)
            source_bytes = (root / manifest.snapshot_path).read_bytes()
            source = source_bytes.decode("utf-8")
            _validate_trusted_bundle(manifest, artifact, source_bytes, source)
        except (
            SnapshotError,
            ChunkError,
            OSError,
            UnicodeError,
            ValidationError,
            ValueError,
        ):
            return cls(trusted_chunks=(), trust_available=False)
        return cls(trusted_chunks=artifact.chunks, trust_available=True)

    def validate(self, result: AgentRunResult) -> CitationGuardResult:
        """建立 current-analysis allowlist，再校验候选 identity/binding。"""
        if not isinstance(result, AgentRunResult):
            raise TypeError("result 必须是 AgentRunResult")
        if not self._trust_available:
            return CitationGuardResult(
                analysis_id=result.analysis_id,
                trust_available=False,
                allowlisted_chunk_ids=(),
                valid_citations=(),
                items=_trusted_source_failure_items(result),
            )

        current_chunks: dict[str, OfficialDocChunk] = {}
        current_errors: dict[str, CitationErrorType] = {}
        for retrieved in result.retrieved_chunks:
            trusted = self._trusted_chunks.get(retrieved.chunk_id)
            if trusted is None:
                current_errors[retrieved.chunk_id] = (
                    CitationErrorType.SOURCE_IDENTITY_MISMATCH
                )
                continue
            error = _retrieved_provenance_error(retrieved, trusted)
            if error is None:
                current_chunks[retrieved.chunk_id] = retrieved
            else:
                current_errors[retrieved.chunk_id] = error

        candidates = result.draft_report.selected_doc_candidates
        duplicate_keys = {
            key
            for key, count in Counter(
                (item.analysis_id, item.group_id, item.chunk_id) for item in candidates
            ).items()
            if count > 1
        }
        items: list[CitationValidationItem] = []
        citations: list[ValidatedCitation] = []
        referenced_chunk_ids: set[str] = set()
        for candidate in candidates:
            referenced_chunk_ids.add(candidate.chunk_id)
            duplicate = (
                candidate.analysis_id,
                candidate.group_id,
                candidate.chunk_id,
            ) in duplicate_keys
            item, citation = self._validate_candidate(
                result,
                candidate,
                current_chunks,
                current_errors,
                duplicate=duplicate,
            )
            items.append(item)
            if citation is not None:
                citations.append(citation)

        candidate_groups = {item.group_id for item in candidates}
        for group in result.ambiguous_groups:
            if group.group_id not in candidate_groups:
                items.append(
                    _invalid_item(
                        result.analysis_id,
                        CitationErrorType.NO_CANDIDATE,
                        group_id=group.group_id,
                        finding_ids=group.finding_ids,
                        retry_eligible=True,
                    )
                )
        for chunk_id, error in current_errors.items():
            if chunk_id not in referenced_chunk_ids:
                items.append(
                    _invalid_item(
                        result.analysis_id,
                        error,
                        chunk_id=chunk_id,
                    )
                )

        ordered_citations = tuple(
            sorted(
                citations,
                key=lambda item: (item.group_id, item.chunk_id, item.finding_ids),
            )
        )
        ordered_items = tuple(sorted(items, key=_validation_item_sort_key))
        return CitationGuardResult(
            analysis_id=result.analysis_id,
            trust_available=True,
            allowlisted_chunk_ids=tuple(sorted(current_chunks)),
            valid_citations=ordered_citations,
            items=ordered_items,
        )

    def _validate_candidate(
        self,
        result: AgentRunResult,
        candidate: SelectedDocCandidate,
        current_chunks: dict[str, OfficialDocChunk],
        current_errors: dict[str, CitationErrorType],
        *,
        duplicate: bool,
    ) -> tuple[CitationValidationItem, ValidatedCitation | None]:
        if candidate.analysis_id != result.analysis_id:
            return (
                _candidate_error(
                    result,
                    candidate,
                    CitationErrorType.CROSS_ANALYSIS_CHUNK,
                ),
                None,
            )
        group_by_id = {item.group_id: item for item in result.ambiguous_groups}
        group = group_by_id.get(candidate.group_id)
        if group is None:
            return (
                _candidate_error(result, candidate, CitationErrorType.UNKNOWN_GROUP),
                None,
            )
        known_finding_ids = set(result.finding_ids)
        if not set(candidate.finding_ids).issubset(known_finding_ids):
            return (
                _candidate_error(result, candidate, CitationErrorType.UNKNOWN_FINDING),
                None,
            )
        if candidate.finding_ids != group.finding_ids:
            return (
                _candidate_error(
                    result,
                    candidate,
                    CitationErrorType.FINDING_GROUP_MISMATCH,
                ),
                None,
            )
        finding_by_id = dict(zip(result.finding_ids, result.findings, strict=True))
        findings = tuple(finding_by_id[item] for item in group.finding_ids)
        if any(finding.rule_id is not group.rule_id for finding in findings):
            return (
                _candidate_error(result, candidate, CitationErrorType.RULE_MISMATCH),
                None,
            )
        if duplicate:
            return (
                _candidate_error(
                    result,
                    candidate,
                    CitationErrorType.DUPLICATE_CITATION,
                ),
                None,
            )
        if candidate.chunk_id not in current_chunks:
            if candidate.chunk_id in current_errors:
                error = current_errors[candidate.chunk_id]
                retry = False
            elif candidate.chunk_id in self._trusted_chunks:
                error = CitationErrorType.CROSS_ANALYSIS_CHUNK
                retry = False
            else:
                error = CitationErrorType.FORGED_CHUNK_ID
                retry = True
            return (
                _candidate_error(result, candidate, error, retry_eligible=retry),
                None,
            )

        bindings = tuple(
            item
            for item in result.retrieval_bindings
            if item.group_id == group.group_id and candidate.chunk_id in item.chunk_ids
        )
        if not bindings:
            return (
                _candidate_error(
                    result,
                    candidate,
                    CitationErrorType.QUERY_BINDING_MISSING,
                ),
                None,
            )
        binding = bindings[0]
        if len(bindings) != 1 or (
            binding.rule_id is not group.rule_id
            or binding.finding_ids != group.finding_ids
        ):
            return (
                _candidate_error(
                    result,
                    candidate,
                    CitationErrorType.QUERY_BINDING_MISMATCH,
                ),
                None,
            )
        expected_terms = _expected_rule_terms(findings)
        if not binding.matched_query_terms or not all(
            item.casefold() in expected_terms for item in binding.matched_query_terms
        ):
            return (
                _candidate_error(
                    result,
                    candidate,
                    CitationErrorType.QUERY_BINDING_MISMATCH,
                ),
                None,
            )

        trusted = self._trusted_chunks[candidate.chunk_id]
        if not any(term in trusted.text.casefold() for term in expected_terms):
            return (
                _candidate_error(
                    result,
                    candidate,
                    CitationErrorType.KEYWORD_MISMATCH,
                    retry_eligible=True,
                ),
                None,
            )

        citation = ValidatedCitation(
            analysis_id=result.analysis_id,
            group_id=group.group_id,
            finding_ids=group.finding_ids,
            rule_id=group.rule_id,
            chunk_id=trusted.chunk_id,
            source_id=trusted.source_id,
            source_url=trusted.source_url,
            git_ref=trusted.git_ref,
            resolved_commit_sha=trusted.resolved_commit_sha,
            source_path=trusted.source_path,
            heading_path=trusted.heading_path,
            content_sha256=trusted.content_sha256,
            source_snapshot_sha256=trusted.source_snapshot_sha256,
            validity=CitationValidity.VALID,
            support_status=CitationSupportStatus.NOT_EVALUATED,
        )
        return (
            CitationValidationItem(
                analysis_id=result.analysis_id,
                group_id=group.group_id,
                finding_ids=group.finding_ids,
                chunk_id=trusted.chunk_id,
                validity=CitationValidity.VALID,
                error_type=None,
                retry_eligible=False,
            ),
            citation,
        )


def _validate_trusted_bundle(
    manifest: SnapshotManifest,
    artifact,
    source_bytes: bytes,
    source: str,
) -> None:
    raw_repository = SOURCE_UPSTREAM_REPO.replace(
        "github.com", "raw.githubusercontent.com"
    )
    expected_source_url = (
        f"{raw_repository}/{manifest.resolved_commit_sha}/{manifest.path}"
    )
    if (
        manifest.source_url != expected_source_url
        or artifact.source_id != manifest.source_id
        or artifact.source_url != manifest.source_url
        or artifact.git_ref != manifest.git_ref
        or artifact.resolved_commit_sha != manifest.resolved_commit_sha
        or artifact.source_path != manifest.path
        or artifact.source_snapshot_path != manifest.snapshot_path
        or artifact.source_snapshot_sha256 != manifest.sha256
        or artifact.source_snapshot_byte_length != manifest.byte_length
        or calculate_sha256(source_bytes) != manifest.sha256
        or len(source_bytes) != manifest.byte_length
    ):
        raise ValueError("trusted artifact provenance mismatch")
    audit_chunk_artifact(source, artifact)
    for chunk in artifact.chunks:
        if chunk.chunk_id != calculate_chunk_id(
            source_id=chunk.source_id,
            source_path=chunk.source_path,
            heading_path=chunk.heading_path,
            text=chunk.text,
            identity_occurrence=chunk.identity_occurrence,
        ):
            raise ValueError("trusted chunk identity mismatch")


def _retrieved_provenance_error(
    retrieved: OfficialDocChunk,
    trusted: MarkdownChunk,
) -> CitationErrorType | None:
    if (
        retrieved.source_id != trusted.source_id
        or retrieved.source_path != trusted.source_path
    ):
        return CitationErrorType.SOURCE_IDENTITY_MISMATCH
    if retrieved.source_url != trusted.source_url:
        return CitationErrorType.URL_MISMATCH
    if retrieved.git_ref != trusted.git_ref:
        return CitationErrorType.REF_MISMATCH
    if retrieved.resolved_commit_sha != trusted.resolved_commit_sha:
        return CitationErrorType.COMMIT_MISMATCH
    if retrieved.heading_path != trusted.heading_path:
        return CitationErrorType.HEADING_MISMATCH
    if retrieved.content_sha256 != trusted.content_sha256:
        return CitationErrorType.CONTENT_HASH_MISMATCH
    if retrieved.source_snapshot_sha256 != trusted.source_snapshot_sha256:
        return CitationErrorType.SOURCE_HASH_MISMATCH
    expected_text = trusted.text[: len(retrieved.text)]
    if (
        retrieved.full_text_characters != len(trusted.text)
        or retrieved.text != expected_text
        or retrieved.text_truncated != (len(retrieved.text) < len(trusted.text))
    ):
        return CitationErrorType.TEXT_MISMATCH
    return None


def _expected_rule_terms(findings: tuple[Finding, ...]) -> set[str]:
    rule_spec = get_rule_spec(findings[0].rule_id)
    values = {
        findings[0].rule_id.value,
        findings[0].rule_id.value.removeprefix("pydantic_v1_"),
        rule_spec.category.value,
        rule_spec.category.value.replace("_", " "),
        *rule_spec.old_apis,
        *(item.old_api for item in findings),
    }
    return {item.casefold() for item in values if item}


def _trusted_source_failure_items(
    result: AgentRunResult,
) -> tuple[CitationValidationItem, ...]:
    if result.ambiguous_groups:
        return tuple(
            _invalid_item(
                result.analysis_id,
                CitationErrorType.TRUSTED_SOURCE_INVALID,
                group_id=group.group_id,
                finding_ids=group.finding_ids,
            )
            for group in result.ambiguous_groups
        )
    return ()


def _candidate_error(
    result: AgentRunResult,
    candidate: SelectedDocCandidate,
    error: CitationErrorType,
    *,
    retry_eligible: bool = False,
) -> CitationValidationItem:
    return _invalid_item(
        result.analysis_id,
        error,
        group_id=candidate.group_id,
        finding_ids=tuple(sorted(set(candidate.finding_ids))),
        chunk_id=candidate.chunk_id,
        retry_eligible=retry_eligible,
    )


def _invalid_item(
    analysis_id: str,
    error: CitationErrorType,
    *,
    group_id: str | None = None,
    finding_ids: tuple[str, ...] = (),
    chunk_id: str | None = None,
    retry_eligible: bool = False,
) -> CitationValidationItem:
    return CitationValidationItem(
        analysis_id=analysis_id,
        group_id=group_id,
        finding_ids=finding_ids,
        chunk_id=chunk_id,
        validity=CitationValidity.INVALID,
        error_type=error,
        retry_eligible=retry_eligible,
    )


def _validation_item_sort_key(
    item: CitationValidationItem,
) -> tuple[str, str, str, str]:
    return (
        item.group_id or "",
        item.chunk_id or "",
        item.error_type.value if item.error_type is not None else "",
        ",".join(item.finding_ids),
    )
