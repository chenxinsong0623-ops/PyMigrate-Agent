from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    DEFAULT_MAX_CHARS,
    DEFAULT_MIN_CHARS,
    DEFAULT_OVERLAP_CHARS,
    ChunkArtifact,
    ChunkArtifactPublishError,
    ChunkSourceValidationError,
    MarkdownChunkBuilder,
    MarkdownChunkingError,
    calculate_text_sha256,
    load_chunk_artifact,
    main,
)
from app.ingestion.pydantic_snapshot import (
    MANIFEST_PATH,
    SNAPSHOT_PATH,
    SOURCE_PATH,
    SOURCE_UPSTREAM_REPO,
    SnapshotManifest,
    calculate_sha256,
)

COMMIT_SHA = "1" * 40
SOURCE_URL = (
    f"https://raw.githubusercontent.com/pydantic/pydantic/{COMMIT_SHA}/{SOURCE_PATH}"
)
LICENSE_URL = (
    f"https://raw.githubusercontent.com/pydantic/pydantic/{COMMIT_SHA}/LICENSE"
)


def write_day_eight_source(
    repo_root: Path,
    markdown: str,
    *,
    expected_hash: str | None = None,
    expected_length: int | None = None,
    source_url: str = SOURCE_URL,
) -> tuple[Path, SnapshotManifest]:
    source_bytes = markdown.encode("utf-8")
    snapshot_path = repo_root / SNAPSHOT_PATH
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(source_bytes)
    manifest = SnapshotManifest(
        source_id="pydantic-v2-migration",
        upstream_repo=SOURCE_UPSTREAM_REPO,
        git_ref="v2.13.4",
        resolved_commit_sha=COMMIT_SHA,
        path=SOURCE_PATH,
        source_url=source_url,
        snapshot_path=SNAPSHOT_PATH,
        retrieved_at_utc="2026-08-12T01:02:03Z",
        sha256=expected_hash or calculate_sha256(source_bytes),
        byte_length=(len(source_bytes) if expected_length is None else expected_length),
        license="MIT",
        license_source_url=LICENSE_URL,
        license_path="third_party/pydantic-LICENSE",
        license_sha256="2" * 64,
        license_byte_length=123,
        attribution_path="THIRD_PARTY_NOTICES.md",
    )
    manifest_path = repo_root / MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return snapshot_path, manifest


def build_fixture(
    repo_root: Path,
    markdown: str,
) -> tuple[MarkdownChunkBuilder, object]:
    write_day_eight_source(repo_root, markdown)
    builder = MarkdownChunkBuilder(repo_root=repo_root)
    return builder, builder.build()


def chunks_for_path(artifact: ChunkArtifact, *path: str):
    return [chunk for chunk in artifact.chunks if chunk.heading_path == path]


def test_day_nine_constants_match_frozen_contract() -> None:
    assert DEFAULT_MIN_CHARS == 500
    assert DEFAULT_MAX_CHARS == 1200
    assert DEFAULT_OVERLAP_CHARS == 120
    assert CHUNK_ARTIFACT_PATH == "data/chunks/pydantic-v2-migration.json"


def test_builder_construction_has_no_file_or_network_side_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_network(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("constructor must not use network")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    MarkdownChunkBuilder(repo_root=tmp_path)

    assert calls == 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("min_chars", "max_chars", "overlap_chars"),
    [
        (0, 1200, 120),
        (500, 499, 120),
        (500, 1200, 99),
        (500, 1200, 151),
        (500, 100, 100),
        (True, 1200, 120),
    ],
)
def test_builder_rejects_invalid_length_contract(
    tmp_path: Path,
    min_chars: int,
    max_chars: int,
    overlap_chars: int,
) -> None:
    with pytest.raises(ValueError):
        MarkdownChunkBuilder(
            repo_root=tmp_path,
            min_chars=min_chars,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )


def test_source_hash_mismatch_fails_before_artifact_publish(tmp_path: Path) -> None:
    write_day_eight_source(tmp_path, "## A\nbody\n", expected_hash="0" * 64)

    with pytest.raises(ChunkSourceValidationError, match="hash"):
        MarkdownChunkBuilder(repo_root=tmp_path).build()

    assert not (tmp_path / CHUNK_ARTIFACT_PATH).exists()


def test_source_byte_length_mismatch_fails_before_artifact_publish(
    tmp_path: Path,
) -> None:
    markdown = "## A\nbody\n"
    write_day_eight_source(
        tmp_path,
        markdown,
        expected_length=len(markdown.encode("utf-8")) + 1,
    )

    with pytest.raises(ChunkSourceValidationError, match="length"):
        MarkdownChunkBuilder(repo_root=tmp_path).build()

    assert not (tmp_path / CHUNK_ARTIFACT_PATH).exists()


