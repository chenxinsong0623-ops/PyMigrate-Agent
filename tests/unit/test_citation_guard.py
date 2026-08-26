from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent import SelectedDocCandidate
from app.reporting import (
    CitationErrorType,
    CitationGuard,
    CitationSupportStatus,
    CitationValidity,
)
from app.scanner import RuleId
from tests.reporting_fixtures import (
    make_agent_result,
    official_chunk,
    trusted_chunk_containing,
)


def _guard(root: Path | None = None) -> CitationGuard:
    return CitationGuard.from_repository(root or Path.cwd())


def test_valid_current_analysis_citation_uses_trusted_local_artifacts() -> None:
    result = make_agent_result()

    checked = _guard().validate(result)

    assert checked.allowlisted_chunk_ids == (result.retrieved_chunks[0].chunk_id,)
    assert checked.items[0].validity is CitationValidity.VALID
    assert (
        checked.valid_citations[0].support_status is CitationSupportStatus.NOT_EVALUATED
    )
    assert (
        checked.valid_citations[0].source_url == result.retrieved_chunks[0].source_url
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("source_url", "https://forged.invalid/doc", CitationErrorType.URL_MISMATCH),
        ("git_ref", "v0.0.0", CitationErrorType.REF_MISMATCH),
        ("resolved_commit_sha", "f" * 40, CitationErrorType.COMMIT_MISMATCH),
        ("heading_path", ("forged",), CitationErrorType.HEADING_MISMATCH),
        ("content_sha256", "f" * 64, CitationErrorType.CONTENT_HASH_MISMATCH),
        (
            "source_snapshot_sha256",
            "f" * 64,
            CitationErrorType.SOURCE_HASH_MISMATCH,
        ),
        ("source_id", "forged-source", CitationErrorType.SOURCE_IDENTITY_MISMATCH),
        ("source_path", "forged.md", CitationErrorType.SOURCE_IDENTITY_MISMATCH),
        ("text", "forged text", CitationErrorType.TEXT_MISMATCH),
    ],
)
def test_retrieved_metadata_tampering_fails_closed(
    field: str,
    value: object,
    expected: CitationErrorType,
) -> None:
    result = make_agent_result()
    tampered = result.retrieved_chunks[0].model_copy(update={field: value})
    result = result.model_copy(update={"retrieved_chunks": (tampered,)})

    checked = _guard().validate(result)

    assert checked.valid_citations == ()
    assert checked.items[0].error_type is expected
    assert checked.items[0].retry_eligible is False


def test_forged_chunk_id_is_rejected_but_is_model_selection_retryable() -> None:
    result = make_agent_result(candidate_chunk_id="sha256:" + "f" * 64)

    checked = _guard().validate(result)

    assert checked.items[0].error_type is CitationErrorType.FORGED_CHUNK_ID
    assert checked.items[0].retry_eligible is True


def test_real_global_chunk_from_another_analysis_is_not_in_current_allowlist() -> None:
    other = trusted_chunk_containing("BaseSettings")
    result = make_agent_result(candidate_chunk_id=other.chunk_id)

    checked = _guard().validate(result)

    assert checked.items[0].error_type is CitationErrorType.CROSS_ANALYSIS_CHUNK
    assert checked.items[0].retry_eligible is False


def test_cross_result_chunk_is_rejected_even_when_all_global_hashes_are_real() -> None:
    analysis_a = make_agent_result(analysis_id="analysis-a")
    analysis_b = make_agent_result(analysis_id="analysis-b", include_candidate=False)
    injected = analysis_a.draft_report.selected_doc_candidates[0]
    forged_b = analysis_b.model_copy(
        update={
            "draft_report": analysis_b.draft_report.model_copy(
                update={"selected_doc_candidates": (injected,)}
            )
        }
    )

    checked = _guard().validate(forged_b)

    assert checked.items[0].error_type in {
        CitationErrorType.UNKNOWN_GROUP,
        CitationErrorType.CROSS_ANALYSIS_CHUNK,
    }


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("group", CitationErrorType.UNKNOWN_GROUP),
        ("finding", CitationErrorType.UNKNOWN_FINDING),
        ("group_finding", CitationErrorType.FINDING_GROUP_MISMATCH),
    ],
)
def test_candidate_group_and_finding_identity_fail_closed(
    change: str,
    expected: CitationErrorType,
) -> None:
    result = make_agent_result()
    candidate = result.draft_report.selected_doc_candidates[0]
    if change == "group":
        candidate = candidate.model_copy(update={"group_id": "sha256:" + "e" * 64})
    elif change == "finding":
        candidate = candidate.model_copy(
            update={"finding_ids": ("sha256:" + "d" * 64,)}
        )
    else:
        candidate = candidate.model_copy(
            update={
                "finding_ids": tuple(reversed(result.finding_ids)) + result.finding_ids
            }
        )
    forged = result.model_copy(
        update={
            "draft_report": result.draft_report.model_copy(
                update={"selected_doc_candidates": (candidate,)}
            )
        }
    )

    checked = _guard().validate(forged)

    assert checked.items[0].error_type is expected


