from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation import citation_audit
from app.evaluation.citation_audit import (
    AuditStatus,
    CitationAuditError,
    FrozenCitationEvidence,
    HumanReviewRow,
    ReviewerStatus,
    SupportVerdict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _evidence(index: int) -> FrozenCitationEvidence:
    return FrozenCitationEvidence(
        run_id="day24-test-run",
        frozen_commit="a" * 40,
        fixture_id=f"fixture-{index:02d}",
        analysis_id=f"analysis-{index:02d}",
        finding_id=f"sha256:{index:064x}",
        file=f"pkg/model_{index:02d}.py",
        line=index + 1,
        rule_id="pydantic_v1_config",
        old_api="Config",
        claim=f"claim-{index:02d}",
        citation_identifier=f"citation-{index:02d}",
        chunk_id=f"sha256:{index + 100:064x}",
        citation_heading=f"Heading {index:02d}",
        citation_ref="v2.13.4",
        citation_url=f"https://example.invalid/{index:02d}",
        citation_content_sha256=f"{index + 200:064x}",
        citation_evidence=f"evidence-{index:02d}",
        day24_citation_validity="valid",
    )


def _population(size: int = 25) -> tuple[FrozenCitationEvidence, ...]:
    return tuple(_evidence(index) for index in range(size))


def _pending_rows(
    sample: tuple[FrozenCitationEvidence, ...],
) -> tuple[HumanReviewRow, ...]:
    return tuple(
        HumanReviewRow(
            evidence=evidence,
            review_index=index,
            reviewer_status=ReviewerStatus.PENDING_HUMAN_REVIEW,
        )
        for index, evidence in enumerate(sample, start=1)
    )


def _reviewed_rows(
    sample: tuple[FrozenCitationEvidence, ...],
    verdicts: tuple[SupportVerdict, ...],
) -> tuple[HumanReviewRow, ...]:
    return tuple(
        HumanReviewRow(
            evidence=evidence,
            review_index=index,
            reviewer_status=ReviewerStatus.HUMAN_REVIEWED,
            human_support_verdict=verdict,
            reviewed_at="2026-09-01T00:00:00Z",
            human_note=(
                None if verdict is SupportVerdict.SUPPORTED else f"note-{index}"
            ),
        )
        for index, (evidence, verdict) in enumerate(
            zip(sample, verdicts, strict=True), start=1
        )
    )


def _copy_day24_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for relative_path in citation_audit.DAY24_EXPECTED_SHA256:
        source = REPO_ROOT / relative_path
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    expected = {
        path: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest()
        for path in citation_audit.DAY24_EXPECTED_SHA256
    }
    monkeypatch.setattr(citation_audit, "DAY24_EXPECTED_SHA256", expected)
    return tmp_path


def _refresh_expected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {
        path: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest()
        for path in citation_audit.DAY24_EXPECTED_SHA256
    }
    monkeypatch.setattr(citation_audit, "DAY24_EXPECTED_SHA256", expected)


def test_real_day24_artifacts_pass_integrity_and_identity_checks() -> None:
    result = citation_audit.verify_day24_artifacts(REPO_ROOT)

    assert result.run_id == "day24-3bec58084e13-1787815381"
    assert result.frozen_commit == "3bec58084e13d0734b891d290099a0695ec8dab6"
    assert result.component_attempts == {
        "detection": 1,
        "retrieval": 1,
        "agent": 1,
    }
    assert result.rerun_count == 0
    assert len(result.artifacts) == 7
    assert not result.manifest_internal_self_hash_matches


@pytest.mark.parametrize("relative_path", citation_audit.DAY24_EXPECTED_SHA256)
def test_each_day24_sealed_artifact_hash_drift_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
) -> None:
    root = _copy_day24_artifacts(tmp_path, monkeypatch)
    (root / relative_path).write_bytes((root / relative_path).read_bytes() + b"x")

    with pytest.raises(CitationAuditError, match="hash"):
        citation_audit.verify_day24_artifacts(root)