def test_source_url_must_bind_manifest_commit_and_path(tmp_path: Path) -> None:
    write_day_eight_source(
        tmp_path,
        "## A\nbody\n",
        source_url="https://docs.pydantic.dev/latest/migration/",
    )

    with pytest.raises(ChunkSourceValidationError, match="source URL"):
        MarkdownChunkBuilder(repo_root=tmp_path).build()


def test_h2_h3_heading_paths_and_new_h2_clears_h3(tmp_path: Path) -> None:
    markdown = (
        "front matter\n\n"
        "## BaseModel\n\nbase body\n\n"
        "### dict\n\ndict body\n\n"
        "## Field\n\nfield body\n"
    )
    _, result = build_fixture(tmp_path, markdown)

    assert [chunk.heading_path for chunk in result.artifact.chunks] == [
        (),
        ("BaseModel",),
        ("BaseModel", "dict"),
        ("Field",),
    ]
    assert "## BaseModel" in chunks_for_path(result.artifact, "BaseModel")[0].text
    assert "### dict" in chunks_for_path(result.artifact, "BaseModel", "dict")[0].text
    assert chunks_for_path(result.artifact, "Field")[0].heading_path == ("Field",)


def test_backtick_fence_is_atomic_and_code_headings_are_ignored(
    tmp_path: Path,
) -> None:
    code = "```python\n## not a heading\n### neither\nprint('ok')\n```\n"
    markdown = "## API\n\nintro\n\n" + code + "\nafter\n"
    _, result = build_fixture(tmp_path, markdown)

    assert {chunk.heading_path for chunk in result.artifact.chunks} == {("API",)}
    containing = [chunk for chunk in result.artifact.chunks if code in chunk.text]
    assert len(containing) == 1
    assert result.audit.source_fenced_block_count == 1
    assert result.audit.preserved_fenced_block_count == 1


def test_tilde_fence_with_language_info_is_atomic(tmp_path: Path) -> None:
    code = "~~~python\n### still code\nprint('ok')\n~~~\n"
    _, result = build_fixture(tmp_path, "## API\n\n" + code + "\nafter\n")

    assert len([chunk for chunk in result.artifact.chunks if code in chunk.text]) == 1
    assert result.audit.source_fenced_block_count == 1


def test_list_indented_fence_is_atomic(tmp_path: Path) -> None:
    code = "    ```python\n    ## still code\n    print('ok')\n    ```\n"
    _, result = build_fixture(tmp_path, "## API\n\n1. Example:\n\n" + code)

    assert len([chunk for chunk in result.artifact.chunks if code in chunk.text]) == 1
    assert result.audit.source_fenced_block_count == 1


def test_longer_backtick_fence_does_not_close_on_shorter_run(tmp_path: Path) -> None:
    code = "````markdown\n```python\n## code\n```\n````\n"
    _, result = build_fixture(tmp_path, "## Fence\n\n" + code)

    assert len([chunk for chunk in result.artifact.chunks if code in chunk.text]) == 1
    assert result.audit.source_fenced_block_count == 1


def test_short_structural_chunk_is_not_padded_or_merged_across_heading(
    tmp_path: Path,
) -> None:
    markdown = "## Short\n\nsmall\n\n## Normal\n\n" + ("word " * 120)
    _, result = build_fixture(tmp_path, markdown)
    short = chunks_for_path(result.artifact, "Short")

    assert len(short) == 1
    assert short[0].char_length < DEFAULT_MIN_CHARS
    assert short[0].text == "## Short\n\nsmall\n\n"
    assert result.audit.short_structural_count >= 1
    assert all("## Normal" not in chunk.text for chunk in short)


def test_oversized_prose_splits_deterministically_with_exact_overlap(
    tmp_path: Path,
) -> None:
    markdown = "## Long\n\n" + ("migration sentence. " * 180)
    _, result = build_fixture(tmp_path, markdown)
    chunks = chunks_for_path(result.artifact, "Long")

    assert len(chunks) > 1
    assert all(chunk.char_length <= DEFAULT_MAX_CHARS for chunk in chunks)
    assert chunks[0].overlap_chars == 0
    for previous, current in zip(chunks[:-1], chunks[1:], strict=True):
        assert current.overlap_chars == DEFAULT_OVERLAP_CHARS
        assert previous.text[-DEFAULT_OVERLAP_CHARS:] == current.text[:120]
        assert current.source_start_char > previous.source_start_char
    assert result.audit.overlap_chunk_count == len(chunks) - 1


