from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.evaluation.detection import (
    DETECTION_CANDIDATE_ARTIFACT_PATH,
    DetectionCandidateStatus,
    load_detection_candidate_artifact,
    validate_detection_candidate_files,
)
from app.scanner import RuleCategory


def test_day15_day16_candidates_are_strict_small_projects_with_real_gold() -> None:
    repo_root = Path(__file__).parents[2]
    artifact = load_detection_candidate_artifact(
        repo_root / DETECTION_CANDIDATE_ARTIFACT_PATH
    )

    summary = validate_detection_candidate_files(artifact, repo_root=repo_root)

    assert artifact.status is DetectionCandidateStatus.CANDIDATE
    assert summary.fixture_count == 10
    assert summary.python_file_count == 13
    assert summary.positive_label_count == 35
    assert summary.negative_label_count == 20
    assert summary.one_hop_positive_label_count == 3
    assert summary.one_hop_negative_label_count == 1
    assert summary.min_python_loc >= 30
    assert summary.max_python_loc <= 200


def test_candidates_cover_all_eight_rules_with_positive_and_negative_gold() -> None:
    repo_root = Path(__file__).parents[2]
    artifact = load_detection_candidate_artifact(
        repo_root / DETECTION_CANDIDATE_ARTIFACT_PATH
    )
    labels_by_category = Counter(
        (label.rule_category, label.expected) for label in artifact.labels
    )

    for category in (
        RuleCategory.CONFIG,
        RuleCategory.VALIDATOR,
        RuleCategory.SETTINGS,
        RuleCategory.ROOT_MODEL,
        RuleCategory.BASE_MODEL_METHOD,
        RuleCategory.DATA_LOADING,
        RuleCategory.FIELD,
        RuleCategory.GENERIC_MODEL,
    ):
        assert labels_by_category[(category, True)] >= 1
        assert labels_by_category[(category, False)] >= 1


def test_candidate_gold_uses_only_fixed_official_chunk_headings() -> None:
    repo_root = Path(__file__).parents[2]
    artifact = load_detection_candidate_artifact(
        repo_root / DETECTION_CANDIDATE_ARTIFACT_PATH
    )

    summary = validate_detection_candidate_files(artifact, repo_root=repo_root)

    assert summary.gold_heading_count == 6
    assert summary.gold_headings == (
        ("Migration guide", "Changes to `pydantic.BaseModel`"),
        ("Migration guide", "Changes to `pydantic.Field`"),
        ("Migration guide", "Changes to `pydantic.generics.GenericModel`"),
        ("Migration guide", "Changes to config"),
        ("Migration guide", "Changes to validators"),
        (
            "Migration guide",
            "`BaseSettings` has moved to `pydantic-settings`",
        ),
    )


def test_day17_importer_gold_is_separate_from_finding_gold() -> None:
    repo_root = Path(__file__).parents[2]
    artifact = load_detection_candidate_artifact(
        repo_root / DETECTION_CANDIDATE_ARTIFACT_PATH
    )

    day15_day16_labels = tuple(
        label for label in artifact.labels if not label.fixture_id.startswith("day17-")
    )
    assert sum(label.expected for label in day15_day16_labels) == 33
    assert sum(not label.expected for label in day15_day16_labels) == 20
    assert {
        (
            label.direct_file,
            label.importer_file,
            label.expected,
        )
        for label in artifact.one_hop_importer_labels
    } == {
        ("project/models.py", "project/service.py", True),
        ("project/models.py", "project/features/api.py", False),
        ("project/service.py", "project/features/api.py", True),
        ("project/service.py", "project/models.py", True),
    }