def test_invalid_day24_json_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_day24_artifacts(tmp_path, monkeypatch)
    (root / citation_audit.DAY24_RAW_EVIDENCE_PATH).write_text("{", encoding="utf-8")
    _refresh_expected(root, monkeypatch)

    with pytest.raises(CitationAuditError, match="无法解析"):
        citation_audit.verify_day24_artifacts(root)


def test_run_identity_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_day24_artifacts(tmp_path, monkeypatch)
    eval_path = root / citation_audit.DAY24_EVAL_PATH
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    payload["run_id"] = "different-run"
    eval_path.write_text(json.dumps(payload), encoding="utf-8")
    _refresh_expected(root, monkeypatch)

    with pytest.raises(CitationAuditError, match="run_id"):
        citation_audit.verify_day24_artifacts(root)


def test_frozen_commit_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_day24_artifacts(tmp_path, monkeypatch)
    agent_path = root / "reports/agent_metrics.json"
    payload = json.loads(agent_path.read_text(encoding="utf-8"))
    payload["frozen_commit"] = "b" * 40
    agent_path.write_text(json.dumps(payload), encoding="utf-8")
    _refresh_expected(root, monkeypatch)

    with pytest.raises(CitationAuditError, match="frozen commit"):
        citation_audit.verify_day24_artifacts(root)


def test_rerun_count_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_day24_artifacts(tmp_path, monkeypatch)
    eval_path = root / citation_audit.DAY24_EVAL_PATH
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    payload["rerun_count"] = 1
    eval_path.write_text(json.dumps(payload), encoding="utf-8")
    _refresh_expected(root, monkeypatch)

    with pytest.raises(CitationAuditError, match="rerun"):
        citation_audit.verify_day24_artifacts(root)


def test_real_day24_aggregate_only_evidence_is_insufficient() -> None:
    raw = json.loads(
        (REPO_ROOT / citation_audit.DAY24_RAW_EVIDENCE_PATH).read_text(encoding="utf-8")
    )

    result = citation_audit.audit_evidence_sufficiency(raw)

    assert not result.sufficient
    assert result.status is AuditStatus.BLOCKED
    assert result.finding_population_size == 0
    assert "findings[].claim" in result.missing_fields
    assert "exact finding_to_citation_mapping" in result.missing_fields


