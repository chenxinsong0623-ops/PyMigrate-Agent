"""把已验证的 Day 8 Markdown snapshot 转换为稳定的离线 chunks。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.ingestion.pydantic_snapshot import (
    MANIFEST_PATH,
    SOURCE_UPSTREAM_REPO,
    SnapshotManifest,
    calculate_sha256,
)

CHUNK_ARTIFACT_PATH = "data/chunks/pydantic-v2-migration.json"
CHUNK_SCHEMA_VERSION = 1
DEFAULT_MIN_CHARS = 500
DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 120

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_CHUNK_ID_PATTERN = r"^sha256:[0-9a-f]{64}$"
_FENCE_OPEN_PATTERN = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})(?P<info>[^\r\n]*)$")
_HEADING_PATTERN = re.compile(r"^[ ]{0,3}(?P<marks>#{2,3})[ \t]+(?P<title>.*?)[ \t]*$")
_PARAGRAPH_BOUNDARY_PATTERN = re.compile(r"(?:\r?\n)[ \t]*(?:\r?\n)")
_LINE_BOUNDARY_PATTERN = re.compile(r"\r?\n")
_SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.!?。！？][\"')\]]*[ \t]+")
_WHITESPACE_BOUNDARY_PATTERN = re.compile(r"\s+")


class ChunkError(RuntimeError):
    """Day 9 离线 chunk 构建的受控基础异常。"""


class ChunkSourceValidationError(ChunkError):
    """Day 8 manifest 或 raw snapshot 未通过完整性验证。"""


class MarkdownChunkingError(ChunkError):
    """Markdown 结构、chunk 或 artifact 未通过确定性契约。"""


class ChunkArtifactPublishError(ChunkError):
    """已验证的单一 chunk artifact 无法安全发布。"""


def calculate_text_sha256(text: str) -> str:
    """计算最终 chunk text UTF-8 bytes 的 lowercase SHA256。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def calculate_chunk_id(
    *,
    source_id: str,
    source_path: str,
    heading_path: tuple[str, ...],
    text: str,
    identity_occurrence: int,
) -> str:
    """公开重算 Day 9 内容 identity，供后续可信引用边界复核。"""
    if (
        isinstance(identity_occurrence, bool)
        or not isinstance(identity_occurrence, int)
        or identity_occurrence < 0
    ):
        raise ValueError("identity occurrence 必须是非负整数")
    identity_base = _canonical_chunk_identity(
        source_id=source_id,
        source_path=source_path,
        heading_path=heading_path,
        text=text,
    )
    return _chunk_id(identity_base, identity_occurrence)