def test_duplicate_candidate_is_rejected_as_contract_violation() -> None:
    result = make_agent_result()
    candidate = result.draft_report.selected_doc_candidates[0]
    forged = result.model_copy(
        update={
            "draft_report": result.draft_report.model_copy(
                update={"selected_doc_candidates": (candidate, candidate)}
            )
        }
    )

    checked = _guard().validate(forged)

    assert checked.valid_citations == ()
    assert all(
        item.error_type is CitationErrorType.DUPLICATE_CITATION
        for item in checked.items
    )


def test_missing_rule_query_binding_and_keyword_mismatch_are_separate() -> None:
    missing_binding = _guard().validate(make_agent_result(include_binding=False))
    unrelated = trusted_chunk_containing("Pydantic V2 introduces")
    keyword_mismatch = _guard().validate(
        make_agent_result(chunk=unrelated, retrieved=official_chunk(unrelated))
    )

    assert (
        missing_binding.items[0].error_type is CitationErrorType.QUERY_BINDING_MISSING
    )
    assert missing_binding.items[0].retry_eligible is False
    assert keyword_mismatch.items[0].error_type is CitationErrorType.KEYWORD_MISMATCH


def test_rule_and_safe_query_binding_mismatch_fail_closed() -> None:
    source = make_agent_result()
    group = source.ambiguous_groups[0]
    wrong_rule = source.model_copy(
        update={
            "ambiguous_groups": (
                group.model_copy(update={"rule_id": RuleId.PYDANTIC_V1_SETTINGS}),
            )
        }
    )
    wrong_query = make_agent_result(matched_query_terms=("untrusted-term",))

    rule_checked = _guard().validate(wrong_rule)
    query_checked = _guard().validate(wrong_query)

    assert rule_checked.items[0].error_type is CitationErrorType.RULE_MISMATCH
    assert query_checked.items[0].error_type is CitationErrorType.QUERY_BINDING_MISMATCH
    assert query_checked.items[0].retry_eligible is False


def test_empty_candidate_is_rejected_by_strict_boundary_model() -> None:
    source = make_agent_result()
    group = source.ambiguous_groups[0]

    with pytest.raises(ValidationError):
        SelectedDocCandidate(
            analysis_id=source.analysis_id,
            group_id=group.group_id,
            finding_ids=group.finding_ids,
            chunk_id="",
        )


def test_no_candidate_is_explicit_and_retryable() -> None:
    checked = _guard().validate(make_agent_result(include_candidate=False))

    assert checked.items[0].error_type is CitationErrorType.NO_CANDIDATE
    assert checked.items[0].retry_eligible is True


@pytest.mark.parametrize("target_kind", ["snapshot", "artifact"])
def test_corrupt_snapshot_or_artifact_disables_trust_and_never_retries(
    tmp_path: Path,
    target_kind: str,
) -> None:
    for relative in (
        "data/manifests/pydantic-v2-migration.json",
        "data/chunks/pydantic-v2-migration.json",
        "data/snapshots/pydantic-v2-migration/migration.md",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(relative), target)
    if target_kind == "snapshot":
        snapshot = tmp_path / "data/snapshots/pydantic-v2-migration/migration.md"
        snapshot.write_bytes(snapshot.read_bytes() + b"tampered")
    else:
        artifact_path = tmp_path / "data/chunks/pydantic-v2-migration.json"
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["source_url"] = "https://forged.invalid/migration.md"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    checked = _guard(tmp_path).validate(make_agent_result())

    assert checked.trust_available is False
    assert checked.items[0].error_type is CitationErrorType.TRUSTED_SOURCE_INVALID
    assert checked.items[0].retry_eligible is False


def test_guard_models_are_strict_frozen_and_deterministically_ordered() -> None:
    result = make_agent_result()
    first = _guard().validate(result)
    second = _guard().validate(result)

    assert first == second
    with pytest.raises(ValidationError):
        first.trust_available = False
    with pytest.raises(ValidationError):
        type(first)(**first.model_dump(mode="python"), extra_field=True)


def test_unknown_programmer_exception_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _guard()

    def explode(*_args, **_kwargs):
        raise RuntimeError("programmer bug")

    monkeypatch.setattr(guard, "_validate_candidate", explode)
    with pytest.raises(RuntimeError, match="programmer bug"):
        guard.validate(make_agent_result())