def test_single_oversized_code_block_remains_whole(tmp_path: Path) -> None:
    code = "```python\n" + ("value = 1\n" * 150) + "```\n"
    _, result = build_fixture(tmp_path, "## Large code\n\n" + code)
    containing = [chunk for chunk in result.artifact.chunks if code in chunk.text]

    assert len(containing) == 1
    assert containing[0].char_length > DEFAULT_MAX_CHARS
    assert result.audit.oversized_structural_count == 1
    assert result.audit.oversized_code_block_count == 1


def test_preamble_and_heading_only_section_are_preserved(tmp_path: Path) -> None:
    markdown = "---\ndescription: intro\n---\n\n## Empty\n\n## Next\n\nbody\n"
    _, result = build_fixture(tmp_path, markdown)

    assert result.artifact.chunks[0].heading_path == ()
    assert result.artifact.chunks[0].text == "---\ndescription: intro\n---\n\n"
    empty = chunks_for_path(result.artifact, "Empty")
    assert len(empty) == 1
    assert empty[0].text == "## Empty\n\n"
    assert all(chunk.text for chunk in result.artifact.chunks)


def test_unicode_order_and_duplicate_text_under_different_headings_are_kept(
    tmp_path: Path,
) -> None:
    markdown = "## 甲\n\n相同正文\n\n## 乙\n\n相同正文\n"
    _, result = build_fixture(tmp_path, markdown)

    assert [chunk.heading_path for chunk in result.artifact.chunks] == [
        ("甲",),
        ("乙",),
    ]
    assert len(result.artifact.chunks) == 2
    assert result.artifact.chunks[0].chunk_id != result.artifact.chunks[1].chunk_id


def test_chunk_id_and_content_hash_are_stable_and_have_distinct_meaning(
    tmp_path: Path,
) -> None:
    markdown = "## Stable\n\n" + ("content " * 90)
    _, first = build_fixture(tmp_path, markdown)
    first_chunk = first.artifact.chunks[0]

    second = MarkdownChunkBuilder(repo_root=tmp_path).build()
    second_chunk = second.artifact.chunks[0]

    assert first_chunk.chunk_id == second_chunk.chunk_id
    assert first_chunk.content_sha256 == calculate_text_sha256(first_chunk.text)
    assert first_chunk.chunk_id.removeprefix("sha256:") != first_chunk.content_sha256


