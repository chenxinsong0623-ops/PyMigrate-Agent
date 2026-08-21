from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from app.evaluation.detection import (
    DETECTION_CANDIDATE_ARTIFACT_PATH,
    DetectionFixture,
    load_detection_candidate_artifact,
)
from app.scanner import ASTScanner, RuleScanner
from app.security import ZipGuard


@pytest.mark.parametrize(
    "fixture_id",
    [
        "day15-config-positive",
        "day15-negatives",
        "day15-root-model-positive",
        "day15-settings-positive",
        "day15-validator-positive",
        "day16-base-model-methods",
        "day16-data-loading",
        "day16-field",
        "day16-generic-model",
    ],
)
def test_candidate_gold_matches_real_zip_ast_rule_chain(
    tmp_path: Path,
    fixture_id: str,
) -> None:
    repo_root = Path(__file__).parents[2]
    artifact = load_detection_candidate_artifact(
        repo_root / DETECTION_CANDIDATE_ARTIFACT_PATH
    )
    fixture = next(item for item in artifact.fixtures if item.fixture_id == fixture_id)
    archive = _zip_fixture(tmp_path / f"{fixture_id}.zip", repo_root, fixture)

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        result = RuleScanner().scan(ASTScanner().scan(validated))

    actual_keys = {
        (
            finding.relative_path,
            finding.location.start_line,
            finding.rule_id,
        )
        for finding in result.findings
    }
    positive_keys = {
        (label.file, label.start_line, label.rule_id)
        for label in artifact.labels
        if label.fixture_id == fixture_id and label.expected
    }
    negative_keys = {
        (label.file, label.start_line, label.rule_id)
        for label in artifact.labels
        if label.fixture_id == fixture_id and not label.expected
    }

    assert actual_keys == positive_keys
    assert actual_keys.isdisjoint(negative_keys)


def _zip_fixture(
    archive_path: Path,
    repo_root: Path,
    fixture: DetectionFixture,
) -> Path:
    fixture_root = repo_root.joinpath(*fixture.relative_directory.split("/"))
    with zipfile.ZipFile(archive_path, "w") as archive:
        for relative_path in fixture.python_files:
            info = zipfile.ZipInfo(relative_path)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, (fixture_root / relative_path).read_bytes())
    return archive_path