def test_complete_finding_citation_mapping_passes_sufficiency_gate() -> None:
    raw = {
        "raw_predictions": {
            "agent": [
                {
                    "findings": [
                        {
                            "finding_id": "sha256:" + "1" * 64,
                            "finding": {"rule_id": "rule"},
                            "claim": "claim",
                            "citations": [
                                {
                                    "chunk_id": "sha256:" + "2" * 64,
                                    "heading_path": ["heading"],
                                    "content_sha256": "3" * 64,
                                    "evidence_text": "evidence",
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    }

    result = citation_audit.audit_evidence_sufficiency(raw)

    assert result.sufficient
    assert result.status is AuditStatus.AWAITING_HUMAN_REVIEW
    assert result.finding_population_size == 1
    assert result.missing_fields == ()


def test_deterministic_sample_is_stable_across_input_order() -> None:
    population = _population()

    first = citation_audit.select_deterministic_sample(population)
    second = citation_audit.select_deterministic_sample(tuple(reversed(population)))

    assert first == second


def test_deterministic_sample_has_exactly_twenty_unique_findings() -> None:
    sample = citation_audit.select_deterministic_sample(_population())

    assert len(sample) == 20
    assert len({item.finding_id for item in sample}) == 20


def test_deterministic_sample_rejects_small_population() -> None:
    with pytest.raises(CitationAuditError, match="少于 20"):
        citation_audit.select_deterministic_sample(_population(19))


def test_deterministic_sample_rejects_duplicate_finding() -> None:
    population = (*_population(20), _evidence(0))

    with pytest.raises(CitationAuditError, match="不得重复"):
        citation_audit.select_deterministic_sample(population)


def test_deterministic_sample_rejects_non_twenty_contract() -> None:
    with pytest.raises(CitationAuditError, match="恰好为 20"):
        citation_audit.select_deterministic_sample(_population(), sample_size=10)


def test_pending_rows_do_not_compute_support_rate() -> None:
    sample = citation_audit.select_deterministic_sample(_population())

    summary = citation_audit.aggregate_human_review(_pending_rows(sample), sample)

    assert summary.status is AuditStatus.AWAITING_HUMAN_REVIEW
    assert summary.reviewed_count == 0
    assert summary.strict_support_rate is None


def test_completed_human_review_counts_all_verdicts() -> None:
    sample = citation_audit.select_deterministic_sample(_population())
    verdicts = (
        *(SupportVerdict.SUPPORTED for _ in range(11)),
        *(SupportVerdict.PARTIALLY_SUPPORTED for _ in range(4)),
        *(SupportVerdict.UNSUPPORTED for _ in range(3)),
        *(SupportVerdict.NOT_ASSESSABLE for _ in range(2)),
    )

    summary = citation_audit.aggregate_human_review(
        _reviewed_rows(sample, verdicts), sample
    )

    assert summary.status is AuditStatus.COMPLETED
    assert summary.reviewed_count == 20
    assert summary.supported == 11
    assert summary.partially_supported == 4
    assert summary.unsupported == 3
    assert summary.not_assessable == 2
    assert summary.strict_support_rate == 11 / 20


def test_partially_supported_is_strict_failure_in_denominator() -> None:
    sample = citation_audit.select_deterministic_sample(_population())
    verdicts = (SupportVerdict.SUPPORTED,) * 19 + (SupportVerdict.PARTIALLY_SUPPORTED,)

    summary = citation_audit.aggregate_human_review(
        _reviewed_rows(sample, verdicts), sample
    )

    assert summary.strict_support_rate == 19 / 20


def test_non_supported_human_verdict_requires_note() -> None:
    with pytest.raises(ValidationError, match="human note"):
        HumanReviewRow(
            evidence=_evidence(1),
            review_index=1,
            reviewer_status=ReviewerStatus.HUMAN_REVIEWED,
            human_support_verdict=SupportVerdict.UNSUPPORTED,
            reviewed_at="2026-09-01T00:00:00Z",
        )


def test_unsupported_verdict_enum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        HumanReviewRow.model_validate(
            {
                "evidence": _evidence(1).model_dump(mode="json"),
                "review_index": 1,
                "reviewer_status": "human_reviewed",
                "human_support_verdict": "MAYBE",
                "reviewed_at": "2026-09-01T00:00:00Z",
                "human_note": "note",
            },
            strict=True,
        )


def test_sample_replacement_after_review_is_rejected() -> None:
    sample = citation_audit.select_deterministic_sample(_population())
    rows = list(_pending_rows(sample))
    rows[0] = rows[0].model_copy(update={"evidence": _evidence(999)})

    with pytest.raises(CitationAuditError, match="发生漂移"):
        citation_audit.validate_review_rows(tuple(rows), sample)


def test_citation_replacement_after_review_is_rejected() -> None:
    sample = citation_audit.select_deterministic_sample(_population())
    rows = list(_pending_rows(sample))
    changed = sample[0].model_copy(update={"chunk_id": "sha256:" + "f" * 64})
    rows[0] = rows[0].model_copy(update={"evidence": changed})

    with pytest.raises(CitationAuditError, match="发生漂移"):
        citation_audit.validate_review_rows(tuple(rows), sample)


def test_duplicate_review_finding_is_rejected() -> None:
    sample = citation_audit.select_deterministic_sample(_population())
    rows = list(_pending_rows(sample))
    rows[1] = rows[1].model_copy(update={"evidence": rows[0].evidence})

    with pytest.raises(CitationAuditError):
        citation_audit.validate_review_rows(tuple(rows), sample)


def test_review_index_drift_is_rejected() -> None:
    sample = citation_audit.select_deterministic_sample(_population())
    rows = list(_pending_rows(sample))
    rows[0] = rows[0].model_copy(update={"review_index": 2})

    with pytest.raises(CitationAuditError, match="1..20"):
        citation_audit.validate_review_rows(tuple(rows), sample)


def test_partially_reviewed_sample_cannot_be_aggregated() -> None:
    sample = citation_audit.select_deterministic_sample(_population())
    rows = list(_pending_rows(sample))
    rows[0] = HumanReviewRow(
        evidence=sample[0],
        review_index=1,
        reviewer_status=ReviewerStatus.HUMAN_REVIEWED,
        human_support_verdict=SupportVerdict.SUPPORTED,
        reviewed_at="2026-09-01T00:00:00Z",
    )

    with pytest.raises(CitationAuditError, match="partially reviewed"):
        citation_audit.aggregate_human_review(tuple(rows), sample)


def test_blocked_csv_is_one_non_human_blocker_record() -> None:
    integrity = citation_audit.verify_day24_artifacts(REPO_ROOT)
    content = citation_audit.build_blocked_audit_csv(
        run_id=integrity.run_id,
        frozen_commit=integrity.frozen_commit,
        block_reason="insufficient sealed per-finding citation evidence",
    )

    citation_audit.validate_blocked_audit_csv(content, integrity)
    rows = tuple(csv.DictReader(io.StringIO(content.decode("utf-8"))))
    assert len(rows) == 1
    assert rows[0]["review_index"] == ""
    assert rows[0]["finding_id"] == ""
    assert rows[0]["human_support_verdict"] == ""


def test_blocked_csv_wrong_run_identity_is_rejected() -> None:
    integrity = citation_audit.verify_day24_artifacts(REPO_ROOT)
    content = citation_audit.build_blocked_audit_csv(
        run_id="wrong-run",
        frozen_commit=integrity.frozen_commit,
        block_reason="blocked",
    )

    with pytest.raises(CitationAuditError, match="identity"):
        citation_audit.validate_blocked_audit_csv(content, integrity)


def test_day25_aggregate_is_additive_and_preserves_day24_metrics() -> None:
    integrity = citation_audit.verify_day24_artifacts(REPO_ROOT)
    day24 = json.loads(
        (REPO_ROOT / citation_audit.DAY24_EVAL_PATH).read_text(encoding="utf-8")
    )
    raw = json.loads(
        (REPO_ROOT / citation_audit.DAY24_RAW_EVIDENCE_PATH).read_text(encoding="utf-8")
    )
    evidence = citation_audit.audit_evidence_sufficiency(raw)

    result = citation_audit.build_day25_aggregate(
        day24_eval=day24,
        integrity=integrity,
        evidence=evidence,
        audit_sha256="f" * 64,
    )

    assert result["day24_automated_evaluation"] == day24
    assert result["day24_automated_evaluation"]["detection"] == day24["detection"]
    assert result["day24_automated_evaluation"]["retrieval"] == day24["retrieval"]
    assert result["day24_automated_evaluation"]["agent"] == day24["agent"]
    assert result["day24_automated_evaluation"]["rerun_count"] == 0
    assert result["citation_support"]["status"] == "blocked"
    assert result["citation_support"]["strict_support_rate"] is None


def test_day25_helper_has_no_production_or_locked_runner_imports() -> None:
    source_path = Path(citation_audit.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    forbidden = {
        "app.agent",
        "app.scanner",
        "app.retrieval",
        "app.reporting",
        "app.evaluation.locked",
    }

    assert imports.isdisjoint(forbidden)
    assert imported_names.isdisjoint(forbidden)


def test_day25_helper_source_has_no_network_or_execution_capability() -> None:
    source = Path(citation_audit.__file__).read_text(encoding="utf-8")

    for forbidden in ("subprocess", "socket", "httpx", "requests", "urlopen", "exec("):
        assert forbidden not in source