def test_text_or_heading_change_updates_only_affected_identity(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    third_root = tmp_path / "third"
    for root in (first_root, second_root, third_root):
        root.mkdir()

    _, first = build_fixture(first_root, "## A\n\nalpha\n\n## B\n\nbeta\n")
    _, second = build_fixture(
        second_root,
        "preamble inserted\n\n## A\n\nalpha\n\n## B\n\nbeta\n",
    )
    _, third = build_fixture(third_root, "## A changed\n\nalpha\n\n## B\n\nbeta\n")

    first_by_path = {
        chunk.heading_path: chunk.chunk_id for chunk in first.artifact.chunks
    }
    second_by_path = {
        chunk.heading_path: chunk.chunk_id for chunk in second.artifact.chunks
    }
    third_by_path = {
        chunk.heading_path: chunk.chunk_id for chunk in third.artifact.chunks
    }
    assert first_by_path[("A",)] == second_by_path[("A",)]
    assert first_by_path[("B",)] == second_by_path[("B",)]
    assert first_by_path[("B",)] == third_by_path[("B",)]
    assert first_by_path[("A",)] != third_by_path[("A changed",)]


def test_source_provenance_and_offsets_round_trip(tmp_path: Path) -> None:
    markdown = "## A\n\n" + ("text " * 400)
    _, result = build_fixture(tmp_path, markdown)
    loaded = load_chunk_artifact(tmp_path / CHUNK_ARTIFACT_PATH)

    assert loaded == result.artifact
    assert loaded.source_id == "pydantic-v2-migration"
    assert loaded.git_ref == "v2.13.4"
    assert loaded.resolved_commit_sha == COMMIT_SHA
    assert loaded.source_url == SOURCE_URL
    assert loaded.source_path == SOURCE_PATH
    for chunk in loaded.chunks:
        assert chunk.source_url == SOURCE_URL
        assert chunk.git_ref == "v2.13.4"
        assert chunk.resolved_commit_sha == COMMIT_SHA
        assert chunk.text == markdown[chunk.source_start_char : chunk.source_end_char]


def test_repeated_build_keeps_artifact_bytes_hash_ids_and_mtime(tmp_path: Path) -> None:
    _, first = build_fixture(tmp_path, "## Stable\n\n" + ("text " * 400))
    output = tmp_path / CHUNK_ARTIFACT_PATH
    first_bytes = output.read_bytes()
    first_hash = hashlib.sha256(first_bytes).hexdigest()
    first_mtime = output.stat().st_mtime_ns
    first_ids = [chunk.chunk_id for chunk in first.artifact.chunks]

    second = MarkdownChunkBuilder(repo_root=tmp_path).build()

    assert first.build_state == "written"
    assert second.build_state == "unchanged"
    assert output.read_bytes() == first_bytes
    assert second.artifact_sha256 == first_hash
    assert output.stat().st_mtime_ns == first_mtime
    assert [chunk.chunk_id for chunk in second.artifact.chunks] == first_ids


def test_invalid_rebuild_preserves_existing_valid_artifact(tmp_path: Path) -> None:
    snapshot, _ = write_day_eight_source(tmp_path, "## A\n\nvalid\n")
    builder = MarkdownChunkBuilder(repo_root=tmp_path)
    builder.build()
    output = tmp_path / CHUNK_ARTIFACT_PATH
    before = output.read_bytes()
    snapshot.write_text("tampered", encoding="utf-8")

    with pytest.raises(ChunkSourceValidationError):
        builder.build()

    assert output.read_bytes() == before


def test_atomic_replace_failure_preserves_existing_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_day_eight_source(tmp_path, "## A\n\nfirst\n")
    builder = MarkdownChunkBuilder(repo_root=tmp_path)
    builder.build()
    output = tmp_path / CHUNK_ARTIFACT_PATH
    before = output.read_bytes()
    write_day_eight_source(tmp_path, "## A\n\nsecond content\n")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected publish failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(ChunkArtifactPublishError):
        builder.build()

    assert output.read_bytes() == before


def test_build_is_fully_offline_and_does_not_modify_day_eight_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown = "## Offline\n\n" + ("text " * 150)
    snapshot, _ = write_day_eight_source(tmp_path, markdown)
    before = snapshot.read_bytes()

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Day 9 must not use network")
        ),
    )
    MarkdownChunkBuilder(repo_root=tmp_path).build()

    assert snapshot.read_bytes() == before


def test_audit_proves_all_source_blocks_and_characters_are_covered(
    tmp_path: Path,
) -> None:
    markdown = (
        "intro\n\n## A\n\n"
        + ("long sentence. " * 150)
        + "\n\n```python\nprint('ok')\n```\n"
    )
    _, result = build_fixture(tmp_path, markdown)

    assert result.audit.source_character_count == len(markdown)
    assert result.audit.covered_character_count == len(markdown)
    assert result.audit.coverage_gap_count == 0
    assert result.audit.source_block_count == result.audit.covered_source_block_count
    assert result.audit.source_fenced_block_count == 1
    assert result.audit.preserved_fenced_block_count == 1


def test_unclosed_fence_fails_without_artifact(tmp_path: Path) -> None:
    write_day_eight_source(tmp_path, "## Broken\n\n```python\nprint('x')\n")

    with pytest.raises(MarkdownChunkingError, match="unclosed"):
        MarkdownChunkBuilder(repo_root=tmp_path).build()

    assert not (tmp_path / CHUNK_ARTIFACT_PATH).exists()


def test_artifact_models_are_frozen_and_reject_extra_fields(tmp_path: Path) -> None:
    _, result = build_fixture(tmp_path, "## A\n\nbody\n")
    chunk = result.artifact.chunks[0]

    with pytest.raises(ValidationError):
        chunk.text = "changed"  # type: ignore[misc]
    payload = result.artifact.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        ChunkArtifact.model_validate(payload)


def test_cli_reports_success_and_failure_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot, _ = write_day_eight_source(tmp_path, "## CLI\n\nbody\n")

    assert main(["--repo-root", str(tmp_path)]) == 0
    success = capsys.readouterr()
    assert "chunk_count=" in success.out
    assert "artifact_sha256=" in success.out

    snapshot.write_text("tampered", encoding="utf-8")
    assert main(["--repo-root", str(tmp_path)]) == 1
    failure = capsys.readouterr()
    assert "ChunkSourceValidationError" in failure.err
    assert "Traceback" not in failure.err