class MarkdownChunk(BaseModel):
    """Day 10 和后续引用边界可直接消费的不可变 chunk。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(pattern=_CHUNK_ID_PATTERN)
    text: str = Field(min_length=1)
    heading_path: tuple[str, ...]
    content_sha256: str = Field(pattern=_SHA256_PATTERN)
    char_length: int = Field(gt=0)
    source_id: Literal["pydantic-v2-migration"]
    source_url: str = Field(min_length=1)
    git_ref: str = Field(min_length=1)
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: Literal["docs/migration.md"]
    source_snapshot_sha256: str = Field(pattern=_SHA256_PATTERN)
    source_start_char: int = Field(ge=0)
    source_end_char: int = Field(gt=0)
    continuation_index: int = Field(ge=0)
    overlap_chars: int = Field(ge=0, le=150)
    identity_occurrence: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_derived_fields(self) -> Self:
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("heading_path entries must be non-empty")
        if self.char_length != len(self.text):
            raise ValueError("char_length does not match chunk text")
        if self.source_end_char - self.source_start_char != self.char_length:
            raise ValueError("source character span does not match chunk text")
        if calculate_text_sha256(self.text) != self.content_sha256:
            raise ValueError("content_sha256 does not match chunk text")
        if self.continuation_index == 0 and self.overlap_chars != 0:
            raise ValueError("first structural chunk cannot have overlap")
        return self


class ChunkArtifact(BaseModel):
    """确定性 JSON schema v1 chunk artifact。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    source_id: Literal["pydantic-v2-migration"]
    source_url: str = Field(min_length=1)
    git_ref: str = Field(min_length=1)
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: Literal["docs/migration.md"]
    source_snapshot_path: Literal["data/snapshots/pydantic-v2-migration/migration.md"]
    source_snapshot_sha256: str = Field(pattern=_SHA256_PATTERN)
    source_snapshot_byte_length: int = Field(gt=0)
    source_retrieved_at_utc: str = Field(min_length=1)
    min_chars: int = Field(gt=0)
    max_chars: int = Field(gt=0)
    overlap_chars: int = Field(ge=100, le=150)
    chunks: tuple[MarkdownChunk, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        if self.min_chars > self.max_chars:
            raise ValueError("min_chars cannot exceed max_chars")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")

        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("chunk IDs must be unique")

        previous_start = -1
        for chunk in self.chunks:
            if chunk.source_start_char <= previous_start:
                raise ValueError("chunks must keep strictly increasing document order")
            previous_start = chunk.source_start_char
            if chunk.source_id != self.source_id:
                raise ValueError("chunk source_id does not match artifact")
            if chunk.source_url != self.source_url:
                raise ValueError("chunk source_url does not match artifact")
            if chunk.git_ref != self.git_ref:
                raise ValueError("chunk git_ref does not match artifact")
            if chunk.resolved_commit_sha != self.resolved_commit_sha:
                raise ValueError("chunk resolved commit does not match artifact")
            if chunk.source_path != self.source_path:
                raise ValueError("chunk source path does not match artifact")
            if chunk.source_snapshot_sha256 != self.source_snapshot_sha256:
                raise ValueError("chunk snapshot hash does not match artifact")
            if chunk.overlap_chars not in {0, self.overlap_chars}:
                raise ValueError("chunk overlap does not match artifact contract")
        return self


@dataclass(frozen=True, slots=True)
class ChunkAudit:
    """从 source 与最终 artifact 重新计算的完整性统计。"""

    chunk_count: int
    min_char_length: int
    max_char_length: int
    target_range_count: int
    short_structural_count: int
    oversized_structural_count: int
    oversized_code_block_count: int
    continuation_chunk_count: int
    overlap_chunk_count: int
    unique_chunk_id_count: int
    chunk_id_collision_count: int
    unique_content_hash_count: int
    duplicate_content_hash_count: int
    source_fenced_block_count: int
    preserved_fenced_block_count: int
    source_block_count: int
    covered_source_block_count: int
    source_character_count: int
    covered_character_count: int
    coverage_gap_count: int


ChunkBuildState = Literal["written", "unchanged"]


@dataclass(frozen=True, slots=True)
class ChunkBuildResult:
    """显式 Day 9 builder 返回的 artifact 与独立审计结果。"""

    artifact: ChunkArtifact
    audit: ChunkAudit
    build_state: ChunkBuildState
    output_path: Path
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class _FenceSpan:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _SemanticSection:
    start: int
    end: int
    heading_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ChunkSpan:
    start: int
    end: int
    heading_path: tuple[str, ...]
    continuation_index: int
    overlap_chars: int


class MarkdownChunkBuilder:
    """验证 Day 8 source 并离线构建 deterministic Markdown chunks。"""

    def __init__(
        self,
        *,
        repo_root: Path,
        manifest_path: str = MANIFEST_PATH,
        output_path: str = CHUNK_ARTIFACT_PATH,
        min_chars: int = DEFAULT_MIN_CHARS,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> None:
        resolved_root = repo_root.resolve()
        if not resolved_root.is_dir():
            raise ValueError("repo_root 必须是已存在目录")
        self._validate_length_contract(min_chars, max_chars, overlap_chars)
        self._repo_root = resolved_root
        self._manifest_path = manifest_path
        self._output_path = output_path
        self._min_chars = min_chars
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    @staticmethod
    def _validate_length_contract(
        min_chars: int,
        max_chars: int,
        overlap_chars: int,
    ) -> None:
        values = (min_chars, max_chars, overlap_chars)
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in values
        ):
            raise ValueError("chunk length contract must use integers")
        if min_chars <= 0 or max_chars < min_chars:
            raise ValueError("chunk min/max contract is invalid")
        if not 100 <= overlap_chars <= 150 or overlap_chars >= max_chars:
            raise ValueError("chunk overlap must be 100..150 and smaller than max")

    def build(self) -> ChunkBuildResult:
        """从正式本地 snapshot 构建或幂等验证单一 chunk artifact。"""
        manifest, source = self._load_verified_source()
        sections, source_fences = _parse_semantic_sections(source)
        chunk_spans: list[_ChunkSpan] = []
        for section in sections:
            chunk_spans.extend(self._chunk_section(source, section, source_fences))
        if not chunk_spans:
            raise MarkdownChunkingError("validated source produced no chunks")

        identity_occurrences: dict[bytes, int] = {}
        chunks: list[MarkdownChunk] = []
        for span in chunk_spans:
            text = source[span.start : span.end]
            identity_base = _canonical_chunk_identity(
                source_id=manifest.source_id,
                source_path=manifest.path,
                heading_path=span.heading_path,
                text=text,
            )
            identity_occurrence = identity_occurrences.get(identity_base, 0)
            identity_occurrences[identity_base] = identity_occurrence + 1
            chunk_id = calculate_chunk_id(
                source_id=manifest.source_id,
                source_path=manifest.path,
                heading_path=span.heading_path,
                text=text,
                identity_occurrence=identity_occurrence,
            )
            chunks.append(
                MarkdownChunk(
                    chunk_id=chunk_id,
                    text=text,
                    heading_path=span.heading_path,
                    content_sha256=calculate_text_sha256(text),
                    char_length=len(text),
                    source_id=manifest.source_id,
                    source_url=manifest.source_url,
                    git_ref=manifest.git_ref,
                    resolved_commit_sha=manifest.resolved_commit_sha,
                    source_path=manifest.path,
                    source_snapshot_sha256=manifest.sha256,
                    source_start_char=span.start,
                    source_end_char=span.end,
                    continuation_index=span.continuation_index,
                    overlap_chars=span.overlap_chars,
                    identity_occurrence=identity_occurrence,
                )
            )

        artifact = ChunkArtifact(
            schema_version=CHUNK_SCHEMA_VERSION,
            source_id=manifest.source_id,
            source_url=manifest.source_url,
            git_ref=manifest.git_ref,
            resolved_commit_sha=manifest.resolved_commit_sha,
            source_path=manifest.path,
            source_snapshot_path=manifest.snapshot_path,
            source_snapshot_sha256=manifest.sha256,
            source_snapshot_byte_length=manifest.byte_length,
            source_retrieved_at_utc=manifest.retrieved_at_utc,
            min_chars=self._min_chars,
            max_chars=self._max_chars,
            overlap_chars=self._overlap_chars,
            chunks=tuple(chunks),
        )
        audit = audit_chunk_artifact(source, artifact)
        serialized = _serialize_artifact(artifact)
        output_path = self._target(self._output_path)
        build_state = _publish_if_changed(output_path, serialized)

        round_trip = load_chunk_artifact(output_path)
        if round_trip != artifact:
            raise MarkdownChunkingError("chunk artifact round-trip changed content")
        round_trip_audit = audit_chunk_artifact(source, round_trip)
        if round_trip_audit != audit:
            raise MarkdownChunkingError("chunk artifact round-trip changed audit")
        return ChunkBuildResult(
            artifact=round_trip,
            audit=round_trip_audit,
            build_state=build_state,
            output_path=output_path,
            artifact_sha256=calculate_sha256(serialized),
        )

    def _load_verified_source(self) -> tuple[SnapshotManifest, str]:
        manifest_path = self._target(self._manifest_path)
        try:
            manifest = SnapshotManifest.model_validate_json(manifest_path.read_bytes())
        except (OSError, ValidationError, ValueError) as error:
            raise ChunkSourceValidationError(
                "Day 8 source manifest is missing or invalid"
            ) from error

        raw_repository = SOURCE_UPSTREAM_REPO.replace(
            "github.com", "raw.githubusercontent.com"
        )
        expected_url = (
            f"{raw_repository}/{manifest.resolved_commit_sha}/{manifest.path}"
        )
        if manifest.source_url != expected_url:
            raise ChunkSourceValidationError(
                "Day 8 source URL is not bound to manifest commit and path"
            )

        snapshot_path = self._target(manifest.snapshot_path)
        try:
            source_bytes = snapshot_path.read_bytes()
        except OSError as error:
            raise ChunkSourceValidationError(
                "Day 8 migration snapshot is missing"
            ) from error
        if calculate_sha256(source_bytes) != manifest.sha256:
            raise ChunkSourceValidationError(
                "Day 8 migration snapshot hash does not match manifest"
            )
        if len(source_bytes) != manifest.byte_length:
            raise ChunkSourceValidationError(
                "Day 8 migration snapshot length does not match manifest"
            )
        try:
            source = source_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ChunkSourceValidationError(
                "Day 8 migration snapshot is not valid UTF-8"
            ) from error
        if not source:
            raise ChunkSourceValidationError("Day 8 migration snapshot is empty")
        return manifest, source

    def _chunk_section(
        self,
        source: str,
        section: _SemanticSection,
        source_fences: tuple[_FenceSpan, ...],
    ) -> list[_ChunkSpan]:
        spans: list[_ChunkSpan] = []
        cursor = section.start
        continuation_index = 0
        incoming_overlap = 0
        while cursor < section.end:
            remaining = section.end - cursor
            suppress_overlap = False
            if remaining <= self._max_chars:
                end = section.end
            else:
                end, suppress_overlap = self._choose_end(
                    source,
                    cursor,
                    section.end,
                    source_fences,
                )
            if end <= cursor:
                raise MarkdownChunkingError("chunk cursor did not advance")
            spans.append(
                _ChunkSpan(
                    start=cursor,
                    end=end,
                    heading_path=section.heading_path,
                    continuation_index=continuation_index,
                    overlap_chars=incoming_overlap,
                )
            )
            if end == section.end:
                break

            next_cursor = end
            if not suppress_overlap:
                overlap_start = end - self._overlap_chars
                if overlap_start > cursor and not _position_inside_fence(
                    overlap_start,
                    source_fences,
                ):
                    next_cursor = overlap_start
            incoming_overlap = end - next_cursor
            cursor = next_cursor
            continuation_index += 1
        return spans

    def _choose_end(
        self,
        source: str,
        cursor: int,
        section_end: int,
        source_fences: tuple[_FenceSpan, ...],
    ) -> tuple[int, bool]:
        limit = min(cursor + self._max_chars, section_end)
        crossing = next(
            (
                span
                for span in source_fences
                if span.start < limit < span.end
                and span.end > cursor
                and span.start < section_end
            ),
            None,
        )
        if crossing is not None:
            if crossing.start > cursor:
                return crossing.start, True
            return min(crossing.end, section_end), True

        lower = min(cursor + self._min_chars, limit)
        segment = source[cursor:limit]
        for pattern in (
            _PARAGRAPH_BOUNDARY_PATTERN,
            _LINE_BOUNDARY_PATTERN,
            _SENTENCE_BOUNDARY_PATTERN,
            _WHITESPACE_BOUNDARY_PATTERN,
        ):
            candidates = [
                cursor + match.end()
                for match in pattern.finditer(segment)
                if lower <= cursor + match.end() <= limit
                and not _position_inside_fence(
                    cursor + match.end(),
                    source_fences,
                )
            ]
            if candidates:
                end = max(candidates)
                suppress_overlap = _next_oversized_code_requires_clean_start(
                    end,
                    self._max_chars,
                    self._overlap_chars,
                    source_fences,
                )
                return end, suppress_overlap
        if _position_inside_fence(limit, source_fences):
            raise MarkdownChunkingError("hard split would cut fenced code")
        return limit, False

    def _target(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ChunkSourceValidationError(
                "artifact path must be repository-relative"
            )
        target = (self._repo_root / candidate).resolve()
        try:
            target.relative_to(self._repo_root)
        except ValueError as error:
            raise ChunkSourceValidationError(
                "artifact path escapes repository"
            ) from error
        return target


def _canonical_chunk_identity(
    *,
    source_id: str,
    source_path: str,
    heading_path: tuple[str, ...],
    text: str,
) -> bytes:
    payload = {
        "heading_path": list(heading_path),
        "identity_schema": "migrationlens-chunk-id-v1",
        "source_id": source_id,
        "source_path": source_path,
        "text": text,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _chunk_id(identity_base: bytes, occurrence: int) -> str:
    digest_input = identity_base + b"\noccurrence=" + str(occurrence).encode("ascii")
    return "sha256:" + hashlib.sha256(digest_input).hexdigest()


def _parse_semantic_sections(
    source: str,
) -> tuple[tuple[_SemanticSection, ...], tuple[_FenceSpan, ...]]:
    if not source:
        raise MarkdownChunkingError("Markdown source is empty")

    sections: list[_SemanticSection] = []
    fences: list[_FenceSpan] = []
    section_start = 0
    current_path: tuple[str, ...] = ()
    current_h2: str | None = None
    fence_character: str | None = None
    fence_length = 0
    fence_start = 0
    offset = 0

    for line in source.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        logical_line = line.rstrip("\r\n")
        if fence_character is not None:
            if _is_closing_fence(logical_line, fence_character, fence_length):
                fences.append(_FenceSpan(fence_start, offset))
                fence_character = None
                fence_length = 0
            continue

        opening = _FENCE_OPEN_PATTERN.fullmatch(logical_line)
        if opening is not None:
            fence = opening.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            fence_start = line_start
            continue

        heading = _HEADING_PATTERN.fullmatch(logical_line)
        if heading is None:
            continue
        title = _normalize_heading_title(
            heading.group("marks"),
            heading.group("title"),
        )
        if line_start > section_start:
            sections.append(_SemanticSection(section_start, line_start, current_path))
        if len(heading.group("marks")) == 2:
            current_h2 = title
            current_path = (title,)
        else:
            current_path = (current_h2, title) if current_h2 is not None else (title,)
        section_start = line_start

    if fence_character is not None:
        raise MarkdownChunkingError("Markdown contains an unclosed fenced code block")
    if section_start < len(source):
        sections.append(_SemanticSection(section_start, len(source), current_path))
    return tuple(sections), tuple(fences)


def _normalize_heading_title(marks: str, title: str) -> str:
    normalized = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()
    return normalized or marks


def _is_closing_fence(line: str, character: str, minimum_length: int) -> bool:
    return (
        re.fullmatch(
            rf"[ \t]*{re.escape(character)}{{{minimum_length},}}[ \t]*",
            line,
        )
        is not None
    )


def _position_inside_fence(
    position: int,
    fences: tuple[_FenceSpan, ...],
) -> bool:
    return any(span.start < position < span.end for span in fences)


def _next_oversized_code_requires_clean_start(
    end: int,
    max_chars: int,
    overlap_chars: int,
    fences: tuple[_FenceSpan, ...],
) -> bool:
    return any(
        span.start == end and span.end - (end - overlap_chars) > max_chars
        for span in fences
    )


def _source_blocks(
    source: str,
    fences: tuple[_FenceSpan, ...],
) -> tuple[tuple[int, int], ...]:
    blocks: list[tuple[int, int]] = []
    cursor = 0
    for fence in fences:
        if cursor < fence.start:
            blocks.extend(_prose_blocks(source, cursor, fence.start))
        blocks.append((fence.start, fence.end))
        cursor = fence.end
    if cursor < len(source):
        blocks.extend(_prose_blocks(source, cursor, len(source)))
    return tuple(block for block in blocks if block[0] < block[1])


def _prose_blocks(source: str, start: int, end: int) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    cursor = start
    for match in _PARAGRAPH_BOUNDARY_PATTERN.finditer(source[start:end]):
        boundary = start + match.end()
        if cursor < boundary:
            blocks.append((cursor, boundary))
        cursor = boundary
    if cursor < end:
        blocks.append((cursor, end))
    return blocks


def audit_chunk_artifact(source: str, artifact: ChunkArtifact) -> ChunkAudit:
    """独立验证 source slice、覆盖率、fence、hash、顺序和统计。"""
    chunks = artifact.chunks
    for chunk in chunks:
        if source[chunk.source_start_char : chunk.source_end_char] != chunk.text:
            raise MarkdownChunkingError(
                "chunk text does not match source character span"
            )

    covered_end = 0
    covered_characters = 0
    coverage_gap_count = 0
    for chunk in chunks:
        if chunk.source_start_char > covered_end:
            coverage_gap_count += 1
        new_start = max(covered_end, chunk.source_start_char)
        if chunk.source_end_char > new_start:
            covered_characters += chunk.source_end_char - new_start
        covered_end = max(covered_end, chunk.source_end_char)
    if covered_end < len(source):
        coverage_gap_count += 1
    if coverage_gap_count or covered_characters != len(source):
        raise MarkdownChunkingError("chunk artifact does not cover the full source")

    _, source_fences = _parse_semantic_sections(source)
    preserved_fences = sum(
        1
        for fence in source_fences
        if any(
            chunk.source_start_char <= fence.start
            and chunk.source_end_char >= fence.end
            for chunk in chunks
        )
    )
    if preserved_fences != len(source_fences):
        raise MarkdownChunkingError("a fenced code block crosses chunk boundaries")
    for chunk in chunks:
        _parse_semantic_sections(chunk.text)

    source_blocks = _source_blocks(source, source_fences)
    covered_source_blocks = sum(
        1
        for block_start, block_end in source_blocks
        if _interval_is_covered(block_start, block_end, chunks)
    )
    if covered_source_blocks != len(source_blocks):
        raise MarkdownChunkingError("source block coverage audit failed")

    lengths = [chunk.char_length for chunk in chunks]
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    content_hashes = [chunk.content_sha256 for chunk in chunks]
    oversized_code_count = 0
    for chunk in chunks:
        if chunk.char_length <= artifact.max_chars:
            continue
        _, chunk_fences = _parse_semantic_sections(chunk.text)
        if any(span.end - span.start > artifact.max_chars for span in chunk_fences):
            oversized_code_count += 1

    unique_ids = len(set(chunk_ids))
    unique_content_hashes = len(set(content_hashes))
    return ChunkAudit(
        chunk_count=len(chunks),
        min_char_length=min(lengths),
        max_char_length=max(lengths),
        target_range_count=sum(
            artifact.min_chars <= length <= artifact.max_chars for length in lengths
        ),
        short_structural_count=sum(length < artifact.min_chars for length in lengths),
        oversized_structural_count=sum(
            length > artifact.max_chars for length in lengths
        ),
        oversized_code_block_count=oversized_code_count,
        continuation_chunk_count=sum(chunk.continuation_index > 0 for chunk in chunks),
        overlap_chunk_count=sum(chunk.overlap_chars > 0 for chunk in chunks),
        unique_chunk_id_count=unique_ids,
        chunk_id_collision_count=len(chunks) - unique_ids,
        unique_content_hash_count=unique_content_hashes,
        duplicate_content_hash_count=len(chunks) - unique_content_hashes,
        source_fenced_block_count=len(source_fences),
        preserved_fenced_block_count=preserved_fences,
        source_block_count=len(source_blocks),
        covered_source_block_count=covered_source_blocks,
        source_character_count=len(source),
        covered_character_count=covered_characters,
        coverage_gap_count=coverage_gap_count,
    )


def _interval_is_covered(
    start: int,
    end: int,
    chunks: tuple[MarkdownChunk, ...],
) -> bool:
    covered_until = start
    for chunk in chunks:
        if chunk.source_end_char <= covered_until:
            continue
        if chunk.source_start_char > covered_until:
            return False
        covered_until = max(covered_until, chunk.source_end_char)
        if covered_until >= end:
            return True
    return covered_until >= end


def _serialize_artifact(artifact: ChunkArtifact) -> bytes:
    return (
        json.dumps(
            artifact.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def load_chunk_artifact(path: Path) -> ChunkArtifact:
    """从磁盘严格解析 schema v1 artifact。"""
    try:
        return ChunkArtifact.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise MarkdownChunkingError("chunk artifact is missing or invalid") from error


def _publish_if_changed(target: Path, content: bytes) -> ChunkBuildState:
    try:
        if target.is_file() and target.read_bytes() == content:
            return "unchanged"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{uuid.uuid4().hex[:8]}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    except OSError as error:
        raise ChunkArtifactPublishError(
            "chunk artifact could not be published atomically"
        ) from error
    return "written"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从固定 Day 8 snapshot 离线构建 deterministic Markdown chunks。"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="MigrationLens 仓库根目录。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """运行显式离线 chunk build；受控失败返回非零且不输出 traceback。"""
    args = _build_parser().parse_args(argv)
    try:
        result = MarkdownChunkBuilder(repo_root=args.repo_root).build()
    except ChunkError as error:
        print(
            f"chunk_build_failed error_type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    audit = result.audit
    print(f"build_state={result.build_state}")
    print(f"artifact_path={CHUNK_ARTIFACT_PATH}")
    print(f"artifact_sha256={result.artifact_sha256}")
    print(f"source_snapshot_sha256={result.artifact.source_snapshot_sha256}")
    print(f"git_ref={result.artifact.git_ref}")
    print(f"resolved_commit_sha={result.artifact.resolved_commit_sha}")
    print(f"chunk_count={audit.chunk_count}")
    print(f"min_char_length={audit.min_char_length}")
    print(f"max_char_length={audit.max_char_length}")
    print(f"target_range_count={audit.target_range_count}")
    print(f"short_structural_count={audit.short_structural_count}")
    print(f"oversized_structural_count={audit.oversized_structural_count}")
    print(f"oversized_code_block_count={audit.oversized_code_block_count}")
    print(f"continuation_chunk_count={audit.continuation_chunk_count}")
    print(f"overlap_chunk_count={audit.overlap_chunk_count}")
    print(f"unique_chunk_id_count={audit.unique_chunk_id_count}")
    print(f"chunk_id_collision_count={audit.chunk_id_collision_count}")
    print(f"unique_content_hash_count={audit.unique_content_hash_count}")
    print(f"duplicate_content_hash_count={audit.duplicate_content_hash_count}")
    print(f"source_fenced_block_count={audit.source_fenced_block_count}")
    print(f"preserved_fenced_block_count={audit.preserved_fenced_block_count}")
    print(f"source_block_count={audit.source_block_count}")
    print(f"covered_source_block_count={audit.covered_source_block_count}")
    print(f"source_character_count={audit.source_character_count}")
    print(f"covered_character_count={audit.covered_character_count}")
    print(f"coverage_gap_count={audit.coverage_gap_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
